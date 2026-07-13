# Results — Retrieval

_Draft, results chapter. Grounded in `eval/results/grid_stageA.json`, `grid_stageB.json`,
`grid_labels_*.json`, and `grid_glossary_pin.json`. Numbers reproduced by the commands in
§Reproduce. Prose to be tightened for the final chapter; the measurements are final._

## Overview

The central claim of this thesis is that **deterministic scaffolding can substitute for
model capability, measurably**. This section tests that claim at the *retrieval* layer —
the point in the pipeline where a natural-language question is turned into the set of
tables the answer will be computed over. Retrieval is where the "silent miss" failure mode
lives: if the schema-RAG stage drops a table the answer needs, every downstream stage
(SQL, chart, narration) is confidently wrong over partial data, and nothing in the trace
flags it. The metric that isolates this is **table-recall**: of the tables a gold answer
requires, what fraction survived into the top-K schema context.

The section establishes three linked results:

1. **Retrieval is model-independent, and the scaffolding gradient rescues the weak model.**
   Table-recall at each scaffold level is *byte-identical* across a ~60× span of model
   sizes; the accuracy that scaffolding buys shows up in the weak model's *generation*
   metrics, not its retrieval.
2. **A frozen semantic label layer moves retrieval in the right direction but cannot break
   the recall ceiling** — a genuine, nuanced-negative result.
3. **A deterministic glossary→table pinning rule breaks the ceiling exactly where labels
   could not** — the sharpest form of the thesis claim, applied to retrieval itself.

Together, results 2 and 3 form a matched pair: a semantic scaffold (labels) that shifts
ranking without breaking the ceiling, and a deterministic scaffold (pinning) that breaks it
by construction — scaffolding substituting for capability at the retrieval layer.

## Experimental setup

**Benchmark database.** Retrieval difficulty is only measurable when top-K must *choose*.
An earlier iteration measured recall over a database containing only the three gold tables;
with `SCHEMA_TOP_K = 6`, top-6-of-3 returns all three trivially and recall saturates at
1.0, discriminating nothing. The benchmark database (`ecommerce_large`, built by
`eval/build_demo_db.py`) therefore holds the **3 gold tables plus 24 distractors**, several
deliberately *confusable* with the gold tables so that lexical overlap alone cannot resolve
them:

| gold table | confusable distractors (designated traps in `build_demo_db.py`) |
|------------|------------------------|
| `sales` | `sales_forecast` (`forecast_revenue`), `revenue_targets` (`quarter`, `target`), `product_catalog` (`product`) — revenue/quarter/product-name overlap, but none carries `cost` |
| `returns` | `refunds` (`amount`) |
| `produced_items` | `manufacturing` (`output_units`) |

**Gold set.** Five questions, each with a verified `expected_tables` set that drives the
table-recall metric. They span a difficulty gradient from single-table lookup to
document-grounded causal reasoning:

| id | question | expected tables | difficulty |
|----|----------|-----------------|-----------|
| q1 | Show total revenue per month for 2024 as a line chart. | `sales` | single-table baseline |
| q2 | What was net revenue in Q4? | `sales`, `returns` | glossary-metric trap (net = gross − returns) |
| q3 | Top 10 products by revenue. | `sales` | single-table baseline |
| q4 | Why were Q3 sales weak? | `sales`, `produced_items` | causal / document-grounded |
| q5 | What was our gross margin by quarter? | `sales` | vocabulary trap (margin ≠ any table name) |

**Model ladder.** Four tool-capable models spanning roughly a 60× parameter range, all
served identically over the same OpenAI-compatible endpoint: `ministral-8b` (8B),
`gpt-oss-20b` (20B), `gpt-oss:120b` (120B, keyed `ollama-cloud`), and `qwen3-coder:480b`
(480B, keyed `qwen3-coder`).

**Scaffold levels.** The pipeline is swept across four cumulative scaffolding
configurations: `none` (no schema-RAG — the full schema is dumped into context),
`rag` (semantic schema retrieval, top-6), `rag+val+rep` (adds SQL validation and
error-repair), and `full` (adds intent routing and document-RAG).

**Embedder.** Unless noted, schema retrieval uses `potion-base-8M` (a `model2vec` static
embedder, torch-free, the product default), with `SCHEMA_TOP_K = 6`.

