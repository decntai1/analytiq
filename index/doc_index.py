"""
Document-RAG — the unstructured arm.

Ingests text from a documents directory (.txt, .md, .pdf), chunks it, embeds it,
and retrieves the most relevant chunks for a question — returned WITH source
filenames so answers can be cited. Same VectorStore + Embedder as schema-RAG, just
pointed at a different corpus: that shared machinery is why "structured AND
unstructured" is one architecture, not two.
"""
from __future__ import annotations

import os

from core.embeddings import Embedder
from index.vectorstore import VectorStore


def _read_file(path: str) -> str:
    if path.lower().endswith(".pdf"):
        try:
            from pypdf import PdfReader
            return "\n".join((pg.extract_text() or "") for pg in PdfReader(path).pages)
        except Exception:
            return ""
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""


def _chunk(text: str, size: int = 1000, overlap: int = 150) -> list[str]:
    words, chunks, i = text.split(), [], 0
    while i < len(words):
        chunks.append(" ".join(words[i:i + size]))
        i += size - overlap
    return [c for c in chunks if c.strip()]


class DocIndex:
    def __init__(self, embedder: Embedder) -> None:
        self.store = VectorStore(embedder=embedder)
        self.count = 0

    def ingest_dir(self, docs_dir: str) -> int:
        if not os.path.isdir(docs_dir):
            return 0
        ids, texts, metas = [], [], []
        for root, _, files in os.walk(docs_dir):
            for fn in files:
                if not fn.lower().endswith((".txt", ".md", ".pdf")):
                    continue
                path = os.path.join(root, fn)
                for j, chunk in enumerate(_chunk(_read_file(path))):
                    ids.append(f"{fn}::{j}")
                    texts.append(chunk)
                    metas.append({"source": fn, "chunk": j, "text": chunk})
        if ids:
            self.store.add(ids, texts, metas)
        self.count = len(ids)
        return self.count

    def retrieve(self, question: str, top_k: int) -> list[dict]:
        return [
            {"source": h.metadata["source"], "text": h.metadata["text"], "score": round(s, 3)}
            for h, s in self.store.search(question, top_k=top_k)
        ]
