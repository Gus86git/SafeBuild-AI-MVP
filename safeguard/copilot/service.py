"""Coordinates independent evidence tools without invoking generation."""

from time import perf_counter
import re
from .router import route, normalized


class DocumentRetriever:
    def __init__(self, retriever):
        self.retriever = retriever

    def search(self, question, method, normative=False):
        return self.retriever.search(
            question,
            method=method,
            top_k=4,
            source_types=["official", "technical_guide"]
            if normative
            else ["simulated_manual", "simulated_procedure"],
        )


def gather(
    question,
    context,
    operational,
    documents=None,
    method="BM25",
    start=None,
    end=None,
    *,
    analysis_id=None,
):
    began = perf_counter()
    routing = route(question, contextual=analysis_id is not None)
    package = {
        "question": question,
        "routing": routing,
        "sql": None,
        "documents": [],
        "warnings": [],
        "status": "insufficient",
    }
    if analysis_id is not None:
        package["analysis_id"] = analysis_id
    if routing["kind"] in ("ambiguous", "insufficient"):
        package["warnings"].append(routing["message"])
    else:
        q = normalized(question)
        # Known demo aliases may not override the selected application scope.
        mismatch = ("torre norte" in q and context["site_id"] != "OBRA-NORTE-001") or (
            "centro logistico sur" in q and context["site_id"] != "OBRA-SUR-002"
        )
        if (
            routing["kind"] in ("operational", "combined")
            and start is None
            and re.search(
                r"\b(hoy|ayer|semana|mes|ano|enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\b|(?<![\w-])\d{4}-\d{2}(?:-\d{2})?(?![\w-])|(?<!\w)\d{1,2}/\d{1,2}(?:/\d{2,4})?(?!\w)",
                q,
            )
        ):
            package["warnings"].append(
                "Seleccione el intervalo de fechas en los controles para consultar ese período. No se deducen fechas del texto."
            )
            package["latency_seconds"] = perf_counter() - began
            return package
        if mismatch:
            package["warnings"].append(
                "La obra mencionada no coincide con el selector. Cambie el contexto antes de consultar."
            )
        else:
            selected = None
            if analysis_id is not None:
                try:
                    selected = operational.analysis(
                        analysis_id,
                        context["company_id"],
                        context["site_id"],
                        context["origin"],
                    )
                except (ValueError, OSError, __import__("sqlite3").Error):
                    package["warnings"].append(
                        "Análisis inexistente o fuera del contexto autorizado. Seleccione nuevamente."
                    )
                    package["latency_seconds"] = perf_counter() - began
                    return package
            if routing["kind"] in ("operational", "combined"):
                try:
                    package["sql"] = (
                        selected
                        if selected is not None
                        else operational.query(
                            context["company_id"],
                            context["site_id"],
                            context["origin"],
                            start,
                            end,
                        )
                    )
                except (ValueError, OSError, __import__("sqlite3").Error):
                    package["warnings"].append(
                        "No se pudo consultar SQLite en el contexto seleccionado."
                    )
            if routing["kind"] in ("documentary", "combined"):
                try:
                    if documents is None:
                        raise ValueError("Corpus no disponible")
                    # Combined intent uses the internal review procedure, not operational counts as search terms.
                    review_intent = "observacion" in q and any(
                        word in q
                        for word in (
                            "revis",
                            "inteligencia artificial",
                            "procedimiento",
                        )
                    )
                    search = (
                        "TechCorp procedimiento observaciones inteligencia artificial revision"
                        if (routing["kind"] == "combined" or review_intent)
                        and not routing["normative"]
                        else question
                    )
                    if (
                        selected is not None
                        and not review_intent
                        and routing["kind"] != "combined"
                        and not routing["normative"]
                    ):
                        # Known EPP labels only; never infer an activity from boxes or model positions.
                        labels = {r["label"] for r in selected["detection_categories"]}
                        search += " " + " ".join(
                            word
                            for label, word in [
                                ("helmet", "casco"),
                                ("vest", "chaleco"),
                                ("gloves", "guantes"),
                                ("goggles", "gafas"),
                                ("boots", "botas"),
                            ]
                            if label in labels
                        )
                    package["document_query"] = search
                    result = documents.search(search, method, routing["normative"])
                    package["documents"] = [r["chunk"] for r in result["results"]]
                    package["retrieval_method"] = result["method"]
                    if result.get("warning"):
                        package["warnings"].append(result["warning"])
                except Exception:
                    package["warnings"].append(
                        "Recuperación documental no disponible; revise el índice en Conocimiento."
                    )
            found = bool(package["sql"]) + bool(package["documents"])
            needed = 2 if routing["kind"] == "combined" else 1
            package["status"] = (
                "grounded"
                if found == needed
                else "partial"
                if found
                else "insufficient"
            )
    if routing["normative"]:
        package["warnings"].append(
            "Generación normativa deshabilitada. Completitud, vigencia y validación independiente pendientes."
        )
    package["latency_seconds"] = perf_counter() - began
    return package
