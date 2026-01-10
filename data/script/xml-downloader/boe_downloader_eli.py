#!/usr/bin/env python3
"""
boe_downloader_eli.py

Downloader/ingestor para BOE (orientado a ELI) con:

- Descarga del catálogo de legislación consolidada (solo items con url_eli) y
  descarga del XML consolidado por doc_id.
- Descarga del sumario BOE diario (AAAAMMDD) y descarga del XML de cada item
  (url_xml).
- Caché HTTP condicional (ETag / Last-Modified) -> 304 no reescribe.
- Manifest JSONL (index/) con run_id, status, hashes, etc.
- Concurrencia fija o AUTO (AIMD) para adaptarse a rate limiting / saturación.
- Reintentos con backoff + decorrelated jitter, respetando Retry-After.
- Barra de progreso Rich con métricas (ok/errors/429, bytes, concurrency, etc.).

Uso (help):
  python3 boe_downloader_eli_optimized.py -h

Notas:
- Los payloads se guardan como .bin aunque sean XML/JSON para tratarlo como "bytes" opacos.
  El Content-Type real queda en meta/*.json y en el manifest.

Ejecucion:
- Maximo rendimiento
uv run python3 boe_downloader_eli_debugopt.py \
  --store ./boe_store \
  --concurrency auto --concurrency-start 10 --concurrency-max 25 \
  --progress \
  consolidada --part full --accept application/xml

- Depuracion eficiente (errores no-200)
uv run python3 boe_downloader_eli_debugopt.py \
  --store ./boe_store \
  --concurrency auto --concurrency-start 10 --concurrency-max 25 \
  --progress --debug-http \
  consolidada --part full --accept application/xml

"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import secrets
import sys
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List

import aiofiles  # type: ignore[import-untyped]
import aiofiles.os  # type: ignore[import-untyped]
import aiohttp
import asyncpg  # type: ignore[import-untyped]
from aiohttp import ClientSession
from rich.console import Console

from boe_downloader_db import DbCtx
from boe_downloader_parsing import (
    extract_boe_ids_from_sumario_bytes,
    extract_boe_ids_from_sumario_schema,
    extract_boe_ids_from_sumario_with_source,
    extract_sumario_item_urls,
    extract_urls_from_act_html,
    parse_boe_xml_to_model,
)

__all__ = [
    "extract_boe_ids_from_sumario_bytes",
    "extract_boe_ids_from_sumario_schema",
    "extract_boe_ids_from_sumario_with_source",
    "extract_urls_from_act_html",
    "parse_boe_xml_to_model",
]

from boe_downloader_http import (
    AdaptiveLimiter,
    RunStats,
    autotune_concurrency,
    ensure_dirs,
    fetch_with_cache,
    paths_for_url,
)
from boe_downloader_pipeline import make_console, make_status_panel, run_queue_download
from boe_downloader_web import WebState, start_web_server, stop_web_server


BOE_ID_RE = re.compile(r"BOE-[A-Z]-\d{4}-\d+")

# psutil es opcional: permite mostrar CPU/RAM en la barra de progreso.
try:
    import psutil as psutil_module  # type: ignore
except ImportError:  # pragma: no cover
    psutil_module = None  # type: ignore


BASE = "https://www.boe.es"
SUMARIO_API = f"{BASE}/datosabiertos/api/boe/sumario"  # + /{fecha}
LEGIS_API = f"{BASE}/datosabiertos/api/legislacion-consolidada"

DEFAULT_STORE = "./boe_store"
DEFAULT_TIMEOUT_S = 90
DEFAULT_RETRIES = 6
DEFAULT_BASE_DELAY = 0.5
DEFAULT_CAP_DELAY = 20.0
DEFAULT_CONCURRENCY_START = 10
DEFAULT_CONCURRENCY_MAX = 25
DEFAULT_UI_REFRESH_PER_SECOND = 4
DEFAULT_CPU_HIGH_PCT = 85.0
DEFAULT_CPU_LOW_PCT = 70.0


# -----------------------------
# BOE helpers
# -----------------------------


def is_eli_url(url: str | None) -> bool:
    """Return True when the URL points to a BOE ELI resource."""
    return bool(url) and (url or "").strip().startswith(f"{BASE}/eli/")


def build_consolidated_id_url(doc_id: str, *, part: str) -> str:
    """Build the consolidated BOE API URL for a document identifier."""
    base = f"{LEGIS_API}/id/{doc_id}"
    if part and part != "full":
        return f"{base}/{part}"
    return base


async def get_consolidated_list_json(
    options: "DownloadOptions",
    *,
    since_from: str | None,
    since_to: str | None,
) -> List[Dict[str, Any]]:
    """Fetch the consolidated catalog JSON list."""
    session = options.io.session
    if session is None:
        raise RuntimeError("ClientSession no inicializada.")
    if since_from or since_to:
        params: List[str] = []
        if since_from:
            params.append(f"from={since_from}")
        if since_to:
            params.append(f"to={since_to}")
        params.append("limit=-1")
        url = f"{LEGIS_API}?{'&'.join(params)}"
    else:
        url = f"{LEGIS_API}?limit=-1"

    content, _meta, status, _headers = await fetch_with_cache(
        session=session,
        store_dir=options.io.store_dir,
        url=url,
        accept="application/json",
        retries=options.retry.retries,
        base_delay_s=options.retry.base_delay,
        cap_delay_s=options.retry.cap_delay,
        jitter=options.retry.jitter,
        return_bytes=True,
        debug_http=options.debug.debug_http,
        debug_http_all=options.debug.debug_http_all,
        no_cache=options.debug.no_cache,
    )
    if content is None:
        data_path, _ = paths_for_url(options.io.store_dir, url)
        if os.path.exists(data_path):
            async with aiofiles.open(data_path, "rb") as f:
                content = await f.read()
        else:
            raise RuntimeError("Catálogo consolidado devolvió 304 sin caché local.")
    if status >= 400:
        raise RuntimeError(f"Catálogo consolidado HTTP {status}")

    data = json.loads(content.decode("utf-8"))
    if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
        return data["data"]
    if isinstance(data, list):
        return data
    raise RuntimeError("Formato JSON inesperado en catálogo consolidado.")


async def get_sumario_xml(
    options: "DownloadOptions",
    *,
    fecha: str,
) -> bytes:
    """Fetch the BOE daily sumario XML payload."""
    session = options.io.session
    if session is None:
        raise RuntimeError("ClientSession no inicializada.")
    url = f"{SUMARIO_API}/{fecha}"
    content, _meta, status, _headers = await fetch_with_cache(
        session=session,
        store_dir=options.io.store_dir,
        url=url,
        accept="application/xml",
        retries=options.retry.retries,
        base_delay_s=options.retry.base_delay,
        cap_delay_s=options.retry.cap_delay,
        jitter=options.retry.jitter,
        return_bytes=True,
        debug_http=options.debug.debug_http,
        debug_http_all=options.debug.debug_http_all,
        no_cache=options.debug.no_cache,
    )
    if content is None:
        data_path, _ = paths_for_url(options.io.store_dir, url)
        async with aiofiles.open(data_path, "rb") as f:
            return await f.read()
    if status >= 400:
        raise RuntimeError(f"Sumario HTTP {status}")
    return content


# -----------------------------


# -----------------------------
# Pipelines
# -----------------------------


@dataclass
class IOConfig:
    """I/O configuration for downloads."""

    session: ClientSession | None
    store_dir: str


@dataclass
class RuntimeState:
    """Runtime state shared across the download run."""

    run_id: str
    limiter: AdaptiveLimiter
    stats: RunStats
    web_state: WebState | None
    db: DbCtx | None


@dataclass
class UiConfig:
    """UI configuration for progress output."""

    progress: bool
    ui_refresh: int


@dataclass
class RetryConfig:
    """Retry/backoff configuration."""

    retries: int
    base_delay: float
    cap_delay: float
    jitter: str


@dataclass
class DebugConfig:
    """Debug and cache control flags."""

    debug_http: bool
    debug_http_all: bool
    no_cache: bool


@dataclass
class DownloadOptions:
    """Bundle runtime options for downloads."""

    io: IOConfig
    runtime: RuntimeState
    ui: UiConfig
    retry: RetryConfig
    debug: DebugConfig


@dataclass
class RuntimeContext:
    """Aggregated runtime context for a download run."""

    timeout: aiohttp.ClientTimeout
    connector: aiohttp.TCPConnector
    options: DownloadOptions
    start: int
    max_limit: int


async def run_with_status(
    console: Console,
    enabled: bool,
    message: str,
    func,
    *args,
    **kwargs,
):
    """Run a coroutine with an optional Rich status spinner."""
    if enabled:
        with console.status(message):
            return await func(*args, **kwargs)
    return await func(*args, **kwargs)


async def load_eli_filter(eli_list_file: str | None) -> set[str] | None:
    """Load an optional ELI allowlist from a file."""
    if not eli_list_file:
        return None
    async with aiofiles.open(eli_list_file, "r", encoding="utf-8") as f:
        return {ln.strip() for ln in (await f.read()).splitlines() if ln.strip()}


def build_consolidated_targets(
    items: List[Dict[str, Any]],
    part: str,
    wanted: set[str] | None,
    fmt: str,
    source_kind: str,
) -> List[Dict[str, Any]]:
    """Build download targets from consolidated catalog entries."""
    targets: List[Dict[str, Any]] = []
    for it in items:
        doc_id = it.get("identificador")
        eli = it.get("url_eli")
        if not doc_id or not isinstance(eli, str) or not is_eli_url(eli):
            continue
        eli = eli.strip()
        if wanted is not None and eli not in wanted:
            continue
        url = build_consolidated_id_url(doc_id, part=part)
        targets.append(
            {"key": eli, "doc_id": doc_id, "url": url, "fmt": fmt, "source_kind": source_kind}
        )
    return targets


def build_sumario_targets(
    urls: List[str],
    fmt: str,
    source_kind: str,
) -> List[Dict[str, Any]]:
    """Build download targets for sumario item URLs."""
    return [
        {"key": u, "url": u, "fmt": fmt, "source_kind": source_kind} for u in urls
    ]


async def fetch_consolidated_items(
    options: DownloadOptions,
    console: Console,
    since_from: str | None,
    since_to: str | None,
) -> List[Dict[str, Any]]:
    """Fetch and prepare consolidated catalog items."""
    return await run_with_status(
        console,
        options.ui.progress,
        "Preparando lista de URLs (catálogo consolidado)...",
        get_consolidated_list_json,
        options,
        since_from=since_from,
        since_to=since_to,
    )


async def fetch_sumario_xml(
    options: DownloadOptions,
    console: Console,
    fecha: str,
) -> bytes:
    """Fetch the sumario XML payload for a date."""
    return await run_with_status(
        console,
        options.ui.progress,
        f"Preparando lista de URLs (sumario {fecha})...",
        get_sumario_xml,
        options,
        fecha=fecha,
    )


async def cmd_consolidada(options: DownloadOptions, args: argparse.Namespace) -> None:
    """Run the consolidated catalog download command."""
    console = Console(force_terminal=True, force_interactive=True)
    formats = args.formats
    if "xml" not in formats:
        console.print("[yellow]Aviso: consolidada solo soporta XML en este script.[/yellow]")
        return
    fecha = args.fecha
    since_from = args.since_from
    since_to = args.since_to
    if fecha:
        if since_from or since_to:
            raise ValueError("No combines --fecha con --since-from/--since-to")
        normalized = normalize_fecha(fecha)
        since_from = normalized
        since_to = normalized
    accept = args.accept
    part = args.part
    manifest = args.manifest
    eli_list_file = args.eli_list

    targets: List[Dict[str, Any]] = []
    if fecha:
        sumario_xml = await fetch_sumario_xml(options, console, since_from)
        urls = extract_sumario_item_urls(sumario_xml)
        for u in urls:
            url_abs = u
            if url_abs.startswith("/"):
                url_abs = f"{BASE}{url_abs}"
            match = BOE_ID_RE.search(url_abs)
            key = match.group(0) if match else url_abs
            targets.append(
                {"key": key, "url": url_abs, "fmt": "xml", "source_kind": "consolidada_id"}
            )
    else:
        items = await fetch_consolidated_items(options, console, since_from, since_to)
        wanted = await load_eli_filter(eli_list_file)
        targets = build_consolidated_targets(
            items, part, wanted, fmt="xml", source_kind="consolidada_id"
        )

    await run_queue_download(
        session=options.io.session,
        store_dir=options.io.store_dir,
        cmd="consolidada",
        items=targets,
        accept=accept,
        manifest_file=manifest,
        limiter=options.runtime.limiter,
        stats=options.runtime.stats,
        run_id=options.runtime.run_id,
        progress=options.ui.progress,
        ui_refresh=options.ui.ui_refresh,
        retries=options.retry.retries,
        base_delay=options.retry.base_delay,
        cap_delay=options.retry.cap_delay,
        jitter=options.retry.jitter,
        debug_http=options.debug.debug_http,
        debug_http_all=options.debug.debug_http_all,
        no_cache=options.debug.no_cache,
        db=options.runtime.db,
        web_state=options.runtime.web_state,
    )


async def cmd_sumario(options: DownloadOptions, args: argparse.Namespace) -> None:
    """Run the daily sumario download command."""
    console = Console(force_terminal=True, force_interactive=True)
    formats = args.formats
    if "xml" not in formats:
        console.print("[yellow]Aviso: sumario requiere XML para extraer URLs.[/yellow]")
        return
    fecha = args.fecha
    manifest = args.manifest

    if not re.fullmatch(r"\d{8}", fecha):
        raise ValueError("fecha debe tener formato AAAAMMDD")

    sumario_xml = await fetch_sumario_xml(options, console, fecha)
    urls = extract_sumario_item_urls(sumario_xml)
    targets = build_sumario_targets(urls, fmt="xml", source_kind="sumario_item")

    await run_queue_download(
        session=options.io.session,
        store_dir=options.io.store_dir,
        cmd="sumario",
        items=targets,
        accept="application/xml",
        manifest_file=manifest,
        limiter=options.runtime.limiter,
        stats=options.runtime.stats,
        run_id=options.runtime.run_id,
        progress=options.ui.progress,
        ui_refresh=options.ui.ui_refresh,
        retries=options.retry.retries,
        base_delay=options.retry.base_delay,
        cap_delay=options.retry.cap_delay,
        jitter=options.retry.jitter,
        debug_http=options.debug.debug_http,
        debug_http_all=options.debug.debug_http_all,
        no_cache=options.debug.no_cache,
        db=options.runtime.db,
        web_state=options.runtime.web_state,
    )


# -----------------------------
# CLI
# -----------------------------


def parse_formats(value: str) -> set[str]:
    """Parse the --formats CLI flag."""
    fmts = {v.strip().lower() for v in value.split(",") if v.strip()}
    if not fmts:
        raise argparse.ArgumentTypeError("Debes indicar al menos un formato.")
    invalid = fmts - {"xml", "json", "pdf"}
    if invalid:
        raise argparse.ArgumentTypeError(f"Formatos invalidos: {sorted(invalid)}")
    return fmts


def normalize_fecha(value: str) -> str:
    """Normalize DD-MM-AAAA or AAAAMMDD into AAAAMMDD."""
    v = value.strip()
    if re.fullmatch(r"\d{8}", v):
        return v
    if re.fullmatch(r"\d{2}-\d{2}-\d{4}", v):
        dd, mm, yyyy = v.split("-")
        return f"{yyyy}{mm}{dd}"
    raise ValueError("fecha debe tener formato DD-MM-AAAA o AAAAMMDD")


def parse_web_port(value: str) -> int:
    """Parse web port; empty or None falls back to 8000."""
    if value is None:
        return 8000
    value = str(value).strip()
    if not value:
        return 8000
    if not value.isdigit():
        raise ValueError("web-port debe ser un entero valido")
    port = int(value)
    if port <= 0 or port > 65535:
        raise ValueError("web-port fuera de rango (1-65535)")
    return port


def _parse_concurrency(value: str) -> str | int:
    """Parse the concurrency CLI value."""
    v = value.strip().lower()
    if v in ("auto", "a"):
        return "auto"
    if v.isdigit():
        n = int(v)
        if n < 1:
            raise argparse.ArgumentTypeError("concurrency must be >= 1")
        return n
    raise argparse.ArgumentTypeError(
        "concurrency must be an integer (e.g. 25) or 'auto'"
    )


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    p = argparse.ArgumentParser(
        prog="boe_downloader_eli_optimized.py",
        description=(
            "Descarga BOE orientada a ELI (consolidada y sumario) con caché "
            "y concurrencia auto."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ejemplos:\n"
            "  python3 boe_downloader_eli_optimized.py --store ./boe_store "
            "--concurrency auto consolidada --since-from 20260101\n"
            "  python3 boe_downloader_eli_optimized.py --concurrency 20 sumario "
            "--fecha 20260104\n"
        ),
    )
    p.add_argument(
        "--store",
        default=DEFAULT_STORE,
        metavar="DIR",
        help=f"Directorio base de almacenamiento. Default: {DEFAULT_STORE}",
    )
    p.add_argument(
        "--db-dsn",
        default=os.environ.get("BOE_DB_DSN"),
        metavar="DSN",
        help="PostgreSQL DSN (o BOE_DB_DSN).",
    )
    p.add_argument(
        "--no-db",
        action="store_true",
        help="No usar Postgres para estados de descarga.",
    )
    p.add_argument(
        "--formats",
        type=parse_formats,
        default={"xml"},
        metavar="FMTs",
        help="Formatos a descargar: xml,json,pdf (default: xml).",
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_S,
        metavar="S",
        help=f"Timeout total por request (segundos). Default: {DEFAULT_TIMEOUT_S}",
    )
    p.add_argument(
        "--retries",
        type=int,
        default=DEFAULT_RETRIES,
        metavar="N",
        help=(
            f"Máximo reintentos por URL (429/5xx/transitorios). "
            f"Default: {DEFAULT_RETRIES}"
        ),
    )
    p.add_argument(
        "--concurrency",
        type=_parse_concurrency,
        default="auto",
        metavar="N|auto",
        help="Concurrencia fija N o auto (AIMD). Default: auto",
    )
    p.add_argument(
        "--concurrency-start",
        type=int,
        default=DEFAULT_CONCURRENCY_START,
        metavar="N",
        help=f"Concurrencia inicial en auto. Default: {DEFAULT_CONCURRENCY_START}",
    )
    p.add_argument(
        "--concurrency-max",
        type=int,
        default=DEFAULT_CONCURRENCY_MAX,
        metavar="N",
        help=f"Techo de concurrencia en auto. Default: {DEFAULT_CONCURRENCY_MAX}",
    )
    p.add_argument(
        "--progress",
        action="store_true",
        default=True,
        help="Muestra barra de progreso y métricas en vivo (Rich).",
    )
    p.add_argument(
        "--no-progress",
        action="store_false",
        dest="progress",
        help="Desactiva la barra de progreso Rich.",
    )
    p.add_argument(
        "--ui-refresh",
        type=int,
        default=DEFAULT_UI_REFRESH_PER_SECOND,
        metavar="N",
        help=f"Refresco UI Rich (veces/seg). Default: {DEFAULT_UI_REFRESH_PER_SECOND}",
    )
    # Debug HTTP:
    #  - --debug-http       : modo selectivo (solo status != 200) para no degradar rendimiento
    #  - --debug-http-all   : imprime TODO (útil en sesiones cortas de diagnóstico)
    #  - --debug            : alias de --debug-http (compatibilidad)
    p.add_argument(
        "--debug-http",
        action="store_true",
        help="HTTP debug (modo NO-200): solo imprime peticiones/respuestas con status != 200.",
    )
    p.add_argument(
        "--debug-http-all",
        action="store_true",
        help="HTTP debug (modo ALL): imprime TODAS las peticiones/respuestas (más lento).",
    )
    p.add_argument(
        "--debug", action="store_true", help="Alias de --debug-http (compatibilidad)."
    )
    p.add_argument(
        "--no-cache",
        action="store_true",
        help=(
            "Desactiva caché condicional (no envía If-None-Match/If-Modified-Since). "
            "Sigue guardando en disco."
        ),
    )

    p.add_argument(
        "--cpu-high",
        type=float,
        default=DEFAULT_CPU_HIGH_PCT,
        metavar="PCT",
        help=(
            f"En auto, si CPU del proceso supera este %, reduce concurrencia. "
            f"Default: {DEFAULT_CPU_HIGH_PCT}"
        ),
    )
    p.add_argument(
        "--cpu-low",
        type=float,
        default=DEFAULT_CPU_LOW_PCT,
        metavar="PCT",
        help=(
            f"En auto, si CPU del proceso está por debajo de este % y no hay "
            f"congestión, permite subir concurrencia. Default: {DEFAULT_CPU_LOW_PCT}"
        ),
    )
    p.add_argument(
        "--jitter",
        choices=["decorrelated", "full"],
        default="decorrelated",
        help="Jitter para backoff de reintentos. Default: decorrelated",
    )
    p.add_argument(
        "--base-delay",
        type=float,
        default=DEFAULT_BASE_DELAY,
        metavar="S",
        help=f"Delay base para backoff (segundos). Default: {DEFAULT_BASE_DELAY}",
    )
    p.add_argument(
        "--open-web",
        action="store_true",
        help="Levanta el panel web y lo abre en el navegador local.",
    )
    p.add_argument(
        "--web-host",
        default="127.0.0.1",
        help="Host para el panel web. Default: 127.0.0.1",
    )
    p.add_argument(
        "--web-port",
        default="8000",
        help="Puerto para el panel web. Default: 8000",
    )

    p.add_argument(
        "--cap-delay",
        type=float,
        default=DEFAULT_CAP_DELAY,
        metavar="S",
        help=f"Delay máximo para backoff (segundos). Default: {DEFAULT_CAP_DELAY}",
    )

    sub = p.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser(
        "consolidada",
        help="Descarga legislación consolidada SOLO con url_eli.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    pc.add_argument(
        "--part",
        default="full",
        choices=[
            "full",
            "metadatos",
            "analisis",
            "metadata-eli",
            "texto",
            "texto/indice",
        ],
        help="Parte del documento. Default: full",
    )
    pc.add_argument(
        "--accept",
        default="application/xml",
        metavar="MIME",
        help="Cabecera Accept. Default: application/xml",
    )
    pc.add_argument(
        "--manifest",
        default="manifest_consolidada_eli.jsonl",
        metavar="FILE",
        help="Manifest JSONL en index/. Default: manifest_consolidada_eli.jsonl",
    )
    pc.add_argument(
        "--fecha",
        default=None,
        metavar="DD-MM-AAAA|AAAAMMDD",
        help=(
            "Fecha unica (equivale a --since-from/--since-to). "
            "Formato DD-MM-AAAA o AAAAMMDD."
        ),
    )
    pc.add_argument(
        "--since-from",
        default=None,
        metavar="AAAAMMDD",
        help="Filtra por fecha actualización desde AAAAMMDD.",
    )
    pc.add_argument(
        "--since-to",
        default=None,
        metavar="AAAAMMDD",
        help="Filtra por fecha actualización hasta AAAAMMDD.",
    )
    pc.add_argument(
        "--eli-list",
        default=None,
        metavar="FILE",
        help="Archivo con una ELI por línea (descarga solo esas).",
    )

    ps = sub.add_parser(
        "sumario",
        help="Descarga sumario diario y XML de items.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ps.add_argument(
        "--fecha", required=True, metavar="AAAAMMDD", help="Fecha AAAAMMDD."
    )
    ps.add_argument(
        "--manifest",
        default="manifest_sumario.jsonl",
        metavar="FILE",
        help="Manifest JSONL en index/. Default: manifest_sumario.jsonl",
    )

    return p


def compute_concurrency(args: argparse.Namespace) -> tuple[int, int]:
    """Devuelve (max_limit, start) según args.concurrency."""
    if args.concurrency == "auto":
        return int(args.concurrency_max), int(args.concurrency_start)
    return int(args.concurrency), int(args.concurrency)


def make_connector(max_limit: int) -> aiohttp.TCPConnector:
    """Create the aiohttp connector for the desired concurrency."""
    return aiohttp.TCPConnector(
        limit=max_limit,
        limit_per_host=max_limit,
        ttl_dns_cache=300,
    )


def print_debug_http(console: Console, args: argparse.Namespace) -> tuple[bool, bool]:
    """Emit HTTP debug status based on CLI flags."""
    debug_http = bool(
        getattr(args, "debug_http", False) or getattr(args, "debug", False)
    )
    debug_http_all = bool(getattr(args, "debug_http_all", False))
    if debug_http:
        mode = "ALL" if debug_http_all else "NO-200"
        detail = (
            "imprime TODAS las peticiones/respuestas"
            if debug_http_all
            else "solo imprime status != 200"
        )
        console.print(f"[dim]HTTP debug activo (modo={mode}):[/dim] {detail}")
    return debug_http, debug_http_all


def make_cpu_sampler():
    """Return a callable that yields a warmed-up psutil.Process."""

    def sample():
        if psutil_module is None:
            return None
        proc = psutil_module.Process()
        try:
            proc.cpu_percent(interval=None)
        except (RuntimeError, OSError):
            return None
        return proc

    return sample


async def build_runtime_context(
    args: argparse.Namespace,
    run_id: str,
    debug_http: bool,
    debug_http_all: bool,
    web_state: WebState | None,
    db: DbCtx | None,
) -> RuntimeContext:
    """Build runtime context with connector and options."""
    timeout = aiohttp.ClientTimeout(total=int(args.timeout))
    max_limit, start = compute_concurrency(args)
    connector = make_connector(max_limit)

    stats = RunStats()
    stats.max_concurrency_configured = max_limit
    limiter = AdaptiveLimiter(max_limit=max_limit, initial=start)
    await limiter.initialize()
    stats.max_concurrency_reached = max(stats.max_concurrency_reached, start)

    options = DownloadOptions(
        io=IOConfig(session=None, store_dir=args.store),
        runtime=RuntimeState(
            run_id=run_id,
            limiter=limiter,
            stats=stats,
            web_state=web_state,
            db=db,
        ),
        ui=UiConfig(progress=args.progress, ui_refresh=args.ui_refresh),
        retry=RetryConfig(
            retries=int(args.retries),
            base_delay=float(args.base_delay),
            cap_delay=float(args.cap_delay),
            jitter=args.jitter,
        ),
        debug=DebugConfig(
            debug_http=debug_http,
            debug_http_all=debug_http_all,
            no_cache=args.no_cache,
        ),
    )

    return RuntimeContext(
        timeout=timeout,
        connector=connector,
        options=options,
        start=start,
        max_limit=max_limit,
    )


async def print_final_status(
    console: Console,
    args: argparse.Namespace,
    options: DownloadOptions,
) -> None:
    """Print the final status panel."""
    cur = await options.runtime.limiter.get_target()
    proc = psutil_module.Process() if psutil_module is not None else None  # type: ignore
    if proc is not None:
        try:
            proc.cpu_percent(interval=None)
        except (RuntimeError, OSError):
            proc = None

    cpu_val = proc.cpu_percent(interval=None) if proc is not None else None
    cpu_pct = f"{cpu_val:.1f}%" if cpu_val is not None else "n/a"
    rss_mb = (
        f"{(proc.memory_info().rss / 1024 / 1024):.1f} MB ({proc.memory_percent():.1f}%)"
        if proc is not None
        else "n/a"
    )

    console.print(
        make_status_panel(
            run_id=options.runtime.run_id,
            cmd=args.cmd,
            stats=options.runtime.stats,
            concurrency=cur,
            cpu_pct=cpu_pct,
            rss_mb=rss_mb,
        )
    )


def maybe_start_tuner(
    args: argparse.Namespace,
    limiter: AdaptiveLimiter,
    stats: RunStats,
    start: int,
    max_limit: int,
) -> asyncio.Task | None:
    """Start the adaptive concurrency tuner when enabled."""
    if args.concurrency != "auto":
        return None
    return asyncio.create_task(
        autotune_concurrency(
            limiter,
            stats,
            start=start,
            max_limit=max_limit,
            cpu_high=float(args.cpu_high),
            cpu_low=float(args.cpu_low),
            interval_s=5.0,
            cpu_sample=make_cpu_sampler(),
        )
    )


async def run_command(options: DownloadOptions, args: argparse.Namespace) -> None:
    """Dispatch the selected command."""
    if args.cmd == "consolidada":
        await cmd_consolidada(options, args)
        return
    if args.cmd == "sumario":
        await cmd_sumario(options, args)
        return
    raise RuntimeError(f"Comando no reconocido: {args.cmd}")


async def amain(args: argparse.Namespace) -> None:
    """Async CLI entrypoint."""
    store_dir = args.store
    ensure_dirs(store_dir)

    run_id = (
        datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        + f"-{(secrets.randbelow(9999 - 1000 + 1) + 1000)}"
    )
    console = make_console(args.progress)
    console.print(f"[bold]run_id:[/bold] {run_id}")

    web_state = WebState() if args.open_web else None
    if web_state is not None:
        web_state.set_run_info(run_id, args.cmd)
        web_state.set_status("PREPARANDO")
        web_state.set_timestamp()
    prep_stop = asyncio.Event()
    prep_task: asyncio.Task | None = None
    if web_state is not None:
        async def prep_loop() -> None:
            while not prep_stop.is_set():
                web_state.set_timestamp()
                await asyncio.sleep(0.8)
        prep_task = asyncio.create_task(prep_loop())
    db_ctx: DbCtx | None = None
    if not args.no_db:
        dsn = args.db_dsn or os.environ.get("BOE_DB_DSN")
        if not dsn:
            print("Falta --db-dsn o BOE_DB_DSN (o usa --no-db).", file=sys.stderr)
            raise SystemExit(2)
        db_ctx = DbCtx(pool=await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5))
    web_handle = None
    if args.open_web and web_state is not None:
        try:
            web_handle = start_web_server(
                web_state, host=args.web_host, port=parse_web_port(args.web_port)
            )
            console.print(f"[bold]Panel web:[/bold] {web_handle.url}")
            try:
                webbrowser.open(web_handle.url)
            except OSError:
                console.print(
                    "[dim]No se pudo abrir el navegador automaticamente.[/dim]"
                )
        except RuntimeError as exc:
            banner = (
                "\n"
                "===============================\n"
                "PUERTO OCUPADO\n"
                f"{exc}\n"
                "Usa --web-port con otro puerto para continuar.\n"
                "===============================\n"
            )
            console.print(banner)
            raise SystemExit(2) from exc

    debug_http, debug_http_all = print_debug_http(console, args)
    context = await build_runtime_context(
        args, run_id, debug_http, debug_http_all, web_state, db_ctx
    )

    tuner_task = maybe_start_tuner(
        args,
        context.options.runtime.limiter,
        context.options.runtime.stats,
        context.start,
        context.max_limit,
    )

    try:
        async with aiohttp.ClientSession(
            timeout=context.timeout, connector=context.connector
        ) as session:
            context.options.io.session = session
            await run_command(context.options, args)

    finally:
        if prep_task is not None:
            prep_stop.set()
            prep_task.cancel()
            await asyncio.gather(prep_task, return_exceptions=True)
        if tuner_task is not None:
            tuner_task.cancel()
            await asyncio.gather(tuner_task, return_exceptions=True)
        if web_handle is not None:
            stop_web_server(web_handle)
        if db_ctx is not None:
            await db_ctx.pool.close()

    if not args.progress:
        await print_final_status(console, args, context.options)


def main() -> None:
    """Sync CLI entrypoint."""

    parser = build_arg_parser()
    args = parser.parse_args()
    asyncio.run(amain(args))


if __name__ == "__main__":
    main()
