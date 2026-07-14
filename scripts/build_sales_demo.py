#!/usr/bin/env python3
r"""
Build the sales-demo SQLite DB for the fan-out sales demo, and (docstring) how the
demo tenant is provisioned. This DB is a permanent sales asset — it lives in the
`analytiq_data` volume at /data/sales_demo.db, so keep this script as its regen source.

WHY: it is a clean, presentable two-table schema (sales 1-to-many returns) where a
Q4 return-rate / net-revenue question exercises the join fan-out. With
SCAFFOLD_AGG_BEFORE_JOIN=1 the trace visibly shows the model's original (fan-out) SQL,
the "-- [aggregate-before-join scaffold: corrected join fan-out]" correction, and the
right number — the demo the fix exists to sell.

Ground truth: Q4 net revenue = 9550 (naive fan-out would give 12550); Aurora Speaker
return fraction = 420/5800 = 7.24% (the fan-out double-counts its revenue).

BUILD (writes into the running app container's data volume):
    docker compose -f docker-compose.prod.yml exec -T app python - < scripts/build_sales_demo.py

PROVISION the dedicated demo tenant (dedicated, database-backed, NEVER touches existing
tenants or the default upload routing; enable_uploads=False keeps it a PURE SQLConnector
so the scaffold's relationships() is available). Credentials go in .env (gitignored), not
the repo. Retrievable any time via `GET /admin/tenants` with the ADMIN_TOKEN.
    POST /admin/tenants  (header X-Admin-Token: $ADMIN_TOKEN)
    {"name":"Sales Demo (fan-out)","data_source":"database",
     "db_url":"sqlite:////data/sales_demo.db","plan":"business",
     "default_model":"ministral-8b","enable_uploads":false}
Then /ask with header X-API-Key: <returned api_key>.
"""
import os
import sqlite3

PATH = os.environ.get("SALES_DEMO_DB", "/data/sales_demo.db")

SALES = [
    # Q4 — the demo quarter (total revenue 10000)
    (1, "Aurora Speaker", "Q4", 3000), (2, "Nimbus Router", "Q4", 2500),
    (3, "Vertex Keyboard", "Q4", 1500), (4, "Halo Monitor", "Q4", 2000),
    (5, "Fable Tablet", "Q4", 1000),
    # Q1-Q3 for realism
    (6, "Aurora Speaker", "Q1", 2800), (7, "Nimbus Router", "Q2", 2600),
    (8, "Vertex Keyboard", "Q3", 1700), (9, "Halo Monitor", "Q1", 2100),
    (10, "Fable Tablet", "Q2", 1200),
]
RETURNS = [
    (1, 1, 200), (2, 1, 100),   # sale 1 (Q4) has TWO returns -> the fan-out
    (3, 2, 150),                 # sale 2 (Q4) one return
    (4, 6, 120), (5, 7, 90),     # other-quarter returns
]


def main() -> None:
    if os.path.exists(PATH):
        os.remove(PATH)
    con = sqlite3.connect(PATH)
    c = con.cursor()
    c.execute("CREATE TABLE sales (sale_id INTEGER PRIMARY KEY, product TEXT, quarter TEXT, revenue REAL)")
    c.execute("CREATE TABLE returns (return_id INTEGER PRIMARY KEY, sale_id INTEGER, amount REAL)")
    c.executemany("INSERT INTO sales VALUES (?,?,?,?)", SALES)
    c.executemany("INSERT INTO returns VALUES (?,?,?)", RETURNS)
    con.commit()
    correct = con.execute(
        "SELECT (SELECT SUM(revenue) FROM sales WHERE quarter='Q4') - "
        "COALESCE((SELECT SUM(amount) FROM returns r JOIN sales s ON r.sale_id=s.sale_id "
        "WHERE s.quarter='Q4'),0)").fetchone()[0]
    print(f"built {PATH}: Q4 net revenue (correct) = {correct}")
    con.close()


if __name__ == "__main__":
    main()
