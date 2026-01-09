# Impacto de las 16 guías de la AESIA en este stack tecnológico y solucion técnica

Cada guía del sandbox regulatorio de la Agencia Española de Supervisión de Inteligencia Artificial (AESIA) está pensada para facilitar el cumplimiento del Reglamento europeo de Inteligencia Artificial (RIA) en sistemas de alto riesgo. A continuación se analizan los puntos clave de cada guía que afectan a un ingeniero de telecomunicaciones y funcionario y se proponen estrategias técnicas para adaptar un stack de IA a los requisitos.

## Guías introductorias

### Guía 01 – Introducción al Reglamento de IA

#### Puntos clave

* Explica que el objetivo del RIA es garantizar que los sistemas de IA sean seguros, respeten la legislación vigente y proporcionen certidumbre jurídica para incentivar la inversión
[aesia.digital.gob.es](https://aesia.digital.gob.es/storage/media/01-guia-introductoria-al-reglamento-de-ia.pdf#:~:text=El%20Reglamento%20de%20Inteligencia%20Artificial,siguiente%20contenido%20o%20alcance%20regulatorio)

* Aclara que el reglamento no se aplica a actividades puramente de investigación y desarrollo, siempre que sus resultados no se pongan en el mercado o en servicio
[aesia.digital.gob.es](https://aesia.digital.gob.es/storage/media/01-guia-introductoria-al-reglamento-de-ia.pdf#:~:text=El%20artículo%202%20del%20Reglamento,actividad%20de%20investigación%2C%20prueba%20o)

#### Impacto en el stack y solución

* Alcance y exclusiones: Antes de planificar un proyecto de IA, verifica si entra dentro del ámbito del RIA. Para proyectos de I+D en telecomunicaciones sin puesta en servicio, se aplican menos obligaciones.
  
* Plan de cumplimiento: Diseña un plan de conformidad que identifique los artículos del RIA aplicables al sistema y asigne responsabilidades (equipo legal, seguridad, desarrollo).
  
### Guía 02 – Guía práctica y ejemplos para entender el Reglamento de IA

#### Puntos clave

* Está dirigida a entidades que quieren comprender el Reglamento y prevé el uso de las guías técnicas. Incluye ejemplos de sistemas de IA de alto riesgo, como un sistema biométrico de control de asistencia
[aesia.digital.gob.es](https://aesia.digital.gob.es/storage/media/02-guia-practica-y-ejemplos-para-entender-el-reglamento-de-ia.pdf#:~:text=En%20el%20cuarto%20apartado%20proporciona,o%20consultar%20las%20guías%20técnicas)

#### Impacto en el stack y solución

* Determinación de riesgo: Evalúa si tu aplicación se encuentra en las categorías de alto riesgo (p. ej., sistemas biométricos de reconocimiento de empleados).
  
* Uso de ejemplos: Utiliza los casos ilustrados para elaborar tus propios análisis de riesgo y documentación. Adaptar los ejemplos de la guía al ámbito de telecomunicaciones (gestión de redes, servicios públicos) facilita el cumplimiento.
  
#### Guías técnicas

### Guía 03 – Evaluación de conformidad

#### Puntos clave

* El RIA establece dos formas de evaluación de conformidad para los sistemas de IA de alto riesgo: control interno (según el Anexo VI del Reglamento) y evaluación por un organismo notificado (Anexo VII). La opción depende del tipo de sistema y del nivel de riesgo
[aesia.digital.gob.es](https://aesia.digital.gob.es/storage/media/03-guia-evaluacion-de-conformidad.pdf#:~:text=puede%20requerir%20la%20intervención%20de,Esta%20clasificación%20se%20analiza)

#### Impacto en el stack y solución

* Elección de procedimiento: Determina si puedes optar por autoevaluación o necesitas un organismo notificado. En sistemas que no impliquen tecnologías de reconocimiento biométrico o infraestructuras críticas, la autoevaluación puede ser suficiente.
  
* Documentación de la conformidad: Implementa un sistema de control de versiones para toda la documentación técnica (código, datos, modelos, evaluaciones) y prepara evidencias de pruebas. Herramientas de MLOps (e.g., MLflow, DVC) facilitan la trazabilidad.
  
### Guía 04 – Sistema de gestión de la calidad

#### Puntos clave

* El artículo 17 del RIA exige un sistema de gestión de la calidad que incluya políticas y procedimientos para garantizar que el sistema cumple la normativa, abarcando estrategias de conformidad, control de diseño y desarrollo, examen y validación, gestión de datos, gestión de riesgos, vigilancia poscomercialización y notificación de incidentes
[aesia.digital.gob.es](https://aesia.digital.gob.es/storage/media/04-guia-del-sistema-de-gestion-de-la-calidad.pdf)

#### Impacto en el stack y solución

* Implementación de un SGC: Establece un marco de calidad basado en normas ISO (p.ej. ISO 42001) con procesos documentados. Integra un sistema de control de cambios que obligue a revisar y aprobar cualquier modificación del modelo o de los datos antes de la puesta en producción.
  
* Herramientas: Utiliza pipelines de CI/CD de IA que incluyan pruebas de rendimiento, de seguridad y validación de datos. Adoptar herramientas de gestión de requisitos (Jira, GitLab Issues) permite rastrear requisitos y evidencias.
  
### Guía 05 – Sistema de gestión de riesgos

#### Puntos clave

* Define el sistema de gestión de riesgos como un conjunto de procesos para identificar, analizar y mitigar riesgos a lo largo de todo el ciclo de vida, con especial atención a los riesgos que afectan a la salud, la seguridad y los derechos fundamentales
[aesia.digital.gob.es](https://aesia.digital.gob.es/storage/media/05-guia-de-gestion-de-riesgos.pdf#:~:text=2,hasta%20su%20comercialización%20y%20poscomercialización)

#### Impacto en el stack y solución

* Identificación de riesgos: Realiza análisis de riesgos antes del desarrollo (p. ej., listas de peligros y análisis de modos de fallo). Para un sistema de IA que gestiona redes de telecomunicaciones, considera fallos que puedan degradar servicios o afectar a infraestructuras críticas.
  
* Herramientas de gestión: Utiliza marcos como ISO 31000 y herramientas de riesgo (p. ej., risk registers en hojas de cálculo o software especializado). Integra los riesgos en el backlog del proyecto y asigna acciones de mitigación.
  
### Guía 06 – Vigilancia (supervisión) humana

#### Puntos clave

* El artículo 14 requiere que los sistemas permitan una supervisión humana efectiva. Los sistemas deben diseñarse para permitir al operador comprender su comportamiento y, si es necesario, intervenir o detenerlo. Deben definirse las responsabilidades de proveedor y despliegue y prever medidas específicas para sistemas biométricos remotos
[aesia.digital.gob.es](https://aesia.digital.gob.es/storage/media/06-guia-vigilancia-humana.pdf#:~:text=El%20artículo%20sobre%20Vigilancia%20humana,a%20la%20identificación%20biométrica%20remota)

#### Impacto en el stack y solución

* Interfaces explicables: Implementa interfaces de usuario que muestren las recomendaciones del modelo y permitan al operador revisar y aprobar las decisiones antes de ejecutarlas. Utiliza técnicas de explicabilidad (SHAP, LIME) para mostrar razones de la decisión.

* Funciones de rescate: Añade mecanismos de parada segura para detener el sistema ante comportamientos anómalos. En un sistema de telecomunicaciones, esto puede ser un mecanismo de rollback automático o de redireccionamiento manual.

* Formación y responsabilidades: Define claramente quién vigila el sistema y proporciona formación sobre los límites y riesgos del modelo.

### Guía 07 – Datos y gobernanza del dato

#### Puntos clave

* Describe la gobernanza de datos como políticas y procedimientos para garantizar que los conjuntos de entrenamiento, validación y prueba son adecuados, representativos y cumplen requisitos de calidad y completitud; la falta de gobernanza puede generar resultados sesgados
[aesia.digital.gob.es](https://aesia.digital.gob.es/storage/media/07-guia-de-datos-y-gobernanza-de-datos.pdf#:~:text=2,derechos%20fundamentales%20de%20los%20usuarios)

#### Impacto en el stack y solución

* Gobernanza de datos: Implementa procesos de catalogación de datos, control de accesos y monitorización de la calidad. Usa catálogos de datos (Data Catalog, Datahub) para documentar origen, variables, licencias y tratamientos.

* Control de sesgos y representatividad: Incorpora etapas de exploración y limpieza que evalúen la representatividad de los datos respecto a la población objetivo. Para un sistema de IA que gestiona solicitudes ciudadanas, asegúrate de que las muestras reflejan la diversidad de usuarios (género, edad, zonas geográficas) sin infringir las leyes de protección de datos.

* Seguridad y privacidad: Utiliza técnicas de anonimización o pseudonimización cuando corresponda y controles de acceso granulares.

### Guía 08 – Transparencia y provisión de información a los usuarios

#### Puntos clave

* El artículo 13 exige que los sistemas de IA de alto riesgo se diseñen para ser transparentes, de modo que los usuarios puedan interpretar y utilizar correctamente las salidas del sistema. Deben ir acompañados de instrucciones con información clara sobre la finalidad prevista, niveles de precisión, robustez y ciberseguridad, y riesgos conocidos
[aesia.digital.gob.es](https://aesia.digital.gob.es/storage/media/08-guia-transparencia.pdf#:~:text=Art,previstas%20en%20la%20sección%203)

#### Impacto en el stack y solución

* Documentación de usuario: Crea manuales y fichas técnicas con el propósito del sistema, limitaciones conocidas, métricas de rendimiento y requisitos de ciberseguridad.

* Interfaces informativas: Asegúrate de que la interfaz muestre al usuario final datos clave como el nivel de confianza en la respuesta y las fuentes de datos utilizadas.

* Gestión de cambios: Mantén un registro de versiones de modelos y comunica actualizaciones significativas a los usuarios.

### Guía 09 – Precisión

#### Puntos clave

* El concepto de precisión se considera un requisito fundamental para mitigar riesgos. La guía conecta los requisitos de precisión con la gestión de riesgos, la calidad de los datos, la documentación, la transparencia, la supervisión humana, la solidez y la ciberseguridad
[aesia.digital.gob.es](https://aesia.digital.gob.es/storage/media/09-guia-de-precision.pdf#:~:text=2,asociados%20al%20sistema%20de%20IA)

#### Impacto en el stack y solución

* Métricas de rendimiento: Define claramente las métricas de precisión relevantes para tu aplicación (accuracy, recall, F1, BER en redes).

* Establece umbrales mínimos en la documentación técnica.

* Monitorización: Implementa monitorización continua para detectar degradación de rendimiento (drift). Utiliza herramientas de MLOps (Prometheus, Grafana, Evidently AI) para supervisar métricas en producción.

* Reentrenamiento: Planifica reentrenamientos regulares y mecanismos de autoaprendizaje con cuidado (garantizando supervisión y control humano). Documenta cada reentrenamiento y el impacto en precisión.

### Guía 10 – Solidez

#### Puntos clave

* Un sistema de IA de alto riesgo debe estar preparado para minimizar comportamientos perjudiciales y detectar entradas fuera de su dominio previsto; debe poder interrumpir su funcionamiento de manera segura cuando la solidez no esté garantizada
[aesia.digital.gob.es](https://aesia.digital.gob.es/storage/media/10-guia-solidez.pdf#:~:text=1,de%20solidez%20técnica%20como%20un)

* El artículo 15 considera la solidez técnica como requisito clave; las soluciones incluyen mecanismos de detección de anomalías, planes de prevención contra fallos y medidas para que, si la solidez no puede garantizarse, el sistema se interrumpa controladamente
[aesia.digital.gob.es](https://aesia.digital.gob.es/storage/media/10-guia-solidez.pdf#:~:text=,73)

* La guía explica que la solidez se vincula con la conservación de la precisión, la eficiencia, el rendimiento y la monitorización a lo largo del ciclo de vida; su relación con la ciberseguridad es estrecha, ya que la protección frente a ataques adversarios aumenta la solidez
[aesia.digital.gob.es](https://aesia.digital.gob.es/storage/media/10-guia-solidez.pdf#:~:text=La%20solidez%20del%20sistema%20de,adversarios%2C%20que%20podrían%20AI%20Act)

#### Impacto en el stack y solución

* Gestión de entradas fuera de dominio: Implementa detectores de distribución (Out‑of‑Distribution, OOD) y valida que las entradas en producción se encuentren en el espacio esperado.

* Planes de contingencia: Añade mecanismos de fail-safe y redundancia. Por ejemplo, en un sistema de telecomunicaciones, incluye servidores de respaldo y políticas de conmutación por error que se activan ante una degradación del rendimiento.

* Pruebas de robustez: Realiza pruebas adversarias y fuzzing para identificar vulnerabilidades. Utiliza pruebas de rotación, ruido y perturbaciones para evaluar la solidez. Documenta métricas y umbrales en la documentación técnica.

* Monitorización y actualización: Controla continuamente la solidez mediante indicadores (pérdida de precisión, incremento de errores). Establece procesos de actualización del modelo y de las defensas de ciberseguridad cuando se detecte degradación.

### Guía 11 – Ciberseguridad

#### Puntos clave

* Esta guía tiene por objeto proporcionar a las empresas medidas para integrar la ciberseguridad específica de la IA dentro de un esquema más amplio de seguridad. Se centra en el artículo 15 del RIA y cubre la identificación de activos y actores, la identificación de vulnerabilidades, la definición de controles de seguridad y la revisión periódica de su efectividad
[aesia.digital.gob.es](https://aesia.digital.gob.es/storage/media/11-guia-ciberseguridad.pdf#:~:text=1,para%20implementar%20los%20requisitos%20de)

* La guía destaca que las amenazas de IA incluyen manipulaciones de los datos de entrenamiento, ataques de envenenamiento, evasión, inversión, extracción, canales laterales y cadena de suministro
[aesia.digital.gob.es](https://aesia.digital.gob.es/storage/media/11-guia-ciberseguridad.pdf#:~:text=2,la%20fase%20de%20inferencia%2C%20el)

* Se definen medidas organizativas, como planificar el nivel de ciberseguridad desde el diseño, involucrar al delegado de protección de datos, incluir recomendaciones de seguridad en las instrucciones del sistema, establecer responsables de ciberseguridad y programar auditorías regulares
[aesia.digital.gob.es](https://aesia.digital.gob.es/storage/media/11-guia-ciberseguridad.pdf#:~:text=activos%20para%20defenderse%20ante%20amenazas,puntos%20detallados%20en%20esta%20guía)
También se proponen medidas técnicas: automatizar pruebas de seguridad, actualizar con parcheado seguro y definir indicadores de ciberseguridad
[aesia.digital.gob.es](https://aesia.digital.gob.es/storage/media/11-guia-ciberseguridad.pdf#:~:text=19%20●%20En%20los%20procesos,El%20uso%20de%20estas)

#### Impacto en el stack y solución

* Análisis de amenazas: Realiza un modelo de amenazas específico para IA e identifica los activos (modelos, datos, hardware, API). Evalúa la exposición a ataques de envenenamiento y adversarios.
* Controles técnicos:
    * Usa pipelines seguros de datos (hashing, firma de datasets) para detectar manipulación y controles de integridad.
    * Aplica técnicas de robustez adversarial (defensive distillation, regularización) y medidas anti-exfiltración (differential privacy o devolución limitada de resultados).
    * Fortalece la cadena de suministro: revisa dependencias de código abierto, firma de software y hardware.
    * Implementa controles de acceso estrictos y monitorea logs para detectar anomalías.
      
* Medidas organizativas:
    * Integra ciberseguridad en el ciclo de vida (security-by-design).
    * Designa un responsable de seguridad y define indicadores clave; realiza auditorías internas y externas periódicas; documenta incidentes y su resolución.
    * Involucra al Delegado de Protección de Datos para alinear seguridad y privacidad.
      
### Guía 12 – Registros y archivos de registro generados automáticamente

#### Puntos clave

* Proporciona medidas para cumplir con los requisitos del RIA sobre generación y conservación de registros. Señala que un sistema de IA de alto riesgo debe incorporar registros que faciliten la transparencia y la rendición de cuentas
[aesia.digital.gob.es](https://aesia.digital.gob.es/storage/media/12-guia-de-registros.pdf#:~:text=En%20esta%20guía%20se%20presentan,a%20los%20requisitos%20del%20Reglamento)

* Define registro como un archivo que almacena información sobre el comportamiento y desempeño del sistema (entradas, salidas, errores) durante su entrenamiento o uso. Los registros son esenciales para análisis, mejora continua y como evidencia de cumplimiento
[aesia.digital.gob.es](https://aesia.digital.gob.es/storage/media/12-guia-de-registros.pdf#:~:text=2,que%20almacena%20información%20sobre%20el)

* Un sistema de gestión de registros implica procesos de captura, almacenamiento, control de acceso, retención y eliminación, así como seguimiento y mejora continua
[aesia.digital.gob.es](https://aesia.digital.gob.es/storage/media/12-guia-de-registros.pdf#:~:text=En%20el%20contexto%20de%20la,y%20mejora%20continua%20del%20sistema)

* Los principios que deben garantizarse incluyen confidencialidad, integridad, disponibilidad, autenticidad, accesibilidad, trazabilidad y responsabilidad
[aesia.digital.gob.es](https://aesia.digital.gob.es/storage/media/12-guia-de-registros.pdf#:~:text=2,ser%20responsabilidad%20del%20propietario%20del)

#### Impacto en el stack y solución

* Infraestructura de registros: Configura un sistema centralizado de logging (ELK Stack, Graylog) para almacenar entradas, predicciones, métricas de rendimiento y errores.
* Control de acceso: Implementa mecanismos de autenticación y autorización para acceder a los registros; cifra los logs sensibles.
* Política de retención: Define periodos de retención de logs y procedimientos seguros para su eliminación.
* Trazabilidad y auditoría: Asegura que cada entrada en el registro esté asociada a una transacción y persona responsable. Utiliza identificadores únicos y firma digital para verificar autenticidad.
* Integración con vigilancia poscomercialización: Los registros alimentan los indicadores utilizados para la supervisión continua.

### Guía 13 – Plan de vigilancia poscomercialización

#### Puntos clave

* El AI Act exige un plan de vigilancia poscomercialización para los sistemas de IA de alto riesgo; la guía lo define como un conjunto de actividades para recolectar y evaluar la experiencia de sistemas en servicio, asegurando que siguen siendo seguros y funcionan correctamente
[aesia.digital.gob.es](https://aesia.digital.gob.es/storage/media/13-guia-vigilancia-poscomercializacion.pdf#:~:text=dentro%20del%20plan%20de%20vigilancia,se%20contempla%20el%20desarrollo%20de)

* La vigilancia implica subsistemas de captación de indicadores, registro de indicadores, alertas automatizadas y interfaces de análisis
[aesia.digital.gob.es](https://aesia.digital.gob.es/storage/media/13-guia-vigilancia-poscomercializacion.pdf)

* El responsable del despliegue debe notificar al proveedor cualquier modificación anómala del comportamiento; si no puede contactar, debe aplicar cambios o suspender el uso según el artículo 26-5 del Reglamento
[aesia.digital.gob.es](https://aesia.digital.gob.es/storage/media/13-guia-vigilancia-poscomercializacion.pdf#:~:text=Los%20requisitos%20descritos%20en%20el,centran%20en%20la%20notificación%20de)

#### Impacto en el stack y solución

* Sistema de monitorización:
    * Configura sistemas de monitorización continua (por ejemplo, Prometheus + Grafana) que recojan indicadores sobre rendimiento, consumo de recursos, seguridad y acciones de usuarios.
    * Establece alertas automatizadas cuando los indicadores se salen de los umbrales.
    * Crea paneles de control accesibles para los vigilantes humanos.
* Procedimiento de vigilancia: Elabora un plan que defina cómo se recogerán los indicadores, qué umbrales dispararán revisiones, quién revisará los resultados y cómo se reportarán anomalías al proveedor.
  
* Retroalimentación en el ciclo de vida: Integrar el feedback de la vigilancia para ajustar modelos, datos y controles. Documentar todas las acciones realizadas.
  
### Guía 14 – Notificación de incidentes graves

#### Puntos clave

* El artículo 73 del Reglamento obliga a notificar a las autoridades de vigilancia del mercado cualquier incidente grave relacionado con un sistema de IA de alto riesgo. La guía describe el procedimiento y las medidas para abordar la notificación
[aesia.digital.gob.es](https://aesia.digital.gob.es/storage/media/14-guia-gestion-de-incidentes.pdf#:~:text=,25)

* Un incidente grave se define como un incidente o defecto de funcionamiento que pueda causar muerte o daños graves a personas, alteraciones irreversibles de infraestructuras críticas, incumplimiento de derechos fundamentales o daños graves a la propiedad o al medio ambiente
[aesia.digital.gob.es](https://aesia.digital.gob.es/storage/media/14-guia-gestion-de-incidentes.pdf#:~:text=Para%20comenzar%2C%20es%20importante%20fijar,“incidente%20grave”%20al%20que%20hace)

* Los proveedores deben notificar inmediatamente una vez establecida la relación causal entre el sistema y el incidente y, en cualquier caso, en un máximo de 15 días
[aesia.digital.gob.es](https://aesia.digital.gob.es/storage/media/14-guia-gestion-de-incidentes.pdf#:~:text=1,su%20caso%2C%20el%20responsable%20del)
Si el responsable del despliegue no consigue contactar con el proveedor, debe notificar él mismo
[aesia.digital.gob.es](https://aesia.digital.gob.es/storage/media/14-guia-gestion-de-incidentes.pdf#:~:text=Este%20documento%20está%20dirigido%20a,que%20el%20Reglamento%20en%20el)

#### Impacto en el stack and solución

* Gestión de incidentes: Implementa un sistema de detección y respuesta a incidentes (SIEM). Define un protocolo interno para categorizar incidentes según su gravedad e iniciar la notificación.

* Procedimientos de notificación:
    * Establece plantillas de reporte y flujos de aprobación.
    * Recopila evidencias (registros, métricas, decisiones humanas) que respalden el informe.
    * Guarda registros de notificaciones enviadas y de cualquier comunicación con la autoridad.
    * Responsabilidad compartida: Documenta las responsabilidades del proveedor y del responsable del despliegue y sus mecanismos de contacto.

### Guía 15 – Documentación técnica

#### Puntos clave

* La guía detalla qué exige el Reglamento a la documentación técnica, cómo reflejarlo y cómo conservarla
[aesia.digital.gob.es](https://aesia.digital.gob.es/storage/media/15-guia-documentacion-tecnica.pdf#:~:text=4%201,estructurar%20la%20documentación%2C%20en%20detalle)
Incluye la descripción general del sistema de IA, sus componentes, procesos de diseño y validación, especificación de datos de entrada, medidas de riesgo y de supervisión humana, resultados no deseados, parámetros de rendimiento, sistema de gestión de riesgos, control de cambios, normas armonizadas y declaración de conformidad
[aesia.digital.gob.es](https://aesia.digital.gob.es/storage/media/15-guia-documentacion-tecnica.pdf#:~:text=5,12%20Sistema%20de%20vigilancia%20poscomercialización)

* El objetivo es garantizar que la documentación sirva de evidencia durante la evaluación de conformidad y pueda ser consultada por las autoridades.

#### Impacto en el stack y solución

* Repositorio de documentación: Utiliza un repositorio versionado (Git/GitHub) para almacenar documentación técnica junto con el código.

* Contenido mínimo:
    * Descripción del sistema: Arquitectura, algoritmos, hardware, software y interfaces.
    * Datos: Origen, representatividad, tratamientos, calidad y justificación de su idoneidad.
    * Procesos: Diseño, entrenamiento, validación, pruebas de precisión y robustez, gestión de riesgos y de ciberseguridad.
    * Supervisión humana y mecanismos de intervención.
    * Registro de cambios y versiones de modelos.
* Conservación: Define políticas de conservación en línea con el artículo 18 del RIA; almacena la documentación durante un periodo adecuado y garantiza su acceso a las autoridades.
 
### Guía 16 – Manual de checklist de guías de requisitos

#### Puntos clave

* El manual forma parte del sandbox y ofrece una herramienta de checklist que permite a las entidades realizar un autodiagnóstico de su cumplimiento del RIA y diseñar un Plan de Adaptación (PDA). El objetivo es identificar la brecha entre el estado actual y el cumplimiento y planificar las medidas a implantar
[aesia.digital.gob.es](https://aesia.digital.gob.es/storage/media/16-manual-de-checklist-de-guias-de-requisitos.pdf#:~:text=5%201,de%20manera%20sencilla%2C%20pudiendo%20además)

* La herramienta tiene secciones informativas (portada, introducción, relación con artículos del RIA, medidas de las guías) y secciones operativas (auto-evaluación de las medidas, medidas adicionales y su relación con apartados del RIA)
[aesia.digital.gob.es](https://aesia.digital.gob.es/storage/media/16-manual-de-checklist-de-guias-de-requisitos.pdf#:~:text=3%20Índice%20detallado%201,Operativa%5D....................................................%20.......................................................12)

* Se dispone de un checklist específico para cada uno de los 12 requisitos: sistema de gestión de la calidad, gestión de riesgos, supervisión humana, gobernanza de datos, transparencia, precisión, solidez, ciberseguridad, registros, documentación técnica, vigilancia poscomercialización y gestión de incidentes
[aesia.digital.gob.es](https://aesia.digital.gob.es/storage/media/16-manual-de-checklist-de-guias-de-requisitos.pdf#:~:text=Existe%20una%20herramienta%20checklist%20para,poscomercialización%20y%20gestión%20de%20incidentes)

#### Impacto en el stack y solución

* Autoevaluación: Utiliza la herramienta de checklist para evaluar el estado de tu sistema frente a cada guía. Anota las medidas cumplidas y las pendientes.

* Plan de Adaptación: Diseña un PDA indicando recursos, responsables y plazos para implantar las medidas faltantes.
* Integración continua: Incluye la autoevaluación en ciclos de mejora continua, alineándola con auditorías de calidad y revisiones periódicas.

## Conclusión y recomendaciones generales
El conjunto de guías de la AESIA proporciona un marco integral para desarrollar y operar sistemas de IA de alto riesgo de forma segura, transparente y conforme al Reglamento Europeo de Inteligencia Artificial. Para un ingeniero de telecomunicaciones y funcionario que gestione sistemas de IA en un contexto de servicios públicos o de infraestructura crítica, las principales acciones a implementar en su stack son:
1. Adoptar un enfoque de calidad y riesgo: Establecer sistemas de gestión de la calidad y de riesgos que abarquen desde la concepción del sistema hasta su retirada.

2. Integrar la vigilancia humana: Garantizar que cualquier decisión automatizada esté supervisada por personal cualificado con herramientas de explicabilidad y mecanismos de intervención.

3. Controlar el ciclo de vida de los datos: Aplicar prácticas de gobernanza, documentar el origen y las características de los datos, asegurar la representatividad y proteger la privacidad.

4. Garantizar transparencia y precisión: Informar a los usuarios sobre el funcionamiento, las limitaciones y los riesgos del sistema, y monitorizar continuamente la precisión para evitar degradaciones.

5. Asegurar la solidez y la ciberseguridad: Diseñar sistemas que resistan ataques, errores y entradas fuera de dominio, implementando defensas frente a amenazas específicas de IA y adoptando medidas de protección de la cadena de suministro.

6. Establecer sistemas de registro y vigilancia: Crear infraestructuras de logging y monitorización que permitan analizar el comportamiento del sistema, detectar anomalías y generar alertas.

7. Preparar procedimientos de notificación e incidentes: Definir protocolos de respuesta ante incidentes graves, asignar responsabilidades y preparar la documentación para notificar a las autoridades en tiempo y forma.

8. Desarrollar documentación técnica exhaustiva: Registrar de manera estructurada toda la información requerida por el RIA, desde la descripción del modelo y de los datos hasta las pruebas realizadas y los mecanismos de supervisión y seguridad.

9. Usar el checklist como herramienta de mejora: Aplicar la herramienta del manual para evaluar periódicamente el cumplimiento y planificar las mejoras necesarias.
    
La implantación diligente de estas medidas no solo permitirá cumplir con la normativa europea, sino que también mejorará la fiabilidad, seguridad y aceptación social de los sistemas de IA desplegados en entornos de telecomunicaciones y servicios públicos