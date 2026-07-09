"""Clean-room battery — run from the extracted FINAL tarball root.
Covers every tested claim: imports, eval grid, single-tenant demo flow,
accounts/tiers/credits/memory/chats/deck, MT isolation, pages."""
import importlib, json, os, subprocess, sys, threading, zipfile

# runnable from repo root as `python3 scripts/cleanroom_battery.py`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.update(EMBEDDING_MODE="test", MULTI_TENANT="1", ADMIN_TOKEN="sec",
                  DEFAULT_MODEL="stub")

# 1) import sweep
mods = ["config","core.llm","core.embeddings","core.router","core.tools","core.runtime",
        "core.inference","core.tenancy","core.tenant_runtime","core.orchestrator",
        "core.deck_planner","core.accounts","connectors.base","connectors.sql",
        "connectors.duckdb_conn","connectors.multi","connectors.factory",
        "index.vectorstore","index.schema_index","index.doc_index","viz.spec",
        "viz.render_vegalite","viz.presentation","viz.raster","api.ingest","api.auth",
        "api.routes_accounts","api.app","eval.score","scripts.seed_demo"]
for m in mods: importlib.import_module(m)
print(f"[1] imports OK ({len(mods)} modules)")

from fastapi.testclient import TestClient
from api.app import app
c = TestClient(app)

# 2) pages
for p in ("/", "/login", "/app", "/health", "/models"):
    assert c.get(p).status_code == 200, p
print("[2] pages OK (landing/login/app/health/models)")

# 3) accounts: register -> logout -> login roundtrip
r = c.post("/auth/register", json={"email":"anna@x.io","password":"secret123"})
assert r.status_code == 200 and r.json()["plan"]["name"] == "free"
c.post("/auth/logout")
assert c.get("/auth/me").status_code == 401
r = c.post("/auth/login", json={"email":"anna@x.io","password":"secret123"})
assert r.status_code == 200
assert c.post("/auth/login", json={"email":"anna@x.io","password":"WRONG"}).status_code == 401
print("[3] register/logout/login roundtrip OK, bad password 401")

# 4) upload + ask + chart + persistence + title
csv = "region,orders\nEU,120\nUS,95\nAPAC,70\n"
assert c.post("/upload", files={"file":("regional_orders.csv",csv,"text/csv")}).json()["ok"]
cid = c.post("/chats").json()["conv_id"]
d = c.post("/ask", json={"question":"bar chart of regional_orders","model":"stub",
                         "conversation_id":cid}).json()
assert d["credits_remaining"] == 14 and len(d["charts"]) == 1
assert isinstance(d["plan"], dict) and d["plan"]["arm"] == "structured" and d["tier"] == "free"
msgs = c.get(f"/chats/{cid}").json()["messages"]
assert [m["role"] for m in msgs] == ["user","assistant"] and msgs[1]["charts"]
title = c.get("/chats").json()["conversations"][0]["title"]
assert title.startswith("bar chart of regional_orders"), title
print("[4] ask: credits/chart/plan-dict/tier OK · chat persisted · title =", repr(title[:32]))

# 5) free credit exhaustion -> 402
for _ in range(14):
    c.post("/ask", json={"question":"top regional_orders","model":"stub","conversation_id":cid})
assert c.post("/ask", json={"question":"x","model":"stub"}).status_code == 402
print("[5] free plan 402 gate OK")

# 6) company: invite join, shared workspace, concurrency, isolation
inv = c.post("/admin/tenants", json={"name":"Acme","plan":"business"},
             headers={"X-Admin-Token":"sec"}).json()["invite_code"]
assert c.post("/admin/tenants", json={"name":"Nope"}).status_code == 403
b, e = TestClient(app), TestClient(app)
rb = b.post("/auth/register", json={"email":"b@acme.hu","password":"secret123","invite_code":inv})
re_ = e.post("/auth/register", json={"email":"e@acme.hu","password":"secret123","invite_code":inv})
assert rb.json()["workspace"]["tenant_id"] == re_.json()["workspace"]["tenant_id"]
b.post("/upload", files={"file":("acme.csv","m,v\n1,10\n2,20\n","text/csv")})
res = {}
def go(cl, k): res[k] = cl.post("/ask", json={"question":"line chart of acme","model":"stub"}).status_code
ts = [threading.Thread(target=go, args=a) for a in ((b,"b"),(e,"e"))]
[t.start() for t in ts]; [t.join() for t in ts]
assert res == {"b":200,"e":200}
tb = e.post("/ask", json={"question":"top acme","model":"stub"}).json()["tables_retrieved"]
assert "acme" in tb  # employee sees the shared upload
print("[6] company invite/shared-workspace/concurrent asks/admin-gate OK")

