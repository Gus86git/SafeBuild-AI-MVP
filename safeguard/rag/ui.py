"""Streamlit presentation for evidence retrieval; document text is always inert."""

from pathlib import Path
import gc
import re
import json
import streamlit as st
from .indexing import load_snapshot, rag_path
from .hybrid_retriever import Retriever
from .citations import citation, safe_url, LABELS

EXAMPLES = [
    "¿Qué establece la normativa sobre los elementos de protección personal?",
    "¿Qué obligaciones existen para registrar la entrega de elementos de protección personal?",
    "¿Qué medidas preventivas se contemplan para trabajos en altura?",
    "¿Cómo gestiona TechCorp una observación visual pendiente de revisión?",
    "¿Qué procedimiento tiene TechCorp para comunicar una emergencia?",
]
CONTENT_LABELS = {
    "partial_publication_description_only": "Parcial: presentación de la publicación",
    "supplied_transcription_completeness_unverified": "Copia aportada; completitud pendiente de revisión",
    "academic_simulation": "Simulación académica",
}


def release_resources():
    retriever = st.session_state.pop("rag_retriever", None)
    if retriever:
        retriever.release()
    gc.collect()


def render(root, configuration=None):
    if configuration is None:
        configuration = st.sidebar.expander("Configuración de Copilot")
    st.subheader("SafeBuild Copilot — Base de conocimiento")
    st.caption(
        "Consultá documentos y revisá sus fuentes. Esta etapa recupera fragmentos: no genera respuestas conversacionales ni consulta eventos de SQLite."
    )
    rag_root = rag_path(root)
    try:
        snapshot = load_snapshot(rag_root)
    except Exception as exc:
        st.warning(str(exc))
        st.code(
            ".\\.venv\\Scripts\\python.exe scripts/build_rag_index.py",
            language="powershell",
        )
        return
    documents = snapshot["documents"]
    indexed = [d for d in documents if d["ingestion_status"] == "indexed"]
    with configuration:
        st.markdown("**Búsqueda documental**")
        method = st.selectbox(
            "Método", ["BM25", "Semántica con ChromaDB", "Híbrida"], key="rag_method"
        )
        sources = st.multiselect(
            "Fuentes",
            list(LABELS),
            default=list(LABELS),
            format_func=lambda s: LABELS[s],
            key="rag_sources",
        )
        top_k = st.number_input(
            "Resultados", min_value=1, max_value=10, value=5, key="rag_top_k"
        )
    with configuration:
        with st.expander("Estado del corpus y documentos"):
            values = [
                len(indexed),
                len(snapshot["chunks"]),
                sum(d["source_type"] == "official" for d in indexed),
                sum(d["is_synthetic"] for d in indexed),
            ]
            for col, label, value in zip(
                st.columns(2) * 2,
                [
                    "Documentos cargados",
                    "Fragmentos",
                    "Copias normativas",
                    "Documentos ficticios",
                ],
                values,
            ):
                col.metric(label, value)
            descriptor = snapshot.get("vector")
            st.caption(
                "BM25: índice léxico preparado. ChromaDB: "
                + (
                    "índice persistente preparado; se comprueba al consultar."
                    if descriptor
                    else "sin preparar; puede usar BM25."
                )
            )
            st.caption(
                "Embeddings: "
                + (
                    descriptor["model"]["model_id"]
                    + " · revisión "
                    + descriptor["model"]["revision"][:12]
                    if descriptor
                    else "no disponibles en este índice"
                )
            )
            st.warning(
                "Las fuentes normativas son copias aportadas: vigencia, anexos y completitud requieren revisión. Los Word se citan por párrafo, sin páginas inventadas."
            )
            if any(
                d.get("content_status") == "partial_publication_description_only"
                for d in indexed
            ):
                st.caption(
                    "El documento OIT disponible contiene la presentación de la publicación, no la guía completa."
                )
            with st.expander("Explorador documental y procedencia"):
                st.dataframe(
                    [
                        {
                            "Documento": d["title"],
                            "Tipo": LABELS[d["source_type"]],
                            "Versión": d.get("document_version"),
                            "Páginas PDF": d.get("page_count"),
                            "Estado": {
                                "indexed": "Indexado",
                                "error": "Error de ingesta",
                                "duplicate_excluded": "Duplicado excluido",
                            }.get(d["ingestion_status"], d["ingestion_status"]),
                            "Contenido": CONTENT_LABELS.get(
                                d.get("content_status"), "Estado no verificado"
                            ),
                            "Advertencias": "; ".join(d.get("warnings", [])),
                            "Error": d.get("error", ""),
                        }
                        for d in documents
                    ],
                    width="stretch",
                )
                st.download_button(
                    "Descargar catálogo JSON",
                    json.dumps(documents, ensure_ascii=False, indent=2),
                    file_name="catalogo_safeguard.json",
                    mime="application/json",
                )
        with st.expander("Preguntas de ejemplo"):
            example = st.selectbox("Elegí una pregunta", EXAMPLES, key="rag_example")
            if st.button("Usar pregunta de ejemplo"):
                st.session_state["rag_question"] = example
    st.subheader("Consultar fuentes")
    st.caption(
        "Configuración activa: "
        + method
        + " · "
        + str(len(sources))
        + " tipos de fuente · hasta "
        + str(top_k)
        + " fragmentos. Ajustes en la barra lateral."
    )
    question = st.text_input(
        "Pregunta documental",
        key="rag_question",
        max_chars=1000,
        placeholder="Por ejemplo: ¿cómo se registra la entrega de EPP?",
    )
    st.caption(
        "Seleccione fuentes → formule la pregunta → revise fragmentos y citas. BM25 no necesita cargar embeddings."
    )
    identity = (
        str(rag_root),
        snapshot["corpus_hash"],
        descriptor["collection"] if descriptor else None,
    )
    old = st.session_state.get("rag_retriever")
    if old is None or st.session_state.get("rag_identity") != identity:
        release_resources()
        try:
            st.session_state["rag_retriever"] = Retriever(
                snapshot, rag_root, Path(root)
            )
            st.session_state["rag_identity"] = identity
        except Exception as exc:
            st.error(
                f"BM25 no disponible ({type(exc).__name__}). Instale requirements-rag.txt."
            )
            return
    signature = (question, method, tuple(sources), top_k, identity)
    if st.button("Buscar evidencia", type="primary", key="rag_search"):
        if not question.strip():
            st.info("Escribí una pregunta para recuperar fragmentos.")
        elif not sources:
            st.info("Seleccioná al menos una fuente documental.")
        else:
            with st.spinner("Recuperando evidencia local…"):
                try:
                    result = st.session_state["rag_retriever"].search(
                        question, method, top_k, sources
                    )
                    st.session_state["rag_result"] = (signature, result)
                except Exception as exc:
                    st.error(
                        f"No se pudo completar la búsqueda ({type(exc).__name__})."
                    )
    saved = st.session_state.get("rag_result")
    if saved and saved[0] == signature:
        result = saved[1]
        if result["warning"]:
            st.warning(result["warning"])
        if result.get("scope_note"):
            st.caption(result["scope_note"])
        st.caption(
            f"Método efectivo: {result['method']} · {result['latency_seconds']:.3f} s · {result['evidence_status']}"
        )
        if not result["results"]:
            st.info(
                "No se encontró evidencia suficiente con estos criterios. Revisá la pregunta, los filtros o la disponibilidad del índice."
            )
        else:
            st.info(
                "Son fragmentos candidatos, no una respuesta validada. El ranking no garantiza pertinencia; los puntajes no son probabilidades de corrección."
            )
        for rank, item in enumerate(result["results"], 1):
            chunk = item["chunk"]
            label = re.sub(
                r"([\\`*_{}\[\]()#+.!<>|])",
                r"\\\1",
                f"{rank}. {chunk['title']} · {chunk['locator']}",
            )
            with st.expander(label, expanded=rank == 1):
                st.text(LABELS[chunk["source_type"]])
                st.caption(f"{item['method']} · puntuación {item['score']:.5f}")
                st.text(chunk["text"])
                st.text(citation(chunk))
                url = safe_url(chunk)
                if url:
                    st.link_button("Abrir fuente oficial verificada", url)
                st.caption(
                    "Contenido: "
                    + CONTENT_LABELS.get(
                        chunk.get("content_status"), "Estado no verificado"
                    )
                )
    with configuration:
        with st.expander("Preparación e incorporación controlada"):
            st.write(
                "La ingesta es un proceso local separado: agregar archivo autorizado al corpus, revisar su ficha y hash en el manifiesto y ejecutar el indexador. No se reconstruye al buscar ni al recargar."
            )
            st.code(
                ".\\.venv\\Scripts\\python.exe scripts/build_rag_index.py --vectors",
                language="powershell",
            )
            st.caption(
                "PDF: hasta 20 MB y 500 páginas. Documentos sin texto requieren OCR autorizado. Los índices contienen texto y permanecen fuera de Git."
            )
    if configuration.button("Liberar embeddings de esta sesión"):
        release_resources()
        st.rerun()
