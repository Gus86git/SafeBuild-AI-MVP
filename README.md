# SafeBuild AI

**Sistema Inteligente de Detección de EPP**

Aplicación Streamlit para analizar imágenes y muestras de video, consultar observaciones registradas y recuperar evidencia documental sobre seguridad en obra. Combina visión artificial, SQLite y búsqueda documental con una interfaz oscura y navegación por empresa y obra.

## Funcionalidades

- Análisis de imágenes con un modelo YOLO local autorizado, cajas y confianza configurables.
- Observaciones por persona y asociación experimental de casco/chaleco, con abstención ante ambigüedad.
- Exploración de muestras de video, sin seguimiento de identidades entre fotogramas.
- Historial SQLite, dashboard interactivo por contexto y exportaciones CSV, Excel y PNG.
- Recuperación BM25, semántica con ChromaDB e híbrida, con filtros, fragmentos y citas.
- Copilot para preguntas documentales, operativas o relacionadas con una imagen seleccionada.
- Integración opcional con Groq para explicaciones y transcripción de voz, con autorización de envío.
- Barra de texto/micrófono y lectura mediante voces locales del navegador.

Una observación visual no certifica seguridad ni cumplimiento legal. La ausencia de una detección no confirma ausencia de EPP. La precisión independiente del detector y el recorrido remoto completo de voz/generación permanecen pendientes de validación; las evidencias locales funcionan sin Groq.

## Arquitectura

```text
app.py                       Interfaz, navegación y contexto de trabajo
safeguard/core.py            Contratos y evaluación de observaciones
safeguard/vision.py          Adaptador de inferencia y anotaciones
safeguard/media.py           Ingreso validado y muestreo de medios
safeguard/models.py          Autorización y carga de modelos locales
safeguard/storage.py         SQLite e integridad de registros
safeguard/reporting.py       Tablas, gráficos y exportaciones
safeguard/rag/               Ingesta, fragmentos, BM25, Chroma y citas
safeguard/copilot/           Consultas, contexto, generación y voz
safeguard/ui/                Tema, bienvenida y dashboard
assets/safebuild/            CSS e imágenes de interfaz
scripts/                    Indexación, evaluaciones y comprobaciones
tests/                      Regresión y fixtures sintéticos
```

Tecnologías: Python 3.12, Streamlit, Ultralytics/PyTorch CPU, OpenCV, Pillow, NumPy, pandas, SQLite, Plotly, XlsxWriter, pypdf, rank-bm25, sentence-transformers, ChromaDB y SDK Groq. El componente de audio usa JavaScript y APIs públicas del navegador; no requiere React ni un servicio adicional.

El paquete Python conserva el nombre `safeguard` por compatibilidad de imports. La identidad pública del producto es SafeBuild AI.

## Instalación en Windows

Requisitos: Python 3.12 y acceso a los repositorios de paquetes. No se requiere Linux, WSL ni Docker.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

Abrir <http://127.0.0.1:8501>. Detener con `Ctrl+C`.

`requirements.txt` reúne UI, inferencia CPU, RAG y Groq. Utiliza el índice oficial de PyTorch para sus ruedas CPU. Las versiones directas están fijadas; no es un lock transitivo de Linux. La instalación limpia en Ubuntu se comprueba con el workflow incluido y su resultado debe revisarse antes de publicar.

El paquete de demo incluye el modelo EPP V1 y 15 documentos con hashes. El arranque prepara los archivos locales y BM25 sin descargas. Los embeddings oficiales y Chroma se preparan con el botón **Preparar búsqueda semántica**, dentro de Configuración de Copilot. Consultar [puesta en marcha y continuidad](docs/CONTINUIDAD_STREAMLIT.md), incluyendo límites de memoria, licencias, almacenamiento y pruebas online pendientes.

## Configuración

| Variable / archivo | Uso |
|---|---|
| `SAFEGUARD_DB_PATH` | SQLite; por defecto `data/local/safeguard_demo.sqlite3`. |
| `SAFEGUARD_MODEL_PATH` | Pesos locales; por defecto `models/epp_v1/best.pt`. Deben estar dentro del proyecto y aprobados en el manifiesto. |
| `models/authorized.json` | Aprobación por ruta, hash, fuente, licencia y clases esperadas. No se distribuye. |
| `SAFEGUARD_RAG_PATH` | Directorio de índice, metadatos y manifiesto; por defecto `data/rag`. |
| `SAFEGUARD_EMBEDDING_PATH` | Embeddings y manifiesto local; por defecto `models/embeddings/minilm-multilingual`. |
| `GROQ_API_KEY` | Credencial del proveedor: entorno o gestor de secretos, nunca Git. |
| `GROQ_MODEL` | Modelo de generación; se comprueba al solicitar una generación. |
| `.streamlit/config.toml` | Tema y límites de servidor; sin secretos ni dirección específica del hosting. |

