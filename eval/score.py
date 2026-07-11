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


# --------------------------------------------------------------------------
# ANSWER VERIFICATION (the reasoning-bottleneck metric).
#
# "Executed without error" != "correct". On hard SQL a model can write a query
# that RUNS but computes the WRONG number (join fan-out double-count, wrong window
# partition, off-by-one growth). So we grade the executed query's RESULT (the last
# run_sql's rows, surfaced as result["result_rows"]) against the gold item's
# computed `expected_value`, with a float tolerance.
#
# The model writes its OWN SQL, so column NAMES and ORDER are unpredictable. We do
# NOT parse column names — we extract positionally per row: the first text cell is
# the LABEL, the first numeric cell is the VALUE (and the 2nd text cell is a second
# label for grouped-label answers). This is heuristic; it is validated offline
# against every ladder item's reference output before any model runs (see
# eval/validate_grader.py). Grading is additive and defensive: any structural
# surprise -> answer_correct=False, never an exception that aborts the run.
#
# expected_value kinds:
#   scalar     {"kind":"scalar","value":N,"rtol":..,"atol":..}
#   map        {"kind":"map","pairs":{label:N,..}}          unordered label->number
#   ordered    {"kind":"ordered","rows":[[label,N|null],..]} ordered label->number
#   label_map  {"kind":"label_map","pairs":{group:text,..}}  group->text (exact)
#   label_set  {"kind":"label_set","labels":[text,..]}       set of labels (exact)
# --------------------------------------------------------------------------

def _is_num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _cells(row):
    if isinstance(row, dict):
        return list(row.values())
    if isinstance(row, (list, tuple)):
        return list(row)
    return [row]


def _first_str(cells):
    for c in cells:
        if isinstance(c, str):
            return c
    return None


def _strs(cells):
    return [c for c in cells if isinstance(c, str)]


def _match(got, exp, rtol: float, atol: float, scale_tol: bool = False) -> bool:
    """One value vs one expected, with float tolerance. scale_tol also accepts the model's
    value scaled by x100 or /100 — for percentage questions where "fraction" (0.15) vs
    "percent" (15) is a legitimate reading of an ambiguous prompt, NOT a reasoning error."""
    if exp is None:
        return got is None
    if got is None or not _is_num(got):
        return False
    tol = max(rtol * abs(exp), atol)
    cands = [got, got * 100.0, got / 100.0] if scale_tol else [got]
    return any(abs(c - exp) <= tol for c in cands)


def _num_col_indices(rowlists) -> list:
    """Positions of columns that hold a number in at least one row. Models routinely emit
    intermediate columns (e.g. revenue, total_returns) BEFORE the answer column, so we must
    try EVERY numeric column, not just the first — otherwise a correct answer sitting in a
    later column scores a false miss (the L5a `(month, revenue, growth)` bug)."""
    width = max((len(r) for r in rowlists), default=0)
    return [c for c in range(width) if any(_is_num(r[c]) for r in rowlists if c < len(r))]


def grade_answer(rows: list, expected: dict) -> bool:
    """Grade executed result rows against a gold expected_value. Returns True/False.

    A model writes its OWN SQL, so we can't rely on column names/order. We extract
    positionally and, for the numeric answer, accept a match in ANY numeric column the
    model produced — the answer is "present" if some column equals the expected sequence.
    A full-sequence coincidental match across an unrelated column is vanishingly unlikely,
    so this stays strict on genuine errors (validated in eval/validate_grader.py) while no
    longer penalising extra diagnostic columns."""
    try:
        kind = expected.get("kind")
        rtol = expected.get("rtol", 0.005)
        atol = expected.get("atol", 0.01)
        scale = bool(expected.get("scale_tol"))
        rls = [_cells(r) for r in rows]

        if kind == "scalar":
            if not rls:
                return False
            return any(_match(c, expected["value"], rtol, atol, scale)
                       for c in rls[0] if _is_num(c))

        if kind == "map":
            exp = expected["pairs"]
            labels = [_first_str(r) for r in rls]
            if any(l is None for l in labels) or set(labels) != set(exp):
                return False
            for c in _num_col_indices(rls):
                got = {labels[i]: (rls[i][c] if c < len(rls[i]) else None)
                       for i in range(len(rls))}
                if all(_match(got[k], exp[k], rtol, atol, scale) for k in exp):
                    return True
            return False

        if kind == "ordered":
            # Compare the ORDERED value sequence, trying each numeric column. Length must
            # match: a model that drops the first-month null (L5a) or emits per-month
            # instead of cumulative (L4b) yields a different sequence and fails — exactly
            # the reasoning error we want to catch. None must match None (L5a first month).
            exp_vals = [v for _, v in expected["rows"]]
            if len(rls) != len(exp_vals):
                return False
            for c in _num_col_indices(rls):
                vals = [(rls[i][c] if c < len(rls[i]) else None) for i in range(len(rls))]
                if all(_match(g, e, rtol, atol, scale) for g, e in zip(vals, exp_vals)):
                    return True
            return False

        if kind == "label_map":
            got = {}
            for r in rls:
                labels = _strs(r)
                if len(labels) < 2:
                    return False
                got[labels[0]] = labels[1]
            return got == expected["pairs"]

        if kind == "label_set":
            got = set()
            for r in rls:
                labels = _strs(r)
                if not labels:
                    return False
                got.add(labels[0])
            return got == set(expected["labels"])

        return False
    except Exception:
        return False


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

    out = {
        "table_recall": round(recall, 3),
        "chart_ok": chart_ok,
        "docs_ok": docs_ok,
        "error_count": len(result.get("errors", [])),
    }
    # ADDITIVE: only when the gold item carries a computed ground-truth answer.
    # answer_correct is None (= "not graded") for items without expected_value, so
    # the existing recall/chart-only gold set is unaffected.
    exp_val = gold.get("expected_value")
    out["answer_correct"] = grade_answer(result.get("result_rows", []), exp_val) if exp_val else None
    return out


