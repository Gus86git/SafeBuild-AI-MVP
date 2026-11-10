"""Explicit manifest-to-index preparation with atomic snapshot publication."""

from pathlib import Path
from hashlib import sha256
from datetime import datetime, timezone
import json
import os
import uuid
from .documents import extract, safe_path, SOURCE_TYPES, DocumentError
from .chunking import chunks_for, CONFIG


def rag_path(root):
    return Path(
        os.environ.get("SAFEGUARD_RAG_PATH", str(Path(root) / "data/rag"))
    ).resolve()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf8")
    temp.replace(path)


def build_index(
    manifest_path, source_root, rag_root, project_root, with_vectors=False, config=None
):
    config = config or CONFIG
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf8"))
    if not isinstance(manifest, list) or len(manifest) > 100:
        raise DocumentError(
            "El manifiesto debe contener hasta 100 documentos autorizados."
        )
    documents, chunks, hashes, ids = [], [], set(), set()
    for entry in manifest:
        doc = dict(entry)
        if not doc.get("approved") or doc.get("source_type") not in SOURCE_TYPES:
            raise DocumentError("Documento no aprobado o clasificación inválida.")
        if doc["document_id"] in ids:
            raise DocumentError("ID documental duplicado.")
        ids.add(doc["document_id"])
        if doc.get("is_synthetic") != doc["source_type"].startswith("simulated_"):
            raise DocumentError("Clasificación sintética contradictoria.")
        try:
            file = safe_path(source_root, doc["filename"])
            data = extract(file)
            if doc.get("sha256") and doc["sha256"] != data["sha256"]:
                raise DocumentError(
                    "Documento modificado: actualizar y aprobar el manifiesto antes de indexar."
                )
            doc.update(
                sha256=data["sha256"],
                page_count=data["page_count"],
                warnings=data["warnings"],
            )
            if data["sha256"] in hashes:
                doc["ingestion_status"] = "duplicate_excluded"
            else:
                hashes.add(data["sha256"])
                doc["ingestion_status"] = "indexed"
                chunks.extend(chunks_for(doc, data, config))
        except (DocumentError, OSError) as exc:
            doc.update(ingestion_status="error", error=str(exc))
        documents.append(doc)
    if len(chunks) > 10000:
        raise DocumentError("Corpus superior al límite de 10000 fragmentos.")
    fingerprint = sha256(
        json.dumps(
            {"documents": documents, "chunks": chunks, "chunking": config},
            ensure_ascii=False,
            sort_keys=True,
        ).encode()
    ).hexdigest()
    snapshot = {
        "schema_version": 1,
        "corpus_hash": fingerprint,
        "chunking": config,
        "documents": documents,
        "chunks": chunks,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "vector": None,
    }
    if with_vectors and chunks:
        from .embeddings import LocalEmbeddings, model_path
        from .vector_store import VectorStore

        embeddings = LocalEmbeddings(model_path(project_root))
        generation = sha256(
            (fingerprint + embeddings.signature + "mean-token-windows-v1").encode()
        ).hexdigest()[:32]
        collection = "safeguard_" + generation
        store = VectorStore(
            Path(rag_root) / "indexes/chroma",
            collection,
            embeddings.signature,
            create=True,
        )
        try:
            if store.collection.count() != len(chunks):
                for start in range(0, len(chunks), 48):
                    batch = chunks[start : start + 48]
                    store.upsert(batch, embeddings.encode([c["text"] for c in batch]))
                if store.collection.count() != len(chunks):
                    raise DocumentError(
                        "Índice incompleto; no se publica la nueva generación."
                    )
            snapshot["vector"] = {
                "collection": collection,
                "embedding_signature": embeddings.signature,
                "model": embeddings.identity,
                "pooling": "mean-token-windows-v1",
                "space": "cosine",
                "max_distance": 0.55,
                "count": store.collection.count(),
            }
        finally:
            store.close()
    # Preserve previous published corpus on rebuild; no collection is silently deleted.
    destination = Path(rag_root) / "indexes/corpus.json"
    if destination.exists():
        previous = json.loads(destination.read_text(encoding="utf8"))
        atomic_json(
            Path(rag_root) / "indexes/snapshots" / (previous["corpus_hash"] + ".json"),
            previous,
        )
    atomic_json(destination, snapshot)
    return snapshot


def load_snapshot(rag_root):
    path = Path(rag_root) / "indexes/corpus.json"
    if not path.is_file():
        raise DocumentError(
            "Base documental sin preparar. Ejecute scripts/build_rag_index.py con el manifiesto autorizado."
        )
    if path.stat().st_size > 40 * 1024 * 1024:
        raise DocumentError("Índice documental demasiado grande.")
    data = json.loads(path.read_text(encoding="utf8"))
    if data.get("schema_version") != 1:
        raise DocumentError("Versión de índice desconocida.")
    return data
