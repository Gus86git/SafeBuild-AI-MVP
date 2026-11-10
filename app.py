"""SafeBuild AI: interfaz Streamlit sobre el núcleo de observación existente."""

from pathlib import Path
from hashlib import sha256
import sys
import sqlite3
import streamlit as st

from safeguard.models import dependency_versions, runtime_model
from safeguard.media import (
    read_image,
    png_bytes,
    explore_video,
    video_format,
    MediaError,
    IMAGE_EXTENSIONS,
    MAX_SAMPLES,
)
from safeguard.reporting import (
    export_rows,
    csv_bytes,
    excel_bytes,
    person_rows,
    state_chart,
    video_counts_chart,
    ppe_scene_rows,
)
from safeguard.workflow import image_record, video_record, append_history
from safeguard import storage
from safeguard.ui import presentation as ui

ROOT = Path(__file__).resolve().parent
PAGES = [
    "Inicio",
    "Dashboard",
    "Imágenes",
    "Videos",
    "Historial",
    "Copilot · Asistente",
    "Copilot · Conocimiento",
    "Exportar",
    "Sistema",
    "Ayuda",
    "Resumen",
]


@st.cache_resource(show_spinner=False)
def load_model():
    # A missing artifact must not block navigation or trigger imports/downloads.
    return runtime_model(ROOT)


def persist_record(record, settings, input_hash):
    if not settings.get("db_path"):
        raise ValueError("SQLite no disponible; el resultado aún no está guardado.")
    identifier, created = storage.save_analysis(
        settings["db_path"],
        record,
        settings["company_id"],
        settings["site_id"],
        input_hash,
        origin="real_inference",
    )
    record.update(
        analysis_id=identifier,
        company_id=settings["company_id"],
        site_id=settings["site_id"],
        origin="real_inference",
        input_sha256=input_hash,
        input_origin="user_upload",
        review_status="pending",
    )
    if not created:
        record.update(
            storage.get_analysis(
                settings["db_path"],
                identifier,
                settings["company_id"],
                settings["site_id"],
            )
        )
    history = st.session_state.setdefault("history_v1a", [])
    if not any(r.get("analysis_id") == identifier for r in history):
        if len(history) < 100:
            append_history(st.session_state, record)
    return identifier, created


def persisted_dashboard(settings):
    st.title("Centro de revisión")
    st.subheader("Registros persistentes · SQLite")
    st.caption(
        "Empresa y obras de demostración sintéticas. Los análisis se separan por procedencia; no son infracciones confirmadas."
    )
    if not settings.get("db_path"):
        st.warning("SQLite no disponible. Revise la ruta y permisos.")
        return
    try:
        data = storage.dashboard(
            settings["db_path"], settings["company_id"], origin=settings["origin"]
        )
        for col, label, value in zip(
            st.columns(3),
            ["Análisis registrados", "Observaciones", "Observaciones pendientes"],
            [data["total"], data["observations"], data["pending"]],
        ):
            col.metric(label, value)
        st.caption(
            "Consulta para toda la empresa y el origen seleccionado. Observaciones no equivale a trabajadores únicos."
        )
        st.write("Distribución de análisis por obra")
        if data["by_site"]:
            st.dataframe(data["by_site"], width="stretch")
        else:
            st.info("Aún no hay análisis registrados para esta procedencia.")
        st.write("Detecciones del modelo por clase")
        if data["classes"]:
            st.dataframe(data["classes"], width="stretch")
        recent = storage.history(
            settings["db_path"],
            settings["company_id"],
            origin=settings["origin"],
            limit=10,
        )
        if recent:
            st.write("Análisis recientes")
            st.dataframe(
                [
                    {
                        "ID": r["analysis_id"],
                        "Obra": r["site_id"],
                        "Fecha": r["ts"],
                        "Archivo": r["file"],
                        "Estado": r["level"],
                        "Origen": r["origin"],
                    }
                    for r in recent
                ],
                width="stretch",
            )
    except (sqlite3.Error, OSError, ValueError) as exc:
        st.error(f"No se pudo consultar SQLite ({type(exc).__name__}).")


def persisted_history(settings):
    st.subheader("Historial persistente de la obra")
    st.caption(
        "Hasta 1000 registros más recientes de la obra y procedencia seleccionadas. Limpiar sesión no borra SQLite."
    )
    if not settings.get("db_path"):
        st.warning("SQLite no disponible.")
        return []
    try:
        records = storage.history(
            settings["db_path"],
            settings["company_id"],
            settings["site_id"],
            settings["origin"],
            limit=1000,
        )
        if not records:
            st.info(
                "No hay registros en esta obra y procedencia. Cambie los filtros laterales o analice una imagen."
            )
        else:
            st.dataframe(export_rows(records), width="stretch", hide_index=True)
        return records
    except (sqlite3.Error, OSError, ValueError) as exc:
        st.error(f"Consulta de historial no disponible ({type(exc).__name__}).")
        return []


