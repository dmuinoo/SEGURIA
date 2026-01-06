"""
BOE (datosabiertos) — Descarga + parseo SOLO XML (ELI) + ingesta en Neo4j y Qdrant

Objetivo
--------
1) Partiendo de una lista de URLs XML (idealmente en formato ELI) o de identificadores BOE-A-XXXX-YYYYY,
   descargamos únicamente la representación XML (con HTTP condicional: ETag/Last-Modified).
2) Parseamos el XML para extraer:
   - metadatos del recurso (identificador, título, fechas)
   - unidades de contenido (artículos/disposiciones) como "chunks" textuales
3) Ingestamos:
   - Neo4j: grafo documental (Document -> CONTAINS -> Unit)
   - Qdrant: embeddings por chunk para RAG (payload con evidencia y metadatos)

Requisitos (pip)
----------------
pip install aiohttp lxml qdrant-client neo4j

Variables de entorno recomendadas
--------------------------------
# Almacenamiento local
export BOE_STORE_DIR="./boe_xml_store"

# Neo4j
export NEO4J_URI="neo4j://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="password"

# Qdrant
export QDRANT_URL="http://localhost:6333"
export QDRANT_COLLECTION="boe_eli_chunks"

# Embeddings (Ollama)
export OLLAMA_BASE_URL="http://localhost:11434"
export OLLAMA_EMBED_MODEL="nomic-embed-text"   # o el que uses

Uso
---
1) Si ya tienes las URLs XML (incluyendo el campo 'uri' ELI en tu catálogo), pásalas a ingest_urls().
2) Si solo tienes identificadores BOE-A-..., usa build_boe_eli_xml_url() como aproximación y ajusta el patrón si procede.

Nota importante
---------------
- El XML de BOE puede venir con namespaces y estructuras variables; por eso el parseo usa XPath por local-name()
  y heurísticas. Ajusta extract_units_from_xml() si tu XML concreto tiene tags más específicos.
"""

import asyncio
import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import aiohttp
from lxml import etree

from neo4j import AsyncGraphDatabase
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels


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


async def fetch_one(session: aiohttp.ClientSession, url: str, meta: StoredMeta) -> FetchResult:
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


async def fetch_dedup(session: aiohttp.ClientSession, url: str, meta: StoredMeta) -> FetchResult:
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


async def download_xml_if_changed(session: aiohttp.ClientSession, doc_id: str, url_xml: str) -> Optional[bytes]:
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
    return "ELI-" + hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]


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

@dataclass
class ParsedDocument:
    doc_id: str                 # interno (carpeta)
    source_url: str             # URL origen
    eli_uri: Optional[str]      # URI ELI si aparece
    boe_id: Optional[str]       # BOE-A-... si aparece
    title: Optional[str]
    dates: Dict[str, Optional[str]]
    units: List[Dict[str, Any]]  # chunks: {unit_id, label, text, path}


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


def extract_units_from_xml(root: etree._Element) -> List[Dict[str, Any]]:
    """
    Heurística para extraer “unidades” (artículos/disposiciones) como chunks:
    - Busca nodos cuyo nombre local sea 'articulo'/'artículo'/'disposicion'/'disposición'/'anexo'
    - Si no existen, cae a párrafos grandes por secciones.
    Ajusta aquí cuando veas la estructura real del XML de BOE (es el punto que más se personaliza).
    """
    units: List[Dict[str, Any]] = []

    # 1) Candidatos típicos
    candidates = root.xpath(
        "//*["
        "translate(local-name(), 'ÁÉÍÓÚÜÑ', 'AEIOUUN')="
        "'articulo' or "
        "translate(local-name(), 'ÁÉÍÓÚÜÑ', 'AEIOUUN')="
        "'disposicion' or "
        "translate(local-name(), 'ÁÉÍÓÚÜÑ', 'AEIOUUN')="
        "'anexo'"
        "]"
    )

    for idx, el in enumerate(candidates, start=1):
        label = (
            _first_xpath_text(el, ".//*[translate(local-name(), 'ÁÉÍÓÚÜÑ', 'AEIOUUN')='titulo'][1]")
            or _first_xpath_text(el, ".//*[translate(local-name(), 'ÁÉÍÓÚÜÑ', 'AEIOUUN')='rubrica'][1]")
            or el.get("id")
            or f"unit-{idx}"
        )
        text = _t(el)
        if not text or len(text) < 30:
            continue

        units.append(
            {
                "unit_id": el.get("id") or f"u{idx}",
                "label": label,
                "text": text,
                "path": root.getroottree().getpath(el),
            }
        )

    # 2) Fallback si no hay “artículos/disposiciones” detectables
    if not units:
        # Agrupar por bloques grandes (por ejemplo, secciones/capitulos)
        blocks = root.xpath(
            "//*[translate(local-name(), 'ÁÉÍÓÚÜÑ', 'AEIOUUN')='seccion' or "
            "translate(local-name(), 'ÁÉÍÓÚÜÑ', 'AEIOUUN')='capitulo' or "
            "translate(local-name(), 'ÁÉÍÓÚÜÑ', 'AEIOUUN')='titulo']"
        )
        for idx, el in enumerate(blocks[:50], start=1):
            text = _t(el)
            if not text or len(text) < 200:
                continue
            units.append(
                {
                    "unit_id": el.get("id") or f"b{idx}",
                    "label": _first_xpath_text(el, ".//*[1]") or f"block-{idx}",
                    "text": text,
                    "path": root.getroottree().getpath(el),
                }
            )

    return units


