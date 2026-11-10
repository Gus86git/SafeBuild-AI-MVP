"""Read-only, uncapped home indicators; no schema or operational data writes."""

from pathlib import Path
import sqlite3
from datetime import datetime, timezone


def context_metrics(path, company_id, site_id, origin):
    """Count the exact selected scope, including video and observation states."""
    if not path or not company_id or not site_id:
        raise ValueError("Seleccione empresa y obra con una base disponible.")
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        if not db.execute(
            "SELECT 1 FROM sites WHERE id=? AND company_id=?", (site_id, company_id)
        ).fetchone():
            raise ValueError("La obra no pertenece a la empresa seleccionada.")
        scope = (company_id, site_id, origin)
        total, videos = db.execute(
            """SELECT count(*), coalesce(sum(kind='video'),0)
            FROM analyses WHERE company_id=? AND site_id=? AND origin=?""",
            scope,
        ).fetchone()
        observations, pending = db.execute(
            """SELECT count(*), coalesce(sum(o.review_status='pending'),0)
            FROM observations o JOIN analyses a ON a.id=o.analysis_id
            WHERE a.company_id=? AND a.site_id=? AND a.origin=?""",
            scope,
        ).fetchone()
        return dict(
            total=total,
            observations=observations,
            pending=pending,
            videos=videos,
            queried_at=datetime.now(timezone.utc),
        )
    finally:
        db.close()