def header(page, model_info):
    if page == "Dashboard":
        return
    ui.topbar(st)
    if page not in ("Inicio", "Dashboard"):
        ui.page_heading(page, st)


def render_model_summary(model, info, errors):
    if model is None:
        if st.session_state.get("model_requested", False):
            st.warning("Modelo no disponible · inferencia deshabilitada")
        else:
            st.info(
                "Modelo sin cargar · use «Cargar modelo autorizado» en el panel lateral."
            )
        st.caption(
            "Puede explorar archivos. No se generan detecciones ni resultados simulados."
        )
    else:
        st.info(f"Artefacto local autorizado: {info['path']}")
        st.caption(
            "Precisión EPP no validada. La autorización del archivo no certifica su capacidad."
        )
    for error in errors:
        st.caption(error)


def render_people(result):
    st.subheader("Observaciones por persona")
    rows = person_rows(result)
    if not rows:
        st.info(
            "No se detectaron personas sobre el umbral. El estado es no verificable."
        )
    for row in rows:
        with st.container(border=True):
            st.markdown(f"**{row['Persona']}**")
            st.write(row["Estado"])
            st.write("Casco:", row["Casco"])
            st.write("Chaleco:", row["Chaleco"])
            st.caption(row["Origen"])
            st.caption(
                f"Caja: {row['Caja']} · puntuación persona: {row['Puntuación persona']} · umbral: {row['Umbral']}"
            )
            st.caption("Indicio de color: " + row["Indicio de color"])
            st.write(row["Motivo"])
    st.caption(
        "Los identificadores solo corresponden a esta imagen o fotograma. No identifican personas entre medios."
    )
    with st.expander("Detecciones y puntuaciones de origen"):
        st.dataframe(result["detections"], width="stretch")
        st.caption(
            "Las puntuaciones del modelo no son probabilidades calibradas. Los indicios de color son experimentales."
        )


def result_summary(result):
    """Recovered base metrics, using the corrected observation contracts."""
    stats = result["stats"]
    for col, label, value in zip(
        st.columns(4),
        ["Detecciones", "Personas", "Cascos", "Chalecos"],
        [stats["total_detections"], stats["persons"], stats["helmets"], stats["vests"]],
    ):
        col.metric(label, value)
    with st.container(border=True):
        st.subheader(result["level"])
        st.write(
            result.get("action", "Revisar evidencia y contexto con un profesional.")
        )
        st.caption(
            f"Personas con casco y chaleco asociados: {stats.get('associated_pairs', 0)}. Esto no acredita cumplimiento."
        )
        st.caption(
            "Cumplimiento: N/A · La imagen no permite certificar condiciones de seguridad."
        )


def session_summary(history, total_label="Análisis de sesión"):
    cols = st.columns(4)
    cols[0].metric(total_label, len(history))
    cols[1].metric("Imágenes", sum(r.get("kind") == "imagen" for r in history))
    cols[2].metric("Videos", sum(r.get("kind") == "video" for r in history))
    cols[3].metric(
        "Para revisión humana",
        sum(r["level"] == "Requiere revisión humana" for r in history),
    )


def help_page():
    st.title("Cómo usar SafeBuild AI")
    st.write("1. Abra Imágenes o Videos desde el menú lateral y cargue un archivo.")
    st.write(
        "2. Ajuste el umbral y la visualización de cajas. Los recursos CPU están en la barra lateral."
    )
    st.write(
        "3. Cargue un modelo autorizado para analizar; sin modelo puede previsualizar y explorar."
    )
    st.write(
        "4. Revise métricas, observaciones individuales y motivos de incertidumbre."
    )
    st.write("5. Descargue el PNG y exporte CSV o Excel antes de cerrar la sesión.")
    with st.container(border=True):
        st.subheader("Fotos claras, observaciones más útiles")
        st.write(
            "Busque buena iluminación, contraste y personas visibles. Evite desenfoque y oclusiones; conserve detalle suficiente para observar casco y chaleco."
        )
        st.caption(
            "La recomendación de la base de 640 × 480 px no garantiza precisión; también se admiten imágenes pequeñas dentro de los límites."
        )
    st.subheader("Formatos y límites")
    st.write(
        "Fotos: JPEG/JPG/JFIF, PNG, BMP, WebP, TIFF, GIF y AVIF. En GIF, TIFF o WebP con varias imágenes se utiliza solamente la primera y se informa en pantalla."
    )
    st.write(
        "HEIC/HEIF, RAW, SVG y PDF no tienen un decodificador habilitado. Exporte una copia JPEG o PNG desde su aplicación de fotos."
    )
    st.write(
        "Video: MP4, MOV, AVI y MKV, sujeto a codecs disponibles. Hasta 60 muestras; solo se guardan fotogramas seleccionados."
    )
    st.caption(
        "Los límites de tamaño se configuran al costado. La ausencia de detección no confirma ausencia física de EPP."
    )


