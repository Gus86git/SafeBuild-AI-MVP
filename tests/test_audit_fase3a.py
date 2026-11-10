from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest
from unittest.mock import Mock
from safeguard import storage
from safeguard.copilot.generation import (
    external_package,
    AnswerGenerator,
    build_request,
)
from test_copilot import package


class AuditTests(unittest.TestCase):
    def test_compatible_schema_read_only(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "db.sqlite3"
            storage.initialize(path)
            before = path.read_bytes()
            storage.validate_schema(path)
            self.assertEqual(before, path.read_bytes())

    def test_future_schema_preserved(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "db.sqlite3"
            storage.initialize(path)
            with storage.connect(path) as db:
                db.execute("PRAGMA user_version=99")
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                storage.validate_schema(path)
            self.assertEqual(before, path.read_bytes())

    def test_incomplete_schema_rejected(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "db.sqlite3"
            with storage.connect(path) as db:
                db.execute("PRAGMA user_version=1")
            with self.assertRaises(ValueError):
                storage.validate_schema(path)

    def test_missing_schema_does_not_create_db(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "missing.sqlite3"
            with self.assertRaises(sqlite3.OperationalError):
                storage.validate_schema(path)
            self.assertFalse(path.exists())

    def test_key_like_question_blocked_before_network(self):
        obj = package()
        obj["question"] = "consulta " + "gsk_" + "a" * 40
        factory = Mock()
        result = AnswerGenerator("test", "test", factory).generate(obj, True)
        self.assertEqual(result["state"], "sensitive_question")
        factory.assert_not_called()

    def test_key_like_document_blocked(self):
        obj = package()
        obj["documents"] = [
            {
                "is_synthetic": True,
                "source_type": "simulated_manual",
                "chunk_id": "fixture",
                "text": "gsk_" + "a" * 40,
                "title": "fixture",
                "locator": "fixture",
            }
        ]
        with self.assertRaisesRegex(ValueError, "sensitive_content"):
            external_package(obj, True)

    def test_fixed_rag_labels_are_distinct_and_complete(self):
        import json

        root = Path(__file__).resolve().parents[1]
        new = json.loads(
            (root / "tests/fixtures/rag_fase3a.json").read_text(encoding="utf8")
        )
        old = json.loads(
            (root / "tests/fixtures/rag_evaluation.json").read_text(encoding="utf8")
        )
        self.assertFalse({c["question"] for c in new} & {c["question"] for c in old})
        self.assertEqual(len(new), 16)
        self.assertTrue(
            all(bool(c["chunk_prefixes"]) == bool(c["expected_documents"]) for c in new)
        )

    def test_api_diagnostics_do_not_echo_error_body(self):
        error = type("BadRequestError", (Exception,), {})("private-body")
        error.status_code = 400
        error.body = {
            "error": {"code": "json_validate_failed", "message": "private-body"}
        }
        client = Mock()
        client.models.list.side_effect = error
        result = AnswerGenerator("test", "test", Mock(return_value=client)).generate(
            package(), True
        )
        self.assertEqual(result["http_status"], 400)
        self.assertEqual(result["provider_code"], "json_validate_failed")
        self.assertNotIn("private-body", str(result))

    def test_supported_model_strict_request_and_citation_allowlist(self):
        evidence = external_package(package(), True)
        request = build_request("openai/gpt-oss-20b", evidence)
        schema = request["response_format"]["json_schema"]
        self.assertTrue(schema["strict"])
        self.assertFalse(schema["schema"]["additionalProperties"])
        self.assertEqual(
            schema["schema"]["properties"]["source_ids"]["items"]["enum"],
            evidence["source_ids"],
        )
        self.assertEqual(request["reasoning_effort"], "low")

    def test_other_models_keep_json_object_without_unsupported_options(self):
        request = build_request("test-model", external_package(package(), True))
        self.assertEqual(request["response_format"], {"type": "json_object"})
        self.assertNotIn("reasoning_effort", request)
