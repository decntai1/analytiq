"""
Dashboards — pin chat results as tiles; refresh WITHOUT the LLM.

A tile stores {question, sql, spec}. Refresh re-runs the saved SQL through the
tenant connector (whose read-only guard applies to every refresh, forever) and
re-binds the fresh rows into the saved neutral-spec-rendered chart. This is the
roadmap's "persistent panel below" surface, Vega-Lite-native: same neutral
spec, no re-prompting, deterministic by construction.
"""
from __future__ import annotations

import copy
import json
import os
import re
import secrets
import time

DB_ROOT = os.getenv("DASHBOARD_DIR", "./dashboards")
MAX_TILES = int(os.getenv("DASHBOARD_MAX_TILES", "60"))
_ID_RE = re.compile(r"^(bd|tl)_[a-z0-9]{10}$")


class BoardStore:
    """JSON-backed, tenant-scoped store under DB_ROOT/<scope>/boards.json."""

    def __init__(self, root: str = DB_ROOT):
        self.root = os.path.abspath(root)
        os.makedirs(self.root, exist_ok=True)

    def _path(self, scope: str) -> str:
        d = os.path.join(self.root, re.sub(r"\W+", "_", scope or "default") or "default")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "boards.json")

    def _load(self, scope: str) -> dict:
        p = self._path(scope)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        return {"boards": [], "tiles": []}

    def _save(self, scope: str, data: dict) -> None:
        with open(self._path(scope), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)

    # -- boards ---------------------------------------------------------------
    def list_boards(self, scope: str) -> list[dict]:
        d = self._load(scope)
        counts: dict[str, int] = {}
        for t in d["tiles"]:
            counts[t["board_id"]] = counts.get(t["board_id"], 0) + 1
        return [{**b, "tiles": counts.get(b["id"], 0)} for b in d["boards"]]

    def create_board(self, scope: str, name: str) -> dict:
        d = self._load(scope)
        b = {"id": "bd_" + secrets.token_hex(5), "name": (name or "My dashboard")[:80],
             "created": time.time()}
        d["boards"].append(b)
        self._save(scope, d)
        return b

    def delete_board(self, scope: str, board_id: str) -> None:
        d = self._load(scope)
        if not any(b["id"] == board_id for b in d["boards"]):
            raise KeyError(board_id)
        d["boards"] = [b for b in d["boards"] if b["id"] != board_id]
        d["tiles"] = [t for t in d["tiles"] if t["board_id"] != board_id]
        self._save(scope, d)

    def default_board(self, scope: str) -> dict:
        d = self._load(scope)
        return d["boards"][0] if d["boards"] else self.create_board(scope, "My dashboard")

    # -- tiles ------------------------------------------------------------------
    def add_tile(self, scope: str, board_id: str | None, title: str, question: str,
                 sql: str, spec: dict | None) -> dict:
        d = self._load(scope)
        if len(d["tiles"]) >= MAX_TILES:
            raise ValueError(f"tile limit ({MAX_TILES}) reached")
        # Resolve the target board: honor an explicit board_id when it exists in this
        # scope, else fall back to the default board. The chat page pins to the user's
        # last-viewed board (from localStorage), which may be stale/deleted/foreign — a
        # bad id must NOT lose the pin. default_board creates "My dashboard" if none.
        if board_id and any(b["id"] == board_id for b in d["boards"]):
            bid = board_id
        else:
            bid = self.default_board(scope)["id"]
        if spec:  # store the spec LEAN: data is re-bound on every refresh
            spec = copy.deepcopy(spec)
            spec["data"] = {"values": []}
        t = {"id": "tl_" + secrets.token_hex(5), "board_id": bid,
             "title": (title or question or "Tile")[:120], "question": question or "",
             "sql": sql or "", "spec": spec, "created": time.time()}
        d = self._load(scope)
        d["tiles"].append(t)
        self._save(scope, d)
        return t

    def list_tiles(self, scope: str, board_id: str) -> list[dict]:
        return [t for t in self._load(scope)["tiles"] if t["board_id"] == board_id]

    def get_tile(self, scope: str, tile_id: str) -> dict:
        if not _ID_RE.match(tile_id or ""):
            raise KeyError(tile_id)
        for t in self._load(scope)["tiles"]:
            if t["id"] == tile_id:
                return t
        raise KeyError(tile_id)

    def update_tile(self, scope: str, tile_id: str, title: str | None = None,
                    sql: str | None = None) -> dict:
        d = self._load(scope)
        for t in d["tiles"]:
            if t["id"] == tile_id:
                if title is not None:
                    t["title"] = title[:120]
                if sql is not None:
                    t["sql"] = sql
                self._save(scope, d)
                return t
        raise KeyError(tile_id)

    def delete_tile(self, scope: str, tile_id: str) -> None:
        d = self._load(scope)
        before = len(d["tiles"])
        d["tiles"] = [t for t in d["tiles"] if t["id"] != tile_id]
        if len(d["tiles"]) == before:
            raise KeyError(tile_id)
        self._save(scope, d)

    # -- refresh: re-run guarded SQL, re-bind rows — NO LLM ----------------------
    def refresh_tile(self, scope: str, tile_id: str, ctx) -> dict:
        t = self.get_tile(scope, tile_id)
        if not t["sql"].strip():
            return {"tile": t, "error": "tile has no SQL to run"}
        try:
            # the connector's read-only guard applies here on EVERY refresh
            qr = ctx.connector.run_query(t["sql"])
        except Exception as e:
            return {"tile": t, "error": f"query failed: {e}"}
        rows = qr.rows
        base = {"tile": t, "row_count": len(rows), "truncated": bool(qr.truncated),
                "refreshed_at": time.time()}
        if t.get("spec"):
            # A chart tile that binds no rows, or whose encoded columns the query no
            # longer returns, would render a SILENTLY BLANK chart. Refuse honestly with
            # a per-tile message instead (the dashboard shows it as an errline).
            if not rows:
                return {**base, "error": "the saved query returned no rows — the source "
                        "table may have changed or been emptied"}
            missing = self._spec_fields(t["spec"]) - set(qr.columns)
            if missing:
                return {**base, "error": "the chart needs column(s) the query no longer "
                        f"returns: {', '.join(sorted(missing))}"}
            spec = copy.deepcopy(t["spec"])
            spec["data"] = {"values": rows}
            return {**base, "spec": spec}
        base["columns"], base["rows"] = qr.columns, rows[:200]
        return base

    @staticmethod
    def _spec_fields(spec: dict) -> set:
        """Column names a Vega-Lite spec's encodings reference (top-level + one layer
        deep — value-labelled charts are layered). Used to detect a refresh whose rows
        no longer carry the chart's fields (→ honest error, not a blank tile)."""
        fields: set = set()
        def walk(enc):
            for ch in (enc or {}).values():
                if isinstance(ch, dict) and isinstance(ch.get("field"), str):
                    fields.add(ch["field"])
        walk(spec.get("encoding"))
        for layer in (spec.get("layer") or []):
            walk(layer.get("encoding"))
        return fields

    def board_to_deck(self, scope: str, board_id: str, ctx) -> bytes:
        """Export a board as an editable PPTX: fresh data per tile."""
        from viz.presentation import DeckBuilder  # lazy: needs pptx + vl-convert
        boards = {b["id"]: b for b in self._load(scope)["boards"]}
        if board_id not in boards:
            raise KeyError(board_id)
        deck = DeckBuilder()
        deck.title_slide(boards[board_id]["name"], "Dashboard export · generated by Analytiq")
        audit = []
        for t in self.list_tiles(scope, board_id):
            r = self.refresh_tile(scope, t["id"], ctx)
            if r.get("spec"):
                deck.chart_slide(t["title"], t.get("question", "")[:300], r["spec"])
            else:
                lines = [f"{r.get('row_count', 0)} rows" if not r.get("error") else r["error"]]
                deck.summary_slide(t["title"], lines)
            if t.get("sql"):
                audit.append({"title": t["title"], "sql": t["sql"][:1200]})
        if audit:
            deck.appendix_slide(audit)
        import io
        buf = io.BytesIO()
        deck.prs.save(buf)
        return buf.getvalue()
