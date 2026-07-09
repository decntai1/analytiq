"""
DuckDB connector — the "their data is in files" case.

Many SMBs don't have a clean warehouse; they have CSVs, Excel exports, Parquet,
maybe a Postgres too. DuckDB queries all of these with one SQL surface, zero-ops,
embedded in the app. Point it at a folder; each file becomes a queryable view.

This pairs with SQLConnector to cover ~90% of SMB data realities with two adapters:
  SQLConnector  -> live databases
  DuckDBConnector -> files / spreadsheets / mixed sources
"""
from __future__ import annotations

import glob
import os
import re

from connectors.base import QueryResult, StructuredConnector
from config import settings

_WRITE = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|replace|attach|copy|"
    r"export|install|load|pragma|call)\b",
    re.IGNORECASE,
)


class DuckDBConnector(StructuredConnector):
    def __init__(self, data_dir: str | None = None) -> None:
        import duckdb
        self.con = duckdb.connect(database=":memory:")
        self.data_dir = data_dir or os.getenv("DUCKDB_DIR", "./data")
        self._views: list[str] = []
        self._register_files()

    def _register_files(self) -> None:
        patterns = {"*.csv": "read_csv_auto", "*.parquet": "read_parquet"}
        for pat, reader in patterns.items():
            for path in glob.glob(os.path.join(self.data_dir, "**", pat), recursive=True):
                view = re.sub(r"\W+", "_", os.path.splitext(os.path.basename(path))[0]).lower()
                try:
                    self.con.execute(f"CREATE VIEW {view} AS SELECT * FROM {reader}('{path}')")
                    self._views.append(view)
                except Exception:
                    pass

    def schema_by_table(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for view in self._views:
            try:
                cols = self.con.execute(f"DESCRIBE {view}").fetchall()
                col_desc = ", ".join(f"{c[0]} {c[1]}" for c in cols)
                out[view] = f"TABLE {view} ({col_desc})"
            except Exception:
                pass
        return out

    def _guard(self, query: str) -> None:
        q = query.strip().rstrip(";")
        if ";" in q:
            raise ValueError("Only a single statement is allowed.")
        if (q.split(None, 1)[0].lower() if q else "") not in ("select", "with"):
            raise ValueError("Only SELECT / WITH queries are permitted.")
        if _WRITE.search(q):
            raise ValueError("Query contains a forbidden keyword.")

    def run_query(self, query: str) -> QueryResult:
        self._guard(query)
        limit = settings.sql_row_limit
        cur = self.con.execute(query)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchmany(limit + 1)]
        return QueryResult(columns=cols, rows=rows[:limit], truncated=len(rows) > limit)


    _RESERVED = {"group", "order", "select", "from", "where", "table", "join", "union",
                 "case", "end", "on", "in", "and", "or", "not", "to", "by", "limit",
                 "offset", "desc", "asc", "values", "rank", "user", "default", "index",
                 "using", "between", "distinct", "all"}

    def _clean_ident(self, s: str) -> str:
        import re as _re
        v = _re.sub(r"\W+", "_", str(s)).strip("_").lower() or "sheet"
        if v in self._RESERVED:
            v += "_"          # 'group' -> 'group_': unquoted model SQL must not explode
        # digit-leading view names silently fail in SQL — prefix them
        return ("t_" + v) if v[0].isdigit() else v

    def _ingest_xlsx(self, path: str) -> list[dict]:
        """Ingest every DATA-BEARING sheet of a workbook as its own view.

        Heuristics (deterministic, no model involved):
          - header row = earliest of the densest rows in the first 10 content rows
            (real headers are dense; title/logo rows above them are sparse)
          - decorative sheets die at the quality gate: after cleaning we require
            >=3 data rows and >=2 columns that are >=40% filled
        Returns [{'view','sheet','rows','cols'}...] and stores it on self.last_ingest.
        """
        import os
        import pandas as pd
        base = self._clean_ident(os.path.splitext(os.path.basename(path))[0])
        raw = pd.read_excel(path, sheet_name=None, header=None, dtype=object)
        report: list[dict] = []
        for sheet, df in raw.items():
            df = df.dropna(how="all").dropna(axis=1, how="all")
            if df.shape[0] < 4 or df.shape[1] < 2:
                continue
            nn = df.head(10).notna().sum(axis=1)
            hdr_pos = next(i for i, v in enumerate(nn.values) if v >= nn.values.max() - 1)
            header = df.iloc[hdr_pos].tolist()
            body = df.iloc[hdr_pos + 1:].copy()
            cols, seen = [], {}
            for j, v in enumerate(header):
                raw_c = "" if v is None else str(v).strip()
                c = self._clean_ident(raw_c)[:60] if raw_c and raw_c.lower() != "nan" else f"col_{j+1}"
                seen[c] = seen.get(c, 0) + 1
                cols.append(c if seen[c] == 1 else f"{c}_{seen[c]}")
            body.columns = cols
            body = body.dropna(how="all")
            keep = [c for c in body.columns if body[c].notna().mean() >= 0.4]
            if len(keep) < 2 or body.shape[0] < 3:
                continue
            body = body[keep].copy()
            # types: numeric where possible; remaining mixed/object columns -> text
            for c in body.columns:
                try:
                    body[c] = pd.to_numeric(body[c])
                except (ValueError, TypeError):
                    body[c] = body[c].map(lambda x: None if pd.isna(x) else str(x))
            view = base if len(raw) == 1 else f"{base}_{self._clean_ident(sheet)}"
            self.con.register(f"_tmp_{view}", body)
            self.con.execute(f'CREATE OR REPLACE VIEW "{view}" AS SELECT * FROM "_tmp_{view}"')
            if view not in self._views:
                self._views.append(view)
            report.append({"view": view, "sheet": sheet,
                           "rows": int(body.shape[0]), "cols": int(len(keep))})
        self.last_ingest = report
        return report

    def register_file(self, path: str) -> str | None:
        """Register a single uploaded data file as a queryable view. Returns view name."""
        import os, re as _re
        ext = os.path.splitext(path)[1].lower()
        reader = {".csv": "read_csv_auto", ".parquet": "read_parquet"}.get(ext)
        if ext in (".xlsx", ".xls"):
            # Real-world workbooks are PRESENTATION documents (title pages, bracket
            # art, per-topic sheets) — not tidy single tables. Ingest every
            # data-bearing sheet, detect its header row, and drop decorative sheets.
            try:
                tables = self._ingest_xlsx(path)
            except Exception:
                return None
            if not tables:
                return None
            # primary view (backward-compatible return) = the largest table;
            # the full per-sheet report is on self.last_ingest for the API layer.
            return max(tables, key=lambda t: t["rows"])["view"]
        if not reader:
            return None
        view = _re.sub(r"\W+", "_", os.path.splitext(os.path.basename(path))[0]).lower()
        try:
            self.con.execute(f"CREATE OR REPLACE VIEW {view} AS SELECT * FROM {reader}('{path}')")
            if view not in self._views:
                self._views.append(view)
            return view
        except Exception:
            return None
