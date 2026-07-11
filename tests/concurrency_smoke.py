#!/usr/bin/env python3
"""
Concurrency + persistence acceptance for the DuckDB data layer (foundation package).

Exercises the two foundation fixes together, at the connector level (model-independent,
offline, no LLM, no network), and exits non-zero on any failure so it can gate a deploy:

  A. concurrent same-tenant queries      -> the shared cached connector is hammered from
                                             many threads at once (FastAPI's sync threadpool)
  B. an upload racing a query            -> register_file() interleaved with run_query()
  C. a dashboard refresh burst           -> several pinned tiles' SQL re-run concurrently
                                             (exactly what dashboards.refresh_tile does)
  D. file-backing + restart/migration    -> the store is on disk, and a fresh connector on
                                             the same dirs rebuilds every view (incl. xlsx)

Run ISOLATED (tempdir, zero prod writes), e.g. in a throwaway container from the app image:
    docker run --rm -v /opt/analytiq:/app -w /app analytiq:latest python tests/concurrency_smoke.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading

# import from the repo root regardless of CWD
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from connectors.duckdb_conn import DuckDBConnector, analytics_db_path  # noqa: E402

N_THREADS = 16
ITERS = 40


def _write_fixtures(data_dir: str) -> dict:
    """A CSV and a multi-sheet-ish xlsx, with known row counts."""
    import pandas as pd
    os.makedirs(data_dir, exist_ok=True)
    sales = pd.DataFrame({
        "id": list(range(1, 61)),
        "region": ["north", "south", "east", "west"] * 15,
        "amount": [float(i) for i in range(1, 61)],
    })
    sales.to_csv(os.path.join(data_dir, "sales.csv"), index=False)

    returns = pd.DataFrame({"id": list(range(1, 13)), "reason": ["damaged", "late"] * 6})
    returns.to_csv(os.path.join(data_dir, "returns.csv"), index=False)

    # a workbook with a title row above a real header (exercises the header heuristic)
    xpath = os.path.join(data_dir, "book.xlsx")
    with pd.ExcelWriter(xpath) as xw:
        top = pd.DataFrame(
            [["Quarterly report", None, None],
             ["quarter", "product", "units"],
             ["Q1", "widget", 10], ["Q2", "widget", 20],
             ["Q3", "gadget", 30], ["Q4", "gadget", 40]])
        top.to_excel(xw, sheet_name="data", header=False, index=False)
    return {"sales": 60, "returns": 12, "book_units_total": 100}


def _run_threads(fn, n=N_THREADS):
    errs: list[str] = []
    lock = threading.Lock()

    def wrap(i):
        try:
            fn(i)
        except Exception as e:  # noqa: BLE001 — surface ANY thread failure
            with lock:
                errs.append(f"thread {i}: {type(e).__name__}: {e}")

    ts = [threading.Thread(target=wrap, args=(i,)) for i in range(n)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return errs


def main() -> int:
    root = tempfile.mkdtemp(prefix="concurrency_smoke_")
    data_dir = os.path.join(root, "uploads")
    db_path = analytics_db_path(data_dir, "analytics.duckdb")  # -> <root>/analytics.duckdb
    expect = _write_fixtures(data_dir)
    fails: list[str] = []

    # --- construct once; _register_files loads all fixtures through register_file ----
    conn = DuckDBConnector(data_dir=data_dir, db_path=db_path)
    views = set(conn.schema_by_table().keys())
    for need in ("sales", "returns", "book"):
        if not any(v == need or v.startswith(need) for v in views):
            fails.append(f"setup: view for {need!r} missing after load (got {sorted(views)})")

    def q_sales():
        return conn.run_query("SELECT count(*) AS n FROM sales").rows[0]["n"]

    def q_returns():
        return conn.run_query("SELECT count(*) AS n FROM returns").rows[0]["n"]

    # A. concurrent same-tenant queries -----------------------------------------------
    def hammer(_i):
        for _ in range(ITERS):
            if q_sales() != expect["sales"] or q_returns() != expect["returns"]:
                raise AssertionError("row count mismatch under concurrency")
    errs = _run_threads(hammer)
    fails += [f"A(concurrent queries) {e}" for e in errs]

    # B. an upload racing a query ------------------------------------------------------
    def racer(i):
        import pandas as pd
        for k in range(6):
            if i % 2 == 0:                      # writers register fresh files
                name = f"extra_{i}_{k}"
                p = os.path.join(data_dir, f"{name}.csv")
                pd.DataFrame({"x": list(range(5))}).to_csv(p, index=False)
                conn.register_file(p)
            else:                               # readers keep querying + reading schema
                q_sales()
                conn.schema_by_table()
    errs = _run_threads(racer)
    fails += [f"B(upload racing query) {e}" for e in errs]
    if q_sales() != expect["sales"]:
        fails.append("B: sales table corrupted after racing uploads")

    # C. dashboard refresh burst (several tiles' guarded SQL, concurrently) -------------
    tiles = [
        ("t1", "SELECT region, sum(amount) AS s FROM sales GROUP BY region", 4),
        ("t2", "SELECT count(*) AS n FROM returns", 1),
        ("t3", "SELECT sum(units) AS u FROM book", 1),
        ("t4", "SELECT region, count(*) AS c FROM sales GROUP BY region ORDER BY region", 4),
    ]

    def refresh(i):
        tid, sql, want_rows = tiles[i % len(tiles)]
        for _ in range(ITERS):
            qr = conn.run_query(sql)             # == dashboards.refresh_tile's core
            if len(qr.rows) != want_rows:
                raise AssertionError(f"{tid}: expected {want_rows} rows, got {len(qr.rows)}")
    errs = _run_threads(refresh)
    fails += [f"C(refresh burst) {e}" for e in errs]
    # book units total sanity (xlsx ingested correctly)
    if conn.run_query("SELECT sum(units) AS u FROM book").rows[0]["u"] != expect["book_units_total"]:
        fails.append("C: xlsx 'book' units total wrong (ingest/persist regression)")

    # D. file-backing + restart/migration ---------------------------------------------
    if not (os.path.exists(db_path) and os.path.getsize(db_path) > 0):
        fails.append(f"D: DuckDB file not on disk at {db_path}")
    conn.close()                                 # release the single-writer file lock
    conn2 = DuckDBConnector(data_dir=data_dir, db_path=db_path)   # "restart" — same paths
    v2 = set(conn2.schema_by_table().keys())
    for need in ("sales", "returns", "book"):
        if not any(v == need or v.startswith(need) for v in v2):
            fails.append(f"D: {need!r} not rebuilt after restart (got {sorted(v2)})")
    try:
        if conn2.run_query("SELECT count(*) AS n FROM sales").rows[0]["n"] != expect["sales"]:
            fails.append("D: sales row count wrong after restart")
        if conn2.run_query("SELECT sum(units) AS u FROM book").rows[0]["u"] != expect["book_units_total"]:
            fails.append("D: xlsx 'book' not durable across restart")
    except Exception as e:  # noqa: BLE001
        fails.append(f"D: query failed after restart: {type(e).__name__}: {e}")
    conn2.close()

    # --- report -----------------------------------------------------------------------
    checks = [
        ("A  concurrent same-tenant queries", "A("),
        ("B  upload racing a query", "B"),
        ("C  dashboard refresh burst", "C"),
        ("D  file-backing + restart/migration", "D"),
    ]
    print(f"\nconcurrency_smoke — {N_THREADS} threads x {ITERS} iters, file-backed at {db_path}\n")
    for label, prefix in checks:
        bad = [f for f in fails if f.startswith(prefix)]
        print(f"  [{'FAIL' if bad else 'PASS'}] {label}")
        for b in bad:
            print(f"         - {b}")
    setup_bad = [f for f in fails if f.startswith("setup")]
    for b in setup_bad:
        print(f"  [FAIL] {b}")

    import shutil
    shutil.rmtree(root, ignore_errors=True)
    if fails:
        print(f"\nRESULT: FAIL ({len(fails)} issue(s))")
        return 1
    print("\nRESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
