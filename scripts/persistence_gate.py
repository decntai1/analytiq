#!/usr/bin/env python3
"""Cross-process dashboard-persistence gate.

smoke_live.py §7 pins → lists → refreshes → deletes a tile all inside ONE process,
so it proves the API is coherent but is STRUCTURALLY BLIND to whether a pinned tile
survives a container recreate. It stayed green through a real data-loss bug: the
BoardStore default path (./dashboards → /app/dashboards) lived on the container's
ephemeral layer, so every `docker compose up --build` wiped every pinned tile
(fixed 2026-07-19 by pointing DASHBOARD_DIR/WORKBENCH_DIR at the /data volume).

This gate is the only kind of test that can catch that class: it splits pin and
verify into two invocations with a REAL container recreate in between.

Usage (run on the HOST, around a rebuild):
    python3 scripts/persistence_gate.py pin    --base-url https://analytiq.dcentai.tech
    docker compose -f docker-compose.prod.yml up -d --build      # real recreate
    python3 scripts/persistence_gate.py verify --base-url https://analytiq.dcentai.tech

`pin` registers a throwaway account, creates a board, pins a tile, and writes the
session cookie + ids to a state file (default: a temp file that survives on the
host across the recreate). `verify` reloads that session and asserts the tile is
still on the board. Exit 0 iff the tile survived. Stdlib only.
"""
import argparse
import http.cookiejar
import json
import os
import ssl
import sys
import urllib.error
import urllib.request

STATE_DEFAULT = os.path.join(os.environ.get("TMPDIR", "/tmp"), "analytiq_persist_gate")


def _client(cookie_file: str):
    jar = http.cookiejar.MozillaCookieJar(cookie_file)
    if os.path.exists(cookie_file):
        jar.load(ignore_discard=True, ignore_expires=True)
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
    )
    return opener, jar


def _req(opener, base, method, path, payload=None, timeout=60):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base.rstrip("/") + path, data=data, method=method, headers=headers)
    try:
        resp = opener.open(req, timeout=timeout)
        return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _json(raw):
    try:
        return json.loads(raw or b"{}")
    except Exception:
        return {}


def do_pin(base, state):
    cookie_file = state + ".cookies"
    opener, jar = _client(cookie_file)
    # unique throwaway account (register auto-logs-in via session cookie)
    import time
    email = f"persist_gate_{int(time.time())}@example.com"
    password = "gate-pw-123456"
    st, raw = _req(opener, base, "POST", "/auth/register", {"email": email, "password": password})
    if st != 200:
        print(f"FAIL: register status={st} body={raw[:200]!r}")
        return 1
    st, raw = _req(opener, base, "POST", "/dashboard/api/boards", {"name": "persist gate board"})
    board = _json(raw)
    bid = board.get("id") or board.get("board_id")
    if st != 200 or not bid:
        print(f"FAIL: create board status={st} body={raw[:200]!r}")
        return 1
    sentinel = f"persist-sentinel-{int(time.time())}"
    st, raw = _req(opener, base, "POST", "/dashboard/api/tiles", {
        "board_id": bid, "title": sentinel,
        "question": "persistence gate", "sql": "SELECT 1 AS one", "spec": None})
    tile = _json(raw)
    tid = tile.get("id") or tile.get("tile_id")
    if st != 200 or not tid:
        print(f"FAIL: pin tile status={st} body={raw[:200]!r}")
        return 1
    jar.save(ignore_discard=True, ignore_expires=True)
    with open(state + ".json", "w") as f:
        json.dump({"base": base, "email": email, "board_id": bid,
                   "tile_id": tid, "sentinel": sentinel}, f)
    print(f"PIN OK: board={bid} tile={tid} sentinel={sentinel}")
    print(f"  state → {state}.json / {cookie_file}")
    print("  now recreate the container, then run: persistence_gate.py verify")
    return 0


def do_verify(base, state):
    cookie_file = state + ".cookies"
    try:
        meta = json.load(open(state + ".json"))
    except Exception as e:
        print(f"FAIL: no pin state at {state}.json ({e}); run `pin` first")
        return 1
    opener, _ = _client(cookie_file)
    bid, tid = meta["board_id"], meta["tile_id"]
    st, raw = _req(opener, base, "GET", f"/dashboard/api/boards/{bid}/tiles")
    if st != 200:
        # 401 here = the session itself didn't survive (accounts.db off-volume) —
        # a DIFFERENT persistence bug, still a fail worth surfacing distinctly.
        print(f"FAIL: list tiles status={st} (session or board gone) body={raw[:200]!r}")
        return 1
    tiles = _json(raw).get("tiles", [])
    match = [t for t in tiles if (t.get("id") or t.get("tile_id")) == tid]
    if not match:
        print(f"FAIL: tile {tid} DID NOT SURVIVE the recreate "
              f"(board {bid} now has {len(tiles)} tile(s)) — dashboards are not on a durable volume")
        return 1
    got = match[0]
    if got.get("sql") != "SELECT 1 AS one" or got.get("title") != meta["sentinel"]:
        print(f"FAIL: tile survived but content changed: {got!r}")
        return 1
    print(f"VERIFY OK: tile {tid} survived the container recreate with intact content "
          f"(sentinel={meta['sentinel']}). Dashboards are durable.")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=["pin", "verify"])
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--state", default=STATE_DEFAULT,
                    help=f"state file path prefix (default {STATE_DEFAULT})")
    a = ap.parse_args()
    rc = do_pin(a.base_url, a.state) if a.action == "pin" else do_verify(a.base_url, a.state)
    sys.exit(rc)


if __name__ == "__main__":
    main()