def dashboard(history, model, info, errors):
    st.subheader("Actividad de esta sesión")
    st.write(
        "Una vista de los análisis realizados en esta sesión, sin extrapolar a condiciones de seguridad."
    )
    cols = st.columns(3)
    cols[0].metric("Análisis en sesión", len(history))
    cols[1].metric(
        "Imágenes analizadas", sum(r.get("kind") == "imagen" for r in history)
    )
    cols[2].metric("Videos analizados", sum(r.get("kind") == "video" for r in history))
    render_model_summary(model, info, errors)
    if history:
        st.subheader("Análisis recientes")
        st.dataframe(
            [
                {
                    "Archivo": r["file"],
                    "Tipo": r.get("kind", "imagen"),
                    "Estado": r["level"],
                }
                for r in reversed(history[-5:])
            ],
            width="stretch",
        )
        try:
            st.plotly_chart(state_chart(history), width="stretch")
        except ImportError:
            st.info("El gráfico requiere Plotly. El historial sigue disponible.")
    else:
        with st.container(border=True):
            st.subheader("Empiece por una imagen")
            st.write(
                "Abra Imágenes para previsualizar un archivo. Con un modelo autorizado podrá revisar cajas y asociaciones por trabajador."
            )
            st.caption(
                "El panel se completará con sus análisis. No incluye ejemplos ni métricas simuladas."
            )
            if st.button(
                "Comenzar con una imagen", key="dashboard_image", type="primary"
            ):
                st.session_state["pending_navigation"] = "Imágenes"
                st.rerun()
            if st.button("Consultar documentos", key="dashboard_documents"):
                st.session_state["pending_navigation"] = "Copilot · Conocimiento"
                st.rerun()
    with st.container(border=True):
        st.subheader("Un flujo de trabajo transparente")
        st.write(
            "01 · Cargar un medio   →   02 · Explorar observaciones   →   03 · Exportar para revisión"
        )
    st.caption(
        "Esta vista resume la sesión; los análisis guardados se consultan también desde SQLite por obra."
    )


