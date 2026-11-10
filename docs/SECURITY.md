# Seguridad y tratamiento de datos

SafeBuild AI está preparado como MVP académico. No incluye autenticación ni autorización empresarial por usuario. No debe exponerse con datos privados suponiendo que los selectores de empresa/obra constituyen control de acceso.

## Controles presentes

- Modelos locales aprobados por hash, fuente y licencia declarada antes de deserializar.
- Ingreso de medios con límites y validación; temporales acotados.
- SQL parametrizado, comprobación de alcance, claves foráneas e idempotencia de guardado.
- Consultas de Copilot/dashboard de solo lectura; validación de contexto de imagen.
- Evidencias externas visibles, consentimiento por paquete, validación de citas y cantidades, errores sin cuerpos sensibles.
- Audio con consentimiento independiente, validación PCM, límites por sesión y sin almacenamiento de grabaciones en disco.
- CORS/XSRF activos; claves e índices excluidos del inventario Git.

## Restricciones

Los límites de sesión no sustituyen cuotas globales, protección ante abuso ni monitoreo. El presupuesto de video no interrumpe necesariamente una llamada nativa bloqueada. Los codecs no están aislados en un sandbox propio. Las advertencias legales no sustituyen validación profesional.

Antes de usar datos reales: definir autenticación, roles, retención, recuperación, tratamiento de medios/voz, proveedores autorizados y auditoría de revisión humana. Mantener deshabilitadas las capacidades remotas no aprobadas.

## Secretos

Usar variables de entorno o el gestor de secretos. No copiar `.streamlit/secrets.toml`, `.env`, claves, bases reales ni logs a Git. Revocar cualquier credencial expuesta y generar su sustituta fuera del chat. El escáner local detecta algunos patrones y archivos prohibidos sin imprimir valores, pero no prueba ausencia universal de secretos ni analiza un historial Git antiguo.

La primera entrega se prepara sin `.git`; por lo tanto no hereda historial previo. Después de aprobar e inicializar el repositorio, revisar el índice de archivos y cada cambio antes de transferirlo. Las reglas de `.gitignore` no eliminan un secreto que ya estuviera versionado.
