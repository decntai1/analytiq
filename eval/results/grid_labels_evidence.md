# Phase 3 thesis gate — schema-label enrichment A/B (labels ON vs OFF)

**Question under test:** does a *frozen, offline-authored* table-label layer, embedded
into schema-RAG, break the 0.70 table-recall ceiling on the confusable-trap gold set —
**while retrieval stays independent of model size**?

**Verdict (honest):**
- **Condition B — model-independence: HELD.** Retrieval is byte-identical across model
  sizes in both arms. Nothing re-coupled. (This is the gate's hard stop condition; it did
  **not** trigger.)
- **Condition A — recall improves past 0.70: NOT MET.** Frozen labels move the right tables
  in the right direction and recover one trap on a retrieval-tuned embedder, but the two
  hardest traps persist; aggregate recall stays 0.70.

This is a genuine (nuanced-negative) result, not a shipped win. It is recorded here in full.

---

## Method (Guardrail §4.2 — clean by construction)

- **Labels are frozen.** `labels.json` was written once, offline, by a single fixed model
  (`gpt-oss-20b`, recorded in the file's `_meta`) via `python -m eval.label`. The labeller
  was **blind to the gold questions** — it saw only each table's schema + sample rows + the
  roster of sibling tables, and emitted `{summary, grain, distinct_from, key_columns}`.
  No label was tuned to a gold outcome (that would be training on the test set).
- **Enrichment is retrieval-only.** `index/labels.py` appends the label to the *embedded*
  string only; `metadata["schema"]` (what the LLM prompt sees) stays the factual connector
  description. So labels can change *which* tables are retrieved, never *what the model is
  told about them*.
- **A/B toggle** is a single env var: `SCHEMA_LABELS_PATH` set (ON) / unset (OFF). Off ⇒
  `SchemaIndex.build()` is byte-identical to today (verified).
- **Retrieval is model-independent by construction:** `SchemaIndex.relevant_tables(question)`
  never receives the model — the retrieved set is a pure function of (question, embedder,
  schema texts, top-K). Condition B therefore *cannot* break from a labels change; the
  empirical grid below confirms it did not.

Demo DB: `ecommerce_large.db` (3 gold tables + 24 distractors, several deliberately
confusable: `refunds`~`returns`, `manufacturing`~`produced_items`, `sales_forecast`/
`revenue_targets`~`sales`). `SCHEMA_TOP_K=6`, `EMBEDDING_MODE=model2vec`.

---

## Result 1 — Empirical grid (end-to-end pipeline, `full` level)

Models: `ministral-8b` (8B), `gpt-oss-20b` (20B). Embedder: potion-base-8M (product default).

| arm | ministral-8b recall | gpt-oss-20b recall | tables_retrieved identical across models? |
|-----|--------------------:|-------------------:|-------------------------------------------|
| **OFF** | 0.70 | 0.70 | ✅ byte-identical |
| **ON**  | 0.70 | 0.70 | ✅ byte-identical |

→ **Condition B holds.** Retrieval did not re-couple to model size.
→ Aggregate recall unchanged. ON *does* change per-item ordering/membership vs OFF (labels
   are active end-to-end) — it just doesn't cross the top-6 threshold on the two trap items.

Per-item (model-independent), potion-base-8M:

| qid | expected | OFF recall | ON recall | note |
|-----|----------|-----------:|----------:|------|
| q1_monthly_revenue | sales | 1.0 | 1.0 | easy |
| q2_net_revenue_trap | sales, returns | 1.0 | 1.0 | both retrieved |
| q3_top_products | sales | 1.0 | 1.0 | easy |
| q4_why_q3_weak | sales, produced_items | 0.5 | 0.5 | **misses `produced_items`** (→ `manufacturing`/`inventory`) |
| q5_margin | sales | 0.0 | 0.0 | **misses `sales`** (→ `revenue_targets`/`sales_forecast`) |

---

## Result 2 — Deterministic embedder matrix (retrieval only, no LLM)

Retrieval computed directly from `store.search` (deterministic; model-independent), OFF vs ON,
across two torch-free static embedders:

| embedder | OFF avg | ON avg | what labels did |
|----------|--------:|-------:|-----------------|
| potion-base-8M (default) | **0.700** | **0.700** | q5 `sales` rank 15→11 (score 0.061→0.137) — right direction, short of top-6 |
| potion-retrieval-32M | **0.600** | **0.700** | **recovers q2 `returns`** (0.50→1.00); q4/q5 still miss |

Neither embedder + labels clears the two hard traps. The 0.70 line is dominated by the
embedder, consistent with the banked hypothesis ("the ceiling is an EMBEDDER property") —
but even the retrieval-tuned 32M model does not resolve q4/q5.

---

## Why q4 and q5 resist frozen labels

- **q5 "gross margin by quarter" → needs `sales`.** `sales` is the only table with both
  `revenue` and `cost`. But the query vocabulary ("gross margin", "quarter") lexically
  matches the traps: `revenue_targets` literally has a `quarter` column and "revenue target"
  text. Static (bag-of-token) embeddings can't bridge "margin" → "revenue − cost" without
  the word *margin* appearing — and putting *margin* in the `sales` label **because we know
  q5 asks it** would be gold-tuning. The blind labeller wrote "profitability"; it helped
  (rank 15→11) but not enough.
- **q4 "why were Q3 sales weak?" → needs `produced_items`.** This is a *reasoning-retrieval*
  case: the causal link (weak sales ← production shortfall) is in the document, not the query
  tokens. `produced_items` sits at rank ~21; no honest label bridges that lexical gap.

---

## Recommended next levers (do not re-couple to the model)

1. **Stronger embeddings for retrieval** — OpenAI `text-embedding-3-*` (already wired via
   `EMBEDDING_MODE=openai`) or a larger local model. Labels + a contextual embedder is the
   untested combination most likely to move q5.
2. **Hybrid lexical+semantic retrieval** (BM25 ∪ vector) — directly attacks the
   vocabulary-mismatch traps that static embeddings miss.
3. **Query expansion** at retrieval time ("gross margin" → "revenue cost profit") — but this
   is a *retrieval* transform, kept off the LLM/answer path to preserve the thesis separation.

All three keep retrieval model-independent (upstream of generation), so Condition B stays safe.

---

## Reproduce

```
# 1. build demo DB (in a snapshot of the app image, host repo mounted at /work)
docker run --rm -i -v /opt/analytiq:/work -w /work \
  -e DEMO_DB=/work/ecommerce_large.db -e DEMO_DOCS=/work/eval/demo_docs \
  <app-image> python - < eval/build_demo_db.py

# 2. author frozen labels (blind to gold) — ONE fixed model, recorded in _meta
docker run --rm -v /opt/analytiq:/work -w /work -e OLLAMA_API_KEY=... \
  <app-image> python -m eval.label --model gpt-oss-20b \
  --out /work/labels.json --db-url sqlite:////work/ecommerce_large.db

# 3. A/B grid (OFF then ON via SCHEMA_LABELS_PATH)
COMMON="-e EMBEDDING_MODE=model2vec -e DB_URL=sqlite:////work/ecommerce_large.db \
        -e DOCS_DIR=/work/eval/demo_docs -e OLLAMA_API_KEY=..."
docker run --rm -i -v /opt/analytiq:/work -w /work $COMMON <app-image> \
  python -m eval.score --models ministral-8b gpt-oss-20b --levels full \
  --gold gold/gold_set.json --out eval/results/grid_labels_OFF.json
docker run --rm -i -v /opt/analytiq:/work -w /work $COMMON \
  -e SCHEMA_LABELS_PATH=/work/labels.json <app-image> \
  python -m eval.score --models ministral-8b gpt-oss-20b --levels full \
  --gold gold/gold_set.json --out eval/results/grid_labels_ON.json
```
