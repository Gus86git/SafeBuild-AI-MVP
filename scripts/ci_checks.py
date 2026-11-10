"""Reproducible checks without private data, model downloads or provider calls."""

import argparse
import importlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUTPUT = ROOT / "output/ci"


def imports():
    for name in (
        "streamlit",
        "cv2",
        "numpy",
        "PIL",
        "pandas",
        "xlsxwriter",
        "plotly",
        "torch",
        "torchvision",
        "ultralytics",
        "pypdf",
        "rank_bm25",
        "chromadb",
        "sentence_transformers",
        "groq",
        "safeguard.storage",
        "safeguard.core",
        "safeguard.rag.indexing",
        "safeguard.copilot.service",
    ):
        importlib.import_module(name)
        print(f"Import OK: {name}")


def tests():
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    summary = {
        "run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": [
            {"test": str(test), "reason": reason} for test, reason in result.skipped
        ],
        "successful": result.wasSuccessful(),
    }
    (OUTPUT / "python-tests.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    if not result.wasSuccessful():
        raise SystemExit(1)


def smoke():
    with tempfile.TemporaryDirectory() as temporary:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        environment = dict(os.environ)
        environment.update(
            SAFEGUARD_DB_PATH=str(Path(temporary) / "smoke.sqlite3"),
            SAFEGUARD_MODEL_PATH=str(Path(temporary) / "absent.pt"),
            SAFEGUARD_RAG_PATH=str(Path(temporary) / "rag"),
            GROQ_API_KEY="",
            GROQ_MODEL="",
        )
        command = [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "app.py",
            "--server.address",
            "127.0.0.1",
            "--server.port",
            str(port),
            "--server.headless",
            "true",
            "--browser.gatherUsageStats",
            "false",
        ]
        with (OUTPUT / "startup.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                command, cwd=ROOT, env=environment, stdout=log, stderr=log
            )
            try:
                deadline = time.monotonic() + 45
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError("Streamlit exited before becoming healthy")
                    try:
                        with urlopen(
                            f"http://127.0.0.1:{port}/_stcore/health", timeout=2
                        ) as response:
                            if (
                                response.status == 200
                                and response.read().strip() == b"ok"
                            ):
                                print(
                                    "HTTP health OK; UI behavior is covered separately by AppTest."
                                )
                                return
                    except (URLError, TimeoutError, OSError):
                        time.sleep(0.5)
                raise TimeoutError("Streamlit startup exceeded 45 seconds")
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)


def resources():
    # These are intentionally not represented as successful model/provider tests.
    report = """# External validation scope

| Validation | Status | Reason |
|---|---|---|
| Real YOLO inference | NOT RUN | Authorized weights and images are not distributed. |
| Real corpus / embedding retrieval | NOT RUN | Corpus and embedding artifacts are provisioned separately. Synthetic retrieval tests still run. |
| Groq generation and STT | NOT RUN | No credentials or external-request authorization supplied to CI. |
| Physical microphone / audible TTS | NOT RUN | Requires an interactive browser and a human check. |
| Linux hosting capacity and persistence | NOT CERTIFIED | CI smoke is not a deployment or load test. |

Consult python-tests.json for every unittest skip and its reason. An omitted check is not a pass.
"""
    (OUTPUT / "resource-status.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("check", choices=("imports", "tests", "smoke", "resources"))
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    globals()[args.check]()