All grids reported here fix the deterministic glossary-pin scaffold OFF except in §Result 3,
so banked results do not silently inherit the production flag.

## Result 1 — Retrieval is model-independent; scaffolding rescues the weak model

Table-recall, averaged over the five gold questions, at each (model × scaffold-level) cell:

| model | none | rag | rag+val+rep | full |
|-------|:----:|:---:|:-----------:|:----:|
| ministral-8b (8B) | 1.00 | 0.70 | 0.70 | 0.70 |
| gpt-oss-20b (20B) | 1.00 | 0.70 | 0.70 | 0.70 |
| gpt-oss:120b (120B) | 1.00 | 0.70 | 0.70 | 0.70 |
| qwen3-coder:480b (480B) | 1.00 | 0.70 | 0.70 | 0.70 |

The columns are identical down to the model. This is not a coincidence of averaging: across
all 20 (scaffold-level × question) cells, the **exact set of retrieved tables was
byte-identical across all four models — zero cross-model mismatches**. Table-recall is a
pure function of the scaffold level and the embedder; it does not depend on the language
model at all. The crux of the thesis — that the deterministic scaffold, not the model, owns
retrieval — holds across a ~60× capability gap, and the router-on levels (`full`) did not
re-introduce any model dependence.

Two readings of the recall column matter:

- The `none = 1.00` figure is **degenerate, not competence**. With schema-RAG off, the
  entire schema is dumped into context, so every table — gold and distractor alike — is
  trivially "present." Recall of 1.0 here means the model was handed all 27 tables and
  asked to cope, not that retrieval succeeded. It is reported for completeness; it is not a
  measure of retrieval quality.
- The number that measures retrieval *quality* is the `0.70` shared by `rag`,
  `rag+val+rep`, and `full` — semantic top-6 over the confusable set. That 0.70 is a
  ceiling set by the **embedder** (`potion-base-8M`), not the LLM, which is precisely why
  it does not move with model size. Results 2 and 3 attack that ceiling directly.

If retrieval is model-independent, where does model capability show up — and where does the
scaffolding *substitute* for it? In the generation-layer metrics, and specifically in the
weak model. Selected metrics at `none` vs. `rag`:

| model | metric | none | rag |
|-------|--------|:----:|:---:|
| ministral-8b (8B) | errors / question | 3.40 | 0.60 |
| ministral-8b (8B) | chart validity | 0.60 | 0.80 |
| gpt-oss-20b … 480b | errors / question | ~0.0 | ~0.0 |

The 8B model, handed the raw 27-table dump at `none`, drowns — 3.4 errors per question. The
single act of turning on schema-RAG (narrowing 27 tables to a focused top-6) collapses that
to 0.6 and lifts its chart validity from 0.60 to 0.80. The 20B, 120B, and 480B models sit at
roughly zero errors at *every* level: they are capable enough to handle the undifferentiated
dump unaided, so the scaffold has little left to rescue. This is the thesis gradient in its
cleanest form — **the scaffold's value is largest exactly where model capability is
smallest**, and it shrinks monotonically as capability grows.

## Result 2 — Frozen semantic labels: right direction, ceiling holds (nuanced-negative)

