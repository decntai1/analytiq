#!/usr/bin/env python3
"""
verify_paid_models.py — ONE-TIME build-time acceptance for the model selector.

NOT part of the recurring gate (smoke_live.py). This proves every model offered
in the picker actually answers a real question end-to-end — including the PAID
models a Free smoke account can't reach. To do that it needs a paid context, so
it uses ADMIN_TOKEN to mint a throwaway Business tenant, /ask each model through
the real app with a known CSV, and assert answer + sql_log + the correct number.

    ADMIN_TOKEN=... python scripts/verify_paid_models.py --base-url https://analytiq.dcentai.tech

Why admin is OK here but NOT in smoke_live.py: this is a manual acceptance check
you run ONCE after building, not an automated gate hammering production. The
recurring smoke test stays admin-free.

Caveat: this tree has no delete-tenant endpoint, so the throwaway Business tenant
persists (no billing attached — harmless). Its id is printed for your records; a
DELETE /admin/tenants/{id} admin route would let this self-clean (follow-up).

Exit 0 iff all offered models pass.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid

DEFAULT_BASE = "https://analytiq.dcentai.tech"

# every model the picker can offer (registry name -> friendly label). North's
# total (120+150) = 270 requires real aggregation, so "270" in the answer is a
# strong correctness signal a row-echo can't fake.
# ministral-3:8b + qwen3-coder:480b RETIRED by Ollama Cloud 2026-07-15 — removed
# from the picker; re-add here only after they (or a replacement) pass live.
MODELS = [("gpt-oss-20b", "GPT-OSS 20B (Free default)"),
          ("ollama-cloud", "GPT-OSS 120B")]
CSV = ("region,revenue\nNorth,120\nNorth,150\nSouth,90\n"
       "South,110\nEast,70\nWest,140\n").encode()
EXPECT = "270"   # North total


def _req(url, method="GET", headers=None, data=None, timeout=180):
    r = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        resp = urllib.request.urlopen(r, timeout=timeout)
        return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _json(raw):
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="One-time end-to-end acceptance for the model picker.")
    ap.add_argument("--base-url", default=DEFAULT_BASE)
    args = ap.parse_args()
    base = args.base_url.rstrip("/")

    admin = os.environ.get("ADMIN_TOKEN")
    if not admin:
        print("ERROR: set ADMIN_TOKEN (this script needs it to mint a paid test tenant).")
        return 2

    print(f"\n== Paid-model acceptance → {base} ==\n")

    # 1. mint a throwaway Business tenant (has every model) --------------------
    name = f"verify-{uuid.uuid4().hex[:10]}"
    st, raw = _req(f"{base}/admin/tenants", "POST",
                   {"X-Admin-Token": admin, "Content-Type": "application/json"},
                   json.dumps({"name": name, "plan": "business",
                               "data_source": "upload", "enable_uploads": True}).encode())
    t = _json(raw) or {}
    api_key, tenant_id = t.get("api_key"), t.get("tenant_id")
    if st != 200 or not api_key:
        print(f"  FAILED to create tenant (HTTP {st}): {str(_json(raw))[:200]}")
        return 1
    print(f"  created Business tenant {tenant_id} (plan={t.get('plan')})")
    ah = {"X-API-Key": api_key}

    # 2. upload the known CSV -------------------------------------------------
    boundary = "----verify" + uuid.uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
            f"filename=\"sales.csv\"\r\nContent-Type: text/csv\r\n\r\n").encode() + CSV + \
           f"\r\n--{boundary}--\r\n".encode()
    st, raw = _req(f"{base}/upload", "POST",
                   {**ah, "Content-Type": f"multipart/form-data; boundary={boundary}"}, body)
    up = _json(raw) or {}
    view = up.get("table")
    if st != 200 or not view:
        print(f"  FAILED to upload CSV (HTTP {st}): {str(up)[:200]}")
        return 1
    print(f"  uploaded CSV as table '{view}'\n")

    # 3. /ask each offered model end-to-end -----------------------------------
    failures = 0
    for reg_name, label in MODELS:
        st, raw = _req(f"{base}/ask", "POST",
                       {**ah, "Content-Type": "application/json"},
                       json.dumps({"question": f"What is the total revenue by region in {view}?",
                                   "model": reg_name}).encode())
        d = _json(raw) or {}
        answer = (d.get("answer") or "")
        sql = d.get("sql_log") or []
        ok = st == 200 and bool(answer.strip()) and bool(sql) and EXPECT in answer
        mark = "\033[32mPASS\033[0m" if ok else "\033[31mFAIL\033[0m"
        if not ok:
            failures += 1
        detail = (f"answer_len={len(answer)}, sql={len(sql)}, has_{EXPECT}={EXPECT in answer}"
                  if st == 200 else f"HTTP {st}: {str(d)[:80]}")
        print(f"  [{mark}] {label:<28} ({reg_name}) — {detail}")

    print(f"\n  NOTE: throwaway tenant {tenant_id} persists (no delete-tenant endpoint). "
          f"Harmless (no billing); delete via a future DELETE /admin/tenants route.")
    total = len(MODELS)
    print(f"\n== {total - failures}/{total} models passed end-to-end ==")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
