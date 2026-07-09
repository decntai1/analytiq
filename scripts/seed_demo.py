"""
Seed a demo database matching the gold set (sales / returns / produced_items + noise
tables) so you can test the full pipeline and run the eval immediately.

    python -m scripts.seed_demo            # writes ./demo.db
    DB_URL="sqlite:///demo.db" DATA_SOURCE=database uvicorn api.app:app

The gold set (gold/gold_set.json) is written against this schema.
"""
from __future__ import annotations

import os
import random
random.seed(42)  # deterministic demo data: stub-eval grids comparable across machines
import sqlite3

DB = os.getenv("SEED_DB", "demo.db")


def main() -> None:
    if os.path.exists(DB):
        os.remove(DB)
    c = sqlite3.connect(DB)
    c.executescript("""
    CREATE TABLE sales(month TEXT, product_id INT, revenue REAL, cost REAL, quantity INT);
    CREATE TABLE returns(month TEXT, product_id INT, amount REAL);
    CREATE TABLE produced_items(month TEXT, product_id INT, units_produced INT);
    CREATE TABLE products(product_id INT, name TEXT, category TEXT);
    CREATE TABLE spendings(month TEXT, category TEXT, amount REAL);
    -- noise tables so schema-RAG has something to filter out (recall test)
    CREATE TABLE hr_employees(id INT, name TEXT, dept TEXT);
    CREATE TABLE support_tickets(id INT, opened TEXT, severity TEXT);
    CREATE TABLE inventory(product_id INT, warehouse TEXT, on_hand INT);
    """)
    for p in range(1, 21):
        c.execute("INSERT INTO products VALUES(?,?,?)",
                  (p, f"Product {p:02d}", random.choice(["A", "B", "C"])))
    for m in range(1, 13):
        mm = f"2024-{m:02d}"
        # Q3 (months 7-9) deliberately softer, to make "why Q3 weak" answerable
        season = 0.6 if m in (7, 8, 9) else 1.0
        for p in range(1, 21):
            rev = round(random.uniform(2000, 9000) * season, 2)
            c.execute("INSERT INTO sales VALUES(?,?,?,?,?)",
                      (mm, p, rev, round(rev * 0.55, 2), random.randint(10, 120)))
            c.execute("INSERT INTO returns VALUES(?,?,?)",
                      (mm, p, round(rev * random.uniform(0.01, 0.06), 2)))
            c.execute("INSERT INTO produced_items VALUES(?,?,?)",
                      (mm, p, int(random.randint(80, 300) * season)))
        c.execute("INSERT INTO spendings VALUES(?,?,?)", (mm, "marketing",
                  round(random.uniform(3000, 9000) * (0.5 if m in (7, 8, 9) else 1.0), 2)))
    # noise tables get a few rows too: a wrong-table pick must return PLAUSIBLE
    # wrong data (the silent-miss condition the eval studies), not a telltale
    # empty result that tips the model off.
    for i in range(1, 13):
        c.execute("INSERT INTO hr_employees VALUES(?,?,?)",
                  (i, f"Employee {i:02d}", random.choice(["ops", "sales", "eng"])))
        c.execute("INSERT INTO support_tickets VALUES(?,?,?)",
                  (i, f"2024-{i:02d}-15", random.choice(["low", "med", "high"])))
        c.execute("INSERT INTO inventory VALUES(?,?,?)",
                  (i, random.choice(["BUD", "VIE", "PRG"]), random.randint(0, 500)))
    c.commit()
    c.close()
    print(f"✓ wrote {DB} (sales, returns, produced_items, products, spendings + 3 noise tables)")

    # a small document corpus so the doc-RAG arm (gold item q4 expect_documents)
    # has something to ground in — the numbers above dip in Q3, this memo says why.
    docs = os.getenv("SEED_DOCS_DIR", "./documents")
    os.makedirs(docs, exist_ok=True)
    memo = os.path.join(docs, "q3_2024_postmortem.md")
    with open(memo, "w", encoding="utf-8") as f:
        f.write(
            "# Q3 2024 postmortem\n\n"
            "Q3 sales were weak for two compounding reasons. First, the supplier\n"
            "outage in July halved component deliveries, so production volume dropped\n"
            "roughly 40% versus Q2 (visible in produced_items). Second, the marketing\n"
            "budget was cut ~50% for the quarter (see spendings), reducing inbound\n"
            "demand. Both recovered in October.\n"
        )
    print(f"✓ wrote {memo} (doc-RAG corpus for the 'why was Q3 weak' question)")
    print("  run:  DB_URL=\"sqlite:///%s\" DATA_SOURCE=database uvicorn api.app:app" % DB)


if __name__ == "__main__":
    main()
