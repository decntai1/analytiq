"""
Eval scorer — the thesis measurement rig.

Runs the gold set through the pipeline across a grid of (model x scaffolding-level)
and scores each run, producing the accuracy-vs-scaffolding-vs-model numbers that are
the thesis's central finding.

Metrics per question:
  - table_recall : fraction of expected_tables that appeared in the retrieved context.
                   This is the direct measure of the "did it miss a table?" failure.
  - chart_ok     : produced a valid chart when one was expected (and right type if given).
  - docs_ok      : used the document arm when expected.
  - error_count  : tool errors during the run (lower = more reliable).
  - latency_s

Scaffolding levels swept (the independent variable):
  none  -> all scaffolding OFF (raw model: full schema dump, no router/glossary/validate/repair)
  rag   -> + schema retrieval
  rag+val+rep -> + chart validation + error-repair loop
  full  -> + router + glossary (everything on)

Usage:
    python -m eval.score --models qwen2.5-14b gpt-4o-mini --out results.json
    python -m eval.score --models qwen2.5-14b --levels none rag full

Requires a reachable model endpoint (Ollama/OpenAI/etc.) and a demo DB matching the
gold set. With no endpoint it still runs structure checks via a scripted stub if you
pass --stub (smoke test of the harness itself).
"""
from __future__ import annotations

import argparse
import json
import os
import time

import config
from connectors.sql import SQLConnector
from core.embeddings import get_embedder
from core.orchestrator import Orchestrator
from index.doc_index import DocIndex
from index.schema_index import SchemaIndex

# Rendered charts carry Vega-Lite mark names; the gold set speaks the NEUTRAL spec
# vocabulary. Inverse of viz/render_vegalite._MARK (+ "table" passes through as _kind).
_VL_TO_NEUTRAL = {"bar": "bar", "line": "line", "area": "area", "point": "scatter", "arc": "pie"}

# the scaffolding levels swept along the x-axis
LEVELS = {
    "none":        {"schema_rag": False, "validate_chart": False, "repair": False, "glossary": False, "router": False},
    "rag":         {"schema_rag": True,  "validate_chart": False, "repair": False, "glossary": False, "router": False},
    "rag+val+rep": {"schema_rag": True,  "validate_chart": True,  "repair": True,  "glossary": False, "router": True},
    "full":        {"schema_rag": True,  "validate_chart": True,  "repair": True,  "glossary": True,  "router": True},
}


def load_gold(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)["items"]


def build_orchestrator() -> Orchestrator:
    emb = get_embedder()
    conn = SQLConnector()
    si = SchemaIndex(emb); si.build(conn.schema_by_table())
    di = DocIndex(emb); di.ingest_dir(config.settings.docs_dir)
    return Orchestrator(conn, si, di)


def _chart_mark(spec: dict) -> str | None:
    """Extract the Vega-Lite mark type from a rendered chart spec, mirroring the
    THREE shapes viz/render_vegalite emits: tables carry _kind; pie/plain charts
    put the mark at the top level; charts with value labels are LAYERED, where the
    real mark is layer[0] (layer[1] is the 'text' label overlay). The old scorer
    only checked the top-level mark, so every value-labelled chart (single-series
    line/bar) scored a false miss."""
    if not isinstance(spec, dict):
        return None
    mark = spec.get("mark")
    if isinstance(mark, dict):
        return mark.get("type")
    if isinstance(mark, str):
        return mark
    layers = spec.get("layer")
    if isinstance(layers, list) and layers and isinstance(layers[0], dict):
        m0 = layers[0].get("mark")
        if isinstance(m0, dict):
            return m0.get("type")
        if isinstance(m0, str):
            return m0
    return spec.get("_kind")


def score_item(result: dict, gold: dict) -> dict:
    retrieved = set(result.get("tables_retrieved", []))
    expected = set(gold.get("expected_tables", []))
    recall = (len(expected & retrieved) / len(expected)) if expected else 1.0

    chart_ok = True
    if gold.get("expect_chart"):
        charts = result.get("charts", [])
        chart_ok = len(charts) > 0
        want = gold.get("expected_chart_type")
        if chart_ok and want:
            got = _chart_mark(charts[0])
            # rendered charts carry VEGA-LITE mark names; gold uses NEUTRAL spec names.
            # Map back before comparing (must mirror viz/render_vegalite._MARK).
            got = _VL_TO_NEUTRAL.get(got, got)
            chart_ok = (got == want)
    docs_ok = True
    if gold.get("expect_documents"):
        docs_ok = len(result.get("citations", [])) > 0

    return {
        "table_recall": round(recall, 3),
        "chart_ok": chart_ok,
        "docs_ok": docs_ok,
        "error_count": len(result.get("errors", [])),
    }


def run(models: list[str], levels: list[str], gold_path: str, out_path: str) -> None:
    gold = load_gold(gold_path)
    orch = build_orchestrator()
    rows = []

    for model in models:
        for level in levels:
            config.apply_scaffold(LEVELS[level])
            # orchestrator reads config.settings live; rebuild not needed
            agg = {"table_recall": [], "chart_ok": [], "docs_ok": [], "error_count": [], "latency": []}
            for item in gold:
                t0 = time.time()
                try:
                    res = orch.ask(item["question"], model_name=model)
                    sc = score_item(res, item)
                    sc["latency"] = round(time.time() - t0, 2)
                    # record the actual retrieved tables per item so the per-model
                    # retrieval pattern (the crux: is retrieval model-independent?)
                    # is inspectable, not just the aggregate recall.
                    sc["tables_retrieved"] = res.get("tables_retrieved", [])
                except Exception as e:
                    sc = {"table_recall": 0, "chart_ok": False, "docs_ok": False,
                          "error_count": 1, "latency": round(time.time() - t0, 2),
                          "tables_retrieved": [], "exc": str(e)}
                for k in agg:
                    agg[k].append(sc.get(k, 0))
                rows.append({"model": model, "level": level, "qid": item["id"], **sc})

            n = len(gold)
            summary = {
                "model": model, "level": level,
                "table_recall": round(sum(agg["table_recall"]) / n, 3),
                "chart_ok_rate": round(sum(1 for x in agg["chart_ok"] if x) / n, 3),
                "docs_ok_rate": round(sum(1 for x in agg["docs_ok"] if x) / n, 3),
                "avg_errors": round(sum(agg["error_count"]) / n, 2),
                "avg_latency_s": round(sum(agg["latency"]) / n, 2),
            }
            print(f"{model:>18} | {level:>12} | recall={summary['table_recall']:.2f} "
                  f"chart={summary['chart_ok_rate']:.2f} docs={summary['docs_ok_rate']:.2f} "
                  f"err={summary['avg_errors']:.1f} {summary['avg_latency_s']:.1f}s")
            rows.append({"_summary": True, **summary})

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)
    print(f"\nwrote {out_path}  ({len([r for r in rows if '_summary' in r])} model×level cells)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=[config.settings.default_model])
    ap.add_argument("--levels", nargs="+", default=list(LEVELS), choices=list(LEVELS))
    ap.add_argument("--gold", default="gold/gold_set.json")
    ap.add_argument("--out", default="eval_results.json")
    ap.add_argument("--stub", action="store_true",
                    help="offline smoke test: run the scripted stub model (no endpoint/key needed)")
    args = ap.parse_args()
    models = ["stub"] if args.stub else args.models
    run(models, args.levels, args.gold, args.out)


if __name__ == "__main__":
    main()
