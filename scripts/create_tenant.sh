#!/usr/bin/env bash
# Create a tenant and print its API key. Requires ADMIN_TOKEN + the app running.
#   ./scripts/create_tenant.sh "Acme Corp" [data_source] [db_url]
set -euo pipefail
NAME="${1:?usage: create_tenant.sh <name> [data_source] [db_url]}"
DS="${2:-upload}"; DBURL="${3:-}"
: "${ADMIN_TOKEN:?set ADMIN_TOKEN (same as in .env)}"
HOST="${HOST:-http://localhost:8000}"
curl -fsS -X POST "$HOST/admin/tenants" \
  -H "x-admin-token: $ADMIN_TOKEN" -H "content-type: application/json" \
  -d "{\"name\":\"$NAME\",\"data_source\":\"$DS\",\"db_url\":\"$DBURL\"}" | (jq . 2>/dev/null || cat)