def image_page(model, info, threshold, use_color, settings):
    st.title("Análisis de imágenes")
    st.write(
        "Compare la imagen original con sus observaciones y revise cada asociación."
    )
    st.caption(
        "1 · Confirme empresa y obra al costado → 2 · Cargue y analice → 3 · Revise el guardado → 4 · Consulte Copilot o exporte"
    )
    from safeguard.copilot.selection import selected_id
    from safeguard.copilot.operational import OperationalQueryService

    identifier = selected_id(st.session_state, settings)
    if identifier:
        try:
            from safeguard.copilot.ui import display_analysis

            selected = OperationalQueryService(settings["db_path"]).analysis(
                identifier,
                settings["company_id"],
                settings["site_id"],
                settings["origin"],
            )
            with st.expander(
                "Volver a las observaciones del análisis seleccionado", expanded=True
            ):
                display_analysis(selected)
                cached = st.session_state.get("image_result", {})
                if cached.get("analysis_id") == identifier and cached.get("png"):
                    st.image(
                        cached["png"],
                        caption="Vista anotada conservada en esta sesión",
                        width="stretch",
                    )
                else:
                    st.caption(
                        "SQLite conserva observaciones y referencias, no la fotografía. Puede volver a cargar el archivo para verla."
                    )
                contextual_action(identifier, settings, key="image_selected_copilot")
        except (ValueError, OSError, sqlite3.Error):
            st.warning("El análisis seleccionado ya no está disponible en esta obra.")
    uploaded = st.file_uploader(
        "Cargar imagen",
        type=IMAGE_EXTENSIONS,
        key="image_upload",
        max_upload_size=settings["image_mb"],
    )
    st.caption(
        f"JPG/JPEG/JFIF · PNG · BMP · WebP · TIFF · GIF · AVIF. Límite actual: {settings['image_mb']} MB, 20 megapíxeles y 8192 px por lado."
    )
    st.caption(
        "HEIC/HEIF y RAW: convierta una copia a JPEG o PNG. No basta con cambiar la extensión."
    )
    if uploaded is None:
        st.info(
            "Seleccione una imagen para comenzar. Sin modelo podrá previsualizarla."
        )
        st.caption(
            "Recomendación: buena iluminación, trabajadores visibles y detalle suficiente en casco y chaleco."
        )
        return
    try:
        data = uploaded.getvalue()
        image = read_image(
            data,
            uploaded.name,
            getattr(uploaded, "type", None),
            max_bytes=settings["image_mb"] * 1024 * 1024,
        )
    except (MediaError, OSError) as exc:
        st.error(str(exc))
        return
    st.text(uploaded.name)
    if image.info.get("source_frames", 1) > 1:
        st.warning(
            f"Archivo con {image.info['source_frames']} imágenes: se utiliza solo la primera. Para secuencias temporales, use Videos."
        )
    signature = (
        sha256(data).hexdigest(),
        threshold,
        use_color,
        settings["imgsz"],
        (info or {}).get("sha256"),
        settings.get("company_id"),
        settings.get("site_id"),
    )
    original_col, result_col = st.columns(2)
    with original_col:
        st.image(
            image,
            caption="Imagen original · no es un resultado de inferencia",
            width="stretch",
        )
    if model is None:
        st.info(
            "Inferencia no disponible: no existe un modelo especializado autorizado y cargado. Puede previsualizar la imagen; no se ejecutó inferencia."
        )
    if st.button(
        "Analizar imagen", type="primary", disabled=model is None, key="analyze_image"
    ):
        try:
            from safeguard.vision import analyze_image

            with st.spinner("Procesando la imagen…"):
                result, annotated = analyze_image(
                    image,
                    model,
                    threshold,
                    use_color=use_color,
                    imgsz=settings["imgsz"],
                )
                output = png_bytes(annotated)
                st.session_state["image_result"] = {
                    "signature": signature,
                    "result": result,
                    "png": output,
                    "record": image_record(uploaded.name, result, info, threshold),
                    "persisted": False,
                }
        except Exception as exc:
            st.session_state.pop("image_result", None)
            st.error(
                f"No se completó la inferencia ({type(exc).__name__}). Puede revisar el modelo o probar otro archivo."
            )
    saved = st.session_state.get("image_result")
    if saved and saved["signature"] == signature:
        if not saved.get("persisted"):
            try:
                identifier, created = persist_record(
                    saved["record"], settings, signature[0]
                )
                saved["persisted"] = True
                saved["analysis_id"] = identifier
                st.success(
                    "Análisis guardado en SQLite."
                    if created
                    else "Este análisis ya estaba guardado; no se duplicó."
                )
            except (sqlite3.Error, OSError, ValueError) as exc:
                st.warning(
                    f"Resultado disponible, guardado pendiente ({type(exc).__name__}). Se reintentará al actualizar; puede descargar el PNG."
                )
        if saved.get("persisted"):
            st.caption("ID persistente: " + saved["analysis_id"])
            contextual_action(
                saved["analysis_id"], settings, key="image_result_copilot"
            )
        with result_col:
            st.subheader("Resultado de este análisis")
            if settings.get("show_boxes", True):
                st.image(
                    saved["png"],
                    caption="Imagen anotada · observaciones experimentales",
                    width="stretch",
                )
            else:
                st.image(
                    image,
                    caption="Cajas ocultas · el análisis y el PNG anotado se conservan",
                    width="stretch",
                )
        st.download_button(
            "Descargar PNG anotado",
            data=saved["png"],
            file_name="safeguard_observaciones.png",
            mime="image/png",
        )
        result_summary(saved["result"])
        st.subheader("Cobertura EPP de la escena")
        # This table combines counts and explicit unavailable states. Serialize only
        # the view, keeping numeric model results and export contracts unchanged.
        scene_rows = ppe_scene_rows(saved["result"], (info or {}).get("classes", []))
        st.dataframe(
            [{k: str(v) for k, v in row.items()} for row in scene_rows],
            width="stretch",
            hide_index=True,
        )
        st.caption(
            "Guantes, botas, gafas y clases no_* se muestran por escena; no tienen asociación individual validada. Las clases no_* son indicios para revisión."
        )
        render_people(saved["result"])
    else:
        with result_col:
            st.info(
                "La comparación y las métricas aparecerán aquí después del análisis."
            )


def contextual_action(identifier, settings, *, key):
    if st.button("Consultar este análisis con SafeBuild Copilot", key=key):
        from safeguard.copilot.selection import select_analysis

        try:
            select_analysis(st.session_state, settings, identifier)
            st.session_state["pending_navigation"] = "Copilot · Asistente"
            st.rerun()
        except (ValueError, OSError, sqlite3.Error):
            st.warning(
                "No se pudo autorizar el análisis. Compruebe empresa, obra y procedencia; los análisis nuevos usan Inferencia real."
            )


