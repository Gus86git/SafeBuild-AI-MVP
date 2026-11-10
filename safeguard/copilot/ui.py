"""Session-only conversational UI; network generation requires an explicit click."""

from datetime import date
import os
import hashlib
import json
import sqlite3
from uuid import uuid4
import streamlit as st
from .operational import OperationalQueryService
from .service import DocumentRetriever, gather
from .generation import AnswerGenerator, external_package
from .selection import selected_id, select_analysis, clear_selection
from .audio_ui import render_composer, render_player
from .voice import accept_event, SpeechTranscriber, readable_answer, ERRORS
from safeguard.rag.indexing import rag_path, load_snapshot
from safeguard.rag.hybrid_retriever import Retriever
from safeguard.rag.citations import citation

EXAMPLES = [
    "¿Cómo establece TechCorp que deben revisarse las observaciones generadas por inteligencia artificial?",
    "¿Cuántas observaciones están registradas en Torre Norte?",
    "¿Qué observaciones de EPP tenemos registradas en Torre Norte y qué procedimiento interno corresponde consultar?",
    "¿Cuál es el número de una infracción legal confirmada por una inspección oficial?",
]

CONTEXT_EXAMPLES = [
    "¿Qué detectó SafeBuild AI en esta fotografía?",
    "¿Qué cascos, chalecos y otros EPP se observaron?",
    "¿Qué resultados necesitan revisión humana?",
    "¿Cómo indica TechCorp que se deben revisar las observaciones generadas por IA?",
    "Explicame las observaciones de este análisis y qué procedimiento de TechCorp corresponde consultar.",
    "¿Qué infracción legal fue confirmada en esta fotografía?",
]


def display_analysis(data):
    analysis = data["selected_analysis"]
    st.subheader("Análisis seleccionado")
    st.text("ID: " + analysis["id"])
    st.caption(
        "Obra: " + data["context"]["site_name"] + " · Fecha: " + analysis["created_utc"]
    )
    st.text(
        "Procedencia de ejecución: "
        + analysis["origin"]
        + " · Procedencia del medio: "
        + analysis["input_origin"]
    )
    st.caption(
        "Inferencia real describe el cálculo del modelo; no confirma que la imagen o el incidente sean reales."
    )
    st.write(
        "Estado registrado: "
        + analysis["state"]
        + " · Revisión: "
        + analysis["review_status"]
    )
    a, b, c = st.columns(3)
    a.metric("Análisis seleccionado", data["facts"]["analyses"])
    b.metric("Cajas detectadas", sum(r["count"] for r in data["detection_categories"]))
    c.metric("Observaciones por persona/frame", data["facts"]["observations"])
    st.write("Detecciones por clase; no trabajadores únicos ni EPP obligatorios")
    st.dataframe(data["detection_categories"], width="stretch")
    st.write("Observaciones, asociaciones y motivos de revisión")
    st.dataframe(analysis["people"], width="stretch")
    st.caption(
        "Casco/chaleco: asociaciones experimentales por ID. Guantes, botas, gafas y clases no_*: solo escena, sin asociación individual validada. Falta de asociación no confirma ausencia."
    )
    with st.expander("Modelo, configuración y detecciones registradas"):
        st.text("SHA-256 del modelo local: " + analysis["model_sha256"])
        st.json(analysis["configuration"])
        st.dataframe(analysis["detections"], width="stretch")
    st.caption(
        "Detalle limitado a 200 filas por tabla. IDs efímeros; no reconocimiento de personas."
    )


def release_resources():
    retriever = st.session_state.pop("copilot_retriever", None)
    if retriever:
        retriever.release()


