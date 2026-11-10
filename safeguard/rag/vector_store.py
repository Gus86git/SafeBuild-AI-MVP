"""Explicit embeddings in persistent Chroma; immutable corpus/model generations."""

import os


class VectorUnavailable(RuntimeError):
    pass


class VectorStore:
    def __init__(self, directory, collection_name, embedding_signature, create=False):
        os.environ["ANONYMIZED_TELEMETRY"] = "False"
        try:
            import chromadb
            from chromadb.config import Settings

            self.client = chromadb.PersistentClient(
                path=str(directory), settings=Settings(anonymized_telemetry=False)
            )
            if create:
                self.collection = self.client.get_or_create_collection(
                    name=collection_name,
                    embedding_function=None,
                    metadata={"embedding_signature": embedding_signature},
                    configuration={"hnsw": {"space": "cosine"}},
                )
            else:
                self.collection = self.client.get_collection(
                    name=collection_name, embedding_function=None
                )
            if (
                self.collection.metadata.get("embedding_signature")
                != embedding_signature
            ):
                raise VectorUnavailable(
                    "Modelo incompatible con el índice; reconstruya explícitamente."
                )
        except Exception as exc:
            if hasattr(self, "client"):
                self.client.close()
            raise VectorUnavailable(
                f"ChromaDB no disponible ({type(exc).__name__}). BM25 sigue disponible."
            ) from exc

    def close(self):
        self.client.close()

    def upsert(self, chunks, embeddings):
        if len(chunks) != len(embeddings):
            raise ValueError("Cantidad de vectores incompatible.")
        self.collection.upsert(
            ids=[c["chunk_id"] for c in chunks],
            embeddings=embeddings,
            documents=[c["text"] for c in chunks],
            metadatas=[
                {
                    "document_id": c["document_id"],
                    "source_type": c["source_type"],
                    "is_synthetic": c["is_synthetic"],
                    "locator": c["locator"],
                    "page_number": c.get("page_number") or 0,
                    "title": c["title"],
                    "source_url": c.get("source_url") or "",
                    "document_version": c.get("document_version") or "",
                    "document_sha256": c["document_sha256"],
                }
                for c in chunks
            ],
        )

    def search(
        self, vector, chunks_by_id, top_k=5, source_types=None, max_distance=0.55
    ):
        if source_types == [] or not self.collection.count():
            return []
        where = {"source_type": {"$in": list(source_types)}} if source_types else None
        result = self.collection.query(
            query_embeddings=[vector],
            n_results=min(top_k, self.collection.count()),
            where=where,
            include=["distances"],
        )
        return [
            {
                "chunk": chunks_by_id[ident],
                "score": float(distance),
                "method": "ChromaDB (distancia coseno)",
            }
            for ident, distance in zip(result["ids"][0], result["distances"][0])
            if ident in chunks_by_id and distance <= max_distance
        ]
