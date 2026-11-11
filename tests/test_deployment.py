import hashlib
import io
import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from safeguard.deployment import download_verified, enabled, prepare, safe_child


class DeploymentTests(unittest.TestCase):
    def test_bundled_documents_prepare_offline_and_repeat_safely(self):
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {}, clear=True):
            root = Path(tmp)
            shutil.copytree(
                Path(__file__).resolve().parents[1] / "deployment_resources",
                root / "deployment_resources",
            )
            with patch("safeguard.deployment.urlopen") as network:
                prepare(root)
                prepare(root)
            network.assert_not_called()
            snapshot = json.loads(
                (root / "data/rag/indexes/corpus.json").read_text(encoding="utf8")
            )
            self.assertEqual(len(snapshot["documents"]), 15)
            self.assertGreater(len(snapshot["chunks"]), 0)
            self.assertTrue(
                all(d["ingestion_status"] == "indexed" for d in snapshot["documents"])
            )
            self.assertIsNone(snapshot["vector"])
            self.assertFalse(list(root.rglob("*.sqlite3")))

    def test_path_escape_rejected(self):
        with TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                safe_child(tmp, "../outside")

    def test_custom_resources_disable_bootstrap(self):
        with patch.dict("os.environ", {"SAFEGUARD_RAG_PATH": "custom"}):
            self.assertFalse(enabled(Path(__file__).resolve().parents[1]))

    def test_download_hash_failure_never_published(self):
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "model"
            with patch(
                "safeguard.deployment.urlopen", return_value=io.BytesIO(b"wrong")
            ):
                with self.assertRaises(ValueError):
                    download_verified("https://example.invalid", target, "0" * 64)
            self.assertFalse(target.exists())
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_download_verified_and_reused_without_network(self):
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "model"
            expected = hashlib.sha256(b"valid").hexdigest()
            with patch(
                "safeguard.deployment.urlopen", return_value=io.BytesIO(b"valid")
            ) as fetch:
                download_verified("https://example.invalid", target, expected)
                download_verified("https://example.invalid", target, expected)
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(target.read_bytes(), b"valid")

    def test_tampered_bundle_rejected_before_copy(self):
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {}, clear=True):
            bundle = Path(tmp) / "deployment_resources"
            bundle.mkdir()
            (bundle / "file").write_bytes(b"bad")
            (bundle / "checksums.json").write_text(json.dumps({"file": "0" * 64}))
            with self.assertRaises(ValueError):
                prepare(tmp)
            self.assertFalse((Path(tmp) / "models").exists())
