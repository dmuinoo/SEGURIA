# POC IA + Research RAG (BOE)

Esta carpeta contiene una **POC de una IA con research RAG** que devolvera una respuesta basada en documentos del BOE y una URL a los documentos originales. Por ahora solo se ha desarrollado el script de descarga y su runner de tests, pero el stack objetivo esta definido y se describe mas abajo.

> [!NOTE]
> Normativa aplicable: ver [NORMATIVA.md](data/normativa/NORMATIVA.md).  
> Directrices de la IA Act y de las 16 guias de la AESIA.

## Stack previsto (vision general)

- **Scripts de descarga** (implementados):
  - [`boe_downloader_eli.py`](data/script/xml-downloader/boe_downloader_eli.py): CLI y orquestacion general (argumentos, flujo, panel web).
  - [`boe_downloader_http.py`](data/script/xml-downloader/boe_downloader_http.py): descargas HTTP con cache condicional y metadata.
  - [`boe_downloader_pipeline.py`](data/script/xml-downloader/boe_downloader_pipeline.py): cola de descargas, Rich UI, escrituras y metricas.
  - [`boe_downloader_parsing.py`](data/script/xml-downloader/boe_downloader_parsing.py): parsing del sumario XML y extraccion de URLs.
  - [`boe_downloader_db.py`](data/script/xml-downloader/boe_downloader_db.py): escritura en `ingest.resource` e `ingest.attempt`.
  - [`boe_downloader_web.py`](data/script/xml-downloader/boe_downloader_web.py): panel web FastAPI (estado en vivo).
- **Postgres**: registra estado de ingesta, reintentos, hashes, ubicaciones de almacenamiento y metadatos.
- **Script de introduccion a Parquet con Polars** (pendiente): transforma lo descargado y lo deja listo para reindexacion.
- **Script de embeddings y chunking** (pendiente): genera embeddings y carga en Qdrant (vectorial) y Neo4j (grafo).
- **RAG** (pendiente): motor de recuperacion y respuesta para maximizar exactitud y velocidad.
- **Guardrails y seguridad** (pendiente): validacion, trazabilidad y medidas de seguridad para la POC.
- **LLM local** (pendiente): uso de modelos via Ollama para la POC.

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

## Documentacion adicional

Enlaces a documentacion del proyecto:

- [README.md](data/normativa/README.md)
- [ABOUT.md](data/normativa/ABOUT.md)
- [INSTALACION.md](data/normativa/INSTALACION.md)
- [LICENSE.md](data/normativa/LICENSE.md)
- [NOTICE.md](data/normativa/NOTICE.md)
- [OPTIMIZACIONES.md](data/normativa/OPTIMIZACIONES.md)

## Script principal: boe_downloader_eli.py

Ruta:

- [data/script/xml-downloader/boe_downloader_eli.py](data/script/xml-downloader/boe_downloader_eli.py)

### Que hace

- Descarga documentos del BOE por fecha (sumario) y por BOE-A (consolidada).
- Usa el sumario XML de una fecha para extraer URLs de cada BOE publicado ese dia.
- Descarga XML/PDF segun los formatos indicados.
- Guarda payloads con sha256 en disco y registra el estado en Postgres (`ingest.resource`, `ingest.attempt`).
- Muestra metricas en vivo con Rich (CLI) y un panel web **FastAPI** (progreso, errores, bytes, etc.).

### Panel web (FastAPI)

El script puede levantar un panel web local con graficos y metricas en tiempo real:

- URL por defecto: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- Se mantiene activo mientras el proceso esta en ejecucion.
- Si el puerto esta ocupado, el script aborta antes de iniciar descargas y muestra un aviso.
- Si `fastapi` o `uvicorn` no estan instalados, se muestra un aviso y se desactiva el panel web.
- Con `--open-web` se abre automaticamente en el navegador del **equipo donde se ejecuta el script**.
- Con `--web-port` puedes elegir otro puerto (default 8000).

Vista rapida del panel:

![Panel FastAPI](docs/boe-dashboard.svg)

> [!NOTE]
> El panel web se sirve en el mismo host donde se ejecuta el script. En un servidor remoto no abrira el navegador local automaticamente.

