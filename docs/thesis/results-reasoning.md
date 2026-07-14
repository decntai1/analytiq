# Results — Reasoning (the SQL fan-out)

_Draft, results chapter. Grounded in `eval/results/ladder_full.json`,
`ladder_specialists.json`, and `grid_fanout_fix.json`. Numbers reproduced by the commands
in §Reproduce. Prose to be tightened for the final chapter; the measurements are final._

## Overview

The retrieval chapter established the thesis claim at the point where a question is turned
into a set of tables: deterministic scaffolding, not model scale, owns retrieval, and a
deterministic rule breaks a ceiling that capability cannot. This chapter makes the *same*
argument one stage downstream — at **reasoning**, where the right tables are already in
hand and the model must write SQL that computes the *correct number*. It has the same
shape and the same payoff: a failure that model scale and even model *specialization* do
not fix, solved outright by a small deterministic rule that is model-independent by
construction.

The failure mode here is the **join fan-out**. When a question combines a "one" table with
a "many" table — a sale has several returns — a model that JOINs them row-wise and then
aggregates a column of the *one* side double-counts it: each one-row is repeated once per
matching many-row. The query runs, returns a plausible number, and is silently wrong. It is
the reasoning-layer twin of retrieval's "silent miss": nothing in the trace flags it,
because nothing errored. The metric that isolates it is **answer-correctness**: the model's
result graded against a ground-truth value computed from the data (not merely "did the SQL
execute").

The section establishes three linked results:

1. **The wall is a specific trap, not raw complexity.** Across a 360-run ladder, models of
   every size clear single-table aggregation, multi-table joins, nested subqueries, window
   functions, and growth calculations — but collapse on the fan-out. The collapse does not
   shrink with scale.
2. **Specialization does not rescue it.** Code-specialist models — tuned precisely for
   code and SQL — fail the fan-out just as completely as the general ladder.
3. **A deterministic aggregate-before-join rule solves it outright**, taking the fan-out
   from 0–2/10 to 10/10 for *every* model, and — like glossary-pinning at retrieval — it
   does so by construction rather than by capability.

Results 2 and 3 form the same matched pair the retrieval chapter turned on: a lever that
*should* help but does not (there, semantic labels; here, model specialization), set
against a deterministic rule that supplies the missing competence outright. Here *substitute*
means the same thing it did there — the scaffold lets a weak model match a strong one on the
measured reliability metric (answer-correctness on the fan-out), not that the 8B becomes the
480B.

## Experimental setup

**Reasoning ladder.** Retrieval is held *constant* so that any difference is purely
reasoning: every model is handed the gold item's `expected_tables` directly (`--pin-tables`,
bypassing schema-RAG), and then must write its own SQL. The gold set (`gold/reasoning_ladder.json`,
built by `eval/reasoning_ladder.py`) climbs a nine-rung SQL-complexity ladder, each rung
carrying a ground-truth `expected_value` computed from the data:

| rung | id | what it demands |
|------|----|-----------------|
| L1 | L1a, L1b | single-table aggregation (baseline) |
| L2 | L2a | a legitimate many→one join (`sales`→`orders`) |
| L2 | **L2b** | **net revenue = sales − returns: the fan-out trap** |
| L3 | L3a | two-level aggregation in a subquery (AVG of per-group SUMs) |
| L4 | L4a, L4b | window functions (ROW_NUMBER per partition; running total) |
| L5 | L5a | compound: LAG growth-rate with first-month NULL |
| L5 | **L5b** | **return-rate per product: fan-out *through* a join** |

**Benchmark database.** `ecommerce_ladder.db` (`eval/build_ladder_db.py`): the three gold
tables plus 24 distractors (matching the retrieval DB's 27-table difficulty), seeded so that
**a sale can carry more than one return** (144 sales, 60 returns) — the fan-out is real in the
data, not hypothetical. `returns` reaches a product only *through* `sales` (it carries
`sale_id`, not `product`), which is what makes L5b the harder of the two traps.

**Model ladder.** Four tool-capable models spanning ~60×: `ministral-8b` (8B), `gpt-oss-20b`
(20B), `gpt-oss:120b` (120B, keyed `ollama-cloud`), `qwen3-coder:480b` (480B).

**Specialists.** Three code-specialist models, reachable only from the harness (not offered
in the product picker): `devstral-small-24b`, `devstral-123b` (Mistral code models), and
`qwen3-coder-next`.

**Repeats.** Small models are non-deterministic even at temperature 0, so every cell is run
**10 times** and reported as a success count out of 10 — a pass *rate* with its run-to-run
spread visible, not a single shot. The full ladder is 4 models × 9 questions × 10 =
**360 runs**; the specialist probe adds 3 × {L2b, L5b} × 10 = 60.

**Grading.** `eval/score.py`'s `grade_answer` extracts the answer positionally (the model
names its own columns) and compares to `expected_value` with type-appropriate tolerance
(0.5% relative on revenue totals; a fraction-vs-percent reading of the ambiguous rate prompts
is accepted). A query that runs but returns the wrong number scores a miss — the entire point.

