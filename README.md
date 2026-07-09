# Analytiq — NL → (SQL + RAG) → charts, self-hostable, multi-model

Ask a company's data a question in natural language; get a grounded answer plus a
chart. Handles **structured** (SQL databases, files) and **unstructured**
(documents) sources through one architecture, runs **cloud or fully on-prem**, and
lets you **swap LLMs per request** — built for both a product and thesis model
comparison.

## Architecture (matches the reference design)
```
                      question
                         │
                    intent router        ← SQL? documents? both?  (LLM classify)
                ┌────────┴────────┐
      structured arm          unstructured arm
   schema-RAG (top-K tables)   doc-RAG (top-K chunks)
        → run_sql (read-only)       → grounded passages + citations
        → rows                      │
        └──────────┬────────────────┘
              neutral chart spec  → validate (capability rules)
                         │
              renderer adapter → Vega-Lite (now) / Grafana (later)
                         │
            grounded answer + charts + citations + sql_log
```
The LLM never sees all tables — **schema-RAG retrieves only the relevant ones**,
which is what makes NL→SQL scale to 100+ tables. Structured and unstructured share
the same vector machinery, which is why "both" is one architecture, not two.

## Why these choices
- **Vega-Lite now, Grafana wireable later.** The LLM emits a *neutral* chart spec
  (`viz/spec.py`); a renderer adapter converts it. Vega-Lite renders inline with
  zero infra; the Grafana adapter (`viz/render_grafana.py`, stubbed) drops in for
  the embeddable chat-on-top / panel-below experience — no re-prompting.
- **Schema-RAG over schema-dump.** Retrieval, not a bigger context window, is the
  scaling mechanism (`index/schema_index.py`).
- **Multi-model registry.** `config.py` maps friendly names → provider/endpoint/key.
  OpenAI + Grok + local (Ollama/vLLM) via one OpenAI-compatible adapter; Claude via
  a native adapter. Select per request. Add a model on a bigger GPU box = one entry.
- **Connectors for real SMB data.** `SQLConnector` (Postgres/MySQL/SQL Server/SQLite/
  warehouses via SQLAlchemy) + `DuckDBConnector` (CSV/Parquet/files) cover ~90% of
  cases. New source = one subclass.


## Web UI

A single-page chat UI ships with the server: chat on top, charts rendered inline
(Vega-Lite via vega-embed), an **Upload** button, and a **model picker** so you can
switch between local Ollama models and cloud models live (useful for the thesis
comparison). Run the server and open `http://localhost:8000/`.

- **Upload button:** CSV / Parquet / Excel become queryable tables (DuckDB); PDF /
  TXT / MD become searchable documents (doc-RAG). The index rebuilds immediately, so
  you can upload a file and ask about it in the same session. Built for testing.
- **Model picker:** lists everything in `MODEL_REGISTRY`; the selected model runs the
  next question. Point an entry at Ollama and it's fully local.

## How connectors and schema discovery work

You do NOT hand-pick tables. The connector **auto-discovers** the data source:

1. **Discovery (startup):** the connector introspects the database — every table, its
   columns and types, plus one **sample row** per table (so the model sees real value
   shapes, not just names).
2. **Indexing (startup):** each table's description is embedded into the schema-RAG index.
3. **Per question (runtime):** schema-RAG retrieves only the **top-K relevant tables**
   and injects *those* schemas into the prompt. With 100 tables the model sees ~6 — never
   all of them. This is how the LLM "knows" what tables exist and what's in them: it's
   told the relevant subset, with samples, fresh on every question.

Want per-tenant access control (expose only certain tables)? Add an allowlist filter to
`schema_by_table()` — the default is auto-discover-all.

Just point the app at a database (`DB_URL`) or drop files in `UPLOAD_DIR` / `DOCS_DIR`.
A `MultiConnector` merges a live DB and uploaded files into one table set for the LLM.

## Ollama-only (no cloud at all)
```bash
ollama pull qwen2.5:14b-instruct && ollama serve
export DEPLOY_MODE=onprem DEFAULT_MODEL=qwen2.5-14b EMBEDDING_MODE=local
export DB_URL="sqlite:///ecommerce_large.db"
pip install -r requirements.txt
uvicorn api.app:app
# open http://localhost:8000/
```

## Layout
```
config.py                 deploy mode + MODEL_REGISTRY (cloud + local, per-request)
core/llm.py               provider adapters: OpenAI-compatible + Anthropic
core/embeddings.py        embeddings: openai / local (sentence-transformers) / test
core/router.py            intent routing (structured / unstructured / both)
core/tools.py             tool registry (run_sql, make_chart, search_documents)
core/orchestrator.py      the agent loop tying both arms together
index/vectorstore.py      numpy cosine store (swap to Chroma/FAISS at scale)
index/schema_index.py     schema-RAG — the scaling mechanism
index/doc_index.py        document-RAG — ingest + retrieve + cite
connectors/sql.py         SQLAlchemy connector (read-only guard + schema)
connectors/duckdb_conn.py DuckDB connector (files / CSV / Parquet)
viz/spec.py               neutral chart spec + declared capability + validator
viz/render_vegalite.py    adapter: neutral spec -> Vega-Lite
viz/render_grafana.py     adapter stub: neutral spec -> Grafana panel (later)
api/app.py                FastAPI: POST /ask, GET /models
eval/run_models.py        THESIS: sweep one question across many models
```

## Run — cloud demo
```bash
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...           # for LLM + embeddings
export DEFAULT_MODEL=gpt-4o-mini
export DB_URL="sqlite:///ecommerce_large.db"
export DOCS_DIR="./documents"          # drop PDFs/txt/md here for the doc arm
uvicorn api.app:app --reload
```

## Run — on-prem (data never leaves the box)
```bash
export DEPLOY_MODE=onprem
export DEFAULT_MODEL=qwen2.5-14b       # served by local Ollama
export LOCAL_LLM_BASE_URL=http://localhost:11434/v1
export EMBEDDING_MODE=local            # sentence-transformers on the box
export DB_URL="postgresql://readonly:...@db/sales"
uvicorn api.app:app
```

## Try it
```bash
curl -s localhost:8000/ask -H 'content-type: application/json' \
  -d '{"question":"Show monthly revenue vs spendings vs production for 2024","model":"qwen2.5-14b"}' | jq
curl -s localhost:8000/ask -H 'content-type: application/json' \
  -d '{"question":"Why were Q3 sales weak?"}' | jq      # routes to both arms
```

## Thesis: compare models
```bash
python -m eval.run_models "Why were Q3 sales weak? Show monthly revenue." \
    qwen2.5-14b llama3.1-8b gpt-4o-mini claude-3.5-sonnet
```
Same pipeline, same data — only the model varies. Captures answer, the SQL each
model wrote, chart validity, and latency.

## Bigger GPU box
Add entries to `MODEL_REGISTRY` in `config.py` pointing at the box's Ollama/vLLM
(e.g. `qwen2.5-72b`, `llama3.1-70b`) and include them in the eval sweep. No code
change — the registry + adapters already handle it.

## Security
The SQL guard is defence-in-depth. In production the **primary** control is a
**read-only DB role per tenant**. Never rely on string inspection alone.

## Offline / no-key testing
`EMBEDDING_MODE=test` uses a deterministic hash embedder (no network). The full
pipeline (routing, retrieval, SQL guard, chart spec, doc-RAG) is exercised in the
integration test without any API key; only live LLM calls need keys/Ollama.
