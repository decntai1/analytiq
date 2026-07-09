"""
SQLAlchemy connector — one class, ~30 database backends.

Covers what SMBs and mid-market actually run:
  Postgres, MySQL/MariaDB, SQL Server, SQLite, Oracle,
  and cloud warehouses via dialects (Snowflake, BigQuery, Redshift, Databricks).

You point it at a SQLAlchemy URL; the dialect handles the rest. Per-table schema
is emitted in the shape schema-RAG wants (name, columns, types, a sample row).
"""
from __future__ import annotations

import re

from sqlalchemy import create_engine, inspect, text

from config import settings
from connectors.base import QueryResult, StructuredConnector

_WRITE = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|replace|grant|revoke|"
    r"attach|pragma|vacuum|merge|call|exec|execute|into|copy)\b",
    re.IGNORECASE,
)


class SQLConnector(StructuredConnector):
    def __init__(self, db_url: str | None = None) -> None:
        self.engine = create_engine(db_url or settings.db_url)

    def schema_by_table(self) -> dict[str, str]:
        insp = inspect(self.engine)
        out: dict[str, str] = {}
        for table in insp.get_table_names():
            cols = insp.get_columns(table)
            col_desc = ", ".join(f"{c['name']} {c['type']}" for c in cols)
            desc = f"TABLE {table} ({col_desc})"
            try:
                with self.engine.connect() as conn:
                    row = conn.execute(text(f"SELECT * FROM {table} LIMIT 1")).fetchone()
                if row is not None:
                    desc += f"  sample: {dict(row._mapping)}"
            except Exception:
                pass
            out[table] = desc
        return out

    def _guard(self, query: str) -> None:
        q = query.strip().rstrip(";")
        if ";" in q:
            raise ValueError("Only a single statement is allowed.")
        first = q.split(None, 1)[0].lower() if q else ""
        if first not in ("select", "with"):
            raise ValueError("Only SELECT / WITH queries are permitted.")
        if _WRITE.search(q):
            raise ValueError("Query contains a forbidden write/DDL keyword.")

    def run_query(self, query: str) -> QueryResult:
        self._guard(query)
        limit = settings.sql_row_limit
        with self.engine.connect() as conn:
            res = conn.execute(text(query))
            cols = list(res.keys())
            rows = [dict(r._mapping) for r in res.fetchmany(limit + 1)]
        return QueryResult(columns=cols, rows=rows[:limit], truncated=len(rows) > limit)
