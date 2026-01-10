"""
BOE (datosabiertos) — Descarga SOLO XML (ELI) con cache en disco

Objetivo
--------
1) Partiendo de una lista de URLs XML (idealmente en formato ELI) o de identificadores BOE-A-XXXX-YYYYY,
   descargamos únicamente la representación XML (con HTTP condicional: ETag/Last-Modified).
2) Guardamos el XML y la metadata (etag/last-modified/sha256) en disco para evitar descargas repetidas.

Requisitos (pip)
----------------
pip install aiohttp lxml

Variables de entorno recomendadas
--------------------------------
# Almacenamiento local
export BOE_STORE_DIR="./boe_xml_store"

Uso
---
1) Si ya tienes las URLs XML (incluyendo el campo 'uri' ELI en tu catálogo), pásalas a ingest_urls().
2) Si solo tienes identificadores BOE-A-..., usa build_boe_eli_xml_url() como aproximación y ajusta el patrón si procede.

Nota importante
---------------
- El XML de BOE puede venir con namespaces y estructuras variables; por eso el parseo usa XPath por local-name()
  en las funciones de catálogo. Ajusta parse_catalog_items_xml() si tu XML concreto tiene tags más específicos.
"""

import asyncio
import hashlib
from functools import lru_cache
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import aiohttp
from lxml import etree

# ----------------------------
# Configuración general
# ----------------------------

BASE = "https://www.boe.es"
# API mencionada por ti en turnos previos (catálogo de legislación consolidada):
LEG_CONS_API = f"{BASE}/datosabiertos/api/legislacion-consolidada"

STORE_DIR = os.getenv("BOE_STORE_DIR", "./boe_xml_store")

MAX_CONCURRENCY = 25
TIMEOUT = aiohttp.ClientTimeout(total=90)

DEFAULT_HEADERS = {"User-Agent": "boe-eli-xml-ingestor/1.0"}
_sem = asyncio.Semaphore(MAX_CONCURRENCY)

# Dedupe de descargas en vuelo por URL (evita doble GET si se repite)
_inflight: Dict[str, asyncio.Task] = {}
_inflight_lock = asyncio.Lock()

# ----------------------------
# Persistencia (disco): data + meta
# ----------------------------


@dataclass
class StoredMeta:
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    sha256: Optional[str] = None
    content_type: Optional[str] = None


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def ensure_dirs() -> None:
    os.makedirs(os.path.join(STORE_DIR, "data"), exist_ok=True)
    os.makedirs(os.path.join(STORE_DIR, "meta"), exist_ok=True)


def data_path(doc_id: str) -> str:
    # Guardamos siempre como .xml para simplificar (solo XML)
    return os.path.join(STORE_DIR, "data", doc_id, "document.xml")


def meta_path(doc_id: str) -> str:
    return os.path.join(STORE_DIR, "meta", doc_id, "document.json")


def load_meta(doc_id: str) -> StoredMeta:
    mp = meta_path(doc_id)
    if not os.path.exists(mp):
        return StoredMeta()
    with open(mp, "r", encoding="utf-8") as f:
        d = json.load(f)
    return StoredMeta(
        etag=d.get("etag"),
        last_modified=d.get("last_modified"),
        sha256=d.get("sha256"),
        content_type=d.get("content_type"),
    )


