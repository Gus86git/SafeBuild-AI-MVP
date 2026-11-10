"""Read-only dashboard aggregates over a single authorized SQLite snapshot."""

from datetime import datetime, time, timedelta, timezone
from safeguard.copilot.operational import readonly
from safeguard.storage import ORIGINS

LOCAL = timezone(timedelta(hours=-3))
PPE_LABELS = ("helmet", "vest", "gloves", "boots", "goggles")


def dashboard_data(path, company, site, origin, start=None, end=None, kind="Todos"):
    if not path or not company or not site or origin not in ORIGINS:
        raise ValueError("Seleccione empresa, obra y procedencia válidas.")
    if kind not in ("Todos", "imagen", "video"):
        raise ValueError("Tipo de medio inválido.")
    if (start is None) != (end is None) or (start and start > end):
        raise ValueError("Intervalo de fechas inválido.")
    where = "a.company_id=? AND a.site_id=? AND a.origin=?"
    args = [company, site, origin]
    if start:
        where += " AND julianday(a.created_utc)>=julianday(?) AND julianday(a.created_utc)<julianday(?)"
        args += [
            datetime.combine(start, time.min, LOCAL).isoformat(),
            datetime.combine(end + timedelta(days=1), time.min, LOCAL).isoformat(),
        ]
    if kind != "Todos":
        where += " AND a.kind=?"
        args.append(kind)
    with readonly(path) as db:
        if not db.execute(
            "SELECT 1 FROM sites WHERE id=? AND company_id=?", (site, company)
        ).fetchone():
            raise ValueError("La obra no pertenece a la empresa seleccionada.")

        def rows(sql):
            return [dict(row) for row in db.execute(sql, args)]

        totals = rows(
            f"SELECT count(*) total,coalesce(sum(a.kind='video'),0) videos FROM analyses a WHERE {where}"
        )[0]
        totals.update(
            rows(f"""SELECT count(*) observations,
            coalesce(sum(o.review_status='pending'),0) pending,
            coalesce(sum(o.review_status='reviewed'),0) reviewed
            FROM observations o JOIN analyses a ON a.id=o.analysis_id WHERE {where}""")[
                0
            ]
        )
        classes = rows(f"""SELECT d.label,count(*) count FROM detections d JOIN analyses a ON a.id=d.analysis_id
            WHERE {where} AND d.source='model' AND d.label IN ('helmet','vest','gloves','boots','goggles') GROUP BY d.label ORDER BY count DESC,d.label""")
        daily = rows(f"""SELECT date(a.created_utc,'-3 hours') day,count(*) count FROM analyses a
            WHERE {where} GROUP BY day ORDER BY day""")
        trend = rows(f"""SELECT date(a.created_utc,'-3 hours') day,count(*) count,
            sum(o.review_status='pending') pending,sum(o.review_status='reviewed') reviewed
            FROM observations o JOIN analyses a ON a.id=o.analysis_id WHERE {where} GROUP BY day ORDER BY day""")
        categories = rows(f"""SELECT o.state category,count(*) count FROM observations o
            JOIN analyses a ON a.id=o.analysis_id WHERE {where} GROUP BY o.state ORDER BY count DESC,o.state""")
        recent = rows(f"""SELECT a.id,a.created_utc,a.kind,a.review_status,
            CASE WHEN json_valid(a.record_json) THEN json_extract(a.record_json,'$.file') ELSE NULL END filename,
            (SELECT count(*) FROM detections d WHERE d.analysis_id=a.id AND d.source='model') detections,
            (SELECT count(*) FROM observations o WHERE o.analysis_id=a.id) observations,
            (SELECT count(*) FROM observations o WHERE o.analysis_id=a.id AND o.review_status='pending') pending
            FROM analyses a WHERE {where} ORDER BY julianday(a.created_utc) DESC,a.id LIMIT 20""")
        attention = rows(f"""SELECT o.analysis_id,o.frame_index,o.id,o.state,o.reason FROM observations o
            JOIN analyses a ON a.id=o.analysis_id WHERE {where} AND o.review_status='pending'
            ORDER BY julianday(a.created_utc) DESC,a.id,o.frame_index,o.id LIMIT 20""")
    return dict(
        totals=totals,
        classes=classes,
        daily=daily,
        trend=trend,
        categories=categories,
        recent=recent,
        attention=attention,
        queried_at=datetime.now(LOCAL),
    )
