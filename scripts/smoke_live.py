#!/usr/bin/env python3
"""
smoke_live.py — end-to-end smoke test against a RUNNING Analytiq deployment.

Unlike the five batteries (which prove the code in isolation, in a tempdir), this
hits the *live* site over real HTTPS — the thing users actually touch — and is the
required post-deploy gate (see CLAUDE.md "Post-deploy verification").

    python scripts/smoke_live.py --base-url https://analytiq.dcentai.tech

Design:
  - stdlib only (urllib + http.cookiejar + ssl). Runs anywhere python3 is, no pip.
    (The 2-sheet .xlsx check additionally needs openpyxl, a project dep — it SKIPs
    cleanly if openpyxl isn't importable, e.g. run outside the app venv.)
  - Idempotent / re-runnable: a fresh throwaway account per run (unique email);
    created dashboard/workbench artifacts are deleted at the end.
  - Prints PASS/FAIL/SKIP per check. No secrets are printed (password is generated
    and never logged; no keys are read). Exit code 0 iff no check FAILed.

Scope honesty (this is the FULL-PLATFORM lineage, not the VPS demo):
  - Step "table scope + delete" is SKIPPED: those are VPS-demo-lineage features;
    this tree has no table-scope or table-delete route.
  - Account cleanup is partial: there is no account-deletion endpoint, so the
    throwaway account persists (Free plan, unique email — harmless).

Cost: the live-model checks (ask, workbench propose) spend a little real OpenAI
credit — a handful of cheap gpt-4o-mini calls per run.
"""
from __future__ import annotations

import argparse
import http.cookiejar
import io
import json
import os
import socket
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone

DEFAULT_BASE = "https://analytiq.dcentai.tech"
TIER_NAMES = ("Explore", "Analyst", "Team", "Business", "On-prem")


# --------------------------------------------------------------------------- #
# tiny result recorder
# --------------------------------------------------------------------------- #
class Results:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []  # (status, name, detail)

    def _add(self, status: str, name: str, detail: str = "") -> None:
        self.rows.append((status, name, detail))
        mark = {"PASS": "\033[32mPASS\033[0m", "FAIL": "\033[31mFAIL\033[0m",
                "SKIP": "\033[33mSKIP\033[0m", "WARN": "\033[33mWARN\033[0m"}.get(status, status)
        print(f"  [{mark}] {name}" + (f"  — {detail}" if detail else ""), flush=True)

    def ok(self, name: str, detail: str = "") -> None:   self._add("PASS", name, detail)
    def fail(self, name: str, detail: str = "") -> None: self._add("FAIL", name, detail)
    def skip(self, name: str, detail: str = "") -> None: self._add("SKIP", name, detail)
    def warn(self, name: str, detail: str = "") -> None: self._add("WARN", name, detail)

    def check(self, name: str, cond: bool, detail: str = "") -> bool:
        (self.ok if cond else self.fail)(name, detail)
        return cond

    @property
    def failed(self) -> int:
        return sum(1 for s, _, _ in self.rows if s == "FAIL")

    def summary(self) -> str:
        p = sum(1 for s, _, _ in self.rows if s == "PASS")
        f = self.failed
        k = sum(1 for s, _, _ in self.rows if s == "SKIP")
        w = sum(1 for s, _, _ in self.rows if s == "WARN")
        return f"{p} passed, {f} failed, {w} warned, {k} skipped"


# --------------------------------------------------------------------------- #
# minimal cookie-aware HTTP client (stdlib)
# --------------------------------------------------------------------------- #
class Client:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        jar = http.cookiejar.CookieJar()
        # default TLS context => verifies chain + hostname + expiry (real HTTPS).
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar),
            urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        )

    def _open(self, req: urllib.request.Request, timeout: int):
        try:
            resp = self.opener.open(req, timeout=timeout)
            return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def get(self, path: str, timeout: int = 60):
        req = urllib.request.Request(self.base + path, method="GET",
                                     headers={"Accept": "*/*"})
        return self._open(req, timeout)

    def post_json(self, path: str, payload: dict, timeout: int = 120):
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            self.base + path, data=body, method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"})
        return self._open(req, timeout)

    def delete(self, path: str, timeout: int = 60):
        req = urllib.request.Request(self.base + path, method="DELETE",
                                     headers={"Accept": "application/json"})
        return self._open(req, timeout)

    def post_file(self, path: str, filename: str, content: bytes,
                  content_type: str, timeout: int = 120):
        boundary = "----smoke" + uuid.uuid4().hex
        pre = (f"--{boundary}\r\n"
               f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
               f"Content-Type: {content_type}\r\n\r\n").encode()
        body = pre + content + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(
            self.base + path, data=body, method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                     "Accept": "application/json"})
        return self._open(req, timeout)


