"""Dashboard acceptance battery — run from repo root; isolated tempdir, zero prod writes."""
import json, os, shutil, sys, tempfile, zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TMP = tempfile.mkdtemp(prefix="dash_battery_")
os.chdir(TMP)
import importlib.util
HAS_ACCOUNTS = importlib.util.find_spec("core.accounts") is not None
os.environ.update(EMBEDDING_MODE="test", MULTI_TENANT="1" if HAS_ACCOUNTS else "0", ADMIN_TOKEN="sec",
                  DEFAULT_MODEL="stub", DASHBOARD_DIR=os.path.join(TMP, "dashboards"),
                  WORKBENCH_DIR=os.path.join(TMP, "workbench"))

FAILS = []
def chk(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + (("  -> " + str(d)) if d and not c else ""))
    if not c: FAILS.append(n)

from fastapi.testclient import TestClient  # noqa: E402
from api.app import app  # noqa: E402
c = TestClient(app)
if HAS_ACCOUNTS:
    c.post("/auth/register", json={"email": "a@x.io", "password": "secret123"})
c.post("/upload", files={"file": ("sales.csv", "region,amt\nEU,10\nUS,20\n", "text/csv")})

chk("D1 /dashboard page serves", c.get("/dashboard").status_code == 200 and
    "Dashboard" in c.get("/dashboard").text)
b = c.post("/dashboard/api/boards", json={"name": "Ops"}).json()

# pin a chart tile exactly as the chat's 📌 does
spec = {"$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "data": {"values": [{"region": "EU", "amt": 10}]}, "mark": {"type": "bar"},
        "encoding": {"x": {"field": "region", "type": "nominal"},
                     "y": {"field": "amt", "type": "quantitative"}}}
t = c.post("/dashboard/api/tiles", json={
    "board_id": b["id"], "title": "Sales by region", "question": "sales by region?",
    "sql": 'SELECT region, SUM(amt) AS amt FROM sales GROUP BY 1 ORDER BY 1', "spec": spec}).json()
chk("D2 pin stores tile with LEAN spec", t["spec"]["data"]["values"] == [])

r = c.post(f"/dashboard/api/tiles/{t['id']}/refresh").json()
chk("D3 refresh re-binds fresh rows", r["row_count"] == 2 and
    len(r["spec"]["data"]["values"]) == 2, r.get("error"))

# THE MONITORING PROOF: data changes underneath -> same tile shows the change
c.post("/upload", files={"file": ("sales.csv", "region,amt\nEU,10\nUS,20\nAPAC,30\n", "text/csv")})
r2 = c.post(f"/dashboard/api/tiles/{t['id']}/refresh").json()
chk("D4 MONITORING: refresh reflects changed data (3 rows, no LLM)",
    r2["row_count"] == 3, r2.get("error"))

# edited SQL runs through the read-only guard: a write must be REJECTED
c.patch(f"/dashboard/api/tiles/{t['id']}", json={"sql": "DELETE FROM sales"})
r3 = c.post(f"/dashboard/api/tiles/{t['id']}/refresh").json()
chk("D5 write-SQL rejected by guard on refresh", "error" in r3 and "query failed" in r3["error"])
still = c.post("/dashboard/api/tiles", json={"board_id": b["id"], "title": "probe",
    "question": "", "sql": "SELECT COUNT(*) AS n FROM sales", "spec": None}).json()
rp = c.post(f"/dashboard/api/tiles/{still['id']}/refresh").json()
chk("D6 data untouched by the rejected write", rp["rows"][0]["n"] == 3, rp)
chk("D7 spec-less tile returns table payload", "columns" in rp and rp["columns"] == ["n"])

# restore a good query + export the board as pptx
c.patch(f"/dashboard/api/tiles/{t['id']}", json={"sql": 'SELECT region, SUM(amt) AS amt FROM sales GROUP BY 1'})
r = c.get(f"/dashboard/api/boards/{b['id']}/export.pptx")
ok_pptx = r.status_code == 200 and r.content[:2] == b"PK"
chk("D8 board -> pptx export", ok_pptx, r.status_code)
if ok_pptx:
    open("/tmp/dash.pptx", "wb").write(r.content)
    n = len([x for x in zipfile.ZipFile("/tmp/dash.pptx").namelist() if x.startswith("ppt/slides/slide")])
    chk("D9 deck has title+2 tiles+appendix", n == 4, n)

# tenant isolation: only meaningful where the accounts lineage exists
if HAS_ACCOUNTS:
    e = TestClient(app)
    e.post("/auth/register", json={"email": "b@y.io", "password": "secret123"})
    jb = e.get("/dashboard/api/boards").json()["boards"]
    chk("D10 tenant isolation (fresh default board, 0 tiles)",
        len(jb) == 1 and jb[0]["tiles"] == 0 and jb[0]["id"] != b["id"])
else:
    print("SKIP D10 tenant isolation (single-tenant lineage)")

chk("D11 delete tile + board", c.delete(f"/dashboard/api/tiles/{t['id']}").json()["ok"] and
    c.delete(f"/dashboard/api/boards/{b['id']}").json()["ok"] and
    c.get(f"/dashboard/api/boards/{b['id']}/tiles").json()["tiles"] == [])

shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{'DASHBOARD BATTERY: ALL PASS' if not FAILS else 'FAILURES: ' + ', '.join(FAILS)}")
sys.exit(1 if FAILS else 0)
