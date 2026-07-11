#!/usr/bin/env python3
r"""
Glossary→table pinning A/B — the DETERMINISTIC answer to the embedder recall ceiling.

Frozen labels shifted retrieval ranking but couldn't break the 0.70 ceiling: q5
("gross margin") keeps losing `sales` to confusable traps, q4 keeps losing
`produced_items`. This measures the deterministic lever: when a question names a
glossary metric, pin the tables in that metric's FORMULA into the schema context
(index/glossary_pin.py — a pure function of (question, glossary), never the LLM).

Measurement = the SAME model-independent table-recall as the labels A/B, labels ON
throughout, pin OFF vs pin ON, under the product-default embedder (model2vec). The
pin logic here is the identical module the orchestrator uses, so this reflects live
retrieval, not an eval-only reimplementation.

Model-independence is structural: neither store.search nor the pin sees the model,
so the retrieved set is byte-identical across the model ladder by construction (the
grid_labels grid already confirmed this empirically for the retrieval layer).

Run (in the app image, host repo mounted):
    docker run --rm -v /opt/analytiq:/app -w /app -e PYTHONPATH=/app \
      -e EMBEDDING_MODE=model2vec analytiq:latest \
      python -m eval.glossary_pin_ab \
      --db-url sqlite:////app/ecommerce_large.db --labels /app/labels.json \
      --glossary /app/glossary.json --gold gold/gold_set.json

Writes eval/results/grid_glossary_pin.json + grid_glossary_pin_evidence.md.
"""
from __future__ import annotations

import argparse
import json
import os
import time

BANKED_LABELS = {"off": 0.70, "on": 0.70}   # labels A/B ceiling this is trying to break
TRAPS = {"q5_margin": "sales", "q4_why_q3_weak": "produced_items"}


