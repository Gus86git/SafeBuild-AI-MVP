from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock
import hashlib
import json
import unittest
from safeguard.models import load_authorized_model, runtime_model


class AuthorizationTests(unittest.TestCase):
    def test_wrong_classes_rejected_after_authorized_load(self):
        with TemporaryDirectory() as root:
            self.artifact(
                root,
                {
                    "approved": True,
                    "sha256": hashlib.sha256(b"fixture-not-model").hexdigest(),
                    "source": "test",
                    "license": "test",
                    "expected_classes": ["person", "helmet", "vest"],
                },
            )
            factory = Mock(return_value=SimpleNamespace(names={0: "person"}))
            model, info, errors = load_authorized_model(factory, root)
            self.assertIsNone(model)
            self.assertTrue(errors)
            factory.assert_called_once()

    def artifact(self, root, record=None):
        path = Path(root) / "models"
        path.mkdir()
        (path / "best.pt").write_bytes(b"fixture-not-model")
        if record is not None:
            (path / "authorized.json").write_text(
                json.dumps({"models/best.pt": record}), encoding="utf-8"
            )

    def test_no_manifest_never_deserializes(self):
        factory = Mock()
        with TemporaryDirectory() as root:
            self.artifact(root)
            result = load_authorized_model(factory, root)
        self.assertIsNone(result[0])
        factory.assert_not_called()

    def test_wrong_hash_never_deserializes(self):
        factory = Mock()
        with TemporaryDirectory() as root:
            self.artifact(
                root,
                {
                    "approved": True,
                    "sha256": "wrong",
                    "source": "test",
                    "license": "test",
                },
            )
            self.assertIsNone(load_authorized_model(factory, root)[0])
        factory.assert_not_called()

    def test_missing_provenance_never_deserializes(self):
        factory = Mock()
        with TemporaryDirectory() as root:
            self.artifact(
                root,
                {
                    "approved": True,
                    "sha256": hashlib.sha256(b"fixture-not-model").hexdigest(),
                },
            )
            self.assertIsNone(load_authorized_model(factory, root)[0])
        factory.assert_not_called()

    def test_authorization_is_not_precision_validation(self):
        factory = Mock(return_value=SimpleNamespace(names={0: "person"}))
        with TemporaryDirectory() as root:
            self.artifact(
                root,
                {
                    "approved": True,
                    "sha256": hashlib.sha256(b"fixture-not-model").hexdigest(),
                    "source": "test fixture",
                    "license": "test only",
                },
            )
            model, info, errors = load_authorized_model(factory, root)
            self.assertIsNotNone(model)
            self.assertFalse(info["ppe_validated"])
            self.assertEqual(info["classes"], ["person"])
            self.assertEqual(info["provenance"], "test fixture")
            self.assertEqual(info["device"], "cpu")
            self.assertEqual(errors, [])

    def test_runtime_no_weights_no_external_dependency(self):
        with TemporaryDirectory() as root:
            self.assertIsNone(runtime_model(root)[0])
