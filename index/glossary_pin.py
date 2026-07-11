r"""
Deterministic glossary → table pinning (retrieval scaffold).

The embedder has a recall ceiling: a confusable trap can outrank the table a
question actually needs (q5 "gross margin" loses `sales` to `revenue_targets`/
`sales_forecast`). Frozen labels shift ranking but couldn't break it. This is the
deterministic answer: if a question names a glossary metric, the tables in that
metric's FORMULA are the source-of-truth tables for it — pin them into the schema
context regardless of what the embedder ranked.

§4.2-safe / thesis-clean:
  - The source of truth is `glossary.json`, offline-authored, blind to the gold set.
  - The pin is a PURE function of (question, glossary) — it never sees the LLM, so
    retrieval stays model-independent (the crux the thesis rests on).
  - Retrieval-only: it changes WHICH table schemas enter the context, never what the
    model is told about them.

Determinism boundary (documented on purpose, so it can't be called fuzzy):
  1. table extraction — every `identifier.column` in a formula contributes `identifier`
     as a table (regex `\b([A-Za-z_]\w+)\.\w+`), order-preserving, de-duplicated.
  2. metric match — a metric matches a question iff its key, normalized (`_`→space),
     occurs as a case-insensitive substring of the question. Nothing else: no stemming,
     no embeddings, no synonyms. (A synonym map could be added as an explicit, frozen
     dict later; kept out here so the boundary stays a single, checkable rule.)
"""
from __future__ import annotations

import json
import os
import re

_TABLE_REF = re.compile(r"\b([A-Za-z_]\w+)\.\w+")


def load_glossary(path: str) -> dict[str, str]:
    """{metric: formula}. Missing/malformed file -> {} (pinning becomes a no-op)."""
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            g = json.load(f)
        return g if isinstance(g, dict) else {}
    except Exception:
        return {}


def tables_in_formula(formula: str) -> list[str]:
    """Distinct table identifiers referenced as `table.column`, in first-seen order."""
    out: list[str] = []
    for t in _TABLE_REF.findall(formula or ""):
        if t not in out:
            out.append(t)
    return out


def _norm_key(key: str) -> str:
    return key.replace("_", " ").lower()


def matched_metrics(question: str, glossary: dict[str, str]) -> list[str]:
    """Metric keys whose normalized form is a case-insensitive substring of the question."""
    q = (question or "").lower()
    return [k for k in glossary if _norm_key(k) in q]


def pinned_tables(question: str, glossary: dict[str, str]) -> list[str]:
    """Union (first-seen order) of the formula tables of every matched metric."""
    out: list[str] = []
    for k in matched_metrics(question, glossary):
        for t in tables_in_formula(glossary[k]):
            if t not in out:
                out.append(t)
    return out


def pinned_tables_from_path(question: str, glossary_path: str) -> list[str]:
    return pinned_tables(question, load_glossary(glossary_path))
