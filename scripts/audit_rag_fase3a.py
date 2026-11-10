"""Freeze new passage labels before retrieval; no threshold tuning or remote generation."""

from pathlib import Path
import hashlib
import json
from statistics import mean
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from safeguard.rag.indexing import load_snapshot, rag_path
from safeguard.rag.hybrid_retriever import Retriever
from safeguard.rag.evaluation import document_metrics
from safeguard.rag.citations import citation


def main():
    output = ROOT / "output/audit-fase3a"
    output.mkdir(parents=True, exist_ok=True)
    if (output / "rag-results.json").exists():
        raise RuntimeError(
            "Preserve the first evaluation; choose a new directory for another experiment."
        )
    snapshot = load_snapshot(rag_path(ROOT))
    cases = json.loads(
        (ROOT / "tests/fixtures/rag_fase3a.json").read_text(encoding="utf8")
    )
    old = json.loads(
        (ROOT / "tests/fixtures/rag_evaluation.json").read_text(encoding="utf8")
    )
    assert not {c["question"] for c in old} & {c["question"] for c in cases}
    chunks = {c["chunk_id"]: c for c in snapshot["chunks"]}
    for c in cases:
        c["expected_chunks"] = []
        for prefix in c.pop("chunk_prefixes"):
            matches = [key for key in chunks if key.startswith(prefix)]
            assert len(matches) == 1
            c["expected_chunks"] += matches
        c["source_types"] = c.get(
            "source_types", ["simulated_manual", "simulated_procedure"]
        )
    frozen = json.dumps(
        {
            "corpus_hash": snapshot["corpus_hash"],
            "annotation": "Provisional same-team passage labels, frozen before ranking; independent human review pending",
            "cases": cases,
        },
        ensure_ascii=False,
        indent=2,
    )
    (output / "rag-labels-frozen.json").write_text(frozen, encoding="utf8")
    retriever = Retriever(snapshot, rag_path(ROOT), ROOT)
    runs = []
    for method in ["BM25", "Semántica con ChromaDB", "Híbrida"]:
        for case in cases:
            started = perf_counter()
            result = retriever.search(case["question"], method, 5, case["source_types"])
            retrieved = [r["chunk"] for r in result["results"]]
            relevant = set(case["expected_chunks"])
            hit_ids = [c["chunk_id"] for c in retrieved]
            passage_precision = (
                len(set(hit_ids[:3]) & relevant) / len(hit_ids[:3])
                if hit_ids[:3]
                else 0.0
            )
            runs.append(
                dict(
                    id=case["id"],
                    method=method,
                    effective=result["method"],
                    warning=result["warning"],
                    latency_seconds=perf_counter() - started,
                    **document_metrics(result["results"], case["expected_documents"]),
                    passage_hit_at_1=float(bool(hit_ids) and hit_ids[0] in relevant)
                    if relevant
                    else None,
                    passage_recall_at_3=len(set(hit_ids[:3]) & relevant) / len(relevant)
                    if relevant
                    else None,
                    passage_precision_at_3=passage_precision,
                    citation_metadata_valid=all(
                        c["chunk_id"] in chunks
                        and bool(c["locator"])
                        and bool(citation(c))
                        for c in retrieved
                    ),
                    retrieved=[
                        dict(
                            document_id=c["document_id"],
                            chunk_id=c["chunk_id"],
                            locator=c["locator"],
                            label_relevant=c["chunk_id"] in relevant,
                        )
                        for c in retrieved
                    ],
                )
            )
    retriever.release()
    summary = {}
    for method in ["BM25", "Semántica con ChromaDB", "Híbrida"]:
        rows = [r for r in runs if r["method"] == method]
        valid = [r for r in rows if r["hit_at_1"] is not None]
        negative = [r for r in rows if r["hit_at_1"] is None]
        summary[method] = {
            key: mean(r[key] for r in valid)
            for key in [
                "hit_at_1",
                "recall_at_3",
                "mrr",
                "passage_hit_at_1",
                "passage_recall_at_3",
                "passage_precision_at_3",
            ]
        }
        summary[method].update(
            answerable=len(valid),
            negative=len(negative),
            correct_abstentions=sum(r["abstained"] for r in negative),
            errors=sum(bool(r["warning"]) for r in rows),
            first_query_seconds=rows[0]["latency_seconds"],
            subsequent_mean_seconds=mean(r["latency_seconds"] for r in rows[1:]),
            citations_valid=all(r["citation_metadata_valid"] for r in rows),
        )
    result = {
        "label_sha256": hashlib.sha256(frozen.encode()).hexdigest(),
        "corpus_hash": snapshot["corpus_hash"],
        "summary": summary,
        "runs": runs,
        "limitations": [
            "New questions, same-team provisional labels; not independently annotated.",
            "No tuning after results. Passage scores use fixed labels, not legal validation.",
            "MRR truncation at five results; chunk-level ranks for document metrics.",
        ],
    }
    (output / "rag-results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
