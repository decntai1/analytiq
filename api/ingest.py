"""
Upload ingestion — routes an uploaded file to the right arm and re-indexes so it's
immediately askable.

  .csv / .parquet / .xlsx  -> DuckDB connector (becomes a queryable table)
  .pdf / .txt / .md        -> document-RAG corpus

Kept separate from app.py so the wiring is testable and the routing rule is explicit.
"""
from __future__ import annotations

import os
import re


STRUCTURED_EXT = (".csv", ".parquet", ".xlsx", ".xls")
DOC_EXT = (".pdf", ".txt", ".md")


def classify(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext in STRUCTURED_EXT:
        return "structured"
    if ext in DOC_EXT:
        return "document"
    return "unknown"


def safe_name(filename: str) -> str:
    base = os.path.basename(filename)
    return re.sub(r"[^A-Za-z0-9._-]", "_", base)
