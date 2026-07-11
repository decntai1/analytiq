"""
Schema-RAG — the mechanism that lets NL->SQL scale to 100+ tables.

The LLM never sees all tables. We embed a one-line description per table once,
then at query time retrieve only the top-K tables relevant to the question and
feed *those* schemas into the prompt. This is the thesis's core scaling claim:
retrieval, not a bigger context window, is what makes large schemas tractable.
"""
from __future__ import annotations

from core.embeddings import Embedder
from index.labels import load_labels, labelled_schema_texts
from index.vectorstore import VectorStore


class SchemaIndex:
    def __init__(self, embedder: Embedder) -> None:
        self.store = VectorStore(embedder=embedder)
        self._built = False

    def build(self, schema_by_table: dict[str, str]) -> None:
        """schema_by_table: {table_name: 'TABLE t (col type, ...) sample: {...}'}.

        If config.settings.schema_labels_path points at a valid labels.json, the
        EMBEDDED text per table is enriched with its analytical purpose / grain /
        what-it-is-NOT so retrieval discriminates confusable tables. This changes
        ONLY the embedded string, never metadata["schema"] (what the LLM prompt
        sees). Absent/empty/malformed labels => byte-identical to the plain build.
        """
        from config import settings
        text_map = None
        labels = load_labels(settings.schema_labels_path)
        if labels:
            text_map = labelled_schema_texts(schema_by_table, labels)
        ids, texts, metas = [], [], []
        for table, desc in schema_by_table.items():
            ids.append(table)
            # embed table name + columns so semantic match works on either;
            # enriched with frozen labels when configured (retrieval only)
            texts.append(text_map[table] if text_map else f"{table}: {desc}")
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
