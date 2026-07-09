#!/usr/bin/env python3
"""
Build the eval demo DB (+ the q4 document) that the gold set expects.

Why this exists: eval/score.py measures table_recall — did schema-RAG retrieve the
right tables? With only the 3 gold tables and SCHEMA_TOP_K=6, top-6-of-3 = all 3
every time, so recall saturates at 1.0 and the thesis metric can't discriminate.
The fix is DISTRACTOR tables: ~24 plausible business tables (several deliberately
CONFUSABLE with the gold ones — refunds~returns, manufacturing~produced_items,
sales_forecast~sales) so top-K must actually choose and CAN miss the right table.
Only then does the q2 net-revenue trap bite and the recall metric mean something.

The gold set scores table_recall / chart_ok / docs_ok / errors — NOT exact answer
values — so the data just needs to be coherent + queryable (a Q3 dip and Q4 returns
make the traps realistic). Deterministic; stdlib only.

Run in the app container:
    docker compose -f docker-compose.prod.yml exec -T app python - < eval/build_demo_db.py
Then run the eval against it (DB_URL default already points at /app/ecommerce_large.db):
    docker compose exec -e DOCS_DIR=/app/eval/demo_docs -T app \
        python -m eval.score --models gpt-oss-20b --levels none full
"""
import os
import sqlite3

DB = os.getenv("DEMO_DB", "/app/ecommerce_large.db")
DOCS = os.getenv("DEMO_DOCS", "/app/eval/demo_docs")

MONTHS = [f"2024-{m:02d}" for m in range(1, 13)]
PRODUCTS = ["Aurora Speaker", "Nimbus Router", "Vertex Keyboard", "Halo Monitor",
            "Pulse Earbuds", "Cobalt Laptop", "Fable Tablet", "Quartz Mouse",
            "Ember Charger", "Slate Dock", "Onyx Webcam", "Ivory Stand"]
# quarter -> monthly revenue health per product (Q3 = Jul/Aug/Sep dips ~35%)
def month_factor(m: str) -> float:
    mm = int(m[5:7])
    return 0.62 if mm in (7, 8, 9) else 1.0     # the Q3 weakness the q4 doc explains


def build_db(con: sqlite3.Connection) -> None:
    c = con.cursor()

    # --- GOLD tables -------------------------------------------------------
    c.execute("CREATE TABLE sales (id INTEGER PRIMARY KEY, sale_date TEXT, product TEXT, "
              "quantity INTEGER, revenue REAL, cost REAL)")
    sid = 0
    for m in MONTHS:
        for i, p in enumerate(PRODUCTS):
            base = 8000 + i * 900
            rev = round(base * month_factor(m) * (1 + (i % 5) * 0.07), 2)
            cost = round(rev * (0.58 + (i % 4) * 0.03), 2)     # gross_margin = (rev-cost)/rev
            qty = int(rev // (120 + i * 10))
            sid += 1
            c.execute("INSERT INTO sales VALUES (?,?,?,?,?,?)",
                      (sid, m + "-15", p, qty, rev, cost))

    c.execute("CREATE TABLE returns (id INTEGER PRIMARY KEY, return_date TEXT, product TEXT, amount REAL)")
    rid = 0
    for m in MONTHS:
        mm = int(m[5:7])
        # heavier returns in Q4 (Oct-Dec) so net revenue < gross for the q2 trap
        n = 3 if mm >= 10 else 1
        for k in range(n):
            rid += 1
            amt = round(1400 + mm * 90 + k * 300, 2)
            c.execute("INSERT INTO returns VALUES (?,?,?,?)",
                      (rid, m + "-20", PRODUCTS[(mm + k) % len(PRODUCTS)], amt))

    c.execute("CREATE TABLE produced_items (id INTEGER PRIMARY KEY, produced_date TEXT, "
              "item TEXT, units_produced INTEGER)")
    pid = 0
    for m in MONTHS:
        for i, p in enumerate(PRODUCTS[:6]):
            pid += 1
            units = int(1200 * month_factor(m))     # Q3 production dip -> weak Q3 sales
            c.execute("INSERT INTO produced_items VALUES (?,?,?,?)", (pid, m + "-01", p, units))

    # --- DISTRACTOR tables (some deliberately CONFUSABLE with the gold ones) ----
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
        "orders":             "id INTEGER, user_id INTEGER, order_date TEXT, total REAL",
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
        for r in range(3):     # a few rows so the table isn't empty
            vals = tuple((r + 1) if "INTEGER" in cols.split(",")[j] else f"{name}_{r}"
                         for j in range(ncols))
            c.execute(f"INSERT INTO {name} VALUES ({','.join('?' * ncols)})", vals)

    con.commit()
    return len(distractors)


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
    con.close()

    os.makedirs(DOCS, exist_ok=True)
    with open(os.path.join(DOCS, "q3_performance_review.md"), "w", encoding="utf-8") as f:
        f.write(DOC)

    print(f"DB: {DB}")
    print(f"tables: {len(tables)} ({ndist} distractors) -> {sorted(tables)}")
    print(f"sales rows: {nsales}")
    print(f"doc: {os.path.join(DOCS, 'q3_performance_review.md')}")
    print(f"SCHEMA_TOP_K=6 over {len(tables)} tables -> retrieval MUST discriminate "
          f"(recall can now be < 1.0)")


main()
