"""Conservative deterministic routing; text never supplies SQL or scope."""

import re
import unicodedata


def normalized(text):
    return "".join(
        c
        for c in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(c)
    )


def route(question, contextual=False):
    q = normalized(question)
    if not q.strip() or len(q) > 1000:
        raise ValueError("Escriba una pregunta de 1 a 1000 caracteres.")
    normative = bool(
        re.search(
            r"\b(ley|leyes|legal|legales|normativa|normativo|decreto|articulo|sancion|infraccion|acta|inspeccion oficial)\b",
            q,
        )
    )
    if re.search(r"\b(infraccion|acta|sancion)\b", q):
        return {
            "kind": "insufficient",
            "normative": True,
            "message": "No existe un registro de infracciones, actas o sanciones oficiales en este esquema.",
        }
    docs = normative or bool(
        re.search(
            r"\b(procedimiento|manual|politica|establece|revisarse|documento|documentos)\b",
            q,
        )
    )
    docs = docs or (
        "techcorp" in q
        and any(word in q for word in ("indica", "revis", "procedimiento"))
    )
    ops = bool(
        re.search(
            r"\b(registrad\w*|cuant\w*|recientes|categorias|conteo|tenemos|cantidad)\b",
            q,
        )
    )
    deictic = bool(re.search(r"\b(esta (imagen|fotografia|foto)|este analisis)\b", q))
    if contextual:
        visual = bool(
            re.search(
                r"\b(detect\w*|observaron|cascos?|chalecos?|epp|resultados|revision humana)\b",
                q,
            )
        )
        ops = ops or (deictic or visual) and not (docs and not deictic)
    elif deictic and not normative:
        return {
            "kind": "ambiguous",
            "normative": False,
            "message": "Seleccione un análisis para consultar esta imagen; no se usan los totales de la obra como sustituto.",
        }
    if (
        ops
        and contextual
        and re.search(r"\b(accidentes?|incidentes?|lesiones?|muertes?)\b", q)
    ):
        return {
            "kind": "insufficient",
            "normative": normative,
            "message": "El análisis contiene observaciones visuales, no confirmaciones de accidentes, incidentes o lesiones.",
        }
    if (
        ops
        and not contextual
        and not re.search(
            r"\b(observacion\w*|analisis|deteccion\w*|epp|revision\w*|evidencia\w*)\b",
            q,
        )
    ):
        return {
            "kind": "ambiguous",
            "normative": normative,
            "message": "Solo se consultan análisis, observaciones, detecciones, revisión y referencias de evidencia. Precise la consulta.",
        }
    kind = (
        "combined"
        if docs and ops
        else "operational"
        if ops
        else "documentary"
        if docs
        else "ambiguous"
    )
    return {
        "kind": kind,
        "normative": normative,
        "message": "Precise si necesita documentos, cantidades registradas o ambas fuentes."
        if kind == "ambiguous"
        else "",
    }
