#!/usr/bin/env python3
from __future__ import annotations

import os, re, json, hashlib
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Iterator

import psycopg
import polars as pl
from lxml import etree

PG_DSN = os.getenv("PG_DSN", "").strip()
if not PG_DSN:
    raise SystemExit("Falta PG_DSN. Ej: postgresql://user:pass@127.0.0.1:5432/boe")

DATA_DIR = Path(os.getenv("XML_DIR", "boe_store/data"))
PARQUET_DIR = Path(os.getenv("PARQUET_DIR", "boe_store/parquet"))
PARQUET_DIR.mkdir(parents=True, exist_ok=True)

BATCH_SIZE = int(os.getenv("BATCH_SIZE", "2000"))

# ----------------------
# DDL (modelo genérico)
# ----------------------
DDL = """
CREATE SCHEMA IF NOT EXISTS boe;

CREATE TABLE IF NOT EXISTS boe.boe_doc (
  doc_id        BIGSERIAL PRIMARY KEY,
  file_path     TEXT NOT NULL UNIQUE,
  file_name     TEXT NOT NULL,
  sha256        TEXT NOT NULL,
  file_bytes    BIGINT NOT NULL,
  root_tag      TEXT NOT NULL,
  ingested_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  status        TEXT NOT NULL DEFAULT 'ACCEPTED',
  error         TEXT NULL
);

CREATE TABLE IF NOT EXISTS boe.boe_node (
  node_id       BIGSERIAL PRIMARY KEY,
  doc_id        BIGINT NOT NULL REFERENCES boe.boe_doc(doc_id) ON DELETE CASCADE,
  parent_node_id BIGINT NULL REFERENCES boe.boe_node(node_id) ON DELETE CASCADE,
  ord           INT NOT NULL,
  depth         INT NOT NULL,
  tag           TEXT NOT NULL,
  xpath         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_boe_node_doc ON boe.boe_node(doc_id);
CREATE INDEX IF NOT EXISTS idx_boe_node_xpath ON boe.boe_node(xpath);

CREATE TABLE IF NOT EXISTS boe.boe_attr (
  attr_id       BIGSERIAL PRIMARY KEY,
  node_id       BIGINT NOT NULL REFERENCES boe.boe_node(node_id) ON DELETE CASCADE,
  name          TEXT NOT NULL,
  value         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_boe_attr_node ON boe.boe_attr(node_id);
CREATE INDEX IF NOT EXISTS idx_boe_attr_name ON boe.boe_attr(name);

CREATE TABLE IF NOT EXISTS boe.boe_text (
  text_id       BIGSERIAL PRIMARY KEY,
  node_id       BIGINT NOT NULL REFERENCES boe.boe_node(node_id) ON DELETE CASCADE,
  text          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS boe.boe_kv (
  kv_id         BIGSERIAL PRIMARY KEY,
  doc_id        BIGINT NOT NULL REFERENCES boe.boe_doc(doc_id) ON DELETE CASCADE,
  xpath         TEXT NOT NULL,
  key           TEXT NOT NULL,
  value         TEXT NOT NULL,
  value_type    TEXT NOT NULL,
  ord           INT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_boe_kv_doc ON boe.boe_kv(doc_id);
CREATE INDEX IF NOT EXISTS idx_boe_kv_xpath ON boe.boe_kv(xpath);
CREATE INDEX IF NOT EXISTS idx_boe_kv_key ON boe.boe_kv(key);
"""

# ----------------------
# Utilidades
# ----------------------
WS_RE = re.compile(r"\s+")
URL_RE = re.compile(r"^https?://", re.I)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
INT_RE = re.compile(r"^-?\d+$")
FLOAT_RE = re.compile(r"^-?\d+\.\d+$")
BOE_ID_RE = re.compile(r"\bBOE-[A-Z]-\d{4}-\d+\b")


def norm(s: str) -> str:
    return WS_RE.sub(" ", s).strip()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def guess_type(v: str) -> str:
    v = norm(v)
    if not v:
        return "empty"
    if BOE_ID_RE.search(v):
        return "boe_id"
    if DATE_RE.match(v):
        return "date"
    if INT_RE.match(v):
        return "int"
    if FLOAT_RE.match(v):
        return "float"
    if URL_RE.match(v):
        return "url"
    if len(v) > 300:
        return "text_long"
    return "text"


def iter_xml_files(root: Path) -> Iterator[Path]:
    if root.is_file() and root.suffix.lower() in (".xml", ".html", ".xhtml"):
        yield root
        return
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in (".xml", ".html", ".xhtml"):
            yield p


