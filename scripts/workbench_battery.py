"""Workbench acceptance battery — invariants + every CAPABILITY op + HTTP flow.
Run from repo root: python3 scripts/workbench_battery.py   (isolated; zero prod writes)"""
import hashlib, json, os, shutil, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TMP = tempfile.mkdtemp(prefix="wb_battery_")
os.chdir(TMP)  # everything relative lands here, never in the repo
os.environ.update(EMBEDDING_MODE="test", MULTI_TENANT="0", DEFAULT_MODEL="stub",
                  WORKBENCH_DIR=os.path.join(TMP, "workbench"),
                  UPLOAD_DIR=os.path.join(TMP, "uploads"),
                  DATA_SOURCE="upload", ENABLE_UPLOADS="1")

FAILS = []
def chk(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + (("  -> " + str(d)) if d and not c else ""))
    if not c: FAILS.append(n)

DIRTY = ("name,age,city,joined,score\n"
         " Alice ,31, Budapest ,2024-01-05,10\n"
         "bob,NA,Vienna,2024-02-11,12\n"
         "bob,NA,Vienna,2024-02-11,12\n"
         "CARLA,29,,2024-03-02,x\n"
         "dave,40,Praha,-,9\n")

# ---------- core: session, invariants, profile ------------------------------
from core.workbench import SessionStore, WorkbenchSession, CAPABILITY  # noqa: E402
from connectors.duckdb_conn import DuckDBConnector  # noqa: E402

os.makedirs("uploads")
src = os.path.join(TMP, "uploads", "dirty.csv")
open(src, "w").write(DIRTY)
src_hash = hashlib.sha256(open(src, "rb").read()).hexdigest()

class Ctx:  # minimal ctx: upload duck + connector, like TenantContext
    def __init__(self, d): self._duck = DuckDBConnector(data_dir=d)
    def upload_duck(self): return self._duck
    @property
    def connector(self): return self._duck

ctx = Ctx(os.path.join(TMP, "uploads"))
store = SessionStore()
ses = store.create_from_view("default", "dirty", ctx)
chk("S1 session created, 5 rows", ses.row_count() == 5, ses.row_count())
chk("S2 source hash recorded", ses.meta.get("source_sha256") == src_hash)

prof = ses.profile()
byc = {c["column"]: c for c in prof["columns"]}
chk("P1 whitespace detected (name)", byc["name"]["whitespace_rows"] >= 1)
chk("P2 dup rows detected", prof["duplicate_rows"] == 1, prof["duplicate_rows"])
chk("P3 mixed-type flagged (score: 4 nums + 'x')", byc["score"]["mixed_type"] is True)
chk("P4 date-parse rate on joined", byc["joined"]["date_parse_pct"] >= 60)

# ---------- validation gates -------------------------------------------------
v, r = ses.validate_plan([{"op": "run_python", "args": {}}])
chk("V1 unknown op rejected", not v and r and "unknown" in r[0]["reason"])
v, r = ses.validate_plan([{"op": "trim_whitespace", "args": {"columns": ["../../etc/passwd"]}}])
chk("V2 path-smuggled column rejected", not v)
v, r = ses.validate_plan([{"op": "normalize_case", "args": {"column": "ghost", "mode": "upper"}}])
chk("V3 nonexistent column rejected", not v)
v, r = ses.validate_plan([{"op": "regex_replace", "args": {"column": "city", "pattern": "([", "replacement": ""}}])
chk("V4 invalid regex rejected", not v)
v, r = ses.validate_plan([{"op": "fill_missing", "args": {"column": "city", "strategy": "mean"}}])
chk("V5 mean on text rejected", not v)

# ---------- ops: preview == apply, work untouched by preview -----------------
plan = [
    {"op": "trim_whitespace", "args": {}},
    {"op": "normalize_nulls", "args": {}},
    {"op": "normalize_case", "args": {"column": "name", "mode": "lower"}},
    {"op": "dedupe_rows", "args": {}},
    {"op": "cast_column", "args": {"column": "score", "type": "int"}},
    {"op": "replace_values", "args": {"column": "city", "mapping": {"Praha": "Prague"}}},
    {"op": "regex_replace", "args": {"column": "city", "pattern": "Vien+a", "replacement": "Wien"}},
]
pv = ses.preview(plan)
chk("O1 preview clean (no rejects)", not pv["rejected"], pv["rejected"])
chk("O2 preview leaves work untouched", ses.row_count() == 5)
chk("O3 preview dedupe counted 1", next(x for x in pv["results"] if x["op"] == "dedupe_rows")["affected"] == 1)
ap = ses.apply(plan)
by = {x["op"]: x for x in ap["results"]}
chk("O4 apply == preview per op", all(
    by[x["op"]]["affected"] == x["affected"] for x in pv["results"]),
    [(x["op"], x["affected"], by[x["op"]]["affected"]) for x in pv["results"]])
chk("O5 rows after dedupe", ses.row_count() == 4)
name_vals = [x[0] for x in ses.con.execute("SELECT name FROM work ORDER BY name").fetchall()]
chk("O6 trim+lower applied", name_vals == ["alice", "bob", "carla", "dave"], name_vals)
chk("O7 'NA' -> NULL", ses.con.execute("SELECT COUNT(*) FROM work WHERE age IS NULL").fetchone()[0] == 1)
chk("O8 cast int: 'x' -> NULL, reported", by["cast_column"]["affected"] == 1 and
    ses.con.execute("SELECT COUNT(*) FROM work WHERE score IS NULL").fetchone()[0] == 1)
chk("O9 replace + regex", ses.con.execute(
    "SELECT COUNT(*) FROM work WHERE city IN ('Prague','Wien')").fetchone()[0] == 2)
