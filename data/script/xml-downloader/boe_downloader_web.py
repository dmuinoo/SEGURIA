"""FastAPI web dashboard for BOE downloader."""

from __future__ import annotations

import json
import threading
from datetime import datetime


import socket
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn


HTML_TEMPLATE = """<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Panel de descarga BOE</title>
    <style>
      :root {
        --bg: #0b0f1a;
        --panel: #121829;
        --card: #1a2336;
        --text: #e2e8f0;
        --muted: #94a3b8;
        --accent: #38bdf8;
        --accent-2: #10b981;
        --track: #25314a;
        --warn: #f59e0b;
        --err: #ef4444;
        --ok: #22c55e;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        background: var(--bg);
        color: var(--text);
        font-family: Arial, sans-serif;
      }
      .frame {
        width: min(1200px, 100%);
        min-height: 700px;
        padding: clamp(16px, 2.5vw, 32px);
        margin: 0 auto;
        background: var(--bg);
      }
      .shell {
        width: 100%;
        min-height: 636px;
        background: var(--panel);
        border-radius: 24px;
        padding: clamp(24px, 3.2vw, 40px);
        position: relative;
        overflow: hidden;
      }
      h1 {
        margin: 0;
        font-size: 28px;
      }
      .subtitle {
        color: var(--muted);
        font-size: 14px;
        margin-top: 6px;
      }
      .pill {
        margin-top: 12px;
        display: inline-flex;
        align-items: center;
        padding: 4px 12px;
        border-radius: 999px;
        background: #16253b;
        color: var(--accent);
        font-size: 12px;
      }
      .run-meta {
        display: flex;
        align-items: center;
        gap: 12px;
        row-gap: 6px;
        margin-top: 16px;
        flex-wrap: wrap;
      }
      .run-chip {
        background: #1b2a44;
        color: var(--accent);
        font-size: 11px;
        letter-spacing: 1px;
        padding: 4px 10px;
        border-radius: 999px;
      }
      .status-chip {
        background: #11334f;
        color: #7dd3fc;
      }
      .run-value {
        font-size: 14px;
        font-weight: bold;
        color: var(--text);
        max-width: min(320px, 80vw);
        overflow-wrap: anywhere;
      }
      .grid-top {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
        gap: 24px;
        margin-top: 24px;
      }
      .grid-bottom {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
        gap: 24px;
        margin-top: 30px;
      }
      .card {
        background: var(--card);
        border-radius: 16px;
        padding: 24px;
        min-height: 150px;
        height: auto;
        overflow: hidden;
        min-width: 0;
      }
      .card.bottom {
        min-height: 240px;
        height: auto;
      }
      .card.http-card {
        display: flex;
        flex-direction: column;
      }
      .label {
        color: var(--muted);
        font-size: 12px;
        letter-spacing: 1px;
      }
      .value-lg {
        margin-top: 18px;
        font-size: clamp(18px, 2.2vw, 24px);
        overflow-wrap: anywhere;
      }
      .bar {
        margin-top: 16px;
        width: 100%;
        max-width: 100%;
        height: 12px;
        border-radius: 999px;
        background: var(--track);
        position: relative;
      }
      .bar-fill {
        position: absolute;
        left: 0;
        top: 0;
        height: 12px;
        border-radius: 999px;
        background: var(--accent-2);
        width: 0%;
      }
      .value-sm {
        margin-top: 16px;
        color: var(--muted);
        font-size: 12px;
        overflow-wrap: anywhere;
      }
      .downloads-line {
        margin-top: 18px;
        font-size: 12px;
        color: var(--muted);
        overflow-wrap: anywhere;
      }
      .downloads-metric {
        margin-top: 16px;
        font-size: 14px;
        color: var(--text);
        overflow-wrap: anywhere;
      }
      .downloads-metric strong {
        font-weight: bold;
      }
      .error-bars {
        display: flex;
        align-items: flex-end;
        gap: 20px;
        margin-top: 20px;
        height: 70px;
      }
      .error-bar {
        width: 40px;
        height: 8px;
        border-radius: 0;
      }
      .error-counts {
        display: flex;
        gap: 20px;
        margin-top: 6px;
        color: var(--muted);
        font-size: 11px;
      }
      .error-legend {
        display: flex;
        align-items: center;
        gap: 18px;
        margin-top: 10px;
        font-size: 12px;
        color: var(--muted);
      }
      .legend-item {
        display: inline-flex;
        align-items: center;
        gap: 6px;
      }
      .legend-dot {
        width: 10px;
        height: 10px;
      }
      .http-bars {
        display: flex;
        align-items: flex-end;
        gap: 30px;
        margin-top: 26px;
        height: 120px;
      }
      .http-bar {
        width: 50px;
        height: 10px;
      }
      .http-counts {
        display: flex;
        gap: 68px;
        margin-top: 8px;
        font-size: 11px;
        color: var(--muted);
        overflow-wrap: anywhere;
      }
      .http-labels {
        display: flex;
        gap: 68px;
        margin-top: 4px;
        font-size: 12px;
        color: var(--muted);
      }
      .metrics-list {
        margin-top: 16px;
        display: grid;
        gap: 8px;
        min-width: 0;
      }
      .metric-row {
        font-size: 12px;
        overflow-wrap: anywhere;
      }
      .http-stack {
        margin-top: auto;
        display: flex;
        flex-direction: column;
      }
    </style>
  </head>
  <body>
    <div class="frame">
      <div class="shell">
        <h1>Panel de descarga BOE</h1>
        <div class="subtitle">Actualizacion en vivo del progreso y metricas</div>
        <div class="pill">En vivo</div>
<div class="run-meta">
  <div class="run-chip">RUN</div>
  <div class="run-value" id="run-id">-</div>
  <div class="run-chip">CMD</div>
  <div class="run-value" id="run-cmd">-</div>
  <div class="run-chip status-chip">ESTADO</div>
  <div class="run-value" id="run-status">-</div>
  <div class="run-chip">ACTUALIZADO</div>
  <div class="run-value" id="run-time">-</div>
</div>

        <div class="grid-top">
          <div class="card">
            <div class="label">PROGRESO TOTAL</div>
            <div class="value-lg" id="progress-count">0 / 0</div>
            <div class="bar">
              <div class="bar-fill" id="progress-bar"></div>
            </div>
            <div class="value-sm" id="progress-meta">0%   OK: 0</div>
          </div>

          <div class="card">
            <div class="label">DESCARGAS</div>
            <div class="value-lg" id="bytes-total">0 B</div>
            <div class="downloads-line" id="downloads-line">XML: 0   PDF: 0</div>
            <div class="downloads-metric">
              <strong>XML descargados</strong> <span id="xml-ok">0</span>
            </div>
            <div class="downloads-metric">
              <strong>PDF descargados</strong> <span id="pdf-ok">0</span>
            </div>
          </div>

          <div class="card">
            <div class="label">ERRORES</div>
            <div class="error-bars">
              <div class="error-bar" id="err-timeouts" style="background: var(--warn);"></div>
              <div class="error-bar" id="err-client" style="background: var(--accent);"></div>
              <div class="error-bar" id="err-other" style="background: var(--err);"></div>
            </div>
            <div class="error-counts">
              <div id="err-timeouts-count">0</div>
              <div id="err-client-count">0</div>
              <div id="err-other-count">0</div>
            </div>
            <div class="error-legend">
              <div class="legend-item"><span class="legend-dot" style="background: var(--warn);"></span>Timeouts</div>
              <div class="legend-item"><span class="legend-dot" style="background: var(--accent);"></span>Cliente</div>
              <div class="legend-item"><span class="legend-dot" style="background: var(--err);"></span>Otros</div>
            </div>
          </div>
        </div>

        <div class="grid-bottom">
          <div class="card bottom http-card">
            <div class="label">ESTADO HTTP</div>
            <div class="http-stack">
              <div class="http-bars">
                <div class="http-bar" id="http-2xx" style="background: var(--ok);"></div>
                <div class="http-bar" id="http-3xx" style="background: var(--accent);"></div>
                <div class="http-bar" id="http-4xx" style="background: var(--warn);"></div>
                <div class="http-bar" id="http-5xx" style="background: var(--err);"></div>
              </div>
              <div class="http-counts">
                <div id="http-2xx-count">0</div>
                <div id="http-3xx-count">0</div>
                <div id="http-4xx-count">0</div>
                <div id="http-5xx-count">0</div>
              </div>
              <div class="http-labels">
                <div>2xx</div>
                <div>3xx</div>
                <div>4xx</div>
                <div>5xx</div>
              </div>
            </div>
          </div>

          <div class="card bottom">
            <div class="label">METRICAS</div>
            <div class="metrics-list">
              <div class="metric-row" id="metric-done">Completados: 0</div>
              <div class="metric-row" id="metric-ok">OK: 0</div>
              <div class="metric-row" id="metric-304">Skipped 304: 0</div>
              <div class="metric-row" id="metric-errors">Errores: 0</div>
              <div class="metric-row" id="metric-errors-flag">Errores detectados: NO</div>
              <div class="metric-row" id="metric-429">HTTP 429: 0</div>
              <div class="metric-row" id="metric-5xx">HTTP 5xx: 0</div>
              <div class="metric-row" id="metric-bytes">Bytes descargados: 0 B</div>
              <div class="metric-row" id="metric-xml">XML OK: 0</div>
              <div class="metric-row" id="metric-pdf">PDF OK: 0</div>
              <div class="metric-row" id="metric-concurrency">Concurrentes: 0</div>
              <div class="metric-row" id="metric-max-cfg">Max concurrencia cfg: 0</div>
              <div class="metric-row" id="metric-max-hit">Max concurrencia: 0</div>
              <div class="metric-row" id="metric-cpu">CPU: n/a</div>
              <div class="metric-row" id="metric-ram">RAM: n/a</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <script>
      const initialState = __STATE__;

      function formatBytes(value) {
        if (value <= 0) {
          return "0 B";
        }
        const mb = value / (1024 * 1024);
        if (mb >= 0.1) {
          return `${mb.toFixed(1)} MB`;
        }
        const kb = value / 1024;
        if (kb >= 0.1) {
          return `${kb.toFixed(1)} KB`;
        }
        return `${value} B`;
      }

      function setBarHeight(el, value, max, height) {
        const safeMax = Math.max(max, 1);
        const h = Math.max(6, Math.round((value / safeMax) * height));
        el.style.height = `${h}px`;
      }

      function render(state) {
        const total = state.total || 0;
        const done = state.done || 0;
        const ok = state.ok || 0;
        const percent = total ? Math.round((done / total) * 100) : 0;

        document.getElementById("run-id").textContent = state.run_id || "-";
        document.getElementById("run-cmd").textContent = state.cmd || "-";
        document.getElementById("run-status").textContent = state.status || "-";
        document.getElementById("run-time").textContent = state.last_update_local || "-";
        document.getElementById("progress-count").textContent = `${done} / ${total}`;
        document.getElementById("progress-meta").textContent = `${percent}%   OK: ${ok}`;
        document.getElementById("progress-bar").style.width = `${percent}%`;

        document.getElementById("bytes-total").textContent = formatBytes(state.bytes || 0);
        document.getElementById("downloads-line").textContent = `XML: ${state.xml_ok || 0}   PDF: ${state.pdf_ok || 0}`;
        document.getElementById("xml-ok").textContent = state.xml_ok || 0;
        document.getElementById("pdf-ok").textContent = state.pdf_ok || 0;

        document.getElementById("metric-done").textContent = `Completados: ${state.done || 0}`;
        document.getElementById("metric-ok").textContent = `OK: ${state.ok || 0}`;
        document.getElementById("metric-304").textContent = `Skipped 304: ${state.skipped_304 || 0}`;
        document.getElementById("metric-errors").textContent = `Errores: ${state.errors || 0}`;
        const errCount = state.errors || 0;
        const errPct = total ? ((errCount / total) * 100).toFixed(1) : "0.0";
        const errFlag = errCount > 0 ? "SI" : "NO";
        document.getElementById("metric-errors-flag").textContent = `Errores detectados: ${errFlag} (${errCount}, ${errPct}%)`;
        document.getElementById("metric-429").textContent = `HTTP 429: ${state.http_429 || 0}`;
        document.getElementById("metric-5xx").textContent = `HTTP 5xx: ${state.http_5xx || 0}`;
        document.getElementById("metric-bytes").textContent = `Bytes descargados: ${formatBytes(state.bytes || 0)}`;
        document.getElementById("metric-xml").textContent = `XML OK: ${state.xml_ok || 0}`;
        document.getElementById("metric-pdf").textContent = `PDF OK: ${state.pdf_ok || 0}`;
        document.getElementById("metric-concurrency").textContent = `Concurrentes: ${state.concurrency || 0}`;
        document.getElementById("metric-max-cfg").textContent = `Max concurrencia cfg: ${state.concurrency_max_cfg || 0}`;
        document.getElementById("metric-max-hit").textContent = `Max concurrencia: ${state.max_concurrency_reached || 0}`;
        document.getElementById("metric-cpu").textContent = `CPU: ${state.cpu_pct || "n/a"}`;
        document.getElementById("metric-ram").textContent = `RAM: ${state.ram_text || "n/a"}`;

        document.getElementById("err-timeouts-count").textContent = state.timeouts || 0;
        document.getElementById("err-client-count").textContent = state.client_errors || 0;
        document.getElementById("err-other-count").textContent = state.other_errors || 0;

        const errorMax = Math.max(state.timeouts || 0, state.client_errors || 0, state.other_errors || 0, 1);
        setBarHeight(document.getElementById("err-timeouts"), state.timeouts || 0, errorMax, 70);
        setBarHeight(document.getElementById("err-client"), state.client_errors || 0, errorMax, 70);
        setBarHeight(document.getElementById("err-other"), state.other_errors || 0, errorMax, 70);

        document.getElementById("http-2xx-count").textContent = state.http_2xx || 0;
        document.getElementById("http-3xx-count").textContent = state.http_3xx || 0;
        document.getElementById("http-4xx-count").textContent = state.http_4xx || 0;
        document.getElementById("http-5xx-count").textContent = state.http_5xx || 0;

        const httpMax = Math.max(state.http_2xx || 0, state.http_3xx || 0, state.http_4xx || 0, state.http_5xx || 0, 1);
        setBarHeight(document.getElementById("http-2xx"), state.http_2xx || 0, httpMax, 120);
        setBarHeight(document.getElementById("http-3xx"), state.http_3xx || 0, httpMax, 120);
        setBarHeight(document.getElementById("http-4xx"), state.http_4xx || 0, httpMax, 120);
        setBarHeight(document.getElementById("http-5xx"), state.http_5xx || 0, httpMax, 120);
      }

      async function fetchState() {
        try {
          const res = await fetch("/api/state");
          if (!res.ok) {
            return;
          }
          const data = await res.json();
          render(data);
        } catch (err) {
        }
      }

      render(initialState);
      setInterval(fetchState, 800);
    </script>
  </body>
</html>
"""


