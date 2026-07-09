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
sources immutable (sha256-checked); plan changes ONLY via the verified Stripe
webhook; upload honesty — CSV ingest must NEVER silently bulk-drop rows (no bare
`ignore_errors`; messy/non-UTF-8 files get an encoding-transcode fallback that
loads all rows and REPORTS any genuinely-skipped ones) and NEVER report success
on 0-row ingestion (empty/header-only → honest failure). See
connectors/duckdb_conn.py `_load_csv`; map coverage with scripts/ingest_suite.py.

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
reads clearly) — the script proves plumbing, not experience. The model picker is
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
   Python execution).
3. Table-scope checkbox (pick which tables a question queries).
4. Dormant buy-credits/Stripe path — build 503'd until keys; activate in the one
   Stripe pass (register /billing/webhook now the URL is live, add keys).

## Standing items
- Ollama Cloud is on a FREE/personal key — move to Pro before real traffic (quota
  walls ~5M tok/wk, 120B burns it fast, no SLA).
- The REAL EVAL RUN (models × scaffold levels over the gold set) has NEVER run —
  roadmap item 1, the thesis result. The 8B→480B model ladder is now assembled +
  tool-verified: it IS the eval's independent variable, waiting. Nothing new needs
  building to run it. Flag once per session if still true.
- model2vec port (torch-free semantic embeddings) = the fix for the weak test-mode
  document arm — high value, "next session". See [[cloud-image-torch-free]].
- Live-keys Stripe checkout has never run; first real checkout is a launch-day step.
- Keep this file updated in the same commit as any change to the facts above.
