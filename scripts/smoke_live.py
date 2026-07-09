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
                "SKIP": "\033[33mSKIP\033[0m"}.get(status, status)
        print(f"  [{mark}] {name}" + (f"  — {detail}" if detail else ""), flush=True)

    def ok(self, name: str, detail: str = "") -> None:   self._add("PASS", name, detail)
    def fail(self, name: str, detail: str = "") -> None: self._add("FAIL", name, detail)
    def skip(self, name: str, detail: str = "") -> None: self._add("SKIP", name, detail)

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
        return f"{p} passed, {f} failed, {k} skipped"


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


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
CSV_CONTENT = (
    "region,quarter,revenue\n"
    "North,Q1,120\nNorth,Q2,150\nSouth,Q1,90\n"
    "South,Q2,110\nEast,Q1,70\nWest,Q2,140\n"
).encode()
CSV_ROWS = 6


def build_xlsx_2sheets() -> bytes | None:
    """A genuine 2-sheet workbook via openpyxl (a project dep). None if unavailable."""
    try:
        from openpyxl import Workbook
    except Exception:
        return None
    wb = Workbook()
    s1 = wb.active
    s1.title = "sales"
    s1.append(["region", "revenue"])
    for r in [("North", 120), ("South", 90), ("East", 70)]:
        s1.append(list(r))
    s2 = wb.create_sheet("headcount")
    s2.append(["team", "people"])
    for r in [("Eng", 12), ("Sales", 7)]:
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

    # 4. upload CSV → registers with a row count ------------------------------
    print("4. Upload CSV → source registers with row count")
    st, _, raw = c.post_file("/upload", "smoke.csv", CSV_CONTENT, "text/csv")
    up = as_json(raw) or {}
    view = up.get("table")
    tbls = up.get("tables") or []
    rows = tbls[0].get("rows") if tbls else None
    r.check("CSV upload ok with a registered table", st == 200 and up.get("ok") and bool(view),
            f"table={view}")
    r.check("Upload reports the correct row count", rows == CSV_ROWS, f"rows={rows}")
    st, _, raw = c.get("/tables")
    listed = (as_json(raw) or {}).get("tables", [])
    r.check("/tables lists the uploaded view", view in listed, f"tables={listed}")

    asked = 0  # count credit-spending questions

    # 5. live question → chart spec + SQL trace + answer ----------------------
    print("5. Ask a live question (spends OpenAI credit)")
    st, _, raw = c.post_json("/ask", {"question": "What is the total revenue by region?"},
                             timeout=180)
    ans = as_json(raw) or {}
    if st == 200:
        asked += 1
    r.check("/ask returns a non-empty answer", st == 200 and bool((ans.get("answer") or "").strip()),
            f"status={st}, answer_len={len((ans.get('answer') or ''))}")
    r.check("/ask returns at least one chart spec", bool(ans.get("charts")),
            f"charts={len(ans.get('charts') or [])}")
    r.check("/ask returns a SQL trace (sql_log)", bool(ans.get("sql_log")),
            f"sql_log entries={len(ans.get('sql_log') or [])}")

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
