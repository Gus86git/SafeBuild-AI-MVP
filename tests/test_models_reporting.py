from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import hashlib
import unittest
from unittest.mock import Mock
from safeguard.core import SafetyExpertSystem, summarize_video
from safeguard.models import load_local_model
from safeguard.reporting import export_rows


class ModelTests(unittest.TestCase):
    def test_missing_files_never_invoke_loader(self):
        factory = Mock()
        with TemporaryDirectory() as root:
            self.assertEqual(load_local_model(factory, root), (None, None, []))
        factory.assert_not_called()

    def test_hash_classes_and_unknown_provenance(self):
        with TemporaryDirectory() as root:
            path = Path(root) / "yolov8n.pt"
            path.write_bytes(b"fixture-not-real-weights")
            factory = Mock(return_value=SimpleNamespace(names={0: "person"}))
            _, info, errors = load_local_model(factory, root)
            factory.assert_called_once_with(str(path.resolve()))
            self.assertEqual(
                info["sha256"], hashlib.sha256(path.read_bytes()).hexdigest()
            )
            self.assertEqual(info["classes"], ["person"])
            self.assertFalse(info["ppe_validated"])
            self.assertEqual(info["provenance"], "No verificada")
            self.assertEqual(errors, [])

    def test_failed_local_model_does_not_download_fallback(self):
        with TemporaryDirectory() as root:
            (Path(root) / "models").mkdir()
            (Path(root) / "models/best.pt").write_bytes(b"fixture")
            factory = Mock(side_effect=ValueError("private path not exposed"))
            model, info, errors = load_local_model(factory, root)
            self.assertIsNone(model)
            self.assertIsNone(info)
            self.assertEqual(errors, ["models/best.pt: ValueError"])
            self.assertEqual(factory.call_count, 1)

    def test_local_fallback_preserves_error(self):
        with TemporaryDirectory() as root:
            (Path(root) / "models").mkdir()
            (Path(root) / "models/best.pt").write_bytes(b"broken")
            (Path(root) / "yolov8n.pt").write_bytes(b"fixture")
            factory = Mock(
                side_effect=[ValueError(), SimpleNamespace(names=["person"])]
            )
            _, info, errors = load_local_model(factory, root)
            self.assertEqual(info["path"], "yolov8n.pt")
            self.assertEqual(len(errors), 1)


class ReportingTests(unittest.TestCase):
    def test_mixed_history_na_units_and_trace(self):
        image = SafetyExpertSystem().analyze([])
        video = summarize_video([[], []])
        history = [
            dict(
                result,
                ts=datetime(2026, 10, 14),
                file="example",
                kind=kind,
                threshold=0.4,
                model={"path": "local", "sha256": "fixture"},
            )
            for result, kind in [(image, "imagen"), (video, "video")]
        ]
        rows = export_rows(history)
        self.assertTrue(all(r["Cumplimiento"] == "N/A" for r in rows))
        self.assertEqual(rows[0]["Unidad"], "detecciones por imagen")
        self.assertEqual(rows[1]["Unidad"], "promedio por muestra")
        self.assertEqual(rows[1]["Muestras"], 2)
        self.assertEqual(rows[0]["SHA256"], "fixture")
        self.assertNotIn("Riesgo_Altura", rows[0])