# --------------------------------------------------------------------------
# EVIDENCE LOG — human-readable, provenance-grade record of EVERY run for the
# thesis. Built ENTIRELY from the raw stored outputs (sql_log + result_rows the
# run persisted) — never reconstructed or paraphrased. Grouped by question, then
# model, so the reader sees "here is net-revenue, here's what each model wrote,
# here's who fan-out'd". Written by default on every run() (make evidence the habit).
# --------------------------------------------------------------------------

def _last_num(cells):
    v = None
    for c in cells:
        if _is_num(c):
            v = c
    return v


def _fmt_result(rr, limit=13) -> str:
    if not rr:
        return "(no rows)"
    parts = []
    for r in rr[:limit]:
        cells = _cells(r)
        parts.append("(" + ", ".join(
            (f"{c:.2f}" if isinstance(c, float) else str(c)) for c in cells) + ")")
    more = f" …(+{len(rr) - limit} more rows)" if len(rr) > limit else ""
    return "; ".join(parts) + more


def _fmt_expected(ev) -> str:
    if not ev:
        return "(none)"
    k = ev.get("kind")
    if k == "scalar":
        return f"{ev['value']:.2f}" if isinstance(ev["value"], float) else str(ev["value"])
    if k == "map":
        return ", ".join(f"{a}={b}" for a, b in ev["pairs"].items())
    if k == "ordered":
        return ", ".join(f"{a}:{b}" for a, b in ev["rows"])
    if k == "label_map":
        return ", ".join(f"{a}->{b}" for a, b in ev["pairs"].items())
    if k == "label_set":
        return "{" + ", ".join(ev["labels"]) + "}"
    return str(ev)


def _why_fail(qid: str, sql_log, rr, ev) -> str:
    """One-line, AUTO-DERIVED note on why a run failed — every number cited is read
    from the run's OWN stored SQL + result (provenance-preserving, not invented)."""
    sql = " ".join((sql_log[-1] if sql_log else "").split())
    low = sql.lower()
    n = len(rr)
    fanout = ("returns" in low and "sale_id" in low and "join" in low and "sales" in low)
    if qid.startswith("L2b"):
        got = _last_num(_cells(rr[0])) if rr else None
        exp = ev.get("value")
        if got is None:
            return "no scalar result produced"
        if fanout:
            return (f"fan-out double-count: joined sales↔returns ON sale_id, net {got:,.0f} "
                    f"vs true {exp:,.0f} (Δ{got - exp:+,.0f} = duplicated multi-return sales' revenue)")
        return f"answer mismatch: net {got:,.0f} vs true {exp:,.0f}"
    if qid.startswith("L5b"):
        if n and n < 12:
            return f"INNER JOIN dropped zero-return products: {n} rows vs 12 (LEFT JOIN needed)"
        if fanout:
            return "fan-out double-count: sales↔returns joined ON sale_id inflates the revenue denominator"
        return f"return-fraction values wrong ({n} rows)"
    if qid.startswith("L5a"):
        return (f"wrong row count {n} vs 12 (mishandled first-month null / grouping)"
                if n != 12 else "growth values wrong (LAG / rate / null handling)")
    if qid.startswith("L4b"):
        return (f"wrong row count {n} vs 12" if n != 12
                else "not a running cumulative sequence (per-month totals or mis-ordered window)")
    if qid.startswith("L4a"):
        return "wrong product per quarter (global rank vs per-quarter PARTITION)"
    if qid.startswith("L3a"):
        return f"wrong product set ({n} rows): AVG-over-rows vs AVG-over-per-product-sums"
    if qid.startswith("L2a"):
        return "wrong per-channel totals (join key / grouping)"
    return f"answer mismatch ({n} rows)"


