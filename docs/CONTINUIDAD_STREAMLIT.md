# SafeBuild AI: puesta en marcha y continuidad

## Aplicación desplegada

Repositorio privado: https://github.com/Gus86git/SafeBuild-AI-MVP. Rama `main`, entrada `app.py`, Python 3.12. Streamlit actualiza la aplicación al recibir cambios en esta rama. No se incluye ninguna clave en el repositorio. La credencial debe llamarse `GROQ_API_KEY` en Secrets de Streamlit.

## Recursos incluidos y arranque

`deployment_resources/` contiene el peso EPP V1 aportado, su autorización técnica, 15 documentos aportados (10 copias normativas y 5 documentos ficticios TechCorp), manifiestos y hashes. El arranque verifica la integridad, prepara el modelo en `models/epp_v1/best.pt` y construye el índice documental BM25 en `data/rag`. No importa bases operativas ni fotos del equipo. No sustituye un recurso local diferente sin revisión.

El modelo conserva las 11 clases del artefacto original. Su carga autorizada no acredita precisión. Las asociaciones individuales y los estados de incertidumbre conservan sus limitaciones. Las copias normativas no se certifican como completas o vigentes. Los documentos TechCorp siguen identificados como ficticios.

## Qué hacer al abrir la aplicación

1. Esperar la actualización de Streamlit y recargar la página. Si no cambia, usar **Manage app → Reboot app** y revisar los logs.
2. Elegir empresa, obra y procedencia. Son filtros del contexto, no controles de acceso.
3. En **Controles de análisis y recursos**, pulsar **Cargar modelo autorizado**. Analizar una imagen autorizada y revisar las observaciones antes de guardarlas.
4. Revisar Dashboard, Historial y Exportar. SQLite comienza sin análisis reales; no habrá cifras hasta guardar resultados.
5. Abrir **Copilot · Conocimiento**: BM25 permite consultar los documentos inmediatamente. Verificar las citas y la identificación de contenido ficticio.
6. Para usar recuperación semántica o híbrida, abrir **Configuración de Copilot → Preparar búsqueda semántica**. Descarga el modelo oficial MiniLM con revisión y hashes fijados y construye Chroma localmente. Puede tardar varios minutos; no consume Groq. Tras terminar, elegir **Híbrida**. Si falla, BM25 sigue disponible.
7. En **Copilot · Asistente**, seleccionar el análisis y consultar datos operativos/documentos. La generación Groq es opcional y conserva las autorizaciones y validaciones existentes. La clave por sí sola no ejecuta solicitudes.
8. Probar voz en HTTPS, permitir el micrófono y aceptar el envío de audio cuando la interfaz lo solicite. La lectura en voz alta depende del navegador. Esta entrega no ejecuta llamadas reales a Groq ni transcripciones.

## Almacenamiento y capacidad

La SQLite de esta demo se comparte entre sesiones del servidor y no hay aislamiento empresarial por autenticación. No cargar datos confidenciales ni habilitar acceso irrestricto como aplicación empresarial. Exportar los resultados antes de reiniciar; el disco del alojamiento puede reiniciarse y no hay backup externo automático. No se agregó una segunda base de datos ni se cambió el esquema.

Los embeddings ocupan varios cientos de MB en disco y requieren memoria adicional al cargarse. No están en Git. La preparación se repite si el servidor pierde su disco. Usar BM25 si el alojamiento no soporta la carga; si aparecen reinicios por memoria, revisar logs y capacidad antes de insistir. No se afirma capacidad validada para usuarios concurrentes. El botón de preparación usa un bloqueo de proceso para evitar dos construcciones simultáneas.

## Diagnóstico

| Síntoma | Acción |
|---|---|
| Modelo sin cargar | Pulsar Cargar modelo autorizado; revisar Sistema y errores de integridad. |
| Preparación de recursos incompleta | Revisar logs, existencia del paquete y hashes; no desactivar las comprobaciones. |
| Semántica falla o retorna BM25 | Preparar búsqueda semántica; comprobar red hacia Hugging Face, memoria y disco. |
| Groq sin clave | Confirmar nombre exacto `GROQ_API_KEY` en Secrets; no compartir el valor. |
| Groq rechaza o se abstiene | Revisar código de error y evidencia sin exponer secretos; no omitir validaciones ni forzar respuestas. |
| Historial vacío tras reiniciar | La demo usa almacenamiento efímero; recuperar exportaciones. No hay restauración automática. |
| Fuente normativa incompleta | Contrastar con fuente oficial y revisión profesional; no tratar fragmentos como certificación legal. |

## Verificación técnica reproducible

```bash
python scripts/check_distribution.py
ruff check .
python scripts/ci_checks.py tests
node --test tests/test_audio_component.mjs
python scripts/ci_checks.py smoke
```

Las pruebas usan recursos temporales y no envían solicitudes a Groq. `SAFEGUARD_DISABLE_BOOTSTRAP=1` desactiva la provisión automática; las rutas personalizadas `SAFEGUARD_MODEL_PATH`, `SAFEGUARD_RAG_PATH` o `SAFEGUARD_EMBEDDING_PATH` también la desactivan para preservar instalaciones administradas.

## Pendiente para aceptación online

- Probar imagen → guardado → dashboard → detalle → Copilot → exportación en la URL desplegada.
- Probar video, filtros de obra, ausencia de datos y errores de archivos.
- Probar Groq, su abstención/citas y micrófono en el navegador real.
- Medir memoria y tiempos en el plan de hosting; verificar recuperación tras reinicio.
- Definir acceso, persistencia y backups antes de uso operativo.
- Resolver licencias del producto y obligaciones de Ultralytics/Construction-PPE antes de distribución comercial o pública del artefacto. El permiso de operación solicitado no constituye una auditoría jurídica.

## Información para continuar el desarrollo

La lógica está en `safeguard/`, la entrada en `app.py`, las pruebas en `tests/`. YOLO, SQLite, BM25/Chroma, Copilot, voz y exportaciones conservan sus módulos. La provisión nueva está en `safeguard/deployment.py`. Adjuntar este documento, el error completo sin secretos, `app.py`, el módulo implicado y los resultados de GitHub Actions para continuar una revisión. No compartir Secrets, bases operativas o fotos privadas. Mantener separados lo implementado, lo probado localmente y lo validado online.
