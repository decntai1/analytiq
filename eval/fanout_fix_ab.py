#!/usr/bin/env python3
r"""
Aggregate-before-join fan-out fix A/B — the DETERMINISTIC answer to the reasoning wall.

The reasoning ladder (eval/reasoning_ladder.py) showed the join fan-out is a defect no
model scale reliably clears: on L2b (net revenue) every model in the 8B..480B ladder plus
the code-specialists sits at 0-2/10; L5b is noisier but still low for most. The failure is
always the same shape — a model JOINs a one-table to a many-table row-wise and then
aggregates a ONE-side column, double-counting it (a wrong number that still runs).

This measures the deterministic lever, exactly parallel to eval/glossary_pin_ab.py:
  - It is an OFFLINE REPLAY: every banked ladder run already stored the model's EXACT
    emitted SQL (sql_log) and was graded. We take each run's final query, apply the
    aggregate-before-join rewrite (index/agg_before_join.py — a PURE function of (SQL,
    schema relationships), never the LLM), re-execute it against the SAME ladder DB, and
    re-grade with the SAME grade_answer. So OFF vs ON is a TRUE PAIRED comparison on
    identical model outputs — zero new model calls, fully deterministic, model-independent
    BY CONSTRUCTION.
  - The relationships are derived from the schema (PKs + column names), not declared FKs.

Writes eval/results/grid_fanout_fix.json + grid_fanout_fix_evidence.md.

Run (in the app image, host repo mounted, ladder DB built into a tempdir):
    DEMO_DB=/work/ecommerce_ladder.db DEMO_DOCS=/work/eval/demo_docs \
      python -m eval.build_ladder_db            # or: python - < eval/build_ladder_db.py
    python -m eval.fanout_fix_ab --db /work/ecommerce_ladder.db
"""
from __future__ import annotations

import argparse
import collections
import json
import os

TRAPS = ["L2b_net_revenue", "L5b_return_rate_by_product"]
DEFAULT_BANKED = ["eval/results/ladder_full.json", "eval/results/ladder_specialists.json"]


def run(db_path: str, banked_paths: list[str], gold_path: str) -> dict:
    from sqlalchemy import text

    from connectors.sql import SQLConnector
    from eval.score import grade_answer
    from index.agg_before_join import rewrite

    conn = SQLConnector(f"sqlite:///{db_path}")
    rels = conn.relationships()
    cols = conn.columns_by_table()
    gold = {i["id"]: i for i in json.load(open(gold_path))["items"]}

    def execute(sql: str):
        with conn.engine.connect() as c:
            res = c.execute(text(sql))
            return [dict(r._mapping) for r in res.fetchall()]

    runs = []
    for p in banked_paths:
        if not os.path.exists(p):
            continue
        for r in json.load(open(p)):
            if r.get("qid") in TRAPS and r.get("sql_log"):
                runs.append(r)

    per = collections.defaultdict(lambda: collections.defaultdict(lambda: {"off": 0, "on": 0, "n": 0}))
    fired = collections.Counter()
    example = {}          # qid -> one (original, rewritten) fan-out example for the evidence
    residual = []         # runs still wrong after ON (honest boundary)
    for r in runs:
        qid, model = r["qid"], r["model"]
        exp = gold[qid]["expected_value"]
        sql = r["sql_log"][-1]              # the query that produced the graded rows
        try:
            off_ok = grade_answer(execute(sql), exp)
        except Exception:
            off_ok = False
        new_sql, did_fire, note = rewrite(sql, rels, cols, dialect="sqlite")
        fired[(qid, did_fire)] += 1
        try:
            on_ok = grade_answer(execute(new_sql), exp)
        except Exception:
            on_ok = False
        cell = per[model][qid]
        cell["off"] += off_ok
        cell["on"] += on_ok
        cell["n"] += 1
        if did_fire and qid not in example and " ".join(sql.split()) != " ".join(new_sql.split()):
            example[qid] = {"original": " ".join(sql.split()), "rewritten": " ".join(new_sql.split())}
        if not on_ok:
            residual.append({"model": model, "qid": qid, "fired": did_fire, "note": note})

    def rate(model, qid, arm):
        c = per[model][qid]
        return f"{c[arm]}/{c['n']}" if c["n"] else "-"

    models = sorted(per)
    summary = {q: {"off_total": sum(per[m][q]["off"] for m in models),
                   "on_total": sum(per[m][q]["on"] for m in models),
                   "n_total": sum(per[m][q]["n"] for m in models)}
               for q in TRAPS}
    regressions = [m for m in models for q in TRAPS
                   if per[m][q]["n"] and per[m][q]["on"] < per[m][q]["off"]]

    return {
        "_meta": {
            "experiment": "fanout_fix_ab",
            "method": "offline replay of banked ladder SQL, OFF vs ON, paired on identical "
                      "model outputs; deterministic; model-independent by construction",
            "db": db_path,
            "banked": [p for p in banked_paths if os.path.exists(p)],
            "relationships": [f"{r.one_table} -1:N-> {r.many_table} on {r.key}" for r in rels],
            "traps": TRAPS,
        },
        "per_model": {m: {q: {"off": rate(m, q, "off"), "on": rate(m, q, "on")}
                          for q in TRAPS if per[m][q]["n"]} for m in models},
        "summary": summary,
        "rewrite_fired": {f"{q}:{'fired' if f else 'no-op'}": n for (q, f), n in sorted(fired.items())},
        "regressions": regressions,
        "residual_after_on": residual,
        "example_rewrite": example,
    }


