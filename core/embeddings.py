"""
Embedding abstraction — powers BOTH retrieval arms (schema-RAG and doc-RAG).

Modes:
  - "openai": hosted embeddings (cloud demo)
  - "local":  sentence-transformers, runs on the box (on-prem; nothing leaves)
  - "test":   deterministic hash embedding, zero deps / no network (CI + offline demo)
  - "auto":   openai if a key is present, else local if installed, else test (warns)

Same interface either way, so the index code never branches on deployment.
"""
from __future__ import annotations

import hashlib
import math
import os

from config import settings


class Embedder:
    dim: int
    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class OpenAIEmbedder(Embedder):
    def __init__(self) -> None:
        from openai import OpenAI
        self._client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
        self.model = settings.embedding_model_openai
        self.dim = 1536
    def embed(self, texts: list[str]) -> list[list[float]]:
        resp = self._client.embeddings.create(model=self.model, input=texts)
        return [d.embedding for d in resp.data]


class LocalEmbedder(Embedder):
    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(settings.embedding_model_local)
        self.dim = self._model.get_sentence_embedding_dimension()
    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, normalize_embeddings=True).tolist()


class TestEmbedder(Embedder):
    """Deterministic bag-of-hashed-tokens vector. Not semantic, but real vectors —
    enough to wire and test retrieval offline. Swap to local/openai for quality."""
    def __init__(self, dim: int = 256) -> None:
        self.dim = dim
    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            v = [0.0] * self.dim
            for tok in t.lower().split():
                h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
                v[h % self.dim] += 1.0
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / norm for x in v])
        return out


def get_embedder() -> Embedder:
    mode = settings.embedding_mode
    if mode == "openai":
        return OpenAIEmbedder()
    if mode == "local":
        return LocalEmbedder()
    if mode == "test":
        return TestEmbedder()
    # auto
    if os.getenv("OPENAI_API_KEY") and not settings.is_onprem:
        return OpenAIEmbedder()
    try:
        return LocalEmbedder()
    except Exception:
        import warnings
        warnings.warn("Falling back to TestEmbedder (no OpenAI key, sentence-transformers "
                      "not installed). Retrieval quality will be poor — install "
                      "sentence-transformers or set OPENAI_API_KEY for real use.")
        return TestEmbedder()
