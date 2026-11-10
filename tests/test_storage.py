from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest
from safeguard import storage
from safeguard.core import SafetyExpertSystem
from safeguard.workflow import image_record, video_record
from safeguard.reporting import csv_bytes, ppe_scene_rows


def fixture():
    result = SafetyExpertSystem().analyze(
        [
            {"class": "person", "confidence": 0.9, "bbox": [10, 10, 100, 200]},
            {"class": "helmet", "confidence": 0.9, "bbox": [20, 15, 80, 40]},
            {"class": "vest", "confidence": 0.9, "bbox": [20, 60, 80, 130]},
        ],
        0.4,
        (300, 300),
    )
    result["configuration"] = {"device": "cpu", "imgsz": 480, "threshold": 0.4}
    return image_record(
        "fixture.png",
        result,
        {"sha256": "test-model", "classes": ["person", "helmet", "vest"]},
        0.4,
    )


class SQLiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "test.sqlite3"
        storage.initialize(self.db)

    def save(
        self,
        record=None,
        site="OBRA-NORTE-001",
        origin="real_inference",
        company="TECHCORP-DEMO",
        digest="test-image",
    ):
        return storage.save_analysis(
            self.db, record or fixture(), company, site, digest, origin=origin
        )

    def test_initialization_idempotent_only_synthetic_context(self):
        storage.initialize(self.db)
        self.assertEqual(len(storage.companies(self.db)), 1)
        self.assertEqual(len(storage.sites(self.db, "TECHCORP-DEMO")), 2)
        self.assertEqual(storage.companies(self.db)[0]["synthetic"], 1)
        self.assertEqual(storage.dashboard(self.db, "TECHCORP-DEMO")["total"], 0)

    def test_save_reopen_and_export(self):
        identifier, created = self.save()
        self.assertTrue(created)
        rows = storage.history(self.db, "TECHCORP-DEMO")
        self.assertEqual(rows[0]["analysis_id"], identifier)
        self.assertEqual(rows[0]["observations"][0]["helmet_id"], "1")
        import json

        self.assertEqual(
            rows[0]["detections"], json.loads(storage.encode(fixture()["detections"]))
        )
        self.assertEqual(rows[0]["review_status"], "pending")
        self.assertIn(identifier, csv_bytes(rows).decode("utf-8-sig"))
        with storage.connect(self.db) as db:
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(
                db.execute("SELECT count(*) FROM detections").fetchone()[0], 3
            )
            self.assertEqual(
                db.execute("SELECT count(*) FROM observations").fetchone()[0], 1
            )
            self.assertEqual(
                db.execute("SELECT kind FROM evidence_refs").fetchone()[0], "input_hash"
            )

    def test_reruns_do_not_duplicate(self):
        first = self.save()
        second = self.save()
        self.assertEqual(first[0], second[0])
        self.assertFalse(second[1])
        self.assertEqual(storage.dashboard(self.db, "TECHCORP-DEMO")["total"], 1)

    def test_changed_parameters_produce_new_analysis(self):
        self.save()
        modified = fixture()
        modified["configuration"]["imgsz"] = 640
        self.save(modified)
        self.assertEqual(storage.dashboard(self.db, "TECHCORP-DEMO")["total"], 2)

    def test_origin_and_site_filters(self):
        self.save()
        self.save(site="OBRA-SUR-002")
        self.save(origin="synthetic")
        self.assertEqual(storage.dashboard(self.db, "TECHCORP-DEMO")["total"], 2)
        self.assertEqual(
            storage.dashboard(self.db, "TECHCORP-DEMO", origin="synthetic")["total"], 1
        )
        self.assertEqual(
            len(storage.history(self.db, "TECHCORP-DEMO", "OBRA-NORTE-001")), 1
        )
        self.assertEqual(storage.history(self.db, "' OR 1=1 --"), [])

    def test_company_site_foreign_key_and_rollback(self):
        with storage.connect(self.db) as db:
            db.execute(
                "INSERT INTO companies VALUES(?,?,?)", ("OTHER", "Other synthetic", 1)
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.save(company="OTHER")
        self.assertEqual(storage.history(self.db, "OTHER"), [])
        with storage.connect(self.db) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM models").fetchone()[0], 0)

    def test_bad_association_rolls_back_all_rows(self):
        bad = fixture()
        bad["observations"][0]["helmet_id"] = "missing"
        with self.assertRaises(sqlite3.IntegrityError):
            self.save(bad)
        with storage.connect(self.db) as db:
            for table in (
                "analyses",
                "models",
                "detections",
                "observations",
                "evidence_refs",
            ):
                self.assertEqual(
                    db.execute("SELECT count(*) FROM " + table).fetchone()[0], 0
                )

    def test_unknown_origin_and_missing_hash_rejected(self):
        with self.assertRaises(ValueError):
            self.save(origin="confirmed_violation")
        bad = fixture()
        bad["model"] = None
        with self.assertRaises(ValueError):
            self.save(bad)

    def test_video_frame_ids_remain_scoped(self):
        record = fixture()
        samples = [
            dict(index=i, seconds=i / 10, time_kind="estimated", result=record)
            for i in (0, 10)
        ]
        video = video_record(
            "clip.avi", dict(samples=samples, inference_ran=True), record["model"], 0.4
        )
        self.save(video)
        with storage.connect(self.db) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM observations").fetchone()[0], 2
            )
            self.assertEqual(
                [
                    r[0]
                    for r in db.execute(
                        "SELECT DISTINCT frame_index FROM detections ORDER BY frame_index"
                    )
                ],
                [0, 10],
            )

    def test_unsupported_and_negative_classes_not_confirmed(self):
        record = fixture()
        record["detections"].append(
            dict(
                id="3",
                label="no_helmet",
                source="model",
                confidence=0.8,
                bbox=[0, 0, 5, 5],
            )
        )
        rows = ppe_scene_rows(record, ["person", "helmet", "vest", "no_helmet"])
        self.assertEqual(rows[0]["Estado"], "Revisar indicios del modelo")
        for row in rows[-3:]:
            self.assertEqual(row["Detecciones"], "No evaluable")

    def test_future_schema_not_overwritten(self):
        with storage.connect(self.db) as db:
            db.execute("PRAGMA user_version=99")
        with self.assertRaises(ValueError):
            storage.initialize(self.db)

    def test_same_request_concurrent_writers_one_record(self):
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=2) as pool:
            values = list(pool.map(lambda _: self.save(), range(2)))
        self.assertEqual(values[0][0], values[1][0])
        self.assertEqual(sum(created for _, created in values), 1)
