# POC IA + Research RAG (BOE)

Esta carpeta contiene una **POC de una IA con research RAG** que devolverá una respuesta basada en documentos del BOE y una URL a los documentos originales. Por ahora solo se ha desarrollado el script de descarga y su runner de tests, pero el stack objetivo está definido y se describe más abajo.

> [!NOTE]
> Normativa aplicable: ver [NORMATIVA.md](data/normativa/NORMATIVA.md).  
> Directrices de la IA Act y de las 16 guías de la AESIA.

## Stack previsto (visión general)

- **Script de descarga** (implementado): obtiene sumarios y documentos del BOE, guarda payloads y registra la ingesta.
- **Postgres**: registra estado de ingesta, reintentos, hashes, ubicaciones de almacenamiento y metadatos.
- **Script de introducción a Parquet con Polars** (pendiente): transforma lo descargado y lo deja listo para reindexación.
- **Script de embeddings y chunking** (pendiente): genera embeddings y carga en Qdrant (vectorial) y Neo4j (grafo).
- **RAG** (pendiente): motor de recuperación y respuesta para maximizar exactitud y velocidad.
- **Guardrails y seguridad** (pendiente): validación, trazabilidad y medidas de seguridad para la POC.
- **LLM local** (pendiente): uso de modelos vía Ollama para la POC.

### Diagrama (alto nivel)

```
SERVIDOR BOE
   |
   v
SCRIPT DE DESCARGA
   |
   v
MinIO / Postgres
   |
   v
SCRIPT INGESTA + EMBEDDING + CHUNKING
   |
   v
QDRANT / NEO4J
   |
   v
RAG (LlamaIndex / LangChain)
   |
   v
AGENTE
   |
   v
LLM (Ollama)
```

## Documentación adicional

Enlaces a archivos del downloader:

- [README.md](data/normativa/README.md)
- [ABOUT.md](data/normativa/ABOUT.md)
- [INSTALACION.md](data/normativa/INSTALACION.md)
- [LICENSE.md](data/normativa/LICENSE.md)
- [NOTICE.md](data/normativa/NOTICE.md)
- [OPTIMIZACIONES.md](data/normativa/OPTIMIZACIONES.md)

## Script principal: boe_downloader_eli.py

Ruta:

- [data/script/xml-downloader/boe_downloader_eli.py](data/script/xml-downloader/boe_downloader_eli.py)

### Qué hace

- Descarga documentos del BOE por fecha (sumario) y por BOE-A (consolidada).
- Usa el sumario de una fecha para extraer URLs de cada BOE publicado ese día.
- Descarga XML/PDF según los formatos indicados.
- Guarda payloads con sha256 en disco y registra el estado en Postgres (`ingest.resource`, `ingest.attempt`).
- Opcionalmente puede parsear XML consolidado y poblar tablas `boe.*` con `--ingest-xml`.
- Levanta un panel web en **FastAPI** para visualizar métricas en vivo (progreso, errores, bytes, etc.).

### Panel web (FastAPI)

El script levanta un panel web local con gráficos y métricas en tiempo real:

- URL fija: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- Se mantiene activo mientras el proceso está en ejecución.
- Si el puerto 8000 está ocupado, el panel web **no** se inicia.
- Si `fastapi` o `uvicorn` no están instalados, se muestra un aviso y se desactiva el panel web.
- Con `--open-web` se abre automáticamente en el navegador del **equipo donde se ejecuta el script**.

Vista rápida del panel:

![Diagrama](docs/boe-dashboard.svg)

> [!NOTE]
> El panel web se sirve en el mismo host donde se ejecuta el script. En un servidor remoto no abrirá el navegador local automáticamente.

#### Túnel SSH (cuando ejecutas en remoto)

Si ejecutas el script en un servidor remoto, usa un túnel SSH para abrir el panel desde tu equipo:

```bash
ssh -L 8000:127.0.0.1:8000 usuario@servidor
```

