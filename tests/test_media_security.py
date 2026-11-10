from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock
import unittest
import importlib.util

from safeguard.media import (
    MediaError,
    read_image,
    png_bytes,
    video_format,
    sample_indices,
    explore_video,
    check_size,
    check_dimensions,
)
from safeguard.reporting import safe_cell, csv_bytes, excel_bytes, person_rows
from safeguard.workflow import image_record, video_record
from safeguard.core import SafetyExpertSystem

HAS_IMAGE = all(importlib.util.find_spec(m) for m in ("numpy", "PIL"))


@unittest.skipUnless(HAS_IMAGE, "Pillow/NumPy required")
class ImageTests(unittest.TestCase):
    def fixture(self):
        from PIL import Image

        return png_bytes(Image.new("RGB", (64, 48), "red"))

    def test_real_image_roundtrip(self):
        image = read_image(self.fixture(), "test.png", "image/png")
        self.assertEqual(image.size, (64, 48))
        self.assertEqual(image.mode, "RGB")

    def test_corrupt_image(self):
        with self.assertRaises(MediaError):
            read_image(b"invalid", "bad.png")

    def test_mime_mismatch(self):
        with self.assertRaises(MediaError):
            read_image(self.fixture(), "test.png", "image/jpeg")

    def test_extension_mismatch(self):
        with self.assertRaises(MediaError):
            read_image(self.fixture(), "test.jpg")

    def test_empty_and_excess_bytes(self):
        with self.assertRaises(MediaError):
            check_size(b"", 10)
        with self.assertRaises(MediaError):
            check_size(b"123", 2)

    def test_dimension_limits(self):
        with self.assertRaises(MediaError):
            check_dimensions(8193, 10)
        with self.assertRaises(MediaError):
            check_dimensions(5000, 5000)

    def test_exif_orientation(self):
        from PIL import Image

        image = Image.new("RGB", (80, 40))
        exif = Image.Exif()
        exif[274] = 6
        stream = BytesIO()
        image.save(stream, format="JPEG", exif=exif)
        self.assertEqual(read_image(stream.getvalue(), "test.jpg").size, (40, 80))

    def test_png_annotation_preserves_source(self):
        from PIL import Image
        from safeguard.vision import draw_boxes

        image = Image.new("RGB", (100, 100), "black")
        result = draw_boxes(
            image,
            [{"class": "person", "confidence": 0.9, "bbox": [10, 10, 90, 90]}],
            0.4,
        )
        self.assertEqual(image.getpixel((10, 10)), (0, 0, 0))
        self.assertNotEqual(result.getpixel((10, 10)), (0, 0, 0))
        self.assertEqual(read_image(png_bytes(result), "result.png").size, (100, 100))


