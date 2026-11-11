"""Provision the bundled demo resources; never copy operational databases or keys."""

import hashlib
import json
import os
from pathlib import Path
import shutil
from threading import RLock
from urllib.request import urlopen
from uuid import uuid4

LOCK = RLock()
OVERRIDES = ("SAFEGUARD_MODEL_PATH", "SAFEGUARD_RAG_PATH", "SAFEGUARD_EMBEDDING_PATH")


def enabled(root):
    return (
        (Path(root) / "deployment_resources/checksums.json").is_file()
        and not any(os.environ.get(key) for key in OVERRIDES)
        and os.environ.get("SAFEGUARD_DISABLE_BOOTSTRAP") != "1"
    )


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_child(root, name):
    root = Path(root).resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Ruta de recurso fuera del directorio autorizado.")
    return path


def prepare(root):
    """Small, offline startup step. Custom installations and tests are untouched."""
    root = Path(root)
    if not enabled(root):
        return
    with LOCK:
        bundle = root / "deployment_resources"
        checks = json.loads((bundle / "checksums.json").read_text(encoding="utf8"))
        for name, expected in checks.items():
            if digest(safe_child(bundle, name)) != expected:
                raise ValueError("Integridad del paquete de recursos no válida.")
        mappings = {
            "epp-v1.pt": "models/epp_v1/best.pt",
            "model-authorization.json": "models/authorized.json",
            "documents.json": "data/rag/manifests/documents.json",
        }
        for name, relative in mappings.items():
            target = root / relative
            if target.exists():
                if digest(target) != checks[name]:
                    raise ValueError(
                        "Recurso local diferente: requiere revisión antes de sustituirlo."
                    )
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_name(target.name + "." + uuid4().hex + ".tmp")
            shutil.copyfile(bundle / name, temp)
            temp.replace(target)
        from safeguard.rag.indexing import build_index

        if not (root / "data/rag/indexes/corpus.json").exists():
            snapshot = build_index(
                root / mappings["documents.json"], root, root / "data/rag", root
            )
            if any(d["ingestion_status"] == "error" for d in snapshot["documents"]):
                raise ValueError("Hay documentos que no pudieron indexarse.")


def download_verified(url, target, expected):
    """Publish only complete hash-verified files. No provider credentials are sent."""
    target = Path(target)
    if target.is_file() and digest(target) == expected:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + "." + uuid4().hex + ".tmp")
    try:
        with urlopen(url, timeout=60) as response, temp.open("wb") as output:
            total = 0
            while block := response.read(1024 * 1024):
                total += len(block)
                if total > 700 * 1024 * 1024:
                    raise ValueError("Recurso superior al límite permitido.")
                output.write(block)
        if digest(temp) != expected:
            raise ValueError("Hash de descarga no válido.")
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)


def prepare_semantic(root):
    """Explicit UI action: pinned official embeddings, then local Chroma indexing."""
    root = Path(root)
    if not enabled(root):
        return
    with LOCK:
        prepare(root)
        from safeguard.rag.indexing import build_index, load_snapshot

        snapshot = load_snapshot(root / "data/rag")
        identity = json.loads(
            (root / "deployment_resources/embedding-manifest.json").read_text(
                encoding="utf8"
            )
        )
        if (
            identity["model_id"]
            != "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        ):
            raise ValueError("Modelo de embeddings no permitido.")
        import re

        if not re.fullmatch(r"[0-9a-f]{40}", identity["revision"]):
            raise ValueError("Revisión no válida.")
        destination = root / "models/embeddings/minilm-multilingual"
        for name, expected in identity["files"].items():
            target = safe_child(destination, name)
            from urllib.parse import quote

            url = f"https://huggingface.co/{identity['model_id']}/resolve/{identity['revision']}/{quote(name)}"
            download_verified(url, target, expected)
        (destination / "safeguard_model.json").write_text(
            json.dumps(identity, ensure_ascii=False, indent=2), encoding="utf8"
        )
        if not snapshot.get("vector"):
            build_index(
                root / "data/rag/manifests/documents.json",
                root,
                root / "data/rag",
                root,
                with_vectors=True,
            )
