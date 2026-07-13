#!/usr/bin/env python3
"""
Build the REASONING-LADDER demo DB (ecommerce_ladder.db) for the reasoning-bottleneck test.

WHY A SEPARATE DB (not ecommerce_large.db):
The retrieval grid (the proven thesis result) depends on ecommerce_large.db byte-for-byte,
so we do NOT mutate it. This is a SUPERSET built for a DIFFERENT experiment: hold retrieval
CONSTANT (scaffold=full + pinned tables) and escalate SQL complexity L1->L5 to find where each
model starts producing WRONG answers. It keeps the SAME 27-table shape + the SAME confusable
distractors (so if you ever let retrieval run free it is ~as hard), but ENRICHES the core tables
with the columns and cross-table links the ladder's joins need — links that ecommerce_large.db
lacks (that DB's `sales` has no quarter/order_id/sale_id, `orders` is a distractor with no
channel, `returns` links by product not sale_id). Against those gaps 4 of the 9 reference
queries could not run. Here they all run as written.

TWO things ecommerce_large.db could not do that this DB must:
  1. STRUCTURE — the joins: sales.order_id -> orders(channel) for L2a; returns.sale_id ->
     sales for L2b/L5b (join-through-to-product); an explicit `quarter` for L1b/L4a.
  2. NON-DEGENERATE SEED — ecommerce_large.db has only TWO distinct monthly revenue values
     (every non-Q3 month identical), so L4a's top-product-per-quarter is the SAME product every
     quarter and L5a's month-over-month growth is almost all zeros. Those questions could not
     discriminate models. Here every (product, month) carries a deterministic multiplier so the
     per-quarter winner changes and MoM growth varies month to month.

DETERMINISTIC (no RNG) so the computed expected_values are reproducible. stdlib only.

Run in the app container (or locally):
    python3 - < eval/build_ladder_db.py
    # or: DEMO_DB=/app/ecommerce_ladder.db python3 - < eval/build_ladder_db.py
Then compute the ground-truth answers:
    python3 eval/reasoning_ladder.py --db ecommerce_ladder.db
"""
import math
import os
import sqlite3

DB = os.getenv("DEMO_DB", "/app/ecommerce_ladder.db")
DOCS = os.getenv("DEMO_DOCS", "/app/eval/demo_docs")

MONTHS = [f"2024-{m:02d}" for m in range(1, 13)]
PRODUCTS = ["Aurora Speaker", "Nimbus Router", "Vertex Keyboard", "Halo Monitor",
            "Pulse Earbuds", "Cobalt Laptop", "Fable Tablet", "Quartz Mouse",
            "Ember Charger", "Slate Dock", "Onyx Webcam", "Ivory Stand"]
CHANNELS = ["Online", "Retail", "Partner", "Wholesale"]


def quarter_of(m: str) -> str:
    return f"Q{(int(m[5:7]) - 1) // 3 + 1}"


def seasonal(m: str) -> float:
    # keep the Q3 (Jul/Aug/Sep) production-shortfall dip the q3 doc explains
    return 0.62 if int(m[5:7]) in (7, 8, 9) else 1.0


def pm_factor(i: int, mm: int) -> float:
    """Deterministic per-product, per-month multiplier ~[0.78, 1.30]. Breaks the
    'every month identical' degeneracy so per-quarter winners and MoM growth actually
    move. Uses a fixed trig mix of the product and month indices — reproducible, no RNG."""
    return 1.04 + 0.26 * math.sin(i * 1.7 + mm * 0.9) * math.cos(mm * 0.5 + i * 0.3)


