#!/usr/bin/env python3
"""
Embedder-vs-retrieval-recall A/B — swap the embedder, measure the ceiling.

Same measurement as the model2vec/potion labels A/B (score.py table_recall over the
gold set), but factored so ANY embedder can be dropped in via env and compared on
equal footing: labels-OFF vs labels-ON, per-question recall, plus the runtime cost
(load time, per-query embed latency, RAM/GPU footprint) we need to decide adoption.

Embedder is chosen by the SAME env the product uses — no code change, no default
touched:
    EMBEDDING_MODE=local  EMBEDDING_MODEL_LOCAL=BAAI/bge-m3   # bge-m3 (needs torch+GPU)
    EMBEDDING_MODE=model2vec                                  # potion-base-8M (torch-free)

Retrieval is model-INDEPENDENT by construction (SchemaIndex.relevant_tables never sees
the LLM), so this measures the embedder alone — exactly the variable under test.

Usage (on the GPU box, in the on-prem image that has sentence-transformers+torch):
    EMBEDDING_MODE=local EMBEDDING_MODEL_LOCAL=BAAI/bge-m3 \
      python -m eval.embedder_recall_ab --tag bgem3 \
      --db-url sqlite:////work/ecommerce_large.db --labels /work/labels.json

Writes eval/results/grid_<tag>.json + grid_<tag>_evidence.md.
"""
from __future__ import annotations

import argparse
import json
import os
import time

# Banked model2vec baseline (potion-base-8M) for the head-to-head, and the two traps
# labels could not break — the whole point of trying a stronger embedder.
BANKED_M2V = {"off": 0.70, "on": 0.70}
TRAPS = {"q4_why_q3_weak": "produced_items", "q5_margin": "sales"}


def _rss_mb() -> float:
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024, 1)  # KB -> MB
    except OSError:
        pass
    return -1.0


def _gpu_info() -> dict:
    try:
        import torch
        if torch.cuda.is_available():
            return {"cuda": True, "device": torch.cuda.get_device_name(0),
                    "max_alloc_mb": None}  # filled after embedding
    except Exception:
        pass
    return {"cuda": False, "device": "cpu"}


def _gpu_peak_mb() -> float | None:
    try:
        import torch
        if torch.cuda.is_available():
            return round(torch.cuda.max_memory_allocated() / 1024 / 1024, 1)
    except Exception:
        pass
    return None


def run(tag: str, db_url: str, labels_path: str, gold_path: str, top_k: int | None) -> dict:
    import config
    from connectors.sql import SQLConnector
    from core.embeddings import get_embedder
    from index.schema_index import SchemaIndex

    gold = json.load(open(gold_path))["items"]
    conn = SQLConnector(db_url)
    schema = conn.schema_by_table()
    K = top_k or config.settings.schema_top_k

    gpu = _gpu_info()
    rss_before = _rss_mb()

    # --- load the embedder ONCE, timed -------------------------------------
    t0 = time.time()
    embedder = get_embedder()
    load_s = round(time.time() - t0, 2)

    # sanity + warm embed of the gold questions (also the latency sample)
    questions = [it["question"] for it in gold]
    t1 = time.time()
    qvecs = embedder.embed(questions)
    embed_ms = round((time.time() - t1) * 1000 / max(len(questions), 1), 1)
    dim = len(qvecs[0]) if qvecs else 0

    rec = lambda got, exp: len(set(got) & set(exp)) / len(exp)

    def arm(label_path: str) -> dict:
        object.__setattr__(config.settings, "schema_labels_path", label_path)
        si = SchemaIndex(embedder); si.build(schema)
        per = {}
        for it in gold:
            hits = si.store.search(it["question"], top_k=K)
            tbls = [h.metadata["table"] for h, _ in hits]
            per[it["id"]] = {"expected": it["expected_tables"], "retrieved": tbls,
                             "recall": round(rec(tbls, it["expected_tables"]), 3)}
        avg = round(sum(v["recall"] for v in per.values()) / len(per), 3)
        return {"per_item": per, "avg_recall": avg}

    off = arm("")
    on = arm(labels_path) if labels_path and os.path.exists(labels_path) else None

    gpu["max_alloc_mb"] = _gpu_peak_mb()
    rss_after = _rss_mb()

    def trap_cleared(arm_res):
        if not arm_res:
            return {}
        return {q: (tbl in arm_res["per_item"][q]["retrieved"])
                for q, tbl in TRAPS.items()}

    result = {
        "_meta": {
            "tag": tag,
            "embedder_mode": config.settings.embedding_mode,
            "embedder_model": (config.settings.embedding_model_local
                               if config.settings.embedding_mode == "local"
                               else config.settings.embedding_model_model2vec),
            "embedding_dim": dim,
            "device": gpu["device"], "cuda": gpu["cuda"],
            "gold": gold_path, "schema_top_k": K, "n_tables": len(schema),
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "runtime_cost": {
                "model_load_s": load_s,
                "embed_latency_ms_per_query": embed_ms,
                "rss_mb_before": rss_before, "rss_mb_after": rss_after,
                "rss_mb_delta": round(rss_after - rss_before, 1) if rss_before > 0 else None,
                "gpu_peak_alloc_mb": gpu["max_alloc_mb"],
            },
        },
        "arms": {"off": off, **({"on": on} if on else {})},
        "comparison": {
            "banked_model2vec_potion_base_8M": BANKED_M2V,
            "this_embedder": {"off": off["avg_recall"], "on": on["avg_recall"] if on else None},
        },
        "traps_cleared": {"off": trap_cleared(off), "on": trap_cleared(on)},
    }
    return result