def qname_local(tag) -> str:
    if not isinstance(tag, str):
        return str(tag)
    try:
        return etree.QName(tag).localname
    except Exception:
        return tag


# ----------------------
# Descubrimiento de paths (schema “cuerpo”)
# ----------------------
def discover_paths(sample_files: List[Path], max_files: int = 50) -> Dict[str, Dict]:
    """
    Devuelve un catálogo de XPaths con:
      - ocurrencias
      - tipos dominantes de valores hoja
    """
    from collections import Counter, defaultdict

    stats = defaultdict(lambda: {"count": 0, "types": Counter()})

    for f in sample_files[:max_files]:
        # stack de (tag_local, index_en_hermanos)
        stack: List[Tuple[str, int]] = []
        sibling_counters: List[Dict[str, int]] = []

        for event, elem in etree.iterparse(
            str(f), events=("start", "end"), huge_tree=True, recover=True
        ):
            if event == "start":
                tag = qname_local(elem.tag)
                if not sibling_counters:
                    sibling_counters.append({})
                idx = sibling_counters[-1].get(tag, 0) + 1
                sibling_counters[-1][tag] = idx

                stack.append((tag, idx))
                sibling_counters.append({})

            else:
                # construir xpath con índices para distinguir repetidos: /a[1]/b[2]/c[1]
                parts = [f"{t}[{i}]" for (t, i) in stack]
                xpath = "/" + "/".join(parts)

                # hoja si tiene texto no vacío
                txt = norm(elem.text or "")
                if txt:
                    stats[xpath]["count"] += 1
                    stats[xpath]["types"][guess_type(txt)] += 1

                # atributos como hojas: /.../@attr
                for k, v in (elem.attrib or {}).items():
                    ax = xpath + f"/@{k}"
                    vv = norm(str(v))
                    if vv:
                        stats[ax]["count"] += 1
                        stats[ax]["types"][guess_type(vv)] += 1

                # limpieza streaming
                elem.clear()
                while elem.getprevious() is not None:
                    del elem.getparent()[0]

                stack.pop()
                sibling_counters.pop()

    # compactar
    out = {}
    for xp, d in stats.items():
        dominant = None
        if d["types"]:
            dominant = d["types"].most_common(1)[0][0]
        out[xp] = {
            "count": d["count"],
            "dominant_type": dominant,
            "type_hist": dict(d["types"]),
        }
    return out


# ----------------------
# Ingesta: shred completo
# ----------------------
def upsert_doc(conn: psycopg.Connection, file_path: Path, root_tag: str) -> int:
    row = conn.execute(
        "SELECT doc_id FROM boe.boe_doc WHERE file_path=%s", (str(file_path),)
    ).fetchone()
    if row:
        return int(row[0])

    digest = sha256_file(file_path)
    size = file_path.stat().st_size
    row = conn.execute(
        """
        INSERT INTO boe.boe_doc(file_path,file_name,sha256,file_bytes,root_tag,status)
        VALUES (%s,%s,%s,%s,%s,'ACCEPTED')
        RETURNING doc_id
        """,
        (str(file_path), file_path.name, digest, size, root_tag),
    ).fetchone()
    conn.commit()
    return int(row[0])


