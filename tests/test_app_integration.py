"""Integration with UI/CV/model doubles, not an end-to-end inference test.

Uses existing NumPy/Pillow/pandas/XlsxWriter; never starts a server or loads weights.
"""

from io import BytesIO, StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zipfile import ZipFile
import importlib.util
import runpy
import unittest
from ui_isolation import IsolatedUITest

AVAILABLE = all(
    importlib.util.find_spec(m) for m in ("numpy", "PIL", "pandas", "xlsxwriter")
)


class Session(dict):
    def __getattr__(self, key):
        return self[key]

    def __setattr__(self, key, value):
        self[key] = value


class UI:
    def __init__(self, mode, upload):
        self.mode, self.upload = mode, upload
        self.session_state = Session(
            history=[{"legacy": "preserved"}], model_requested=True
        )
        self.sidebar = self
        self.downloads = []
        self.metrics = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def set_page_config(self, **kwargs):
        pass

    def markdown(self, *args, **kwargs):
        pass

    def caption(self, *args, **kwargs):
        pass

    def write(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass

    def title(self, *args, **kwargs):
        pass

    def subheader(self, *args, **kwargs):
        pass

    def text(self, *args, **kwargs):
        pass

    def divider(self, *args, **kwargs):
        pass

    def video(self, *args, **kwargs):
        pass

    def container(self, **kwargs):
        return self

    def radio(self, *args, **kwargs):
        return "Imágenes" if self.mode == "image" else "Videos"

    def selectbox(self, label, options, **kwargs):
        return options[kwargs.get("index", 0)]

    def success(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass

    def image(self, *args, **kwargs):
        pass

    def dataframe(self, *args, **kwargs):
        pass

    def plotly_chart(self, *args, **kwargs):
        pass

    def json(self, *args, **kwargs):
        pass

    def empty(self):
        pass

    def stop(self):
        raise AssertionError("Unexpected st.stop")

    def cache_resource(self, **kwargs):
        return lambda fn: fn

    def spinner(self, *args):
        return self

    def expander(self, *args):
        return self

    def progress(self, *args):
        return self

    def tabs(self, names):
        return [self for _ in names]

    def columns(self, spec):
        return [self for _ in range(spec if isinstance(spec, int) else len(spec))]

    def checkbox(self, *args, **kwargs):
        return False

    def slider(self, label, low, high, value, *args, **kwargs):
        return value

    def button(self, label, **kwargs):
        if kwargs.get("disabled"):
            return False
        return (
            self.mode == "image"
            and label == "Analizar imagen"
            or self.mode == "video"
            and "fotogramas" in label
        )

    def file_uploader(self, label, **kwargs):
        if self.mode == "image" and "imagen" in label:
            return self.upload
        if self.mode == "video" and "video" in label:
            return self.upload
        return None

    def metric(self, label, value):
        self.metrics.append((label, value))

    def download_button(self, label, *, data, file_name, **kwargs):
        self.downloads.append(
            (file_name, data.getvalue() if hasattr(data, "getvalue") else data)
        )


@unittest.skipUnless(AVAILABLE, "Optional export/image dependencies absent")
class AppIntegrationTests(IsolatedUITest):
    def execute_app(self, mode, *, missing_model=False):
        import numpy as np
        from PIL import Image

        upload = BytesIO()
        Image.new("RGB", (400, 400)).save(upload, format="PNG")
        upload.seek(0)
        if mode == "video":
            upload = BytesIO(b"\x00\x00\x00\x18ftypmp42fixture")
        upload.name = "synthetic.png" if mode == "image" else "synthetic.mp4"
        upload.size = len(upload.getvalue())
        ui = UI(mode, upload)

        def box(label, bbox):
            tensor = SimpleNamespace(
                cpu=lambda: SimpleNamespace(numpy=lambda: np.array(bbox))
            )
            return SimpleNamespace(xyxy=[tensor], cls=[label], conf=[0.9])

        model = SimpleNamespace(
            names={0: "person", 1: "helmet", 2: "vest"},
            predict=Mock(
                return_value=[
                    SimpleNamespace(
                        boxes=[
                            box(0, [20, 100, 120, 300]),
                            box(1, [20, 100, 120, 150]),
                            box(2, [20, 150, 120, 250]),
                        ]
                    )
                ]
            ),
        )
        capture = Mock()
        capture.get.side_effect = lambda prop: 2 if prop == 1 else 25
        capture.isOpened.return_value = True
        capture.read.side_effect = [
            (True, np.zeros((400, 400, 3), dtype=np.uint8)),
            (True, np.zeros((400, 400, 3), dtype=np.uint8)),
            (False, None),
        ]
        cv = SimpleNamespace(
            COLOR_RGB2BGR=1,
            COLOR_BGR2RGB=2,
            COLOR_BGR2HSV=3,
            CAP_PROP_POS_MSEC=3,
            CAP_PROP_FRAME_COUNT=1,
            CAP_PROP_FPS=2,
            FONT_HERSHEY_SIMPLEX=0,
            cvtColor=lambda arr, *_: arr,
            inRange=lambda arr, *_: np.zeros(arr.shape[:2], dtype=np.uint8),
            rectangle=Mock(),
            getTextSize=lambda *args: ((20, 10), 0),
            putText=Mock(),
            VideoCapture=Mock(return_value=capture),
        )
        info = {
            "path": "fixture.pt",
            "sha256": "fixture",
            "classes": list(model.names.values()),
            "provenance": "No verificada",
            "license": "No verificada",
            "ppe_validated": False,
        }
        result = (None, None, []) if missing_model else (model, info, [])
        with (
            patch.dict(
                "sys.modules",
                {
                    "streamlit": ui,
                    "cv2": cv,
                    "ultralytics": SimpleNamespace(YOLO=Mock()),
                    "plotly": None,
                },
            ),
            patch("safeguard.models.runtime_model", return_value=result),
            patch("time.sleep"),
        ):
            namespace = runpy.run_path(
                str(Path(__file__).resolve().parents[1] / "app.py"), run_name="__main__"
            )
            namespace["history_page"](ui.session_state.history_v1a)
        return ui, cv, namespace

    def check_exports(self, ui, kind):
        import pandas as pd

        self.assertEqual(ui.session_state.history, [{"legacy": "preserved"}])
        self.assertEqual(len(ui.session_state.history_v1a), 1)
        record = ui.session_state.history_v1a[0]
        self.assertEqual(record["kind"], kind)
        self.assertIsNone(record["compliance"])
        downloads = dict(ui.downloads)
        csv = next(data for name, data in downloads.items() if name.endswith(".csv"))
        table = pd.read_csv(StringIO(csv.decode()), keep_default_na=False)
        self.assertEqual(table.iloc[0]["Cumplimiento"], "N/A")
        self.assertEqual(table.iloc[0]["SHA256"], "fixture")
        xlsx = next(data for name, data in downloads.items() if name.endswith(".xlsx"))
        with ZipFile(BytesIO(xlsx)) as archive:
            self.assertIsNone(archive.testzip())
            self.assertIn("N/A", archive.read("xl/sharedStrings.xml").decode())
        self.assertTrue(
            all(
                value == "N/A" for label, value in ui.metrics if "Cumplimiento" in label
            )
        )

    def test_image_to_history_csv_xlsx_with_doubles(self):
        ui, cv, _ = self.execute_app("image")
        self.check_exports(ui, "imagen")
        self.assertEqual(
            ui.session_state.history_v1a[0]["stats"]["associated_pairs"], 1
        )
        self.assertTrue(ui.session_state["image_result"]["png"].startswith(b"\x89PNG"))

    def test_video_to_descriptive_exports_with_doubles(self):
        ui, cv, _ = self.execute_app("video")
        self.check_exports(ui, "video")
        self.assertEqual(ui.session_state.history_v1a[0]["sample_count"], 2)
        cv.VideoCapture.return_value.release.assert_called_once()
        self.assertFalse(Path(cv.VideoCapture.call_args.args[0]).exists())

    def test_absent_model_has_no_fabricated_history(self):
        ui, _, _ = self.execute_app("image", missing_model=True)
        self.assertEqual(ui.session_state.history_v1a, [])
        self.assertEqual(ui.downloads, [])

    def test_sqlite_failure_preserves_image_for_retry(self):
        import sqlite3

        with patch(
            "safeguard.storage.save_analysis",
            side_effect=sqlite3.OperationalError("test lock"),
        ):
            ui, _, namespace = self.execute_app("image")
        self.assertEqual(ui.session_state.history_v1a, [])
        saved = ui.session_state["image_result"]
        self.assertFalse(saved["persisted"])
        self.assertTrue(saved["png"].startswith(b"\x89PNG"))
        self.assertTrue(any(name.endswith(".png") for name, _ in ui.downloads))
