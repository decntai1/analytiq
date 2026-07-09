"""
Vector store — minimal numpy cosine index.

At the scale this product targets (≤ a few hundred tables, modest doc corpus) a
numpy cosine search is exact, zero-ops, and fully self-hostable — no extra service
to run on-prem. For large corpora, swap this class for a Chroma/FAISS-backed one
behind the same add()/search() interface; nothing else changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.embeddings import Embedder


@dataclass
class Item:
    id: str
    text: str
    metadata: dict
    vector: list[float]


@dataclass
class VectorStore:
    embedder: Embedder
    items: list[Item] = field(default_factory=list)

    def add(self, ids: list[str], texts: list[str], metadatas: list[dict]) -> None:
        vectors = self.embedder.embed(texts)
        for i, t, m, v in zip(ids, texts, metadatas, vectors):
            self.items.append(Item(id=i, text=t, metadata=m, vector=v))

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5 or 1.0
        nb = sum(y * y for y in b) ** 0.5 or 1.0
        return dot / (na * nb)

    def search(self, query: str, top_k: int) -> list[tuple[Item, float]]:
        if not self.items:
            return []
        qv = self.embedder.embed([query])[0]
        scored = [(it, self._cosine(qv, it.vector)) for it in self.items]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]