def ingest_file(conn: psycopg.Connection, file_path: Path) -> List[dict]:
    """
    Ingresa el XML/HTML completo en boe_node/attr/text/kv.
    Además devuelve filas para Parquet (kv) en batches.
    """
    # detectar root rápido
    root_tag = None
    for _, el in etree.iterparse(
        str(file_path), events=("start",), huge_tree=True, recover=True
    ):
        root_tag = qname_local(el.tag)
        break
    if not root_tag:
        raise RuntimeError("No se pudo leer root tag")

    doc_id = upsert_doc(conn, file_path, root_tag)

    # Para mapear elem -> node_id sin guardar el elem (no es hashable estable), usamos stack paralelo
    node_id_stack: List[Optional[int]] = []
    stack: List[Tuple[str, int]] = []
    sibling_counters: List[Dict[str, int]] = []
    ord_counter = 0

    kv_rows_for_parquet: List[dict] = []

    for event, elem in etree.iterparse(
        str(file_path), events=("start", "end"), huge_tree=True, recover=True
    ):
        if event == "start":
            tag = qname_local(elem.tag)

            if not sibling_counters:
                sibling_counters.append({})
            idx = sibling_counters[-1].get(tag, 0) + 1
            sibling_counters[-1][tag] = idx

            stack.append((tag, idx))
            sibling_counters.append({})

            parts = [f"{t}[{i}]" for (t, i) in stack]
            xpath = "/" + "/".join(parts)

            parent_node_id = node_id_stack[-1] if node_id_stack else None
            ord_counter += 1
            depth = len(stack) - 1

            row = conn.execute(
                """
                INSERT INTO boe.boe_node(doc_id,parent_node_id,ord,depth,tag,xpath)
                VALUES (%s,%s,%s,%s,%s,%s)
                RETURNING node_id
                """,
                (doc_id, parent_node_id, ord_counter, depth, tag, xpath),
            ).fetchone()
            node_id = int(row[0])
            node_id_stack.append(node_id)

            # atributos
            if elem.attrib:
                attrs = [
                    (node_id, k, str(v)) for k, v in elem.attrib.items() if norm(str(v))
                ]
                if attrs:
                    conn.executemany(
                        "INSERT INTO boe.boe_attr(node_id,name,value) VALUES (%s,%s,%s)",
                        attrs,
                    )

        else:
            node_id = node_id_stack[-1] if node_id_stack else None
            parts = [f"{t}[{i}]" for (t, i) in stack]
            xpath = "/" + "/".join(parts)

            # texto
            txt = norm(elem.text or "")
            if txt and node_id is not None:
                conn.execute(
                    "INSERT INTO boe.boe_text(node_id,text) VALUES (%s,%s)",
                    (node_id, txt),
                )

                # KV: guardamos valores hoja para consultas y Parquet
                # key = tag local actual
                key = stack[-1][0] if stack else "text"
                vtype = guess_type(txt)

                conn.execute(
                    "INSERT INTO boe.boe_kv(doc_id,xpath,key,value,value_type,ord) VALUES (%s,%s,%s,%s,%s,%s)",
                    (doc_id, xpath, key, txt, vtype, ord_counter),
                )
                kv_rows_for_parquet.append(
                    {
                        "doc_id": doc_id,
                        "xpath": xpath,
                        "key": key,
                        "value": txt,
                        "value_type": vtype,
                        "ord": ord_counter,
                    }
                )

            # atributos también a KV (opcional, útil)
            if elem.attrib:
                for k, v in elem.attrib.items():
                    vv = norm(str(v))
                    if vv:
                        ax = xpath + f"/@{k}"
                        vtype = guess_type(vv)
                        conn.execute(
                            "INSERT INTO boe.boe_kv(doc_id,xpath,key,value,value_type,ord) VALUES (%s,%s,%s,%s,%s,%s)",
                            (doc_id, ax, f"@{k}", vv, vtype, ord_counter),
                        )
                        kv_rows_for_parquet.append(
                            {
                                "doc_id": doc_id,
                                "xpath": ax,
                                "key": f"@{k}",
                                "value": vv,
                                "value_type": vtype,
                                "ord": ord_counter,
                            }
                        )

            # limpieza streaming
            elem.clear()
            while elem.getprevious() is not None:
                del elem.getparent()[0]

            stack.pop()
            sibling_counters.pop()
            node_id_stack.pop()

    conn.commit()
    return kv_rows_for_parquet


def write_parquet(rows: List[dict], out_dir: Path) -> Path:
    if not rows:
        return out_dir
    df = pl.DataFrame(rows)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = out_dir / f"boe_kv_{ts}.parquet"
    df.write_parquet(out)
    return out


def main():
    files = list(iter_xml_files(DATA_DIR))
    if not files:
        raise SystemExit(f"No hay ficheros XML/HTML en {DATA_DIR}")

    with psycopg.connect(PG_DSN) as conn:
        conn.execute(DDL)
        conn.commit()

        # 1) descubrir “cuerpo” de schema a partir de muestras
        discovered = discover_paths(files, max_files=min(50, len(files)))
        schema_out = PARQUET_DIR / "discovered_schema.json"
        schema_out.write_text(
            json.dumps(discovered, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # 2) ingesta completa + Parquet KV por batches
        batch: List[dict] = []
        for i, f in enumerate(files, 1):
            kv = ingest_file(conn, f)
            batch.extend(kv)

            if len(batch) >= BATCH_SIZE:
                out = write_parquet(batch, PARQUET_DIR)
                print(f"[{i}/{len(files)}] Parquet batch -> {out}")
                batch.clear()

        if batch:
            out = write_parquet(batch, PARQUET_DIR)
            print(f"[DONE] Parquet final -> {out}")

        print(f"Schema descubierto -> {schema_out}")
        print("OK")


if __name__ == "__main__":
    main()