@dataclass
class WebState:
    """Shared state for the FastAPI dashboard."""

    run_id: str = ""
    cmd: str = ""
    status: str = "IDLE"
    last_update_local: str = "-"
    total: int = 0
    done: int = 0
    ok: int = 0
    bytes: int = 0
    xml_ok: int = 0
    pdf_ok: int = 0
    skipped_304: int = 0
    errors: int = 0
    http_2xx: int = 0
    http_3xx: int = 0
    http_4xx: int = 0
    http_5xx: int = 0
    http_429: int = 0
    timeouts: int = 0
    client_errors: int = 0
    other_errors: int = 0
    concurrency: int = 0
    concurrency_max_cfg: int = 0
    max_concurrency_reached: int = 0
    cpu_pct: str = "n/a"
    ram_text: str = "n/a"
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def snapshot(self) -> Dict[str, Any]:
        """Return a thread-safe snapshot of the current state."""
        with self._lock:
            return {
                "run_id": self.run_id,
                "cmd": self.cmd,
                "status": self.status,
                "last_update_local": self.last_update_local,
                "total": self.total,
                "done": self.done,
                "ok": self.ok,
                "bytes": self.bytes,
                "xml_ok": self.xml_ok,
                "pdf_ok": self.pdf_ok,
                "skipped_304": self.skipped_304,
                "errors": self.errors,
                "http_2xx": self.http_2xx,
                "http_3xx": self.http_3xx,
                "http_4xx": self.http_4xx,
                "http_5xx": self.http_5xx,
                "http_429": self.http_429,
                "timeouts": self.timeouts,
                "client_errors": self.client_errors,
                "other_errors": self.other_errors,
                "concurrency": self.concurrency,
                "concurrency_max_cfg": self.concurrency_max_cfg,
                "max_concurrency_reached": self.max_concurrency_reached,
                "cpu_pct": self.cpu_pct,
                "ram_text": self.ram_text,
            }

    def set_run_info(self, run_id: str, cmd: str) -> None:
        """Set run id and command label."""
        with self._lock:
            self.run_id = run_id
            self.cmd = cmd

    def set_status(self, status: str) -> None:
        """Set the current run status."""
        with self._lock:
            self.status = status

    def set_timestamp(self, value: str | None = None) -> None:
        """Set the last-update timestamp (local time)."""
        with self._lock:
            if value is None:
                self.last_update_local = (
                    datetime.now().astimezone().strftime("%d/%m/%Y %H:%M:%S")
                )
            else:
                self.last_update_local = value

    def set_total(self, total: int) -> None:
        """Set total items for the run."""
        with self._lock:
            self.total = max(0, int(total))

    def set_concurrency(self, value: int) -> None:
        """Set current concurrency value."""
        with self._lock:
            self.concurrency = max(0, int(value))

    def set_limits(self, max_cfg: int, max_reached: int) -> None:
        """Set concurrency limit stats."""
        with self._lock:
            self.concurrency_max_cfg = max(0, int(max_cfg))
            self.max_concurrency_reached = max(0, int(max_reached))

    def set_system(self, cpu_pct: str, ram_text: str) -> None:
        """Set system metrics for display."""
        with self._lock:
            self.cpu_pct = cpu_pct
            self.ram_text = ram_text

    def sync_totals(
        self,
        *,
        done: int,
        ok: int,
        skipped_304: int,
        errors: int,
        http_429: int,
        http_5xx: int,
        bytes_total: int,
    ) -> None:
        """Sync aggregate counters from RunStats."""
        with self._lock:
            self.done = max(0, int(done))
            self.ok = max(0, int(ok))
            self.skipped_304 = max(0, int(skipped_304))
            self.errors = max(0, int(errors))
            self.http_429 = max(0, int(http_429))
            self.http_5xx = max(0, int(http_5xx))
            self.bytes = max(0, int(bytes_total))

    def update_item(
        self,
        *,
        status: Optional[int],
        nbytes: int,
        url: str,
        timeout: bool,
        format_hint: str,
    ) -> None:
        """Update counters for a completed item."""
        with self._lock:
            self.done += 1
            self.bytes += max(0, int(nbytes))
            self.last_update_local = (
                datetime.now().astimezone().strftime("%d/%m/%Y %H:%M:%S")
            )
            if timeout:
                self.timeouts += 1
                self.errors += 1

            if status is None:
                self.other_errors += 1
                self.errors += 1
                return

            if status == 304:
                self.skipped_304 += 1
                self.http_3xx += 1
                return

            if 200 <= status < 300:
                self.ok += 1
                self.http_2xx += 1
                hint = (format_hint or "").lower()
                url_lower = url.lower()
                if (
                    "application/pdf" in hint
                    or url_lower.endswith(".pdf")
                    or "/pdfs/" in url_lower
                ):
                    self.pdf_ok += 1
                else:
                    self.xml_ok += 1
                return

            if 300 <= status < 400:
                self.http_3xx += 1
                return

            if status == 429:
                self.http_429 += 1

            if 400 <= status < 500:
                self.http_4xx += 1
                self.client_errors += 1
                self.errors += 1
                return

            if status >= 500:
                self.http_5xx += 1
                self.other_errors += 1
                self.errors += 1

            if status is None:
                self.other_errors += 1
                self.errors += 1
                return

            if status == 304:
                self.skipped_304 += 1
                self.http_3xx += 1
                return

            if 200 <= status < 300:
                self.ok += 1
                self.http_2xx += 1
                if "pdf" in (format_hint or "").lower() or "/pdfs/" in url.lower():
                    self.pdf_ok += 1
                else:
                    self.xml_ok += 1
                return

            if 300 <= status < 400:
                self.http_3xx += 1
                return

            if status == 429:
                self.http_429 += 1

            if 400 <= status < 500:
                self.http_4xx += 1
                self.client_errors += 1
                self.errors += 1
                return

            if status >= 500:
                self.http_5xx += 1
                self.other_errors += 1
                self.errors += 1