def parse_boe_xml(doc_id: str, source_url: str, xml_bytes: bytes) -> ParsedDocument:
    """
    Parsea XML y devuelve un modelo ParsedDocument listo para:
    - upsert en Neo4j
    - indexado en Qdrant
    """
    parser = etree.XMLParser(recover=True, huge_tree=True, remove_comments=True)
    root = etree.fromstring(xml_bytes, parser=parser)

    # Metadatos (heurísticos)
    boe_id = _first_xpath_text(root, "//*[local-name()='identificador'][1]")
    eli_uri = _first_xpath_text(root, "//*[translate(local-name(), 'ÁÉÍÓÚÜÑ', 'AEIOUUN')='uri'][1]")

    # En muchos XML de BOE el título está en <titulo> o similar (ojo: puede haber muchos)
    title = (
        _first_xpath_text(root, "/*//*[translate(local-name(), 'ÁÉÍÓÚÜÑ', 'AEIOUUN')='titulo'][1]")
        or _first_xpath_text(root, "/*//*[translate(local-name(), 'ÁÉÍÓÚÜÑ', 'AEIOUUN')='titulo_disposicion'][1]")
        or _first_xpath_text(root, "/*//*[translate(local-name(), 'ÁÉÍÓÚÜÑ', 'AEIOUUN')='titulo'][1]")
    )

    dates = {
        "fecha_disposicion": _first_xpath_text(root, "//*[translate(local-name(), 'ÁÉÍÓÚÜÑ', 'AEIOUUN')='fecha_disposicion'][1]"),
        "fecha_publicacion": _first_xpath_text(root, "//*[translate(local-name(), 'ÁÉÍÓÚÜÑ', 'AEIOUUN')='fecha_publicacion'][1]"),
        "fecha_vigencia": _first_xpath_text(root, "//*[translate(local-name(), 'ÁÉÍÓÚÜÑ', 'AEIOUUN')='fecha_vigencia'][1]"),
        "fecha_actualizacion": _first_xpath_text(root, "//*[translate(local-name(), 'ÁÉÍÓÚÜÑ', 'AEIOUUN')='fecha_actualizacion'][1]"),
    }

    units = extract_units_from_xml(root)

    return ParsedDocument(
        doc_id=doc_id,
        source_url=source_url,
        eli_uri=eli_uri,
        boe_id=boe_id,
        title=title,
        dates=dates,
        units=units,
    )


# ----------------------------
# Embeddings (Ollama) + Qdrant
# ----------------------------

class OllamaEmbedder:
    """
    Cliente mínimo para embeddings con Ollama:
    POST /api/embeddings {"model":"...", "prompt":"..."}
    """
    def __init__(self, base_url: str, model: str, session: aiohttp.ClientSession):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.session = session

    async def embed(self, text: str) -> List[float]:
        url = f"{self.base_url}/api/embeddings"
        payload = {"model": self.model, "prompt": text}
        async with self.session.post(url, json=payload, headers=DEFAULT_HEADERS) as r:
            r.raise_for_status()
            data = await r.json()
            # Respuesta típica: {"embedding":[...]}
            emb = data.get("embedding")
            if not emb:
                raise RuntimeError(f"Ollama no devolvió embedding. Respuesta: {data}")
            return emb


