"""Offline-only CPU embeddings; downloading is a separate explicit preparation step."""

from hashlib import sha256
from pathlib import Path
from threading import RLock
import json
import os

MODEL_ID = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class EmbeddingUnavailable(RuntimeError):
    pass


def model_path(root):
    return Path(
        os.environ.get(
            "SAFEGUARD_EMBEDDING_PATH",
            str(Path(root) / "models/embeddings/minilm-multilingual"),
        )
    )


def model_identity(path):
    path = Path(path)
    manifest = path / "safeguard_model.json"
    if not manifest.is_file():
        raise EmbeddingUnavailable(
            "Modelo de embeddings local ausente o sin manifiesto. BM25 sigue disponible."
        )
    data = json.loads(manifest.read_text(encoding="utf8"))
    if not data.get("revision") or not data.get("files"):
        raise EmbeddingUnavailable("Manifiesto de embeddings incompleto.")
    return data


class LocalEmbeddings:
    def __init__(self, path):
        path = Path(path)
        self.identity = model_identity(path)
        for name, expected in self.identity["files"].items():
            file = (path / name).resolve()
            if not file.is_relative_to(path.resolve()) or not file.is_file():
                raise EmbeddingUnavailable("Artefacto de embeddings incompleto.")
            with file.open("rb") as stream:
                import hashlib

                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != expected:
                raise EmbeddingUnavailable("Hash del modelo de embeddings no coincide.")
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        from sentence_transformers import SentenceTransformer
        import torch

        torch.set_num_threads(min(4, os.cpu_count() or 1))
        self.model = SentenceTransformer(
            str(path), device="cpu", local_files_only=True, trust_remote_code=False
        )
        self.lock = RLock()
        self.signature = sha256(
            json.dumps(self.identity, sort_keys=True).encode()
        ).hexdigest()

    def encode(self, texts):
        # Pool token-bounded windows, so long legal paragraphs are not silently truncated.
        import numpy as np

        windows, owners = [], []
        with self.lock:
            tokenizer = self.model.tokenizer
            size = self.model.max_seq_length - tokenizer.num_special_tokens_to_add(
                False
            )
            for owner, text in enumerate(texts):
                ids = tokenizer.encode(
                    text, add_special_tokens=False, truncation=False, verbose=False
                )
                for start in range(0, max(1, len(ids)), size):
                    windows.append(
                        tokenizer.decode(
                            ids[start : start + size], skip_special_tokens=True
                        )
                    )
                    owners.append(owner)
            vectors = self.model.encode(
                windows,
                batch_size=16,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            pooled = np.zeros((len(texts), vectors.shape[1]), dtype=np.float32)
            for owner, vector in zip(owners, vectors):
                pooled[owner] += vector
            norms = np.linalg.norm(pooled, axis=1, keepdims=True)
            return (pooled / np.maximum(norms, 1e-12)).tolist()