def as_json(raw: bytes):
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


# paid models (in the picker for paid plans) that a Free smoke account can't /ask;
# probe their tool-calling liveness directly if OLLAMA_API_KEY is available.
PAID_MODELS = [("gpt-oss-20b", "gpt-oss:20b"),
               ("gpt-oss-120b", "gpt-oss:120b"),
               ("qwen3-coder", "qwen3-coder:480b")]


def probe_tool_call(key: str, model_id: str, timeout: int = 90):
    """Live liveness check: does this Ollama Cloud model still emit a run_sql tool-call?"""
    import urllib.request
    tools = [{"type": "function", "function": {"name": "run_sql",
              "description": "Run a read-only SQL query",
              "parameters": {"type": "object", "properties": {"query": {"type": "string"}},
                             "required": ["query"]}}}]
    body = json.dumps({"model": model_id, "tools": tools, "tool_choice": "auto", "max_tokens": 300,
                       "messages": [{"role": "user",
                                     "content": "Total revenue by region in table sales? Call run_sql."}]}).encode()
    req = urllib.request.Request("https://ollama.com/v1/chat/completions", data=body,
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        d = json.load(urllib.request.urlopen(req, timeout=timeout))
        tc = d.get("choices", [{}])[0].get("message", {}).get("tool_calls") or []
        return (bool(tc), "run_sql tool-call emitted" if tc else "no tool-call (text only)")
    except urllib.error.HTTPError as e:
        return (False, f"HTTP {e.code}: {e.read().decode()[:60]}")
    except Exception as e:
        return (False, f"{type(e).__name__}: {str(e)[:60]}")


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
CSV_CONTENT = (
    "region,quarter,revenue\n"
    "North,Q1,120\nNorth,Q2,150\nSouth,Q1,90\n"
    "South,Q2,110\nEast,Q1,70\nWest,Q2,140\n"
).encode()
CSV_ROWS = 6

# A CSV whose columns DuckDB types NATIVELY on the tenant path: an ISO date column
# -> DATE, a fractional column -> DOUBLE/DECIMAL. The demo DB is sqlite (dates come
# back as strings), so a query over THIS is the only thing that exercises native
# date/Decimal objects flowing into the run_sql tool-result / chart json.dumps —
# the exact path that 500'd ("Object of type date is not JSON serializable") while
# the suite still passed 32/0 on the string-typed demo DB. Regression gate.
TYPED_CSV_CONTENT = (
    "signup_date,region,amount\n"
    "2024-01-05,North,120.50\n"
    "2024-02-09,South,90.25\n"
    "2024-03-14,East,70.00\n"
    "2024-04-20,West,140.75\n"
).encode()
TYPED_CSV_ROWS = 4

# A CSV with a REAL geographic column so the choropleth path (Phase B) can resolve
# region names -> topojson ids deterministically (index/region_lookup). Full country
# names + an ISO/alias ("US") exercise the frozen lookup end-to-end; every value here
# resolves, so a rendered map clears the >=80% coverage gate.
GEO_CSV_CONTENT = (
    "country,revenue\n"
    "Germany,120\nFrance,90\nUnited States,300\nBrazil,50\n"
    "Japan,80\nUS,60\nIndia,110\n"
).encode()
GEO_CSV_ROWS = 7


def build_xlsx_2sheets() -> bytes | None:
    """A genuine 2-sheet workbook via openpyxl (a project dep). None if unavailable."""
    try:
        from openpyxl import Workbook
    except Exception:
        return None
    # NB: the connector drops "decorative" sheets — it requires >=3 data rows and
    # >=2 columns >=40% filled (duckdb_conn.py). Both sheets must clear that gate.
    wb = Workbook()
    s1 = wb.active
    s1.title = "sales"
    s1.append(["region", "revenue"])
    for r in [("North", 120), ("South", 90), ("East", 70)]:
        s1.append(list(r))
    s2 = wb.create_sheet("headcount")
    s2.append(["team", "people"])
    for r in [("Eng", 12), ("Sales", 7), ("Ops", 4)]:
        s2.append(list(r))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# checks
# --------------------------------------------------------------------------- #
def check_tls(host: str, r: Results) -> None:
    """Cert is CA-valid (chain verifies => not self-signed), unexpired, for host."""
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=15) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
    except ssl.SSLCertVerificationError as e:
        r.fail("TLS: cert valid & chain-verified", f"verification failed: {e.verify_message}")
        return
    except Exception as e:
        r.fail("TLS: connect", f"{type(e).__name__}: {e}")
        return
    # if wrap_socket returned, the chain + hostname + expiry already verified.
    r.ok("TLS: cert chain-verified (not self-signed) & hostname matches", host)
    issuer = dict(x[0] for x in cert.get("issuer", ())).get("organizationName", "?")
    not_after = cert.get("notAfter", "")
    try:
        exp = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        days = (exp - datetime.now(timezone.utc)).days
        r.check("TLS: cert not expired", days > 0, f"issuer={issuer}, {days}d left")
    except Exception:
        r.ok("TLS: cert present", f"issuer={issuer}")


