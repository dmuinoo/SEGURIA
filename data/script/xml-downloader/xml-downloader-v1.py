#!/usr/bin/env python3
"""
boe_downloader_eli.py

Descarga persistente (con caché HTTP) y orientada a ELI de:
  1) Legislación consolidada: descarga SOLO normas con url_eli (formato https://www.boe.es/eli/...)
     - Construye índice ELI -> doc_id (BOE-...).
     - Descarga el XML consolidado mediante API /id/{doc_id} (o partes), pero lo referencia por ELI.
  2) Sumario BOE diario: dado AAAAMMDD, baja el sumario y descarga el XML de cada item usando url_xml.

Características:
- aiohttp asíncrono, concurrencia configurable
- caché condicional (ETag/Last-Modified)
- manifest JSONL por descarga
- índice persistente ELI->doc_id para resolución rápida


*Descargar todas las normas que tengan url-eli normalizada
python3 boe_downloader_eli.py consolidada --concurrency 25 --part full --accept application/xml

*Descargar por un eli concreto
python3 boe_downloader_eli.py eli --value "https://www.boe.es/eli/es/l/2015/10/01/40"
	Si quieres fforzar recostruccion del indice antes:
python3 boe_downloader_eli.py eli --rebuild-index --value "https://www.boe.es/eli/es/l/2015/10/01/40"

*Descargar BOE por sumario (sin cambios)
python3 boe_downloader_eli.py sumario --fecha 20240529

"""

import argparse
import asyncio
import hashlib
import json
import os
import random
import re
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import aiohttp
from aiohttp import ClientSession
from lxml import etree

# -----------------------------
# Configuración
# -----------------------------

BASE = "https://www.boe.es"

SUMARIO_API = f"{BASE}/datosabiertos/api/boe/sumario"  # + /{fecha}
LEGIS_API = f"{BASE}/datosabiertos/api/legislacion-consolidada"

STORE_DIR = "./boe_store"

DEFAULT_MAX_CONCURRENCY = 25
TIMEOUT = aiohttp.ClientTimeout(total=120)
DEFAULT_RETRIES = 4

# Regex ELI (conservador, suficiente para filtrar por prefijo)
ELI_RE = re.compile(r"^https?://www\.boe\.es/eli/.*", re.IGNORECASE)

# Nombres de ficheros de índice
ELI_INDEX_FILE = "eli_index.json"         # mapa ELI->doc_id
ELI_INDEX_META_FILE = "eli_index_meta.json"  # info de actualización del índice


# -----------------------------
# Persistencia
# -----------------------------

