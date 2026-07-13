#!/usr/bin/env python3
"""
reasoning_ladder.py — the SQL-complexity ladder for the reasoning-bottleneck test.

PURPOSE
-------
The retrieval result is proven (scaffolding equalizes table-finding across model
sizes). This is the COMPLEMENT: hold retrieval constant (scaffold=full + pinned
tables, so the right tables are handed to every model) and ESCALATE SQL complexity,
to find AT WHICH COMPLEXITY each model (8B/20B/120B/480B) starts producing WRONG
answers.

The retrieval gold set is all L1 (single-table aggregation) — too easy to tell the
models apart (all sit at ~0 errors from 20B up). This ladder climbs L1->L5 so the
models DIVERGE, and the divergence point per model IS the reasoning boundary.

KEY DESIGN POINT — why this needs ANSWER-CHECKING, not just "did it run":
On easy SQL, "executed without error" ~= "correct". On HARD SQL, a model can write
a query that RUNS FINE but computes the WRONG number (wrong join = double-count,
wrong window partition, off-by-one in a growth calc). score.py historically only
checked execution — it would score a wrong-but-runs query as SUCCESS. So each item
here carries a computed `expected_value` (the ground-truth answer from the real
data), and score.py now grades the model's answer against it (answer_correct).

This file computes the ground-truth answers by running the reference SQL against the
LADDER DB (eval/build_ladder_db.py -> ecommerce_ladder.db), whose schema is built to
match these references exactly. The reference SQL is used ONLY to compute the answer;
in the eval the model must write its OWN SQL.

Run:
    python3 eval/reasoning_ladder.py --db ecommerce_ladder.db
"""
from __future__ import annotations

import argparse
import json
import sqlite3

# Tolerance presets for grade_answer (see eval/score.py). Revenue totals grade tight
# (0.5% rel); percentages/growth grade with a 0.5-point absolute floor because a model's
# own unrounded SQL differs from the ROUND(...,2) reference by a hair.
REV = {"rtol": 0.005, "atol": 0.01}
# scale_tol: a "fraction" (0.15) vs "percent" (15) reading of the ambiguous return-rate /
# growth-rate prompts is a unit choice, not a reasoning error — accept either.
PCT = {"rtol": 0.01, "atol": 0.5, "scale_tol": True}