@unittest.skipUnless(HAS_IMAGE, "Pillow/NumPy required")
class VideoTests(unittest.TestCase):
    data = b"\x00\x00\x00\x18ftypmp42fixture"

    def fixture(self, total=10, fps=10):
        import numpy as np

        capture = Mock()
        capture.isOpened.return_value = True
        capture.get.side_effect = lambda prop: {1: total, 2: fps, 3: 0}[prop]
        capture.read.side_effect = [
            (True, np.zeros((24, 32, 3), dtype=np.uint8)) for _ in range(total)
        ]
        cv = SimpleNamespace(
            CAP_PROP_FRAME_COUNT=1,
            CAP_PROP_FPS=2,
            CAP_PROP_POS_MSEC=3,
            COLOR_BGR2RGB=1,
            cvtColor=lambda a, *_: a,
            VideoCapture=Mock(return_value=capture),
        )
        return cv, capture

    def test_sampling_includes_tail_original_indices(self):
        self.assertEqual(sample_indices(100, 3), [0, 50, 99])
        cv, cap = self.fixture()
        result = explore_video(self.data, "x.mp4", count=3, cv_module=cv)
        self.assertEqual([s["index"] for s in result["samples"]], [0, 4, 9])
        self.assertEqual(result["omitted"], 7)
        self.assertFalse(result["inference_ran"])
        self.assertTrue(
            all(
                s["result"] is None and s["annotated_png"] is None
                for s in result["samples"]
            )
        )
        cap.release.assert_called_once()
        self.assertFalse(Path(cv.VideoCapture.call_args.args[0]).exists())

    def test_estimated_time_labeled(self):
        cv, _ = self.fixture()
        result = explore_video(self.data, "x.mp4", count=2, cv_module=cv)
        sample = result["samples"][-1]
        self.assertEqual(sample["seconds"], 0.9)
        self.assertEqual(sample["time_kind"], "Estimada por índice/FPS")

    def test_unknown_fps_no_fabricated_time(self):
        cv, _ = self.fixture(fps=0)
        result = explore_video(self.data, "x.mp4", count=2, cv_module=cv)
        self.assertIsNone(result["samples"][-1]["seconds"])
        self.assertEqual(result["samples"][-1]["time_kind"], "No disponible")

    def test_cleanup_on_decoder_failure(self):
        cv, cap = self.fixture()
        cap.read.side_effect = [(False, None)]
        with TemporaryDirectory() as directory:
            with self.assertRaises(MediaError):
                explore_video(self.data, "x.mp4", cv_module=cv, temp_dir=directory)
            self.assertEqual(list(Path(directory).iterdir()), [])
        cap.release.assert_called_once()

    def test_cleanup_on_inference_failure(self):
        cv, cap = self.fixture()
        with TemporaryDirectory() as directory:
            with self.assertRaises(MediaError):
                explore_video(
                    self.data,
                    "x.mp4",
                    cv_module=cv,
                    temp_dir=directory,
                    analyzer=Mock(side_effect=RuntimeError("fixture failure")),
                )
            self.assertEqual(list(Path(directory).iterdir()), [])
        cap.release.assert_called_once()

    def test_cleanup_when_open_fails(self):
        cv, cap = self.fixture()
        cap.isOpened.return_value = False
        with TemporaryDirectory() as directory:
            with self.assertRaises(MediaError):
                explore_video(self.data, "x.mp4", cv_module=cv, temp_dir=directory)
            self.assertEqual(list(Path(directory).iterdir()), [])
        cap.release.assert_called_once()

    def test_cleanup_when_capture_constructor_raises(self):
        cv, _ = self.fixture()
        cv.VideoCapture.side_effect = RuntimeError()
        with TemporaryDirectory() as directory:
            with self.assertRaises(MediaError):
                explore_video(self.data, "x.mp4", cv_module=cv, temp_dir=directory)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_duration_and_processing_budget(self):
        cv, _ = self.fixture(total=10, fps=0.01)
        with self.assertRaises(MediaError):
            explore_video(self.data, "x.mp4", cv_module=cv)
        cv, _ = self.fixture()
        with self.assertRaises(MediaError):
            explore_video(self.data, "x.mp4", cv_module=cv, max_elapsed=-1)

    def test_format_and_mime_checks(self):
        with self.assertRaises(MediaError):
            video_format(b"not a video", "x.mp4")
        with self.assertRaises(MediaError):
            video_format(self.data, "x.avi")
        with self.assertRaises(MediaError):
            video_format(self.data, "x.mp4", "image/png")

    def test_no_analysis_record_without_inference(self):
        cv, _ = self.fixture()
        exploration = explore_video(self.data, "x.mp4", cv_module=cv)
        with self.assertRaises(ValueError):
            video_record("x.mp4", exploration, None, 0.4)


class ExportSecurityTests(unittest.TestCase):
    def record(self, name):
        return image_record(name, SafetyExpertSystem().analyze([]), None, 0.4)

    def test_formula_prefixes(self):
        for value in (
            "=1+1",
            "+SUM(A1:A2)",
            "-1+1",
            "@SUM(1)",
            "  =2",
            "\t=2",
            "\x00=3",
            "\rtest",
        ):
            with self.subTest(value=value):
                self.assertTrue(safe_cell(value).startswith("'"))
        self.assertEqual(safe_cell("normal.png"), "normal.png")
        self.assertEqual(safe_cell(-2), -2)

    def test_csv_roundtrip_and_formula_neutralization(self):
        import csv
        from io import StringIO

        data = csv_bytes([self.record('=HYPERLINK("https://example.com")')])
        row = next(csv.DictReader(StringIO(data.decode("utf-8-sig"))))
        self.assertTrue(row["Archivo"].startswith("'="))
        self.assertEqual(row["Cumplimiento"], "N/A")

    @unittest.skipUnless(importlib.util.find_spec("xlsxwriter"), "XlsxWriter required")
    def test_excel_contains_no_formula_or_external_link(self):
        from zipfile import ZipFile

        with ZipFile(BytesIO(excel_bytes([self.record("=1+1")]))) as archive:
            xml = archive.read("xl/worksheets/sheet1.xml").decode()
            self.assertNotIn("<f>", xml)
            self.assertNotIn("hyperlink", xml)
            self.assertIn("'=1+1", archive.read("xl/sharedStrings.xml").decode())

    @unittest.skipUnless(importlib.util.find_spec("xlsxwriter"), "XlsxWriter required")
    def test_excel_does_not_silently_truncate(self):
        with self.assertRaises(ValueError):
            excel_bytes([self.record("a" * 32768)])

    def test_person_presentation_resolves_ids(self):
        d = lambda c, b: {"class": c, "bbox": b, "confidence": 0.9}
        result = SafetyExpertSystem().analyze(
            [d("person", [10, 10, 100, 210]), d("helmet", [20, 10, 60, 40])]
        )
        row = person_rows(result)[0]
        self.assertIn("ID 1", row["Casco"])
        self.assertIn("0.90", row["Casco"])
        self.assertEqual(row["Chaleco"], "Sin asociación verificable")
