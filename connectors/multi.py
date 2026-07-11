"""
MultiConnector — presents several structured connectors as one.

Lets the app expose a live database AND uploaded files (DuckDB) through a single
schema + query surface, so the LLM sees one unified set of tables. Table names are
assumed unique across sources; on a clash the first source wins.
"""
from __future__ import annotations

from connectors.base import QueryResult, StructuredConnector


class MultiConnector(StructuredConnector):
    def __init__(self, sources: list[StructuredConnector]) -> None:
        self.sources = sources

    def schema_by_table(self) -> dict[str, str]:
        merged: dict[str, str] = {}
        self._owner: dict[str, StructuredConnector] = {}
        for src in self.sources:
            for table, desc in src.schema_by_table().items():
                if table not in merged:
                    merged[table] = desc
                    self._owner[table] = src
        return merged

    def run_query(self, query: str) -> QueryResult:
        # Route by which source owns a table named in the query; default to first.
        if not hasattr(self, "_owner"):
            self.schema_by_table()
        lowered = query.lower()
        for table, src in self._owner.items():
            if table.lower() in lowered:
                return src.run_query(query)
        return self.sources[0].run_query(query)

    def close(self) -> None:
        """Best-effort close every source that supports it (file-backed DuckDB
        stores release their file lock; SQL connectors have nothing to close)."""
        for src in self.sources:
            closer = getattr(src, "close", None)
            if callable(closer):
                closer()