Luego abre en tu navegador local:
[http://127.0.0.1:8000](http://127.0.0.1:8000)

El script puede imprimir una sugerencia automática de túnel si pasas `--ssh-host`:

```bash
python3 data/script/xml-downloader/boe_downloader_eli.py \
  --ssh-host servidor \
  --ssh-user usuario \
  --formats xml,pdf \
  consolidada --fecha AAAAMMDD
```

> [!TIP]
> Puedes ajustar el puerto del túnel con `--ssh-local-port` y `--ssh-remote-port`.
>
> Para abrir el panel web automáticamente en local, añade `--open-web` (el script usa `open` en macOS, `start` en Windows y `xdg-open` en Linux).

Diagrama rápido (FastAPI + túnel SSH):

```
┌───────────────────────┐            ┌──────────────────────────┐
│       SERVIDOR         │            │         TU EQUIPO        │
│  boe_downloader_eli.py  │            │   Navegador web local     │
│  FastAPI :8000          │            │   http://127.0.0.1:8000   │
└───────────┬────────────┘            └───────────┬──────────────┘
            │  Túnel SSH (port forward)           │
            └──────────────┬──────────────────────┘
                           │
       ssh -L 8000:127.0.0.1:8000 usuario@servidor
```

> [!IMPORTANT]
> Comando de túnel recomendado:
>
> ```bash
> ssh -L 8000:127.0.0.1:8000 usuario@servidor
> ```

Ejemplo con ayuda automática del script:

```bash
python3 data/script/xml-downloader/boe_downloader_eli.py \
  --ssh-host servidor \
  --ssh-user usuario \
  --formats xml,pdf \
  consolidada --fecha AAAAMMDD
```

### Funciones principales (resumen)

- `run_sumario(...)`: descarga el sumario por fecha y guarda JSON/XML/PDF según `--formats`.
- `run_consolidada(...)`: usa el sumario XML para sacar URLs por BOE-A y descarga XML/PDF.
- `download_one_format(...)`: descarga un formato concreto, guarda payloads, escribe metadata y registra en BD.
- `extract_consolidada_urls_from_sumario_xml(...)`: parsea el sumario XML y devuelve IDs + URLs.
- `parse_boe_xml_to_model(...)`: parsea XML consolidado a un modelo estructurado (solo si `--ingest-xml`).

### Uso básico

Global:

```bash
# ayuda
python3 data/script/xml-downloader/boe_downloader_eli.py --help
```

Modo sumario:

```bash
# JSON/XML del sumario por fecha
python3 data/script/xml-downloader/boe_downloader_eli.py \
  --formats xml,json \
  --no-db \
  sumario --fecha AAAAMMDD

# PDF del sumario (requiere URL exacta)
python3 data/script/xml-downloader/boe_downloader_eli.py \
  --formats pdf \
  --no-db \
  sumario --fecha AAAAMMDD --pdf-url https://www.boe.es/boe/dias/AAAA/MM/DD/pdfs/BOE-S-AAAA-NNN.pdf
```

Modo consolidada:

```bash
# Consolidadas por fecha (extrae URLs del sumario XML)
python3 data/script/xml-downloader/boe_downloader_eli.py \
  --formats xml,pdf \
  --db-dsn postgresql://USER:PASS@localhost:PORT/DB \
  consolidada --fecha AAAAMMDD

# Consolidadas por IDs (coma-separado)
python3 data/script/xml-downloader/boe_downloader_eli.py \
  --formats xml \
  --no-db \
  consolidada --ids BOE-A-2025-00001,BOE-A-2025-00002

# Consolidadas por archivo (una ID por línea o JSON array)
python3 data/script/xml-downloader/boe_downloader_eli.py \
  --formats xml \
  --no-db \
  consolidada --ids-file /ruta/ids.txt
```

> [!WARNING]
> En consolidada, **JSON está desactivado** porque los endpoints consultados devuelven XML aunque se pida `Accept: application/json`.

> [!IMPORTANT]
> Los argumentos globales (`--formats`, `--db-dsn`, `--store`, etc.) deben ir **antes** del subcomando (`sumario` o `consolidada`).  
> Si se pasan después, el parser los interpreta como argumentos del subcomando y devuelve error.

Notas:

- Para insertar en `boe.*` se debe usar `--ingest-xml` junto con formato XML.
- El almacenamiento por defecto es `./boe_store` (relativo al directorio de ejecución).

> [!TIP]
> Para pruebas rápidas sin BD usa `--no-db` y limita la descarga a pocos IDs con `consolidada --ids`.

### Argumentos principales

Globales:

- `--store`: carpeta base de almacenamiento (default `./boe_store`).
- `--timeout`: timeout total por request (segundos).
- `--retries`: reintentos para 429/5xx/errores transitorios.
- `--concurrency`: concurrencia fija.
- `--formats`: `xml,json,pdf` (coma-separado).
- `--db-dsn`: DSN Postgres para registrar en BD.
- `--no-db`: desactiva escritura en BD.
- `--ingest-xml`: parsea XML y pobla tablas `boe.*`.
- `--ssh-host`: imprime una sugerencia de túnel SSH para el panel web.
- `--ssh-user`: usuario SSH para el comando sugerido.
- `--ssh-port`: puerto SSH remoto (default 22).
- `--ssh-local-port`: puerto local del túnel (default 8000).
- `--ssh-remote-port`: puerto remoto del panel (default 8000).
- `--open-web`: abre el panel web en el navegador local si es posible.

Subcomando `sumario`:

- `--fecha` (AAAAMMDD) **obligatorio**.
- `--pdf-url` si se quiere descargar PDF del sumario.

Subcomando `consolidada`:

- `--fecha` (AAAAMMDD) para obtener IDs desde el sumario.
- `--ids` lista separada por comas.
- `--ids-file` archivo con IDs (líneas o JSON array).

## Script de tests

Ruta:

- [data/script/xml-downloader/test_boe_downloader_eli.py](data/script/xml-downloader/test_boe_downloader_eli.py)

### Qué hace

- Ejecuta pytest, coverage, ruff, mypy, pylint, bandit y black.
- Tiene tests unitarios locales (sin red por defecto).
- Herramientas pesadas (mutmut, locust) se ejecutan solo con `RUN_HEAVY=1`.

### Uso

```bash
# usar el entorno del proyecto con extra de tests
uv run --extra test python3 data/script/xml-downloader/test_boe_downloader_eli.py

# ejecutar herramientas pesadas
RUN_HEAVY=1 uv run --extra test python3 data/script/xml-downloader/test_boe_downloader_eli.py
```

> [!NOTE]
> El runner reconoce `RUN_HEAVY=1`. Y le pasa las herramientas pesadas como mutmut y locust
> que generan trafico y ven su comportamiento

## Esquema de ingesta en Postgres (ingest.\*)

Tabla `ingest.resource` (snapshot por recurso):

- `resource_id`: UUID del recurso.
- `source_kind`: tipo de fuente (`sumario_dia`, `consolidada_id`, etc.).
- `resource_key`: clave del recurso (fecha o BOE-A).
- `url_xml`, `url_json`, `url_pdf`: URLs conocidas para cada formato.
- `xml_downloaded`, `xml_downloaded_at`, `xml_http_status`, `xml_sha256`, `xml_storage_uri`, `xml_error`: estado del último intento XML.
- `json_downloaded`, `json_downloaded_at`, `json_http_status`, `json_sha256`, `json_storage_uri`, `json_error`: estado del último intento JSON.
- `pdf_downloaded`, `pdf_downloaded_at`, `pdf_http_status`, `pdf_sha256`, `pdf_storage_uri`, `pdf_error`: estado del último intento PDF.
- `created_at`, `updated_at`: control de auditoría.

Tabla `ingest.attempt` (histórico de intentos):

- `attempt_id`: UUID del intento.
- `resource_id`: referencia al recurso.
- `format`: formato (`xml`, `json`, `pdf`).
- `request_url`: URL solicitada.
- `accept_header`: valor del header Accept.
- `requested_at`, `finished_at`, `duration_ms`: tiempos de ejecución.
- `http_status`, `response_headers`, `content_type`, `content_length`: respuesta HTTP.
- `sha256`, `storage_uri`: huella y ruta del payload guardado.
- `error_type`, `error_detail`: error si fallo.

### Consultas útiles

```sql
-- Estado por formato en ingest.resource
SELECT
  COUNT(*) AS total,
  SUM(CASE WHEN xml_downloaded THEN 1 ELSE 0 END) AS xml_ok,
  SUM(CASE WHEN json_downloaded THEN 1 ELSE 0 END) AS json_ok,
  SUM(CASE WHEN pdf_downloaded THEN 1 ELSE 0 END) AS pdf_ok
FROM ingest.resource;

-- Intentos por formato y estado HTTP
SELECT format, http_status, COUNT(*)
FROM ingest.attempt
GROUP BY format, http_status
ORDER BY format, http_status;
```

## Esquema de BOE en Postgres (boe.\*)

Tabla `boe.document` (documento consolidado):

- `document_id`: UUID del documento.
- `boe_id`: identificador BOE-A.
- `url_eli`, `url_html_consolidada`: enlaces a ELI/HTML.
- `xml_sha256`, `xml_storage_uri`, `content_type`: huella y ubicación del XML.
- `fecha_actualizacion_utc`, `fecha_disposicion`, `fecha_publicacion`, `fecha_vigencia`: fechas clave.
- `ambito_*`, `departamento_*`, `rango_*`: códigos y textos de metadatos.
- `numero_oficial`, `titulo`, `diario`, `diario_numero`: metadatos principales.
- `estatus_derogacion`, `estatus_anulacion`, `vigencia_agotada`, `estado_consolidacion_*`: estado normativo.
- `metadatos_raw`, `analisis_raw`, `metadata_eli_raw`, `texto_raw`, `xml_raw`: payloads completos.
- `created_at`: auditoría.

Tabla `boe.materia`: catálogo de materias (código y texto).
Tabla `boe.document_materia`: relación documento-materia.
Tabla `boe.document_nota`: notas numeradas del documento.
Tabla `boe.relacion_tipo`: tipos de relación normativa.
Tabla `boe.document_referencia`: referencias anteriores/posteriores con texto y relación.
Tabla `boe.text_block`: bloques del texto estructurado.
Tabla `boe.text_block_version`: versiones de cada bloque (vigencia).
Tabla `boe.text_unit`: unidades de texto (párrafos) por versión.

## Scripts futuros (pendientes)

- **Carga a Parquet con Polars**: transformará los datos descargados a Parquet para reindexación rápida.
- **Embeddings + chunking**: generará embeddings, ingesta en Qdrant (vectorial) y Neo4j (grafo).
- **RAG**: pipeline de recuperación y respuesta para máxima exactitud y velocidad.
- **Guardrails y seguridad**: validaciones, filtrado y medidas defensivas con agentes IA.
- **LLM local vía Ollama**: modelo local para la POC.

## Estructura de almacenamiento en disco (por defecto)

- [boe_store/xml](boe_store/xml/): XML descargados y sus `.meta.json`.
- [boe_store/json](boe_store/json/): JSON descargados y sus `.meta.json` (si se activan).
- [boe_store/pdf](boe_store/pdf/): PDFs descargados y sus `.meta.json`.

Cada payload se guarda como `sha256.ext` y su metadata como `sha256.meta.json`.

## Operación diaria (propuesta)

1. Ejecutar descarga por fecha con `--formats xml,pdf`.
2. Verificar estado en `ingest.resource` y `ingest.attempt`.
3. Convertir a Parquet con el script de Polars (cuando exista).
4. Ejecutar embeddings + chunking y cargar en Qdrant/Neo4j (cuando exista).
5. Ejecutar el RAG y validar respuestas con URLs al BOE.

## Glosario breve

- **RAG**: técnica que combina recuperación de documentos y generación de respuestas.
- **ELI**: identificador europeo de legislación (European Legislation Identifier).
- **Chunking**: fragmentación de texto para mejorar la búsqueda y el embedding.
- **Embedding**: vector numérico que representa el significado del texto.
- **Qdrant**: base de datos vectorial para búsquedas semánticas.
- **Neo4j**: base de datos de grafos para relaciones y dependencias.

## Dependencias (descarga)

- `aiofiles`: E/S de ficheros asíncrona para escribir payloads y metadata sin bloquear.
- `aiohttp`: cliente HTTP asíncrono para descargar recursos en paralelo.
- `asyncpg`: cliente Postgres asíncrono para registrar recursos e intentos.
- `ijson`: parser JSON en streaming para extraer IDs sin cargar el archivo completo en memoria.
- `lxml`: parser XML/HTML robusto para extraer URLs y procesar documentos.
- `psutil`: utilidades del sistema (monitorización/diagnóstico si se necesitara).
- `pygments`: resaltado de texto (útil si se usa en salidas enriquecidas).
- `rich`: salida de terminal mejorada (logs/estilos si se activan).
- `ruff`: linter rápido (usado en el runner de tests).

## Dependencias de tests

- `pytest`: framework principal de tests.
- `pytest-asyncio`: soporte para tests async.
- `pytest-cov` y `coverage`: medición de cobertura.
- `pytest-mock`: utilidades de mocking.
- `hypothesis`: tests basados en propiedades.
- `mypy`: chequeo estático de tipos.
- `pylint`: análisis de estilo y calidad.
- `bandit`: análisis de seguridad.
- `black`: formateo automático.
- `mutmut`: testing de mutaciones (solo con `RUN_HEAVY=1`).
- `locust`: pruebas de carga (solo con `RUN_HEAVY=1`).
- `httpx` y `requests`: clientes HTTP para tests.
- `fastapi` y `pydantic`: utilidades de tests y tipado de modelos.
- `testcontainers`: tests con contenedores.
- `lxml-stubs` y `types-*`: stubs de tipos para mejorar mypy.
