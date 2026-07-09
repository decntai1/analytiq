"""Billing acceptance battery — offline: checkout is monkeypatched (no egress),
but webhook signatures are REAL (computed with Stripe's scheme and verified by
the stripe library). Run from repo root; isolated tempdir, zero prod writes."""
import hashlib, hmac, json, os, shutil, sys, tempfile, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TMP = tempfile.mkdtemp(prefix="bill_battery_")
os.chdir(TMP)
WH = "whsec_testsecret123"
os.environ.update(EMBEDDING_MODE="test", MULTI_TENANT="1", ADMIN_TOKEN="sec",
                  DEFAULT_MODEL="stub", STRIPE_SECRET_KEY="sk_test_offline",
                  STRIPE_WEBHOOK_SECRET=WH, STRIPE_PUBLISHABLE_KEY="pk_test_x",
                  STRIPE_PRICE_ANALYST="price_analyst_x", STRIPE_PRICE_BUSINESS="price_biz_x",
                  PUBLIC_URL="https://demo.test")

FAILS = []
def chk(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + (("  -> " + str(d)) if d and not c else ""))
    if not c: FAILS.append(n)

def sig(payload: bytes, secret: str = WH, t: int | None = None) -> str:
    t = t or int(time.time())
    mac = hmac.new(secret.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={t},v1={mac}"

from fastapi.testclient import TestClient  # noqa: E402
from api.app import app  # noqa: E402
from api import auth  # noqa: E402
import stripe  # noqa: E402

c = TestClient(app)
r = c.post("/auth/register", json={"email": "ceo@corp.io", "password": "secret123"})
tid = None
me = c.get("/auth/me").json()
tid = me["tenant"]["tenant_id"] if "tenant" in me else me.get("tenant_id")
if not tid:  # fall back: only tenant in the store
    tid = auth.store().all()[0].tenant_id

chk("B1 config reports configured + plans", c.get("/billing/config").json()["configured"] is True and
    "analyst" in c.get("/billing/config").json()["plans"])

# checkout: stripe API is unreachable here -> monkeypatch create, assert wiring
captured = {}
class _FakeSession:
    url = "https://checkout.stripe.test/cs_123"
def fake_create(**kw):
    captured.update(kw)
    return _FakeSession()
orig = stripe.checkout.Session.create
stripe.checkout.Session.create = staticmethod(fake_create)
try:
    r = c.post("/billing/checkout", json={"plan": "business"})
finally:
    stripe.checkout.Session.create = orig
chk("B2 checkout returns session url", r.status_code == 200 and "checkout.stripe.test" in r.json()["url"], r.text[:120])
chk("B3 checkout carries tenant metadata + price", captured.get("metadata", {}).get("tenant_id") == tid and
    captured["line_items"][0]["price"] == "price_biz_x")
chk("B4 unknown plan -> 400", c.post("/billing/checkout", json={"plan": "vip"}).status_code == 400)

# webhook with a REAL signature -> plan flips on the LIVE shared store
evt = json.dumps({"type": "checkout.session.completed", "data": {"object": {
    "customer": "cus_TEST1", "metadata": {"tenant_id": tid, "plan": "business"}}}}).encode()
r = c.post("/billing/webhook", content=evt,
           headers={"stripe-signature": sig(evt), "content-type": "application/json"})
chk("B5 signed webhook accepted + applied", r.status_code == 200 and r.json()["ok"] is True, r.text[:120])
t = auth.store().by_id(tid)
chk("B6 plan upgraded LIVE (no restart)", t.plan == "business" and t.stripe_customer_id == "cus_TEST1",
    (t.plan, t.stripe_customer_id))
chk("B7 /auth/me reflects the paid plan", c.get("/auth/me").json()["plan"]["name"] == "business")

# tampered payload -> 400, plan unchanged
bad = evt.replace(b"business", b"analyst!!")
r = c.post("/billing/webhook", content=bad, headers={"stripe-signature": sig(evt)})
chk("B8 bad signature rejected", r.status_code == 400)
chk("B9 plan unchanged after tamper", auth.store().by_id(tid).plan == "business")

# subscription cancelled -> downgrade to free (customer-id fallback path)
evt2 = json.dumps({"type": "customer.subscription.deleted", "data": {"object": {
    "customer": "cus_TEST1", "metadata": {}}}}).encode()
r = c.post("/billing/webhook", content=evt2, headers={"stripe-signature": sig(evt2)})
chk("B10 cancellation downgrades to free", r.json()["ok"] is True and
    auth.store().by_id(tid).plan == "free")
chk("B11 irrelevant events ignored ok", c.post("/billing/webhook",
    content=json.dumps({"type": "invoice.paid", "data": {"object": {}}}).encode(),
    headers={"stripe-signature": sig(json.dumps({"type": "invoice.paid", "data": {"object": {}}}).encode())}
    ).json().get("ignored") == "invoice.paid")

shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{'BILLING BATTERY: ALL PASS' if not FAILS else 'FAILURES: ' + ', '.join(FAILS)}")
sys.exit(1 if FAILS else 0)