## Result 1 — The wall is the fan-out, not complexity

Answer-correctness (x/10) at `full`, retrieval pinned, over the four-model ladder:

| model | L1a | L1b | L2a | **L2b** | L3a | L4a | L4b | L5a | **L5b** |
|-------|:---:|:---:|:---:|:-------:|:---:|:---:|:---:|:---:|:-------:|
| ministral-8b (8B) | 10 | 10 | 10 | **0** | 10 | 10 | 10 | 8 | 10 |
| gpt-oss-20b (20B) | 10 | 10 | 10 | **2** | 10 | 10 | 10 | 9 | 1 |
| gpt-oss:120b (120B) | 10 | 10 | 10 | **2** | 10 | 10 | 10 | 10 | 2 |
| qwen3-coder:480b (480B) | 10 | 10 | 10 | **2** | 10 | 10 | 10 | 10 | 4 |

The striking thing is what the models *can* do. Nested two-level aggregation (L3a), window
functions with partitioning (L4a), running totals (L4b), lag-based growth rates (L5a) — the
"hard SQL" — are cleared at or near 10/10 across the whole ladder. Raw complexity is not the
wall.

**L2b is.** Net revenue — arguably a *simpler* query than the window functions the same
models ace — collapses to **0–2/10 for every model across the ~60× span**. The reason is
that it is not a difficulty problem but a *silent-correctness* problem: the natural
`sales LEFT JOIN returns` then `SUM(sales.revenue)` double-counts revenue for multi-return
sales, and the result still runs. Scaling from 8B to 480B does not close it: the best any
model manages is 2/10, and the 480B is no better than the 20B. The honest statement is a
*reliability* one — **no model in the ladder made the fan-out reliable**; across 360 runs the
trap is a near-flat floor, not a curve that scale bends.

