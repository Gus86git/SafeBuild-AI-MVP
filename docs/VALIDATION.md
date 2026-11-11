# Estado de validación del candidato

## Actualización: recursos de demo, 11 de noviembre de 2026

- Linux del commit inicial: [ejecución satisfactoria](https://github.com/Gus86git/SafeBuild-AI-MVP/actions/runs/42914189581), instalación completa, 219 pruebas Python, 18 JavaScript e inicio Streamlit.
- Después de agregar provisión: suite Windows de 224 pruebas satisfactoria (146,984 s); posteriormente, seis pruebas de provisión satisfactorias (incluyen un caso adicional de ingesta completa e idempotencia). No confundir este total con 230 casos únicos: cinco se superponen.
- JavaScript: 18/18; arranque HTTP con base temporal satisfactorio; Ruff sin hallazgos.
- Recursos reales locales: 15 documentos, 388 fragmentos, 388 vectores Chroma; búsqueda híbrida devuelve cinco fragmentos sin degradación. Construcción semántica: 215,19 s en esta máquina, no una medición del hosting.
- YOLO V1: carga por hash, 11 clases y una inferencia sobre imagen vacía ejecutadas. Es una comprobación del runtime, no de precisión ni de detección de EPP real.
- Descarga HTTP de pesos de embeddings no ejecutada en esta verificación: se reutilizó la copia local verificada. La integridad, el rechazo de descargas inválidas y la reutilización están cubiertos con pruebas aisladas.
- No se hicieron llamadas a Groq ni transcripciones. La UI desplegada, micrófono real, memoria del hosting y persistencia siguen pendientes de comprobación por el operador.

La ejecución inicial dentro del sandbox de Windows falló por permisos de temporales; se repitió fuera del aislamiento y pasó. Los resultados siguientes corresponden a la preparación histórica inicial, no al estado actualizado de recursos.

## Registro histórico: preparación inicial

Fecha: 10 de noviembre de 2026. Plataforma ejecutada: Windows, Python 3.12, entorno CPU existente. No se instaló un entorno nuevo ni se ejecutó Linux durante esta preparación.

| Comprobación | Resultado |
|---|---|
| Suite completa Python sobre el candidato | 219 ejecutadas, 0 fallos, 0 errores, 0 omitidas; 134,619 s. |
| Componente JavaScript | 18 ejecutadas, 18 aprobadas, 0 omitidas; 393 ms. |
| Imports de UI, visión, RAG y Groq | Satisfactorios en el entorno Windows existente; sin cargar pesos ni llamar al proveedor. |
| `pip check` | Sin dependencias rotas en ese entorno. No acredita instalación Linux. |
| Ruff: imports no usados, redefiniciones y nombres indefinidos | Sin hallazgos tras limpieza conservadora. |
| Formato Python | 63 archivos comprobados; formato consistente. |
| Escaneo del paquete | Sin coincidencias de los patrones de credenciales ni recursos prohibidos examinados. No es una auditoría exhaustiva de seguridad. |
| Arranque de Streamlit | Endpoint de salud HTTP satisfactorio en puerto temporal y base aislada. |
| Revisión visual | Bienvenida y dashboard vacío conservan tema, navegación y estados N/A, sin datos privados. |
| Workflow Ubuntu | YAML preparado y validado estructuralmente; NO EJECUTADO en GitHub Actions. |

La suite usa datos sintéticos y mocks donde corresponde. Las pruebas reales de pesos YOLO, corpus/embeddings aportados, Groq, STT, micrófono físico y sonido audible no se ejecutaron para este candidato. Sus recursos se distribuyen separadamente y sus omisiones se documentan expresamente en CI.

Las pruebas históricas del proyecto original no se presentan como nuevas ejecuciones del candidato. La copia de preparación conserva las evidencias completas fuera del inventario de distribución; las futuras ejecuciones CI producirán sus propios artefactos.

## Cambios revisados

- Formato Python consistente y eliminación de 15 imports sin uso verificados.
- Identidad pública SafeBuild AI; compatibilidad interna del paquete `safeguard` conservada.
- README actual, sin mezclar instrucciones de estados históricos.
- Archivo principal de dependencias completo y configuración sin dirección local impuesta al hosting.
- Mayor aislamiento de pruebas respecto de corpus/embeddings/credenciales locales.
- Workflow Linux y scripts de comprobación separados de las funciones de producto.
- No se modificaron algoritmos, umbrales, esquema SQLite, pesos, corpus ni definición de métricas.

## Dictamen

GO técnico para revisar el inventario de un primer repositorio privado. No se creó historial Git ni se transfirió información a un servicio remoto. La creación/primer commit dependen de la aprobación del inventario y de configurar la identidad de Git. NO-GO para despliegue público o uso empresarial: siguen pendientes la ejecución Linux, recursos autorizados, acceso/persistencia, capacidad del hosting y validaciones remotas correspondientes.