def build_db(con: sqlite3.Connection) -> int:
    c = con.cursor()

    # --- GOLD / core tables (enriched vs ecommerce_large.db) --------------------
    # sale_id is explicit (the ladder's returns join through it); order_id links to
    # orders(channel); quarter is materialised so L1b/L4a need no date arithmetic.
    c.execute("CREATE TABLE sales (sale_id INTEGER PRIMARY KEY, order_id INTEGER, "
              "sale_date TEXT, quarter TEXT, product TEXT, quantity INTEGER, "
              "revenue REAL, cost REAL)")
    c.execute("CREATE TABLE orders (order_id INTEGER PRIMARY KEY, channel TEXT, "
              "order_date TEXT, customer_id INTEGER)")
    c.execute("CREATE TABLE returns (return_id INTEGER PRIMARY KEY, sale_id INTEGER, "
              "return_date TEXT, amount REAL)")
    c.execute("CREATE TABLE produced_items (id INTEGER PRIMARY KEY, produced_date TEXT, "
              "item TEXT, units_produced INTEGER)")

    sid = 0
    for m in MONTHS:
        mm = int(m[5:7])
        for i, p in enumerate(PRODUCTS):
            base = 8000 + i * 900
            rev = round(base * seasonal(m) * pm_factor(i, mm), 2)
            cost = round(rev * (0.55 + (i % 4) * 0.04), 2)
            qty = int(rev // (120 + i * 10))
            sid += 1
            # each sale is one order; channel varies deterministically so revenue
            # splits non-trivially across the 4 channels (L2a)
            channel = CHANNELS[(i + mm) % len(CHANNELS)]
            c.execute("INSERT INTO orders VALUES (?,?,?,?)",
                      (sid, channel, m + "-14", (sid % 40) + 1))
            c.execute("INSERT INTO sales VALUES (?,?,?,?,?,?,?,?)",
                      (sid, sid, m + "-15", quarter_of(m), p, qty, rev, cost))

    # returns reference sale_id (NOT product) -> L5b must join through sales to reach
    # the product. Some sales carry MULTIPLE returns -> the L2b/L5b join-fan-out trap:
    # a model that joins sales->returns row-wise double-counts revenue. Heavier in Q4.
    # Deterministic pick: every k-th sale returns; Q4 sales return more often + multiply.
    rid = 0
    for s in range(1, sid + 1):
        # base month of this sale: sales were inserted month-major, 12 products/month
        month_idx = (s - 1) // len(PRODUCTS)          # 0..11
        mm = month_idx + 1
        prod_i = (s - 1) % len(PRODUCTS)
        # ~1 in 3 sales gets a return; Q4 (mm>=10) gets an extra one (fan-out + heavier)
        if s % 3 == 0:
            n = 2 if mm >= 10 else 1
            for k in range(n):
                rid += 1
                amt = round(600 + prod_i * 55 + mm * 40 + k * 320, 2)
                c.execute("INSERT INTO returns VALUES (?,?,?,?)",
                          (rid, s, MONTHS[month_idx] + "-20", amt))

    pid = 0
    for m in MONTHS:
        for i, p in enumerate(PRODUCTS[:6]):
            pid += 1
            units = int(1200 * seasonal(m))     # Q3 production dip -> weak Q3 sales
            c.execute("INSERT INTO produced_items VALUES (?,?,?,?)", (pid, m + "-01", p, units))

    # --- DISTRACTOR tables (MIRRORS eval/build_demo_db.py, minus `orders` which is now
    # a real dimension above; several deliberately CONFUSABLE with the gold ones so the
    # 27-table retrieval difficulty matches ecommerce_large.db). Keep in sync. -----------
    distractors = {
        "refunds":            "id INTEGER, order_id INTEGER, refund_date TEXT, amount REAL",        # ~returns (trap)
        "manufacturing":      "id INTEGER, plant TEXT, run_date TEXT, output_units INTEGER",        # ~produced_items (trap)
        "sales_forecast":     "id INTEGER, month TEXT, forecast_revenue REAL",                      # ~sales (trap)
        "product_catalog":    "id INTEGER, product TEXT, category TEXT, list_price REAL",           # ~sales.product (trap)
        "revenue_targets":    "id INTEGER, quarter TEXT, target REAL",                              # ~sales (trap)
        "customers":          "id INTEGER, name TEXT, email TEXT, region TEXT, signup_date TEXT",
        "employees":          "id INTEGER, name TEXT, department TEXT, hire_date TEXT, salary REAL",
        "inventory":          "id INTEGER, product TEXT, warehouse TEXT, units_on_hand INTEGER",
        "suppliers":          "id INTEGER, name TEXT, country TEXT, lead_time_days INTEGER",
        "shipments":          "id INTEGER, order_id INTEGER, ship_date TEXT, carrier TEXT, status TEXT",
        "campaigns":          "id INTEGER, name TEXT, channel TEXT, spend REAL, start_date TEXT",
        "order_items":        "id INTEGER, order_id INTEGER, product TEXT, qty INTEGER, price REAL",
        "warehouses":         "id INTEGER, name TEXT, region TEXT, capacity INTEGER",
        "payments":           "id INTEGER, order_id INTEGER, method TEXT, amount REAL, paid_date TEXT",
        "invoices":           "id INTEGER, customer_id INTEGER, issued_date TEXT, amount REAL, status TEXT",
        "regions":            "id INTEGER, name TEXT, country TEXT",
        "categories":         "id INTEGER, name TEXT, parent TEXT",
        "promotions":         "id INTEGER, code TEXT, discount_pct REAL, active INTEGER",
        "reviews":            "id INTEGER, product TEXT, rating INTEGER, review_date TEXT",
        "tickets":            "id INTEGER, customer_id INTEGER, opened_date TEXT, priority TEXT, status TEXT",
        "subscriptions":      "id INTEGER, customer_id INTEGER, plan TEXT, started_date TEXT",
        "vendors":            "id INTEGER, name TEXT, category TEXT",
        "purchase_orders":    "id INTEGER, supplier_id INTEGER, po_date TEXT, amount REAL",
    }
    for name, cols in distractors.items():
        c.execute(f"CREATE TABLE {name} ({cols})")
        ncols = len(cols.split(","))
        for r in range(3):
            vals = tuple((r + 1) if "INTEGER" in cols.split(",")[j] else f"{name}_{r}"
                         for j in range(ncols))
            c.execute(f"INSERT INTO {name} VALUES ({','.join('?' * ncols)})", vals)

    con.commit()
    return len(distractors)


# same operations note as the retrieval DB (kept so a reused doc-arm stays coherent)
DOC = """# Q3 2024 Performance Review — Operations Note

Q3 2024 sales were noticeably weak compared with Q1, Q2, and Q4. The root cause
was NOT demand: it was a supply/production shortfall.

In early July a key supplier missed a components delivery, which forced a
production slowdown across the plants. Units produced (produced_items) fell
roughly 35% for July, August, and September versus the rest of the year. With
less finished inventory available to sell, Q3 revenue dropped in step with the
production dip, even though customer demand and order intake stayed healthy.

Production and supply recovered in October, and Q4 sales rebounded to normal
levels (Q4 net revenue is lower than gross because of a seasonal spike in
returns, not weak demand).

Takeaway: the Q3 weakness was a production/supply constraint, not a market or
pricing problem.
"""


def main():
    os.makedirs(os.path.dirname(DB) or ".", exist_ok=True)
    if os.path.exists(DB):
        os.remove(DB)
    con = sqlite3.connect(DB)
    ndist = build_db(con)
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    nsales = con.execute("SELECT count(*) FROM sales").fetchone()[0]
    nret = con.execute("SELECT count(*) FROM returns").fetchone()[0]
    ndistinct = con.execute(
        "SELECT COUNT(DISTINCT rev) FROM (SELECT substr(sale_date,1,7) ym, SUM(revenue) rev "
        "FROM sales GROUP BY 1)").fetchone()[0]
    con.close()

    os.makedirs(DOCS, exist_ok=True)
    with open(os.path.join(DOCS, "q3_performance_review.md"), "w", encoding="utf-8") as f:
        f.write(DOC)

    print(f"DB: {DB}")
    print(f"tables: {len(tables)} ({ndist} distractors + 4 core) -> {sorted(tables)}")
    print(f"sales rows: {nsales}   returns rows: {nret}")
    print(f"distinct monthly-revenue values: {ndistinct}/12 "
          f"(ecommerce_large.db had 2 -> degenerate; >6 means L4a/L5a can discriminate)")


main()
