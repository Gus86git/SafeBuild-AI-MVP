from pathlib import Path
from unittest.mock import patch
import os
from streamlit.testing.v1 import AppTest
from ui_isolation import IsolatedUITest, submit_copilot
from safeguard.rag.indexing import build_index, atomic_json
from safeguard.copilot.ui import EXAMPLES

APP = str(Path(__file__).resolve().parents[1] / "app.py")


class CopilotUITests(IsolatedUITest):
    def prepare(self):
        root = Path(self.sandbox.name)
        (root / "manual.txt").write_text(
            "TechCorp procedimiento observaciones inteligencia artificial revision humana. Revisar observaciones y registrar evidencia.",
            encoding="utf8",
        )
        atomic_json(
            root / "manifest.json",
            [
                {
                    "document_id": "TC-PRO-003",
                    "filename": "manual.txt",
                    "title": "Procedimiento ficticio",
                    "source_type": "simulated_procedure",
                    "is_synthetic": True,
                    "approved": True,
                    "document_version": "test",
                    "content_status": "academic_simulation",
                }
            ],
        )
        build_index(root / "manifest.json", root, root / "rag", root)
        return root

    def test_three_modalities_session_and_no_network(self):
        root = self.prepare()
        with (
            patch.dict(
                os.environ,
                {"SAFEGUARD_RAG_PATH": str(root / "rag"), "GROQ_API_KEY": ""},
            ),
            patch("safeguard.copilot.ui.AnswerGenerator") as generator,
        ):
            app = AppTest.from_file(APP).run(timeout=30)
            app.radio(key="navigation").set_value("Copilot · Asistente").run(timeout=30)
            app.selectbox(key="site").set_value("OBRA-NORTE-001").run(timeout=30)
            for question, kind in zip(
                EXAMPLES[:3], ["documentary", "operational", "combined"]
            ):
                submit_copilot(app, question)
                self.assertFalse(app.exception)
                latest = app.session_state["copilot_history"][-1]
                self.assertEqual(latest["routing"]["kind"], kind)
                self.assertEqual(latest["status"], "grounded")
            generator.assert_not_called()
            self.assertEqual(len(app.session_state["copilot_history"]), 3)
            app.selectbox(key="site").set_value("OBRA-SUR-002").run(timeout=30)
            self.assertEqual(app.session_state["copilot_history"], [])
            app.radio(key="navigation").set_value("Imágenes").run(timeout=30)
            self.assertFalse(app.exception)
            self.assertNotIn("copilot_retriever", app.session_state)

    def test_missing_corpus_keeps_operational_queries(self):
        with patch.dict(
            os.environ, {"SAFEGUARD_RAG_PATH": str(Path(self.sandbox.name) / "empty")}
        ):
            app = AppTest.from_file(APP).run(timeout=30)
            app.radio(key="navigation").set_value("Copilot · Asistente").run(timeout=30)
            submit_copilot(app, "Cuántas observaciones registradas")
            self.assertFalse(app.exception)
            self.assertEqual(
                app.session_state["copilot_history"][-1]["sql"]["facts"][
                    "observations"
                ],
                0,
            )