@dataclass
class StoredMeta:
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    sha256: Optional[str] = None
    content_type: Optional[str] = None
    fetched_at_utc: Optional[str] = None


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def url_key(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()


def ensure_dirs() -> None:
    os.makedirs(os.path.join(STORE_DIR, "data"), exist_ok=True)
    os.makedirs(os.path.join(STORE_DIR, "meta"), exist_ok=True)
    os.makedirs(os.path.join(STORE_DIR, "index"), exist_ok=True)


def paths_for_url(url: str) -> Tuple[str, str]:
    k = url_key(url)
    data_path = os.path.join(STORE_DIR, "data", f"{k}.bin")
    meta_path = os.path.join(STORE_DIR, "meta", f"{k}.json")
    return data_path, meta_path


def load_meta(meta_path: str) -> StoredMeta:
    if not os.path.exists(meta_path):
        return StoredMeta()
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            d = json.load(f)
        return StoredMeta(**d)
    except Exception:
        return StoredMeta()


def save_meta(meta_path: str, meta: StoredMeta) -> None:
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(asdict(meta), f, ensure_ascii=False, indent=2)


def index_path(name: str) -> str:
    return os.path.join(STORE_DIR, "index", name)


def load_json_file(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json_file(path: str, obj: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


# -----------------------------
# HTTP con caché
# -----------------------------

async def fetch_with_cache(
    session: ClientSession,
    url: str,
    accept: str,
    retries: int = DEFAULT_RETRIES,
) -> Tuple[Optional[bytes], StoredMeta, int]:
    data_path, meta_path = paths_for_url(url)
    meta = load_meta(meta_path)

    headers = {"Accept": accept}
    if meta.etag:
        headers["If-None-Match"] = meta.etag
    if meta.last_modified:
        headers["If-Modified-Since"] = meta.last_modified

    last_exc: Optional[Exception] = None

    for attempt in range(retries + 1):
        try:
            async with session.get(url, headers=headers) as resp:
                status = resp.status

                if status == 304:
                    return None, meta, status

                if status >= 400:
                    body = await resp.read()
                    if status == 429 or status >= 500:
                        raise RuntimeError(f"HTTP {status} retryable for {url}: {body[:200]!r}")
                    raise RuntimeError(f"HTTP {status} for {url}: {body[:200]!r}")

                content = await resp.read()

                meta.etag = resp.headers.get("ETag")
                meta.last_modified = resp.headers.get("Last-Modified")
                meta.content_type = resp.headers.get("Content-Type")
                meta.sha256 = sha256_bytes(content)
                meta.fetched_at_utc = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

                with open(data_path, "wb") as f:
                    f.write(content)
                save_meta(meta_path, meta)

                return content, meta, status

        except Exception as e:
            last_exc = e
            if attempt < retries:
                base_delay = 0.6 * (2 ** attempt)
                jitter = random.random() * 0.25
                await asyncio.sleep(base_delay + jitter)
                continue
            break

    raise RuntimeError(f"Failed fetching {url} after retries. Last error: {last_exc}")


# -----------------------------
# XML helpers
# -----------------------------

def parse_xml_bytes(xml_bytes: bytes) -> etree._Element:
    parser = etree.XMLParser(recover=True, resolve_entities=False, huge_tree=True)
    return etree.fromstring(xml_bytes, parser=parser)


def text_or_none(el: Optional[etree._Element]) -> Optional[str]:
    if el is None:
        return None
    t = el.text
    return t.strip() if t else None


# -----------------------------
# Legislación consolidada: índice ELI
# -----------------------------

async def get_consolidated_list_json(
    session: ClientSession,
    since_from: Optional[str],
    since_to: Optional[str],
) -> List[Dict[str, Any]]:
    """
    Descarga el listado de normas consolidadas en JSON.
    - Si since_from/to: usa parámetros from/to para acotar por fecha actualización.
    - Si no: limit=-1 para traer todo el catálogo.
    """
    if since_from or since_to:
        params = []
        if since_from:
            params.append(f"from={since_from}")
        if since_to:
            params.append(f"to={since_to}")
        params.append("limit=-1")
        url = f"{LEGIS_API}?{'&'.join(params)}"
    else:
        url = f"{LEGIS_API}?limit=-1"

    content, _meta, _status = await fetch_with_cache(session, url, accept="application/json")
    if content is None:
        data_path, _ = paths_for_url(url)
        with open(data_path, "rb") as f:
            content = f.read()

    payload = json.loads(content.decode("utf-8", errors="replace"))
    items = payload.get("data") or []
    return items if isinstance(items, list) else []


def is_eli_url(u: Optional[str]) -> bool:
    return bool(u) and bool(ELI_RE.match(u.strip()))


def build_consolidated_doc_url(doc_id: str, part: str, block_id: Optional[str]) -> str:
    """
    Construye URL de descarga por doc_id (BOE-A-....) para legislación consolidada.
    """
    base = f"{LEGIS_API}/id/{doc_id}"

    if part == "full":
        return base
    if part in ("metadatos", "analisis", "metadata-eli", "texto", "texto/indice"):
        return f"{base}/{part}"
    if part == "texto/bloque":
        if not block_id:
            raise ValueError("block_id obligatorio si part='texto/bloque'")
        return f"{base}/texto/bloque/{block_id}"
    raise ValueError(f"part no soportado: {part}")


async def build_or_update_eli_index(
    session: ClientSession,
    since_from: Optional[str],
    since_to: Optional[str],
    only_eli: bool,
) -> Dict[str, str]:
    """
    Construye (o actualiza) el índice ELI->doc_id.
    - Descarga catálogo JSON.
    - Para cada item con identificador y url_eli válido, añade mapping.
    - Persiste en STORE_DIR/index/eli_index.json.
    """
    ensure_dirs()
    idx_path = index_path(ELI_INDEX_FILE)
    meta_path = index_path(ELI_INDEX_META_FILE)

    existing: Dict[str, str] = load_json_file(idx_path, {})
    if not isinstance(existing, dict):
        existing = {}

    items = await get_consolidated_list_json(session, since_from=since_from, since_to=since_to)

    added = 0
    for it in items:
        doc_id = it.get("identificador")
        eli = it.get("url_eli")
        if not doc_id:
            continue
        if only_eli and not is_eli_url(eli):
            continue
        if is_eli_url(eli):
            eli_s = eli.strip()
            # Preferimos no pisar si ya existe y es igual
            if existing.get(eli_s) != doc_id:
                existing[eli_s] = doc_id
                added += 1

    save_json_file(idx_path, existing)
    save_json_file(
        meta_path,
        {
            "updated_at_utc": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "added_or_changed": added,
            "filters": {"from": since_from, "to": since_to, "only_eli": only_eli},
            "size": len(existing),
        },
    )
    return existing


async def download_consolidated_by_eli(
    session: ClientSession,
    eli_index: Dict[str, str],
    max_concurrency: int,
    part: str,
    accept: str,
    manifest_name: str,
    elis: List[str],
) -> None:
    """
    Descarga XML/JSON de normas consolidadas referenciadas por ELI.
    - Resuelve ELI->doc_id por índice.
    - Descarga /id/{doc_id} (o parte).
    - Emite manifest JSONL con ELI como clave principal.
    """
    ensure_dirs()
    sem = asyncio.Semaphore(max_concurrency)
    manifest_path = index_path(manifest_name)

    # normalización + filtro ELI
    targets = []
    for e in elis:
        e = (e or "").strip()
        if not e:
            continue
        if not is_eli_url(e):
            # si el usuario pasa algo que no es ELI, lo ignoramos aquí.
            continue
        targets.append(e)

    async def worker(eli: str) -> None:
        doc_id = eli_index.get(eli)
        if not doc_id:
            out = {
                "kind": "consolidada_eli",
                "eli": eli,
                "error": "ELI no encontrado en índice (reconstruye índice o revisa ELI).",
            }
            with open(manifest_path, "a", encoding="utf-8") as mf:
                mf.write(json.dumps(out, ensure_ascii=False) + "\n")
            return

        url = build_consolidated_doc_url(doc_id=doc_id, part=part, block_id=None)

        async with sem:
            try:
                content, meta, status = await fetch_with_cache(session, url, accept=accept)

                # Validación rápida del XML si corresponde
                parsed_ok = None
                if accept.lower().startswith("application/xml") or accept.lower().startswith("text/xml"):
                    if content is None:
                        data_path, _ = paths_for_url(url)
                        with open(data_path, "rb") as f:
                            xmlb = f.read()
                    else:
                        xmlb = content
                    try:
                        _ = parse_xml_bytes(xmlb)
                        parsed_ok = True
                    except Exception:
                        parsed_ok = False

                out = {
                    "kind": "consolidada_eli",
                    "eli": eli,
                    "doc_id": doc_id,
                    "part": part,
                    "url": url,
                    "http_status": status,
                    "parsed_ok": parsed_ok,
                    "meta": asdict(meta),
                }
                with open(manifest_path, "a", encoding="utf-8") as mf:
                    mf.write(json.dumps(out, ensure_ascii=False) + "\n")

            except Exception as e:
                out = {
                    "kind": "consolidada_eli",
                    "eli": eli,
                    "doc_id": doc_id,
                    "part": part,
                    "url": url,
                    "error": str(e),
                }
                with open(manifest_path, "a", encoding="utf-8") as mf:
                    mf.write(json.dumps(out, ensure_ascii=False) + "\n")

    await asyncio.gather(*(worker(e) for e in targets))


async def download_consolidated_catalog_only_eli(
    session: ClientSession,
    max_concurrency: int,
    part: str,
    accept: str,
    since_from: Optional[str],
    since_to: Optional[str],
    manifest_name: str,
) -> None:
    """
    Flujo “descargar todo consolidado pero SOLO con ELI”:
      1) Construye/actualiza índice ELI->doc_id (filtrado)
      2) Descarga cada doc por ELI usando ese índice
    """
    eli_index = await build_or_update_eli_index(
        session=session,
        since_from=since_from,
        since_to=since_to,
        only_eli=True,
    )
    elis = list(eli_index.keys())
    await download_consolidated_by_eli(
        session=session,
        eli_index=eli_index,
        max_concurrency=max_concurrency,
        part=part,
        accept=accept,
        manifest_name=manifest_name,
        elis=elis,
    )


# -----------------------------
# Sumario diario
# -----------------------------

def extract_sumario_item_urls(sumario_root: etree._Element) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for it in sumario_root.xpath(".//item"):
        rec = {
            "identificador": text_or_none(it.find("identificador")),
            "control": text_or_none(it.find("control")),
            "titulo": text_or_none(it.find("titulo")),
            "url_pdf": text_or_none(it.find("url_pdf")),
            "url_html": text_or_none(it.find("url_html")),
            "url_xml": text_or_none(it.find("url_xml")),
        }
        for k in ("url_pdf", "url_html", "url_xml"):
            if rec.get(k) and rec[k].startswith("/"):
                rec[k] = urljoin(BASE, rec[k])
        if rec.get("url_xml"):
            out.append(rec)
    return out


async def download_sumario_day(
    session: ClientSession,
    fecha: str,
    max_concurrency: int,
    accept_sumario: str = "application/xml",
    accept_item_xml: str = "application/xml",
    out_manifest_name: Optional[str] = None,
) -> None:
    ensure_dirs()

    if not re.fullmatch(r"\d{8}", fecha):
        raise ValueError("fecha debe ser AAAAMMDD (8 dígitos)")

    sumario_url = f"{SUMARIO_API}/{fecha}"
    sum_bytes, _sum_meta, _status = await fetch_with_cache(session, sumario_url, accept=accept_sumario)
    if sum_bytes is None:
        data_path, _ = paths_for_url(sumario_url)
        with open(data_path, "rb") as f:
            sum_bytes = f.read()

    root = parse_xml_bytes(sum_bytes)
    items = extract_sumario_item_urls(root)

    if out_manifest_name is None:
        out_manifest_name = f"manifest_sumario_{fecha}.jsonl"
    manifest_path = index_path(out_manifest_name)

    sem = asyncio.Semaphore(max_concurrency)

    async def worker(rec: Dict[str, Any]) -> None:
        url = rec["url_xml"]
        async with sem:
            try:
                content, meta, status = await fetch_with_cache(session, url, accept=accept_item_xml)

                parsed_ok = False
                if content is None:
                    data_path, _ = paths_for_url(url)
                    with open(data_path, "rb") as f:
                        content2 = f.read()
                else:
                    content2 = content

                try:
                    _ = parse_xml_bytes(content2)
                    parsed_ok = True
                except Exception:
                    parsed_ok = False

                out = {
                    "kind": "sumario_item_xml",
                    "fecha": fecha,
                    "identificador": rec.get("identificador"),
                    "titulo": rec.get("titulo"),
                    "url_xml": url,
                    "http_status": status,
                    "parsed_ok": parsed_ok,
                    "meta": asdict(meta),
                }
                with open(manifest_path, "a", encoding="utf-8") as mf:
                    mf.write(json.dumps(out, ensure_ascii=False) + "\n")

            except Exception as e:
                out = {
                    "kind": "sumario_item_xml",
                    "fecha": fecha,
                    "identificador": rec.get("identificador"),
                    "url_xml": url,
                    "error": str(e),
                }
                with open(manifest_path, "a", encoding="utf-8") as mf:
                    mf.write(json.dumps(out, ensure_ascii=False) + "\n")

    await asyncio.gather(*(worker(r) for r in items))


# -----------------------------
# CLI
# -----------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Descarga BOE orientada a ELI: consolidada (solo ELI) + sumario diario.",
    )
    p.add_argument("--store", default=STORE_DIR, help="Directorio base (por defecto: ./boe_store)")
    p.add_argument("--concurrency", type=int, default=DEFAULT_MAX_CONCURRENCY, help="Máximo de descargas concurrentes")
    p.add_argument("--retries", type=int, default=DEFAULT_RETRIES, help="Reintentos por URL (backoff exponencial)")
    p.add_argument(
        "--proxy-env",
        action="store_true",
        default=True,
        help="Usar HTTP(S)_PROXY/NO_PROXY del entorno (aiohttp trust_env). Por defecto: activo.",
    )

    sub = p.add_subparsers(dest="cmd", required=True)

    # consolidada: descarga todo el catálogo pero filtrando por ELI
    pc = sub.add_parser("consolidada", help="Descarga masiva de legislación consolidada SOLO con url_eli")
    pc.add_argument(
        "--part",
        default="full",
        choices=["full", "metadatos", "analisis", "metadata-eli", "texto", "texto/indice"],
        help="Parte a descargar (por defecto: full)",
    )
    pc.add_argument(
        "--accept",
        default="application/xml",
        help="Accept header (por defecto: application/xml). Para metadatos/analisis/indice puedes usar application/json.",
    )
    pc.add_argument("--from", dest="since_from", default=None, help="Filtro AAAAMMDD por fecha de actualización (inicio)")
    pc.add_argument("--to", dest="since_to", default=None, help="Filtro AAAAMMDD por fecha de actualización (fin)")
    pc.add_argument("--manifest", default="manifest_consolidada_eli.jsonl", help="Nombre del manifest JSONL")

    # eli: descarga por ELI individual (o lista)
    pe = sub.add_parser("eli", help="Descarga norma consolidada resolviendo por URI ELI")
    pe.add_argument("--value", help="ELI concreto (ej: https://www.boe.es/eli/es/l/2015/10/01/40)")
    pe.add_argument("--file", help="Fichero de texto con un ELI por línea")
    pe.add_argument(
        "--part",
        default="full",
        choices=["full", "metadatos", "analisis", "metadata-eli", "texto", "texto/indice"],
        help="Parte a descargar (por defecto: full)",
    )
    pe.add_argument("--accept", default="application/xml", help="Accept header (por defecto: application/xml)")
    pe.add_argument("--manifest", default="manifest_eli_on_demand.jsonl", help="Nombre del manifest JSONL")
    pe.add_argument("--rebuild-index", action="store_true", help="Reconstruye índice ELI->doc_id antes de resolver")

    # sumario
    ps = sub.add_parser("sumario", help="Descarga BOE del día via sumario y baja XML de cada item")
    ps.add_argument("--fecha", required=True, help="Fecha AAAAMMDD")
    ps.add_argument("--manifest", default=None, help="Manifest JSONL (por defecto: manifest_sumario_AAAAMMDD.jsonl)")

    return p


async def amain(args: argparse.Namespace) -> None:
    global STORE_DIR
    global DEFAULT_RETRIES

    STORE_DIR = args.store
    DEFAULT_RETRIES = args.retries

    ensure_dirs()

    connector = aiohttp.TCPConnector(limit=0, ssl=False)
    async with aiohttp.ClientSession(timeout=TIMEOUT, connector=connector, trust_env=bool(args.proxy_env)) as session:
        if args.cmd == "consolidada":
            await download_consolidated_catalog_only_eli(
                session=session,
                max_concurrency=args.concurrency,
                part=args.part,
                accept=args.accept,
                since_from=args.since_from,
                since_to=args.since_to,
                manifest_name=args.manifest,
            )
            return

        if args.cmd == "eli":
            # Cargamos índice existente o lo reconstruimos si se pide
            idx_path = index_path(ELI_INDEX_FILE)
            eli_index: Dict[str, str] = load_json_file(idx_path, {})
            if not isinstance(eli_index, dict):
                eli_index = {}

            if args.rebuild_index or not eli_index:
                eli_index = await build_or_update_eli_index(
                    session=session,
                    since_from=None,
                    since_to=None,
                    only_eli=True,
                )

            elis: List[str] = []
            if args.value:
                elis.append(args.value.strip())
            if args.file:
                with open(args.file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            elis.append(line)

            if not elis:
                raise ValueError("Debes indicar --value o --file para el comando eli")

            await download_consolidated_by_eli(
                session=session,
                eli_index=eli_index,
                max_concurrency=args.concurrency,
                part=args.part,
                accept=args.accept,
                manifest_name=args.manifest,
                elis=elis,
            )
            return

        if args.cmd == "sumario":
            await download_sumario_day(
                session=session,
                fecha=args.fecha,
                max_concurrency=args.concurrency,
                out_manifest_name=args.manifest,
            )
            return

        raise RuntimeError(f"Comando no reconocido: {args.cmd}")


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    asyncio.run(amain(args))


if __name__ == "__main__":
    main()

