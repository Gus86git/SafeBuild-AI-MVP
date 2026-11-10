"""Resultados de sesión y exportación sin porcentajes acreditados."""

import json
from io import BytesIO


def safe_cell(value):
    """Neutraliza prefijos de fórmula incluso tras espacios/controles."""
    controls = "".join(chr(i) for i in range(33)) + "\ufeff"
    if isinstance(value, str) and (
        value.lstrip(controls).startswith(("=", "+", "-", "@"))
        or value.startswith(("\t", "\r", "\n"))
    ):
        return "'" + value
    return value


def export_rows(history):
    rows = []
    for i, record in enumerate(history, 1):
        stats = record["stats"]
        model = record.get("model") or {}
        rows.append(
            {
                "ID": i,
                "Fecha": record["ts"].strftime("%Y-%m-%d"),
                "ID_analisis": record.get("analysis_id", "Solo sesión"),
                "Empresa": record.get("company_id", "No registrada"),
                "Obra": record.get("site_id", "No registrada"),
                "Origen_dato": record.get("origin", "Sesión anterior; no registrada"),
                "Origen_imagen": record.get("input_origin", "No registrado"),
                "SHA256_medio": record.get("input_sha256", "No registrado"),
                "Revision": record.get("review_status", "No registrada"),
                "Hora": record["ts"].strftime("%H:%M:%S"),
                "Archivo": record["file"],
                "Zona_horaria": record["ts"].strftime("%z")
                or "No registrada (sesión anterior)",
                "Tipo": record.get("kind", "imagen"),
                "Estado": record["level"],
                "Cumplimiento": "N/A",
                "Personas_modelo": stats["persons"],
                "Cascos_modelo": stats["helmets"],
                "Chalecos_modelo": stats["vests"],
                "Indicios_color": stats.get("heuristic_hints", 0),
                "Unidad": "promedio por muestra"
                if record.get("kind") == "video"
                else "detecciones por imagen",
                "Muestras": record.get("sample_count", 1),
                "Modelo": model.get("path", "No disponible"),
                "SHA256": model.get("sha256", "N/A"),
                "Regla": record["rule"],
                "Umbral": record.get("threshold"),
                "Detecciones": json.dumps(
                    record.get("detections", []), ensure_ascii=False
                ),
                "Observaciones": json.dumps(
                    record.get("observations", []), ensure_ascii=False
                ),
                "Decisiones": json.dumps(
                    record.get("decisions", []), ensure_ascii=False
                ),
                "Fotogramas": json.dumps(
                    record.get("frame_references", []), ensure_ascii=False
                ),
                "Configuración": json.dumps(
                    record.get("configuration", {}), ensure_ascii=False
                ),
                "Cobertura_EPP_escena": json.dumps(
                    record.get("ppe_scene", []), ensure_ascii=False
                ),
                "Tiempos_medidos": json.dumps(
                    record.get("performance", {}), ensure_ascii=False
                ),
                "Limitación": "Observación experimental. Sin certificación normativa; conteos no equivalen a trabajadores únicos.",
            }
        )
    return [{key: safe_cell(value) for key, value in row.items()} for row in rows]


def csv_bytes(history):
    import csv
    from io import StringIO

    rows = export_rows(history)
    stream = StringIO(newline="")
    if rows:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return stream.getvalue().encode("utf-8-sig")


def excel_bytes(history):
    import xlsxwriter

    rows = export_rows(history)
    if any(
        isinstance(value, str) and len(value) > 32767
        for row in rows
        for value in row.values()
    ):
        raise ValueError(
            "Una celda excede el límite de Excel; exporte CSV para conservar el contenido completo."
        )
    stream = BytesIO()
    with xlsxwriter.Workbook(
        stream,
        {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False},
    ) as workbook:
        sheet = workbook.add_worksheet("Análisis")
        heading = workbook.add_format(
            {"bold": True, "bg_color": "#105B5A", "font_color": "#FFFFFF"}
        )
        if rows:
            sheet.write_row(0, 0, list(rows[0]), heading)
            for ri, row in enumerate(rows, 1):
                for ci, value in enumerate(row.values()):
                    if value is None:
                        sheet.write_blank(ri, ci, None)
                    elif isinstance(value, str):
                        sheet.write_string(ri, ci, value)
                    else:
                        sheet.write(ri, ci, value)
            sheet.set_column(0, len(rows[0]) - 1, 24)
            sheet.freeze_panes(1, 0)
            sheet.autofilter(0, 0, len(rows), len(rows[0]) - 1)
    return stream.getvalue()