def video_page(model, info, threshold, use_color, settings):
    st.title("Exploración de video")
    st.write(
        "Inspeccione muestras del video y sus referencias originales. Sin seguimiento ni identidades persistentes."
    )
    st.caption(
        "1 · Cargue el video → 2 · Elija el número de muestras → 3 · Explore → 4 · Revise cada fotograma y exporte"
    )
    upload = st.file_uploader(
        "Cargar video",
        type=["mp4", "mov", "avi", "mkv"],
        key="video_upload",
        max_upload_size=settings["video_mb"],
    )
    count = st.slider("Máximo de fotogramas a explorar", 2, MAX_SAMPLES, 12)
    st.caption(
        f"Límite actual: {settings['video_mb']} MB, 6000 fotogramas y 120 s estimados. Hasta 60 muestras; el muestreo puede omitir situaciones breves."
    )
    if upload is None:
        st.info(
            "Seleccione un video. La compatibilidad de reproducción depende del contenedor, codec y navegador."
        )
        return
    data = upload.getvalue()
    try:
        ext = video_format(
            data,
            upload.name,
            getattr(upload, "type", None),
            max_bytes=settings["video_mb"] * 1024 * 1024,
        )
    except MediaError as exc:
        st.error(str(exc))
        return
    st.text(upload.name)
    if ext in (".mp4", ".mov"):
        st.video(data, format="video/mp4" if ext == ".mp4" else "video/quicktime")
        st.caption(
            "Video original. Si el navegador no reproduce su codec, pruebe la exploración de fotogramas."
        )
    else:
        st.info(
            "Este contenedor puede no reproducirse en el navegador. Se intentará decodificar sus fotogramas con OpenCV."
        )
    signature = (
        sha256(data).hexdigest(),
        count,
        threshold,
        use_color,
        settings["imgsz"],
        (info or {}).get("sha256"),
        settings.get("company_id"),
        settings.get("site_id"),
    )
    if model is None:
        st.info(
            "Exploración sin inferencia: se mostrarán fotogramas originales, sin detecciones ni análisis guardados."
        )
    label = (
        "Explorar y analizar fotogramas"
        if model is not None
        else "Explorar fotogramas sin inferencia"
    )
    if st.button(label, type="primary", key="explore_video"):
        try:
            analyzer = None
            if model is not None:
                from safeguard.vision import analyze_image

                analyzer = lambda image: analyze_image(
                    image,
                    model,
                    threshold,
                    use_color=use_color,
                    imgsz=settings["imgsz"],
                )
            with st.spinner("Decodificando muestras del video…"):
                progress = st.progress(0.0)
                try:
                    exploration = explore_video(
                        data,
                        upload.name,
                        getattr(upload, "type", None),
                        count=count,
                        analyzer=analyzer,
                        max_bytes=settings["video_mb"] * 1024 * 1024,
                        progress=progress.progress,
                    )
                finally:
                    progress.empty()
                st.session_state["video_result"] = {
                    "signature": signature,
                    "exploration": exploration,
                    "persisted": False,
                    "record": video_record(upload.name, exploration, info, threshold)
                    if exploration["inference_ran"]
                    else None,
                }
        except Exception as exc:
            st.session_state.pop("video_result", None)
            st.error(
                str(exc)
                if isinstance(exc, MediaError)
                else f"No se completó el video ({type(exc).__name__})."
            )
    saved = st.session_state.get("video_result")
    if saved and saved["signature"] == signature:
        exploration = saved["exploration"]
        if saved.get("record") and not saved["persisted"]:
            try:
                identifier, created = persist_record(
                    saved["record"], settings, signature[0]
                )
                saved["persisted"] = True
                st.success(
                    "Video guardado en SQLite."
                    if created
                    else "Video ya registrado, sin duplicar."
                )
            except (sqlite3.Error, OSError, ValueError) as exc:
                st.warning(f"Guardado de video pendiente ({type(exc).__name__}).")
        samples = exploration["samples"]
        st.subheader("Fotogramas explorados")
        st.write("Resolución decodificada:", exploration["resolution"])
        st.write(
            "FPS declarado por el decodificador:", exploration["fps"] or "No disponible"
        )
        st.write(
            "Duración estimada (s):",
            exploration["estimated_duration"]
            if exploration["estimated_duration"] is not None
            else "No disponible",
        )
        st.caption(
            f"Archivo: {len(data) / (1024 * 1024):.1f} MB · muestras distribuidas entre el primer y el último fotograma declarado."
        )
        st.caption(
            f"Modelo de este recorrido: {(info or {}).get('path', 'ninguno; solo exploración')} · dispositivo: CPU"
        )
        st.write(
            f"{len(samples)} muestras · {exploration['omitted']} fotogramas omitidos para evaluación · {exploration['total_frames']} declarados por el decodificador"
        )
        st.caption(
            "Todos se recorren para decodificar; solo las muestras se evalúan. Los índices comienzan en cero. Las referencias temporales no se certifican como exactas."
        )
        st.dataframe(
            [
                {
                    "Índice original": s["index"],
                    "Referencia (s)": s["seconds"],
                    "Origen del tiempo": s["time_kind"],
                    "Inferencia": s["result"] is not None,
                }
                for s in samples
            ],
            width="stretch",
        )
        evaluated = [s for s in samples if s["result"] is not None]
        if evaluated:
            cols = st.columns(4)
            cols[0].metric("Fotogramas evaluados", len(evaluated))
            cols[1].metric(
                "Máximo personas / muestra",
                max(s["result"]["stats"]["persons"] for s in evaluated),
            )
            cols[2].metric(
                "Promedio cascos / muestra",
                f"{sum(s['result']['stats']['helmets'] for s in evaluated) / len(evaluated):.1f}",
            )
            cols[3].metric(
                "Promedio chalecos / muestra",
                f"{sum(s['result']['stats']['vests'] for s in evaluated) / len(evaluated):.1f}",
            )
            st.caption(
                "Conteos descriptivos: no identifican trabajadores únicos ni acreditan cumplimiento."
            )
            try:
                st.plotly_chart(video_counts_chart(samples), width="stretch")
            except ImportError:
                st.caption(
                    "Gráfico no disponible; los datos siguen en la tabla y las observaciones."
                )
        chosen = st.selectbox(
            "Seleccionar fotograma",
            list(range(len(samples))),
            format_func=lambda i: f"Fotograma {samples[i]['index']}",
        )
        sample = samples[chosen]
        st.image(
            sample["original_png"],
            caption=f"Fotograma original {sample['index']}",
            width="stretch",
        )
        if sample["result"] is not None:
            if settings.get("show_boxes", True):
                st.image(
                    sample["annotated_png"],
                    caption="Observaciones de esta muestra",
                    width="stretch",
                )
            st.download_button(
                "Descargar PNG de este fotograma",
                data=sample["annotated_png"],
                file_name=f"safeguard_frame_{sample['index']}.png",
                mime="image/png",
            )
            result_summary(sample["result"])
            render_people(sample["result"])
        else:
            st.caption(
                "Sin inferencia en esta muestra. No hay cajas ni observaciones generadas."
            )


