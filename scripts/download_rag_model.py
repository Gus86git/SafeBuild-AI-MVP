"""One-time authorized download; no documents or queries are transmitted."""

from pathlib import Path
import argparse
import hashlib
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from safeguard.rag.embeddings import MODEL_ID, model_path
from safeguard.rag.indexing import atomic_json

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorized-download", action="store_true", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    destination = model_path(root)
    if (destination / "safeguard_model.json").is_file():
        print("Modelo ya preparado; no se descarga ni se reemplaza.")
        raise SystemExit(0)
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    from huggingface_hub import HfApi, snapshot_download

    revision = HfApi().model_info(MODEL_ID, token=False).sha
    snapshot_download(
        MODEL_ID,
        revision=revision,
        local_dir=str(destination),
        token=False,
        allow_patterns=["*.json", "*.txt", "*.model", "*.safetensors", "1_Pooling/*"],
        ignore_patterns=["onnx/*", "openvino/*"],
        max_workers=2,
    )
    files = {}
    for p in sorted(destination.rglob("*")):
        if p.is_file() and ".cache" not in p.parts:
            with p.open("rb") as stream:
                files[p.relative_to(destination).as_posix()] = hashlib.file_digest(
                    stream, "sha256"
                ).hexdigest()
    atomic_json(
        destination / "safeguard_model.json",
        {
            "model_id": MODEL_ID,
            "revision": revision,
            "files": files,
            "device": "cpu",
            "download_authorized": True,
            "downloaded_at": "2026-10-25",
            "encoding": "mean-token-windows-v1",
        },
    )
    print("Modelo preparado:", MODEL_ID, revision, "archivos:", len(files))