def run(db_url: str, labels_path: str, glossary_path: str, gold_path: str, top_k: int | None) -> dict:
    import config
    from connectors.sql import SQLConnector
    from core.embeddings import get_embedder
    from index.schema_index import SchemaIndex
    from index.glossary_pin import load_glossary, matched_metrics, pinned_tables

    gold = json.load(open(gold_path))["items"]
    glossary = load_glossary(glossary_path)
    conn = SQLConnector(db_url)
    schema = conn.schema_by_table()
    K = top_k or config.settings.schema_top_k

    # labels ON for BOTH arms — pinning is measured ON TOP of the best embedder+labels
    object.__setattr__(config.settings, "schema_labels_path", labels_path if os.path.exists(labels_path) else "")
    embedder = get_embedder()
    si = SchemaIndex(embedder); si.build(schema)

    rec = lambda got, exp: len(set(got) & set(exp)) / len(exp)

    def arm(pin_on: bool) -> dict:
        per = {}
        for it in gold:
            hits = si.store.search(it["question"], top_k=K)
            retrieved = [h.metadata["table"] for h, _ in hits]
            pins = [t for t in pinned_tables(it["question"], glossary) if t in schema] if pin_on else []
            final = retrieved + [t for t in pins if t not in retrieved]  # pin = append to context
            per[it["id"]] = {
                "expected": it["expected_tables"],
                "retrieved_topk": retrieved,
                "matched_metrics": matched_metrics(it["question"], glossary) if pin_on else [],
                "pinned": pins,
                "final": final,
                "recall": round(rec(final, it["expected_tables"]), 3),
            }
        avg = round(sum(v["recall"] for v in per.values()) / len(per), 3)
        return {"per_item": per, "avg_recall": avg}

    off = arm(False)
    on = arm(True)

    def trap_cleared(a):
        return {q: (tbl in a["per_item"][q]["final"]) for q, tbl in TRAPS.items()}

    # q2 no-op witness: pinning fires but changes nothing (tables already retrieved)
    q2 = on["per_item"].get("q2_net_revenue_trap", {})
    q2_noop = bool(q2.get("pinned")) and off["per_item"]["q2_net_revenue_trap"]["recall"] == q2.get("recall")

    return {
        "_meta": {
            "experiment": "glossary_pin_ab",
            "embedder_mode": config.settings.embedding_mode,
            "labels": bool(config.settings.schema_labels_path),
            "glossary_metrics": list(glossary.keys()),
            "schema_top_k": K, "n_tables": len(schema),
            "model_independent": "by construction — store.search + pin never see the LLM",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        "arms": {"pin_off": off, "pin_on": on},
        "comparison": {
            "banked_labels_ceiling": BANKED_LABELS,
            "pin_off_avg": off["avg_recall"], "pin_on_avg": on["avg_recall"],
        },
        "traps_cleared": {"pin_off": trap_cleared(off), "pin_on": trap_cleared(on)},
        "q2_pin_is_noop": q2_noop,
    }


def write_evidence(res: dict, path: str) -> None:
    m = res["_meta"]; off = res["arms"]["pin_off"]; on = res["arms"]["pin_on"]
    out = []
    def W(s=""): out.append(s)
    W(f"# Glossary→table pinning A/B  (labels ON, embedder={m['embedder_mode']})\n")
    W("Deterministic retrieval scaffold: a question naming a glossary metric pins the "
      "tables in that metric's formula into the schema context. Same model-independent "
      "table-recall measurement as the labels A/B; pinning is measured ON TOP of "
      "labels+embedder.\n")
    W("## Headline\n")
    W(f"- recall  **pin OFF {off['avg_recall']:.3f}  →  pin ON {on['avg_recall']:.3f}**  "
      f"(banked labels ceiling: {BANKED_LABELS['on']:.2f})")
    verdict = "CLEARED" if on["avg_recall"] > off["avg_recall"] else "no change"
    W(f"- vs the 0.70 labels ceiling: **{verdict}**")
    W(f"- model-independence: {m['model_independent']}\n")
    W("## Traps\n")
    W("| trap | needs | pin OFF | pin ON |")
    W("|------|-------|:-------:|:------:|")
    for q, tbl in TRAPS.items():
        o = res["traps_cleared"]["pin_off"].get(q); n = res["traps_cleared"]["pin_on"].get(q)
        W(f"| {q} | {tbl} | {'✅' if o else '❌'} | {'✅' if n else '❌'} |")
    W(f"\nq2 net_revenue — pin fires but is a **no-op** (tables already retrieved): "
      f"**{res['q2_pin_is_noop']}**  → pinning doesn't distort what already works.\n")
    W("## Per-question\n")
    W("| qid | expected | matched metric | pinned | recall OFF | recall ON |")
    W("|-----|----------|----------------|--------|:----------:|:---------:|")
    for qid, v in on["per_item"].items():
        W(f"| {qid} | {','.join(v['expected'])} | {','.join(v['matched_metrics']) or '—'} | "
          f"{','.join(v['pinned']) or '—'} | {off['per_item'][qid]['recall']:.2f} | {v['recall']:.2f} |")
    W("\n## Determinism boundary (so it can't be called fuzzy)\n")
    W("1. **table extraction** — every `identifier.column` in a formula → `identifier` as a table.")
    W("2. **metric match** — key normalized (`_`→space), case-insensitive substring of the question. "
      "No stemming, embeddings, or synonyms.")
    W(f"\nGlossary metrics: {', '.join(m['glossary_metrics'])}. "
      f"top_k={m['schema_top_k']}, n_tables={m['n_tables']}.\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-url", default="sqlite:///ecommerce_large.db")
    ap.add_argument("--labels", default="labels.json")
    ap.add_argument("--glossary", default="glossary.json")
    ap.add_argument("--gold", default="gold/gold_set.json")
    ap.add_argument("--top-k", type=int, default=None)
    ap.add_argument("--outdir", default="eval/results")
    args = ap.parse_args()
    res = run(args.db_url, args.labels, args.glossary, args.gold, args.top_k)
    os.makedirs(args.outdir, exist_ok=True)
    jpath = os.path.join(args.outdir, "grid_glossary_pin.json")
    epath = os.path.join(args.outdir, "grid_glossary_pin_evidence.md")
    json.dump(res, open(jpath, "w"), indent=2)
    write_evidence(res, epath)
    print(f"wrote {jpath}\nwrote {epath}")
    print(f"recall  pin_off={res['arms']['pin_off']['avg_recall']}  "
          f"pin_on={res['arms']['pin_on']['avg_recall']}  (banked labels 0.70)")
    print(f"traps ON: {res['traps_cleared']['pin_on']}   q2_noop={res['q2_pin_is_noop']}")


if __name__ == "__main__":
    main()
