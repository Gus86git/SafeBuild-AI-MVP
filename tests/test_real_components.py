"""Real library tests; no weights, inference claims or downloaded fixtures."""

from pathlib import Path
from tempfile import TemporaryDirectory
import importlib.util
import unittest
from ui_isolation import IsolatedUITest
from safeguard.media import explore_video
from safeguard.core import SafetyExpertSystem
from safeguard.workflow import image_record
from safeguard.reporting import state_chart


@unittest.skipUnless(importlib.util.find_spec("streamlit"), "Streamlit not installed")
class StreamlitTests(IsolatedUITest):
    def test_dashboard_shortcuts_preserve_context_and_empty_history(self):
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(
            str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30
        ).run()
        site = app.selectbox(key="site").value
        for key, destination in [
            ("dashboard_image", "Imágenes"),
            ("dashboard_documents", "Copilot · Conocimiento"),
        ]:
            app.radio(key="navigation").set_value("Resumen").run()
            app.button(key=key).click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.radio(key="navigation").value, destination)
            self.assertEqual(app.selectbox(key="site").value, site)
            self.assertEqual(app.session_state["history_v1a"], [])

    def test_all_pages_without_model(self):
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(
            str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30
        ).run()
        self.assertEqual(len(app.exception), 0)
        for page in (
            "Imágenes",
            "Videos",
            "Historial",
            "Exportar",
            "Sistema",
            "Ayuda",
            "Resumen",
        ):
            with self.subTest(page=page):
                app.radio(key="navigation").set_value(page).run()
                self.assertEqual(len(app.exception), 0)
                self.assertEqual(app.session_state["history_v1a"], [])

    def test_load_absent_model_keeps_navigation(self):
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(
            str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30
        ).run()
        app.button(key="load_model").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state["history_v1a"], [])
        self.assertTrue(any("Modelo no disponible" in w.value for w in app.warning))


@unittest.skipUnless(importlib.util.find_spec("cv2"), "OpenCV not installed")
class OpenCVTests(unittest.TestCase):
    def test_real_avi_roundtrip_indices_and_no_inference(self):
        import cv2
        import numpy as np

        with TemporaryDirectory() as directory:
            file = Path(directory) / "test.avi"
            writer = cv2.VideoWriter(
                str(file), cv2.VideoWriter_fourcc(*"MJPG"), 10, (64, 48)
            )
            if not writer.isOpened():
                self.skipTest("MJPG encoder not available")
            try:
                for i in range(12):
                    writer.write(np.full((48, 64, 3), i * 10, dtype=np.uint8))
            finally:
                writer.release()
            temporary = Path(directory) / "processing"
            temporary.mkdir()
            result = explore_video(
                file.read_bytes(),
                "test.avi",
                "video/x-msvideo",
                count=3,
                temp_dir=temporary,
            )
            self.assertEqual([s["index"] for s in result["samples"]], [0, 6, 11])
            self.assertEqual(result["resolution"], (64, 48))
            self.assertAlmostEqual(result["estimated_duration"], 1.2, places=2)
            self.assertFalse(result["inference_ran"])
            self.assertEqual(list(temporary.iterdir()), [])


@unittest.skipUnless(importlib.util.find_spec("plotly"), "Plotly not installed")
class PlotlyTests(unittest.TestCase):
    def test_chart_counts_real_records_not_people(self):
        record = image_record(
            "synthetic fixture", SafetyExpertSystem().analyze([]), None, 0.4
        )
        fig = state_chart([record, record])
        self.assertEqual(list(fig.data[0].x), [2])
        self.assertEqual(list(fig.data[0].y), ["No verificable"])
        self.assertNotIn("Cumplimiento", fig.layout.title.text)