def write_evidence(rows: list, path: str, meta: dict) -> None:
    items = [r for r in rows if "qid" in r]
    if not items:
        return
    qids = sorted({r["qid"] for r in items}, key=lambda q: (int(q[1]), q))
    models = list(dict.fromkeys(r["model"] for r in items))
    lines = []
    W = lines.append
    W("# Reasoning-ladder EVIDENCE LOG")
    W("")
    W(f"- scaffold level(s): `{meta.get('levels')}`  · pinned tables: "
      f"`{meta.get('pin_tables')}`  · repeats: `{meta.get('repeats')}`  · embedding: "
      f"`{meta.get('embedding')}`  · DB: `{meta.get('db')}`")
    W("- Every entry below is the model's **actual** stored SQL and the **actual** rows it "
      "returned (from `sql_log` / `result_rows`). Nothing is reconstructed or paraphrased.")
    W("- `WHY` notes on failures are auto-derived from the run's own SQL + result numbers.")
    W("- Repeats with an identical query+verdict are grouped, listing their repeat numbers, "
      "so per-run provenance is preserved while the non-determinism is visible.")
    W("")
    # ---- headline pass-rate table ----
    W("## Pass-rate summary (answer_correct)")
    W("")
    W("| question | level | " + " | ".join(models) + " |")
    W("|" + "---|" * (len(models) + 2))
    for q in qids:
        cells = []
        for m in models:
            runs = [r for r in items if r["qid"] == q and r["model"] == m
                    and r.get("answer_correct") is not None]
            p = sum(1 for r in runs if r["answer_correct"])
            cells.append(f"{p}/{len(runs)}")
        W(f"| {q} | L{q[1]} | " + " | ".join(cells) + " |")
    W("")
    # ---- per-question, per-model detail ----
    W("## Full evidence — grouped by question, then model")
    for q in qids:
        sample = next(r for r in items if r["qid"] == q)
        W("")
        W(f"### {q}  (Level {q[1]})")
        W(f"**Question:** {sample['question']}")
        W(f"**Expected (ground truth):** {_fmt_expected(sample.get('expected_value'))}")
        for m in models:
            runs = sorted([r for r in items if r["qid"] == q and r["model"] == m],
                          key=lambda r: r.get("repeat", 0))
            if not runs:
                continue
            passes = sum(1 for r in runs if r.get("answer_correct"))
            W("")
            W(f"#### {m} — {passes}/{len(runs)} pass")
            # group identical (last-SQL, verdict) across repeats
            groups = {}
            for r in runs:
                sql = " ".join((r.get("sql_log") or [""])[-1].split()) or "(no SQL)"
                key = (sql, bool(r.get("answer_correct")), r.get("error_count", 0))
                groups.setdefault(key, []).append(r)
            for (sql, ok, errc), grp in groups.items():
                reps = ",".join(str(g.get("repeat")) for g in grp)
                verdict = "PASS" if ok else "FAIL"
                rr = grp[0].get("result_rows") or []
                W("")
                W(f"- **{verdict}** · repeats [{reps}] ({len(grp)}/{len(runs)})"
                  + (f" · tool-errors={errc}" if errc else ""))
                W(f"  - SQL: `{sql}`")
                W(f"  - Result: {_fmt_result(rr)}")
                if not ok:
                    W(f"  - WHY: {_why_fail(q, grp[0].get('sql_log') or [], rr, sample.get('expected_value'))}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote evidence log {path}  ({len(items)} runs, {len(qids)} questions x {len(models)} models)")