# 7) memory: injected for paid, ordered correctly (unit-level capture)
import core.orchestrator as om
from core.llm import LLMResponse
cap = {}
class Cap:
    def chat(self, messages, tools=None):
        cap["roles"] = [m["role"] for m in messages]; return LLMResponse("ok", [])
om.get_provider = lambda name=None, spec_override=None: Cap()
from core.tenant_runtime import TenantRuntime
TenantRuntime().get(None).orchestrator().ask(
    "follow-up", history=[{"role":"user","content":"q1"},{"role":"assistant","content":"a1"}])
assert cap["roles"][:4] == ["system","user","assistant","user"]
importlib.reload(om)
print("[7] plan-gated memory injection order OK")

# 8) dedicated vLLM endpoint resolution
from api.app import _dedicated_spec
from core.tenancy import Tenant
from core.llm import get_provider
sp = _dedicated_spec(Tenant("tX","X","k", llm_base_url="http://10.0.0.5:8000/v1",
                            llm_model_id="qwen2.5-14b"))
assert str(get_provider(spec_override=sp)._client.base_url).startswith("http://10.0.0.5:8000")
print("[8] dedicated company endpoint resolves OK")

# 9) selection deck: business 200 + real pptx, free 403
spec = {"$schema":"https://vega.github.io/schema/vega-lite/v5.json",
        "data":{"values":[{"x":"EU","y":120},{"x":"US","y":95}]},
        "mark":{"type":"bar"},
        "encoding":{"x":{"field":"x","type":"nominal"},"y":{"field":"y","type":"quantitative"}}}
r = b.post("/presentation/from_selection", json={"title":"Q4","items":[
    {"title":"Orders","answer":"EU leads.","chart":spec,"sql":["SELECT 1"]},
    {"title":"Notes","answer":"EU strong\nUS stable"}]})
assert r.status_code == 200 and r.content[:2] == b"PK" and r.headers["x-deck-slides"] == "4"
open("/tmp/cr_deck.pptx","wb").write(r.content)
n = len([x for x in zipfile.ZipFile("/tmp/cr_deck.pptx").namelist()
         if x.startswith("ppt/slides/slide")])
assert n == 4
assert c.post("/presentation/from_selection",
              json={"title":"x","items":[{"title":"t","answer":"a"}]}).status_code == 403
print(f"[9] selection deck OK ({n} slides in pptx) · free plan 403")


# ---- [10] profile, credits & pricing surface --------------------------------
c10 = TestClient(app)
c10.post("/auth/register", json={"email": "pf@x.io", "password": "oldpass123"})
me = c10.get("/auth/me").json()
assert me["plan"]["credits_remaining"] == me["plan"]["credits_month"] - me["plan"]["credits_used"]
assert len(me.get("plans_catalog", [])) == 3 and any("29" in p["price"] for p in me["plans_catalog"])
assert c10.post("/auth/change_password", json={"current": "WRONG", "new": "newpass123"}).status_code == 400
assert c10.post("/auth/change_password", json={"current": "oldpass123", "new": "short"}).status_code == 400
assert c10.post("/auth/change_password", json={"current": "oldpass123", "new": "newpass123"}).json()["ok"] is True
fresh = TestClient(app)
assert fresh.post("/auth/login", json={"email": "pf@x.io", "password": "oldpass123"}).status_code == 401
assert fresh.post("/auth/login", json={"email": "pf@x.io", "password": "newpass123"}).status_code == 200
land = c10.get("/").text
assert "\u20ac29" in land or "€29" in land
assert "€940" in land and "Analyst" in land and "On-prem" in land
idx = open(os.path.join("api", "static", "index.html"), encoding="utf-8").read()
assert "credChip" in idx and "profileDrawer" in idx and "change_password" in idx
print("[10] profile drawer / credits chip / password change / priced landing OK")

print("\nCLEANROOM: ALL 10 SECTIONS PASS")
