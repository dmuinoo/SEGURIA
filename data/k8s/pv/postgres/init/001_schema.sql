BEGIN;

-- 0) Prerrequisitos
CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- gen_random_uuid()

CREATE SCHEMA IF NOT EXISTS boe;
CREATE SCHEMA IF NOT EXISTS ingest;

-- Opcional (en init de Docker suele sobrar, pero no molesta)
ALTER SCHEMA boe OWNER TO CURRENT_USER;
ALTER SCHEMA ingest OWNER TO CURRENT_USER;

SET search_path TO boe, public;

------------------------------------------------------------
-- BOE · DOCUMENTO BASE
------------------------------------------------------------

CREATE TABLE IF NOT EXISTS boe.document (
  document_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Identidad
  boe_id TEXT NOT NULL UNIQUE,             -- <identificador>
  url_eli TEXT,
  url_html_consolidada TEXT,

  -- Huella y payload
  xml_sha256 CHAR(64) NOT NULL UNIQUE,
  xml_storage_uri TEXT NOT NULL,
  content_type TEXT,

  -- Metadatos principales
  fecha_actualizacion_utc TIMESTAMPTZ,
  ambito_codigo TEXT,
  ambito_texto TEXT,
  departamento_codigo TEXT,
  departamento_texto TEXT,
  rango_codigo TEXT,
  rango_texto TEXT,
  fecha_disposicion DATE,
  numero_oficial TEXT,
  titulo TEXT,
  diario TEXT,
  fecha_publicacion DATE,
  diario_numero TEXT,
  fecha_vigencia DATE,
  estatus_derogacion TEXT,
  estatus_anulacion TEXT,
  vigencia_agotada TEXT,
  estado_consolidacion_codigo TEXT,
  estado_consolidacion_texto TEXT,

  -- Lossless
  metadatos_raw JSONB,
  analisis_raw JSONB,
  metadata_eli_raw XML,
  texto_raw XML,
  xml_raw XML,

  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_boe_document_url_eli
  ON boe.document(url_eli);

CREATE INDEX IF NOT EXISTS idx_boe_document_fecha_pub
  ON boe.document(fecha_publicacion);

------------------------------------------------------------
-- BOE · MATERIAS
------------------------------------------------------------

CREATE TABLE IF NOT EXISTS boe.materia (
  materia_codigo TEXT PRIMARY KEY,
  materia_texto TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS boe.document_materia (
  document_id UUID NOT NULL REFERENCES boe.document(document_id) ON DELETE CASCADE,
  materia_codigo TEXT NOT NULL REFERENCES boe.materia(materia_codigo) ON DELETE RESTRICT,
  PRIMARY KEY (document_id, materia_codigo)
);

------------------------------------------------------------
-- BOE · NOTAS
------------------------------------------------------------

CREATE TABLE IF NOT EXISTS boe.document_nota (
  nota_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID NOT NULL REFERENCES boe.document(document_id) ON DELETE CASCADE,
  ordinal INTEGER NOT NULL,
  nota_texto TEXT NOT NULL,
  UNIQUE (document_id, ordinal)
);

------------------------------------------------------------
-- BOE · REFERENCIAS NORMATIVAS
------------------------------------------------------------

CREATE TABLE IF NOT EXISTS boe.relacion_tipo (
  relacion_codigo TEXT PRIMARY KEY,
  relacion_texto TEXT
);

CREATE TABLE IF NOT EXISTS boe.document_referencia (
  ref_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID NOT NULL REFERENCES boe.document(document_id) ON DELETE CASCADE,

  direccion TEXT NOT NULL CHECK (direccion IN ('anterior','posterior')),
  ordinal INTEGER NOT NULL,

  id_norma TEXT,
  relacion_codigo TEXT,
  relacion_texto TEXT,
  texto TEXT,

  UNIQUE (document_id, direccion, ordinal),

  CONSTRAINT fk_relacion_tipo
    FOREIGN KEY (relacion_codigo)
    REFERENCES boe.relacion_tipo(relacion_codigo)
    ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_doc_ref_doc
  ON boe.document_referencia(document_id);

CREATE INDEX IF NOT EXISTS idx_doc_ref_id_norma
  ON boe.document_referencia(id_norma);

------------------------------------------------------------
-- BOE · TEXTO ESTRUCTURADO
------------------------------------------------------------

CREATE TABLE IF NOT EXISTS boe.text_block (
  block_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID NOT NULL REFERENCES boe.document(document_id) ON DELETE CASCADE,

  block_key TEXT NOT NULL,
  block_tipo TEXT NOT NULL,
  block_titulo TEXT,

  parent_block_id UUID REFERENCES boe.text_block(block_id) ON DELETE SET NULL,
  ordinal INTEGER NOT NULL,

  attrs JSONB,

  UNIQUE (document_id, block_key)
);

CREATE INDEX IF NOT EXISTS idx_text_block_doc_parent_ord
  ON boe.text_block(document_id, parent_block_id, ordinal);

CREATE TABLE IF NOT EXISTS boe.text_block_version (
  version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  block_id UUID NOT NULL REFERENCES boe.text_block(block_id) ON DELETE CASCADE,

  id_norma TEXT NOT NULL,
  fecha_publicacion DATE,
  fecha_vigencia DATE,
  vigencia_desde DATE,
  vigencia_hasta DATE,

  attrs JSONB,

  UNIQUE (block_id, id_norma, fecha_publicacion, fecha_vigencia)
);

CREATE INDEX IF NOT EXISTS idx_block_version_vigencia
  ON boe.text_block_version(vigencia_desde, vigencia_hasta);

CREATE TABLE IF NOT EXISTS boe.text_unit (
  unit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  version_id UUID NOT NULL REFERENCES boe.text_block_version(version_id) ON DELETE CASCADE,

  ordinal INTEGER NOT NULL,
  p_class TEXT,
  text TEXT NOT NULL,
  text_raw XML,
  attrs JSONB,

  UNIQUE (version_id, ordinal)
);

------------------------------------------------------------
-- INGEST · RECURSOS
------------------------------------------------------------

CREATE TABLE IF NOT EXISTS ingest.resource (
  resource_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  source_kind TEXT NOT NULL,
  resource_key TEXT NOT NULL,

  url_xml TEXT,
  url_json TEXT,
  url_pdf TEXT,

  xml_downloaded BOOLEAN NOT NULL DEFAULT FALSE,
  xml_downloaded_at TIMESTAMPTZ,
  xml_http_status INTEGER,
  xml_sha256 CHAR(64),
  xml_storage_uri TEXT,
  xml_error TEXT,

  json_downloaded BOOLEAN NOT NULL DEFAULT FALSE,
  json_downloaded_at TIMESTAMPTZ,
  json_http_status INTEGER,
  json_sha256 CHAR(64),
  json_storage_uri TEXT,
  json_error TEXT,

  pdf_downloaded BOOLEAN NOT NULL DEFAULT FALSE,
  pdf_downloaded_at TIMESTAMPTZ,
  pdf_http_status INTEGER,
  pdf_sha256 CHAR(64),
  pdf_storage_uri TEXT,
  pdf_error TEXT,

  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  UNIQUE (source_kind, resource_key)
);

------------------------------------------------------------
-- INGEST · HISTÓRICO DE INTENTOS
------------------------------------------------------------

CREATE TABLE IF NOT EXISTS ingest.attempt (
  attempt_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  resource_id UUID NOT NULL REFERENCES ingest.resource(resource_id) ON DELETE CASCADE,

  format TEXT NOT NULL CHECK (format IN ('xml','json','pdf')),
  request_url TEXT NOT NULL,
  accept_header TEXT,

  requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  duration_ms INTEGER,

  http_status INTEGER,
  response_headers JSONB,
  content_type TEXT,
  content_length BIGINT,

  sha256 CHAR(64),
  storage_uri TEXT,

  error_type TEXT,
  error_detail TEXT
);

CREATE INDEX IF NOT EXISTS idx_attempt_resource_time
  ON ingest.attempt(resource_id, requested_at DESC);

CREATE INDEX IF NOT EXISTS idx_attempt_status
  ON ingest.attempt(http_status);

COMMIT;

