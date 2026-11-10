"""Real local YOLO -> SQLite -> contextual Streamlit -> RAG smoke test.

AppTest cannot upload files: only its upload control is supplied with the authorized
local image bytes. Model, inference, storage, retrieval and navigation are real.
The operational database is copied, never used as the test write target. No Groq.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import hashlib
import argparse
import json
import os
import sqlite3
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from ui_isolation import submit_copilot
from streamlit.testing.v1 import AppTest
from safeguard.storage import database_path
from safeguard.copilot.operational import readonly
from safeguard.copilot.ui import CONTEXT_EXAMPLES


def digest(path):
    with readonly(path) as db:
        return hashlib.sha256("\n".join(db.iterdump()).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=ROOT / "output/verification-fase2d"
    )
    parser.add_argument(
        "--image", type=Path, default=ROOT / "output/colab-imagen-aportada.png"
    )
    args = parser.parse_args()
    source = database_path(ROOT)
    before = digest(source)
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    target = output / "verification.sqlite3"
    if target.exists():
        raise RuntimeError(
            "La evidencia ya existe. Use una nueva carpeta antes de repetir; no se sobrescribe la base de prueba."
        )
    with sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True) as db:
        with sqlite3.connect(target) as dest:
            db.backup(dest)
    data = args.image.read_bytes()
    upload = SimpleNamespace(
        name="imagen_aportada.png", type="image/png", getvalue=lambda: data
    )

    def file_input(*args, **kwargs):
        return upload if kwargs.get("key") == "image_upload" else None

    began = perf_counter()
    env = {"SAFEGUARD_DB_PATH": str(target)}
    results = []
    extra_pages = []
    app_started = perf_counter()
    with (
        patch.dict(os.environ, env),
        patch("streamlit.file_uploader", side_effect=file_input),
        patch("safeguard.copilot.ui.AnswerGenerator") as generator,
    ):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90).run()
        initial_render_seconds = perf_counter() - app_started
        app.selectbox(key="site").set_value("OBRA-NORTE-001").run()
        app.radio(key="navigation").set_value("Imágenes").run()
        app.button(key="load_model").click().run()
        assert not app.button(key="analyze_image").disabled, "Local model unavailable"
        app.button(key="analyze_image").click().run()
        assert not app.exception, str(app.exception)
        image_result = app.session_state["image_result"]
        identifier = image_result["analysis_id"]
        stats = image_result["result"]["stats"]
        assert image_result["persisted"]
        with readonly(target) as db:
            count = db.execute("SELECT count(*) FROM analyses").fetchone()[0]
        app.run()
        with readonly(target) as db:
            assert db.execute("SELECT count(*) FROM analyses").fetchone()[0] == count
        app.button(key="image_result_copilot").click().run()
        assert app.radio(key="navigation").value == "Copilot · Asistente"
        assert app.session_state["copilot_selection"]["analysis_id"] == identifier
        assert not app.session_state.get("model_requested", False)
        for question, kind in zip(
            CONTEXT_EXAMPLES,
            [
                "operational",
                "operational",
                "operational",
                "documentary",
                "combined",
                "insufficient",
            ],
        ):
            submit_copilot(app, question)
            assert not app.exception, str(app.exception)
            p = app.session_state["copilot_history"][-1]
            assert p["routing"]["kind"] == kind
            if p["sql"]:
                assert p["sql"]["selected_analysis"]["id"] == identifier
                with readonly(target) as db:
                    expected = db.execute(
                        "SELECT count(*) FROM observations WHERE analysis_id=?",
                        (identifier,),
                    ).fetchone()[0]
                    expected_boxes = db.execute(
                        "SELECT count(*) FROM detections WHERE analysis_id=?",
                        (identifier,),
                    ).fetchone()[0]
                    assert expected == p["sql"]["facts"]["observations"]
                    assert expected_boxes == sum(
                        r["count"] for r in p["sql"]["detection_categories"]
                    )
            if kind in ("documentary", "combined"):
                assert any(c["document_id"] == "TC-PRO-003" for c in p["documents"])
                assert all(c["is_synthetic"] for c in p["documents"])
            results.append(
                {
                    "question": question,
                    "kind": kind,
                    "status": p["status"],
                    "facts": p["sql"]["facts"] if p["sql"] else None,
                    "latency_seconds": p["latency_seconds"],
                    "sources": [
                        {
                            "document_id": c["document_id"],
                            "chunk_id": c["chunk_id"],
                            "locator": c["locator"],
                        }
                        for c in p["documents"]
                    ],
                }
            )
        app.button(key="copilot_back_image").click().run()
        assert not app.exception, str(app.exception)
        assert app.radio(key="navigation").value == "Imágenes"
        assert app.session_state["copilot_selection"]["analysis_id"] == identifier
        for page in ("Resumen", "Historial", "Exportar"):
            app.radio(key="navigation").set_value(page).run()
            assert not app.exception, str(app.exception)
            extra_pages.append(page)
        assert app.get("download_button"), "Export controls missing"
        from safeguard import storage
        from safeguard.reporting import csv_bytes, excel_bytes

        records = storage.history(
            target, "TECHCORP-DEMO", "OBRA-NORTE-001", "real_inference"
        )
        exported = csv_bytes(records)
        assert identifier in exported.decode("utf-8-sig")
        (output / "verified-export.csv").write_bytes(exported)
        (output / "verified-export.xlsx").write_bytes(excel_bytes(records))
        reopened = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90).run()
        reopened.radio(key="navigation").set_value("Historial").run()
        assert not reopened.exception, str(reopened.exception)
        with readonly(target) as db:
            assert db.execute("SELECT count(*) FROM analyses").fetchone()[0] == count
        generator.assert_not_called()
    assert before == digest(source), "User database changed"
    result = {
        "real_yolo": True,
        "real_sqlite": True,
        "real_rag": True,
        "streamlit_apptest": True,
        "browser_visual_check": False,
        "groq_called": False,
        "user_database_unchanged": True,
        "rerun_no_duplicate": True,
        "back_navigation": True,
        "initial_apptest_render_seconds": initial_render_seconds,
        "extra_pages_verified": extra_pages,
        "export_controls_rendered": True,
        "export_files_cotejados": True,
        "browser_download_not_tested": True,
        "new_session_persistence": True,
        "analysis_id": identifier,
        "stats": stats,
        "input_provenance": "supplied image; real/synthetic scene unverified",
        "inference_seconds": image_result["result"]["performance"],
        "total_smoke_seconds": perf_counter() - began,
        "queries": results,
    }
    (output / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