def history_page(history):
    st.title("Historial de sesión")
    st.write(
        "Análisis trazables para revisión. Los conteos de imágenes y promedios por muestra no se suman como trabajadores únicos."
    )
    st.caption(
        "Esta vista resume la sesión. Los registros con ID persistente también permanecen en SQLite; limpiar esta lista no los elimina."
    )
    if not history:
        st.info(
            "Todavía no hay análisis. Previsualizar un archivo no agrega resultados al historial."
        )
        return
    try:
        st.plotly_chart(state_chart(history), width="stretch")
    except ImportError:
        st.caption("Gráfico no disponible.")
    for index, record in reversed(list(enumerate(history, 1))):
        with st.expander(
            f"Análisis #{index} · {record.get('kind', 'imagen')} · {record['ts'].strftime('%Y-%m-%d %H:%M')}"
        ):
            st.text(record["file"])
            st.write(record["level"])
            st.write(
                "Personas:",
                record["stats"]["persons"],
                "Cascos:",
                record["stats"]["helmets"],
                "Chalecos:",
                record["stats"]["vests"],
            )
            st.caption(
                "Promedio por muestra"
                if record.get("kind") == "video"
                else "Detecciones por imagen"
            )
    rows = export_rows(history)
    visible = [
        "Fecha",
        "Hora",
        "Zona_horaria",
        "Archivo",
        "Tipo",
        "Estado",
        "Personas_modelo",
        "Cascos_modelo",
        "Chalecos_modelo",
        "Unidad",
        "Modelo",
    ]
    st.dataframe([{k: r[k] for k in visible} for r in rows], width="stretch")
    with st.expander("Trazabilidad completa"):
        st.dataframe(rows, width="stretch")
    st.download_button(
        "Descargar CSV",
        data=csv_bytes(history),
        file_name="safeguard_analisis.csv",
        mime="text/csv",
    )
    try:
        st.download_button(
            "Descargar Excel",
            data=excel_bytes(history),
            file_name="safeguard_analisis.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except (ImportError, ValueError) as exc:
        st.warning(f"Excel no disponible: {exc}. Puede utilizar CSV.")
    confirm = st.checkbox(
        "Confirmo que exporté lo necesario y deseo vaciar esta sesión",
        key="confirm_clear",
    )
    if st.button(
        "Limpiar historial de esta versión", disabled=not confirm, key="clear_history"
    ):
        st.session_state["history_v1a"] = []
        st.rerun()


def export_page(history):
    st.title("Exportar resultados")
    st.write("Descargue los análisis de la fuente seleccionada y su trazabilidad.")
    if not history:
        st.info(
            "Todavía no hay análisis para exportar. La previsualización no fabrica registros."
        )
        return
    session_summary(history, total_label="Análisis exportables")
    csv_col, excel_col = st.columns(2)
    with csv_col:
        with st.container(border=True):
            st.subheader("CSV · intercambio de datos")
            st.write("UTF-8, observaciones, parámetros y referencias de fotogramas.")
            st.download_button(
                "Descargar CSV",
                data=csv_bytes(history),
                file_name="safeguard_analisis.csv",
                mime="text/csv",
            )
    with excel_col:
        with st.container(border=True):
            st.subheader("Excel · revisión de análisis")
            st.write(
                "Tabla con filtros, encabezados y protección frente a fórmulas externas."
            )
            try:
                st.download_button(
                    "Descargar Excel",
                    data=excel_bytes(history),
                    file_name="safeguard_analisis.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            except (ImportError, ValueError) as exc:
                st.warning(f"Excel no disponible: {exc}. Utilice CSV.")
    st.subheader("Vista previa de la exportación")
    st.dataframe(export_rows(history), width="stretch")
    st.caption(
        "Cumplimiento: N/A. Los conteos de video son promedios por muestra. El PNG se descarga desde Imágenes o Videos."
    )


def system_page(model, info, errors):
    st.title("Sistema y modelo")
    render_model_summary(model, info, errors)
    st.subheader("Artefacto de inferencia")
    if info:
        st.json(info)
    else:
        st.write("Nombre y ubicación lógica: no disponible")
        st.write("Hash: no disponible · Clases declaradas: no disponibles")
    st.info(
        "La integración de pesos no certifica precisión local. Las métricas aportadas de Colab se documentan por separado; no se reprodujo aquí una evaluación independiente."
    )
    st.subheader("Entorno de ejecución")
    st.caption(
        f"Python {sys.version.split()[0]} · versiones consultadas en el intérprete que ejecuta la aplicación"
    )
    st.dataframe(
        [
            {"Dependencia": name, "Versión": version}
            for name, version in dependency_versions().items()
        ],
        width="stretch",
    )
    st.subheader("Alcance actual")
    st.write(
        "Imágenes y muestras de video; estados conservadores; SQLite local y sesión; exportaciones CSV, Excel y PNG."
    )
    st.caption(
        "Copilot recupera evidencias locales y ofrece generación Groq opcional bajo consentimiento. Sin tracking ni certificación normativa. SQLite local no incorpora autenticación empresarial."
    )


def main():
    if "pending_navigation" in st.session_state:
        st.session_state["navigation"] = st.session_state.pop("pending_navigation")
    st.set_page_config(
        page_title="SafeBuild AI | Sistema Inteligente de Detección de EPP",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.session_state.setdefault("history_v1a", [])
    ui.apply_theme(st)
    with st.sidebar:
        ui.brand(st)
        ui.side_heading("Contexto de trabajo", "layers", st)
        context = {
            "db_path": None,
            "company_id": None,
            "site_id": None,
            "origin": "real_inference",
        }
        try:
            db_path = storage.database_path(ROOT)
            if not db_path.exists():
                storage.initialize(db_path)
            else:
                storage.validate_schema(db_path)
            company_rows = storage.companies(db_path)
            company = st.selectbox(
                "Empresa",
                [r["id"] for r in company_rows],
                format_func=lambda value: next(
                    r["name"] for r in company_rows if r["id"] == value
                ),
                key="company",
            )
            site_rows = storage.sites(db_path, company)
            if not site_rows:
                raise ValueError("La empresa no tiene obras disponibles.")
            if st.session_state.get("site") not in [r["id"] for r in site_rows]:
                st.session_state["site"] = site_rows[0]["id"]
            site = st.selectbox(
                "Obra",
                [r["id"] for r in site_rows],
                format_func=lambda value: next(
                    r["name"] + " · " + value for r in site_rows if r["id"] == value
                ),
                key="site",
            )
            origin = st.selectbox(
                "Procedencia a consultar",
                list(storage.ORIGINS),
                format_func=lambda value: {
                    "real_inference": "Inferencia real",
                    "experimental": "Pruebas experimentales",
                    "synthetic": "Datos sintéticos",
                }[value],
            )
            context.update(
                db_path=db_path, company_id=company, site_id=site, origin=origin
            )
        except (sqlite3.Error, OSError, ValueError) as exc:
            st.warning(
                f"SQLite no disponible ({type(exc).__name__}). Puede explorar medios; el guardado está bloqueado."
            )
        controls_slot = st.container()
        copilot_settings = st.expander("Configuración de Copilot")
        from safeguard.copilot.selection import invalidate_changed_scope

        if invalidate_changed_scope(st.session_state, context):
            st.info("Selección de análisis invalidada por cambio de contexto.")
        st.divider()
        ui.side_heading("Navegación", "layers", st)
        page = st.radio(
            "Navegación",
            PAGES,
            key="navigation",
            format_func=lambda value: ui.NAV_LABELS.get(value, value),
            label_visibility="collapsed",
        )
        if not page.startswith("Copilot ·"):
            copilot_settings.caption(
                "Abrí Copilot · Asistente o Copilot · Conocimiento para ajustar sus fuentes, filtros y opciones aquí."
            )
        if page.startswith("Copilot ·"):
            # Local single-user resource policy: never keep YOLO while querying embeddings.
            if st.session_state.get("model_requested", False):
                load_model.clear()
                st.session_state["model_requested"] = False
        else:
            from safeguard.rag.ui import release_resources
            from safeguard.copilot.ui import release_resources as release_copilot

            release_resources()
            release_copilot()
        ui.crane(st)
        with controls_slot.expander("Controles de análisis y recursos"):
            st.divider()
            st.subheader("Análisis visual")
            threshold = st.slider(
                "Confianza mínima",
                0.1,
                0.95,
                0.4,
                0.05,
                help="Puntuación mínima del modelo para aceptar una detección; no es una probabilidad calibrada.",
            )
            show_boxes = st.checkbox("Mostrar bounding boxes", True, key="show_boxes")
            use_color = st.checkbox("Incluir indicios de color experimentales", False)
            st.caption("El color no acredita un elemento de protección.")
            st.divider()
            with st.expander("Recursos · CPU / 16 GB"):
                imgsz = st.selectbox(
                    "Resolución de inferencia", [320, 480, 640], index=1
                )
                st.selectbox("Dispositivo", ["cpu"])
                image_mb = st.selectbox("Límite de imagen (MB)", [5, 10, 20], index=1)
                video_mb = st.selectbox("Límite de video (MB)", [25, 50, 100], index=1)
                st.caption(
                    "Un modelo a la vez; hasta 60 muestras, sin conservar todos los frames. El límite temporal no interrumpe llamadas nativas bloqueadas."
                )
            settings = dict(
                context,
                imgsz=imgsz,
                image_mb=image_mb,
                video_mb=video_mb,
                show_boxes=show_boxes,
            )
            if st.button(
                "Cargar modelo autorizado", key="load_model"
            ) and not page.startswith("Copilot ·"):
                st.session_state["model_requested"] = True
            if st.session_state.get("model_requested", False):
                with st.spinner("Comprobando artefacto local…"):
                    model, info, errors = load_model()
            else:
                model, info, errors = (
                    None,
                    None,
                    ["Carga bajo demanda. No se inicializó ningún modelo."],
                )
            st.write(
                "Modelo: disponible"
                if model is not None
                else "Modelo: sin cargar o no disponible"
            )
            if info:
                st.caption(
                    f"Artefacto: {info['path']} · clases declaradas: {len(info.get('classes', []))}"
                )
            if st.button("Volver a comprobar modelo", key="reload_model"):
                load_model.clear()
                st.session_state["model_requested"] = True
                st.rerun()
            if st.button("Liberar modelo y vistas de medios", key="release_resources"):
                load_model.clear()
                st.session_state["model_requested"] = False
                st.session_state.pop("image_result", None)
                st.session_state.pop("video_result", None)
                st.rerun()
            with st.expander("Cómo usar"):
                st.write("1. Suba una foto o video.")
                st.write("2. Ajuste confianza y cajas.")
                st.write("3. Analice con un modelo autorizado.")
                st.write("4. Revise observaciones y métricas.")
                st.write("5. Exporte CSV, Excel o PNG.")
            st.caption("Color: indicio experimental, no confirmación de EPP.")
        st.caption(
            "TechCorp y obras ficticias · inferencias separadas por procedencia."
        )
        st.caption("SafeBuild AI · IFTS 33 · Grupo 5")
        if st.session_state.get("model_requested", False) and model is None:
            st.warning("Modelo no disponible · inferencia deshabilitada")
    header(page, info)
    if page not in ("Inicio", "Dashboard"):
        st.caption(
            "Contexto activo · Empresa: "
            + str(context["company_id"] or "No disponible")
            + " · Obra: "
            + str(context["site_id"] or "No disponible")
            + " · Procedencia: "
            + {
                "real_inference": "Inferencia real",
                "experimental": "Pruebas experimentales",
                "synthetic": "Datos sintéticos",
            }.get(context["origin"], context["origin"])
        )
    if page == "Inicio":
        ui.home(settings, st)
    elif page == "Dashboard":
        from safeguard.ui.dashboard import render

        render(settings, st)
    elif page == "Resumen":
        persisted_dashboard(settings)
        dashboard(st.session_state["history_v1a"], model, info, errors)
    elif page == "Imágenes":
        image_page(model, info, threshold, use_color, settings)
    elif page == "Videos":
        video_page(model, info, threshold, use_color, settings)
    elif page == "Historial":
        persisted_history(settings)
        history_page(st.session_state["history_v1a"])
    elif page == "Exportar":
        source = st.selectbox(
            "Fuente de exportación", ["SQLite de la obra", "Sesión temporal"]
        )
        export_page(
            persisted_history(settings)
            if source == "SQLite de la obra"
            else st.session_state["history_v1a"]
        )
    elif page == "Ayuda":
        help_page()
    elif page == "Copilot · Asistente":
        from safeguard.copilot.ui import render

        render(ROOT, settings, configuration=copilot_settings)
    elif page == "Copilot · Conocimiento":
        from safeguard.rag.ui import render

        render(ROOT, configuration=copilot_settings)
    else:
        system_page(model, info, errors)
    st.divider()
    with st.expander("Resumen de la sesión"):
        session_summary(st.session_state["history_v1a"])
    st.caption(
        "SafeBuild AI · Una observación visual no certifica seguridad ni cumplimiento legal. La ausencia de detección no confirma ausencia de EPP."
    )


if __name__ == "__main__":
    main()
