"""
Connector abstraction — the pluggable data-source seam.

The orchestrator talks only to this interface, so supporting a new source = one
new subclass. Two kinds:
  - StructuredConnector: schema + read-only query (SQL databases, DuckDB/files)
  - the unstructured side is handled by index/doc_index.py (documents)

Security: the read-only guard is defence-in-depth. The PRIMARY control in
production must be a read-only DB role/credential per tenant.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[dict] = field(default_factory=list)
    truncated: bool = False


class StructuredConnector(abc.ABC):
    @abc.abstractmethod
    def schema_by_table(self) -> dict[str, str]:
        """{table_name: 'TABLE t (col type, ...) sample: {...}'} for schema-RAG."""

    @abc.abstractmethod
    def run_query(self, query: str) -> QueryResult:
        """Execute a read-only query. Must reject anything that mutates state."""