LADDER = [
    # ---- L1: single-table aggregation (baseline — every model should pass) ----
    {
        "id": "L1a_total_revenue",
        "level": 1,
        "question": "What was the total revenue across all sales?",
        "reference_sql": "SELECT SUM(revenue) FROM sales",
        "expected_tables": ["sales"],
        "ev": {"kind": "scalar", **REV},
        "why_hard": "Nothing. Baseline — one table, one aggregate.",
    },
    {
        "id": "L1b_revenue_by_quarter",
        "level": 1,
        "question": "What was total revenue per quarter?",
        "reference_sql": "SELECT quarter, SUM(revenue) FROM sales GROUP BY quarter ORDER BY quarter",
        "expected_tables": ["sales"],
        "ev": {"kind": "map", **REV},          # quarter -> revenue
        "why_hard": "Trivial GROUP BY. Baseline.",
    },

    # ---- L2: multi-table JOINs ----
    {
        "id": "L2a_revenue_by_channel",
        "level": 2,
        "question": "What was total revenue per sales channel? "
                    "(channel is on the orders table, revenue is on sales)",
        "reference_sql": """
            SELECT o.channel, SUM(s.revenue)
            FROM sales s JOIN orders o ON s.order_id = o.order_id
            GROUP BY o.channel ORDER BY SUM(s.revenue) DESC
        """,
        "expected_tables": ["sales", "orders"],
        "ev": {"kind": "map", **REV},          # channel -> revenue
        "why_hard": "JOIN across sales->orders on order_id. Revenue and channel live in "
                    "different tables; a wrong join key silently changes totals.",
    },
    {
        "id": "L2b_net_revenue",
        "level": 2,
        "question": "What was net revenue (sales revenue minus returned amounts) overall?",
        "reference_sql": """
            SELECT (SELECT COALESCE(SUM(revenue),0) FROM sales)
                 - (SELECT COALESCE(SUM(amount),0) FROM returns)
        """,
        "expected_tables": ["sales", "returns"],
        "ev": {"kind": "scalar", **REV},
        "why_hard": "Combine two tables and SUBTRACT. A model that joins sales->returns "
                    "row-wise DOUBLE-COUNTS revenue (some sales have >1 return) and drops "
                    "non-returned sales — a wrong number that still runs. Classic fan-out trap.",
    },

    # ---- L3: subqueries / nested logic ----
    {
        "id": "L3a_above_avg_products",
        "level": 3,
        "question": "Which products have total revenue above the average total "
                    "revenue per product? List them.",
        "reference_sql": """
            SELECT product, SUM(revenue) AS rev FROM sales GROUP BY product
            HAVING SUM(revenue) > (
                SELECT AVG(prod_rev) FROM (
                    SELECT SUM(revenue) AS prod_rev FROM sales GROUP BY product
                )
            ) ORDER BY rev DESC
        """,
        "expected_tables": ["sales"],
        "ev": {"kind": "label_set"},           # the SET of product names above avg
        "why_hard": "Two-level aggregation: per-product totals, then the AVERAGE of those "
                    "totals, then filter. Models often compute AVG over ROWS (wrong) instead "
                    "of AVG over per-product SUMS (right) — runs fine, wrong answer.",
    },

    # ---- L4: window functions (the difficulty spike) ----
    {
        "id": "L4a_top_product_per_quarter",
        "level": 4,
        "question": "For each quarter, which single product had the highest revenue "
                    "in that quarter, and how much?",
        "reference_sql": """
            WITH pq AS (
                SELECT quarter, product, SUM(revenue) AS rev
                FROM sales GROUP BY quarter, product
            ), ranked AS (
                SELECT quarter, product, rev,
                       ROW_NUMBER() OVER (PARTITION BY quarter ORDER BY rev DESC) AS rk
                FROM pq
            )
            SELECT quarter, product, rev FROM ranked WHERE rk = 1 ORDER BY quarter
        """,
        "expected_tables": ["sales"],
        "ev": {"kind": "label_map"},           # quarter -> winning product (the trap)
        "why_hard": "WINDOW FUNCTION (ROW_NUMBER OVER PARTITION BY quarter). Weak models "
                    "fall back to GROUP BY that returns the max REVENUE but the WRONG product "
                    "name, or rank globally instead of per quarter. Runs, wrong answer.",
    },
    {
        "id": "L4b_running_monthly_total",
        "level": 4,
        "question": "Show the cumulative (running) total of revenue by month across "
                    "the year — each month's figure should include all prior months.",
        "reference_sql": """
            WITH m AS (
                SELECT substr(sale_date,1,7) AS ym, SUM(revenue) AS rev
                FROM sales GROUP BY substr(sale_date,1,7)
            )
            SELECT ym, SUM(rev) OVER (ORDER BY ym) AS running_total
            FROM m ORDER BY ym
        """,
        "expected_tables": ["sales"],
        "ev": {"kind": "ordered", **REV},      # 12 cumulative values, in month order
        "why_hard": "SUM(...) OVER (ORDER BY ...) — a running/cumulative window. Models "
                    "frequently produce per-month totals (no accumulation) or mis-order it.",
    },

    # ---- L5: compound + edge cases (hardest) ----
    {
        "id": "L5a_mom_growth",
        "level": 5,
        "question": "What was the month-over-month revenue growth RATE (as a "
                    "percentage) for each month? The first month has no prior month.",
        "reference_sql": """
            WITH m AS (
                SELECT substr(sale_date,1,7) AS ym, SUM(revenue) AS rev
                FROM sales GROUP BY substr(sale_date,1,7)
            ), lagged AS (
                SELECT ym, rev, LAG(rev) OVER (ORDER BY ym) AS prev_rev FROM m
            )
            SELECT ym,
                   CASE WHEN prev_rev IS NULL THEN NULL
                        ELSE ROUND((rev - prev_rev) * 100.0 / prev_rev, 2) END AS growth_pct
            FROM lagged ORDER BY ym
        """,
        "expected_tables": ["sales"],
        "ev": {"kind": "ordered", **PCT},      # 12 growth %; row0 is None (the edge case)
        "why_hard": "Compound: LAG() for the prior month, a division for the rate, AND correct "
                    "NULL handling for the first month. Integer division, wrong prior month, or "
                    "crashing on the first-month null all give subtly wrong output.",
    },
    {
        "id": "L5b_return_rate_by_product",
        "level": 5,
        "question": "For each product, what fraction of its revenue was returned? "
                    "(returned amount divided by that product's sales revenue). "
                    "Rank products from highest return-fraction to lowest.",
        "reference_sql": """
            WITH prod_sales AS (
                SELECT product, SUM(revenue) AS rev FROM sales GROUP BY product
            ), prod_returns AS (
                SELECT s.product, SUM(r.amount) AS returned
                FROM returns r JOIN sales s ON r.sale_id = s.sale_id
                GROUP BY s.product
            )
            SELECT ps.product,
                   ROUND(COALESCE(pr.returned,0) * 100.0 / ps.rev, 2) AS return_pct
            FROM prod_sales ps LEFT JOIN prod_returns pr ON ps.product = pr.product
            ORDER BY return_pct DESC
        """,
        "expected_tables": ["sales", "returns"],
        "ev": {"kind": "map", **PCT},          # product -> return %; all 12 products (LEFT JOIN)
        "why_hard": "Hardest: returns reach product only THROUGH sales (returns has sale_id, "
                    "not product) — join returns->sales, aggregate returns per product, aggregate "
                    "sales per product SEPARATELY (or double-count via the join), LEFT JOIN so "
                    "zero-return products survive, then divide. Many independent ways to go wrong.",
    },
]


