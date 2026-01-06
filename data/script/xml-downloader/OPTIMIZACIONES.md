# Análisis de Optimizaciones para xml-domloader.py

## 🔍 Optimizaciones Identificadas

### 1. **Paralelización de Embeddings (CRÍTICO - Alto Impacto)**

**Problema**: En `qdrant_upsert_document()` (líneas 499-518), los embeddings se procesan secuencialmente. Esto es muy lento cuando hay muchas unidades.

**Impacto**: Si un documento tiene 50 unidades, y cada embedding tarda 100ms, el total es 5 segundos. Con paralelización (p.ej. 10 concurrentes), sería ~500ms.

**Solución**: Usar `asyncio.gather()` para procesar embeddings en paralelo con un semáforo para limitar concurrencia.

```python
# En lugar de:
for u in doc.units[1:]:
    vec = await embedder.embed(u["text"])
    # ...

# Usar:
async def embed_unit(u):
    vec = await embedder.embed(u["text"])
    return u, vec

# Con semáforo para limitar concurrencia de embeddings
embed_sem = asyncio.Semaphore(10)  # Ajustar según recursos
tasks = [embed_unit(u) for u in doc.units[1:]]
results = await asyncio.gather(*tasks)
```

---

### 2. **Batching de Operaciones Neo4j (ALTO IMPACTO)**

**Problema**: En `neo4j_upsert_document()` (líneas 568-588), cada unidad se inserta con una query separada. Esto genera mucha latencia de red.

**Impacto**: 50 unidades = 50 queries = ~2-5 segundos (dependiendo de latencia). Con batching = 1 query = ~50-100ms.

**Solución**: Usar UNWIND de Cypher para insertar múltiples unidades en una sola query:

```python
# En lugar de:
for u in doc.units:
    await s.run("MERGE...", {...})

# Usar:
units_data = [{"key": f"{doc.doc_id}::{u['unit_id']}", ...} for u in doc.units]
await s.run("""
    MATCH (d:Document {doc_id: $doc_id})
    UNWIND $units AS unit
    MERGE (u:Unit {key: unit.key})
    SET u.unit_id = unit.unit_id, ...
    MERGE (d)-[:CONTAINS]->(u)
""", {"doc_id": doc.doc_id, "units": units_data})
```

---

### 3. **Optimización de XPath con translate() (MEDIO IMPACTO)**

**Problema**: Las expresiones XPath usan `translate()` repetidamente, lo cual es costoso. Además, se construyen strings XPath largos en cada llamada.

**Impacto**: En documentos grandes con muchas unidades, las queries XPath se ejecutan muchas veces.

**Solución**: 
- Pre-compilar namespaces normalizados
- Cachear expresiones XPath comunes
- Usar funciones auxiliares para normalizar nombres una vez

```python
# Cachear expresiones comunes
_NORMALIZE_NS = str.maketrans('ÁÉÍÓÚÜÑ', 'AEIOUUN')
def normalize_tag(tag: str) -> str:
    return tag.translate(_NORMALIZE_NS)

# Pre-compilar XPath cuando sea posible
```

---

### 4. **Hash Calculations Repetidas (BAJO-MEDIO IMPACTO)**

**Problema**: Se calculan hashes SHA1/SHA256 múltiples veces para el mismo contenido (p.ej. en `normalize_doc_id` y en `qdrant_upsert_document`).

**Solución**: Cachear hashes calculados o calcular una vez y reutilizar.

---

### 5. **File I/O Síncrono en Contexto Async (MEDIO IMPACTO)**

**Problema**: `load_meta()`, `save_meta()`, `save_xml()` usan I/O síncrono dentro de funciones async. Esto bloquea el event loop.

**Impacto**: Con alta concurrencia, puede crear cuellos de botella.

**Solución**: Usar `aiofiles` para I/O asíncrono:

```python
import aiofiles
import aiofiles.os

async def load_meta(doc_id: str) -> StoredMeta:
    mp = meta_path(doc_id)
    if not await aiofiles.os.path.exists(mp):
        return StoredMeta()
    async with aiofiles.open(mp, "r", encoding="utf-8") as f:
        content = await f.read()
        d = json.loads(content)
        return StoredMeta(...)
```

---

### 6. **Memory Usage para XML Grandes (BAJO IMPACTO - Solo si hay archivos >100MB)**

**Problema**: XML completo se carga en memoria (`await r.read()`). Para archivos muy grandes (>100MB), esto puede ser problemático.

**Solución**: Streaming parsing solo si es necesario. Para BOE probablemente no hace falta, pero puede considerarse.

---

### 7. **Error Handling Mejorado (CALIDAD DE CÓDIGO)**

**Problema**: Faltan try/except en operaciones críticas (embeddings, Neo4j, Qdrant).

**Solución**: Añadir manejo de errores con logging y retry logic donde sea apropiado.

---

### 8. **Optimización de Construcción de Payloads (BAJO IMPACTO)**

**Problema**: En `qdrant_upsert_document()`, el payload se construye repetidamente con el mismo código para cada unidad.

**Solución**: Función auxiliar para construir payloads:

```python
def _build_unit_payload(doc: ParsedDocument, unit: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "doc_id": doc.doc_id,
        "boe_id": doc.boe_id,
        "eli_uri": doc.eli_uri,
        "title": doc.title,
        "source_url": doc.source_url,
        "unit_id": unit["unit_id"],
        "label": unit["label"],
        "path": unit["path"],
        "text": unit["text"],
        **{k: v for k, v in doc.dates.items() if v},
    }
```

---

### 9. **Connection Pooling y Reutilización (BAJO IMPACTO)**

**Problema**: El driver de Neo4j se cierra y abre. Con múltiples ejecuciones, podría mantenerse abierto.

**Solución**: Ya está bien manejado, pero podría considerarse un contexto manager global si hay múltiples ejecuciones.

---

### 10. **Pre-computación de Paths XML (MUY BAJO IMPACTO)**

**Problema**: `root.getroottree().getpath(el)` se llama para cada unidad. Es relativamente costoso.

**Solución**: Solo llamar si realmente se necesita. Para muchos casos, el unit_id podría ser suficiente.

---

## 📊 Priorización de Implementación

1. **🔴 CRÍTICO**: Paralelización de embeddings (#1)
2. **🟠 ALTO**: Batching de Neo4j (#2)
3. **🟡 MEDIO**: XPath optimization (#3), File I/O async (#5)
4. **🟢 BAJO**: Resto de optimizaciones

## 💡 Estimación de Mejora

Con las optimizaciones #1 y #2 implementadas:
- **Embeddings**: De N×100ms a (N/10)×100ms = **~10x más rápido**
- **Neo4j**: De N×50ms a 1×100ms = **~50x más rápido** (para 50 unidades)
- **Total**: Mejora estimada de **3-5x** en documentos con muchas unidades

