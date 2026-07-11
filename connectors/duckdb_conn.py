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
import threading

from connectors.base import QueryResult, StructuredConnector
from config import settings

_WRITE = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|replace|attach|copy|"
    r"export|install|load|pragma|call)\b",
    re.IGNORECASE,
)


def analytics_db_path(data_dir: str, name: str) -> str:
    """Path of the persistent DuckDB file for a store rooted at data_dir.

    Placed in the PARENT of data_dir (the tenant root, for a tenant store) so the
    upload re-scan — which globs *.csv/*.parquet/*.xlsx INSIDE data_dir — never
    picks it up, and named per-store (analytics.duckdb / analytics_files.duckdb /
    analytics_uploads.duckdb) so a tenant with several stores never collides on a
    single file (DuckDB is single-writer per file)."""
    return os.path.join(os.path.dirname(os.path.realpath(data_dir)), name)


class DuckDBConnector(StructuredConnector):
    def __init__(self, data_dir: str | None = None, db_path: str | None = None) -> None:
        import duckdb
        # ONE re-entrant lock serializes every touch of self.con AND the shared
        # Python state (_views/_ts_hints/_source_of/last_ingest). A DuckDB
        # connection is not safe for concurrent use across threads, and same-tenant
        # requests share ONE cached connector (see core/tenant_runtime) running in
        # FastAPI's sync threadpool — so concurrent /ask, an upload racing a query,
        # and a dashboard refresh burst all land here at once. A per-connector lock
        # (vs per-query cursors) is the right fix at this load: it also covers the
        # Python-side mutations that a cursor would leave unguarded. RLock so a
        # locked public method can call another (register_file -> _load_csv, etc.).
        self._lock = threading.RLock()
        # db_path=None -> in-memory (tests, workbench throwaway, ingest suite). A real
        # path -> file-backed: DuckDB pages tables to disk instead of pinning every
        # uploaded table in RAM (RAM is the binding constraint on this box), and the
        # store survives a restart. Single-writer per file, so each store gets its OWN
        # file (see analytics_db_path); one process holds one handle to it.
        self._db_path = db_path or ":memory:"
        if self._db_path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(self._db_path)) or ".", exist_ok=True)
        self.con = duckdb.connect(database=self._db_path)
        self.data_dir = data_dir or os.getenv("DUCKDB_DIR", "./data")
        self._views: list[str] = []
        self._ts_hints: dict[str, dict] = {}   # view -> {col: strptime_format} (cached)
        self._source_of: dict[str, str] = {}   # view -> source file path (for delete + cleanup)
        self._register_files()

    def _register_files(self) -> None:
        """Startup re-scan: re-register every file on disk through the SAME robust
        path as upload (register_file) — encoding transcode for messy CSVs, xlsx
        multi-sheet, timestamp hints. In-memory DuckDB is wiped on restart, so this
        is what makes uploads survive a rebuild/reboot. NEVER use a parallel bare
        loader here — that's what silently dropped cp1252 CSVs and all xlsx before."""
        seen = set()
        for pat in ("*.csv", "*.parquet", "*.xlsx", "*.xls"):
            for path in sorted(glob.glob(os.path.join(self.data_dir, "**", pat), recursive=True)):
                if path in seen:
                    continue
                seen.add(path)
                try:
                    self.register_file(path)
                except Exception:
                    pass

    # Deterministic timestamp formats to recognize at the schema layer (no LLM,
    # no data mutation — just teach the model how to cast a text timestamp column).
    _TS_FORMATS = (
        "%a %b %d %H:%M:%S +0000 %Y",   # Twitter: "Thu Jun 07 01:13:25 +0000 2018"
        "%Y-%m-%dT%H:%M:%S",            # ISO with T
        "%Y-%m-%d %H:%M:%S",            # ISO with space
        "%Y-%m-%d",                     # plain date
        "%m/%d/%Y",                     # US date
        "%d/%m/%Y",                     # EU date
    )

    def _ts_hints_for(self, view: str) -> dict:
        """Detect timestamp-like VARCHAR columns by sampling values and trying known
        formats via try_strptime. Cached per view. Structural RECOGNITION only — the
        data is never modified; the hint just tells the model the right cast."""
        if view in self._ts_hints:
            return self._ts_hints[view]
        hints: dict[str, str] = {}
        try:
            cols = self.con.execute(f'DESCRIBE "{view}"').fetchall()
        except Exception:
            self._ts_hints[view] = hints
            return hints
        for c in cols:
            name, ctype = c[0], str(c[1]).upper()
            if "VARCHAR" not in ctype:
                continue
            for fmt in self._TS_FORMATS:
                try:
                    ok, tot = self.con.execute(
                        f"SELECT count(*) FILTER (WHERE try_strptime(v, '{fmt}') IS NOT NULL), "
                        f'count(*) FROM (SELECT "{name}" v FROM "{view}" '
                        f'WHERE "{name}" IS NOT NULL LIMIT 200)').fetchone()
                    if tot and ok >= tot * 0.9:     # >=90% of the sample parses -> this format
                        hints[name] = fmt
                        break
                except Exception:
                    continue
        self._ts_hints[view] = hints
        return hints

    def schema_by_table(self) -> dict[str, str]:
        out: dict[str, str] = {}
        with self._lock:
            for view in self._views:
                try:
                    cols = self.con.execute(f'DESCRIBE "{view}"').fetchall()
                    hints = self._ts_hints_for(view)
                    parts = []
                    for c in cols:
                        d = f"{c[0]} {c[1]}"
                        if c[0] in hints:
                            d += f" -- timestamp text; cast with strptime(\"{c[0]}\", '{hints[c[0]]}')"
                        parts.append(d)
                    out[view] = f"TABLE {view} ({', '.join(parts)})"
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

    def close(self) -> None:
        """Release the DuckDB connection (and its file lock, when file-backed) so a
        fresh connect to the same file can succeed within this process. Best-effort
        and idempotent — used by TenantRuntime.invalidate before a rebuild."""
        with self._lock:
            try:
                self.con.close()
            except Exception:
                pass

    def run_query(self, query: str) -> QueryResult:
        self._guard(query)
        limit = settings.sql_row_limit
        with self._lock:
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
            # Materialize as a TABLE (not a VIEW over the registered pandas frame):
            # a registered relation is process-ephemeral, so a persisted view over it
            # would dangle after a restart. A table lands in the file, pages to disk,
            # and survives. Drop the temp registration once copied.
            self.con.execute(f'CREATE OR REPLACE TABLE "{view}" AS SELECT * FROM "_tmp_{view}"')
            try:
                self.con.unregister(f"_tmp_{view}")
            except Exception:
                pass
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
        with self._lock:
            self._ts_hints = {}   # new data -> recompute timestamp hints lazily
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
                for t in tables:                   # remember which file each sheet-view came from
                    self._source_of[t["view"]] = path
                # primary view (backward-compatible return) = the largest table;
                # the full per-sheet report is on self.last_ingest for the API layer.
                return max(tables, key=lambda t: t["rows"])["view"]
            if not reader:
                return None
            view = _re.sub(r"\W+", "_", os.path.splitext(os.path.basename(path))[0]).lower()
            if ext == ".parquet":
                try:
                    self.con.execute(f'CREATE OR REPLACE VIEW "{view}" AS SELECT * FROM read_parquet(\'{path}\')')
                except Exception:
                    return None
                if view not in self._views:
                    self._views.append(view)
                self._source_of[view] = path
                self.last_ingest = [self._table_stat(view)]
                return view
            # CSV: strict UTF-8 fast path; fall back to encoding-normalized load for messy files
            rows, skipped = self._load_csv(view, path)
            if rows is None:
                return None
            if view not in self._views:
                self._views.append(view)
            self._source_of[view] = path
            stat = self._table_stat(view)
            stat["skipped"] = skipped
            self.last_ingest = [stat]
            return view

    def delete_view(self, name: str) -> bool:
        """Drop a table/view AND delete its source file from data_dir. A user can only
        name an existing view (looked up in _views) — the deleted file is the one WE
        recorded at ingest, realpath-confined to data_dir, so a crafted name can't
        escape the tenant's dir. For a multi-sheet workbook, deleting any of its
        tables removes the whole source file and all its sheet-views."""
        view = re.sub(r"\W+", "_", name).lower()
        with self._lock:
            if view not in self._views:
                return False
            path = self._source_of.get(view)
            # every view that came from the same source file (xlsx multi-sheet)
            victims = {v for v, p in self._source_of.items() if path and p == path}
            victims.add(view)
            for v in victims:
                for kind in ("VIEW", "TABLE"):
                    try:
                        self.con.execute(f'DROP {kind} IF EXISTS "{v}"')
                    except Exception:
                        pass
                self._views = [x for x in self._views if x != v]
                self._ts_hints.pop(v, None)
                self._source_of.pop(v, None)
        if path:                                   # remove the file — realpath-confined to data_dir
            root = os.path.realpath(self.data_dir)
            rp = os.path.realpath(path)
            if os.path.isfile(rp) and (rp == root or rp.startswith(root + os.sep)):
                try:
                    os.remove(rp)
                except Exception:
                    pass
        return True

    def _table_stat(self, view: str) -> dict:
        try:
            n = self.con.execute(f'SELECT count(*) FROM "{view}"').fetchone()[0]
        except Exception:
            n = None
        try:
            c = len(self.con.execute(f'DESCRIBE "{view}"').fetchall())
        except Exception:
            c = None
        return {"view": view, "rows": n, "cols": c}

    def _load_csv(self, view: str, path: str) -> tuple:
        """Load a CSV as `view`. Returns (rows, skipped) or (None, None) if genuinely
        unparseable (empty / header-only / not a table).

        Fast path: strict read_csv_auto (clean UTF-8). Fallback for messy real-world
        files: transcode a non-UTF-8 file (utf-8-sig -> cp1252 -> latin-1 -> replace)
        to UTF-8, then parse — skipping ONLY genuinely-malformed rows and COUNTING them.
        Never silently bulk-drops rows (e.g. ignore_errors alone would discard every
        non-UTF-8 row); never reports success on 0 rows (upload-honesty invariant)."""
        import os as _os
        import tempfile
        # 1) strict fast path — clean UTF-8 files load unchanged
        try:
            self.con.execute(f'CREATE OR REPLACE TABLE "{view}" AS SELECT * FROM read_csv_auto(\'{path}\')')
            n = self.con.execute(f'SELECT count(*) FROM "{view}"').fetchone()[0]
            if n > 0:
                return n, 0
        except Exception:
            pass
        # 2) transcode fallback — normalize encoding to UTF-8, then parse tolerantly
        raw = open(path, "rb").read()
        text = None
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except Exception:
                continue
        if text is None:
            text = raw.decode("utf-8", errors="replace")
        tf = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8")
        try:
            tf.write(text)
            tf.close()
            for t in ("reject_errors", "reject_scans"):
                try:
                    self.con.execute(f"DROP TABLE IF EXISTS {t}")
                except Exception:
                    pass
            skipped = 0
            try:
                self.con.execute(f'CREATE OR REPLACE TABLE "{view}" AS SELECT * FROM '
                                 f"read_csv_auto('{tf.name}', ignore_errors=true, sample_size=-1, store_rejects=true)")
                skipped = self.con.execute("SELECT count(*) FROM reject_errors").fetchone()[0]
            except Exception:
                try:
                    self.con.execute(f'CREATE OR REPLACE TABLE "{view}" AS SELECT * FROM '
                                     f"read_csv_auto('{tf.name}', ignore_errors=true, sample_size=-1)")
                except Exception:
                    self.con.execute(f'DROP TABLE IF EXISTS "{view}"')
                    return None, None
            n = self.con.execute(f'SELECT count(*) FROM "{view}"').fetchone()[0]
            if n > 0:
                return n, skipped
            self.con.execute(f'DROP TABLE IF EXISTS "{view}"')
            return None, None
        finally:
            try:
                _os.unlink(tf.name)
            except Exception:
                pass
