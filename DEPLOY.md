# Analytiq — Deployment & Production Hardening

One image, four deploy targets, three data modes, single- or multi-tenant. All driven
by `.env`.

## Targets (./setup.sh <target>)
| target        | proxy/TLS | tenancy       | LLM          | use                         |
|---------------|-----------|---------------|--------------|-----------------------------|
| `dev-cloud`   | none      | single        | cloud API    | quick local/VPS test        |
| `dev-onprem`  | none      | single        | local Ollama | quick on-prem test          |
| `prod`        | Caddy TLS | **multi**     | cloud API    | production SaaS             |
| `prod-onprem` | Caddy TLS | single        | local Ollama | production on-prem (1 box)  |

```bash
./setup.sh prod            # writes .env from template
# edit .env: DOMAIN, ADMIN_TOKEN, OPENAI_API_KEY, CORS_ORIGINS
./setup.sh prod            # builds, starts Caddy+app; TLS auto once DNS points here
```

## Multi-tenant SaaS (prod)
- Auth: every `/ask` `/upload` `/tables` needs `X-API-Key: <tenant key>` (or `Bearer`).
- Isolation: each tenant gets its own connector + indexes + upload/doc dirs under
  `/app/tenants/<id>/`. Tenants never see each other's tables/docs. **Verified by test.**
- Create a tenant (returns the API key — store it):
  ```bash
  ADMIN_TOKEN=<from .env> ./scripts/create_tenant.sh "Acme Corp" upload
  # or database-backed:
  ADMIN_TOKEN=… ./scripts/create_tenant.sh "Acme" database "postgresql+psycopg2://ro:pw@host/db"
  ```
- A tenant attaches data via: their API key + `data_source` (upload | database | files | all)
  + `db_url`. Each tenant can use a different model (`default_model`).

## On-prem (prod-onprem)
- App + Ollama + local embeddings: **nothing leaves the box**. Single implicit tenant,
  no auth needed (set `MULTI_TENANT=0`, the default).
- Customer data: `DATA_SOURCE=database` + their read-only `DB_URL`, or `DATA_SOURCE=files`
  with a read-only mount (`/path:/data/files:ro` in the compose).
- GPU: uncomment the `deploy.resources` block under `ollama`.
- Ollama has no published port here → stays internal to the compose network.

## Security (built in, configurable)
- **TLS** via Caddy (auto Let's Encrypt) + HSTS / nosniff / frame / referrer headers.
- **Auth**: API key per tenant; admin endpoints behind `ADMIN_TOKEN`. **Verified.**
- **Rate limiting**: `RATE_LIMIT_PER_MIN` per tenant/IP (returns 429). **Verified.**
- **Upload cap**: `MAX_UPLOAD_MB` (returns 413). **Verified.**
- **CORS**: `CORS_ORIGINS` allowlist (empty = no cross-origin).
- **SQL**: read-only guard (defence-in-depth). **Still use a read-only DB role per tenant** —
  that's the primary control.

## Air-gapped on-prem
Chart libs load from `/static/vendor/` first, CDN only as fallback. To remove the CDN
dependency entirely, run on a machine with internet before shipping:
```bash
./scripts/vendor_assets.sh      # downloads vega libs into api/static/vendor/
```
Then the bundle is fully offline.

## Routes
- `/`     — marketing landing page (sells the USPs)
- `/app`  — the workspace (chat + charts + audit trail)
- `/health` `/models` `/ask` `/upload` `/tables` `/admin/*` — API

## Test immediately
```bash
docker compose -f docker-compose.prod-onprem.yml exec app python -m scripts.seed_demo
# set DATA_SOURCE=database DB_URL=sqlite:////app/demo.db, restart, then:
curl -sk https://localhost/health | jq
```

## Thesis eval (any target)
```bash
docker compose -f <compose> exec app \
  python -m eval.score --models qwen2.5-14b gpt-4o-mini --out /data/eval_results.json
```

## Pre-customer checklist
- [x] TLS (Caddy) · [x] auth + admin gate · [x] rate limit · [x] upload cap · [x] CORS
- [x] per-tenant data isolation · [x] air-gap option
- [ ] **Read-only DB role per tenant** (you must provision this on the customer DB)
- [ ] Backups of the `analytiq_tenants` / `analytiq_data` volumes
- [ ] Rotate `ADMIN_TOKEN`; store tenant keys securely
- [ ] (scale) move tenant registry + rate limiter from JSON/in-memory to a DB/Redis