def _build_expected_value(ev: dict, rows: list) -> dict:
    """Turn the reference SQL's rows into a stored expected_value (mirrors the extraction
    grade_answer() does on the model's rows: col0 = label, first numeric = value; for
    label_map col1 = the text answer)."""
    kind = ev["kind"]
    out = {k: v for k, v in ev.items()}
    if kind == "scalar":
        out["value"] = rows[0][0]
    elif kind == "map":
        out["pairs"] = {r[0]: round(r[1], 2) if isinstance(r[1], float) else r[1] for r in rows}
    elif kind == "ordered":
        out["rows"] = [[r[0], round(r[1], 2) if isinstance(r[1], float) else r[1]] for r in rows]
    elif kind == "label_map":
        out["pairs"] = {r[0]: r[1] for r in rows}
    elif kind == "label_set":
        out["labels"] = [r[0] for r in rows]
    return out


def emit_gold(db_path: str, out_path: str) -> None:
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    items = []
    for item in LADDER:
        rows = cur.execute(item["reference_sql"]).fetchall()
        items.append({
            "id": item["id"],
            "level": item["level"],
            "question": item["question"],
            "expected_tables": item["expected_tables"],
            "expect_chart": False,
            "expected_value": _build_expected_value(item["ev"], rows),
            "notes": item["why_hard"].strip(),
        })
    doc = {
        "_about": "Reasoning-bottleneck ladder (L1->L5). Retrieval held CONSTANT (run score.py "
                  "with --pin-tables at level=full); expected_value is graded by score.py's "
                  "grade_answer(). Built from eval/reasoning_ladder.py against ecommerce_ladder.db "
                  "(eval/build_ladder_db.py). Regenerate: python3 eval/reasoning_ladder.py "
                  "--db ecommerce_ladder.db --emit-gold gold/reasoning_ladder.json",
        "items": items,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
    print(f"wrote {out_path} ({len(items)} items)")


def compute_answers(db_path: str) -> None:
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    print("=" * 78)
    print("REASONING LADDER — computed ground-truth answers (the expected_values to grade)")
    print("=" * 78)
    by_level: dict[int, int] = {}
    for item in LADDER:
        by_level[item["level"]] = by_level.get(item["level"], 0) + 1
        try:
            rows = cur.execute(item["reference_sql"]).fetchall()
        except Exception as e:
            print(f"\n[{item['id']}] L{item['level']}  *** REFERENCE SQL FAILED: {e} ***")
            continue
        if len(rows) == 1 and len(rows[0]) == 1:
            ans = rows[0][0]
            ans_str = f"{ans:,.2f}" if isinstance(ans, float) else str(ans)
            answer_repr = f"scalar = {ans_str}"
        else:
            answer_repr = f"{len(rows)} rows: " + "; ".join(
                str(tuple(round(c, 2) if isinstance(c, float) else c for c in r)) for r in rows)
        print(f"\n[{item['id']}]  LEVEL {item['level']}")
        print(f"  Q: {item['question']}")
        print(f"  ANSWER: {answer_repr}")

    print("\n" + "=" * 78)
    print("LADDER SHAPE:", ", ".join(f"L{k}={v}q" for k, v in sorted(by_level.items())))
    print("=" * 78)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="ecommerce_ladder.db")
    ap.add_argument("--emit-gold", metavar="PATH",
                    help="write the gold set (question + computed expected_value) to PATH")
    args = ap.parse_args()
    compute_answers(args.db)
    if args.emit_gold:
        emit_gold(args.db, args.emit_gold)


if __name__ == "__main__":
    main()
