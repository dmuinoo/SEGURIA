"""Postgres ingest helpers for boe_downloader_eli."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any, Dict, Optional

DB_UPSERT_RESOURCE = """
INSERT INTO ingest.resource (source_kind, resource_key, url_xml, url_json, url_pdf)
VALUES ($1,$2,$3,$4,$5)
ON CONFLICT (source_kind, resource_key)
DO UPDATE SET
  url_xml  = COALESCE(EXCLUDED.url_xml,  ingest.resource.url_xml),
  url_json = COALESCE(EXCLUDED.url_json, ingest.resource.url_json),
  url_pdf  = COALESCE(EXCLUDED.url_pdf,  ingest.resource.url_pdf),
  updated_at = now()
RETURNING resource_id;
"""

DB_ATTEMPT_START = """
INSERT INTO ingest.attempt (resource_id, format, request_url, accept_header, requested_at)
VALUES ($1,$2,$3,$4, now())
RETURNING attempt_id;
"""

DB_ATTEMPT_FINISH = """
UPDATE ingest.attempt
SET finished_at = now(),
    duration_ms = $2,
    http_status = $3,
    response_headers = $4,
    content_type = $5,
    content_length = $6,
    sha256 = $7,
    storage_uri = $8,
    error_type = $9,
    error_detail = $10
WHERE attempt_id = $1;
"""

DB_UPDATE_RESOURCE_FORMAT_SQL = {
    "xml": """
UPDATE ingest.resource
SET xml_downloaded = $2,
    xml_downloaded_at = $3,
    xml_http_status = $4,
    xml_sha256 = $5,
    xml_storage_uri = $6,
    xml_error = $7,
    updated_at = now()
WHERE resource_id = $1;
""",
    "json": """
UPDATE ingest.resource
SET json_downloaded = $2,
    json_downloaded_at = $3,
    json_http_status = $4,
    json_sha256 = $5,
    json_storage_uri = $6,
    json_error = $7,
    updated_at = now()
WHERE resource_id = $1;
""",
    "pdf": """
UPDATE ingest.resource
SET pdf_downloaded = $2,
    pdf_downloaded_at = $3,
    pdf_http_status = $4,
    pdf_sha256 = $5,
    pdf_storage_uri = $6,
    pdf_error = $7,
    updated_at = now()
WHERE resource_id = $1;
""",
}

DB_UPDATE_RESOURCE_FORMAT_304_SQL = {
    "xml": """
UPDATE ingest.resource
SET xml_downloaded = $2,
    xml_downloaded_at = $3,
    xml_http_status = $4,
    updated_at = now()
WHERE resource_id = $1;
""",
    "json": """
UPDATE ingest.resource
SET json_downloaded = $2,
    json_downloaded_at = $3,
    json_http_status = $4,
    updated_at = now()
WHERE resource_id = $1;
""",
    "pdf": """
UPDATE ingest.resource
SET pdf_downloaded = $2,
    pdf_downloaded_at = $3,
    pdf_http_status = $4,
    updated_at = now()
WHERE resource_id = $1;
""",
}

DB_GET_RESOURCE_FORMAT_SQL = {
    "xml": """
SELECT xml_downloaded AS downloaded,
       xml_sha256 AS sha256,
       xml_storage_uri AS storage_uri
FROM ingest.resource
WHERE resource_id = $1;
""",
    "json": """
SELECT json_downloaded AS downloaded,
       json_sha256 AS sha256,
       json_storage_uri AS storage_uri
FROM ingest.resource
WHERE resource_id = $1;
""",
    "pdf": """
SELECT pdf_downloaded AS downloaded,
       pdf_sha256 AS sha256,
       pdf_storage_uri AS storage_uri
FROM ingest.resource
WHERE resource_id = $1;
""",
}


def db_update_resource_format_sql(fmt: str) -> str:
    if fmt not in DB_UPDATE_RESOURCE_FORMAT_SQL:
        raise ValueError(f"Formato invalido: {fmt}")
    return DB_UPDATE_RESOURCE_FORMAT_SQL[fmt]


def db_update_resource_format_304_sql(fmt: str) -> str:
    if fmt not in DB_UPDATE_RESOURCE_FORMAT_304_SQL:
        raise ValueError(f"Formato invalido: {fmt}")
    return DB_UPDATE_RESOURCE_FORMAT_304_SQL[fmt]


def db_get_resource_format_sql(fmt: str) -> str:
    if fmt not in DB_GET_RESOURCE_FORMAT_SQL:
        raise ValueError(f"Formato invalido: {fmt}")
    return DB_GET_RESOURCE_FORMAT_SQL[fmt]


@dataclass
class DbCtx:
    pool: Any

    async def upsert_resource(
        self,
        source_kind: str,
        resource_key: str,
        url_xml: Optional[str],
        url_json: Optional[str],
        url_pdf: Optional[str],
    ) -> str:
        async with self.pool.acquire() as con:
            return await con.fetchval(
                DB_UPSERT_RESOURCE,
                source_kind,
                resource_key,
                url_xml,
                url_json,
                url_pdf,
            )

    async def attempt_start(
        self,
        resource_id: str,
        fmt: str,
        request_url: str,
        accept: Optional[str],
    ) -> str:
        async with self.pool.acquire() as con:
            return await con.fetchval(
                DB_ATTEMPT_START, resource_id, fmt, request_url, accept
            )

    async def attempt_finish(
        self,
        attempt_id: str,
        duration_ms: int,
        http_status: Optional[int],
        headers: Dict[str, str],
        content_type: Optional[str],
        content_length: Optional[int],
        sha256: Optional[str],
        storage_uri: Optional[str],
        error_type: Optional[str],
        error_detail: Optional[str],
    ) -> None:
        async with self.pool.acquire() as con:
            await con.execute(
                DB_ATTEMPT_FINISH,
                attempt_id,
                duration_ms,
                http_status,
                json.dumps(headers or {}, ensure_ascii=False),
                content_type,
                content_length,
                sha256,
                storage_uri,
                error_type,
                error_detail,
            )

    async def update_resource_format(
        self,
        resource_id: str,
        fmt: str,
        ok: bool,
        downloaded_at: Optional[datetime],
        http_status: Optional[int],
        sha256: Optional[str],
        storage_uri: Optional[str],
        error: Optional[str],
    ) -> None:
        q = db_update_resource_format_sql(fmt)
        async with self.pool.acquire() as con:
            await con.execute(
                q,
                resource_id,
                ok,
                downloaded_at,
                http_status,
                sha256,
                storage_uri,
                error,
            )

    async def update_resource_format_not_modified(
        self,
        resource_id: str,
        fmt: str,
        ok: bool,
        downloaded_at: Optional[datetime],
        http_status: Optional[int],
    ) -> None:
        q = db_update_resource_format_304_sql(fmt)
        async with self.pool.acquire() as con:
            await con.execute(
                q,
                resource_id,
                ok,
                downloaded_at,
                http_status,
            )

    async def get_resource_format_status(
        self, resource_id: str, fmt: str
    ) -> tuple[bool, Optional[str], Optional[str]]:
        q = db_get_resource_format_sql(fmt)
        async with self.pool.acquire() as con:
            row = await con.fetchrow(q, resource_id)
        if not row:
            return False, None, None
        return bool(row.get("downloaded")), row.get("sha256"), row.get("storage_uri")