def qdrant_ensure_collection(client: QdrantClient, collection: str, vector_size: int) -> None:
    """
    Crea colección si no existe (o valida tamaño). Para simplicidad, si existe no tocamos.
    """
    existing = {c.name for c in client.get_collections().collections}
    if collection in existing:
        return
    client.create_collection(
        collection_name=collection,
        vectors_config=qmodels.VectorParams(size=vector_size, distance=qmodels.Distance.COSINE),
    )


async def qdrant_upsert_document(
    qdrant: QdrantClient,
    collection: str,
    doc: ParsedDocument,
    embedder: OllamaEmbedder,
) -> None:
    """
    Inserta/actualiza en Qdrant un punto por unidad (chunk).
    ID determinista por (doc_id + unit_id).
    """
    # Embeddings: en RAG, conviene chunk size razonable.
    # Aquí usamos la unidad completa; si te queda muy grande, añade un chunker adicional.
    points: List[qmodels.PointStruct] = []

    # Para crear colección necesitamos conocer tamaño del vector: lo medimos con la primera unidad.
    if not doc.units:
        return

    first_vec = await embedder.embed(doc.units[0]["text"])
    qdrant_ensure_collection(qdrant, collection, vector_size=len(first_vec))

    # Punto 0
    points.append(
        qmodels.PointStruct(
            id=int(hashlib.sha1(f"{doc.doc_id}::{doc.units[0]['unit_id']}".encode()).hexdigest()[:16], 16),
            vector=first_vec,
            payload={
                "doc_id": doc.doc_id,
                "boe_id": doc.boe_id,
                "eli_uri": doc.eli_uri,
                "title": doc.title,
                "source_url": doc.source_url,
                "unit_id": doc.units[0]["unit_id"],
                "label": doc.units[0]["label"],
                "path": doc.units[0]["path"],
                "text": doc.units[0]["text"],
                **{k: v for k, v in doc.dates.items() if v},
            },
        )
    )

    # Resto en serie (puedes paralelizar, pero ojo con rate-limit y RAM)
    for u in doc.units[1:]:
        vec = await embedder.embed(u["text"])
        points.append(
            qmodels.PointStruct(
                id=int(hashlib.sha1(f"{doc.doc_id}::{u['unit_id']}".encode()).hexdigest()[:16], 16),
                vector=vec,
                payload={
                    "doc_id": doc.doc_id,
                    "boe_id": doc.boe_id,
                    "eli_uri": doc.eli_uri,
                    "title": doc.title,
                    "source_url": doc.source_url,
                    "unit_id": u["unit_id"],
                    "label": u["label"],
                    "path": u["path"],
                    "text": u["text"],
                    **{k: v for k, v in doc.dates.items() if v},
                },
            )
        )

    qdrant.upsert(collection_name=collection, points=points)


# ----------------------------
# Neo4j: grafo documental
# ----------------------------

NEO4J_CONSTRAINTS = [
    "CREATE CONSTRAINT doc_doc_id IF NOT EXISTS FOR (d:Document) REQUIRE d.doc_id IS UNIQUE",
    "CREATE CONSTRAINT unit_key IF NOT EXISTS FOR (u:Unit) REQUIRE u.key IS UNIQUE",
]


async def neo4j_init(driver) -> None:
    async with driver.session() as s:
        for c in NEO4J_CONSTRAINTS:
            await s.run(c)


