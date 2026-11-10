"""Run actual local lexical/vector/hybrid retrieval with the published corpus."""

from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from safeguard.rag.indexing import rag_path, load_snapshot, atomic_json
from safeguard.rag.hybrid_retriever import Retriever
from safeguard.rag.evaluation import evaluate

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    base = rag_path(root)
    cases = json.loads(
        (root / "tests/fixtures/rag_evaluation.json").read_text(encoding="utf8")
    )
    snapshot = load_snapshot(base)
    retriever = Retriever(snapshot, base, root)
    result = evaluate(retriever, cases)
    result.update(
        corpus_hash=snapshot["corpus_hash"],
        chunk_count=len(snapshot["chunks"]),
        model=snapshot.get("vector", {}).get("model")
        if snapshot.get("vector")
        else None,
    )
    atomic_json(base / "evaluation/results.json", result)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