L5b (the fan-out reached *through* a join) is noisier and, unlike L2b, does not present a
clean floor: `ministral-8b` scores 10/10 while the 120B scores 2/10 and the 480B 4/10.
Inspecting the SQL explains it without rescuing the models — on L5b the 8B happened to write
the correct pre-aggregated form (two `GROUP BY` CTEs joined on product), whereas the larger
models wrote the fan-out `SUM(s.revenue)` over the row-wise join. It is a genuine result, not
a grader artifact (the 8B's correct CTEs are in the banked SQL), and it is reported as the
messier companion to L2b's clean wall rather than a second clean wall.

## Result 2 — Specialization does not rescue it

If the fan-out were a capability gap, a model *specialized* for code and SQL should close it.
The specialist probe (10 repeats each) says otherwise:

| model | **L2b** | **L5b** |
|-------|:-------:|:-------:|
| devstral-small-24b | **0/10** | 0/10 |
| devstral-123b | **0/10** | 0/10 |
| qwen3-coder-next | **0/10** | 5/10 |

Every code-specialist fails L2b outright — 0/10, worse than the general ladder's 2/10 ceiling.
Two of the three are worse on L5b than the 8B general model. Specialization changes the SQL
these models are fluent in; it does not change whether they reach for the fan-out shape. The
scoped, defensible claim — the reliability framing again — is: **no tested model or code
specialist made the fan-out reliable across the combined 420 runs** (360 ladder + 60
specialist), so reliability here has to come from somewhere other than model selection.

## Result 3 — Deterministic aggregate-before-join: the fan-out solved

The lever is *deterministic* rather than a bigger or more specialized model. The
**aggregate-before-join scaffold** (`index/agg_before_join.py`, flag `SCAFFOLD_AGG_BEFORE_JOIN`)
applies a single rule to the model's *emitted* SQL: if a scope aggregates a column of the
"one" side of a 1-to-many join, rewrite it to pre-aggregate each table on its own grain
*before* joining. The model still writes every semantic choice — which tables, columns,
filters, the division; the scaffold repairs only the join-cardinality defect.

Because the rule is a pure function of `(emitted SQL, schema relationships)` and never sees
the model, the correction is **model-independent by construction**, in exactly the sense
Results 1–2 of the retrieval chapter established:

1. **relationship derivation** — a single-column primary key named like a cross-table
   reference (`sale_id`) makes any other table carrying that column a "many" side. A bare
   `id` surrogate is a table's own identity, not a foreign reference, so it is excluded. No
   foreign-key declarations are required (the demo schema has none).
2. **detection** — fires on exactly one anti-pattern: a scope equi-joining two base tables on
   a 1-to-many key while aggregating a one-side column. Every scope is examined, so a fan-out
   nested inside a CTE is caught too.
3. **rewrite** — each table is pre-aggregated into a derived table on the query's group keys
   (the many side reaching those keys through a many→one join that cannot fan out, LEFT-joined
   so zero-match groups survive at 0); the projection is re-pointed at the pre-aggregated
   results.

**The gate is an offline replay**, identical in discipline to the frozen-labels and
glossary-pin A/Bs: every banked ladder run already stored the model's exact emitted SQL, so
the rewrite is applied to each stored query, re-executed against the same DB, and re-graded
with the same `grade_answer`. OFF vs ON is therefore a *true paired comparison on identical
model outputs* — zero new model calls, fully deterministic. Result (7 models × 10 repeats per
trap):

| trap | OFF | ON |
|------|:---:|:--:|
| **L2b** net revenue | **6 / 70** | **70 / 70** |
| **L5b** return rate | 22 / 70 | 69 / 70 |
| regressions | — | **0** |

Per model, the clean wall is cleared **uniformly**: L2b goes to **10/10 for all seven
models** — ministral-8b, gpt-oss-20b, the 120B, the 480B, and all three specialists — from a
floor of 0–2/10. The 8B and the 480B end at the identical 10/10, which is the whole point:
the reliability was supplied by the rule, not the model.

Three properties, each mapping to something a deterministic scaffold must have to be
defensible:

- **It breaks the wall where capability could not (L2b).** The trap that no model or
  specialist made reliable becomes reliable for all of them, because the rewrite computes the
  join-cardinality-correct number regardless of which model emitted the query.
- **It does not distort what already works.** Zero regressions across 140 paired runs: the
  already-correct queries (the 8B's L5b CTEs, the models' occasional correct subquery forms)
  are recognised as *not* the anti-pattern and passed through untouched — the rewrite fired on
  111 of 140 runs and no-op'd the rest. A legitimate many→one aggregate (L2a's `sales`→`orders`
  join) is likewise never touched.
- **It respects its own boundary.** The single residual miss (L5b 69/70) is a `qwen3-coder`
  run that selects the *nullable side* of its own LEFT JOIN, yielding NULL product labels — a
  wrong-projection bug, **not** a fan-out. The scaffold honestly declines it, exactly the
  out-of-scope behaviour the determinism boundary predicts (the reasoning-layer analogue of
  q4 for glossary-pinning).

## Synthesis

Read across the three results, the reasoning layer exhibits the thesis claim in the same
two-part form the retrieval layer did:

- **The wall is real and capability does not scale past it.** The fan-out is not hard SQL —
  the models ace window functions and nested aggregation — it is a silent-correctness trap,
  and neither ~60× of scale nor explicit code-specialization made it reliable across 420 runs.
- **A deterministic rule supplies the missing competence.** Aggregate-before-join takes the
  clean-wall trap (L2b) from 0–2/10 to 10/10 for every model, by construction rather than by
  capability, and keeps every already-correct query intact.

This is the matched sibling of the retrieval chapter's pinning result, one stage down the
pipeline: where a richer model (or a specialist one) *should* have closed the gap and did not,
a small deterministic rule — a pure function of the emitted SQL and the schema — closes it
outright, and stays model-independent while doing so. The two chapters together make the
structural point the thesis rests on: at both the retrieval and the reasoning layer,
deterministic scaffolding — not model scale — is what makes the pipeline *reliable*, and it is
worth most exactly where the model is weakest.

## Threats to validity

