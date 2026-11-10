"""Lexical retrieval with accent normalization; scores are not probabilities."""

import re
import unicodedata
from collections import Counter
from math import log1p, ceil

STOP = set(
    "a al ante bajo con contra de del desde durante el ella en entre es esta este la las lo los o para por que qué se sin sobre su sus un una unos unas y como cómo cual cuál cuales cuáles hay tiene tienen debe deben ser son si dónde donde según".split()
)


def tokens(text):
    text = "".join(
        c
        for c in unicodedata.normalize("NFD", text.lower())
        if unicodedata.category(c) != "Mn"
    )
    return [t for t in re.findall(r"[a-z0-9]+", text) if t not in STOP]


class BM25Retriever:
    def __init__(self, chunks):
        from rank_bm25 import BM25Okapi

        self.chunks = chunks
        self.terms = [tokens(c["title"] + " " + c["text"]) for c in chunks]
        self.index = (
            BM25Okapi(self.terms, k1=1.5, b=0.75, epsilon=0.25) if chunks else None
        )
        if self.index:
            # Positive Robertson IDF avoids zero/negative scores on small corpora.
            frequency = Counter(t for terms in self.terms for t in set(terms))
            self.index.idf = {
                t: log1p((len(chunks) - count + 0.5) / (count + 0.5))
                for t, count in frequency.items()
            }

    def search(self, question, top_k=5, source_types=None):
        query = tokens(question)
        if not self.index or not query:
            return []
        scores = self.index.get_scores(query)
        query_terms = set(query)
        minimum = 1 if len(query_terms) < 3 else max(2, ceil(len(query_terms) * 0.35))
        ranked = sorted(
            range(len(scores)), key=lambda i: (-scores[i], self.chunks[i]["chunk_id"])
        )
        return [
            {"chunk": self.chunks[i], "score": float(scores[i]), "method": "BM25"}
            for i in ranked
            if scores[i] > 0
            and len(query_terms.intersection(self.terms[i])) >= minimum
            and (source_types is None or self.chunks[i]["source_type"] in source_types)
        ][:top_k]
