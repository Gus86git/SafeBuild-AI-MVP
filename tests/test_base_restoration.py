"""Regression coverage for restored options and additional photo containers."""

from io import BytesIO
from pathlib import Path
import unittest
from ui_isolation import IsolatedUITest
from PIL import Image
from safeguard.media import read_image, sample_indices, MediaError
from safeguard.core import SafetyExpertSystem
from safeguard.reporting import video_counts_chart
from safeguard.workflow import image_record


class PhotoTests(unittest.TestCase):
    def test_extra_photo_formats(self):
        for fmt, suffix, mime in [
            ("JPEG", "jfif", "image/jpeg"),
            ("TIFF", "tiff", "image/tiff"),
            ("GIF", "gif", "image/gif"),
            ("AVIF", "avif", "image/avif"),
        ]:
            with self.subTest(format=fmt):
                output = BytesIO()
                Image.new("RGB", (32, 24), "red").save(output, format=fmt)
                result = read_image(output.getvalue(), "photo." + suffix, mime)
                self.assertEqual(result.size, (32, 24))
                self.assertEqual(result.mode, "RGB")

    def test_animated_image_is_explicitly_first_frame(self):
        output = BytesIO()
        Image.new("RGB", (32, 24), "red").save(
            output,
            format="GIF",
            save_all=True,
            append_images=[Image.new("RGB", (32, 24), "blue")],
            duration=100,
            loop=0,
        )
        result = read_image(output.getvalue(), "animated.gif", "image/gif")
        self.assertEqual(result.info["source_frames"], 2)
        self.assertEqual(result.getpixel((0, 0)), (255, 0, 0))

    def test_sixty_samples_are_unique_and_keep_endpoints(self):
        samples = sample_indices(6000, 60)
        self.assertEqual(len(samples), 60)
        self.assertEqual((samples[0], samples[-1]), (0, 5999))
        self.assertEqual(samples, sorted(set(samples)))
        with self.assertRaises(MediaError):
            sample_indices(6000, 61)

    def test_video_chart_does_not_fabricate_uninferred_frames(self):
        result = SafetyExpertSystem().analyze([])
        chart = video_counts_chart(
            [
                {"index": 0, "result": result},
                {"index": 10, "result": None},
                {"index": 27, "result": result},
            ]
        )
        for trace in chart.data:
            self.assertEqual(list(trace.x), [0, 27])
            self.assertEqual(list(trace.y), [0, 0])
            self.assertEqual(trace.mode, "markers")


class RestoredUITests(IsolatedUITest):
    def app(self):
        from streamlit.testing.v1 import AppTest

        return AppTest.from_file(
            str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=60
        ).run()

    def test_boxes_control_preserves_history_and_parameters(self):
        app = self.app()
        self.assertTrue(app.checkbox(key="show_boxes").value)
        app.checkbox(key="show_boxes").uncheck().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state["history_v1a"], [])
        self.assertFalse(app.checkbox(key="show_boxes").value)

    def test_export_and_history_render_actual_fixture(self):
        app = self.app()
        app.session_state["history_v1a"] = [
            image_record("fixture.png", SafetyExpertSystem().analyze([]), None, 0.4)
        ]
        for page in ("Historial", "Exportar", "Resumen"):
            app.radio(key="navigation").set_value(page).run()
            if page == "Exportar":
                next(
                    s for s in app.selectbox if s.label == "Fuente de exportación"
                ).set_value("Sesión temporal").run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.session_state["history_v1a"]), 1)
            self.assertTrue(app.dataframe)

    def test_sidebar_help_and_photo_formats_are_visible(self):
        app = self.app()
        app.radio(key="navigation").set_value("Imágenes").run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(
            any("AVIF" in item.value and "TIFF" in item.value for item in app.caption)
        )
        self.assertTrue(any(item.label == "Cómo usar" for item in app.expander))