@dataclass
class WebServerHandle:
    """References to the running web server."""

    server: uvicorn.Server
    thread: threading.Thread
    url: str


def _is_port_available(host: str, port: int) -> bool:
    """Return True if the host:port can be bound."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
            return True
    except OSError:
        return False


def _render_html(state: WebState) -> str:
    payload = json.dumps(state.snapshot())
    return HTML_TEMPLATE.replace("__STATE__", payload)


def create_app(state: WebState) -> FastAPI:
    """Create the FastAPI app for the dashboard."""
    app = FastAPI()

    @app.get("/")
    def index() -> HTMLResponse:
        return HTMLResponse(_render_html(state), headers={"Cache-Control": "no-store"})

    @app.get("/api/state")
    def api_state() -> JSONResponse:
        return JSONResponse(state.snapshot(), headers={"Cache-Control": "no-store"})

    return app


def start_web_server(state: WebState, *, host: str, port: int) -> WebServerHandle:
    """Start the FastAPI server in a background thread."""
    if not _is_port_available(host, port):
        raise RuntimeError(f"Puerto ocupado: {host}:{port}")
    app = create_app(state)
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    url = f"http://{host}:{port}"
    return WebServerHandle(server=server, thread=thread, url=url)


def stop_web_server(handle: WebServerHandle) -> None:
    """Stop the FastAPI server."""
    handle.server.should_exit = True
    handle.thread.join(timeout=2)
