"""SQLite local: transacciones, procedencia y consultas acotadas por empresa/obra."""

from contextlib import contextmanager
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import json
import os
import sqlite3
from uuid import uuid4

ORIGINS = ("real_inference", "experimental", "synthetic")


def validate_schema(path):
    """Check an existing database without initialization or writes."""
    required = {
        "companies",
        "sites",
        "models",
        "analyses",
        "detections",
        "observations",
        "evidence_refs",
    }
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        version = db.execute("PRAGMA user_version").fetchone()[0]
        tables = {
            r[0]
            for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if version != 1 or not required <= tables:
            raise ValueError(
                "Esquema SQLite no compatible; se preserva la base sin cambios."
            )
    finally:
        db.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS companies(
 id TEXT PRIMARY KEY, name TEXT NOT NULL, synthetic INTEGER NOT NULL CHECK(synthetic IN (0,1)));
CREATE TABLE IF NOT EXISTS sites(
 id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id),
 name TEXT NOT NULL, synthetic INTEGER NOT NULL CHECK(synthetic IN (0,1)),
 UNIQUE(id,company_id));
CREATE TABLE IF NOT EXISTS models(
 sha256 TEXT PRIMARY KEY, metadata_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS analyses(
 id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE,
 company_id TEXT NOT NULL, site_id TEXT NOT NULL,
 model_sha256 TEXT NOT NULL REFERENCES models(sha256),
 created_utc TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('imagen','video')),
 origin TEXT NOT NULL CHECK(origin IN ('real_inference','experimental','synthetic')),
 input_sha256 TEXT NOT NULL, input_origin TEXT NOT NULL,
 state TEXT NOT NULL, review_status TEXT NOT NULL DEFAULT 'pending' CHECK(review_status IN ('pending','reviewed')),
 record_json TEXT NOT NULL,
 FOREIGN KEY(site_id,company_id) REFERENCES sites(id,company_id));
CREATE TABLE IF NOT EXISTS detections(
 analysis_id TEXT NOT NULL REFERENCES analyses(id), frame_index INTEGER NOT NULL,
 id TEXT NOT NULL, label TEXT NOT NULL, confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1),
 source TEXT NOT NULL CHECK(source IN ('model','heuristic')), bbox_json TEXT NOT NULL,
 PRIMARY KEY(analysis_id,frame_index,id));
CREATE TABLE IF NOT EXISTS observations(
 analysis_id TEXT NOT NULL REFERENCES analyses(id), frame_index INTEGER NOT NULL,
 id TEXT NOT NULL, person_detection_id TEXT NOT NULL, helmet_id TEXT, vest_id TEXT,
 state TEXT NOT NULL, reason TEXT NOT NULL, payload_json TEXT NOT NULL,
 review_status TEXT NOT NULL DEFAULT 'pending' CHECK(review_status IN ('pending','reviewed')),
 PRIMARY KEY(analysis_id,frame_index,id),
 FOREIGN KEY(analysis_id,frame_index,person_detection_id) REFERENCES detections(analysis_id,frame_index,id),
 FOREIGN KEY(analysis_id,frame_index,helmet_id) REFERENCES detections(analysis_id,frame_index,id),
 FOREIGN KEY(analysis_id,frame_index,vest_id) REFERENCES detections(analysis_id,frame_index,id));
CREATE TABLE IF NOT EXISTS evidence_refs(
 analysis_id TEXT NOT NULL REFERENCES analyses(id), kind TEXT NOT NULL,
 reference TEXT NOT NULL, sha256 TEXT NOT NULL,
 PRIMARY KEY(analysis_id,kind,reference));