async def neo4j_upsert_document(driver, doc: ParsedDocument) -> None:
    """
    Modelo de grafo:
      (:Document {doc_id, boe_id, eli_uri, title, ...})-[:CONTAINS]->(:Unit {key, unit_id, label, path})
    """
    async with driver.session() as s:
        await s.run(
            """
            MERGE (d:Document {doc_id: $doc_id})
            SET d.boe_id = coalesce($boe_id, d.boe_id),
                d.eli_uri = coalesce($eli_uri, d.eli_uri),
                d.title = coalesce($title, d.title),
                d.source_url = coalesce($source_url, d.source_url),
                d.fecha_disposicion = coalesce($fecha_disposicion, d.fecha_disposicion),
                d.fecha_publicacion = coalesce($fecha_publicacion, d.fecha_publicacion),
                d.fecha_vigencia = coalesce($fecha_vigencia, d.fecha_vigencia),
                d.fecha_actualizacion = coalesce($fecha_actualizacion, d.fecha_actualizacion)
            """,
            {
                "doc_id": doc.doc_id,
                "boe_id": doc.boe_id,
                "eli_uri": doc.eli_uri,
                "title": doc.title,
                "source_url": doc.source_url,
                **doc.dates,
            },
        )

        # Unidades
        for u in doc.units:
            key = f"{doc.doc_id}::{u['unit_id']}"
            await s.run(
                """
                MATCH (d:Document {doc_id: $doc_id})
                MERGE (u:Unit {key: $key})
                SET u.unit_id = $unit_id,
                    u.label = $label,
                    u.path = $path,
                    u.text = $text
                MERGE (d)-[:CONTAINS]->(u)
                """,
                {
                    "doc_id": doc.doc_id,
                    "key": key,
                    "unit_id": u["unit_id"],
                    "label": u["label"],
                    "path": u["path"],
                    "text": u["text"],
                },
            )


# ----------------------------
# Orquestación: descargar -> parsear -> ingestar
# ----------------------------

async def process_one_xml(
    session: aiohttp.ClientSession,
    url_xml: str,
    doc_id_hint: str,
    neo4j_driver,
    qdrant: QdrantClient,
    qdrant_collection: str,
    embedder: OllamaEmbedder,
) -> None:
    """
    Pipeline por documento:
      1) descarga condicional (solo si cambia)
      2) parseo XML
      3) upsert Neo4j
      4) upsert Qdrant
    """
    doc_id = normalize_doc_id(doc_id_hint)

    xml_bytes = await download_xml_if_changed(session, doc_id, url_xml)
    if xml_bytes is None:
        # Si ya lo tienes en disco y quieres reingestar, podrías cargarlo:
        dp = data_path(doc_id)
        if not os.path.exists(dp):
            return
        with open(dp, "rb") as f:
            xml_bytes = f.read()

    parsed = parse_boe_xml(doc_id=doc_id, source_url=url_xml, xml_bytes=xml_bytes)

    # Neo4j
    await neo4j_upsert_document(neo4j_driver, parsed)

    # Qdrant
    await qdrant_upsert_document(qdrant, qdrant_collection, parsed, embedder)


async def ingest_urls(urls: List[Tuple[str, str]]) -> None:
    """
    Ingesta desde lista explícita:
      urls = [(doc_id_hint, url_xml), ...]
    doc_id_hint puede ser BOE-A-... o uri ELI.
    """
    # Neo4j config
    neo4j_uri = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_pass = os.getenv("NEO4J_PASSWORD", "password")

    # Qdrant config
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    qdrant_collection = os.getenv("QDRANT_COLLECTION", "boe_eli_chunks")

    # Ollama embeddings config
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

    qdrant = QdrantClient(url=qdrant_url)
    neo4j_driver = AsyncGraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_pass))

    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        embedder = OllamaEmbedder(base_url=ollama_base_url, model=ollama_model, session=session)

        # Inicializa Neo4j (constraints)
        await neo4j_init(neo4j_driver)

        # Procesa en paralelo (semaforizado por _sem dentro de fetch)
        tasks = [
            process_one_xml(
                session=session,
                url_xml=url_xml,
                doc_id_hint=doc_id_hint,
                neo4j_driver=neo4j_driver,
                qdrant=qdrant,
                qdrant_collection=qdrant_collection,
                embedder=embedder,
            )
            for (doc_id_hint, url_xml) in urls
        ]
        await asyncio.gather(*tasks)

    await neo4j_driver.close()


# ----------------------------
# (Opcional) Descubrir URLs desde el catálogo de legislación consolidada
# ----------------------------

async def fetch_leg_consolidada_catalog(session: aiohttp.ClientSession) -> Dict[str, Any]:
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
        uri = _first_xpath_text(item, ".//*[translate(local-name(), 'ÁÉÍÓÚÜÑ', 'AEIOUUN')='uri'][1]")
        url_xml = _first_xpath_text(item, ".//*[translate(local-name(), 'ÁÉÍÓÚÜÑ', 'AEIOUUN')='url_xml'][1]")

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

