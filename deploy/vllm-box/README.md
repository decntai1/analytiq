# Dedicated GPU box — operator notes (Tier 2 sessions / Tier 3 companies)

**Status: written, not live-tested** (no GPU in the build environment).
First-boot check: `curl -s localhost:8000/v1/models` must list the model.

## Where to rent
- **Tier 2 (hourly sessions):** RunPod **Secure Cloud**. Per-second billing, no
  egress fees, and a **network volume** mounted at `MODEL_CACHE` so weights
  download once per region (a 100 GB volume holds 14B+32B+70B AWQ for ~$7/mo).
  EU regions: Norway / France / Netherlands (~5–15% over US).
- **Tier 3 (monthly dedicated):** Verda (ex-DataCrunch, EU) first quote —
  match the committed term to the customer's contract term, never longer.
  Alternates: OVHcloud / Scaleway (EU), RunPod EU for business-hours scheduling.
- Vast.ai: eval runs only. Never customer-facing.

## Boot
```bash
cp .env.example .env       # set MODEL_ID + size tier + VLLM_API_KEY
docker compose up -d
```

## Wire to a customer (SaaS host side)
```bash
curl -X POST https://<saas-host>/admin/tenants -H "X-Admin-Token: $ADMIN_TOKEN" \
  -d '{"name":"Acme","plan":"business",
       "llm_base_url":"http://<box-ip>:8000/v1","llm_model_id":"default"}'
```
Every user of that company now shares this box; vLLM continuous batching
handles their concurrency (see sizing table in the compose header).

## Must-do hardening
- Firewall port 8000 to the SaaS host IP only (`ufw allow from <ip> to any port 8000`).
- Set `VLLM_API_KEY` and put the same value in the tenant record's future
  credential field — until then, the firewall IS the auth. Do both eventually.
- RunPod: terminate pods, keep only the network volume (stopped-pod volume
  disks bill at 2×). Health-check before handing a Tier-2 session URL over.

## Tier presets
| Tier | GPU | MODEL_ID (example) | MAX_MODEL_LEN |
|---|---|---|---|
| 32k standard | 24 GB (4090/L4) | Qwen/Qwen2.5-14B-Instruct-AWQ | 32768 |
| 128k extended | 80 GB (A100/H100) | Qwen/Qwen2.5-32B-Instruct-AWQ | 131072 |
