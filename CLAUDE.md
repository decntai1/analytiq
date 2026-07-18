# CLAUDE.md — Analytiq FULL PLATFORM (accounts lineage, r5)

You are working on the **full Analytiq platform tree**: the multi-tenant SaaS
build with accounts, tiers, credits, billing, chats, decks, workbench, and
dashboards. This is NOT the tree running on the current VPS demo — see
"Two lineages" below before assuming anything about production.

Analytiq: PhD thesis prototype + product. Prompt-based data analysis &
visualization over structured (SQL/files) + unstructured (documents) company
data, deployable fully on-prem with open-source LLMs. Pipeline: NL question →
intent router → schema-RAG / doc-RAG → read-only SQL + doc retrieval →
neutral chart spec → Vega-Lite. Thesis: deterministic scaffolding substitutes
for model capability, measured (scaffold flags × model size → accuracy).

## Two lineages — read this first
- **VPS demo lineage** (`/opt/analytiq` on the demo box, analytiq.nomoad.net):
  single-tenant, NO accounts. Grew its own features (upload ledger, multi-sheet
  xlsx, table delete/verify, name-pin, list_tables, table-scope, data drawer).
  It has its OWN CLAUDE.md. Do not port accounts there or reconcile lineages
  without explicit instruction from Tamás.
- **THIS tree (full platform)**: everything the demo has architecturally, PLUS
  accounts/sessions (scrypt), company invite codes, PLANS + question credits
  (1/question, 10/deck) with 402 gating, plan-gated session memory, per-tenant
  dedicated llm_base_url, chats sidebar, selection→PPTX decks, profile drawer
  (top-right credits chip → email/plan/balance/tier-chooser/portal/password
  change), Stripe billing (checkout + portal + signature-verified webhook as
  the ONLY plan writer), landing page with the 5-tier pricing, workbench
  module, dashboard module.

## Tiers (settled pricing — don't invent numbers)
Explore €0 (15 q/mo) · Analyst €29/user/mo (300 credits, self-serve checkout)
· Team €940/mo up to 10 users, dedicated model (self-serve; PLANS key is
`business`) · Business €2,400/mo billed annually, up to 25 users (contact
sales, no checkout) · On-prem from €9,600/node/yr (contact). Rule: tiers
differentiate on capacity, data boundary, and governance — NEVER on safety
scaffolds. Every tier gets read-only SQL, validated charts, full trace.

## Working discipline (non-negotiable)
1. Recon read-only first; report spec-vs-code contradictions before editing.
2. One concern per commit; commit as you go.
3. Isolated acceptance (tempdir, zero prod writes) before restarts/deploys.
4. Batteries are deploy gates with exit codes. This tree has FIVE:
   scripts/cleanroom_battery.py (10 sections, full stack), workbench_battery
   (41 checks), dashboard_battery, billing_battery (offline: real webhook
   signatures, monkeypatched checkout), plus the stub eval grid
   (python -m eval.score --stub) for the pipeline itself.
5. Never claim untested capability. Static files need no restart; Python does.

