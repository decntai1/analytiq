# Analytiq — Codebase Map

_State-of-record for the code. Update when modules change. One line per file._

**What it is:** prompt-based data analysis + visualization over structured (SQL/files)
and unstructured (documents) company data. Deployable cloud or fully on-prem with
open-source LLMs. PhD thesis prototype + prospective product.

**Flow:** `question → intent router → schema-RAG (structured) / doc-RAG (unstructured)
→ read-only SQL + document retrieval → neutral chart spec → Vega-Lite (Grafana later)`.
The LLM is selectable per request (cloud or local). Scaffolding layers are togglable
for the thesis eval.

## Modules
- `config.py` — deploy mode, **MODEL_REGISTRY** (cloud + local, per-request selectable),
  **scaffolding flags** (`scaffold_schema_rag/validate_chart/repair/glossary/router`) +
  `apply_scaffold()` for the eval. Status: ✅ tested.
- `core/runtime.py` — runtime selector: ollama (demo) / analytiq (your runtime, prod) / custom. Switched by LLM_RUNTIME; local registry models follow it. ✅
- `core/inference.py` — live sampling settings (temp/top_p/top_k/max_tokens/penalties/seed/stop) + PARAM_META for the UI. ✅
- `core/llm.py` — provider adapters: `OpenAICompatibleProvider` (OpenAI/Grok/Ollama/vLLM)
  + `AnthropicProvider` (Claude). `get_provider(model_name)` resolves the registry. ✅
- `core/embeddings.py` — embeddings: `openai` / `local` (sentence-transformers) / `test`
  (offline hash) / `auto`. ✅
- `core/router.py` — intent routing: structured / unstructured / both (LLM classify). ✅
- `core/tools.py` — tool registry: `run_sql`, `make_chart`, `search_documents`. ✅
- `core/deck_planner.py` — plans a deck outline, runs the pipeline per slide, assembles → PPTX. ✅
- `viz/presentation.py` — DeckBuilder: editable PPTX, template-loadable, audit appendix. ✅
- `viz/raster.py` — Vega-Lite → PNG (vl-convert) for decks/export. ✅
- `core/orchestrator.py` — the agent loop; honors all 5 scaffolding flags; records
  `tables_retrieved` (for table-recall) + `errors`. ✅ (reads `config.settings` LIVE —
  do not re-bind `from config import settings`, breaks flag toggling).
- `index/vectorstore.py` — numpy cosine store (swap Chroma/FAISS at scale). ✅
- `index/schema_index.py` — **schema-RAG**: embed per-table descriptions, retrieve top-K.
  The scaling mechanism. ✅
- `index/doc_index.py` — **doc-RAG**: ingest .txt/.md/.pdf → chunks → retrieve + cite. ✅
- `connectors/base.py` — `StructuredConnector` ABC (schema + read-only query). ✅
- `connectors/sql.py` — SQLAlchemy (Postgres/MySQL/SQL Server/SQLite/warehouses) +
  read-only guard + schema introspection w/ sample row. ✅
- `connectors/duckdb_conn.py` — DuckDB (CSV/Parquet/Excel/files) + `register_file()` for
  live uploads. ✅
- `connectors/multi.py` — `MultiConnector`: merge live DB + uploaded files into one
  table surface. ✅
- `viz/spec.py` — **neutral chart spec** + declared `CAPABILITY` (source-of-truth B) +
  `validate_spec()`. ✅
- `viz/render_vegalite.py` — adapter: neutral spec → Vega-Lite v5. ✅
- `viz/render_grafana.py` — adapter STUB (later: neutral spec → Grafana panel + embed URL).
- `api/app.py` — FastAPI: `GET /` (UI), `/models`, `/health`, `POST /ask`, `POST /upload`.
  Live re-index on upload. ✅ tested via TestClient.
- `api/ingest.py` — upload routing: CSV/Parquet/Excel→DuckDB, PDF/txt/md→docs. ✅
- `api/static/landing.html` — marketing page: teal/slate SaaS design, "receipts" hero mock,
  why/how/compare/deploy. Self-hosted fonts (air-gap safe). ✅
- `api/static/index.html` — workspace: teal/slate SaaS chat, inline Vega-Lite charts, "How this
  was answered" provenance panel (table pills + SQL), upload, model picker, **Build deck**, and
  the **⚙ Inference settings drawer** (runtime + sampling params, live). ✅
- `api/static/fonts/` — self-hosted Inter + JetBrains Mono (woff2); `vendor/*.min.js` — vendored
  Vega/Vega-Lite/Vega-Embed. Both make the UI fully offline / air-gap safe. ✅
- `glossary.json` — metric definitions (source-of-truth C), e.g. net_revenue formula.
- `gold/gold_set.json` — eval gold set: questions + expected_tables/chart/docs. Includes
  the `q2_net_revenue_trap` table-recall trap.
- `eval/score.py` — **the measurement rig**: sweeps (model × scaffolding-level) over the
  gold set, scores table-recall / chart_ok / docs_ok / errors / latency → results.json. ✅
  tested via stub.
- `eval/run_models.py` — quick qualitative sweep of one question across models.

## Verified working (offline, stub LLM + test embedder)
router → schema-RAG → guarded SQL → neutral-spec→Vega-Lite → doc-RAG + citations →
grounded answer; UI + upload (CSV→table, txt→doc) + live re-index; scaffolding flags
change behavior; eval scorer produces the grid. **Untested:** live LLM calls (need a
key or running Ollama).

## Run
```bash
pip install -r requirements.txt
# cloud demo:  OPENAI_API_KEY + DEFAULT_MODEL=gpt-4o-mini
# on-prem:     DEPLOY_MODE=onprem DEFAULT_MODEL=qwen2.5-14b EMBEDDING_MODE=local + ollama serve
uvicorn api.app:app          # UI at http://localhost:8000/
python -m eval.score --models qwen2.5-14b gpt-4o-mini   # the thesis numbers
```