def write_evidence(res: dict, path: str) -> None:
    W = []
    m = res["_meta"]
    W.append("# Aggregate-before-join fan-out fix — A/B (offline replay)\n")
    W.append(m["method"] + "\n")
    W.append("Derived relationships (schema-only, no declared FKs):")
    for r in m["relationships"]:
        W.append(f"  - {r}")
    W.append("")
    W.append("## Per-model success (x/10): OFF -> ON\n")
    W.append("| model | " + " | ".join(f"{q.split('_')[0]} OFF | {q.split('_')[0]} ON" for q in res["summary"]) + " |")
    W.append("|" + "---|" * (1 + 2 * len(res["summary"])))
    for model, cells in res["per_model"].items():
        row = [model]
        for q in res["summary"]:
            c = cells.get(q, {"off": "-", "on": "-"})
            row += [c["off"], c["on"]]
        W.append("| " + " | ".join(row) + " |")
    W.append("")
    for q, s in res["summary"].items():
        W.append(f"- **{q}**: OFF {s['off_total']}/{s['n_total']}  ->  ON {s['on_total']}/{s['n_total']}")
    W.append(f"- regressions (ON worse than OFF): **{len(res['regressions'])}**  {res['regressions'] or ''}")
    W.append(f"- rewrite fired: {res['rewrite_fired']}")
    W.append("")
    if res["residual_after_on"]:
        W.append("## Residual misses after ON (honest boundary — non-fan-out model errors)")
        for r in res["residual_after_on"]:
            W.append(f"  - {r['model']} {r['qid']} fired={r['fired']} ({r['note']})")
        W.append("")
    for q, ex in res.get("example_rewrite", {}).items():
        W.append(f"## Example rewrite — {q}")
        W.append(f"- original : `{ex['original']}`")
        W.append(f"- rewritten: `{ex['rewritten']}`")
        W.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(W))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="ecommerce_ladder.db")
    ap.add_argument("--banked", nargs="+", default=DEFAULT_BANKED)
    ap.add_argument("--gold", default="gold/reasoning_ladder.json")
    ap.add_argument("--outdir", default="eval/results")
    args = ap.parse_args()

    res = run(args.db, args.banked, args.gold)
    os.makedirs(args.outdir, exist_ok=True)
    jpath = os.path.join(args.outdir, "grid_fanout_fix.json")
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2)
    write_evidence(res, os.path.join(args.outdir, "grid_fanout_fix_evidence.md"))

    for q, s in res["summary"].items():
        print(f"{q}: OFF {s['off_total']}/{s['n_total']} -> ON {s['on_total']}/{s['n_total']}")
    print("regressions:", len(res["regressions"]), "| residual misses:", len(res["residual_after_on"]))
    print("wrote", jpath)
    # acceptance: the fix must never regress a correct answer.
    if res["regressions"]:
        raise SystemExit("FAIL: aggregate-before-join regressed at least one model")


if __name__ == "__main__":
    main()