def display(package):
    kinds = {
        "documentary": "Documentos",
        "operational": "Registros de la obra",
        "combined": "Registros y documentos",
        "ambiguous": "Pregunta por aclarar",
        "insufficient": "Fuera del alcance verificable",
    }
    states = {
        "grounded": "Evidencias recuperadas",
        "partial": "Evidencias parciales",
        "insufficient": "Evidencia insuficiente",
    }
    st.caption(
        "Tipo: "
        + kinds.get(package["routing"]["kind"], package["routing"]["kind"])
        + " · Evidencia: "
        + states.get(package["status"], package["status"])
        + f" · Consulta local: {package['latency_seconds']:.3f} s"
    )
    for warning in package["warnings"]:
        st.warning(warning)
    sql = package["sql"]
    if sql:
        st.markdown("**Dato registrado en SQLite**")
        if sql.get("selected_analysis"):
            display_analysis(sql)
        else:
            st.text("Obra: " + sql["context"]["site_name"])
            a, b = st.columns(2)
            a.metric("Análisis registrados", sql["facts"]["analyses"])
            b.metric("Observaciones registradas", sql["facts"]["observations"])
        with st.expander("Desglose, revisión y referencias autorizadas"):
            st.write("Detecciones por clase y origen (no incumplimientos)")
            st.dataframe(sql["detection_categories"])
            st.write("Observaciones por estado de revisión")
            st.dataframe(sql["observation_states"])
            st.write("Asociaciones visuales")
            st.json(sql["associations"])
            st.write("Análisis recientes")
            st.dataframe(sql["recent"])
            st.write("Referencias hash; no se abren archivos")
            st.dataframe(sql["evidence_refs"])
        for warning in sql["limitations"]:
            st.caption(warning)
    if package["documents"]:
        st.markdown("**Fragmento documental recuperado**")
        for chunk in package["documents"]:
            with st.expander(
                (
                    "Simulación académica · "
                    if chunk.get("is_synthetic")
                    else "Fuente pendiente de validación · "
                )
                + chunk["title"]
            ):
                st.text(citation(chunk))
                st.text("DOC:" + chunk["chunk_id"])
                st.text(chunk["text"])
    elif package["routing"]["kind"] in ("documentary", "combined"):
        st.info(
            "No se recuperaron fragmentos suficientes. Reformule o consulte el explorador documental."
        )
    generated = package.get("generation")
    if generated:
        st.markdown("**Explicación generada por IA**")
        if generated["state"] == "validated_format":
            answer = generated["answer"]
            st.caption(
                "Formato y referencias comprobados; interpretación semántica pendiente de revisión humana. Estado: "
                + answer["status"]
            )
            st.text(answer["text"])
            st.json(
                {
                    "Fuentes citadas": answer["source_ids"],
                    "Cifras verificadas por SQL": answer["verified_facts"],
                }
            )
            for warning in answer["warnings"]:
                st.text(warning)
        else:
            st.warning(
                "Generación no disponible o no validada: "
                + generated["state"]
                + ". Se conservan las evidencias verificadas."
            )
            if generated.get("validation_reason"):
                st.caption("Control de validación: " + generated["validation_reason"])
            if generated.get("http_status"):
                st.caption("Código HTTP: " + str(generated["http_status"]))


def groq_key():
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        try:
            key = st.secrets.get("GROQ_API_KEY")
        except Exception:
            pass
    return key


def reset_voice():
    for name in (
        "voice_pending",
        "voice_handled",
        "voice_draft",
        "voice_error",
        "voice_consent",
    ):
        st.session_state.pop(name, None)
    st.session_state["voice_conversation"] = str(uuid4())


