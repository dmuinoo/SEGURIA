"""Download pipeline and Rich UI helpers for boe_downloader_eli."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import aiofiles  # type: ignore[import-untyped]
import aiofiles.os  # type: ignore[import-untyped]
import aiohttp
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from boe_downloader_web import WebState

from boe_downloader_db import DbCtx

from boe_downloader_http import (
    AdaptiveLimiter,
    RunStats,
    fetch_with_cache,
    index_path,
    paths_for_url,
)

try:
    import psutil as psutil_module  # type: ignore
except ImportError:  # pragma: no cover
    psutil_module = None  # type: ignore


def make_console(progress: bool) -> "Console":
    """Create a Rich Console respecting TTY conditions."""
    return Console(force_terminal=progress, force_interactive=progress)


def make_status_panel(
    *,
    run_id: str,
    cmd: str,
    stats: RunStats,
    concurrency: int,
    cpu_pct: str,
    rss_mb: str,
) -> Panel:
    """Build the Rich status panel with current metrics."""
    table = Table.grid(expand=True)
    table.add_column(justify="left")
    table.add_column(justify="right")
    table.add_row("run_id", run_id)
    table.add_row("cmd", cmd)
    table.add_row("concurrency(target)", str(concurrency))
    table.add_row("cpu", cpu_pct)
    table.add_row("ram_rss_mb", rss_mb)
    table.add_row("done", str(stats.total_done))
    table.add_row("ok", str(stats.total_ok))
    table.add_row("skipped_304", str(stats.total_skipped_304))
    table.add_row("errors", str(stats.total_errors))
    table.add_row("http_429", str(stats.total_http429))
    table.add_row("http_5xx", str(stats.total_http5xx))
    table.add_row("bytes", str(stats.total_bytes))
    table.add_row("concurrency_max_cfg", str(stats.max_concurrency_configured))
    table.add_row("max_concurrency_reached", str(stats.max_concurrency_reached))
    return Panel(table, title="Estado", border_style="cyan")


async def run_queue_download(
    *,
    session,
    store_dir: str,
    cmd: str,
    items: list[Dict[str, Any]],
    accept: str,
    manifest_file: str,
    limiter: AdaptiveLimiter,
    stats: RunStats,
    run_id: str,
    progress: bool,
    ui_refresh: int,
    retries: int,
    base_delay: float,
    cap_delay: float,
    jitter: str,
    debug_http: bool = False,
    debug_http_all: bool = False,
    no_cache: bool = False,
    db: DbCtx | None = None,
    web_state: WebState | None = None,
) -> None:
    """Download items concurrently with cache and optional UI."""
    manifest_path = index_path(store_dir, manifest_file)
    manifest_lock = asyncio.Lock()
    q: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
    for it in items:
        q.put_nowait(it)

    if web_state is not None:
        web_state.set_run_info(run_id, cmd)
        web_state.set_status("RUNNING")
        web_state.set_timestamp()
        web_state.set_total(len(items))
        web_state.set_concurrency(await limiter.get_target())
        web_state.set_limits(
            stats.max_concurrency_configured,
            stats.max_concurrency_reached,
        )

    console = make_console(progress)
    prog = Progress(
        SpinnerColumn(),
        TextColumn("[bold]Descargando[/bold]"),
        BarColumn(),
        TextColumn("{task.percentage:>3.0f}%"),
        TextColumn("•"),
        TextColumn("[dim]transcurrido[/dim]"),
        TimeElapsedColumn(),
        TextColumn("•"),
        TextColumn("[dim]ETA[/dim]"),
        TimeRemainingColumn(),
        console=console,
        refresh_per_second=ui_refresh,
        transient=False,
    )
    task_id = prog.add_task("download", total=len(items))

    async def write_manifest(obj: Dict[str, Any]) -> None:
        payload = dict(obj)
        payload["run_id"] = run_id
        payload["cmd"] = cmd
        payload["ts_utc"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        line = json.dumps(payload, ensure_ascii=False)
        async with manifest_lock:
            async with aiofiles.open(manifest_path, "a", encoding="utf-8") as f:
                await f.write(line + "\n")

    async def resolve_nbytes(content: Optional[bytes], url: str) -> int:
        if content is not None:
            return len(content)
        data_path, _ = paths_for_url(store_dir, url)
        try:
            st = await aiofiles.os.stat(data_path)
            return st.st_size
        except FileNotFoundError:
            return 0

    def infer_format(url: str, accept_header: str) -> str:
        url_lower = url.lower()
        if url_lower.endswith(".pdf") or "/pdfs/" in url_lower:
            return "pdf"
        accept_lower = (accept_header or "").lower()
        if "application/json" in accept_lower:
            return "json"
        if "application/xml" in accept_lower:
            return "xml"
        return "xml"

    def storage_uri_to_path(uri: str | None) -> str | None:
        if not uri:
            return None
        parsed = urlparse(uri)
        path_val = parsed.path if parsed.scheme else uri
        return path_val or None

    async def ensure_payload_copy(fmt: str, sha256: str | None, data_path: str) -> str | None:
        if not sha256:
            return None
        if fmt == "xml":
            ext = "xml"
        elif fmt == "json":
            ext = "json"
        else:
            ext = "pdf"
        fmt_dir = Path(store_dir) / fmt
        fmt_dir.mkdir(parents=True, exist_ok=True)
        payload_path = fmt_dir / f"{sha256}.{ext}"
        if payload_path.exists():
            return str(payload_path)
        try:
            async with aiofiles.open(data_path, "rb") as src:
                async with aiofiles.open(payload_path, "wb") as dst:
                    while True:
                        chunk = await src.read(1024 * 1024)
                        if not chunk:
                            break
                        await dst.write(chunk)
        except FileNotFoundError:
            return None
        return str(payload_path)

    async def resolve_existing_payload(
        fmt: str,
        sha_existing: str | None,
        storage_uri_existing: str | None,
    ) -> str | None:
        if storage_uri_existing:
            path_val = storage_uri_to_path(storage_uri_existing)
            if path_val:
                if await aiofiles.os.path.exists(path_val):
                    return path_val
        if not sha_existing:
            return None
        if fmt == "xml":
            ext = "xml"
        elif fmt == "json":
            ext = "json"
        else:
            ext = "pdf"
        candidate = Path(store_dir) / fmt / f"{sha_existing}.{ext}"
        if await aiofiles.os.path.exists(str(candidate)):
            return str(candidate)
        return None

    def cpu_mem_snapshot(proc: Optional["psutil_module.Process"]) -> tuple[str, str]:
        if proc is None:
            return "n/a", "n/a"
        cpu_val = proc.cpu_percent(interval=None)
        cpu_pct = f"{cpu_val:.1f}%"
        rss = proc.memory_info().rss / 1024 / 1024
        mem_pct = proc.memory_percent()
        return cpu_pct, f"{rss:.1f} MB ({mem_pct:.1f}%)"

    async def update_live_panel(
        live: Live, proc: Optional["psutil_module.Process"]
    ) -> None:
        cur = await limiter.get_target()
        cpu_pct, rss_mb = cpu_mem_snapshot(proc)
        if web_state is not None:
            web_state.set_system(cpu_pct, rss_mb)
            web_state.set_timestamp()
            web_state.sync_totals(
                done=stats.total_done,
                ok=stats.total_ok,
                skipped_304=stats.total_skipped_304,
                errors=stats.total_errors,
                http_429=stats.total_http429,
                http_5xx=stats.total_http5xx,
                bytes_total=stats.total_bytes,
            )
        grid = Table.grid(padding=(0, 1))
        grid.add_row(
            Panel.fit(prog.get_renderable(), title="Progreso", border_style="green"),
            make_status_panel(
                run_id=run_id,
                cmd=cmd,
                stats=stats,
                concurrency=cur,
                cpu_pct=cpu_pct,
                rss_mb=rss_mb,
            ),
        )
        live.update(grid)

    async def handle_one(it: Dict[str, Any]) -> None:
        status: int | None = None
        nbytes = 0
        timeout = False
        attempt_id: str | None = None
        resource_id = "NO_DB"
        response_headers: Dict[str, str] = {}
        t0 = time.monotonic()
        url = ""
        key: str | None = None
        fmt = ""
        source_kind = cmd
        data_path = ""
        try:
            url = it.get("url") or ""
            if not url:
                raise KeyError("url")
            key = it.get("key") or url
            fmt = it.get("fmt") or infer_format(url, accept)
            source_kind = it.get("source_kind") or cmd
            data_path, _ = paths_for_url(store_dir, url)
            if db is not None:
                url_xml = url if fmt == "xml" else None
                url_json = url if fmt == "json" else None
                url_pdf = url if fmt == "pdf" else None
                resource_id = await db.upsert_resource(
                    source_kind, str(key), url_xml, url_json, url_pdf
                )
                downloaded, sha_existing, storage_uri_existing = (
                    await db.get_resource_format_status(resource_id, fmt)
                )
                payload_path = await resolve_existing_payload(
                    fmt, sha_existing, storage_uri_existing
                )
                if downloaded and payload_path:
                    status = 304
                    try:
                        st = await aiofiles.os.stat(payload_path)
                        nbytes = st.st_size
                    except FileNotFoundError:
                        nbytes = 0
                    await write_manifest(
                        {
                            "key": key,
                            "url": url,
                            "ok": True,
                            "status": 304,
                            "content_type": None,
                            "etag": None,
                            "last_modified": None,
                            "sha256": sha_existing,
                            "fetched_at_utc": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                        }
                    )
                    return
                attempt_id = await db.attempt_start(resource_id, fmt, url, accept)
            content, meta, status, response_headers = await fetch_with_cache(
                session=session,
                store_dir=store_dir,
                url=url,
                accept=accept,
                retries=retries,
                base_delay_s=base_delay,
                cap_delay_s=cap_delay,
                jitter=jitter,
                return_bytes=False,
                debug_http=debug_http,
                debug_http_all=debug_http_all,
                no_cache=no_cache,
            )
            nbytes = await resolve_nbytes(content, url)
            await write_manifest(
                {
                    "key": key,
                    "url": url,
                    "ok": (status is not None and status < 400),
                    "status": status,
                    "content_type": meta.content_type,
                    "etag": meta.etag,
                    "last_modified": meta.last_modified,
                    "sha256": meta.sha256,
                    "fetched_at_utc": meta.fetched_at_utc,
                }
            )
            storage_path = await ensure_payload_copy(fmt, meta.sha256, data_path)
            storage_uri = (
                f"file://{Path(storage_path).resolve()}" if storage_path else None
            )
            content_length = None
            if response_headers:
                clen = response_headers.get("Content-Length")
                if clen and clen.isdigit():
                    content_length = int(clen)
            if db is not None and attempt_id is not None:
                await db.attempt_finish(
                    attempt_id,
                    duration_ms=int((time.monotonic() - t0) * 1000),
                    http_status=status,
                    headers=response_headers,
                    content_type=meta.content_type,
                    content_length=content_length or nbytes or None,
                    sha256=meta.sha256,
                    storage_uri=storage_uri,
                    error_type=None,
                    error_detail=None,
                )
                if status == 304:
                    await db.update_resource_format_not_modified(
                        resource_id, fmt, True, datetime.utcnow(), status
                    )
                else:
                    await db.update_resource_format(
                        resource_id,
                        fmt,
                        status is not None and status < 400,
                        datetime.utcnow(),
                        status,
                        meta.sha256,
                        storage_uri,
                        None,
                    )
        except aiohttp.ClientResponseError as e:
            status = e.status
            safe_url = url or "<missing>"
            await write_manifest(
                {
                    "key": key or safe_url,
                    "url": safe_url,
                    "ok": False,
                    "status": status,
                    "error": str(e),
                }
            )
            if db is not None and attempt_id is not None:
                await db.attempt_finish(
                    attempt_id,
                    duration_ms=int((time.monotonic() - t0) * 1000),
                    http_status=status,
                    headers=response_headers,
                    content_type=None,
                    content_length=None,
                    sha256=None,
                    storage_uri=None,
                    error_type="http",
                    error_detail=str(e),
                )
                await db.update_resource_format(
                    resource_id,
                    fmt,
                    False,
                    datetime.utcnow(),
                    status,
                    None,
                    None,
                    str(e),
                )
        except asyncio.TimeoutError as e:
            timeout = True
            safe_url = url or "<missing>"
            await write_manifest(
                {
                    "key": key or safe_url,
                    "url": safe_url,
                    "ok": False,
                    "status": None,
                    "error": f"timeout: {e}",
                }
            )
            if db is not None and attempt_id is not None:
                await db.attempt_finish(
                    attempt_id,
                    duration_ms=int((time.monotonic() - t0) * 1000),
                    http_status=None,
                    headers=response_headers,
                    content_type=None,
                    content_length=None,
                    sha256=None,
                    storage_uri=None,
                    error_type="timeout",
                    error_detail=str(e),
                )
                await db.update_resource_format(
                    resource_id,
                    fmt,
                    False,
                    datetime.utcnow(),
                    None,
                    None,
                    None,
                    f"timeout: {e}",
                )
        except Exception as e:
            safe_url = url or "<missing>"
            await write_manifest(
                {
                    "key": key or safe_url,
                    "url": safe_url,
                    "ok": False,
                    "status": status,
                    "error": str(e),
                }
            )
            if db is not None and attempt_id is not None:
                await db.attempt_finish(
                    attempt_id,
                    duration_ms=int((time.monotonic() - t0) * 1000),
                    http_status=status,
                    headers=response_headers,
                    content_type=None,
                    content_length=None,
                    sha256=None,
                    storage_uri=None,
                    error_type="client",
                    error_detail=str(e),
                )
                await db.update_resource_format(
                    resource_id,
                    fmt,
                    False,
                    datetime.utcnow(),
                    status,
                    None,
                    None,
                    str(e),
                )
        finally:
            await stats.record(
                status=status,
                latency_s=(time.monotonic() - t0),
                nbytes=nbytes,
                timeout=timeout,
            )
            prog.update(task_id, advance=1)
            if web_state is not None:
                web_state.update_item(
                    status=status,
                    nbytes=nbytes,
                    url=url or "<missing>",
                    timeout=timeout,
                    format_hint=accept,
                )
                web_state.set_concurrency(await limiter.get_target())
                web_state.set_limits(
                    stats.max_concurrency_configured,
                    stats.max_concurrency_reached,
                )

    async def worker() -> None:
        while True:
            try:
                it = q.get_nowait()
            except asyncio.QueueEmpty:
                return
            await limiter.acquire()
            try:
                await handle_one(it)
            finally:
                limiter.release()
                q.task_done()

    workers = [asyncio.create_task(worker()) for _ in range(limiter.max_limit)]

    stop_event = asyncio.Event()
    web_system_task = None

    proc = psutil_module.Process() if psutil_module is not None else None  # type: ignore
    if proc is not None:
        try:
            proc.cpu_percent(interval=None)
        except Exception:
            proc = None

    async def web_system_loop() -> None:
        if web_state is None:
            return
        while not stop_event.is_set():
            cpu_pct, rss_mb = cpu_mem_snapshot(proc)
            web_state.set_system(cpu_pct, rss_mb)
            web_state.set_timestamp()
            web_state.sync_totals(
                done=stats.total_done,
                ok=stats.total_ok,
                skipped_304=stats.total_skipped_304,
                errors=stats.total_errors,
                http_429=stats.total_http429,
                http_5xx=stats.total_http5xx,
                bytes_total=stats.total_bytes,
            )
            web_state.set_concurrency(await limiter.get_target())
            web_state.set_limits(
                stats.max_concurrency_configured,
                stats.max_concurrency_reached,
            )
            await asyncio.sleep(0.8)

    if web_state is not None:
        web_system_task = asyncio.create_task(web_system_loop())

    if progress:
        with Live(console=console, refresh_per_second=ui_refresh or 8) as live:
            while not prog.finished:
                await update_live_panel(live, proc)
                await asyncio.sleep(0.3)
            await update_live_panel(live, proc)

    await q.join()

    if web_state is not None:
        web_state.set_status("DONE")
        web_state.set_timestamp()
        web_state.sync_totals(
            done=stats.total_done,
            ok=stats.total_ok,
            skipped_304=stats.total_skipped_304,
            errors=stats.total_errors,
            http_429=stats.total_http429,
            http_5xx=stats.total_http5xx,
            bytes_total=stats.total_bytes,
        )

    stop_event.set()
    if web_system_task is not None:
        web_system_task.cancel()
        await asyncio.gather(web_system_task, return_exceptions=True)

    for w in workers:
        w.cancel()
    await asyncio.gather(*workers, return_exceptions=True)
