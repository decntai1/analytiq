"""
Billing — Stripe subscriptions wired to the plans/credits system.

Feature-flagged: without STRIPE_SECRET_KEY every endpoint answers 503 and the
UI hides upgrade buttons (GET /billing/config says so). Plan changes flow ONLY
through the signature-verified webhook — the client is never trusted to set a
plan. Uses the shared auth.store() tenant singleton so upgrades are live
immediately, no restart.

Env: STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_PUBLISHABLE_KEY,
     STRIPE_PRICE_ANALYST / STRIPE_PRICE_TEAM / STRIPE_PRICE_BUSINESS,
     PUBLIC_URL (checkout return address).
"""
from __future__ import annotations

import dataclasses
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api import auth
from core.tenancy import Tenant

router = APIRouter()

SECRET = os.getenv("STRIPE_SECRET_KEY", "")
WH_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
PUB_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
PUBLIC_URL = os.getenv("PUBLIC_URL", "http://localhost:8000")
PRICES = {p: os.getenv(f"STRIPE_PRICE_{p.upper()}", "")
          for p in ("analyst", "team", "business")}


def _stripe():
    if not SECRET:
        raise HTTPException(503, "Billing is not configured on this deployment.")
    import stripe
    stripe.api_key = SECRET
    return stripe


class Checkout(BaseModel):
    plan: str


@router.get("/billing/config")
def config_():
    return {"configured": bool(SECRET and WH_SECRET),
            "publishable_key": PUB_KEY,
            "plans": [p for p, pid in PRICES.items() if pid]}


@router.post("/billing/checkout")
def checkout(body: Checkout, request: Request,
             tenant: Tenant | None = Depends(auth.resolve_tenant)):
    stripe = _stripe()
    user = auth.resolve_user(request)
    if not user:
        raise HTTPException(401, "Sign in to upgrade.")
    price = PRICES.get(body.plan, "")
    if not price:
        raise HTTPException(400, f"Unknown or unconfigured plan {body.plan!r}.")
    t = auth.store().by_id(user.tenant_id)
    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price, "quantity": 1}],
        success_url=f"{PUBLIC_URL}/app?billing=success",
        cancel_url=f"{PUBLIC_URL}/app?billing=cancelled",
        customer_email=user.email,
        metadata={"tenant_id": t.tenant_id, "plan": body.plan},
        subscription_data={"metadata": {"tenant_id": t.tenant_id, "plan": body.plan}},
    )
    return {"url": session.url}


@router.post("/billing/portal")
def portal(request: Request, tenant: Tenant | None = Depends(auth.resolve_tenant)):
    stripe = _stripe()
    user = auth.resolve_user(request)
    if not user:
        raise HTTPException(401, "Sign in first.")
    t = auth.store().by_id(user.tenant_id)
    if not getattr(t, "stripe_customer_id", ""):
        raise HTTPException(400, "No active subscription for this workspace.")
    s = stripe.billing_portal.Session.create(customer=t.stripe_customer_id,
                                             return_url=f"{PUBLIC_URL}/app")
    return {"url": s.url}


def _set_plan(tenant_id: str, plan: str, customer_id: str | None = None) -> bool:
    t = auth.store().by_id(tenant_id)
    if not t:
        return False
    fields = {"plan": plan}
    if customer_id is not None:
        fields["stripe_customer_id"] = customer_id
    auth.store().update(dataclasses.replace(t, **fields))
    return True


@router.post("/billing/webhook")
async def webhook(request: Request):
    """The ONLY writer of plan changes. Signature-verified; unverifiable -> 400."""
    if not (SECRET and WH_SECRET):
        raise HTTPException(503, "Billing is not configured on this deployment.")
    import json as _json

    from stripe import WebhookSignature
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        WebhookSignature.verify_header(payload.decode("utf-8"), sig, WH_SECRET, 300)
    except Exception:
        raise HTTPException(400, "Invalid signature.")
    try:
        event = _json.loads(payload)
    except Exception:
        raise HTTPException(400, "Invalid payload.")
    typ, obj = event["type"], event["data"]["object"]

    if typ == "checkout.session.completed":
        meta = obj.get("metadata") or {}
        ok = _set_plan(meta.get("tenant_id", ""), meta.get("plan", "free"),
                       obj.get("customer"))
        return {"ok": ok, "applied": typ}
    if typ in ("customer.subscription.deleted",):
        meta = obj.get("metadata") or {}
        tid = meta.get("tenant_id", "")
        if not tid:  # fall back to customer-id lookup
            cust = obj.get("customer")
            for t in auth.store().all():
                if getattr(t, "stripe_customer_id", "") == cust:
                    tid = t.tenant_id
                    break
        ok = _set_plan(tid, "free") if tid else False
        return {"ok": ok, "applied": typ}
    return {"ok": True, "ignored": typ}