## Safety invariants — never regress
Read-only SQL guard in both connectors (dashboards refresh inherits it);
neutral chart-spec whitelist (never expose raw Vega-Lite; grow primitive by
primitive); uploads/workbench/dashboards realpath-confined; workbench LLM has
NO tools (whitelisted-ops plan → deterministic executor → logged recipe);
structure/type RECOGNITION is automatic & deterministic at ingest (e.g.
timestamp-text detection annotates the schema with the strptime cast — see
duckdb_conn._ts_hints_for) but the LLM NEVER auto-mutates data to "fix" a file
— reshaping/cleaning is user-initiated in the workbench, advise-only;
sources immutable (sha256-checked); plan changes ONLY via the verified Stripe
webhook; upload honesty — CSV ingest must NEVER silently bulk-drop rows (no bare
`ignore_errors`; messy/non-UTF-8 files get an encoding-transcode fallback that
loads all rows and REPORTS any genuinely-skipped ones) and NEVER report success
on 0-row ingestion (empty/header-only → honest failure). See
connectors/duckdb_conn.py `_load_csv`; map coverage with scripts/ingest_suite.py.
Ingest has ONE robust path (`register_file`); the startup re-scan (`_register_files`,
which re-registers uploads into the per-tenant DuckDB after every restart) MUST route
through it — never a parallel bare loader. That drift silently dropped cp1252 CSVs
and ALL xlsx on restart until unified. DuckDB access is THREAD-SAFE via a per-connector
re-entrant lock (guards the shared con AND the shared Python state — same-tenant requests
share one cached connector in FastAPI's sync threadpool); per-tenant DuckDB is FILE-BACKED
at `tenants_root/<tid>/analytics*.duckdb` (one file per store; xlsx materialized as TABLEs
so it persists; migration is the lazy `_register_files` rebuild). Gate:
`tests/concurrency_smoke.py`. Scope/parked scale decisions: `docs/scaling-decisions.md`.

## Deploy (docker-compose + Caddy — this is what the tree ships; see DEPLOY.md)
NOTE: an earlier CLAUDE.md described a bare-metal `deploy_vps.sh` /
`analytiq.env.vps` / systemd+nginx+certbot runbook. That tooling was NEVER in
this tree — it was a phantom from an advisory session. The real, checked-in
deploy path is Docker. Do not recreate the bare-metal runbook.

One image (`Dockerfile`, python:3.12-slim), four targets, all driven by `.env`.
Entry point is `./setup.sh <target>` (writes `.env` from the matching template,
then builds+starts); or drive compose directly. Prod SaaS:
  cp .env.prod.example .env   # edit DOMAIN, ADMIN_TOKEN, keys (see below)
  docker compose -f docker-compose.prod.yml up -d --build
Targets (DEPLOY.md table): dev-cloud / dev-onprem / prod (Caddy TLS, MULTI,
cloud LLM) / prod-onprem (Caddy TLS, single, local Ollama).

TLS: **Caddy** (`deploy/Caddyfile`, image caddy:2) auto-provisions + renews
Let's Encrypt from `DOMAIN` in `.env`. NO nginx, NO certbot. Caddy binds host
80/443; app listens only on internal :8000 (not published). DNS A record for
DOMAIN must resolve to the box before Caddy can issue the cert.

State = **Docker named volumes**, NOT /opt/analytiq/state/: `analytiq_tenants`
→ /app/tenants, `analytiq_data` → /data (so `ACCOUNTS_DB=/data/accounts.db`).
Backups of BOTH volumes are mandatory once real users register.

`.env.prod.example` is the template. Required keys: DEPLOY_MODE=cloud,
MULTI_TENANT=1, DOMAIN, ADMIN_TOKEN, DEFAULT_MODEL, OPENAI_API_KEY,
EMBEDDING_MODE=openai, CORS_ORIGINS, RATE_LIMIT_PER_MIN, MAX_UPLOAD_MB,
DATA_SOURCE, ACCOUNTS_DB, COOKIE_SECURE=1. Billing: STRIPE_SECRET_KEY /
STRIPE_WEBHOOK_SECRET / STRIPE_PUBLISHABLE_KEY, PUBLIC_URL, and THREE price IDs
— STRIPE_PRICE_ANALYST / STRIPE_PRICE_TEAM / STRIPE_PRICE_BUSINESS (code reads
all three: api/billing_routes.py PRICES). Webhook endpoint /billing/webhook
must be registered in the Stripe dashboard.

Prereqs / gotchas: Docker + compose engine must be installed on the host (not
present by default on a fresh box). The cloud image is torch-free: the Dockerfile
installs sentence-transformers ONLY under the `INSTALL_LOCAL_EMBEDDINGS=1` build
arg (set by the on-prem compose files), and requirements.txt keeps it commented
out (fixed in 769368d) so `pip install -r requirements.txt` no longer drags
torch+CUDA (~5G) into every image. Never re-list sentence-transformers in
requirements.txt — on a small (≤4G) box that build is a real OOM risk (it already
powered the box off once) and pure dead weight for cloud prod
(EMBEDDING_MODE=openai). It's only needed for on-prem local embeddings. If a
pip step runs on a box where /tmp is a small tmpfs, point TMPDIR at the big
disk first (a scrubbed `env -i` or Docker build layer resets it to /tmp).
statsmodels IS an allowed base dep (dry-run-verified against the pinned pandas
3.0.3 / numpy 2.5.1: adds only scipy+patsy, ~45MB manylinux wheels, NO torch) —
it powers core/forecast.py and nothing else; the /ask path never imports it.

## Post-deploy verification (required gate)
The five batteries prove the code in isolation (tempdir). They do NOT test the
live deployed site over real HTTPS — that's what `scripts/smoke_live.py` is for.
It hits the RUNNING instance end-to-end:
  python scripts/smoke_live.py --base-url https://analytiq.dcentai.tech
Checks (PASS/FAIL/SKIP per line, no secrets printed, exit 0 iff none FAILed):
health+landing (5 tiers), TLS cert valid/for-domain/unexpired, register→Free+15
credits, CSV upload+row count, live /ask → answer+chart spec+sql_log trace,
2-sheet xlsx (both sheets), dashboard pin→persist→refresh (SQL only, no LLM),
workbench session→profile→propose→apply→download with source sha256 unchanged,
credit metering, billing DISABLED (config configured:false, checkout 503 not
500). Run under the app venv so the xlsx path (openpyxl) runs instead of SKIPs.
Rule: this must pass GREEN against the live site before billing is wired, and
after every future deploy. Two spec items are deliberately SKIPPED because they
are VPS-demo-lineage features absent from this tree: table scope+delete (no
route) and full account deletion (no endpoint — throwaway accounts persist,
unique email per run, harmless). The live-model checks spend a little OpenAI
credit. After it passes, a human still eyeballs the UX (charts render, trace
reads clearly) — the script proves plumbing, not experience. TWO-BACKENDS RULE
(learned the hard way): the demo DB is sqlite (dates → strings) but the tenant
upload path is DuckDB (dates/decimals → NATIVE python objects), so they serialize
DIFFERENTLY. Any smoke assertion about /ask behavior MUST run against BOTH — a
sqlite-only check passed 32/0 while `/ask` over an uploaded DATE column 500'd
("Object of type date is not JSON serializable"). Section 5c uploads a typed CSV
(DATE+DECIMAL) and asserts /ask returns 200; keep that class of coverage. The
model picker is
plan-gated (PLAN_MODELS): Free = ministral-8b only (cheapest tool-capable — Free
must NOT default to the pricey 120B); paid tiers get the full curated set. Every
offered model is tool-VERIFIED for run_sql on the Ollama Cloud tier; smoke_live.py
tool-probes the paid ones (needs OLLAMA_API_KEY in env) and scripts/verify_paid_models.py
is a ONE-TIME build-time acceptance (uses ADMIN_TOKEN to mint a Business tenant and
/ask each model E2E — NOT part of the recurring gate). Only add a model to the picker
after it passes a live query; catalog listing ≠ usable (tier 403s + tool-calling 500s
are real, only a live probe catches them).

## Key map (this lineage; see PROJECT_codebase-map.md for the core pipeline)
core/accounts.py (users/sessions/credits/conversations, change_password) ·
api/routes_accounts.py (/auth/*, /chats) · api/billing_routes.py (/billing/*)
· core/tenancy.py (Tenant + stripe_customer_id; auth.store() is THE shared
singleton) · core/workbench.py + api/workbench_routes.py (+recipes) ·
core/dashboards.py + api/dashboard_routes.py · api/static/: landing.html
(5 tiers), login.html, index.html (chat + chips + drawers + pin), workbench.html,
dashboard.html · config.py: MODEL_REGISTRY, scaffold flags, PLANS, PLAN_MODELS
(per-tier model gating; /ask enforces server-side, /models filters by plan).

## Live deploy state (as of the r5 launch session)
LIVE at https://analytiq.dcentai.tech (Caddy TLS, MULTI, Ollama Cloud). Shipped +
verified this session (see [[deploy-target]] memory):
- Plan-gated model picker (config.PLAN_MODELS): 4 tool-verified Ollama-Cloud
  models, Free=ministral-8b (cheapest, fixes the cost leak), paid=all 4. /models
  filters by plan; /ask ENFORCES server-side (Free POSTing a paid model → 403
  before credits are charged). verify_paid_models.py is ONE-TIME build-time
  acceptance (uses ADMIN_TOKEN), NOT the recurring gate.
- Upload visibility: /tables returns table_details (name/rows/columns) + documents
  (files); document count is FILES not chunks; uploads announce table-vs-document
  and flag doc Q&A limited while EMBEDDING_MODE=test.
- Robust CSV ingest (shipped): encoding transcode fallback, CSVs report row counts,
  honest skip reporting. 24-case scripts/ingest_suite.py green.

## KNOWN ISSUE — copy overpromises (fix before it bites)
The Team tier copy claims a "dedicated private model endpoint" but ALL tiers
currently share the SAME Ollama Cloud endpoint — no dedicated endpoint is
provisioned (the `llm_base_url` hook exists; the RunPod machinery does not). Do
NOT promise dedicated infra in landing/pricing copy until provisioning is built.

## Build queue (priority order)
1. Workbench data-preview + nav links (no /workbench or /dashboard link from the
   main UI yet) — show columns/types/sample rows so users clean what they can see.
2. Colorful charts + numeric data labels (grow the neutral chart-spec whitelist
   primitive-by-primitive — scatter/heatmap within the deterministic model, NEVER
   Python execution). SHIPPED so far: statistical types (histogram/boxplot/heatmap/
   density/stacked_*/rolling_line + scatter trend) via Vega-Lite/DuckDB transforms;
   GEOGRAPHIC maps (choropleth country|us_state + geo_points) — see below.
3. Table-scope checkbox (pick which tables a question queries).
4. Dormant buy-credits/Stripe path — build 503'd until keys; activate in the one
   Stripe pass (register /billing/webhook now the URL is live, add keys).

## Standing items
- GEOGRAPHIC CHARTS (Phase B, shipped): neutral types `choropleth` (region+value,
  region_level country|us_state) and `geo_points` (lat+lon, optional size/color).
  Region names/codes are resolved to topojson feature ids SERVER-SIDE via the FROZEN
  `index/region_lookup.json` (built by scripts/build_region_lookup.py from the vendored
  topojson + ISO-3166 + a curated European-endonym list; 598 country keys, 107 us_state
  keys) — the LLM never emits a
  region code, so maps are model-independent BY CONSTRUCTION (same determinism boundary
  as glossary_pin: normalized exact-match, NO fuzzy/synonyms). The endonyms (Deutschland,
  Magyarország, España, Österreich, Suomi, … — build_region_lookup.py COUNTRY_ENDONYMS)
  are FROZEN exact keys, same status as ISO codes, NOT a fuzzy step; a bucket like "EMEA"
  still does NOT resolve (honest refusal). Renderer refuses HONESTLY (ValueError -> graceful "Chart error", never a
  500) when <80% of region values resolve or the column is non-geographic. Basemaps are
  vendored (`api/static/vendor/world-110m.json`, `us-10m.json`) and referenced by SAME-
  ORIGIN URL (air-gap rule; re-run build_region_lookup.py if you refresh them). Gate:
  smoke_live.py §5e (country CSV -> map 200 + geoshape; non-geo -> honest 200 refusal).
  CAVEAT: the topojson loads by URL, so DECK/PPTX map PNGs (viz/raster.py vl-convert)
  can't fetch the basemap offline — maps render in the BROWSER (vega-embed) but the
  slide raster path is unproven; treat maps as chat-only until that's addressed.
- Ollama Cloud is on a FREE/personal key — move to Pro before real traffic (quota
  walls ~5M tok/wk, 120B burns it fast, no SLA).
- The REAL EVAL RUN (models × scaffold levels over the gold set) — roadmap item 1,
  the thesis result. Recon found the headline metric (table_recall) was DEGENERATE:
  with only the 3 gold tables and SCHEMA_TOP_K=6, top-6-of-3 = all 3 always ->
  recall saturates at 1.0 and can't discriminate. FIXED by eval/build_demo_db.py:
  a demo DB (ecommerce_large.db, 0-byte placeholder before) with the 3 gold tables
  PLUS ~24 distractors (some confusable: refunds~returns, manufacturing~produced_items)
  so top-K must choose. Harness runs end-to-end (gpt-oss-20b, err=0.0). HONEST reading
  of the recall numbers (earlier "none=1.0 vs full=0.5 — it discriminates" was WRONG —
  it discriminated in the WRONG direction between two ARTIFACTS): none=1.0 is DEGENERATE
  (scaffold_schema_rag OFF dumps ALL tables, so every table is trivially "present" —
  not competence); the number that matters is `full` retrieval QUALITY. Two fixes shipped
  this session: (a) chart_ok scorer bug — it read charts[0]["mark"]["type"] but value-
  labelled charts are LAYERED (mark at layer[0]); every line/bar scored a false miss,
  pinning chart_ok at 0.40. Fixed with _chart_mark() (score.py). (b) model2vec DONE —
  EMBEDDING_MODE=model2vec (potion-base-8M, torch-free, in requirements.txt). Under it
  `full` recall 0.50 (hash noise — missed even `sales`) -> 0.70, and now the misses are
  MEANINGFUL: q1/q3 fetch `sales` where hash missed it; q5 "gross MARGIN" loses `sales`
  to confusable traps (revenue_targets/manufacturing), q4 loses `produced_items` — real
  retrieval difficulty, not noise. FULL GRID RAN 2026-07-09 (free key, quota fine — Ollama
  Pro NOT needed; ~80 runs) over the 4-model ladder × 4 levels under model2vec. Raw JSON:
  eval/results/grid_stageA.json (ministral-8b, gpt-oss-20b) + grid_stageB.json (ollama-cloud
  =120B, qwen3-coder=480B). HEADLINE RESULTS (the thesis, measured):
  (1) RETRIEVAL IS MODEL-INDEPENDENT — all 4 models (8B..480B) retrieved BYTE-IDENTICAL
  tables at every level & question (the crux held across a ~60x capability gap; router-ON
  levels did NOT diverge). table_recall is purely a function of scaffold level: 1.0 none
  (dump), 0.70 rag/rag+val+rep/full (semantic top-6) — identical across ALL models. The 0.70
  ceiling is an EMBEDDER property (potion-base-8M), not the LLM — lift it with potion-32M.
  (2) SCAFFOLDING SUBSTITUTES FOR CAPABILITY (the payoff) — the weak model is where it bites:
  ministral-8b errors 3.4/q at `none` (drowns in the 27-table dump) -> 0.6 at `rag`; its
  chart_ok 0.60 -> 0.80. The 20B/120B/480B sit at ~0 errors everywhere — capable enough to
  handle the dump unaided, so scaffolding has little to rescue. Clean monotonic gradient.
  Caveats: latency is noisy on shared Ollama Cloud (20B ran SLOWER than 120B that day — not a
  clean signal); docs_ok reliable only once router is ON (full=1.0 all models). Re-run:
  docker compose exec -T app python - < eval/build_demo_db.py  # (re)build DB+doc
  docker compose exec -e EMBEDDING_MODE=model2vec -e DB_URL=sqlite:////app/ecommerce_large.db \
    -e DOCS_DIR=/app/eval/demo_docs -T app \
    python -m eval.score --models <ladder> --levels none rag rag+val+rep full
- GLOSSARY→TABLE PINNING (the deterministic ceiling-breaker) SHIPPED as a retrieval
  scaffold: `index/glossary_pin.py` + `SCAFFOLD_GLOSSARY_PIN` (code default OFF; ENABLED
  in prod via docker-compose.prod.yml env as of the flip — the eval result justified it).
  eval/score.py LEVELS pin `glossary_pin:False` on every level so banked grids don't
  inherit the prod flag. Rule: a question naming a glossary metric
  pins the tables in that metric's FORMULA (`SUM(sales.revenue)` → `sales`) into the schema
  context; pure function of (question, glossary), so retrieval stays model-independent BY
  CONSTRUCTION. Wired in `orchestrator._schema_context` (skips authoritative user table-
  scope; only pins tables the connector has). A/B `eval/glossary_pin_ab.py` (labels ON,
  model2vec) → `eval/results/grid_glossary_pin*`: recall **0.70→0.90**, q5 `gross_margin`
  CLEARS (`sales` 0.00→1.00) where frozen labels could NOT; q2 `net_revenue` pins but is a
  NO-OP (already retrieved — doesn't distort what works); q4 (causal/doc, no metric match)
  unchanged 0.50. Determinism boundary is documented in the module + evidence md (normalized-
  key substring match; no synonyms/stemming). Paired thesis result with the labels nuanced-
  negative: labels shift ranking but can't break the ceiling; a deterministic glossary rule
  breaks it exactly where labels couldn't — scaffolding substituting for capability at the
  retrieval layer. bge-m3 (the embedder-ceiling arm) now OPTIONAL — parked pending Ntest1.
- AGGREGATE-BEFORE-JOIN (the deterministic fan-out fix — the REASONING-layer sibling of
  glossary_pin) SHIPPED as a SQL-shaping scaffold: `index/agg_before_join.py` +
  `SCAFFOLD_AGG_BEFORE_JOIN` (code default OFF; ENABLED in prod via docker-compose.prod.yml env
  as of the flip — the banked eval justified it). Needs `sqlglot` (pure-Python, in requirements).
  TRANSPARENCY: when the rewrite fires, orchestrator records BOTH the model's original SQL AND
  the rewritten query in `sql_log` (the /ask trace) + a server log line — a scaffold that alters
  the computed number must be auditable. Prod blast radius today is the SQLConnector path only
  (DuckDB uploads no-op — see parked item).
  Rule: when a model's emitted SQL aggregates a column of the "one" side across a 1-to-many
  join it double-counts (the join fan-out — a wrong number that still runs); the scaffold
  rewrites that scope to pre-aggregate each table before joining. PURE function of (emitted
  SQL, schema relationships), never the LLM → model-independent BY CONSTRUCTION. Relationships
  derived from the schema (single-col PK named `<entity>_id`; a bare `id` surrogate is NOT a
  cross-table ref — excluded). Wired in `orchestrator._maybe_agg_before_join` (intercepts
  run_sql when ON; duck-typed on `connector.relationships()`, graceful no-op otherwise — e.g.
  DuckDB uploads, a follow-up). eval/score.py LEVELS pin `agg_before_join:False` on every
  level; `--agg-before-join` forces it ON for the live gate. A/B `eval/fanout_fix_ab.py` is an
  OFFLINE REPLAY of the banked ladder SQL (paired on identical model outputs, zero model calls,
  same discipline as glossary_pin_ab) → `eval/results/grid_fanout_fix*`: **L2b net-revenue
  0-2/10 → 10/10 for ALL 7 models (8B..480B + specialists), L5b return-rate 22/70 → 69/70,
  0 regressions**. The single L5b residual is a wrong-outer-join-projection bug (NULL labels),
  NOT a fan-out, so the scaffold honestly declines it (the q4-style boundary). Determinism
  boundary documented in the module + evidence md. The reasoning-arm's matched pair: fan-out
  defeats every model AND every code-specialist (ladder_full/ladder_specialists), a
  deterministic rule solves it outright — scaffolding substituting for capability at the
  reasoning/SQL layer, mirroring pinning at retrieval.
  PARKED (record, don't build yet): (a) before any real BYO-database customer, harden
  `derive_relationships` to prefer DECLARED foreign keys (`inspector.get_foreign_keys`) over the
  `<entity>_id` name convention, falling back to the convention only when no FKs are declared —
  real customer schemas won't reliably follow naming; declared FKs remove the heuristic risk.
  (b) DuckDB-upload `relationships()` so the fix protects the wedge path (tenant CSV uploads) —
  needs a design pass since uploaded CSVs declare no PKs.
- Live-keys Stripe checkout has never run; first real checkout is a launch-day step.
- Keep this file updated in the same commit as any change to the facts above.
