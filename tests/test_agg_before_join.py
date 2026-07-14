#!/usr/bin/env python3
"""Self-contained unit test for the aggregate-before-join scaffold.

Builds a tiny in-memory SQLite fan-out (a sale with two returns) and asserts:
  - relationships are derived from PK+column names (no FK declarations needed);
  - the fan-out anti-pattern is rewritten to the CORRECT number;
  - legitimate many->one joins and already-correct queries are NOT touched;
  - the module is a safe no-op on unparseable / multi-statement input.

Run:  python3 tests/test_agg_before_join.py   (exit 0 = all pass; needs sqlglot)
"""
import sqlite3
import sys

sys.path.insert(0, ".")
from index.agg_before_join import derive_relationships, rewrite


def _fixture():
    con = sqlite3.connect(":memory:")
    con.executescript("""
        CREATE TABLE sales   (sale_id INTEGER PRIMARY KEY, product TEXT, revenue REAL);
        CREATE TABLE returns (return_id INTEGER PRIMARY KEY, sale_id INTEGER, amount REAL);
        INSERT INTO sales   VALUES (1,'A',100),(2,'A',200),(3,'B',50);
        -- sale 1 has TWO returns => a row-wise join double-counts sale 1's revenue
        INSERT INTO returns VALUES (10,1,30),(11,1,10),(12,2,20);
    """)
    pk, cols = {}, {}
    for t in ("sales", "returns"):
        info = con.execute(f"PRAGMA table_info({t})").fetchall()
        cols[t] = [c[1] for c in info]
        pk[t] = [c[1] for c in info if c[5]]
    return con, pk, cols


def _scalar(con, sql):
    return con.execute(sql).fetchone()[0]


def main():
    con, pk, cols = _fixture()
    rels = derive_relationships(pk, cols)
    assert any(r.one_table == "sales" and r.many_table == "returns" and r.key == "sale_id"
               for r in rels), f"expected sales-1:N->returns, got {rels}"
    # returns.sale_id is NOT returns' PK, so no spurious returns->sales; sanity:
    assert not any(r.one_table == "returns" for r in rels), rels

    true_net = 350 - 60  # SUM(revenue)=350, SUM(amount)=60  => 290
    fanout = ("SELECT SUM(sales.revenue) - COALESCE(SUM(returns.amount),0) AS net "
              "FROM sales LEFT JOIN returns ON sales.sale_id = returns.sale_id")
    assert _scalar(con, fanout) != true_net, "fixture should exhibit the fan-out bug"
    new_sql, fired, _ = rewrite(fanout, rels, cols)
    assert fired, "fan-out query should be rewritten"
    assert abs(_scalar(con, new_sql) - true_net) < 1e-6, \
        f"rewrite gave {_scalar(con, new_sql)}, expected {true_net}"

    # grouped fan-out (return fraction per product): row-wise join double-counts revenue
    grouped = ("SELECT s.product, COALESCE(SUM(r.amount),0)/SUM(s.revenue) AS frac "
               "FROM sales s LEFT JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product")
    new_g, fired_g, _ = rewrite(grouped, rels, cols)
    assert fired_g
    got = {row[0]: row[1] for row in con.execute(new_g).fetchall()}
    # A: returns 30+10+20=60 / revenue 300 = 0.20 ; B: 0 / 50 = 0.0 (must survive, LEFT JOIN)
    assert abs(got["A"] - 60 / 300) < 1e-6, got
    assert got.get("B") in (0, 0.0), f"zero-return product B must survive at 0.0, got {got}"

    # NO-OP: legitimate many->one aggregate (SUM over the MANY side) is untouched
    _, fired_noop, _ = rewrite(
        "SELECT SUM(r.amount) FROM returns r JOIN sales s ON r.sale_id = s.sale_id", rels, cols)
    assert not fired_noop, "aggregating the many side must not fire"

    # NO-OP: already-correct pre-aggregated form is untouched
    _, fired_ok, _ = rewrite(
        "SELECT (SELECT SUM(revenue) FROM sales) - (SELECT SUM(amount) FROM returns)", rels, cols)
    assert not fired_ok

    # NO-OP: unparseable / multi-statement input returns unchanged, no exception
    for bad in ("this is not sql", "SELECT 1; SELECT 2", ""):
        out, f, _ = rewrite(bad, rels, cols)
        assert f is False and out == bad

    print("test_agg_before_join: ALL PASS")


if __name__ == "__main__":
    main()
