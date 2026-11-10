"""Registros de sesión sin persistencia durable ni resultados simulados."""

from datetime import datetime, timezone
from safeguard.core import summarize_results


def image_record(name, result, model_info, threshold):
    return dict(
        result,
        ts=datetime.now(timezone.utc),
        file=name,
        kind="imagen",
        model=model_info,
        threshold=threshold,
    )


def video_record(name, exploration, model_info, threshold):
    samples = exploration["samples"]
    if not exploration["inference_ran"] or any(s["result"] is None for s in samples):
        raise ValueError("La exploración sin inferencia no es un análisis.")
    summary = summarize_results([s["result"] for s in samples])
    return dict(
        summary,
        ts=datetime.now(timezone.utc),
        file=name,
        kind="video",
        model=model_info,
        threshold=threshold,
        configuration=samples[0]["result"].get("configuration", {}) if samples else {},
        performance={"elapsed_seconds": exploration.get("elapsed_seconds")},
        detections=[s["result"]["detections"] for s in samples],
        observations=[s["result"]["observations"] for s in samples],
        decisions=[s["result"]["decisions"] for s in samples],
        frame_references=[
            {"index": s["index"], "seconds": s["seconds"], "time_kind": s["time_kind"]}
            for s in samples
        ],
    )


def append_history(session, record):
    # Older sessions remain untouched. Bound memory in this local prototype.
    history = session.setdefault("history_v1a", [])
    if len(history) >= 100:
        raise ValueError(
            "La sesión alcanzó 100 análisis. Exporte y limpie el historial antes de continuar."
        )
    history.append(record)
