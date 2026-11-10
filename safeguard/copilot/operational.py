"""Fixed, bounded SQL operations on the existing database, in read-only mode."""

from contextlib import contextmanager
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
import sqlite3
import json
from zoneinfo import ZoneInfo

ORIGINS = ("real_inference", "experimental", "synthetic")


@contextmanager
def readonly(path):
    con = sqlite3.connect(
        Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=3
    )
    try:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA query_only=ON")
        con.set_progress_handler(
            lambda: 1 if __import__("time").monotonic() > deadline else 0, 1000
        )
        deadline = __import__("time").monotonic() + 3
        con.execute("BEGIN")
        yield con
    finally:
        con.close()


class OperationalQueryService:
    def __init__(self, path):
        self.path = path

    def list_analyses(self, company_id, site_id, origin):
        if not company_id or not site_id or origin not in ORIGINS:
            raise ValueError("Contexto inválido.")
        with readonly(self.path) as db:
            return [
                dict(row)
                for row in db.execute(
                    """SELECT id,created_utc,kind,input_origin
                FROM analyses WHERE company_id=? AND site_id=? AND origin=? AND kind='imagen'
                ORDER BY julianday(created_utc) DESC,id LIMIT 50""",
                    (company_id, site_id, origin),
                )
            ]

    def analysis(self, analysis_id, company_id, site_id, origin):
        if (
            not isinstance(analysis_id, str)
            or not analysis_id
            or len(analysis_id) > 128
        ):
            raise ValueError("Identificador inválido.")
        return self.query(company_id, site_id, origin, analysis_id=analysis_id)

    def query(
        self, company_id, site_id, origin, start=None, end=None, *, analysis_id=None
    ):
        if not company_id or not site_id or origin not in ORIGINS:
            raise ValueError("Seleccione empresa, obra y procedencia válidas.")
        if (start is None) != (end is None) or (start and start > end):
            raise ValueError("Intervalo de fechas inválido.")
        params = [company_id, site_id, origin]
        where = "a.company_id=? AND a.site_id=? AND a.origin=?"
        if analysis_id is not None:
            where += " AND a.id=?"
            params.append(analysis_id)
        if start:
            zone = ZoneInfo("America/Argentina/Buenos_Aires")
            begin = datetime.combine(start, time.min, zone).astimezone(timezone.utc)
            finish = datetime.combine(
                end + timedelta(days=1), time.min, zone
            ).astimezone(timezone.utc)
            where += " AND julianday(a.created_utc)>=julianday(?) AND julianday(a.created_utc)<julianday(?)"
            params += [begin.isoformat(), finish.isoformat()]
        with readonly(self.path) as db:
            site = db.execute(
                "SELECT name FROM sites WHERE id=? AND company_id=?",
                (site_id, company_id),
            ).fetchone()
            if site is None:
                raise ValueError("La obra no pertenece a la empresa seleccionada.")

            def rows(sql):
                return [dict(r) for r in db.execute(sql, params).fetchall()]

            selected = None
            if analysis_id is not None:
                metadata = rows(f"""SELECT a.id,a.kind,a.created_utc,a.model_sha256,a.origin,a.input_origin,a.state,a.review_status,
                    CASE WHEN json_valid(a.record_json) THEN substr(json_extract(a.record_json,'$.configuration'),1,4000) ELSE NULL END AS configuration
                    FROM analyses a WHERE {where}""")
                if not metadata:
                    raise ValueError(
                        "Análisis inexistente o fuera del contexto autorizado."
                    )
                selected = metadata[0]
                try:
                    configuration = json.loads(selected.pop("configuration") or "{}")
                except (ValueError, TypeError):
                    configuration = {}
                # Only known numeric/boolean configuration fields; no model paths or arbitrary nested data.
                selected["configuration"] = (
                    {
                        k: v
                        for k, v in configuration.items()
                        if k in ("imgsz", "threshold", "use_color", "max_det")
                        and isinstance(v, (int, float, bool))
                    }
                    if isinstance(configuration, dict)
                    else {}
                )
                selected["detections"] = (
                    rows(f"""SELECT d.frame_index,d.id,d.label,d.confidence,d.source
                    FROM detections d JOIN analyses a ON a.id=d.analysis_id WHERE {where}
                    ORDER BY d.frame_index,d.id LIMIT 200""")
                )
                selected["people"] = (
                    rows(f"""SELECT o.frame_index,o.id,o.person_detection_id,o.helmet_id,o.vest_id,
                    o.state,substr(o.reason,1,1500) AS reason,o.review_status,
                    CASE WHEN json_valid(o.payload_json) THEN json_extract(o.payload_json,'$.ambiguous') END AS ambiguous,
                    CASE WHEN json_valid(o.payload_json) THEN json_extract(o.payload_json,'$.obstructed') END AS obstructed,
                    CASE WHEN json_valid(o.payload_json) THEN json_extract(o.payload_json,'$.heuristic_hint') END AS heuristic_hint
                    FROM observations o JOIN analyses a ON a.id=o.analysis_id WHERE {where}
                    ORDER BY o.frame_index,o.id LIMIT 200""")
                )
            analyses = rows(f"SELECT count(*) AS count FROM analyses a WHERE {where}")[
                0
            ]["count"]
            observations = rows(
                f"SELECT count(*) AS count FROM observations o JOIN analyses a ON a.id=o.analysis_id WHERE {where}"
            )[0]["count"]
            categories = rows(
                f"SELECT d.label,d.source,count(*) AS count FROM detections d JOIN analyses a ON a.id=d.analysis_id WHERE {where} GROUP BY d.label,d.source ORDER BY count DESC,d.label,d.source LIMIT 50"
            )
            states = rows(
                f"SELECT o.state,o.review_status,count(*) AS count FROM observations o JOIN analyses a ON a.id=o.analysis_id WHERE {where} GROUP BY o.state,o.review_status ORDER BY o.state,o.review_status LIMIT 30"
            )
            associations = rows(
                f"SELECT sum(CASE WHEN o.helmet_id IS NOT NULL THEN 1 ELSE 0 END) AS helmet_associated,sum(CASE WHEN o.vest_id IS NOT NULL THEN 1 ELSE 0 END) AS vest_associated FROM observations o JOIN analyses a ON a.id=o.analysis_id WHERE {where}"
            )[0]
            recent = rows(
                f"SELECT a.id,a.created_utc,a.kind,a.review_status FROM analyses a WHERE {where} ORDER BY julianday(a.created_utc) DESC,a.id LIMIT 10"
            )
            # Hash references only, never paths, images, record_json or filenames.
            refs = rows(
                f"SELECT e.analysis_id,e.sha256 FROM evidence_refs e JOIN analyses a ON a.id=e.analysis_id WHERE {where} AND e.kind='input_hash' ORDER BY a.created_utc DESC LIMIT 10"
            )
        result = {
            "source_id": "SQL:scope",
            "context": {
                "company_id": company_id,
                "site_id": site_id,
                "site_name": site["name"],
                "origin": origin,
                "start": str(start) if start else None,
                "end": str(end) if end else None,
                "timezone": "America/Argentina/Buenos_Aires",
            },
            "facts": {"analyses": analyses, "observations": observations},
            "detection_categories": categories,
            "observation_states": states,
            "associations": {k: v or 0 for k, v in associations.items()},
            "recent": recent,
            "evidence_refs": refs,
            "limitations": [
                "Conteos de registros y de observaciones por frame; no personas únicas ni infracciones.",
                "Categorías: detecciones, no categorías de incumplimiento. Asociaciones sin EPP no confirman ausencia.",
                "Revisión pending/reviewed no certifica cumplimiento. Listados limitados; agregados calculados sobre todo el intervalo.",
            ],
        }
        if selected is not None:
            result["selected_analysis"] = selected
            result["limitations"] += [
                "Contexto limitado al análisis seleccionado; hasta 200 detecciones y 200 observaciones detalladas.",
                "IDs de persona efímeros por análisis/frame; no reconocimiento ni identidad personal.",
                "Una inferencia computacional real puede analizar una imagen sintética. El origen del medio no acredita un incidente laboral.",
                "Solo casco y chaleco tienen asociación individual experimental. Otras clases son detecciones de escena, no ausencias confirmadas.",
            ]
        return result
