"""HTTP/cache helpers and concurrency stats for boe_downloader_eli."""

from __future__ import annotations

import asyncio
import email.utils
import hashlib
import json
import os
import secrets
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import aiofiles  # type: ignore[import-untyped]
import aiofiles.os  # type: ignore[import-untyped]
import aiohttp


@dataclass
class StoredMeta:
    """Metadata persisted alongside cached responses."""

    etag: Optional[str] = None
    last_modified: Optional[str] = None
    sha256: Optional[str] = None
    content_type: Optional[str] = None
    fetched_at_utc: Optional[str] = None


class RetryableHTTPError(RuntimeError):
    """Signals an HTTP response that should be retried."""

    def __init__(
        self,
        status: int,
        url: str,
        retry_after_s: float | None = None,
        msg: str | None = None,
    ) -> None:
        super().__init__(msg or f"HTTP {status} retryable for {url}")
        self.status = status
        self.url = url
        self.retry_after_s = retry_after_s


class NonRetryableHTTPError(RuntimeError):
    """Signals an HTTP response that should not be retried."""

    def __init__(self, status: int, url: str, msg: str | None = None) -> None:
        super().__init__(msg or f"HTTP {status} for {url}")
        self.status = status
        self.url = url


class RunStats:
    """Tracks per-run and windowed download metrics."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self.reset_window()
        self.total_done = 0
        self.total_ok = 0
        self.total_skipped_304 = 0
        self.total_errors = 0
        self.total_http429 = 0
        self.total_http5xx = 0
        self.total_bytes = 0
        self.max_concurrency_reached = 0
        self.max_concurrency_configured = 0

    def reset_window(self) -> None:
        """Reset the sliding window counters."""
        self.win_ok = 0
        self.win_err = 0
        self.win_429 = 0
        self.win_5xx = 0
        self.win_timeouts = 0
        self.win_lat: list[float] = []
        self.win_started = time.monotonic()

    async def record(
        self,
        *,
        status: int | None,
        latency_s: float,
        nbytes: int,
        timeout: bool = False,
    ) -> None:
        """Record metrics for a single request."""
        async with self._lock:
            self.total_done += 1
            if status == 304:
                self.total_skipped_304 += 1
            if status is not None and 200 <= status < 300:
                self.total_ok += 1
                self.win_ok += 1
            elif status == 304:
                pass
            else:
                self.total_errors += 1
                self.win_err += 1
            if status == 429:
                self.total_http429 += 1
                self.win_429 += 1
            if status is not None and status >= 500:
                self.total_http5xx += 1
                self.win_5xx += 1
            if timeout:
                self.win_timeouts += 1
            self.total_bytes += max(0, nbytes)
            self.win_lat.append(max(0.0, latency_s))

    async def snapshot_window(self) -> dict[str, float]:
        """Return and reset the current window metrics."""
        async with self._lock:
            dur = max(0.001, time.monotonic() - self.win_started)
            avg_lat = (sum(self.win_lat) / len(self.win_lat)) if self.win_lat else 0.0
            rps = (self.win_ok + self.win_err) / dur
            snap: dict[str, float] = {
                "duration_s": dur,
                "ok": self.win_ok,
                "err": self.win_err,
                "http429": self.win_429,
                "http5xx": self.win_5xx,
                "timeouts": self.win_timeouts,
                "avg_latency_s": avg_lat,
                "rps": rps,
            }
            self.reset_window()
            return snap


class AdaptiveLimiter:
    """Adjustable semaphore to raise/lower concurrency on the fly."""

    def __init__(self, max_limit: int, initial: int) -> None:
        self.max_limit = max(1, int(max_limit))
        self._sem = asyncio.Semaphore(self.max_limit)
        self._reserved = 0
        self._target = max(1, min(self.max_limit, int(initial)))
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Apply initial target reservations."""
        await self.set_target(self._target)

    async def _set_reserved(self, desired_reserved: int) -> None:
        desired_reserved = max(0, min(self.max_limit - 1, int(desired_reserved)))
        while self._reserved < desired_reserved:
            await self._sem.acquire()
            self._reserved += 1
        while self._reserved > desired_reserved:
            self._sem.release()
            self._reserved -= 1

    async def set_target(self, target: int) -> int:
        """Update the target concurrency."""
        target = max(1, min(self.max_limit, int(target)))
        async with self._lock:
            self._target = target
            desired_reserved = self.max_limit - self._target
        await self._set_reserved(desired_reserved)
        return self._target

    async def get_target(self) -> int:
        """Return the current target concurrency."""
        async with self._lock:
            return self._target

    async def acquire(self) -> None:
        """Acquire a unit from the limiter."""
        await self._sem.acquire()

    def release(self) -> None:
        """Release a unit back to the limiter."""
        self._sem.release()


