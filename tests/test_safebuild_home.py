"""SafeBuild home regression: live scope, uncapped SQL and working native actions."""

from pathlib import Path
import os
import sqlite3
from unittest.mock import patch
from ui_isolation import IsolatedUITest
from test_storage import fixture
from safeguard import storage
from safeguard.ui.home_metrics import context_metrics

ROOT = Path(__file__).resolve().parents[1]


class HomeMetricsTests(IsolatedUITest):
    def setUp(self):
        super().setUp()
        self.path = Path(os.environ["SAFEGUARD_DB_PATH"])
        storage.initialize(self.path)

    def metrics(
        self, site="OBRA-NORTE-001", origin="real_inference", company="TECHCORP-DEMO"
    ):
        return context_metrics(self.path, company, site, origin)

    def test_empty_is_zero_missing_is_unavailable(self):
        self.assertEqual(
            [self.metrics()[k] for k in ("total", "observations", "pending", "videos")],
            [0, 0, 0, 0],
        )
        with self.assertRaises(sqlite3.OperationalError):
            context_metrics(
                self.path.parent / "missing.sqlite3",
                "TECHCORP-DEMO",
                "OBRA-NORTE-001",
                "real_inference",
            )
        self.assertFalse((self.path.parent / "missing.sqlite3").exists())

    def test_scope_pending_video_and_read_only(self):
        for site, origin, digest in [
            ("OBRA-NORTE-001", "real_inference", "one"),
            ("OBRA-SUR-002", "real_inference", "two"),
            ("OBRA-NORTE-001", "synthetic", "three"),
        ]:
            storage.save_analysis(
                self.path, fixture(), "TECHCORP-DEMO", site, digest, origin=origin
            )
        with storage.connect(self.path) as db:
            db.execute("UPDATE analyses SET kind='video' WHERE input_sha256='one'")
            db.execute(
                "UPDATE observations SET review_status='reviewed' WHERE analysis_id IN (SELECT id FROM analyses WHERE input_sha256='one')"
            )
        before = self.path.read_bytes()
        got = self.metrics()
        self.assertEqual(
            [got[k] for k in ("total", "observations", "pending", "videos")],
            [1, 1, 0, 1],
        )
        self.assertEqual(self.metrics(origin="synthetic")["pending"], 1)
        self.assertEqual(self.metrics(site="OBRA-SUR-002")["total"], 1)
        self.assertEqual(before, self.path.read_bytes())

    def test_rejects_cross_company_and_sql_injection(self):
        for company in ("OTHER", "' OR 1=1 --"):
            with self.assertRaises(ValueError):
                self.metrics(company=company)


class HomeNavigationTests(IsolatedUITest):
    def test_presentation_video_opens_without_autoplay_or_navigation(self):
        app = self.app()
        self.assertFalse(app.get("video"))
        site = app.selectbox(key="site").value
        app.button(key="home_presentation_video").click().run()
        self.assertFalse(app.exception)
        videos = app.get("video")
        self.assertEqual(len(videos), 1)
        self.assertIn("T4TzRgYSeVY", videos[0].proto.url)
        self.assertFalse(videos[0].proto.autoplay)
        self.assertEqual(app.radio(key="navigation").value, "Inicio")
        self.assertEqual(app.selectbox(key="site").value, site)

    def app(self):
        from streamlit.testing.v1 import AppTest

        return AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()

    def test_default_home_and_all_entry_points_keep_context(self):
        app = self.app()
        self.assertEqual(app.radio(key="navigation").value, "Inicio")
        site = app.selectbox(key="site").value
        app.session_state["retained_marker"] = "keep"
        for key, destination in [
            ("home_analyze", "Imágenes"),
            ("home_knowledge", "Copilot · Conocimiento"),
            ("home_card_0", "Imágenes"),
            ("home_card_1", "Historial"),
            ("home_card_2", "Copilot · Conocimiento"),
            ("home_card_3", "Resumen"),
        ]:
            app.radio(key="navigation").set_value("Inicio").run()
            app.button(key=key).click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.radio(key="navigation").value, destination)
            self.assertEqual(app.selectbox(key="site").value, site)
            self.assertEqual(app.session_state["retained_marker"], "keep")
            self.assertEqual(app.session_state["history_v1a"], [])

    def test_home_filters_and_refresh_use_current_scope(self):
        storage.initialize(Path(os.environ["SAFEGUARD_DB_PATH"]))
        with storage.connect(Path(os.environ["SAFEGUARD_DB_PATH"])) as db:
            db.execute(
                "INSERT INTO companies VALUES(?,?,?)", ("OTHER", "Other synthetic", 1)
            )
            db.execute(
                "INSERT INTO sites VALUES(?,?,?,?)",
                ("OTHER-SITE", "OTHER", "Other site", 1),
            )
        app = self.app()
        app.selectbox(key="company").set_value("TECHCORP-DEMO").run()
        with patch(
            "safeguard.ui.presentation.context_metrics", wraps=context_metrics
        ) as metrics:
            app.selectbox(key="site").set_value("OBRA-SUR-002").run()
            self.assertEqual(metrics.call_args.args[2], "OBRA-SUR-002")
            origin = next(
                w for w in app.selectbox if w.label == "Procedencia a consultar"
            )
            origin.set_value("synthetic").run()
            self.assertEqual(metrics.call_args.args[3], "synthetic")
            app.selectbox(key="company").set_value("OTHER").run()
            self.assertEqual(metrics.call_args.args[1:3], ("OTHER", "OTHER-SITE"))
            app.button(key="home_refresh").click().run()
            self.assertFalse(app.exception)

    def test_unavailable_metrics_never_show_fake_values(self):
        with patch(
            "safeguard.ui.presentation.context_metrics",
            side_effect=sqlite3.OperationalError("unavailable"),
        ):
            app = self.app()
        self.assertFalse(app.exception)
        self.assertTrue(any("Sin datos" in item.value for item in app.markdown))
        self.assertTrue(
            any("No se pudieron consultar" in item.value for item in app.info)
        )
