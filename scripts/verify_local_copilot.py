"""Explicit local evidence/UI smoke test. Does not call Groq or write operational records."""

from pathlib import Path
import json
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from ui_isolation import submit_copilot
from safeguard.copilot.ui import EXAMPLES
from safeguard.copilot.operational import readonly
from safeguard.storage import database_path
from streamlit.testing.v1 import AppTest


def digest(path):
    import hashlib

    with readonly(path) as con:
        return hashlib.sha256("\n".join(con.iterdump()).encode()).hexdigest()


def main():
    path = database_path(ROOT)
    before = digest(path)
    results = []
    with patch("safeguard.copilot.ui.AnswerGenerator") as generator:
        app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=60)
        app.radio(key="navigation").set_value("Copilot · Asistente").run(timeout=60)
        app.selectbox(key="site").set_value("OBRA-NORTE-001").run(timeout=60)
        for question in EXAMPLES:
            submit_copilot(app, question)
            assert not app.exception, str(app.exception)
            p = app.session_state["copilot_history"][-1]
            facts = p["sql"]["facts"] if p["sql"] else None
            if facts:
                with readonly(path) as db:
                    expected = db.execute(
                        "SELECT count(*) FROM observations o JOIN analyses a ON a.id=o.analysis_id WHERE a.company_id=? AND a.site_id=? AND a.origin=?",
                        ("TECHCORP-DEMO", "OBRA-NORTE-001", "real_inference"),
                    ).fetchone()[0]
                    assert expected == facts["observations"]
            results.append(
                {
                    "question": question,
                    "kind": p["routing"]["kind"],
                    "status": p["status"],
                    "facts": facts,
                    "documents": [
                        {
                            "id": c["document_id"],
                            "chunk_id": c["chunk_id"],
                            "locator": c["locator"],
                        }
                        for c in p["documents"]
                    ],
                    "latency_seconds": p["latency_seconds"],
                    "warnings": p["warnings"],
                }
            )
        generator.assert_not_called()
    assert before == digest(path), "Operational database changed"
    output = {
        "streamlit_apptest": True,
        "database_unchanged": True,
        "groq_called": False,
        "queries": results,
    }
    target = ROOT / "output/evaluacion-fase2c.json"
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