def save_meta(doc_id: str, meta: StoredMeta) -> None:
    mp = meta_path(doc_id)
    os.makedirs(os.path.dirname(mp), exist_ok=True)
    with open(mp, "w", encoding="utf-8") as f:
        json.dump(
            {
                "etag": meta.etag,
                "last_modified": meta.last_modified,
                "sha256": meta.sha256,
                "content_type": meta.content_type,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )


def save_xml(doc_id: str, data: bytes) -> None:
    dp = data_path(doc_id)
    os.makedirs(os.path.dirname(dp), exist_ok=True)
    with open(dp, "wb") as f:
        f.write(data)


# ----------------------------
# HTTP: fetch condicional + dedupe
# ----------------------------


@dataclass
class FetchResult:
    url: str
    status: int
    data: Optional[bytes]
    etag: Optional[str]
    last_modified: Optional[str]
    content_type: Optional[str]
    not_modified: bool = False


async def fetch_one(
    session: aiohttp.ClientSession, url: str, meta: StoredMeta
) -> FetchResult:
    """
    Descarga una URL con soporte de HTTP condicional:
    - If-None-Match / If-Modified-Since
    - Si 304: not_modified=True y data=None
    """
    headers = dict(DEFAULT_HEADERS)
    headers["Accept"] = "application/xml, text/xml;q=0.9, */*;q=0.1"
    if meta.etag:
        headers["If-None-Match"] = meta.etag
    if meta.last_modified:
        headers["If-Modified-Since"] = meta.last_modified

    async with _sem:
        async with session.get(url, headers=headers) as r:
            if r.status == 304:
                return FetchResult(
                    url=url,
                    status=304,
                    data=None,
                    etag=meta.etag,
                    last_modified=meta.last_modified,
                    content_type=meta.content_type,
                    not_modified=True,
                )
            r.raise_for_status()
            data = await r.read()
            return FetchResult(
                url=url,
                status=r.status,
                data=data,
                etag=r.headers.get("ETag"),
                last_modified=r.headers.get("Last-Modified"),
                content_type=r.headers.get("Content-Type"),
                not_modified=False,
            )


async def fetch_dedup(
    session: aiohttp.ClientSession, url: str, meta: StoredMeta
) -> FetchResult:
    """
    Dedupe por URL: si varias corrutinas piden el mismo recurso, solo hace un GET real.
    """
    async with _inflight_lock:
        t = _inflight.get(url)
        if t is None:
            t = asyncio.create_task(fetch_one(session, url, meta))
            _inflight[url] = t
    try:
        return await t
    finally:
        async with _inflight_lock:
            if _inflight.get(url) is t:
                _inflight.pop(url, None)


async def download_xml_if_changed(
    session: aiohttp.ClientSession, doc_id: str, url_xml: str
) -> Optional[bytes]:
    """
    Descarga XML, lo persiste en disco solo si cambió (por ETag/LM o por hash).
    Devuelve bytes (si hay cambios) o None (si 304 o mismo sha256).
    """
    ensure_dirs()

    meta_old = load_meta(doc_id)
    res = await fetch_dedup(session, url_xml, meta_old)

    if res.not_modified or res.data is None:
        return None

    h = sha256_bytes(res.data)
    if meta_old.sha256 and meta_old.sha256 == h:
        # Cambió cabecera pero contenido idéntico
        return None

    save_xml(doc_id, res.data)
    save_meta(
        doc_id,
        StoredMeta(
            etag=res.etag or meta_old.etag,
            last_modified=res.last_modified or meta_old.last_modified,
            sha256=h,
            content_type=res.content_type,
        ),
    )
    return res.data


# ----------------------------
# Helpers: construir URL XML (ELI/BOE)
# ----------------------------


def normalize_doc_id(s: str) -> str:
    """
    Usamos doc_id como nombre de carpeta:
    - Si viene un ELI URI largo, lo hasheamos para path estable
    - Si es BOE-A-..., lo mantenemos
    """
    if s.startswith("BOE-"):
        return s
    # ELI u otras URIs: hash corto + prefijo
    return "ELI-" + sha1_hex(s)[:16]


@lru_cache(maxsize=4096)
def sha1_hex(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def build_boe_eli_xml_url(identificador_boe: str) -> str:
    """
    Aproximación de URL para pedir XML de legislación consolidada por identificador.
    Ajusta el patrón si tu API exige otros parámetros.
    """
    # Muchas APIs de BOE aceptan identificador como parámetro. Si ya tienes la URL XML exacta, mejor úsala.
    # Ejemplo orientativo:
    return f"{LEG_CONS_API}?id={identificador_boe}&formato=xml"


# ----------------------------
# Parseo XML (robusto a namespaces)
# ----------------------------


def _t(el: Optional[etree._Element]) -> Optional[str]:
    if el is None:
        return None
    txt = " ".join("".join(el.itertext()).split())
    return txt or None


def _first_xpath_text(root: etree._Element, xpath: str) -> Optional[str]:
    # XPath con local-name() para tolerar namespaces
    found = root.xpath(xpath)
    if not found:
        return None
    if isinstance(found[0], etree._Element):
        return _t(found[0])
    # Si xpath devuelve strings
    return str(found[0]).strip() if str(found[0]).strip() else None


# ----------------------------
# Orquestación: descargar
# ----------------------------


async def process_one_xml(
    session: aiohttp.ClientSession,
    url_xml: str,
    doc_id_hint: str,
) -> None:
    """
    Pipeline por documento:
      1) descarga condicional (solo si cambia)
    """
    doc_id = normalize_doc_id(doc_id_hint)

    xml_bytes = await download_xml_if_changed(session, doc_id, url_xml)
    if xml_bytes is None:
        dp = data_path(doc_id)
        if not os.path.exists(dp):
            return
        return


async def ingest_urls(urls: List[Tuple[str, str]]) -> None:
    """
    Descarga desde lista explícita:
      urls = [(doc_id_hint, url_xml), ...]
    doc_id_hint puede ser BOE-A-... o uri ELI.
    """
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        tasks = [
            process_one_xml(
                session=session,
                url_xml=url_xml,
                doc_id_hint=doc_id_hint,
            )
            for (doc_id_hint, url_xml) in urls
        ]
        await asyncio.gather(*tasks)


# ----------------------------
# (Opcional) Descubrir URLs desde el catálogo de legislación consolidada
# ----------------------------


async def fetch_leg_consolidada_catalog(
    session: aiohttp.ClientSession,
) -> Dict[str, Any]:
    """
    Descarga el catálogo (si tu endpoint devuelve XML/JSON con items).
    IMPORTANTE: el formato exacto puede variar; ajusta según lo que tú ya ves (tu <item> ...).
    """
    # Si el endpoint devuelve XML por defecto, mantenemos Accept para XML.
    headers = dict(DEFAULT_HEADERS)
    headers["Accept"] = "application/xml, text/xml;q=0.9"
    async with session.get(LEG_CONS_API, headers=headers) as r:
        r.raise_for_status()
        return {"raw": await r.read(), "content_type": r.headers.get("Content-Type")}


def parse_catalog_items_xml(xml_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Parsea el XML de catálogo y devuelve items con:
      - identificador (BOE-A-...)
      - uri (ELI)
      - (si existe) url_xml

    Ajusta XPaths si tu catálogo tiene estructura distinta.
    """
    parser = etree.XMLParser(recover=True, huge_tree=True, remove_comments=True)
    root = etree.fromstring(xml_bytes, parser=parser)

    items = []
    for item in root.xpath("//*[local-name()='item']"):
        identificador = _first_xpath_text(item, ".//*[local-name()='identificador'][1]")
        uri = _first_xpath_text(
            item, ".//*[translate(local-name(), 'ÁÉÍÓÚÜÑ', 'AEIOUUN')='uri'][1]"
        )
        url_xml = _first_xpath_text(
            item, ".//*[translate(local-name(), 'ÁÉÍÓÚÜÑ', 'AEIOUUN')='url_xml'][1]"
        )

        # Si el catálogo NO trae url_xml, la construimos por identificador (aproximación)
        if not url_xml and identificador:
            url_xml = build_boe_eli_xml_url(identificador)

        if identificador and url_xml:
            items.append(
                {
                    "identificador": identificador,
                    "uri": uri,
                    "url_xml": url_xml,
                }
            )
    return items


async def ingest_from_catalog(limit: int = 50) -> None:
    """
    Descubre documentos desde el catálogo y los ingesta (solo XML).
    """
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        cat = await fetch_leg_consolidada_catalog(session)
        xml_bytes = cat["raw"]
        items = parse_catalog_items_xml(xml_bytes)[:limit]

    urls = []
    for it in items:
        # Preferimos doc_id_hint = uri ELI si existe, si no BOE-A
        doc_id_hint = it.get("uri") or it["identificador"]
        urls.append((doc_id_hint, it["url_xml"]))

    await ingest_urls(urls)


# ----------------------------
# Main
# ----------------------------

if __name__ == "__main__":
    # Caso A) Ya tienes las URLs (recomendado)
    # Sustituye por tus URLs reales (ELI o directas a xml).
    demo_urls = [
        # ("BOE-A-2003-10295", "https://www.boe.es/datosabiertos/api/legislacion-consolidada?id=BOE-A-2003-10295&formato=xml"),
        # ("eli:es-cv:l:2003-04-10;11", "https://.../eli/.../xml"),
    ]
    if demo_urls:
        asyncio.run(ingest_urls(demo_urls))
    else:
        # Caso B) Descubrir desde catálogo (si tu endpoint devuelve <item> como el ejemplo)
        asyncio.run(ingest_from_catalog(limit=50))
