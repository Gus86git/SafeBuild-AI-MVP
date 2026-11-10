"""Streamlit integration on isolated fixtures; no real model or operational DB."""

from pathlib import Path
import os
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from ui_isolation import IsolatedUITest
from safeguard.rag.indexing import build_index, atomic_json

APP = str(Path(__file__).resolve().parents[1] / "app.py")


class RagUITests(IsolatedUITest):
    def test_missing_corpus_keeps_app_operational(self):
        with patch.dict(
            os.environ, {"SAFEGUARD_RAG_PATH": str(Path(self.sandbox.name) / "empty")}
        ):
            app = AppTest.from_file(APP).run(timeout=30)
            app.radio(key="navigation").set_value("Copilot · Conocimiento").run(
                timeout=30
            )
            self.assertFalse(app.exception)
            self.assertTrue(any("sin preparar" in w.value for w in app.warning))
            app.radio(key="navigation").set_value("Resumen").run(timeout=30)
            self.assertFalse(app.exception)

    def test_search_citations_and_source_filter(self):
        root = Path(self.sandbox.name)
        (root / "a.txt").write_text(
            "casco entrega registro proteccion trabajador", encoding="utf8"
        )
        (root / "b.txt").write_text(
            "TechCorp simulacion procedimiento emergencia", encoding="utf8"
        )
        entries = [
            {
                "document_id": name,
                "filename": name + ".txt",
                "title": name,
                "source_type": typ,
                "is_synthetic": typ.startswith("simulated"),
                "approved": True,
                "document_version": "fixture",
                "content_status": "fixture",
            }
            for name, typ in [("a", "official"), ("b", "simulated_manual")]
        ]
        atomic_json(root / "manifest.json", entries)
        build_index(root / "manifest.json", root, root / "rag", root)
        with patch.dict(os.environ, {"SAFEGUARD_RAG_PATH": str(root / "rag")}):
            app = AppTest.from_file(APP).run(timeout=30)
            app.radio(key="navigation").set_value("Copilot · Conocimiento").run(
                timeout=30
            )
            app.text_input(key="rag_question").set_value("casco")
            app.button(key="rag_search").click().run(timeout=30)
            self.assertFalse(app.exception)
            self.assertTrue(any("Fragmento" in t.value for t in app.text))
            app.multiselect(key="rag_sources").set_value(["simulated_manual"])
            app.button(key="rag_search").click().run(timeout=30)
            self.assertTrue(any("No se encontró" in t.value for t in app.info))
