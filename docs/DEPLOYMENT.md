# Recursos y compatibilidad de despliegue

**Actualización 11/11/2026:** la provisión de demo está implementada. Consultar [la guía de continuidad](CONTINUIDAD_STREAMLIT.md) para los recursos incluidos, el botón de preparación semántica y las pruebas online pendientes. El flujo Linux del commit inicial pasó en [GitHub Actions](https://github.com/Gus86git/SafeBuild-AI-MVP/actions/runs/42914189581); esto no verifica por sí solo la instancia Streamlit desplegada.

## Entorno

Python 3.12, dependencias de `requirements.txt` y bibliotecas del sistema listadas en `packages.txt`. La validación Linux se prepara en GitHub Actions con `ubuntu-latest`; no requiere instalar Linux, WSL o Docker en la computadora de desarrollo.

La configuración omite una dirección de escucha fija: el destino debe definirla. En una PC usar explícitamente `--server.address 127.0.0.1`. CORS y protección XSRF permanecen activos. No copiar secretos locales al repositorio.

`requirements-ui.txt`, `requirements-inference.txt`, `requirements-rag.txt` y `requirements-copilot.txt` mantienen responsabilidades separadas; `requirements.txt` los reúne. `requirements-cpu.txt` se conserva como instalación explícita CPU alternativa, sin confundir su índice exclusivo con el índice para el resto de paquetes. Las versiones directas están fijadas; se necesita una instalación Linux satisfactoria antes de generar o afirmar un lock transitivo validado.

## Recursos y condiciones de ejecución

| Recurso | Provisión y comprobación |
|---|---|
| Pesos YOLO | Copia autorizada bajo `models/`, hash y clase coincidentes con `models/authorized.json`; fuente/licencia revisadas. Sin pesos, análisis deshabilitado con aviso. |
| Embeddings | Modelo multilingüe local y `safeguard_model.json` con revisión y hashes; sin él BM25 puede funcionar con un corpus indexado. |
| Documentos | Solo archivos autorizados y manifiesto con procedencia, tipo, versión y estado. No copiar automáticamente el corpus local. |
| Índice RAG | Construcción explícita por `scripts/build_rag_index.py`; generación vectorial compatible con modelo y versión de Chroma. |
| SQLite | Ruta escribible, política de acceso, persistencia, backup y restauración. Para demo desechable, informar que puede reiniciarse y prohibir datos privados. |
| Groq | Credencial en el gestor de secretos del destino, límites de uso y generación/transcripción probadas con autorización. |
| Medios de entrada | La distribución no contiene fotografías/videos de prueba. El operador debe tener autorización para los medios que cargue. |

Ejemplo estructural del manifiesto de modelo; estos valores no autorizan un artefacto real:

```json
{
  "models/epp_v1/best.pt": {
    "approved": false,
    "sha256": "REEMPLAZAR_POR_HASH_VERIFICADO",
    "source": "PROCEDENCIA_VERIFICADA",
    "license": "CONDICIONES_REVISADAS",
    "expected_classes": []
  }
}
```

En el manifiesto documental cada registro necesita al menos `document_id`, `filename`, `title`, `source_type`, `is_synthetic`, `approved` y metadatos de versión/procedencia. Las rutas se resuelven respecto de la raíz del proyecto. La ingesta rechaza archivos fuera del ámbito autorizado; no registrar rutas de una computadora como recursos portables.

## GitHub Actions

El workflow instala el conjunto completo CPU, ejecuta `pip check`, Ruff, un escaneo de patrones y pruebas Python/JavaScript, e inicia Streamlit para comprobar su endpoint de salud. AppTest cubre la ejecución de páginas por separado: un HTTP 200 por sí solo no valida la UI.

El resultado de `unittest` enumera omisiones y motivos en `output/ci/python-tests.json`. `resource-status.md` identifica pruebas reales no ejecutadas: YOLO con pesos, corpus/embeddings reales, Groq, STT y micrófono. No hay `continue-on-error` para ocultar fallos de instalación o regresión.

El workflow no prueba capacidad del hosting, persistencia, cuentas simultáneas ni precisión. Debe ejecutarse en el futuro repositorio y revisarse su evidencia antes de afirmar compatibilidad Linux. Los scripts de descarga y de verificación con datos reales no se ejecutan automáticamente.

## Aceptación antes de difusión

- Instalación Linux reproducida sin conflictos.
- Modelos/documentos autorizados disponibles y límites de memoria medidos.
- Separación de sesiones y acceso definida; el selector de empresa no equivale a permisos.
- Persistencia y restauración o descarte de datos de demo comprobados.
- Recorrido imagen → SQLite → dashboard/historial → exportación → Copilot comprobado en HTTPS.
- Video, errores de entrada, estado vacío y falta de recursos comprobados.
- Micrófono/Groq probados en una instancia controlada o deshabilitados hasta su aprobación.
- Paquete, licencias, secretos, acceso y recuperación revisados antes de publicar.

Referencias: [dependencias Streamlit](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies), [organización de archivos](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/file-organization), [secretos](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management), [workflow Python oficial](https://docs.github.com/en/actions/tutorials/build-and-test-code/python).