CREATE INDEX IF NOT EXISTS analysis_scope ON analyses(company_id,site_id,origin,created_utc);
"""


def database_path(root):
    value = Path(
        os.environ.get("SAFEGUARD_DB_PATH", "data/local/safeguard_demo.sqlite3")
    )
    return value if value.is_absolute() else Path(root) / value


@contextmanager
def connect(path):
    connection = sqlite3.connect(str(path), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as db:
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            raise ValueError("Versión SQLite no compatible; no se modificó el esquema.")
        db.executescript(SCHEMA)
        db.execute(
            "INSERT OR IGNORE INTO companies VALUES(?,?,?)",
            ("TECHCORP-DEMO", "TechCorp Construcciones", 1),
        )
        db.executemany(
            "INSERT OR IGNORE INTO sites VALUES(?,?,?,?)",
            [
                ("OBRA-NORTE-001", "TECHCORP-DEMO", "Torre Norte", 1),
                ("OBRA-SUR-002", "TECHCORP-DEMO", "Centro Logístico Sur", 1),
            ],
        )
        db.execute("PRAGMA user_version=1")


def companies(path):
    with connect(path) as db:
        return [dict(r) for r in db.execute("SELECT * FROM companies ORDER BY name")]


def sites(path, company_id):
    with connect(path) as db:
        return [
            dict(r)
            for r in db.execute(
                "SELECT * FROM sites WHERE company_id=? ORDER BY id", (company_id,)
            )
        ]


def encode(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
        default=lambda x: x.isoformat() if isinstance(x, datetime) else str(x),
    )


def save_analysis(
    path,
    record,
    company_id,
    site_id,
    input_sha256,
    *,
    origin="real_inference",
    input_origin="user_upload",
    evidence=None,
):
    if origin not in ORIGINS:
        raise ValueError("Procedencia inválida")
    model = record.get("model") or {}
    digest = model.get("sha256")
    if not digest or not input_sha256:
        raise ValueError("Falta hash del modelo o del medio")
    if record.get("kind") not in ("imagen", "video"):
        raise ValueError("Tipo de análisis inválido")
    fingerprint = sha256(
        encode(
            [
                company_id,
                site_id,
                input_sha256,
                digest,
                record.get("kind"),
                record.get("configuration", {}),
                record.get("threshold"),
                record.get("rule"),
                origin,
                input_origin,
                record.get("frame_references", []),
            ]
        ).encode()
    ).hexdigest()
    identifier = str(uuid4())
    enriched = dict(
        record,
        analysis_id=identifier,
        company_id=company_id,
        site_id=site_id,
        origin=origin,
        input_sha256=input_sha256,
        input_origin=input_origin,
        review_status="pending",
    )
    with connect(path) as db:
        db.execute("BEGIN IMMEDIATE")
        previous = db.execute(
            "SELECT id FROM analyses WHERE idempotency_key=?", (fingerprint,)
        ).fetchone()
        if previous:
            return previous["id"], False
        db.execute("INSERT OR IGNORE INTO models VALUES(?,?)", (digest, encode(model)))
        db.execute(
            """INSERT INTO analyses(id,idempotency_key,company_id,site_id,model_sha256,
            created_utc,kind,origin,input_sha256,input_origin,state,record_json)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                identifier,
                fingerprint,
                company_id,
                site_id,
                digest,
                record["ts"].isoformat(),
                record["kind"],
                origin,
                input_sha256,
                input_origin,
                record["level"],
                encode(enriched),
            ),
        )
        if record["kind"] == "imagen":
            frames = [(-1, record)]
        else:
            references = record.get("frame_references", [])
            results = record.get("frames", [])
            if len(references) != len(results) or not results:
                raise ValueError("Video sin resultados o referencias consistentes")
            frames = [
                (ref["index"], result) for ref, result in zip(references, results)
            ]
        for index, result in frames:
            for d in result["detections"]:
                db.execute(
                    "INSERT INTO detections VALUES(?,?,?,?,?,?,?)",
                    (
                        identifier,
                        index,
                        d["id"],
                        d["label"],
                        d["confidence"],
                        d["source"],
                        encode(d["bbox"]),
                    ),
                )
            decisions = {d["person_id"]: d for d in result["decisions"]}
            for o in result["observations"]:
                decision = decisions[o["person_id"]]
                db.execute(
                    """INSERT INTO observations(analysis_id,frame_index,id,person_detection_id,
                    helmet_id,vest_id,state,reason,payload_json) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (
                        identifier,
                        index,
                        o["person_id"],
                        o["person_id"].removeprefix("person-"),
                        o["helmet_id"],
                        o["vest_id"],
                        decision["state"],
                        decision["reason"],
                        encode(o),
                    ),
                )
        # Hash references only by default: no photo or video bytes in SQLite.
        db.execute(
            "INSERT INTO evidence_refs VALUES(?,?,?,?)",
            (identifier, "input_hash", "sha256:" + input_sha256, input_sha256),
        )
        for item in evidence or []:
            db.execute(
                "INSERT INTO evidence_refs VALUES(?,?,?,?)",
                (identifier, item["kind"], item["reference"], item["sha256"]),
            )
    return identifier, True


def _scope(company_id, site_id, origin):
    if origin not in ORIGINS:
        raise ValueError("Procedencia inválida")
    where = "a.company_id=? AND a.origin=?"
    args = [company_id, origin]
    if site_id is not None:
        where += " AND a.site_id=?"
        args.append(site_id)
    return where, args


def history(path, company_id, site_id=None, origin="real_inference", limit=100):
    where, args = _scope(company_id, site_id, origin)
    with connect(path) as db:
        rows = db.execute(
            f"SELECT a.record_json FROM analyses a WHERE {where} ORDER BY a.created_utc DESC,a.id DESC LIMIT ?",
            [*args, max(1, min(int(limit), 1000))],
        ).fetchall()
    records = []
    for row in rows:
        record = json.loads(row[0])
        record["ts"] = datetime.fromisoformat(record["ts"])
        records.append(record)
    return records


def get_analysis(path, identifier, company_id, site_id):
    with connect(path) as db:
        row = db.execute(
            "SELECT record_json FROM analyses WHERE id=? AND company_id=? AND site_id=?",
            (identifier, company_id, site_id),
        ).fetchone()
    if row is None:
        raise ValueError("Análisis no encontrado en la obra seleccionada")
    record = json.loads(row[0])
    record["ts"] = datetime.fromisoformat(record["ts"])
    return record


def dashboard(path, company_id, site_id=None, origin="real_inference"):
    where, args = _scope(company_id, site_id, origin)
    with connect(path) as db:
        total = db.execute(
            f"SELECT count(*) FROM analyses a WHERE {where}", args
        ).fetchone()[0]
        observations = db.execute(
            f"SELECT count(*) FROM observations o JOIN analyses a ON a.id=o.analysis_id WHERE {where}",
            args,
        ).fetchone()[0]
        pending = db.execute(
            f"SELECT count(*) FROM observations o JOIN analyses a ON a.id=o.analysis_id WHERE {where} AND o.review_status='pending'",
            args,
        ).fetchone()[0]
        by_site = [
            dict(r)
            for r in db.execute(
                f"SELECT a.site_id,count(*) AS analyses FROM analyses a WHERE {where} GROUP BY a.site_id",
                args,
            )
        ]
        classes = [
            dict(r)
            for r in db.execute(
                f"""SELECT d.label,count(*) AS detections FROM detections d
            JOIN analyses a ON a.id=d.analysis_id WHERE {where} AND d.source='model'
            GROUP BY d.label ORDER BY detections DESC""",
                args,
            )
        ]
    return dict(
        total=total,
        observations=observations,
        pending=pending,
        by_site=by_site,
        classes=classes,
    )
