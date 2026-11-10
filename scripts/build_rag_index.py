"""Explicit, offline index build. Never run on Streamlit reruns."""

from pathlib import Path
import argparse
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from safeguard.rag.indexing import build_index, rag_path

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path, default=rag_path(root) / "manifests/documents.json"
    )
    parser.add_argument("--vectors", action="store_true")
    args = parser.parse_args()
    started = time.perf_counter()
    result = build_index(
        args.manifest, root, rag_path(root), root, with_vectors=args.vectors
    )
    print(
        f"Documentos: {len(result['documents'])}; fragmentos: {len(result['chunks'])}; segundos: {time.perf_counter() - started:.3f}"
    )
    print(
        "ChromaDB:",
        result["vector"]["collection"] if result["vector"] else "no preparado",
    )
    for doc in result["documents"]:
        print(doc["document_id"], doc["ingestion_status"], doc.get("error", ""))