def person_rows(result):
    by_id = {d["id"]: d for d in result["detections"]}
    decisions = {d["person_id"]: d for d in result["decisions"]}
    rows = []
    for observation in result["observations"]:
        decision = decisions[observation["person_id"]]
        row = {
            "Persona": observation["person_id"],
            "Estado": decision["state"],
            "Motivo": decision["reason"],
            "Origen": "Modelo sin precisión validada",
            "Indicio de color": "Sí (experimental)"
            if observation["heuristic_hint"]
            else "No",
        }
        person = by_id.get(observation["person_id"].removeprefix("person-"))
        row["Caja"] = str(person["bbox"]) if person else "No disponible"
        row["Puntuación persona"] = person["confidence"] if person else None
        row["Umbral"] = result.get("configuration", {}).get(
            "threshold", "No registrado"
        )
        for label, key in [("Casco", "helmet_id"), ("Chaleco", "vest_id")]:
            item = by_id.get(observation[key])
            row[label] = (
                f"ID {item['id']} · puntuación {item['confidence']:.2f}"
                if item
                else "Sin asociación verificable"
            )
        rows.append(row)
    return rows


def state_chart(history):
    from collections import Counter
    import plotly.graph_objects as go

    counts = Counter(r["level"] for r in history)
    fig = go.Figure(
        go.Bar(
            x=list(counts.values()),
            y=list(counts),
            orientation="h",
            marker_color="#29E6CF",
        )
    )
    fig.update_layout(
        title="Estados de los análisis",
        xaxis_title="Análisis de sesión",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#F2F7F8",
        height=280,
        margin=dict(l=10, r=20, t=50, b=20),
    )
    return fig


def video_counts_chart(samples):
    """Plot only actual inferred samples, retaining original frame indices."""
    import plotly.graph_objects as go

    actual = [sample for sample in samples if sample.get("result") is not None]
    fig = go.Figure()
    for key, label, color in [
        ("persons", "Personas", "#89B8ED"),
        ("helmets", "Cascos", "#29E6CF"),
        ("vests", "Chalecos", "#F0B44B"),
    ]:
        fig.add_trace(
            go.Scatter(
                x=[s["index"] for s in actual],
                y=[s["result"]["stats"][key] for s in actual],
                mode="markers",
                name=label,
                marker_color=color,
                marker_symbol={
                    "persons": "circle",
                    "helmets": "diamond",
                    "vests": "square",
                }[key],
                marker_size=9,
            )
        )
    fig.update_layout(
        title="Detecciones por fotograma evaluado",
        xaxis_title="Índice original (base cero)",
        yaxis_title="Detecciones del modelo",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#F2F7F8",
        height=300,
    )
    return fig


def ppe_scene_rows(result, classes):
    """Scene-level classes; never imply per-person ownership for new PPE."""
    from collections import Counter

    known = {c.lower() for c in classes}
    counts = Counter(d["label"] for d in result["detections"] if d["source"] == "model")
    rows = []
    for title, positive, negative in [
        ("Casco", "helmet", "no_helmet"),
        ("Chaleco", "vest", None),
        ("Guantes", "gloves", "no_gloves"),
        ("Botas", "boots", "no_boots"),
        ("Gafas", "goggles", "no_goggle"),
        ("Arnés", "harness", None),
        ("Protección auditiva", "hearing_protection", None),
        ("Protección respiratoria", "respirator", None),
    ]:
        supported = positive in known
        rows.append(
            {
                "Elemento": title,
                "Detecciones": counts[positive] if supported else "No evaluable",
                "Indicios no_*": counts[negative]
                if negative in known
                else "Clase no disponible",
                "Estado": (
                    "Fuera de las clases entrenadas"
                    if not supported
                    else "Revisar indicios del modelo"
                    if negative and counts[negative]
                    else "Detectado en la escena"
                    if counts[positive]
                    else "No observado / no verificable"
                ),
            }
        )
    return rows
