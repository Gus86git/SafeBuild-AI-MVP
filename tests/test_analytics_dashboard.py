from datetime import date, datetime, timezone
from pathlib import Path
import os
from unittest.mock import patch
from ui_isolation import IsolatedUITest
from test_storage import fixture
from safeguard import storage
from safeguard.ui.analytics import dashboard_data

ROOT = Path(__file__).resolve().parents[1]


class AnalyticsTests(IsolatedUITest):
    def setUp(self):
        super().setUp()
        self.path = Path(os.environ["SAFEGUARD_DB_PATH"])
        storage.initialize(self.path)

    def data(self, **kw):
        return dashboard_data(
            self.path, "TECHCORP-DEMO", "OBRA-NORTE-001", "real_inference", **kw
        )

    def save(
        self, digest="one", site="OBRA-NORTE-001", origin="real_inference", ts=None
    ):
        record = fixture()
        if ts:
            record["ts"] = ts
        return storage.save_analysis(
            self.path, record, "TECHCORP-DEMO", site, digest, origin=origin
        )[0]

    def test_empty_readonly_and_scope_validation(self):
        before = self.path.read_bytes()
        got = self.data()
        self.assertEqual(
            got["totals"],
            dict(total=0, videos=0, observations=0, pending=0, reviewed=0),
        )
        self.assertEqual(got["classes"], [])
        self.assertEqual(before, self.path.read_bytes())
        with self.assertRaises(ValueError):
            dashboard_data(self.path, "OTHER", "OBRA-NORTE-001", "real_inference")
        with self.assertRaises(ValueError):
            self.data(kind="invalid")
        with self.assertRaises(ValueError):
            self.data(start=date(2026, 1, 2), end=date(2026, 1, 1))

    def test_filters_local_date_and_counts_do_not_multiply(self):
        self.save(ts=datetime(2026, 1, 2, 2, 59, tzinfo=timezone.utc))
        second = self.save("two", ts=datetime(2026, 1, 2, 3, 0, tzinfo=timezone.utc))
        self.save("other-site", site="OBRA-SUR-002")
        self.save("synthetic", origin="synthetic")
        with storage.connect(self.path) as db:
            db.execute("UPDATE analyses SET kind='video' WHERE id=?", (second,))
            db.execute(
                "UPDATE observations SET review_status='reviewed' WHERE analysis_id=?",
                (second,),
            )
            db.execute(
                "INSERT INTO detections VALUES(?,0,'h','helmet',.6,'heuristic','[]')",
                (second,),
            )
            db.execute(
                "INSERT INTO detections VALUES(?,0,'n','no_helmet',.6,'model','[]')",
                (second,),
            )
            db.execute(
                "INSERT INTO detections VALUES(?,0,'g','gloves',.6,'model','[]')",
                (second,),
            )
        data = self.data()
        self.assertEqual(
            data["totals"],
            dict(total=2, videos=1, observations=2, pending=1, reviewed=1),
        )
        self.assertEqual(
            {r["label"]: r["count"] for r in data["classes"]},
            {"helmet": 2, "vest": 2, "gloves": 1},
        )
        self.assertEqual(
            self.data(start=date(2026, 1, 1), end=date(2026, 1, 1))["totals"]["total"],
            1,
        )
        self.assertEqual(
            self.data(start=date(2026, 1, 2), end=date(2026, 1, 2))["totals"][
                "reviewed"
            ],
            1,
        )
        self.assertEqual(self.data(kind="imagen")["totals"]["pending"], 1)
        self.assertEqual(self.data(kind="video")["totals"]["pending"], 0)
        self.assertEqual(sum(r["count"] for r in data["categories"]), 2)
        self.assertEqual(sum(r["count"] for r in data["daily"]), 2)
        self.assertEqual(sum(r["count"] for r in data["trend"]), 2)

    def test_aggregates_not_limited_to_recent(self):
        for i in range(23):
            self.save(str(i))
        got = self.data()
        self.assertEqual(got["totals"]["total"], 23)
        self.assertEqual(got["totals"]["pending"], 23)
        self.assertEqual(len(got["recent"]), 20)
        self.assertEqual(len(got["attention"]), 20)

    def test_ui_filters_detail_scope_and_copilot(self):
        identifier = self.save()
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=40).run()
        self.assertEqual(app.radio(key="navigation").options[1], "Dashboard")
        app.radio(key="navigation").set_value("Dashboard").run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.get("plotly_chart")), 5)
        app.button(key="dash_detail_open").click().run()
        self.assertEqual(app.session_state["dash_detail"][1], identifier)
        app.button(key="dash_copilot").click().run()
        self.assertEqual(app.radio(key="navigation").value, "Copilot · Asistente")
        self.assertEqual(
            app.session_state["copilot_selection"]["analysis_id"], identifier
        )
        app.radio(key="navigation").set_value("Dashboard").run()
        app.button(key="dash_attention_open").click().run()
        self.assertIsNotNone(app.session_state["dash_detail"][3])
        app.selectbox(key="dash_kind").set_value("video").run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.get("plotly_chart")), 0)
        self.assertNotIn("dash_detail", app.session_state)
        app.selectbox(key="dash_kind").set_value("Todos").run()
        app.selectbox(key="site").set_value("OBRA-SUR-002").run()
        self.assertEqual(len(app.get("plotly_chart")), 0)
        app.selectbox(key="dash_period").set_value("Personalizado").run()
        self.assertFalse(app.exception)
        app.button(key="dash_history").click().run()
        self.assertEqual(app.radio(key="navigation").value, "Historial")

    def test_ui_database_error_is_not_zero(self):
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=40).run()
        with patch(
            "safeguard.ui.dashboard.dashboard_data",
            side_effect=ValueError("unavailable"),
        ):
            app.radio(key="navigation").set_value("Dashboard").run()
        self.assertFalse(app.exception)
        self.assertTrue(
            any("No se pudo consultar el dashboard" in w.value for w in app.warning)
        )
        self.assertEqual(len(app.get("plotly_chart")), 0)