def sha256_bytes(payload: bytes) -> str:
    """Compute a SHA256 for a byte payload."""
    return hashlib.sha256(payload).hexdigest()


async def stream_to_file_and_hash(
    resp, path: str, chunk_size: int = 1024 * 256
) -> tuple[str, int]:
    """Stream response body to disk while computing sha256."""
    h = hashlib.sha256()
    n = 0
    os.makedirs(os.path.dirname(path), exist_ok=True)
    async with aiofiles.open(path, "wb") as f:
        async for chunk in resp.content.iter_chunked(chunk_size):
            if not chunk:
                continue
            h.update(chunk)
            n += len(chunk)
            await f.write(chunk)
    return h.hexdigest(), n


def ensure_dirs(store_dir: str) -> None:
    """Ensure local cache directories exist."""
    os.makedirs(os.path.join(store_dir, "data"), exist_ok=True)
    os.makedirs(os.path.join(store_dir, "meta"), exist_ok=True)
    os.makedirs(os.path.join(store_dir, "index"), exist_ok=True)


def url_key(url: str) -> str:
    """Return a stable cache key for a URL."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def secure_uniform(low: float, high: float) -> float:
    """Return a cryptographically-secure float in [low, high]."""
    scale = 1_000_000
    return low + (high - low) * (secrets.randbelow(scale) / scale)


def paths_for_url(store_dir: str, url: str) -> Tuple[str, str]:
    """Return (data_path, meta_path) for a given URL."""
    k = url_key(url)
    data_path = os.path.join(store_dir, "data", f"{k}.bin")
    meta_path = os.path.join(store_dir, "meta", f"{k}.json")
    return data_path, meta_path


def index_path(store_dir: str, name: str) -> str:
    """Return the manifest path for a named index file."""
    return os.path.join(store_dir, "index", name)


async def load_meta(meta_path: str) -> StoredMeta:
    """Load cached metadata from disk if present."""
    try:
        if not await aiofiles.os.path.exists(meta_path):
            return StoredMeta()
        async with aiofiles.open(meta_path, "r", encoding="utf-8") as f:
            return StoredMeta(**json.loads(await f.read()))
    except Exception:
        return StoredMeta()


async def save_meta(meta_path: str, meta: StoredMeta) -> None:
    """Persist cached metadata to disk."""
    os.makedirs(os.path.dirname(meta_path), exist_ok=True)
    async with aiofiles.open(meta_path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(asdict(meta), ensure_ascii=False, indent=2))


def parse_retry_after(value: str) -> float | None:
    """Parse Retry-After header into seconds."""
    value = (value or "").strip()
    if not value:
        return None
    if value.isdigit():
        return float(value)
    try:
        dt = email.utils.parsedate_to_datetime(value)
        if dt is None:
            return None
        if dt.tzinfo is None:
            now = datetime.utcnow()
            return max(0.0, (dt - now).total_seconds())
        now = datetime.now(dt.tzinfo)
        return max(0.0, (dt - now).total_seconds())
    except Exception:
        return None


async def autotune_concurrency(
    limiter: AdaptiveLimiter,
    stats: RunStats,
    *,
    start: int,
    max_limit: int,
    cpu_high: float,
    cpu_low: float,
    interval_s: float = 5.0,
    cpu_sample,
) -> None:
    """Adjust concurrency using AIMD based on runtime stats."""
    proc = cpu_sample()
    baseline: float | None = None
    await limiter.set_target(start)
    while True:
        await asyncio.sleep(interval_s)
        snap = await stats.snapshot_window()
        cur = await limiter.get_target()
        cpu_val = proc.cpu_percent(interval=None) if proc is not None else None

        if snap["rps"] > 0 and baseline is None and snap["avg_latency_s"] > 0:
            baseline = snap["avg_latency_s"]

        congested = (
            (snap["http429"] > 0) or (snap["http5xx"] > 0) or (snap["timeouts"] > 0)
        )
        if cpu_val is not None and cpu_val >= cpu_high:
            congested = True
        if baseline is not None and snap["avg_latency_s"] > 0 and snap["err"] > 0:
            if snap["avg_latency_s"] >= 2.0 * baseline:
                congested = True

        if congested:
            new = max(1, int(cur * 0.7))
            await limiter.set_target(new)
        else:
            if cpu_val is not None and cpu_val > cpu_low:
                await limiter.set_target(cur)
            else:
                if cur < max_limit:
                    await limiter.set_target(cur + 1)

        tgt = await limiter.get_target()
        stats.max_concurrency_reached = max(stats.max_concurrency_reached, tgt)


def cache_exists(path: str) -> bool:
    """Return True if a cache path exists and is non-empty."""
    try:
        return os.path.exists(path) and os.path.getsize(path) > 0
    except OSError:
        return False


def build_headers(*, accept: str, meta: StoredMeta, no_cache: bool) -> dict[str, str]:
    """Build conditional headers for cache-aware requests."""
    headers = {"Accept": accept}
    if not no_cache:
        if meta.etag:
            headers["If-None-Match"] = meta.etag
        if meta.last_modified:
            headers["If-Modified-Since"] = meta.last_modified
    return headers


def update_meta_from_headers(meta: StoredMeta, headers: Any) -> None:
    """Update cached metadata from response headers."""
    if headers.get("ETag"):
        meta.etag = headers.get("ETag")
    if headers.get("Last-Modified"):
        meta.last_modified = headers.get("Last-Modified")
    if headers.get("Content-Type"):
        meta.content_type = headers.get("Content-Type")


def debug_http_event(enabled: bool, message: str) -> None:
    """Print a debug line for HTTP tracing."""
    if enabled:
        print(message)


def read_cache_bytes(data_path: str) -> bytes | None:
    """Read cached bytes if present."""
    if not cache_exists(data_path):
        return None
    with open(data_path, "rb") as f:
        return f.read()


async def write_bytes_to_cache(
    *, data_path: str, meta_path: str, content: bytes, meta: StoredMeta
) -> None:
    """Write response bytes and metadata to cache."""
    os.makedirs(os.path.dirname(data_path), exist_ok=True)
    async with aiofiles.open(data_path, "wb") as f:
        await f.write(content)
    await save_meta(meta_path, meta)


async def stream_response_to_cache(
    *,
    resp,
    data_path: str,
    meta_path: str,
    meta: StoredMeta,
) -> tuple[str, int]:
    """Stream response body to cache and update metadata."""
    sha256, nbytes = await stream_to_file_and_hash(resp, data_path)
    meta.sha256 = sha256
    await save_meta(meta_path, meta)
    return sha256, nbytes


def compute_backoff_sleep(
    *,
    use_decorrelated: bool,
    sleep_s: float,
    base_delay_s: float,
    cap_delay_s: float,
    attempt: int,
) -> float:
    """Compute a backoff interval for a retry attempt."""
    if use_decorrelated:
        upper = min(cap_delay_s, sleep_s * 3.0)
        return secure_uniform(base_delay_s, upper)
    backoff = min(cap_delay_s, base_delay_s * (2 ** (attempt - 1)))
    return secure_uniform(0, backoff)


def handle_not_modified(
    *,
    data_path: str,
    meta: StoredMeta,
    return_bytes: bool,
    headers: Dict[str, str],
) -> tuple[bytes | None, StoredMeta, int, Dict[str, str]]:
    """Handle 304 responses, optionally returning cached bytes."""
    if return_bytes:
        cached = read_cache_bytes(data_path)
        if cached is not None:
            return cached, meta, 304, headers
    return None, meta, 304, headers


async def retry_without_conditionals(
    *,
    session: aiohttp.ClientSession,
    url: str,
    accept: str,
    data_path: str,
    meta_path: str,
    return_bytes: bool,
    debug_http: bool,
    debug_http_all: bool,
) -> tuple[bytes | None, StoredMeta, int, Dict[str, str]]:
    """Retry a request without conditional headers (no-cache)."""
    meta = StoredMeta()
    headers = {"Accept": accept}
    if debug_http:
        debug_http_event(
            debug_http_all,
            f"[HTTP DEBUG] RETRY NO-CACHE GET {url} headers={headers}",
        )
    async with session.get(url, headers=headers) as resp:
        status = resp.status
        if status == 304:
            return handle_not_modified(
                data_path=data_path,
                meta=meta,
                return_bytes=return_bytes,
                headers=dict(resp.headers),
            )
        update_meta_from_headers(meta, resp.headers)
        if return_bytes:
            content = await resp.read()
            await write_bytes_to_cache(
                data_path=data_path,
                meta_path=meta_path,
                content=content,
                meta=meta,
            )
            return content, meta, status, dict(resp.headers)
        await stream_response_to_cache(
            resp=resp,
            data_path=data_path,
            meta_path=meta_path,
            meta=meta,
        )
        return None, meta, status, dict(resp.headers)


async def fetch_with_cache(
    *,
    session: aiohttp.ClientSession,
    store_dir: str,
    url: str,
    accept: str,
    retries: int,
    base_delay_s: float,
    cap_delay_s: float,
    jitter: str,
    return_bytes: bool = False,
    debug_http: bool = False,
    debug_http_all: bool = False,
    no_cache: bool = False,
) -> tuple[bytes | None, StoredMeta, int, Dict[str, str]]:
    """Fetch a URL with conditional caching and retry logic."""
    data_path, meta_path = paths_for_url(store_dir, url)
    meta = await load_meta(meta_path)
    headers = build_headers(accept=accept, meta=meta, no_cache=no_cache)

    if debug_http:
        debug_http_event(
            debug_http_all,
            f"[HTTP DEBUG] REQUEST GET {url} headers={headers}",
        )

    attempt = 0
    sleep_s = base_delay_s
    last_exc: Exception | None = None
    use_decorrelated = jitter == "decorrelated"

    while attempt < retries:
        attempt += 1
        try:
            async with session.get(url, headers=headers) as resp:
                status = resp.status
                if status == 304:
                    return handle_not_modified(
                        data_path=data_path,
                        meta=meta,
                        return_bytes=return_bytes,
                        headers=dict(resp.headers),
                    )

                if status == 412 and not no_cache:
                    return await retry_without_conditionals(
                        session=session,
                        url=url,
                        accept=accept,
                        data_path=data_path,
                        meta_path=meta_path,
                        return_bytes=return_bytes,
                        debug_http=debug_http,
                        debug_http_all=debug_http_all,
                    )

                if status >= 400:
                    body = await resp.read()
                    if debug_http:
                        print(
                            f"[HTTP DEBUG] ERROR BODY (first 200 bytes): {body[:200]!r}\n"
                        )
                    if status in (429, 503) or status >= 500:
                        ra = parse_retry_after(resp.headers.get("Retry-After", ""))
                        raise RetryableHTTPError(
                            status=status,
                            url=url,
                            retry_after_s=ra,
                            msg=f"HTTP {status} retryable: {body[:200]!r}",
                        )
                    raise NonRetryableHTTPError(
                        status=status, url=url, msg=f"HTTP {status}: {body[:200]!r}"
                    )

                update_meta_from_headers(meta, resp.headers)
                if return_bytes:
                    content = await resp.read()
                    await write_bytes_to_cache(
                        data_path=data_path,
                        meta_path=meta_path,
                        content=content,
                        meta=meta,
                    )
                    return content, meta, status, dict(resp.headers)

                await stream_response_to_cache(
                    resp=resp, data_path=data_path, meta_path=meta_path, meta=meta
                )
                return None, meta, status, dict(resp.headers)

        except NonRetryableHTTPError:
            raise
        except RetryableHTTPError as e:
            last_exc = e
            if attempt >= retries:
                break
            if e.retry_after_s and e.retry_after_s > 0:
                await asyncio.sleep(min(cap_delay_s, e.retry_after_s))
                continue
            sleep_s = compute_backoff_sleep(
                use_decorrelated=use_decorrelated,
                sleep_s=sleep_s,
                base_delay_s=base_delay_s,
                cap_delay_s=cap_delay_s,
                attempt=attempt,
            )
            await asyncio.sleep(sleep_s)

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            last_exc = e
            if attempt >= retries:
                break
            sleep_s = compute_backoff_sleep(
                use_decorrelated=use_decorrelated,
                sleep_s=sleep_s,
                base_delay_s=base_delay_s,
                cap_delay_s=cap_delay_s,
                attempt=attempt,
            )
            await asyncio.sleep(sleep_s)

        except Exception as e:
            last_exc = e
            if attempt >= retries:
                break
            await asyncio.sleep(min(cap_delay_s, base_delay_s * attempt))

    raise RuntimeError(
        f"Failed fetching {url} after {retries} retries. Last error: {last_exc}"
    )
