#!/usr/bin/env bash
# Analytiq setup. Usage: ./setup.sh <target>
#   dev-cloud     app only, hosted LLM, no TLS, single-tenant   (quick local/VPS test)
#   dev-onprem    app + Ollama, no TLS, single-tenant           (quick on-prem test)
#   prod          Caddy(TLS) + app, multi-tenant, cloud LLM     (production SaaS)
#   prod-onprem   Caddy(TLS) + app + Ollama, single-tenant      (production on-prem)
set -euo pipefail
T="${1:-}"
case "$T" in
  dev-cloud)    COMPOSE=docker-compose.cloud.yml;        ENVEX=.env.cloud.example;        OLLAMA=0;;
  dev-onprem)   COMPOSE=docker-compose.onprem.yml;       ENVEX=.env.onprem.example;       OLLAMA=1;;
  prod)         COMPOSE=docker-compose.prod.yml;         ENVEX=.env.prod.example;         OLLAMA=0;;
  prod-onprem)  COMPOSE=docker-compose.prod-onprem.yml;  ENVEX=.env.prod-onprem.example;  OLLAMA=1;;
  *) echo "Usage: ./setup.sh [dev-cloud|dev-onprem|prod|prod-onprem]"; exit 1;;
esac

if [[ ! -f .env ]]; then
  cp "$ENVEX" .env
  echo "→ created .env from $ENVEX"
  echo "  EDIT IT (keys, DOMAIN, ADMIN_TOKEN, data source), then re-run: ./setup.sh $T"
  exit 0
fi

# air-gap: vendor chart libs if not present and we have internet
if [[ ! -f api/static/vendor/vega.min.js ]]; then
  echo "→ (optional) vendoring chart libs for offline use…"
  ./scripts/vendor_assets.sh || echo "  (skipped — no internet; UI will use CDN)"
fi

echo "→ building + starting [$T]…"
docker compose -f "$COMPOSE" up -d --build

if [[ "$OLLAMA" == "1" ]]; then
  TAG="$(grep -E '^DEFAULT_MODEL=' .env | cut -d= -f2)"
  OTAG="qwen2.5:14b-instruct"; [[ "$TAG" == "llama3.1-8b" ]] && OTAG="llama3.1:8b-instruct"
  echo "→ pulling $OTAG into Ollama (one-time)…"
  docker compose -f "$COMPOSE" exec -T ollama ollama pull "$OTAG"
fi

echo
if [[ "$T" == prod* ]]; then
  echo "✓ up behind TLS. Once DNS for \$DOMAIN points here, https://\$DOMAIN/ is live."
  [[ "$T" == "prod" ]] && echo "  create a tenant:  ADMIN_TOKEN=… ./scripts/create_tenant.sh \"Acme\" upload"
else
  echo "✓ up → http://localhost:8000/"
fi