# remaining ops individually
ap2 = ses.apply([{"op": "fill_missing", "args": {"column": "score", "strategy": "median"}},
                 {"op": "rename_column", "args": {"column": "joined", "new_name": "join date"}},
                 {"op": "drop_rows_where", "args": {"column": "city", "condition": "is_null"}},
                 {"op": "drop_columns", "args": {"columns": ["age"]}}])
chk("O10 fill median filled the NULL", ses.con.execute(
    "SELECT COUNT(*) FROM work WHERE score IS NULL").fetchone()[0] == 0)
chk("O11 rename sanitized", "join_date" in ses.columns() and "joined" not in ses.columns())
chk("O12 drop_rows_where + drop_columns", ses.row_count() == 3 and "age" not in ses.columns())
chk("R1 recipe carries every applied op with SQL", len(ses.meta["recipe"]) == 11 and
    all(x.get("sql") for x in ses.meta["recipe"]))

# ---------- recipe library: save + re-apply with skip reporting ---------------
rec = store.save_recipe("default", ses.sid, "Monthly clean")
chk("L1 recipe saved with all 11 ops", len(rec["ops"]) == 11)
open(os.path.join(TMP, "uploads", "nextmonth.csv"), "w").write(
    "name,age,score\n  Eve ,NA,7\n  Eve ,NA,7\nfrank,33,x\n")  # no city/joined cols
ctx2 = Ctx(os.path.join(TMP, "uploads"))
ses2 = store.create_from_view("default", "nextmonth", ctx2)
res = store.apply_recipe("default", ses2.sid, rec["id"])
ops_ran = [r["op"] for r in res["results"]]
chk("L2 recipe re-applies fitting ops", "trim_whitespace" in ops_ran and "dedupe_rows" in ops_ran)
chk("L3 misfit ops SKIPPED with reasons (city/joined gone)",
    len(res["skipped"]) >= 3 and all(x["reason"] for x in res["skipped"]), res["skipped"])
chk("L4 recipe outcome on new file", ses2.row_count() == 2 and
    ses2.con.execute("SELECT name FROM work ORDER BY name").fetchall()[0][0] == "eve")
store.delete("default", ses2.sid)

# ---------- reset, download, source immutability -----------------------------
ses.reset()
chk("R2 reset -> pristine (5 rows, recipe cleared)", ses.row_count() == 5 and ses.meta["recipe"] == [])
csv = ses.export_csv()
chk("D1 download exists with header", open(csv).readline().startswith("name,"))
chk("I1 SOURCE byte-identical after full cycle",
    hashlib.sha256(open(src, "rb").read()).hexdigest() == src_hash)

# ---------- propose: validated, tool-less; path escape ------------------------
import core.workbench as wb  # noqa: E402
class FakePlanner:
    def chat(self, messages, tools=None):
        assert tools is None, "workbench LLM must get NO tools"
        from core.llm import LLMResponse
        return LLMResponse(json.dumps([
            {"op": "trim_whitespace", "args": {}, "reason": "ws rows in profile"},
            {"op": "drop_table", "args": {"table": "work"}, "reason": "evil"},
            {"op": "normalize_case", "args": {"column": "ghost", "mode": "upper"}, "reason": "bad col"},
        ]), [])
import core.llm as llm_mod  # noqa: E402
_orig = llm_mod.get_provider
llm_mod.get_provider = lambda m=None, **k: FakePlanner()
try:
    pr = ses.propose("clean it")
finally:
    llm_mod.get_provider = _orig
chk("A1 propose keeps only valid ops", [o["op"] for o in pr["plan"]] == ["trim_whitespace"])
chk("A2 invalid ops rejected w/ reasons", len(pr["rejected"]) == 2)
try:
    store.get("default", "../../etc"); chk("E1 sid escape rejected", False)
except (ValueError, KeyError):
    chk("E1 sid escape rejected", True)

# ---------- HTTP flow (single-tenant, stub-safe propose) ----------------------
os.environ["UPLOAD_DIR"] = os.path.join(TMP, "uploads")
import importlib, config  # noqa: E402
importlib.reload(config)
from fastapi.testclient import TestClient  # noqa: E402
from api.app import app  # noqa: E402
c = TestClient(app)
chk("H1 /workbench page serves", c.get("/workbench").status_code == 200 and
    "Workbench" in c.get("/workbench").text)
r = c.post("/workbench/api/sessions", json={"view": "dirty"})
chk("H2 create via API", r.status_code == 200, r.text[:120])
sid = r.json()["sid"]
chk("H3 profile via API", c.get(f"/workbench/api/sessions/{sid}/profile").json()["profile"]["rows"] == 5)
r = c.post(f"/workbench/api/sessions/{sid}/propose", json={"instruction": "clean", "model": "stub"})
chk("H4 stub propose degrades gracefully (no 500)", r.status_code == 200 and "note" in r.json())
r = c.post(f"/workbench/api/sessions/{sid}/apply", json={"ops": [{"op": "dedupe_rows", "args": {}}]})
chk("H5 apply via API", r.json()["rows"] == 4)
r = c.get(f"/workbench/api/sessions/{sid}/download")
chk("H6 download via API", r.status_code == 200 and r.content.startswith(b"name,"))
chk("H7 delete via API", c.delete(f"/workbench/api/sessions/{sid}").json()["ok"] is True and
    c.get(f"/workbench/api/sessions/{sid}/profile").status_code == 404)

shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{'WORKBENCH BATTERY: ALL PASS' if not FAILS else 'FAILURES: ' + ', '.join(FAILS)}")
sys.exit(1 if FAILS else 0)