def render(root, context, configuration=None):
    if configuration is None:
        configuration = st.sidebar.expander("Configuración de Copilot")
    from safeguard.ui.presentation import heading

    heading(
        "SafeBuild Copilot",
        "Consultas inteligentes · RAG + SQLite + IA opcional",
        "people",
        st,
    )
    st.caption(
        "TechCorp y procedimientos ficticios · observaciones sin certificación · generación normativa deshabilitada."
    )
    identifier = selected_id(st.session_state, context)
    operational = OperationalQueryService(context["db_path"])
    selected = None
    try:
        if identifier:
            selected = operational.analysis(
                identifier, context["company_id"], context["site_id"], context["origin"]
            )
        choices = operational.list_analyses(
            context["company_id"], context["site_id"], context["origin"]
        )
    except (ValueError, OSError, sqlite3.Error, TypeError):
        clear_selection(st.session_state)
        identifier = None
        choices = []
        st.warning(
            "No se pudo verificar el análisis seleccionado o consultar SQLite. No se conserva un contexto sin verificar."
        )
    with configuration:
        with st.expander("Elegir un análisis existente de esta obra", expanded=False):
            by_id = {row["id"]: row for row in choices}
            options = [None] + list(by_id)
            if identifier and identifier not in options:
                options.append(identifier)
            if st.session_state.get("copilot_choice_seed") != identifier:
                st.session_state["copilot_analysis_choice"] = identifier
                st.session_state["copilot_choice_seed"] = identifier
            choice = st.selectbox(
                "Análisis de imagen (hasta 50 recientes)",
                options,
                format_func=lambda value: "Sin selección"
                if value is None
                else value
                + " · "
                + by_id.get(value, {}).get("created_utc", "seleccionado"),
                key="copilot_analysis_choice",
            )
            if st.button(
                "Seleccionar análisis",
                key="copilot_select_analysis",
                disabled=choice is None,
            ):
                try:
                    select_analysis(st.session_state, context, choice)
                    st.rerun()
                except (ValueError, OSError, sqlite3.Error):
                    st.warning(
                        "El análisis no está disponible en el contexto autorizado."
                    )
    if selected:
        st.caption("Análisis seleccionado: " + identifier)
        with st.expander("Contexto del análisis seleccionado", expanded=False):
            display_analysis(selected)
        st.info(
            "Las preguntas contextuales consultan únicamente este análisis, no el total de la obra."
        )
        if st.button("Volver al análisis de imagen", key="copilot_back_image"):
            st.session_state["pending_navigation"] = "Imágenes"
            st.rerun()
        if configuration.button(
            "Quitar análisis y consultar la obra", key="copilot_clear_selection"
        ):
            clear_selection(st.session_state)
            st.rerun()
    identity = tuple(
        str(context.get(k)) for k in ("db_path", "company_id", "site_id", "origin")
    ) + (identifier,)
    if st.session_state.get("copilot_scope") != identity:
        st.session_state["copilot_history"] = []
        st.session_state["copilot_scope"] = identity
        reset_voice()
    history = st.session_state.setdefault("copilot_history", [])
    with configuration:
        if st.button("Limpiar conversación", key="copilot_clear"):
            history.clear()
            reset_voice()
            st.rerun()
    conversation = st.session_state.setdefault("voice_conversation", str(uuid4()))
    voice_scope = hashlib.sha256(repr((identity, conversation)).encode()).hexdigest()
    key = groq_key()
    with configuration:
        with st.expander("Privacidad de voz y permisos"):
            st.caption(
                "Al grabar, el audio se envía desde el servidor a GroqCloud para transcribirlo en español. Máximo 30 segundos; no se guarda en disco. El permiso solo vale para esta conversación y contexto. Las preguntas transcritas se consultan localmente; generar explicaciones externas conserva su autorización por paquete."
            )
            consent = st.checkbox(
                "Autorizo el micrófono y el envío de mis grabaciones a GroqCloud para transcripción en este contexto.",
                key="voice_consent",
            )
            st.caption(
                "La lectura utiliza voces españolas locales del navegador; no envía documentos a un servicio de voz. Podés revocar el permiso desmarcando esta casilla."
            )
            st.caption(
                "Groq STT: clave configurada; prueba real pendiente."
                if key
                else "Groq STT: sin clave configurada; podés escribir."
            )
    if not consent and st.session_state.get("voice_pending", {}).get("mode") == "voice":
        st.session_state.pop("voice_pending", None)
    docs = None
    try:
        path = rag_path(root)
        snapshot = load_snapshot(path)
        signature = (str(path), snapshot["corpus_hash"])
        if (
            st.session_state.get("copilot_index") != signature
            or "copilot_retriever" not in st.session_state
        ):
            release_resources()
            st.session_state["copilot_retriever"] = Retriever(snapshot, path, root)
            st.session_state["copilot_index"] = signature
        docs = DocumentRetriever(st.session_state["copilot_retriever"])
    except Exception:
        st.info("Corpus no disponible. Las consultas SQLite siguen habilitadas.")
    with configuration:
        with st.expander("Fuentes y período de consulta"):
            method = st.selectbox(
                "Recuperación del asistente",
                ["BM25", "Semántica con ChromaDB", "Híbrida"],
                key="copilot_method",
            )
            filter_dates = st.checkbox(
                "Filtrar intervalo de fechas",
                key="copilot_dates",
                disabled=identifier is not None,
            )
            start = end = None
            if filter_dates and identifier is None:
                start = st.date_input(
                    "Desde (Buenos Aires)", date.today(), key="copilot_start"
                )
                end = st.date_input(
                    "Hasta inclusive (Buenos Aires)", date.today(), key="copilot_end"
                )
            st.caption(
                "La consulta usa la empresa, obra y procedencia del panel lateral. Las fechas se eligen aquí; no se interpretan automáticamente del texto."
            )
        with st.expander("Preguntas sugeridas", expanded=False):
            example = st.selectbox(
                "Ejemplo",
                CONTEXT_EXAMPLES if identifier else EXAMPLES,
                key="copilot_example",
            )
            if st.button("Usar ejemplo", key="copilot_use_example"):
                st.session_state["voice_draft"] = example
    st.caption(
        "Ajustes y sugerencias en Configuración de Copilot, en la barra lateral. Método: "
        + method
        + (
            " · intervalo de fechas activo"
            if filter_dates and identifier is None
            else ""
        )
    )
    if not history:
        st.info(
            "Escriba una pregunta o use una sugerencia. Primero verá registros y fuentes; el envío a Groq requiere una autorización separada."
        )
    for item in history:
        item.setdefault("message_id", str(uuid4()))
        item.setdefault("input_mode", "text")
        with st.chat_message("user"):
            st.caption(
                "Pregunta por voz"
                if item["input_mode"] == "voice"
                else "Pregunta escrita"
            )
            st.text(item["question"])
        with st.chat_message("assistant"):
            response = readable_answer(item)
            st.markdown("**Respuesta de SafeBuild**")
            st.text(response)
            render_player(response, item["message_id"], item["input_mode"], voice_scope)
            with st.expander("Fuentes documentales y registros verificables"):
                display(item)
    pending = st.session_state.get("voice_pending")
    if pending and pending.get("scope") != voice_scope:
        st.session_state.pop("voice_pending", None)
        pending = None
    if pending and pending.get("question"):
        with st.chat_message("user"):
            st.caption(
                "Pregunta por voz" if pending["mode"] == "voice" else "Pregunta escrita"
            )
            st.text(pending["question"])
    with st.container(key="copilot_input_bar"):
        event = render_composer(
            voice_scope,
            consent=consent,
            has_key=bool(key),
            phase=pending["phase"] if pending else None,
            draft=st.session_state.get("voice_draft", ""),
            error=st.session_state.get("voice_error", ""),
        )
    if event:
        try:
            accepted = accept_event(
                st.session_state, event, voice_scope, consent=consent
            )
            if accepted:
                st.session_state["voice_pending"] = accepted
                st.session_state.pop("voice_draft", None)
                st.session_state.pop("voice_error", None)
                st.rerun()
        except ValueError as exc:
            st.session_state["voice_error"] = ERRORS.get(
                str(exc), "No se pudo procesar el envío."
            )
            st.rerun()
    if pending:
        if pending["phase"] == "TRANSCRIBING":
            with st.spinner("Transcribiendo audio en español…"):
                transcription = SpeechTranscriber(key).transcribe(
                    pending.pop("audio", b""), authorized=consent
                )
            if transcription["state"] == "transcribed":
                pending.update(
                    question=transcription["text"],
                    phase="PROCESSING",
                    stt_latency_seconds=transcription.get("latency_seconds"),
                )
            else:
                st.session_state.pop("voice_pending", None)
                st.session_state["voice_error"] = ERRORS.get(
                    transcription["state"], "No se pudo transcribir el audio."
                )
            st.rerun()
        if pending["phase"] == "PROCESSING":
            # Remove before querying so unexpected reruns cannot repeat this event.
            st.session_state.pop("voice_pending", None)
            try:
                with st.spinner("Consultando registros y fragmentos locales…"):
                    result = gather(
                        pending["question"],
                        context,
                        operational,
                        docs,
                        method,
                        start,
                        end,
                        analysis_id=identifier,
                    )
                result.update(
                    message_id=pending["id"],
                    input_mode=pending["mode"],
                    stt_latency_seconds=pending.get("stt_latency_seconds"),
                )
                history.append(result)
                del history[:-8]
            except (ValueError, sqlite3.Error, OSError):
                st.session_state["voice_error"] = (
                    "No se pudo completar la consulta. Revisá la pregunta, las fechas y el contexto."
                )
            st.rerun()
    with configuration:
        with st.expander("Explicación opcional · Groq"):
            render_generation(history, key)


