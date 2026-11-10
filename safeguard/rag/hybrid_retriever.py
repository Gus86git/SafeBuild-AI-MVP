"""Ranking fusion and explicit degradation, independent of Streamlit."""

from time import perf_counter
import re
from .bm25_retriever import BM25Retriever
from .embeddings import LocalEmbeddings, model_path
from .vector_store import VectorStore, VectorUnavailable


def rrf(rankings, top_k=5, constant=60):
    scores, items = {}, {}
    for ranking in rankings:
        seen = set()
        for rank, item in enumerate(ranking, 1):
            ident = item["chunk"]["chunk_id"]
            if ident in seen:
                continue
            seen.add(ident)
            scores[ident] = scores.get(ident, 0.0) + 1 / (constant + rank)
            items[ident] = item["chunk"]
    return [
        {"chunk": items[i], "score": scores[i], "method": "Híbrida RRF"}
        for i in sorted(scores, key=lambda x: (-scores[x], x))[:top_k]
    ]


class Retriever:
    def __init__(self, snapshot, rag_root, project_root):
        self.snapshot, self.rag_root, self.project_root = (
            snapshot,
            rag_root,
            project_root,
        )
        self.bm25 = BM25Retriever(snapshot["chunks"])
        self.by_id = {c["chunk_id"]: c for c in snapshot["chunks"]}
        self.embeddings = self.store = None

    def release(self):
        if self.store is not None:
            self.store.close()
        self.embeddings = self.store = None

    def vector_search(self, question, top_k, source_types):
        descriptor = self.snapshot.get("vector")
        if not descriptor:
            raise VectorUnavailable(
                "Índice vectorial aún no preparado. BM25 sigue disponible."
            )
        if self.embeddings is None:
            self.embeddings = LocalEmbeddings(model_path(self.project_root))
        if self.embeddings.signature != descriptor["embedding_signature"]:
            raise VectorUnavailable("El modelo cambió: índice vectorial incompatible.")
        if self.store is None:
            self.store = VectorStore(
                self.rag_root / "indexes/chroma",
                descriptor["collection"],
                self.embeddings.signature,
            )
        if self.store.collection.count() != len(self.by_id):
            raise VectorUnavailable(
                "Índice vectorial incompleto; reconstrucción requerida."
            )
        return self.store.search(
            self.embeddings.encode([question])[0], self.by_id, top_k, source_types
        )

    def search(self, question, method="BM25", top_k=5, source_types=None):
        if method not in ("BM25", "Semántica con ChromaDB", "Híbrida"):
            raise ValueError("Método desconocido.")
        if not question.strip() or len(question) > 1000 or not 1 <= top_k <= 10:
            raise ValueError("Pregunta de 1–1000 caracteres y entre 1 y 10 resultados.")
        scope_note = None
        if re.search(r"\btechcorp\b", question, re.IGNORECASE):
            simulated = ["simulated_manual", "simulated_procedure"]
            source_types = (
                simulated
                if source_types is None
                else [s for s in source_types if s in simulated]
            )
            scope_note = "Consulta sobre TechCorp: limitada a documentos ficticios compatibles con el filtro seleccionado."
        start = perf_counter()
        effective, warning = method, None
        lexical = self.bm25.search(question, max(10, top_k), source_types)
        if method == "BM25":
            results = lexical[:top_k]
        else:
            try:
                semantic = self.vector_search(question, max(10, top_k), source_types)
                results = (
                    semantic[:top_k]
                    if method == "Semántica con ChromaDB"
                    else rrf([lexical, semantic], top_k)
                )
            except Exception as exc:
                warning = f"Motor vectorial no disponible ({type(exc).__name__}): {str(exc)[:180]}"
                if method == "Híbrida":
                    effective, results = "BM25 (degradación explícita)", lexical[:top_k]
                else:
                    results = []
        return {
            "results": results,
            "method": effective,
            "requested_method": method,
            "warning": warning,
            "scope_note": scope_note,
            "latency_seconds": perf_counter() - start,
            "evidence_status": "fragmentos candidatos; pertinencia pendiente de revisión"
            if results
            else "sin evidencia recuperada",
        }