- **The dedicated NL→SQL specialists were not tested.** The specialist probe covers
  *tool-calling* code models (devstral, qwen3-coder-next). The purpose-built text-to-SQL
  adapters (`sqlcoder`, `duckdb-nsql`) are completion-only and not hosted on the tool-calling
  endpoint, so they could not run in this harness at all — running them needs a separate
  native-completion harness and local inference, out of scope here. The "specialization does
  not help" claim is therefore scoped to tool-calling code models; whether a dedicated NL→SQL
  model writes the fan-out shape is untested, and is the most direct threat to Result 2.
- **Single schema, synthetic data, one dialect.** One ecommerce schema, synthetic seed,
  SQLite. The fan-out mechanism is general, but the numbers are measured on one schema family;
  the rewrite is implemented and tested for SQLite (the eval path). Generalisation to other
  schemas, real data, and other SQL dialects is untested (the rewriter passes a dialect through
  to `sqlglot`, but only SQLite is exercised).
- **The rewrite's recognised family is deliberately narrow.** It fires on a single 1-to-many
  equi-join with a one-side aggregate. Multi-table fan-out chains, non-equi joins, and
  fan-outs the detector does not recognise are no-ops — safe (they are left unchanged) but not
  solved. The L5b residual shows the flip side honestly: a non-fan-out SQL bug is out of scope
  and remains. The scaffold's real-world value scales with how often the recognised family is
  the actual defect; on this ladder it is the dominant one.
- **L5b is not a clean wall.** Unlike L2b, L5b's OFF numbers are model-dependent (the 8B beats
  the frontier models on it). The strong, clean claim is made on L2b; L5b is reported as the
  messier companion, and the fix's L5b result (69/70) is stated with its one residual, not
  rounded to a wall-clear.
- **Generation is non-deterministic; the retrieval-side numbers are not.** The OFF ladder
  cells are 10-repeat rates precisely because generation is noisy at temperature 0 (this is a
  statistical strength over the retrieval chapter's single-pass generation caveat). The ON
  numbers, by contrast, are deterministic given the OFF SQL — the rewrite is a pure function,
  so the paired comparison carries no additional sampling noise.
- **Latency is not a clean signal.** All models were served over a shared cloud endpoint;
  wall-clock times were noisy (the 20B sometimes ran slower than the 120B on the same day), so
  latency is excluded from the argument.

## Reproduce

All commands run from `/opt/analytiq` against the prod compose file — read every
`docker compose` below as `docker compose -f docker-compose.prod.yml`. The ladder DB is built
into a tempdir (it is regenerable and not committed).

```bash
# Build the ladder DB (3 gold tables + 24 distractors; multi-return sales = real fan-out)
DEMO_DB=/tmp/ecommerce_ladder.db DEMO_DOCS=/tmp/demo_docs \
  docker compose exec -T app python eval/build_ladder_db.py

# Results 1 & 2 — the reasoning ladder (retrieval pinned, 10 repeats). Banked raw:
#   eval/results/ladder_full.json (4-model ladder, 360 runs)
#   eval/results/ladder_specialists.json (3 code specialists, 60 runs)
docker compose exec -e EMBEDDING_MODE=model2vec -e DB_URL=sqlite:////tmp/ecommerce_ladder.db -T app \
  python -m eval.score --models ministral-8b gpt-oss-20b ollama-cloud qwen3-coder \
  --levels full --pin-tables --repeats 10 --gold gold/reasoning_ladder.json \
  --out eval/results/ladder_full.json

# Result 3 — aggregate-before-join A/B (offline replay of the banked SQL; deterministic,
# zero model calls). Writes grid_fanout_fix.json + grid_fanout_fix_evidence.md.
docker compose exec -T app python -m eval.fanout_fix_ab --db /tmp/ecommerce_ladder.db

# Live-wiring confirmation (spends a little OpenAI/Ollama credit): the same score.py with
# --agg-before-join forces the scaffold ON in the live orchestrator loop. On L2b, a model
# that scored 0/10 OFF returns the corrected (pre-aggregated) SQL and grades correct.
docker compose exec -e EMBEDDING_MODE=test -e DB_URL=sqlite:////tmp/ecommerce_ladder.db -T app \
  python -m eval.score --models ministral-8b --levels full --pin-tables --repeats 1 \
  --agg-before-join --gold gold/reasoning_ladder.json --out /tmp/on.json

# Module unit test (self-contained, in-memory SQLite fan-out; needs sqlglot)
python tests/test_agg_before_join.py
```