def write_evidence(res: dict, path: str) -> None:
    m = res["_meta"]; rc = m["runtime_cost"]
    off = res["arms"]["off"]; on = res["arms"].get("on")
    L = []
    W = L.append
    W(f"# Embedder A/B — {m['embedder_model']}  (tag: {m['tag']})\n")
    W("Same gold-set table-recall measurement as the model2vec labels A/B, with a "
      "different embedder. Retrieval is model-independent by construction, so this "
      "isolates the embedder.\n")
    W("## Headline\n")
    W(f"- **{m['embedder_model']}** ({m['embedding_dim']}-dim, on `{m['device']}`)")
    W(f"- recall OFF: **{off['avg_recall']:.3f}**"
      + (f"  ·  ON: **{on['avg_recall']:.3f}**" if on else "  ·  ON: (labels not run)"))
    W(f"- banked model2vec/potion-base-8M: OFF {BANKED_M2V['off']:.2f} · ON {BANKED_M2V['on']:.2f}")
    verdict_off = "CLEARED" if off["avg_recall"] > BANKED_M2V["off"] else "did NOT clear"
    W(f"- vs the 0.70 ceiling: **{verdict_off}** (labels-OFF)\n")
    W("## Did it clear the two traps model2vec+labels missed?\n")
    W("| trap | needs | OFF cleared? | ON cleared? |")
    W("|------|-------|--------------|-------------|")
    for q, tbl in TRAPS.items():
        o = res["traps_cleared"]["off"].get(q)
        n = res["traps_cleared"]["on"].get(q) if on else None
        W(f"| {q} | {tbl} | {'✅' if o else '❌'} | {'✅' if n else ('❌' if on else '—')} |")
    W("\n## Per-question recall\n")
    W("| qid | expected | OFF | ON |")
    W("|-----|----------|----:|---:|")
    for it_id, v in off["per_item"].items():
        onr = on["per_item"][it_id]["recall"] if on else None
        W(f"| {it_id} | {','.join(v['expected'])} | {v['recall']:.2f} | "
          f"{onr:.2f} |" if on else f"| {it_id} | {','.join(v['expected'])} | {v['recall']:.2f} | — |")
    W("\n## Runtime cost (adoption decision)\n")
    W(f"- model load: **{rc['model_load_s']} s**")
    W(f"- embed latency: **{rc['embed_latency_ms_per_query']} ms/query**")
    W(f"- process RSS: {rc['rss_mb_before']} → {rc['rss_mb_after']} MB "
      f"(Δ {rc['rss_mb_delta']} MB)")
    W(f"- GPU peak alloc: {rc['gpu_peak_alloc_mb']} MB" if rc["gpu_peak_alloc_mb"] is not None
      else "- GPU: not used (CPU run)")
    W(f"\n_The 3.7GB/no-swap VPS cannot hold this (torch ~5GB). Adoption ⇒ a box with "
      f"enough RAM/VRAM; measured footprint above._\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="embedder")
    ap.add_argument("--db-url", default="sqlite:///ecommerce_large.db")
    ap.add_argument("--labels", default="labels.json")
    ap.add_argument("--gold", default="gold/gold_set.json")
    ap.add_argument("--top-k", type=int, default=None)
    ap.add_argument("--outdir", default="eval/results")
    args = ap.parse_args()
    res = run(args.tag, args.db_url, args.labels, args.gold, args.top_k)
    os.makedirs(args.outdir, exist_ok=True)
    jpath = os.path.join(args.outdir, f"grid_{args.tag}.json")
    epath = os.path.join(args.outdir, f"grid_{args.tag}_evidence.md")
    json.dump(res, open(jpath, "w"), indent=2)
    write_evidence(res, epath)
    print(f"\nwrote {jpath}\nwrote {epath}")
    print(f"\n{m}".format(m="") if False else "")
    print(f"embedder={res['_meta']['embedder_model']} device={res['_meta']['device']}")
    print(f"recall OFF={res['arms']['off']['avg_recall']}"
          + (f"  ON={res['arms']['on']['avg_recall']}" if 'on' in res['arms'] else "")
          + f"   (banked model2vec 0.70)")
    print(f"load={res['_meta']['runtime_cost']['model_load_s']}s "
          f"embed={res['_meta']['runtime_cost']['embed_latency_ms_per_query']}ms/q "
          f"rss_delta={res['_meta']['runtime_cost']['rss_mb_delta']}MB "
          f"gpu_peak={res['_meta']['runtime_cost']['gpu_peak_alloc_mb']}MB")


if __name__ == "__main__":
    main()
