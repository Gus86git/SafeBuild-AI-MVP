"""Document-level retrieval metrics on explicit, reviewable relevance labels."""

from statistics import mean


def document_metrics(results, expected):
    retrieved = [r["chunk"]["document_id"] for r in results]
    expected = set(expected)
    if not expected:
        return {
            "hit_at_1": None,
            "recall_at_3": None,
            "mrr": None,
            "abstained": not retrieved,
        }
    return {
        "hit_at_1": float(bool(retrieved) and retrieved[0] in expected),
        "recall_at_3": len(set(retrieved[:3]) & expected) / len(expected),
        "mrr": next((1 / n for n, d in enumerate(retrieved, 1) if d in expected), 0.0),
        "abstained": not retrieved,
    }


def evaluate(retriever, cases):
    runs = []
    for method in ("BM25", "Semántica con ChromaDB", "Híbrida"):
        for case in cases:
            response = retriever.search(
                case["question"], method, 5, case.get("source_types")
            )
            metrics = document_metrics(response["results"], case["expected_documents"])
            runs.append(
                {
                    **case,
                    "method": method,
                    "effective_method": response["method"],
                    "warning": response["warning"],
                    "latency_seconds": response["latency_seconds"],
                    **metrics,
                    "retrieved": [
                        {
                            "document_id": r["chunk"]["document_id"],
                            "chunk_id": r["chunk"]["chunk_id"],
                            "locator": r["chunk"]["locator"],
                            "score": r["score"],
                            "document_label_relevant": r["chunk"]["document_id"]
                            in case["expected_documents"],
                            "passage_relevance": "pending_human_review",
                        }
                        for r in response["results"]
                    ],
                }
            )
    summaries = {}
    for method in ("BM25", "Semántica con ChromaDB", "Híbrida"):
        rows = [r for r in runs if r["method"] == method]
        valid = [r for r in rows if r["expected_documents"] and not r["warning"]]
        absent = [r for r in rows if not r["expected_documents"] and not r["warning"]]
        summaries[method] = {
            m: mean(r[m] for r in valid) if valid else None
            for m in ("hit_at_1", "recall_at_3", "mrr")
        }
        summaries[method].update(
            evaluated_answerable=len(valid),
            errors=sum(bool(r["warning"]) for r in rows),
            no_answer_cases=len(absent),
            correct_abstentions=sum(r["abstained"] for r in absent),
            mean_latency_seconds=mean(r["latency_seconds"] for r in rows),
        )
    return {
        "scope": "provisional document-level labels; no independent legal or passage validation",
        "summary": summaries,
        "runs": runs,
    }