def render_generation(history, key):
    st.caption(
        "Las consultas locales no envían datos a este proveedor. Revise el paquete antes de autorizar cada generación."
    )
    st.caption(
        "Groq: clave configurada (conexión sin comprobar)."
        if key
        else "Groq: sin clave. Evidencias locales disponibles."
    )
    model = st.text_input(
        "Modelo Groq (se valida al solicitar generación)",
        value=os.environ.get("GROQ_MODEL", ""),
        key="copilot_model",
    )
    if history:
        latest = history[-1]
        gate = st.session_state.get("copilot_groq_gate", {})
        gate_verified = (
            gate.get("model") == model
            and gate.get("corpus_hash")
            == st.session_state.get("copilot_index", (None, None))[1]
        )
        if latest.get("analysis_id") and not gate_verified:
            st.info(
                "Generación contextual pendiente del Gate 1: primero debe aprobarse una prueba real, con consentimiento, sobre un procedimiento ficticio sin análisis seleccionado. Las evidencias locales siguen disponibles."
            )
            return
        try:
            payload = external_package(latest, authorized=True)
        except ValueError:
            st.info(
                "Esta consulta no admite generación externa. Puede revisar las evidencias locales."
            )
            return
        with st.expander("Revisar exactamente qué se enviaría a GroqCloud"):
            st.json(payload)
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()
        consent = st.checkbox(
            "Autorizar el envío de esta pregunta y este paquete a GroqCloud; confirmé que no contienen datos personales ni información privada no autorizada.",
            key="copilot_consent_" + fingerprint,
        )
        if st.button(
            "Generar explicación con Groq",
            key="copilot_generate",
            disabled=not (consent and key and model.strip()),
        ):
            with st.spinner(
                "Esperando la respuesta del proveedor y verificando sus referencias…"
            ):
                latest["generation"] = AnswerGenerator(key, model).generate(
                    latest, authorized=consent, contextual_gate_verified=gate_verified
                )
            if (
                latest["generation"]["state"] == "validated_format"
                and latest["routing"]["kind"] == "documentary"
                and latest["generation"]["answer"]["status"] in ("grounded", "partial")
                and not latest.get("analysis_id")
                and latest["documents"]
                and not latest["sql"]
            ):
                st.session_state["copilot_groq_gate"] = {
                    "model": model,
                    "corpus_hash": st.session_state.get("copilot_index", (None, None))[
                        1
                    ],
                    "latency_seconds": latest["generation"]["latency_seconds"],
                    "status": latest["generation"]["answer"]["status"],
                }
            st.rerun()
