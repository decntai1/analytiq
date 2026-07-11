"""
Schema labels — a frozen, offline-authored enrichment of the text schema-RAG embeds.

The retrieval ceiling (potion-base-8M) sits at ~0.70 on the confusable traps:
`sales` loses to `revenue_targets`/`manufacturing`, `produced_items` to
`manufacturing`, because a bare `TABLE t (col type, ...)` string embeds close to
its lexical neighbours. A one-time labelling pass adds, per table, its analytical
PURPOSE, GRAIN, what it is NOT (vs its confusable siblings), and key columns.
Embedding THAT pushes the right table up and the trap down.

Design guarantees (Guardrail §4.2):
  - Labels are FROZEN: written once offline (eval/label.py), never generated per
    query. The labeller model is recorded in the file's `_meta`.
  - Enrichment is ADDITIVE and RETRIEVAL-ONLY: it changes only the string the
    vector store embeds, NOT `metadata["schema"]` (what the LLM sees in the
    prompt stays the factual connector description — no label prose reaches
    SQL generation).
  - Absent / empty / malformed file => behaviour is BYTE-IDENTICAL to today.
    SchemaIndex.build() only calls in here when config.settings.schema_labels_path
    is set AND load_labels() returns a non-empty mapping.
"""
from __future__ import annotations

import json


def load_labels(path: str) -> dict | None:
    """Load a labels.json. Returns {table: {summary, grain, distinct_from, key_columns}}
    or None on any problem (missing file, bad JSON, wrong shape) — the caller treats
    None as "labels off", so a broken file degrades to today's behaviour, never a crash."""
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    tables = data.get("tables") if isinstance(data, dict) else None
    if not isinstance(tables, dict) or not tables:
        return None
    # keep only well-formed per-table entries; ignore junk without failing the whole file
    clean = {t: v for t, v in tables.items() if isinstance(v, dict)}
    return clean or None


def _enrich(table: str, base: str, label: dict) -> str:
    """Append the label's semantic cues to the embedded string. Only non-empty fields
    are added so a partial label still helps. Order puts PURPOSE and the DISTINCT-FROM
    clause first — those carry the most retrieval signal against confusable traps."""
    parts: list[str] = []
    summary = str(label.get("summary") or "").strip()
    grain = str(label.get("grain") or "").strip()
    distinct = str(label.get("distinct_from") or "").strip()
    keys = label.get("key_columns") or []
    if summary:
        parts.append(summary)
    if grain:
        parts.append(f"Grain: {grain}")
    if distinct:
        parts.append(f"Not to be confused with: {distinct}")
    if isinstance(keys, list) and keys:
        parts.append("Key columns: " + ", ".join(str(k) for k in keys))
    if not parts:
        return base
    return base + " || " + " ".join(parts)


def labelled_schema_texts(schema_by_table: dict[str, str], labels: dict) -> dict[str, str]:
    """Map {table: embedded_text}. Tables with a label are enriched; tables without one
    fall back to the exact base string `f"{table}: {desc}"` SchemaIndex uses today."""
    out: dict[str, str] = {}
    for table, desc in schema_by_table.items():
        base = f"{table}: {desc}"
        label = labels.get(table)
        out[table] = _enrich(table, base, label) if isinstance(label, dict) else base
    return out
