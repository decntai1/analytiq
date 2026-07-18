#!/usr/bin/env python3
"""Self-contained unit test for the deterministic forecasting module.

Builds an in-memory DuckDB with a KNOWN 36-month seasonal series and asserts:
  - Holt-Winters fits, returns `horizon` points, each with lower <= mean <= upper
    and a strictly positive band (intervals are always present — the band IS the
    honesty; a point forecast without one would be a fabrication);
  - the result is byte-for-byte identical on a repeat call (determinism);
  - `period='auto'` infers monthly for a ~3-year span;
  - the linear method works and also yields a band;
  - every honest refusal raises ForecastError (never a 500): too few points,
    a non-numeric value column, an unparseable time column, a bad horizon.

Run:  python3 tests/test_forecast.py   (exit 0 = all pass; needs duckdb+statsmodels)
"""
import json
import math
import sys

sys.path.insert(0, ".")
import duckdb

from core.forecast import ForecastError, forecast


class _Res:
    def __init__(self, cols, rows, truncated=False):
        self.columns, self.rows, self.truncated = cols, rows, truncated


class FakeConn:
    """Minimal connector shim: real DuckDB SQL, the QueryResult interface
    (.columns/.rows/.truncated) forecast.py depends on, and schema_by_table()."""
    def __init__(self, con, tables):
        self.con, self._tables = con, tables

    def schema_by_table(self):
        return {t: "" for t in self._tables}

    def run_query(self, sql):
        cur = self.con.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        return _Res(cols, rows)


def _seasonal_db():
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE sales (day DATE, revenue DOUBLE)")
    rows = []
    for i in range(36):  # 2021-01 .. 2023-12, one row per month
        y, mth = 2021 + i // 12, i % 12 + 1
        # trend + clean season + DETERMINISTIC irregular wiggle (not random, so
        # the fit has residual variance -> a real band, yet repeats byte-identically)
        val = (100 + 2 * i + 25 * math.sin(2 * math.pi * (i % 12) / 12)
               + 8 * math.sin(i * 2.399))
        rows.append((f"{y}-{mth:02d}-01", val))
    con.executemany("INSERT INTO sales VALUES (?, ?)", rows)
    # a too-short series, a text column, and an unparseable date column
    con.execute("CREATE TABLE tiny AS SELECT * FROM sales LIMIT 5")
    con.execute("CREATE TABLE txt (day DATE, note VARCHAR)")
    con.executemany("INSERT INTO txt VALUES (?, ?)",
                    [(f"2022-{m:02d}-01", "n/a") for m in range(1, 13)])
    con.execute("CREATE TABLE baddate (ts VARCHAR, revenue DOUBLE)")
    con.executemany("INSERT INTO baddate VALUES (?, ?)",
                    [("not-a-date", float(i)) for i in range(12)])
    return FakeConn(con, ["sales", "tiny", "txt", "baddate"])


def _expect(fn, *, msg):
    try:
        fn()
    except ForecastError:
        return
    raise AssertionError(f"expected ForecastError: {msg}")


def main():
    conn = _seasonal_db()

    # 1. seasonal fit ------------------------------------------------------
    r = forecast(conn, "sales", "day", "revenue", horizon=6, period="M",
                 method="holt_winters")
    assert r["method_used"] == "holt_winters", r["method_used"]
    assert r["n_points"] == 36, r["n_points"]
    assert len(r["forecast"]) == 6, len(r["forecast"])
    for p in r["forecast"]:
        assert p["lower"] <= p["y"] <= p["upper"], p
        assert p["upper"] > p["lower"], f"band must be non-degenerate: {p}"
    assert r["spec"]["type"] == "forecast"
    kinds = {row["kind"] for row in r["rows"]}
    assert kinds == {"history", "forecast"}, kinds
    assert r["diagnostics"]["seasonal_periods"] == 12
    assert r["sql"].lower().startswith("select date_trunc")
    print("PASS  holt-winters fit: 6 points, all with a non-degenerate interval")

    # 2. determinism (byte-for-byte) --------------------------------------
    r2 = forecast(conn, "sales", "day", "revenue", horizon=6, period="M",
                  method="holt_winters")
    assert json.dumps(r, sort_keys=True) == json.dumps(r2, sort_keys=True), \
        "forecast must be byte-for-byte deterministic on repeat"
    print("PASS  determinism: identical result on repeat")

    # 3. auto period -------------------------------------------------------
    ra = forecast(conn, "sales", "day", "revenue", horizon=3, period="auto")
    assert ra["period"] == "M", ra["period"]
    print(f"PASS  auto period -> monthly (method {ra['method_used']})")

    # 4. linear method -----------------------------------------------------
    rl = forecast(conn, "sales", "day", "revenue", horizon=4, period="M",
                  method="linear")
    assert rl["method_used"] == "linear"
    assert all(p["upper"] > p["lower"] for p in rl["forecast"])
    print("PASS  linear trend: fits with a t-based interval")

    # 5. honest refusals ---------------------------------------------------
    _expect(lambda: forecast(conn, "sales", "day", "revenue", horizon=0,
                             period="M"), msg="bad horizon")
    _expect(lambda: forecast(conn, "tiny", "day", "revenue", horizon=3,
                             period="M"), msg="too few points")
    _expect(lambda: forecast(conn, "txt", "day", "note", horizon=3,
                             period="M"), msg="non-numeric value column")
    _expect(lambda: forecast(conn, "baddate", "ts", "revenue", horizon=3,
                             period="auto"), msg="unparseable time column")
    _expect(lambda: forecast(conn, "sales", "nope", "revenue", horizon=3,
                             period="M"), msg="unknown column")
    print("PASS  honest refusals: horizon, sparsity, non-numeric, bad dates, bad column")

    print("\nALL FORECAST UNIT CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
