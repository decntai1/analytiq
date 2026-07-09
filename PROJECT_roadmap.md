# Analytiq — Roadmap

_The build queue. Ordered by impact. Status: ✅ done · 🔧 in progress · ⏳ next · 📋 later._

## Sellability waves (in progress)
- ✅ **Wave 1 — Presentation generator**: `/presentation` builds an editable PPTX from a request; outline-plan → per-slide pipeline → charts (vl-convert) → **audit-trail appendix with the SQL behind every number**. Template-loadable (per-tenant brand). UI: Build-deck button.
- ⏳ Wave 2 — Scheduled reports + alerts (tool→subscription)
- ⏳ Wave 3 — Saved dashboards + Grafana adapter
- ⏳ Wave 4 — Trust surfacing (confidence, catalog-browse, self-verify)
- ⏳ Wave 5 — RBAC / row-level security
- ⏳ Wave 6 — Conversational drill-down
- ⏳ Wave 7 — Semantic layer / multi-source joins

## Done
- ✅ **Runtime abstraction**: Ollama (demo) ↔ your Analytiq runtime (prod, on customer hardware) ↔ custom, via LLM_RUNTIME. Brain is runtime-agnostic (OpenAI-compatible contract). `RUNTIME.md` documents the contract.
- ✅ **Inference settings UI**: LM-Studio-style ⚙ panel — temp/top_p/top_k/max_tokens/penalties/seed/stop, each explained, live via `/settings/inference`.
- ✅ Core pipeline: router → schema-RAG → guarded SQL → neutral-spec→Vega-Lite → doc-RAG.
- ✅ Multi-model registry (cloud + local), per-request selection; Anthropic + OpenAI-compat adapters.
- ✅ Connectors: SQLAlchemy (live DBs) + DuckDB (files) + MultiConnector.
- ✅ Web UI: chat, inline charts, upload button, model picker, SQL/arm/tables trace.
- ✅ Scaffolding flags + `apply_scaffold()`; orchestrator honors all 5.
- ✅ Eval rig: `gold/gold_set.json` + `eval/score.py` (table-recall, chart, docs, errors, latency).

## Next (thesis-critical, in order)
1. ⏳ **Run the real eval.** Point at a demo DB matching the gold set, run
   `python -m eval.score --models qwen2.5-14b llama3.1-8b gpt-4o-mini` across all levels.
   Produces the accuracy-vs-scaffolding-vs-model curve = the thesis's central result.
2. ⏳ **Expand the gold set.** ~20–40 questions with verified `expected_tables` / values /
   chart types, including more table-recall traps (metrics needing a joined/secondary table).
   The eval is only as strong as the gold set.
3. ⏳ **Show retrieved tables in the UI** (the "did it miss a table?" answer). The `/ask`
   response already returns `tables_retrieved`; render it in the trace strip so a skeptical
   user/committee sees which tables were considered. Small change, high credibility.
4. ⏳ **Catalog-browse tool** (`list_tables(keyword)`): let the model browse the full table
   catalog when top-K retrieval looks thin / request more — turns a hard cutoff into a
   searchable catalog. Biggest robustness win against silent misses.

## Then (accuracy + product)
5. 📋 **Metric glossary wired into retrieval.** Glossary already injected as a prompt block
   (`scaffold_glossary`); next, make a defined metric *pull its named tables into context*
   so retrieval can't miss them. Highest-leverage accuracy fix.
6. 📋 **Self-verification pass** (`scaffold_verify`): after drafting SQL, ask "does this use
   every table the question needs?" Add as a 6th scaffolding flag → another eval data point.
7. 📋 **Grafana adapter** (`viz/render_grafana.py`): neutral spec → panel JSON → OSS API →
   embed URL. Unlocks the chat-on-top / persistent-panel-below experience.
8. 📋 **build_presentation tool:** assemble answers + charts into a report/deck (pptx).

## Product-only (post-PhD decision)
- 📋 Per-tenant connector resolution (auth → tenant → their DB creds + deploy mode).
- 📋 Read-only DB role per tenant (the PRIMARY SQL safety control; current guard is
  defence-in-depth only).
- 📋 On-prem installer (compose: app + Ollama + read-only DB binding); vendor chart libs
  locally for air-gapped sites.
- 📋 Scale the vector store (Chroma/FAISS) when a customer's doc corpus is large.

## Known caveats (carry forward)
- Chart libs load from CDN in the UI — vendor locally for air-gapped on-prem.
- numpy vector store is right-sized for ≤ few hundred tables; swap at scale.
- SQL guard is defence-in-depth, NOT primary; production needs read-only DB roles.
- Open-model capability gap is real; the eval should map *where scaffolding stops helping*.
