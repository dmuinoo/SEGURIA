NOTICE
======

Proyecto: ia
Versión: 0.1.0
Autor principal: Diego Muiño Orallo
Colaboración: Asistencia técnica mediante Vibecoding
Año: 2025

Este software forma parte del proyecto "ia" y se distribuye conforme a la
Licencia Pública de la Unión Europea, versión 1.2 (EUPL v1.2).
Consulte el fichero LICENSE para el texto legal completo.

===============================================================================
AVISO DE COPYRIGHT
===============================================================================

Copyright (c) 2025
Diego Muiño Orallo

Todos los derechos sobre la autoría original quedan reservados.  
La redistribución con o sin modificaciones debe mantener:

  • Este fichero NOTICE.  
  • El fichero LICENSE con el texto íntegro de la EUPL v1.2.  
  • Las cabeceras de licencia incluidas en cada archivo fuente.  

Toda obra derivada deberá indicar claramente las modificaciones y su fecha
(tal y como exige la EUPL, Art. 5).

===============================================================================
COMPONENTES DE TERCEROS — DEPENDENCIAS PRINCIPALES (pyproject.toml)
===============================================================================

El proyecto "ia" utiliza dependencias de terceros que se distribuyen bajo sus
propias licencias. A continuación se listan las dependencias principales, su
propósito general y su licencia cuando esta es conocida públicamente.

Estas dependencias están claramente declaradas en `pyproject.toml`:

  • crewai (>=1.7.0) — MIT License  
    Framework para agentes AI.  
    https://github.com/joaompinto/crewai

  • crewai-tools (>=1.7.0) — MIT License  
    Herramientas auxiliares para agentes CrewAI.

  • fastembed (>=0.7.4) — Apache-2.0  
    Embeddings ultrarrápidos.  
    https://github.com/qdrant/fastembed

  • gradio (>=6.1.0) — Apache-2.0  
    Interfaz web interactiva para aplicaciones ML.  
    https://github.com/gradio-app/gradio

  • guardrails-ai (>=0.7.1) — Apache-2.0  
    Validación y control de resultados LLM.  
    https://github.com/guardrails-ai/guardrails

  • opentelemetry-exporter-otlp-proto-http (>=1.34.1) — Apache-2.0  
  • opentelemetry-instrumentation (>=0.55b1) — Apache-2.0  
  • opentelemetry-instrumentation-requests (>=0.55b1) — Apache-2.0  
    Telemetría y observabilidad estándar.  
    https://opentelemetry.io/

  • presidio-anonymizer (>=2.2.360) — MIT License  
    Anonimización de datos sensibles.  
    https://github.com/microsoft/presidio

  • pydantic (>=2.11.10) — MIT License  
  • pydantic-settings (>=2.10.1) — MIT License  
    Validación de datos y configuración tipada.

  • python-dotenv (>=1.1.1) — BSD 3-Clause  
    Gestión de variables de entorno.

  • regex (>=2024.9.11) — Multilicencia BSD / Python License  
    Motor regex avanzado.

  • semgrep (>=1.79.0) — LGPL-2.1 / GPL-Compatible  
    Análisis estático de seguridad.  
    https://github.com/semgrep/semgrep

  • tokenizers (>=0.20.3) — Apache-2.0  
    Tokenización acelerada.  
    https://github.com/huggingface/tokenizers

  • tomli-w (<1.2) — MIT License  
    Escritura de toml.

Estas bibliotecas deben respetarse conforme a sus licencias individuales.

===============================================================================
DEPENDENCIAS COMPLETAS — requirements.lock.txt
===============================================================================

El fichero `requirements.lock.txt` contiene la lista exhaustiva de dependencias
(y versiones exactas) necesarias para reproducir el entorno del proyecto.
Estas dependen a su vez de múltiples licencias open-source, entre ellas:

  • MIT  
  • Apache-2.0  
  • BSD (2-clause, 3-clause o variantes modificadas)  
  • LGPL / GPL (licencias compatibles según la EUPL Art. 5)  
  • Licencias específicas para componentes científicos o de IA  

El usuario que redistribuya este proyecto es responsable de cumplir con cada
una de las licencias incluidas en dichos paquetes, así como de proporcionar
los avisos de copyright y LICENSE de terceros cuando la licencia así lo exija.

Se recomienda revisar individualmente los paquetes más relevantes, por ejemplo:

  • aiohttp, fastapi, uvicorn, httpx, pandas, numpy, spacy, langchain,
    langgraph, chromadb, posthog, sqlalchemy, openai, onnxruntime, etc.

Cada uno se rige por su propia licencia de software libre.

===============================================================================
DESCARGO DE RESPONSABILIDAD
===============================================================================

Este software se proporciona “TAL CUAL”, sin garantías explícitas o implícitas,
incluyendo sin limitación las garantías de comerciabilidad, adecuación a un
propósito particular o no infracción.

El autor no será responsable de daños directos o indirectos derivados del uso
de este software.

===============================================================================
CONTACTO
===============================================================================

Para consultas sobre licencia, autoría o redistribución:

    Diego Muiño Orallo