The 0.70 ceiling is an embedder property, so the first lever tried was a richer *embedded
representation* of each table — a **frozen, offline-authored label layer**. Each table was
described once, in advance, by a single fixed model (`gpt-oss-20b`, recorded in the label
file's metadata) that saw only the table's schema, sample rows, and the roster of sibling
tables — and was **blind to the gold questions**. The label (`{summary, grain, distinct_from,
key_columns}`) is appended to the *embedded* string only; the factual description the LLM's
prompt sees is unchanged. Labels can therefore change *which* tables are retrieved, never
*what the model is told about them*, and the A/B is a single environment variable. Crucially,
no label was tuned to a gold outcome — that would be training on the test set.

The evaluation was framed as two conditions:

- **Condition B (must not break): retrieval stays model-independent.** *Held.* Retrieval was
  byte-identical across model sizes in both the OFF and ON arms; the label change re-coupled
  nothing to the model. (This is guaranteed by construction — `relevant_tables(question)`
  never receives the model — and the grid confirms it empirically.)
- **Condition A (the hoped-for win): recall improves past 0.70.** *Not met.*

Retrieval-only recall (computed directly from the vector store, model-independent), OFF vs.
ON, across two torch-free embedders:

| embedder | OFF | ON | what the labels did |
|----------|:---:|:--:|---------------------|
| potion-base-8M (default) | 0.700 | 0.700 | pushed q5 `sales` from rank 15 → 11 (score 0.061 → 0.137) — right direction, short of top-6 |
| potion-retrieval-32M | 0.600 | 0.700 | **recovered q2 `returns`** (0.50 → 1.00); q4 and q5 still miss |

Frozen labels move the right tables in the right direction, and on the retrieval-tuned 32M
embedder they recover one trap — but the two hardest traps persist and aggregate recall
stays pinned at 0.70. The two survivors are instructive about *why* a frozen semantic layer
cannot reach them:

- **q5 ("gross margin by quarter" → `sales`).** `sales` is the only table carrying both
  `revenue` and `cost`, but the query vocabulary ("gross margin", "quarter") lexically
  matches the *traps*: `revenue_targets` literally has a `quarter` column and "revenue
  target" text. A static bag-of-token embedding cannot bridge "margin" → "revenue − cost"
  unless the word *margin* appears in the label — and writing *margin* into the `sales`
  label *because we know q5 asks it* is gold-tuning. The blind labeller wrote
  "profitability"; it helped (rank 15 → 11) but did not clear top-6.
- **q4 ("why were Q3 sales weak?" → `produced_items`).** This is a *reasoning-retrieval*
  case: the causal link (weak sales ← production shortfall) lives in a document, not in the
  query tokens. `produced_items` sits near rank 21; no honest, question-blind label bridges
  that gap.

This is a real result, recorded as negative: a semantic scaffold shifts the ranking but
cannot, on its own, break a ceiling rooted in vocabulary mismatch.

## Result 3 — Deterministic glossary pinning: the ceiling breaks where labels could not

The final lever is *deterministic* rather than semantic. Analytiq maintains a metric
glossary — business definitions such as `net_revenue = SUM(sales.revenue) − COALESCE(SUM(returns.amount), 0)`
and `gross_margin = (SUM(sales.revenue) − SUM(sales.cost)) / SUM(sales.revenue)`. The
**glossary-pin scaffold** (`index/glossary_pin.py`, flag `SCAFFOLD_GLOSSARY_PIN`) applies a
single rule: if a question names a glossary metric, the tables appearing in that metric's
*formula* are pinned into the schema context, regardless of what the embedder ranked. The
rule is a pure function of `(question, glossary)`:

1. **table extraction** — every `identifier.column` in a formula contributes `identifier`
   as a table (`SUM(sales.revenue)` → `sales`);
2. **metric match** — the metric key is normalized (`_` → space) and matched
   case-insensitively as a substring of the question. No stemming, no synonyms, no
   embeddings.

Because the LLM is never in this path, retrieval remains **model-independent by
construction**, in the same sense as Results 1 and 2 — the pinning scaffold cannot re-couple
retrieval to model size. The rule is wired in `orchestrator._schema_context`: it defers to
an authoritative user table-scope when one is set, and only pins tables the connector
actually has. It is measured *on top of* the frozen-labels + `model2vec` configuration, so
the comparison is like-for-like against Result 2.

Aggregate table-recall:

**pin OFF 0.700 → pin ON 0.900** — the frozen-labels ceiling of 0.70 is **cleared**.

Per-question:

| id | expected | matched metric | tables pinned | recall OFF | recall ON |
|----|----------|----------------|---------------|:----------:|:---------:|
| q1 | `sales` | — | — | 1.00 | 1.00 |
| q2 | `sales`, `returns` | net_revenue | `sales`, `returns` | 1.00 | 1.00 |
| q3 | `sales` | — | — | 1.00 | 1.00 |
| q4 | `sales`, `produced_items` | — | — | 0.50 | 0.50 |
| q5 | `sales` | gross_margin | `sales` | **0.00** | **1.00** |

Three behaviours are worth reading off this table, because each maps to a property a
deterministic scaffold must have to be defensible:

- **It breaks the ceiling where the semantic scaffold could not (q5).** The single trap that
  frozen labels moved but could not clear — `sales` for "gross margin" — goes from 0.00 to
  1.00. The glossary formula names `sales` explicitly, so the vocabulary gap that defeated
  the embedder simply does not exist for the rule.
- **It does not distort what already works (q2).** For "net revenue", the pin fires and pins
  `sales`, `returns` — but both were *already* retrieved (recall was 1.00 OFF). The pin is a
  no-op here: it adds no wrong table and removes no right one. A scaffold that could only help
  by also harming elsewhere would not be worth shipping; this one is monotone on the gold set.
- **It respects its own boundary (q4).** "Why were Q3 sales weak?" names no glossary metric,
  so the rule does nothing, and recall stays 0.50. The pin makes no attempt to guess at the
  causal, document-grounded case it was not designed for — exactly the honest failure the
  determinism boundary predicts.

## Synthesis

Read across the three results, the retrieval layer exhibits the thesis claim twice over, at
two different points in the pipeline:

- **At generation (Result 1):** turning on schema-RAG substitutes for model capability — it
  rescues the 8B model from 3.4 errors/question to 0.6, while leaving the already-capable
  larger models roughly unchanged. Scaffolding is worth most where the model is weakest.
- **At retrieval (Results 2 + 3):** table-recall is model-independent, so no amount of model
  scale (across ~60×) moves it. A frozen *semantic* scaffold shifts the ranking but cannot
  break the 0.70 ceiling (nuanced-negative). A *deterministic* scaffold — the glossary-pin
  rule — breaks it to 0.90, clearing precisely the trap the semantic layer could not, and
  does so by construction rather than by capability.

The matched pair (Result 2 → Result 3) is the strongest single statement of the thesis in
this chapter: where a richer representation *hinted* at the answer but could not commit to
it, a small deterministic rule — a pure function of the question and a business glossary —
supplies the missing competence outright, and keeps retrieval model-independent while doing
it. That model-independence is not incidental: it is the property that lets a weaker,
on-prem, open-source model reach the same retrieval quality as a frontier model, which is
what makes the product claim downstream of the thesis viable.

## Threats to validity

- **Gold-set size.** Five questions over one demo schema. The results are consistent and
  mechanistically explained, but the aggregate figures (0.70, 0.90) are coarse — one
  question is 0.20 of recall. The claims are about *mechanism* (model-independence, the
  labels-vs-pinning contrast), which the per-question breakdowns support directly; the
  aggregates should be read as illustrative of that mechanism, not as population estimates.
- **The embedder ceiling.** The 0.70 semantic ceiling is a property of `potion-base-8M`. A
  stronger contextual embedder (OpenAI `text-embedding-3-*`, or a larger local model such as
  `bge-m3`) is the untested lever most likely to move q5 semantically; it is parked pending
  hardware (`bge-m3` does not fit the current box). The deterministic pin is reported as the
  scaffold that clears the trap *without* requiring a heavier embedder.
- **q4 remains open.** The causal, document-grounded trap is not solved by any scaffold here.
  It is a reasoning-retrieval problem (the answer's evidence is in a document, not the query
  tokens) and is left as future work; it is honestly reported as 0.50 throughout.
- **Latency is not a clean signal.** All models were served over a shared cloud endpoint;
  wall-clock times were noisy (the 20B model occasionally ran slower than the 120B on the
  same day), so latency is excluded from the substitution argument.
- **`none`-level recall is degenerate by construction** (schema dump), and is reported only
  for completeness, never as evidence of retrieval competence.

## Reproduce

```bash
# Result 1 — model-independence grid (4-model ladder × 4 scaffold levels)
docker compose exec -T app python - < eval/build_demo_db.py   # (re)build DB + docs
docker compose exec -e EMBEDDING_MODE=model2vec \
  -e DB_URL=sqlite:////app/ecommerce_large.db -e DOCS_DIR=/app/eval/demo_docs -T app \
  python -m eval.score --models ministral-8b gpt-oss-20b ollama-cloud qwen3-coder \
  --levels none rag rag+val+rep full
# banked raw: eval/results/grid_stageA.json (8B, 20B) + grid_stageB.json (120B, 480B)

# Result 2 — frozen-labels A/B (OFF then ON via SCHEMA_LABELS_PATH)
# banked raw: eval/results/grid_labels_OFF.json, grid_labels_ON.json
#   evidence: eval/results/grid_labels_evidence.md

# Result 3 — glossary-pin A/B (labels ON, model2vec)
python eval/glossary_pin_ab.py
# banked raw: eval/results/grid_glossary_pin.json
#   evidence: eval/results/grid_glossary_pin_evidence.md
```