def run(models: list[str], levels: list[str], gold_path: str, out_path: str,
        pin_tables: bool = False, repeats: int = 1, evidence_path: str | None = None) -> None:
    gold = load_gold(gold_path)
    orch = build_orchestrator()
    rows = []

    for model in models:
        for level in levels:
            config.apply_scaffold(LEVELS[level])
            # orchestrator reads config.settings live; rebuild not needed
            agg = {"table_recall": [], "chart_ok": [], "docs_ok": [], "error_count": [],
                   "latency": [], "answer_correct": []}
            for rep in range(repeats):
                for item in gold:
                    t0 = time.time()
                    try:
                        # pin_tables: hand every model the gold item's expected_tables
                        # (bypasses schema-RAG) so retrieval is CONSTANT and any
                        # answer_correct difference is PURELY reasoning, not a retrieval miss.
                        pinned = item.get("expected_tables") if pin_tables else None
                        res = orch.ask(item["question"], model_name=model, tables=pinned)
                        sc = score_item(res, item)
                        sc["latency"] = round(time.time() - t0, 2)
                        # record the actual retrieved tables per item so the per-model
                        # retrieval pattern (the crux: is retrieval model-independent?)
                        # is inspectable, not just the aggregate recall.
                        sc["tables_retrieved"] = res.get("tables_retrieved", [])
                        # persist the RAW executed output (the model's EXACT SQL + the rows
                        # it produced) so every result is thesis-citable EVIDENCE, and so
                        # grading can be re-run OFFLINE if grade_answer is later refined —
                        # without re-invoking the (non-deterministic) models.
                        sc["result_rows"] = res.get("result_rows", [])
                        sc["sql_log"] = res.get("sql_log", [])
                    except Exception as e:
                        sc = {"table_recall": 0, "chart_ok": False, "docs_ok": False,
                              "error_count": 1, "latency": round(time.time() - t0, 2),
                              "answer_correct": None, "tables_retrieved": [],
                              "result_rows": [], "sql_log": [], "exc": str(e)}
                    for k in agg:
                        agg[k].append(sc.get(k))
                    # store question + expected on every row so the JSON is self-contained
                    # evidence (no join back to the gold file needed to read a run).
                    rows.append({"model": model, "level": level, "qid": item["id"],
                                 "repeat": rep + 1, "question": item["question"],
                                 "expected_value": item.get("expected_value"), **sc})

            n = len(agg["table_recall"])   # gold items x repeats
            # answer_correct rate is over GRADED items only (expected_value present)
            graded = [x for x in agg["answer_correct"] if x is not None]
            ans_rate = round(sum(1 for x in graded if x) / len(graded), 3) if graded else None
            summary = {
                "model": model, "level": level,
                "table_recall": round(sum(agg["table_recall"]) / n, 3),
                "chart_ok_rate": round(sum(1 for x in agg["chart_ok"] if x) / n, 3),
                "docs_ok_rate": round(sum(1 for x in agg["docs_ok"] if x) / n, 3),
                "answer_correct_rate": ans_rate,
                "answer_graded_n": len(graded),
                "avg_errors": round(sum(agg["error_count"]) / n, 2),
                "avg_latency_s": round(sum(agg["latency"]) / n, 2),
            }
            ans_str = f"{ans_rate:.2f}" if ans_rate is not None else "  NA"
            print(f"{model:>18} | {level:>12} | recall={summary['table_recall']:.2f} "
                  f"ans={ans_str} chart={summary['chart_ok_rate']:.2f} "
                  f"docs={summary['docs_ok_rate']:.2f} err={summary['avg_errors']:.1f} "
                  f"{summary['avg_latency_s']:.1f}s")
            rows.append({"_summary": True, **summary})

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)
    print(f"\nwrote {out_path}  ({len([r for r in rows if '_summary' in r])} model×level cells)")

    # DEFAULT: always emit the human-readable evidence log so every run is
    # thesis-citable. Derive the path from out_path unless one was given.
    ev_path = evidence_path or (out_path.rsplit(".", 1)[0] + "_evidence.md")
    write_evidence(rows, ev_path, {
        "levels": levels, "pin_tables": pin_tables, "repeats": repeats,
        "embedding": os.getenv("EMBEDDING_MODE"), "db": config.settings.db_url,
    })


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=[config.settings.default_model])
    ap.add_argument("--levels", nargs="+", default=list(LEVELS), choices=list(LEVELS))
    ap.add_argument("--gold", default="gold/gold_set.json")
    ap.add_argument("--out", default="eval_results.json")
    ap.add_argument("--stub", action="store_true",
                    help="offline smoke test: run the scripted stub model (no endpoint/key needed)")
    ap.add_argument("--pin-tables", action="store_true",
                    help="hand each model the gold item's expected_tables (bypass schema-RAG) so "
                         "retrieval is CONSTANT — for the reasoning-bottleneck ladder")
    ap.add_argument("--repeats", type=int, default=1,
                    help="run the whole gold set N times per model×level (small models are "
                         "non-deterministic; report a pass RATE not a single shot)")
    ap.add_argument("--evidence", metavar="PATH", default=None,
                    help="human-readable evidence log path (default: <out>_evidence.md). "
                         "Always written — every run is thesis-citable evidence.")
    args = ap.parse_args()
    models = ["stub"] if args.stub else args.models
    run(models, args.levels, args.gold, args.out, pin_tables=args.pin_tables,
        repeats=args.repeats, evidence_path=args.evidence)


if __name__ == "__main__":
    main()