En Windows se pueden definir variables para la sesión con `$env:SAFEGUARD_DB_PATH = 'ruta-local'`. Para secretos se admite `.streamlit/secrets.toml`, excluido de Git. No introducir claves en preguntas, archivos públicos, capturas o logs.

SQLite inicializa un catálogo ficticio de empresas/obras cuando falta la base. No precarga análisis reales. Los filtros por empresa/obra no sustituyen autenticación ni permisos multiusuario.

### Modelo de detección

El administrador debe revisar procedencia, derechos y hash antes de autorizar un peso. La autorización de carga no acredita precisión. El manifiesto debe identificar exactamente el archivo y sus clases; no cargar pesos de origen desconocido. Véase [recursos y despliegue](docs/DEPLOYMENT.md).

### Corpus documental

Preparar documentos autorizados y un manifiesto en `data/rag/manifests/documents.json` con metadatos de procedencia. La ingesta no se ejecuta durante las consultas:

```powershell
.\.venv\Scripts\python.exe scripts/build_rag_index.py --manifest data/rag/manifests/documents.json
```

Para construir también el índice vectorial, preparar primero el modelo de embeddings local con su manifiesto e incluir `--vectors`. El script `download_rag_model.py` solo realiza una descarga al invocarlo explícitamente con `--authorized-download`; no forma parte del arranque ni de CI.

## Uso

1. Seleccionar empresa, obra y procedencia en el sidebar.
2. Abrir «Controles de análisis y recursos», cargar el modelo autorizado y ajustar confianza/resolución.
3. En Imagen o Video, cargar el medio, analizar y revisar detecciones, asociaciones y advertencias.
4. Consultar registros en Dashboard/Historial o exportar los resultados.
5. Desde una imagen persistida, abrir la consulta contextual de Copilot y revisar sus fuentes.
6. En «Configuración de Copilot», ajustar análisis, método, fechas, fuentes y opciones del asistente activo. El centro se reserva para preguntas y evidencias.

Para voz, autorizar el envío de audio y conceder permiso al navegador. La transcripción remota y la generación documental tienen consentimientos separados. La lectura usa voces españolas locales y depende de su disponibilidad. Si la reproducción automática falla, se ofrece lectura manual.

## Pruebas

```powershell
.\.venv\Scripts\python.exe scripts/ci_checks.py tests
node --test tests/test_audio_component.mjs
.\.venv\Scripts\python.exe scripts/ci_checks.py smoke
.\.venv\Scripts\python.exe scripts/check_distribution.py
```

Node.js se necesita para las pruebas JavaScript, no para ejecutar Streamlit. Las pruebas usan fixtures y bases temporales. Ninguna aprobación de mocks se presenta como validación de pesos, corpus privado, micrófono o proveedor real.

El workflow [Linux compatibility](.github/workflows/linux.yml) comprueba instalación, imports, estilo, regresión y arranque HTTP con `ubuntu-latest`. No despliega, no recibe secretos y no descarga modelos. Publica un informe de omisiones. Su inclusión no significa que ya haya sido ejecutado: consultar [estado de validación](docs/VALIDATION.md).

## Restricciones relevantes

- MVP académico, sin autenticación empresarial ni flujo completo de revisión profesional firmado/auditado.
- La asociación individual es experimental para casco/chaleco; otros EPP son detecciones de escena.
- Video por muestras: sin tracking, cámaras en vivo ni conteo de trabajadores únicos.
- Imágenes hasta 20 MB/20 megapíxeles y video hasta 100 MB, con límites adicionales; codecs y memoria deben verificarse en el destino.
- Las imágenes animadas/multipágina se tratan como una primera imagen con aviso; no se admiten todos los formatos existentes.
- Los documentos aportados requieren revisión de vigencia/completitud. Las fuentes ficticias se identifican. La generación normativa permanece bloqueada.
- SQLite local no incorpora por sí solo persistencia garantizada, backups ni aislamiento entre clientes. El estado actual de revisión no constituye un historial de decisiones.
- Gate 1 de generación contextual remota permanece pendiente. No se garantiza disponibilidad ni corrección semántica de Groq o transcripción real por el solo hecho de configurar una clave.

Para distribución, revisar [seguridad](docs/SECURITY.md), [derechos y atribuciones](docs/RIGHTS.md) y [recursos del hosting](docs/DEPLOYMENT.md). No se concede una licencia del proyecto por omisión: su elección corresponde a los titulares.