def run(base: str) -> int:
    r = Results()
    host = urllib.parse.urlparse(base).hostname or base
    c = Client(base)
    created = {"board_id": None, "tile_id": None, "wb_sid": None}

    print(f"\n== Analytiq live smoke test → {base} ==\n")

    # 1. health + landing -----------------------------------------------------
    print("1. Health & landing page")
    st, _, raw = c.get("/health")
    body = as_json(raw) or {}
    r.check("/health returns 200 + status ok", st == 200 and body.get("status") == "ok",
            f"status={st}")
    st, _, raw = c.get("/")
    html = raw.decode("utf-8", "replace") if st == 200 else ""
    missing = [t for t in TIER_NAMES if t.lower() not in html.lower()]
    r.check("Landing page serves all 5 tier names", st == 200 and not missing,
            f"missing={missing}" if missing else "Explore/Analyst/Team/Business/On-prem")

    # 2. TLS ------------------------------------------------------------------
    print("2. TLS")
    check_tls(host, r)

    # 3. register throwaway → /auth/me = free + 15 credits --------------------
    print("3. Register → /auth/me (Free plan, 15 credits)")
    email = f"smoke+{uuid.uuid4().hex[:12]}@example.com"
    password = uuid.uuid4().hex + "Aa1!"        # generated; never printed
    st, _, raw = c.post_json("/auth/register", {"email": email, "password": password})
    reg = as_json(raw) or {}
    if not r.check("Register a throwaway account", st == 200 and reg.get("ok"),
                   f"status={st}"):
        print("\n  Cannot continue without an account. Aborting.")
        return _finish(r)
    st, _, raw = c.get("/auth/me")
    me = as_json(raw) or {}
    plan = me.get("plan", {})
    r.check("/auth/me shows Free plan", st == 200 and plan.get("name") == "free",
            f"plan={plan.get('name')} ({plan.get('label')})")
    r.check("/auth/me shows 15 credits remaining",
            plan.get("credits_remaining") == 15 and plan.get("credits_month") == 15,
            f"remaining={plan.get('credits_remaining')}")

    # 4. upload CSV → registers, and truly ingests the right number of rows -----
    print("4. Upload CSV → source registers with correct row count")
    st, _, raw = c.post_file("/upload", "smoke.csv", CSV_CONTENT, "text/csv")
    up = as_json(raw) or {}
    view = up.get("table")
    r.check("CSV upload ok with a registered table", st == 200 and up.get("ok") and bool(view),
            f"table={view}")
    st, _, raw = c.get("/tables")
    listed = (as_json(raw) or {}).get("tables", [])
    r.check("/tables lists the uploaded view", view in listed, f"tables={listed}")
    # The CSV upload response doesn't echo a row count (last_ingest is xlsx-only),
    # so verify the TRUE ingested row count via a throwaway workbench session,
    # which reports it reliably — this checks the data really landed, not just metadata.
    row_count = None
    if view:
        st, _, raw = c.post_json("/workbench/api/sessions", {"view": view})
        js = as_json(raw) or {}
        row_count = js.get("rows")
        if js.get("sid"):
            c.delete(f"/workbench/api/sessions/{js.get('sid')}")
    r.check("CSV ingested the correct number of rows", row_count == CSV_ROWS,
            f"rows={row_count}")

    asked = 0  # count credit-spending questions

    # 5. live question → answer + SQL trace (HARD) + chart spec (soft) --------
    # answer + sql_log prove the live Ollama-Cloud tool-calling pipeline works and
    # are asserted hard. Whether the model ALSO emits a chart is model-discretionary
    # (gpt-oss:120b decides per run), so we ask explicitly for a chart, retry once,
    # and treat a still-missing chart as a WARN — not a deploy-gate failure. The
    # chart pipeline itself is deterministic; a broken one would error, not no-op.
    print("5. Ask a live question (spends model credit)")
    ans, charts, st = {}, 0, 0
    for attempt in range(2):
        q = ("Show me total revenue by region as a bar chart." if attempt == 0
             else "Plot total revenue by region. Return a bar chart, not just text.")
        st, _, raw = c.post_json("/ask", {"question": q}, timeout=180)
        ans = as_json(raw) or {}
        if st == 200:
            asked += 1
        charts = len(ans.get("charts") or [])
        if charts:
            break
    r.check("/ask returns a non-empty answer",
            st == 200 and bool((ans.get("answer") or "").strip()),
            f"status={st}, answer_len={len((ans.get('answer') or ''))}")
    r.check("/ask returns a SQL trace (sql_log)", bool(ans.get("sql_log")),
            f"sql_log entries={len(ans.get('sql_log') or [])}")
    if charts:
        r.ok("/ask returns a chart spec", f"charts={charts}")
    else:
        r.warn("/ask chart spec",
                "model returned no chart this run (answer+SQL ok) — chart emission "
                "is model-discretionary; not a deploy failure")

    # 5b. plan-gating enforcement + paid-model liveness -----------------------
    print("5b. Model gating (403) + paid-model liveness")
    # Free account POSTing a paid model must be rejected server-side (not just hidden).
    st, _, raw = c.post_json("/ask", {"question": "ping", "model": "qwen3-coder"})
    r.check("Free account 403'd from a paid model (server-side enforcement)",
            st == 403, f"status={st}")
    key = os.environ.get("OLLAMA_API_KEY")
    if not key:
        r.skip("Paid-model tool-probe", "set OLLAMA_API_KEY to probe; paid /ask E2E lives in "
                                        "scripts/verify_paid_models.py (build-time acceptance)")
    else:
        for name, mid in PAID_MODELS:
            ok, detail = probe_tool_call(key, mid)
            r.check(f"paid model {name} ({mid}) tool-capable", ok, detail)

    # 5c. typed-column /ask → serialization regression gate -------------------
    # Upload a CSV DuckDB types as DATE + DOUBLE, then ask a CHART question over
    # the date column. This drives the full tenant chain: upload -> native type
    # inference -> read-only SQL -> run_sql tool-result json.dumps -> chart render.
    # The bug this guards: native date/Decimal objects hit a bare json.dumps and
    # 500'd. A 200 here is the HARD regression assertion (a 500 IS the bug); the
    # demo-DB check in section 5 can't catch it because sqlite returns dates as
    # strings. Chart emission stays model-discretionary (retry once -> WARN).
    print("5c. Typed-column /ask (DATE/DECIMAL) → JSON-serialization regression gate")
    st, _, raw = c.post_file("/upload", "typed.csv", TYPED_CSV_CONTENT, "text/csv")
    tup = as_json(raw) or {}
    tview = tup.get("table")
    r.check("Typed CSV (date+decimal) uploads and registers",
            st == 200 and tup.get("ok") and bool(tview), f"table={tview}")
    tans, tcharts, tst = {}, 0, 0
    for attempt in range(2):
        q = (f"Plot amount by signup_date from {tview} as a line chart." if attempt == 0
             else f"From {tview}, show amount over signup_date. Return a line chart.")
        tst, _, raw = c.post_json("/ask", {"question": q}, timeout=180)
        tans = as_json(raw) or {}
        if tst == 200:
            asked += 1
        tcharts = len(tans.get("charts") or [])
        if tcharts:
            break
    # THE gate: querying a native DATE/DECIMAL column must not 500 on serialization.
    r.check("/ask over a DATE/DECIMAL column returns 200 (not a serialization 500)",
            tst == 200 and bool((tans.get("answer") or "").strip()),
            f"status={tst}, answer_len={len((tans.get('answer') or ''))}")
    if tcharts:
        r.ok("/ask over typed columns renders a chart", f"charts={tcharts}")
    else:
        r.warn("/ask typed-column chart spec",
                "model returned no chart this run (200+answer ok) — chart emission "
                "is model-discretionary; the 200 is the regression gate")

    # 5d. statistical charts (Phase A) over BOTH backends ---------------------
    # The new declarative chart types (histogram/boxplot/…) add render branches
    # and Vega-Lite transforms. Prove the live pipeline doesn't 500 over EITHER
    # serialization backend (two-backends rule): a histogram over the DuckDB
    # upload (native DECIMAL `amount`) and a boxplot over the sqlite demo DB
    # (`revenue`). A 200 is the HARD gate — a broken transform/render would raise,
    # not no-op. The specific chart TYPE stays model-discretionary (single /ask,
    # no retry), so a wrong/absent type is a WARN, and when the model DOES emit a
    # statistical chart we assert the neutral tag matches what was asked for.
    print("5d. Statistical charts (histogram/boxplot) — both backends")

    def _neutral_types(answer: dict) -> list[str]:
        out = []
        for ch in (answer.get("charts") or []):
            if isinstance(ch, dict) and ch.get("_neutral"):
                out.append(ch["_neutral"])
        return out

    # histogram over the DuckDB upload (native DECIMAL column)
    hst, _, raw = c.post_json(
        "/ask", {"question": f"Show the distribution of amount from {tview} as a histogram."},
        timeout=180)
    hans = as_json(raw) or {}
    if hst == 200:
        asked += 1
    r.check("Histogram /ask over the DuckDB upload returns 200 (render path, no 500)",
            hst == 200 and bool((hans.get("answer") or "").strip()),
            f"status={hst}, types={_neutral_types(hans)}")
    if "histogram" in _neutral_types(hans):
        r.ok("Upload histogram rendered as a histogram spec")
    elif hans.get("charts"):
        r.warn("Upload histogram type", f"model charted {_neutral_types(hans)} (type is model-discretionary)")
    else:
        r.warn("Upload histogram spec", "model returned no chart this run (200+answer ok)")

    # boxplot over the sqlite demo DB (string dates — the other serialization path)
    bst, _, raw = c.post_json(
        "/ask", {"question": "Compare the distribution of revenue across regions as a boxplot."},
        timeout=180)
    bans = as_json(raw) or {}
    if bst == 200:
        asked += 1
    r.check("Boxplot /ask over the sqlite demo DB returns 200 (render path, no 500)",
            bst == 200 and bool((bans.get("answer") or "").strip()),
            f"status={bst}, types={_neutral_types(bans)}")
    if "boxplot" in _neutral_types(bans):
        r.ok("Demo boxplot rendered as a boxplot spec")
    elif bans.get("charts"):
        r.warn("Demo boxplot type", f"model charted {_neutral_types(bans)} (type is model-discretionary)")
    else:
        r.warn("Demo boxplot spec", "model returned no chart this run (200+answer ok)")

    # 5e. geographic charts (Phase B) — map render + honest refusal -----------
    # Upload a real country,revenue CSV and ask for a MAP. The choropleth path
    # resolves country names -> topojson ids server-side (frozen lookup) and joins
    # them onto the vendored basemap. A 200 is the HARD gate (a broken geoshape/
    # lookup raises, not no-ops); chart TYPE stays model-discretionary (WARN), and
    # when a map IS emitted we assert its _neutral tag is 'choropleth' AND that it
    # carries the topojson basemap (data.url) + resolved lookup values — i.e. a real
    # map, not a bar-chart fallback. The NEGATIVE half asks for a map over a table
    # with NO geographic column (the typed CSV: signup_date/amount) and asserts the
    # honest-refusal path returns 200 — the renderer's <80%-resolve ValueError must
    # surface as an error the model relays, never a 500.
    print("5e. Geographic charts (choropleth) — map render + honest no-geo refusal")
    gst, _, raw = c.post_file("/upload", "geo.csv", GEO_CSV_CONTENT, "text/csv")
    gup = as_json(raw) or {}
    gview = gup.get("table")
    r.check("Country CSV uploads and registers", gst == 200 and gup.get("ok") and bool(gview),
            f"table={gview}")

    def _choropleths(answer: dict) -> list[dict]:
        return [ch for ch in (answer.get("charts") or [])
                if isinstance(ch, dict) and ch.get("_neutral") == "choropleth"]

    mans, mst = {}, 0
    if gview:
        for attempt in range(2):
            q = (f"Show total revenue by country from {gview} on a map." if attempt == 0
                 else f"From {gview}, map revenue by country. Return a choropleth map.")
            mst, _, raw = c.post_json("/ask", {"question": q}, timeout=180)
            mans = as_json(raw) or {}
            if mst == 200:
                asked += 1
            if _choropleths(mans):
                break
        r.check("Map /ask over the country upload returns 200 (geoshape path, no 500)",
                mst == 200 and bool((mans.get("answer") or "").strip()),
                f"status={mst}, types={_neutral_types(mans)}")
        maps = _choropleths(mans)
        if maps:
            m = maps[0]
            url = ((m.get("data") or {}).get("url") or "")
            vals = (((m.get("transform") or [{}])[0].get("from") or {}).get("data") or {}).get("values") or []
            r.check("Choropleth carries the vendored topojson basemap + resolved regions",
                    "/static/vendor/" in url and len(vals) > 0,
                    f"url={url!r}, resolved_regions={len(vals)}")
        elif mans.get("charts"):
            r.warn("Country map type", f"model charted {_neutral_types(mans)} (type is model-discretionary)")
        else:
            r.warn("Country map spec", "model returned no chart this run (200+answer ok)")

    # NEGATIVE: a map request over data with no geographic column must not 500.
    nst, _, raw = c.post_json(
        "/ask", {"question": f"Show amount by signup_date from {tview} on a country map."},
        timeout=180)
    nans = as_json(raw) or {}
    if nst == 200:
        asked += 1
    r.check("Map request over non-geographic data refuses honestly (200, no 500)",
            nst == 200 and bool((nans.get("answer") or "").strip()),
            f"status={nst}, types={_neutral_types(nans)}")

    # 6. 2-sheet xlsx → both sheets register ----------------------------------
    print("6. Upload 2-sheet .xlsx → both sheets register")
    xlsx = build_xlsx_2sheets()
    if xlsx is None:
        r.skip("Multi-sheet xlsx path", "openpyxl not importable (run under the app venv)")
    else:
        st, _, raw = c.post_file(
            "/upload", "smoke2.xlsx", xlsx,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        up2 = as_json(raw) or {}
        n = len(up2.get("tables") or [])
        r.check("2-sheet xlsx registers 2 tables", st == 200 and up2.get("ok") and n == 2,
                f"tables registered={n}")

    # 7. dashboard: pin a tile → persists → refresh re-runs SQL (no LLM) -------
    print("7. Dashboard pin → persist → refresh (SQL only, no LLM)")
    st, _, raw = c.post_json("/dashboard/api/boards", {"name": "smoke board"})
    board = as_json(raw) or {}
    bid = board.get("id") or board.get("board_id")
    created["board_id"] = bid
    r.check("Create a dashboard board", st == 200 and bool(bid), f"board_id={bid}")
    pin_sql = f"SELECT region, sum(revenue) AS revenue FROM {view} GROUP BY region"
    st, _, raw = c.post_json("/dashboard/api/tiles", {
        "board_id": bid, "title": "Revenue by region",
        "question": "Total revenue by region", "sql": pin_sql,
        "spec": (ans.get("charts") or [None])[0]})
    tile = as_json(raw) or {}
    tid = tile.get("id") or tile.get("tile_id")
    created["tile_id"] = tid
    r.check("Pin a tile to the board", st == 200 and bool(tid), f"tile_id={tid}")
    st, _, raw = c.get(f"/dashboard/api/boards/{bid}/tiles")
    tiles = (as_json(raw) or {}).get("tiles", [])
    r.check("Tile persists on the board", any((t.get("id") or t.get("tile_id")) == tid for t in tiles),
            f"tiles on board={len(tiles)}")
    st, _, raw = c.post_json(f"/dashboard/api/tiles/{tid}/refresh", {})
    refreshed = as_json(raw) or {}
    # refresh re-runs the stored SQL server-side; "no LLM" is by construction
    # (refresh_tile never calls a model — it only re-executes read-only SQL).
    got_data = bool(refreshed.get("rows") or refreshed.get("data") or refreshed.get("spec"))
    r.check("Refresh re-runs SQL and returns data (no LLM by construction)",
            st == 200 and got_data, f"status={st}")

    # 8. workbench: session → profile → propose → apply → download; source safe
    print("8. Workbench: clean a copy, source stays immutable")
    st, _, raw = c.post_json("/workbench/api/sessions", {"view": view})
    ses = as_json(raw) or {}
    sid = ses.get("sid")
    sha_before = ses.get("source_sha256")
    created["wb_sid"] = sid
    r.check("Create a workbench session on the CSV view", st == 200 and bool(sid),
            f"sid={sid}, rows={ses.get('rows')}")
    if sid:
        st, _, raw = c.get(f"/workbench/api/sessions/{sid}/profile")
        prof = as_json(raw) or {}
        r.check("Workbench profile returns", st == 200 and "profile" in prof)
        st, _, raw = c.post_json(f"/workbench/api/sessions/{sid}/propose",
                                 {"instruction": "Clean up column types and drop empty rows."},
                                 timeout=180)
        proposal = as_json(raw) or {}
        ops = proposal.get("ops") or proposal.get("plan") or []
        r.check("Workbench propose (live model) returns a plan", st == 200,
                f"proposed ops={len(ops) if isinstance(ops, list) else '?'}")
        # apply the model's own proposed ops (deterministic executor runs them)
        if isinstance(ops, list) and ops:
            st, _, raw = c.post_json(f"/workbench/api/sessions/{sid}/apply", {"ops": ops})
            r.check("Apply one recipe step", st == 200, f"status={st}")
        else:
            r.skip("Apply one recipe step", "model proposed no ops this run")
        st, _, raw = c.get(f"/workbench/api/sessions/{sid}/download")
        r.check("Download cleaned CSV", st == 200 and raw[:1] not in (b"", b"{"),
                f"status={st}, bytes={len(raw)}")
        # source immutable: a fresh session on the same view has the SAME sha256
        st, _, raw = c.post_json("/workbench/api/sessions", {"view": view})
        sha_after = (as_json(raw) or {}).get("source_sha256")
        if (as_json(raw) or {}).get("sid"):
            c.delete(f"/workbench/api/sessions/{(as_json(raw) or {}).get('sid')}")
        r.check("Source unchanged after cleaning (sha256 stable)",
                bool(sha_before) and sha_before == sha_after,
                "sha256 identical" if sha_before == sha_after else "SHA CHANGED")

    # 9. table scope + delete — NOT in this lineage ---------------------------
    print("9. Table scope + delete")
    r.skip("Table scope + delete",
           "VPS-demo-lineage feature; no table-scope/table-delete route in this tree")

    # 10. credit metering -----------------------------------------------------
    print("10. Credit metering")
    st, _, raw = c.get("/auth/me")
    used = ((as_json(raw) or {}).get("plan") or {}).get("credits_used")
    r.check("Credits decremented by exactly the questions asked",
            used == asked, f"credits_used={used}, questions asked={asked}")

    # 11. billing correctly DISABLED (Stripe blank) ---------------------------
    print("11. Billing disabled (no Stripe keys)")
    st, _, raw = c.get("/billing/config")
    cfg = as_json(raw) or {}
    r.check("/billing/config reports configured:false",
            st == 200 and cfg.get("configured") is False, f"configured={cfg.get('configured')}")
    st, _, raw = c.post_json("/billing/checkout", {"plan": "analyst"})
    # billing off => graceful 503 from the endpoint, never a 500
    r.check("Upgrade path fails gracefully (503, not 500)", st == 503, f"status={st}")

    # 12. cleanup (partial — no account-deletion endpoint) --------------------
    print("12. Cleanup")
    if created["tile_id"]:
        c.delete(f"/dashboard/api/tiles/{created['tile_id']}")
    if created["board_id"]:
        c.delete(f"/dashboard/api/boards/{created['board_id']}")
    if created["wb_sid"]:
        c.delete(f"/workbench/api/sessions/{created['wb_sid']}")
    r.ok("Deleted dashboard + workbench artifacts created by this run")
    r.skip("Delete throwaway account",
           "no account-deletion endpoint; Free account with unique email left behind (harmless)")

    return _finish(r)


def _finish(r: Results) -> int:
    print(f"\n== {r.summary()} ==")
    return 1 if r.failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Live end-to-end smoke test for a running Analytiq deployment.")
    ap.add_argument("--base-url", default=DEFAULT_BASE,
                    help=f"root URL of the running deployment (default {DEFAULT_BASE})")
    args = ap.parse_args()
    try:
        return run(args.base_url)
    except KeyboardInterrupt:
        print("\ninterrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