#### Tunel SSH (cuando ejecutas en remoto)

Si ejecutas el script en un servidor remoto, usa un tunel SSH para abrir el panel desde tu equipo:

```bash
ssh -L 8000:127.0.0.1:8000 usuario@servidor
```

Luego abre en tu navegador local:
[http://127.0.0.1:8000](http://127.0.0.1:8000)

Diagrama rapido (FastAPI + tunel SSH):

```
┌───────────────────────┐            ┌──────────────────────────┐
│       SERVIDOR         │            │         TU EQUIPO        │
│  boe_downloader_eli.py  │            │   Navegador web local     │
│  FastAPI :8000          │            │   http://127.0.0.1:8000   │
└───────────┬────────────┘            └───────────┬──────────────┘
            │  Tunel SSH (port forward)           │
            └──────────────┬──────────────────────┘
                           │
       ssh -L 8000:127.0.0.1:8000 usuario@servidor
```

### Componentes principales (resumen)

- `boe_downloader_eli.py`: CLI, orquestacion, validacion de argumentos y arranque del panel web.
- `boe_downloader_http.py`: descargas HTTP con cache condicional y metadata.
- `boe_downloader_pipeline.py`: cola de descargas, Rich UI, escrituras de payloads y metricas.
- `boe_downloader_parsing.py`: parsing de sumario XML y extraccion de URLs.
- `boe_downloader_db.py`: persistencia en `ingest.resource` e `ingest.attempt`.
- `boe_downloader_web.py`: panel web FastAPI (estado en vivo y diseno del dashboard).

### Uso basico

Global:

```bash
# ayuda
python3 data/script/xml-downloader/boe_downloader_eli.py --help
```

Modo sumario:

```bash
# XML del sumario por fecha
python3 data/script/xml-downloader/boe_downloader_eli.py   --formats xml   --no-db   sumario --fecha AAAAMMDD
```

Modo consolidada:

```bash
# Consolidadas por fecha (extrae URLs del sumario XML)
python3 data/script/xml-downloader/boe_downloader_eli.py   --formats xml,pdf   --db-dsn postgresql://USER:PASS@localhost:PORT/DB   consolidada --fecha AAAAMMDD
```

> [!WARNING]
> En consolidada, **JSON esta desactivado** porque los endpoints consultados devuelven XML aunque se pida `Accept: application/json`.

> [!IMPORTANT]
> Los argumentos globales (`--formats`, `--db-dsn`, `--store`, etc.) deben ir **antes** del subcomando (`sumario` o `consolidada`).  
> Si se pasan despues, el parser los interpreta como argumentos del subcomando y devuelve error.

Notas:

- El almacenamiento por defecto es `./boe_store` (relativo al directorio de ejecucion).

> [!TIP]
> Para pruebas rapidas sin BD usa `--no-db` y una fecha concreta con `consolidada --fecha`.
> Para ver un dashboard con los datos de las descargas `--open-web`.

### Argumentos principales

Globales:

- `--store`: carpeta base de almacenamiento (default `./boe_store`).
- `--timeout`: timeout total por request (segundos).
- `--retries`: reintentos para 429/5xx/errores transitorios.
- `--concurrency`: concurrencia fija o `auto`.
- `--concurrency-start`: concurrencia inicial en modo auto.
- `--concurrency-max`: techo de concurrencia en modo auto.
- `--formats`: `xml,json,pdf` (coma-separado).
- `--db-dsn`: DSN Postgres para registrar en BD.
- `--no-db`: desactiva escritura en BD.
- `--progress`: muestra barra de progreso Rich (default activo).
- `--no-progress`: desactiva la barra Rich.
- `--ui-refresh`: refresco de la UI Rich (veces/seg).
- `--debug-http`: solo imprime HTTP con status != 200.
- `--debug-http-all`: imprime todo el trafico HTTP (mas lento).
- `--debug`: alias de `--debug-http`.
- `--no-cache`: desactiva cache condicional (sin `If-None-Match`).
- `--cpu-high`: umbral de CPU para bajar concurrencia en modo auto.
- `--cpu-low`: umbral de CPU para subir concurrencia en modo auto.
- `--jitter`: tipo de jitter para backoff (`decorrelated` o `full`).
- `--base-delay`: delay base para backoff.
- `--cap-delay`: delay maximo para backoff.
- `--open-web`: abre el panel web en el navegador local si es posible.
- `--web-host`: host del panel web (default `127.0.0.1`).
- `--web-port`: puerto del panel web (default `8000`).

Subcomando `sumario`:

- `--fecha` (AAAAMMDD) **obligatorio**.
- `--manifest` para el JSONL de indices.

Subcomando `consolidada`:

- `--fecha` (DD-MM-AAAA o AAAAMMDD) para obtener IDs desde el sumario.
- `--since-from` / `--since-to` para rango de fechas (AAAAMMDD).
- `--eli-list` archivo con una ELI por linea.
- `--part` y `--accept` para controlar la parte del documento y el Accept header.

## Script de tests

Ruta:

- [data/script/xml-downloader/test_boe_downloader_eli.py](data/script/xml-downloader/test_boe_downloader_eli.py)

### Que hace

- Ejecuta pytest, coverage, ruff, mypy, pylint, bandit y black.
- Tiene tests unitarios locales (sin red por defecto).
- Herramientas pesadas (mutmut, locust) se ejecutan solo con `RUN_HEAVY=1`.

### Uso

```bash
# usar el entorno del proyecto con grupo de tests
uv run --group test python3 data/script/xml-downloader/test_boe_downloader_eli.py

# ejecutar herramientas pesadas
RUN_HEAVY=1 uv run --group test python3 data/script/xml-downloader/test_boe_downloader_eli.py
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
- `xml_downloaded`, `xml_downloaded_at`, `xml_http_status`, `xml_sha256`, `xml_storage_uri`, `xml_error`: estado del ultimo intento XML.
- `json_downloaded`, `json_downloaded_at`, `json_http_status`, `json_sha256`, `json_storage_uri`, `json_error`: estado del ultimo intento JSON.
- `pdf_downloaded`, `pdf_downloaded_at`, `pdf_http_status`, `pdf_sha256`, `pdf_storage_uri`, `pdf_error`: estado del ultimo intento PDF.
- `created_at`, `updated_at`: control de auditoria.

Tabla `ingest.attempt` (historico de intentos):

- `attempt_id`: UUID del intento.
- `resource_id`: referencia al recurso.
- `format`: formato (`xml`, `json`, `pdf`).
- `request_url`: URL solicitada.
- `accept_header`: valor del header Accept.
- `requested_at`, `finished_at`, `duration_ms`: tiempos de ejecucion.
- `http_status`, `response_headers`, `content_type`, `content_length`: respuesta HTTP.
- `sha256`, `storage_uri`: huella y ruta del payload guardado.
- `error_type`, `error_detail`: error si fallo.

### Consultas utiles

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
- `xml_sha256`, `xml_storage_uri`, `content_type`: huella y ubicacion del XML.
- `fecha_actualizacion_utc`, `fecha_disposicion`, `fecha_publicacion`, `fecha_vigencia`: fechas clave.
- `ambito_*`, `departamento_*`, `rango_*`: codigos y textos de metadatos.
- `numero_oficial`, `titulo`, `diario`, `diario_numero`: metadatos principales.
- `estatus_derogacion`, `estatus_anulacion`, `vigencia_agotada`, `estado_consolidacion_*`: estado normativo.
- `metadatos_raw`, `analisis_raw`, `metadata_eli_raw`, `texto_raw`, `xml_raw`: payloads completos.
- `created_at`: auditoria.

Tabla `boe.materia`: catalogo de materias (codigo y texto).
Tabla `boe.document_materia`: relacion documento-materia.
Tabla `boe.document_nota`: notas numeradas del documento.
Tabla `boe.relacion_tipo`: tipos de relacion normativa.
Tabla `boe.document_referencia`: referencias anteriores/posteriores con texto y relacion.
Tabla `boe.text_block`: bloques del texto estructurado.
Tabla `boe.text_block_version`: versiones de cada bloque (vigencia).
Tabla `boe.text_unit`: unidades de texto (parrafos) por version.

## Scripts futuros (pendientes)

- **Carga a Parquet con Polars**: transformara los datos descargados a Parquet para reindexacion rapida.
- **Embeddings + chunking**: generara embeddings, ingesta en Qdrant (vectorial) y Neo4j (grafo).
- **RAG**: pipeline de recuperacion y respuesta para maxima exactitud y velocidad.
- **Guardrails y seguridad**: validaciones, filtrado y medidas defensivas con agentes IA.
- **LLM local via Ollama**: modelo local para la POC.

## Estructura de almacenamiento en disco (por defecto)

- [boe_store/xml](boe_store/xml/): XML descargados y sus `.meta.json`.
- [boe_store/json](boe_store/json/): JSON descargados y sus `.meta.json` (si se activan).
- [boe_store/pdf](boe_store/pdf/): PDFs descargados y sus `.meta.json`.

Cada payload se guarda como `sha256.ext` y su metadata como `sha256.meta.json`.

## Operacion diaria (propuesta)

1. Ejecutar descarga por fecha con `--formats xml,pdf`.
2. Verificar estado en `ingest.resource` y `ingest.attempt`.
3. Convertir a Parquet con el script de Polars (cuando exista).
4. Ejecutar embeddings + chunking y cargar en Qdrant/Neo4j (cuando exista).
5. Ejecutar el RAG y validar respuestas con URLs al BOE.

## Glosario breve

- **RAG**: tecnica que combina recuperacion de documentos y generacion de respuestas.
- **ELI**: identificador europeo de legislacion (European Legislation Identifier).
- **Chunking**: fragmentacion de texto para mejorar la busqueda y el embedding.
- **Embedding**: vector numerico que representa el significado del texto.
- **Qdrant**: base de datos vectorial para busquedas semanticas.
- **Neo4j**: base de datos de grafos para relaciones y dependencias.

## Dependencias (descarga)

- `aiofiles`: E/S de ficheros asincrona para escribir payloads y metadata sin bloquear.
- `aiohttp`: cliente HTTP asincrono para descargar recursos en paralelo.
- `asyncpg`: cliente Postgres asincrono para registrar recursos e intentos.
- `defusedxml`: parser seguro para XML de terceros.
- `fastapi`: servidor web ligero para el dashboard.
- `ijson`: parser JSON en streaming para extraer IDs sin cargar el archivo completo en memoria.
- `lxml`: parser XML/HTML robusto para extraer URLs y procesar documentos.
- `polars`: procesamiento columnar (futuro pipeline a Parquet).
- `psutil`: utilidades del sistema (monitorizacion/diagnostico).
- `psycopg`: driver PostgreSQL adicional (futuras tareas offline/ETL).
- `pygments`: resaltado de texto (util si se usa en salidas enriquecidas).
- `rich`: salida de terminal mejorada (logs/estilos si se activan).
- `ruff`: linter rapido (usado en el runner de tests).
- `uvicorn`: servidor ASGI para levantar FastAPI.

## Dependencias de tests

- `pytest`: framework principal de tests.
- `pytest-asyncio`: soporte para tests async.
- `pytest-cov` y `coverage`: medicion de cobertura.
- `pytest-mock`: utilidades de mocking.
- `hypothesis`: tests basados en propiedades.
- `mypy`: chequeo estatico de tipos.
- `pylint`: analisis de estilo y calidad.
- `bandit`: analisis de seguridad.
- `black`: formateo automatico.
- `mutmut`: testing de mutaciones (solo con `RUN_HEAVY=1`).
- `locust`: pruebas de carga (solo con `RUN_HEAVY=1`).
- `httpx` y `requests`: clientes HTTP para tests.
- `fastapi` y `pydantic`: utilidades de tests y tipado de modelos.
- `testcontainers`: tests con contenedores.
- `lxml-stubs` y `types-*`: stubs de tipos para mejorar mypy.

## Historico de cambios

- 2026-01-10: refactorizacion del codigo y separacion de `boe_downloader_eli.py` en modulos para facilitar el versionado y el mantenimiento.
