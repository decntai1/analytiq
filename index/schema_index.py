"""
Schema-RAG — the mechanism that lets NL->SQL scale to 100+ tables.

The LLM never sees all tables. We embed a one-line description per table once,
then at query time retrieve only the top-K tables relevant to the question and
feed *those* schemas into the prompt. This is the thesis's core scaling claim:
retrieval, not a bigger context window, is what makes large schemas tractable.
"""
from __future__ import annotations

from core.embeddings import Embedder
from index.vectorstore import VectorStore


class SchemaIndex:
    def __init__(self, embedder: Embedder) -> None:
        self.store = VectorStore(embedder=embedder)
        self._built = False

    def build(self, schema_by_table: dict[str, str]) -> None:
        """schema_by_table: {table_name: 'TABLE t (col type, ...) sample: {...}'}."""
        ids, texts, metas = [], [], []
        for table, desc in schema_by_table.items():
            ids.append(table)
            # embed table name + columns so semantic match works on either
            texts.append(f"{table}: {desc}")
            metas.append({"table": table, "schema": desc})
        if ids:
            self.store.add(ids, texts, metas)
        self._built = True

    def relevant_tables(self, question: str, top_k: int) -> str:
        """Return the concatenated schemas of the top-K tables for this question."""
        if not self._built:
            raise RuntimeError("SchemaIndex.build() not called.")
        hits = self.store.search(question, top_k=top_k)
        return "\n".join(h.metadata["schema"] for h, _ in hits)
