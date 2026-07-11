"""
Offline table-labelling agent — writes a FROZEN labels.json for schema-RAG.

Run ONCE against the demo DB with ONE fixed registry model (recorded in the file's
`_meta`). For each table it hands the model that table's schema + a few sample rows
PLUS the roster of every other table in the database, and asks for a compact catalog
label: analytical PURPOSE, GRAIN, what it is NOT (vs its confusable siblings), and
key columns. Embedding that (index/labels.py) is what lets retrieval tell `sales`
from `revenue_targets` and `produced_items` from `manufacturing`.

Guardrail §4.2: labels are FROZEN — generated here, offline, once; never per query.
The labeller model is recorded in the output. The labeller has NO tools and touches
no data: it only reads schema + read-only samples and emits JSON.

Usage:
    python -m eval.label                       # gpt-oss-20b over settings.db_url -> ./labels.json
    python -m eval.label --model gpt-oss-20b --out labels.json --db-url sqlite:///ecommerce_large.db
Then turn it on for the eval / product by pointing SCHEMA_LABELS_PATH at the file.
"""
from __future__ import annotations

import argparse
import json
import re
import time

from connectors.sql import SQLConnector

# The ONE fixed labeller. gpt-oss-20b: tool-verified, capable enough for descriptive
# cataloguing, and quota-friendly on the free Ollama key (120B is reserved — it burns
# quota fast and labelling does not need it). Recorded in labels.json _meta.
DEFAULT_LABELLER = "gpt-oss-20b"

_FIELDS = ("summary", "grain", "distinct_from", "key_columns")


def get_samples(connector, table: str, n: int = 5) -> dict:
    """Read-only sample of a table: {columns, rows}. Goes through the connector's
    read-only guard (SELECT only). Never raises — returns empty on any failure."""
    try:
        qr = connector.run_query(f'SELECT * FROM "{table}" LIMIT {int(n)}')
        return {"columns": list(qr.columns), "rows": [dict(r) for r in qr.rows]}
    except Exception:
        return {"columns": [], "rows": []}


def build_label_prompt(table: str, schema_desc: str, samples: dict,
                       roster: dict[str, str]) -> tuple[str, str]:
    """(system, user) for one table. The roster (every OTHER table's one-line schema)
    is the context that lets the model name confusable siblings in `distinct_from`."""
    system = (
        "You are a precise data cataloguer. Given ONE database table (its schema and a "
        "few sample rows) and the list of OTHER tables in the same database, write a "
        "compact catalog label for the ONE table. Respond with PURE JSON only (no prose, "
        "no markdown), an object with exactly these keys:\n"
        '  "summary":       one sentence — the table\'s analytical PURPOSE (what it is used '
        "to answer).\n"
        '  "grain":         what ONE ROW represents (e.g. "one row per order line", '
        '"one row per product per month").\n'
        '  "distinct_from": the confusable sibling table(s) from the roster this is most '
        "likely to be mistaken for, and the KEY DIFFERENCE — begin by naming them. If none "
        'are confusable, use "".\n'
        '  "key_columns":   3-6 column names most useful for analysis (must be real columns '
        "of THIS table).\n"
        "Base every field ONLY on the evidence given. Do not invent columns or tables."
    )
    others = "\n".join(f"- {t}: {d}" for t, d in roster.items() if t != table)
    sample_str = json.dumps(samples["rows"][:5], default=str)[:2000]
    user = (
        f"TABLE TO LABEL: {table}\n"
        f"SCHEMA: {schema_desc}\n"
        f"SAMPLE ROWS: {sample_str}\n\n"
        f"OTHER TABLES IN THIS DATABASE (for distinct_from):\n{others}\n\n"
        "Return the JSON label for "
        f"{table} now."
    )
    return system, user


def _parse_label(text: str, valid_columns: list[str]) -> dict | None:
    """Parse the model's JSON label; keep only known fields; drop key_columns that
    aren't real columns of the table. Returns None if unparseable / empty."""
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.M).strip()
    # tolerate leading/trailing prose by grabbing the first {...} block
    if not t.startswith("{"):
        m = re.search(r"\{.*\}", t, flags=re.S)
        t = m.group(0) if m else t
    try:
        raw = json.loads(t)
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    out: dict = {}
    for f in ("summary", "grain", "distinct_from"):
        v = raw.get(f)
        if isinstance(v, str) and v.strip():
            out[f] = v.strip()
    keys = raw.get("key_columns")
    if isinstance(keys, list):
        cols_lower = {c.lower(): c for c in valid_columns}
        kept = [cols_lower[str(k).lower()] for k in keys if str(k).lower() in cols_lower]
        if kept:
            out["key_columns"] = kept
    return out or None


def run_labelling(model: str = DEFAULT_LABELLER, out_path: str = "labels.json",
                  db_url: str | None = None, connector=None,
                  tables: list[str] | None = None) -> dict:
    """Label every table once and write out_path. Returns the written document.
    Partial success is fine: a table the model fails to label is simply omitted
    (index/labels.py falls back to its base schema text — behaviour unchanged)."""
    from core.llm import get_provider
    conn = connector or SQLConnector(db_url)
    provider = get_provider(model)
    schema = conn.schema_by_table()
    roster = {t: d for t, d in schema.items()}
    names = tables or list(schema.keys())

    labels: dict[str, dict] = {}
    for i, table in enumerate(names, 1):
        desc = schema.get(table, "")
        samples = get_samples(conn, table)
        cols = samples["columns"] or _cols_from_desc(desc)
        system, user = build_label_prompt(table, desc, samples, roster)
        try:
            resp = provider.chat([{"role": "system", "content": system},
                                  {"role": "user", "content": user}], tools=None)
            label = _parse_label(resp.content or "", cols)
        except Exception as e:
            label = None
            print(f"  [{i}/{len(names)}] {table}: ERROR {e}")
        if label:
            labels[table] = label
            print(f"  [{i}/{len(names)}] {table}: labelled "
                  f"({', '.join(k for k in _FIELDS if k in label)})")
        else:
            print(f"  [{i}/{len(names)}] {table}: no valid label (skipped)")

    doc = {
        "_meta": {
            "labeller_model": model,
            "db_url": db_url or getattr(conn, "engine", None) and str(conn.engine.url),
            "generated_by": "eval/label.py run_labelling",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "table_count": len(names),
            "labelled_count": len(labels),
            "frozen": True,
            "note": "Frozen offline labels for schema-RAG. Regenerate deliberately; "
                    "never per-query. See index/labels.py.",
        },
        "tables": labels,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
    print(f"\nwrote {out_path}: {len(labels)}/{len(names)} tables labelled by {model}")
    return doc


def _cols_from_desc(desc: str) -> list[str]:
    """Fallback column extraction from a 'TABLE t (col type, ...)' schema string."""
    m = re.search(r"\((.*)\)", desc, flags=re.S)
    if not m:
        return []
    return [seg.strip().split()[0] for seg in m.group(1).split(",") if seg.strip()]


def main() -> None:
    ap = argparse.ArgumentParser(description="Offline table-labelling agent for schema-RAG.")
    ap.add_argument("--model", default=DEFAULT_LABELLER, help="registry model id (the labeller)")
    ap.add_argument("--out", default="labels.json", help="output path (next to glossary.json)")
    ap.add_argument("--db-url", default=None, help="override settings.db_url")
    args = ap.parse_args()
    run_labelling(model=args.model, out_path=args.out, db_url=args.db_url)


if __name__ == "__main__":
    main()
