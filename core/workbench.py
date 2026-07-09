"""
Workbench — AI-assisted data cleansing on SANDBOXED COPIES, never sources.

Safety model (stricter than the chat pipeline):
  - The source is IMMUTABLE: hashed at session start; nothing here ever opens it
    for write. Sessions work on a materialized copy in their own folder, with
    their own DuckDB database file (no shared-connection involvement at all).
  - The LLM has NO TOOLS. It can only emit a cleaning PLAN in the whitelisted
    operations vocabulary below. The only actor that touches data is the
    deterministic executor, and every op it runs is logged SQL (the recipe).
  - validate_plan() rejects unknown ops, unknown columns, and non-enum args.
    Invalid ops are DROPPED with a reason, never "fixed up".
  - All session paths are realpath-confined under the workbench root.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import time
from typing import Any

import duckdb

WB_ROOT = os.getenv("WORKBENCH_DIR", "./workbench")
MAX_SESSIONS = int(os.getenv("WORKBENCH_MAX_SESSIONS", "5"))
MAX_ROWS = int(os.getenv("WORKBENCH_MAX_ROWS", "250000"))

_SID_RE = re.compile(r"^wb_[a-z0-9]{10}$")


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _q(ident: str) -> str:
    return '"' + str(ident).replace('"', '""') + '"'


# --------------------------------------------------------------------------- #
# CAPABILITY — the whole vocabulary the LLM may propose. Everything else is
# rejected at validation. `cols:"text"|"num"|"any"` = column-type requirement.
# --------------------------------------------------------------------------- #
CAPABILITY: dict[str, dict] = {
    "trim_whitespace":  {"args": {"columns": "cols?"}, "cols": "text",
                         "doc": "strip leading/trailing whitespace (all text columns if none given)"},
    "normalize_nulls":  {"args": {"columns": "cols?", "tokens": "list?"}, "cols": "text",
                         "doc": "turn placeholder tokens ('', 'NA', 'null', '-', 'nan', 'n/a', 'none') into real NULLs"},
    "normalize_case":   {"args": {"column": "col", "mode": ["upper", "lower"]}, "cols": "text",
                         "doc": "uppercase/lowercase a text column"},
    "rename_column":    {"args": {"column": "col", "new_name": "str"}, "cols": "any",
                         "doc": "rename a column"},
    "drop_columns":     {"args": {"columns": "cols"}, "cols": "any",
                         "doc": "remove columns"},
    "cast_column":      {"args": {"column": "col", "type": ["int", "double", "date", "varchar", "boolean"]},
                         "cols": "any",
                         "doc": "convert a column's type; unparseable values become NULL (count reported)"},
    "dedupe_rows":      {"args": {"subset": "cols?"}, "cols": "any",
                         "doc": "remove duplicate rows (whole row, or by a subset of key columns; keeps the first)"},
    "drop_rows_where":  {"args": {"column": "col", "condition": ["is_null", "equals"], "value": "str?"},
                         "cols": "any",
                         "doc": "delete rows where a column is NULL / equals a value"},
    "fill_missing":     {"args": {"column": "col", "strategy": ["constant", "zero", "mean", "median"],
                                  "value": "str?"}, "cols": "any",
                         "doc": "fill NULLs (mean/median need a numeric column)"},
    "replace_values":   {"args": {"column": "col", "mapping": "map"}, "cols": "text",
                         "doc": "exact-value replacement via a mapping {from: to}"},
    "regex_replace":    {"args": {"column": "col", "pattern": "str", "replacement": "str"}, "cols": "text",
                         "doc": "regexp_replace on a text column (data transform, not code)"},
}


def capability_doc() -> str:
    lines = [f"- {name}({', '.join(spec['args'])}): {spec['doc']}" for name, spec in CAPABILITY.items()]
    return "\n".join(lines)


def _find_source(duck, view: str) -> str | None:
    """Backing file for a view, cross-lineage: prefer the connector's
    _view_source ledger (newer trees); else derive from the data dir via the
    same stem-sanitization rule the ingestion uses."""
    src = getattr(duck, "_view_source", {}).get(view)
    if src:
        return src
    data_dir = getattr(duck, "data_dir", None)
    if not data_dir or not os.path.isdir(data_dir):
        return None
    def stem(p: str) -> str:
        v = re.sub(r"\W+", "_", os.path.splitext(os.path.basename(p))[0]).strip("_").lower()
        return ("t_" + v) if v and v[0].isdigit() else v
    for f in sorted(os.listdir(data_dir)):
        p = os.path.join(data_dir, f)
        if os.path.isfile(p) and (view == stem(p) or view.startswith(stem(p) + "_")):
            return p
    return None


class WorkbenchSession:
    """One sandbox: a folder, a DuckDB file, a `work` table + `pristine` copy."""

    def __init__(self, sid: str, folder: str, meta: dict | None = None):
        self.sid, self.folder = sid, folder
        self.db_path = os.path.join(folder, "session.duckdb")
        self.meta_path = os.path.join(folder, "session.json")
        self.meta = meta or (json.load(open(self.meta_path)) if os.path.exists(self.meta_path) else {})
        self._con: duckdb.DuckDBPyConnection | None = None

    @property
    def con(self) -> duckdb.DuckDBPyConnection:
        if self._con is None:
            self._con = duckdb.connect(self.db_path)
        return self._con

    def _save(self) -> None:
        with open(self.meta_path, "w", encoding="utf-8") as f:
            json.dump(self.meta, f, indent=1)

    # -- schema helpers ------------------------------------------------------
    def columns(self, table: str = "work") -> dict[str, str]:
        rows = self.con.execute(f"PRAGMA table_info({_q(table)})").fetchall()
        return {r[1]: str(r[2]).upper() for r in rows}

    def _text_cols(self) -> list[str]:
        return [c for c, t in self.columns().items() if "VARCHAR" in t or "CHAR" in t]

    def row_count(self, table: str = "work") -> int:
        return self.con.execute(f"SELECT COUNT(*) FROM {_q(table)}").fetchone()[0]

    # -- deterministic profile (no LLM) --------------------------------------
    def profile(self) -> dict:
        cols = self.columns()
        n = self.row_count()
        out = []
        for c, t in cols.items():
            qc = _q(c)
            nulls = self.con.execute(f"SELECT COUNT(*) FROM work WHERE {qc} IS NULL").fetchone()[0]
            distinct = self.con.execute(f"SELECT COUNT(DISTINCT {qc}) FROM work").fetchone()[0]
            top = self.con.execute(
                f"SELECT CAST({qc} AS VARCHAR) v, COUNT(*) c FROM work WHERE {qc} IS NOT NULL "
                f"GROUP BY 1 ORDER BY c DESC LIMIT 5").fetchall()
            info: dict[str, Any] = {"column": c, "dtype": t, "null_pct": round(100 * nulls / n, 1) if n else 0,
                                    "distinct": distinct, "top": [{"value": v, "count": k} for v, k in top]}
            if "VARCHAR" in t:
                ws = self.con.execute(
                    f"SELECT COUNT(*) FROM work WHERE {qc} IS NOT NULL AND {qc} <> TRIM({qc})").fetchone()[0]
                nn = self.con.execute(f"SELECT COUNT(*) FROM work WHERE {qc} IS NOT NULL").fetchone()[0]
                num_ok = self.con.execute(
                    f"SELECT COUNT(*) FROM work WHERE {qc} IS NOT NULL AND TRY_CAST({qc} AS DOUBLE) IS NOT NULL"
                ).fetchone()[0]
                date_ok = self.con.execute(
                    f"SELECT COUNT(*) FROM work WHERE {qc} IS NOT NULL AND TRY_CAST({qc} AS DATE) IS NOT NULL"
                ).fetchone()[0]
                info["whitespace_rows"] = ws
                info["numeric_parse_pct"] = round(100 * num_ok / nn, 1) if nn else 0
                info["date_parse_pct"] = round(100 * date_ok / nn, 1) if nn else 0
                info["mixed_type"] = bool(nn and 5 <= (100 * num_ok / nn) <= 95)
            out.append(info)
        dup = n - self.con.execute("SELECT COUNT(*) FROM (SELECT DISTINCT * FROM work)").fetchone()[0]
        return {"table": self.meta.get("source_view"), "rows": n, "columns": out, "duplicate_rows": dup}

    # -- plan validation ------------------------------------------------------
    def validate_plan(self, plan: list[dict]) -> tuple[list[dict], list[dict]]:
        """Returns (valid_ops, rejected[{op, reason}]). Never mutates an op."""
        cols = self.columns()
        valid, rejected = [], []
        for raw in (plan or []):
            if not isinstance(raw, dict) or raw.get("op") not in CAPABILITY:
                rejected.append({"op": str(raw)[:80], "reason": "unknown or malformed op"})
                continue
            name, args = raw["op"], dict(raw.get("args") or {})
            spec, why = CAPABILITY[name], None
            for a, kind in spec["args"].items():
                v = args.get(a)
                if kind == "col":
                    if v not in cols:
                        why = f"column {v!r} does not exist"
                    elif spec["cols"] == "text" and "VARCHAR" not in cols[v]:
                        why = f"column {v!r} is not text"
                elif kind in ("cols", "cols?"):
                    if v is None and kind == "cols":
                        why = f"missing arg {a!r}"
                    elif v is not None:
                        if not isinstance(v, list) or any(x not in cols for x in v):
                            why = f"{a}: unknown column(s)"
                elif isinstance(kind, list):
                    if v not in kind:
                        why = f"{a} must be one of {kind}"
                elif kind == "map":
                    if not isinstance(v, dict) or not v or any(
                            not isinstance(k, str) or not isinstance(x, (str, int, float)) for k, x in v.items()):
                        why = f"{a} must be a non-empty string mapping"
                elif kind == "str":
                    if not isinstance(v, str) or not v or len(v) > 500:
                        why = f"{a} must be a short string"
                if why:
                    break
            if not why and name == "regex_replace":
                try:
                    re.compile(args["pattern"])
                except re.error as e:
                    why = f"invalid regex: {e}"
            if not why and name == "fill_missing" and args.get("strategy") in ("mean", "median"):
                t = cols[args["column"]]
                if not any(k in t for k in ("INT", "DOUBLE", "FLOAT", "DECIMAL", "BIGINT")):
                    why = "mean/median need a numeric column"
            if not why and name == "fill_missing" and args.get("strategy") == "constant" and "value" not in args:
                why = "constant fill needs a value"
            (rejected if why else valid).append(
                {"op": name, "reason": why} if why else {"op": name, "args": args,
                                                         "reason": str(raw.get("reason", ""))[:300]})
        return valid, rejected

    # -- executor: each handler returns {sql:[...], affected:int, examples:[...]}
    def _run_op(self, table: str, op: dict) -> dict:
        name, a = op["op"], op.get("args", {})
        con, qt = self.con, _q(table)
        sqls: list[str] = []
        affected, examples = 0, []

        def run(s: str) -> None:
            sqls.append(s)
            con.execute(s)

        def count(where: str) -> int:
            return con.execute(f"SELECT COUNT(*) FROM {qt} WHERE {where}").fetchone()[0]

        def sample(col: str, where: str, expr: str) -> list[dict]:
            rows = con.execute(
                f"SELECT DISTINCT CAST({_q(col)} AS VARCHAR) b, CAST({expr} AS VARCHAR) a "
                f"FROM {qt} WHERE {where} LIMIT 5").fetchall()
            return [{"before": b, "after": x} for b, x in rows]

        if name == "trim_whitespace":
            for c in (a.get("columns") or self._text_cols()):
                w = f"{_q(c)} IS NOT NULL AND {_q(c)} <> TRIM({_q(c)})"
                k = count(w)
                if k:
                    examples += sample(c, w, f"TRIM({_q(c)})")[: max(0, 5 - len(examples))]
                    run(f"UPDATE {qt} SET {_q(c)} = TRIM({_q(c)}) WHERE {w}")
                affected += k
        elif name == "normalize_nulls":
            toks = [str(t).lower() for t in (a.get("tokens") or ["", "na", "n/a", "null", "none", "-", "nan"])]
            lit = ", ".join("'" + t.replace("'", "''") + "'" for t in toks)
            for c in (a.get("columns") or self._text_cols()):
                w = f"{_q(c)} IS NOT NULL AND LOWER(TRIM({_q(c)})) IN ({lit})"
                k = count(w)
                if k:
                    run(f"UPDATE {qt} SET {_q(c)} = NULL WHERE {w}")
                affected += k
        elif name == "normalize_case":
            c, fn = a["column"], ("UPPER" if a["mode"] == "upper" else "LOWER")
            w = f"{_q(c)} IS NOT NULL AND {_q(c)} <> {fn}({_q(c)})"
            affected = count(w)
            examples = sample(c, w, f"{fn}({_q(c)})")
            run(f"UPDATE {qt} SET {_q(c)} = {fn}({_q(c)}) WHERE {w}")
        elif name == "rename_column":
            new = re.sub(r"\W+", "_", a["new_name"]).strip("_") or "col"
            run(f"ALTER TABLE {qt} RENAME COLUMN {_q(a['column'])} TO {_q(new)}")
            affected = self.row_count(table)
        elif name == "drop_columns":
            for c in a["columns"]:
                run(f"ALTER TABLE {qt} DROP COLUMN {_q(c)}")
            affected = self.row_count(table)
        elif name == "cast_column":
            c, ty = a["column"], {"int": "BIGINT", "double": "DOUBLE", "date": "DATE",
                                  "varchar": "VARCHAR", "boolean": "BOOLEAN"}[a["type"]]
            bad = count(f"{_q(c)} IS NOT NULL AND TRY_CAST({_q(c)} AS {ty}) IS NULL")
            cols = list(self.columns(table))
            sel = ", ".join(f"TRY_CAST({_q(x)} AS {ty}) AS {_q(x)}" if x == c else _q(x) for x in cols)
            run(f"CREATE OR REPLACE TABLE {qt} AS SELECT {sel} FROM {qt}")
            affected = bad
            examples = [{"note": f"{bad} unparseable value(s) became NULL"}]
        elif name == "dedupe_rows":
            before = self.row_count(table)
            subset = a.get("subset")
            if subset:
                part = ", ".join(_q(c) for c in subset)
                run(f"CREATE OR REPLACE TABLE {qt} AS "
                    f"WITH t AS (SELECT *, ROW_NUMBER() OVER () AS _rn FROM {qt}) "
                    f"SELECT * EXCLUDE (_rn) FROM t "
                    f"QUALIFY ROW_NUMBER() OVER (PARTITION BY {part} ORDER BY _rn) = 1")
            else:
                run(f"CREATE OR REPLACE TABLE {qt} AS SELECT DISTINCT * FROM {qt}")
            affected = before - self.row_count(table)
        elif name == "drop_rows_where":
            c = _q(a["column"])
            w = f"{c} IS NULL" if a["condition"] == "is_null" else \
                f"CAST({c} AS VARCHAR) = '" + str(a.get("value", "")).replace("'", "''") + "'"
            affected = count(w)
            run(f"DELETE FROM {qt} WHERE {w}")
        elif name == "fill_missing":
            c, st = a["column"], a["strategy"]
            if st in ("mean", "median"):
                fn = "AVG" if st == "mean" else "MEDIAN"
                v = con.execute(f"SELECT {fn}({_q(c)}) FROM {qt}").fetchone()[0]
                expr = "NULL" if v is None else str(v)
            elif st == "zero":
                expr = "0"
            else:
                expr = "'" + str(a["value"]).replace("'", "''") + "'"
            affected = count(f"{_q(c)} IS NULL")
            run(f"UPDATE {qt} SET {_q(c)} = {expr} WHERE {_q(c)} IS NULL")
        elif name == "replace_values":
            c = a["column"]
            for frm, to in a["mapping"].items():
                w = f"CAST({_q(c)} AS VARCHAR) = '" + frm.replace("'", "''") + "'"
                affected += count(w)
                run(f"UPDATE {qt} SET {_q(c)} = '" + str(to).replace("'", "''") + f"' WHERE {w}")
        elif name == "regex_replace":
            c, p, r_ = a["column"], a["pattern"].replace("'", "''"), str(a["replacement"]).replace("'", "''")
            w = f"{_q(c)} IS NOT NULL AND regexp_matches({_q(c)}, '{p}')"
            affected = count(w)
            examples = sample(c, w, f"regexp_replace({_q(c)}, '{p}', '{r_}', 'g')")
            run(f"UPDATE {qt} SET {_q(c)} = regexp_replace({_q(c)}, '{p}', '{r_}', 'g') WHERE {w}")
        return {"op": name, "args": a, "affected": affected, "examples": examples, "sql": sqls}

    def preview(self, ops: list[dict]) -> dict:
        """Run approved ops on a THROWAWAY clone; `work` is untouched."""
        valid, rejected = self.validate_plan(ops)
        self.con.execute('CREATE OR REPLACE TABLE _preview AS SELECT * FROM "work"')
        try:
            results = [self._run_op("_preview", op) for op in valid]
            after = self.row_count("_preview")
        finally:
            self.con.execute("DROP TABLE IF EXISTS _preview")
        return {"results": results, "rejected": rejected,
                "rows_before": self.row_count(), "rows_after": after, "committed": False}

    def apply(self, ops: list[dict]) -> dict:
        """Execute the user-APPROVED ops on `work`; append to the recipe."""
        valid, rejected = self.validate_plan(ops)
        results = [self._run_op("work", op) for op in valid]
        self.meta.setdefault("recipe", []).extend(
            [{"op": r["op"], "args": r["args"], "affected": r["affected"],
              "sql": r["sql"], "ts": time.time()} for r in results])
        self._save()
        return {"results": results, "rejected": rejected,
                "rows": self.row_count(), "recipe": self.meta["recipe"], "committed": True}

    def reset(self) -> dict:
        self.con.execute('CREATE OR REPLACE TABLE "work" AS SELECT * FROM "pristine"')
        self.meta["recipe"] = []
        self._save()
        return {"rows": self.row_count(), "recipe": []}

    def export_csv(self) -> str:
        path = os.path.join(self.folder, "cleaned.csv")
        self.con.execute(f"COPY \"work\" TO '{path}' (HEADER, DELIMITER ',')")
        return path

    # -- LLM proposal: same registry as the chat, but NO TOOLS ----------------
    def propose(self, instruction: str, model: str | None = None) -> dict:
        from core.llm import get_provider
        provider = get_provider(model)
        system = ("You are a data-cleaning planner. You have NO tools and CANNOT run anything. "
                  "Given the column profile below, propose a cleaning plan as a PURE JSON array "
                  "(no prose, no markdown) of {\"op\", \"args\", \"reason\"} objects, using ONLY "
                  "these operations:\n" + capability_doc() +
                  "\nCite evidence from the profile in each reason. Propose only what the "
                  "profile supports; do not invent columns.")
        user = ("PROFILE:\n" + json.dumps(self.profile()) +
                "\n\nUSER REQUEST: " + (instruction or "clean this table sensibly"))
        resp = provider.chat([{"role": "system", "content": system},
                              {"role": "user", "content": user}], tools=None)
        text = (resp.content or "").strip()
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
        try:
            raw = json.loads(text)
            if not isinstance(raw, list):
                raise ValueError("not a list")
        except Exception:
            return {"plan": [], "rejected": [], "note": "model did not return a valid JSON plan",
                    "model": model}
        valid, rejected = self.validate_plan(raw)
        return {"plan": valid, "rejected": rejected, "model": model}


class SessionStore:
    """Folder-backed registry under WB_ROOT/<scope>/wb_<id>/, realpath-confined."""

    def __init__(self, root: str = WB_ROOT):
        self.root = os.path.abspath(root)
        os.makedirs(self.root, exist_ok=True)

    def _scope_dir(self, scope: str) -> str:
        d = os.path.join(self.root, re.sub(r"\W+", "_", scope or "default") or "default")
        os.makedirs(d, exist_ok=True)
        return d

    def _folder(self, scope: str, sid: str) -> str:
        if not _SID_RE.match(sid or ""):
            raise ValueError("invalid session id")
        f = os.path.realpath(os.path.join(self._scope_dir(scope), sid))
        if not (f + os.sep).startswith(os.path.realpath(self.root) + os.sep):
            raise ValueError("session path escapes the workbench root")
        return f

    def list(self, scope: str) -> list[dict]:
        d = self._scope_dir(scope)
        out = []
        for sid in sorted(os.listdir(d)):
            mp = os.path.join(d, sid, "session.json")
            if _SID_RE.match(sid) and os.path.exists(mp):
                m = json.load(open(mp))
                out.append({"sid": sid, "source_view": m.get("source_view"),
                            "created": m.get("created"), "ops_applied": len(m.get("recipe", []))})
        return out

    def get(self, scope: str, sid: str) -> WorkbenchSession:
        f = self._folder(scope, sid)
        if not os.path.exists(os.path.join(f, "session.json")):
            raise KeyError(sid)
        return WorkbenchSession(sid, f)

    def delete(self, scope: str, sid: str) -> None:
        s = self.get(scope, sid)
        if s._con:
            s._con.close()
        shutil.rmtree(self._folder(scope, sid))

    # -- recipe library: save a session's recipe, re-apply to future files -----
    def _recipes_path(self, scope: str) -> str:
        return os.path.join(self._scope_dir(scope), "recipes.json")

    def list_recipes(self, scope: str) -> list[dict]:
        p = self._recipes_path(scope)
        return json.load(open(p)) if os.path.exists(p) else []

    def save_recipe(self, scope: str, sid: str, name: str) -> dict:
        ses = self.get(scope, sid)
        ops = [{"op": r["op"], "args": r["args"]} for r in ses.meta.get("recipe", [])]
        if not ops:
            raise ValueError("this session has no applied operations to save")
        recs = self.list_recipes(scope)
        rec = {"id": "rc_" + secrets.token_hex(5), "name": (name or "My recipe")[:80],
               "ops": ops, "source_view": ses.meta.get("source_view"), "created": time.time()}
        recs.append(rec)
        with open(self._recipes_path(scope), "w", encoding="utf-8") as f:
            json.dump(recs, f, indent=1)
        return rec

    def apply_recipe(self, scope: str, sid: str, recipe_id: str) -> dict:
        """Re-apply a saved recipe to a NEW session. Ops that don't fit the new
        table (e.g. missing columns) are SKIPPED with reasons — never guessed."""
        rec = next((r for r in self.list_recipes(scope) if r["id"] == recipe_id), None)
        if not rec:
            raise KeyError(recipe_id)
        ses = self.get(scope, sid)
        result = ses.apply(rec["ops"])   # validate_plan inside drops misfits
        result["recipe_name"] = rec["name"]
        result["skipped"] = result.pop("rejected")
        return result

    def create_from_view(self, scope: str, view: str, ctx) -> WorkbenchSession:
        """Copy an upload-backed file (or materialize any queryable view) into a
        fresh session; source is hashed and NEVER opened for write."""
        if len(self.list(scope)) >= MAX_SESSIONS:
            raise ValueError(f"session limit ({MAX_SESSIONS}) reached — delete one first")
        sid = "wb_" + secrets.token_hex(5)
        folder = os.path.join(self._scope_dir(scope), sid)
        os.makedirs(folder)
        meta = {"source_view": view, "created": time.time(), "recipe": []}
        try:
            duck = ctx.upload_duck() if hasattr(ctx, "upload_duck") else None
            src = _find_source(duck, view) if duck else None
            ses = WorkbenchSession(sid, folder, meta)
            if src and os.path.exists(src):
                meta["source_file"] = os.path.basename(src)
                meta["source_sha256"] = _sha256(src)
                copy = os.path.join(folder, "original" + os.path.splitext(src)[1].lower())
                shutil.copy(src, copy)  # read source, write only inside the session
                # re-ingest the COPY with the platform's own ingestion (throwaway
                # connector on an isolated subdir) and materialize the chosen view
                from connectors.duckdb_conn import DuckDBConnector
                ing_dir = os.path.join(folder, "_ingest")
                os.makedirs(ing_dir)
                shutil.copy(copy, os.path.join(ing_dir, os.path.basename(src)))
                tmp = DuckDBConnector(data_dir=ing_dir)
                if view not in getattr(tmp, "_views", []):
                    raise ValueError(f"view {view!r} not found in the copied file "
                                     f"(available: {getattr(tmp, '_views', [])})")
                df = tmp.con.execute(f"SELECT * FROM {_q(view)}").df()
                shutil.rmtree(ing_dir, ignore_errors=True)
            else:
                # connector-backed (live DB / demo DB): materialize read-only
                qr = ctx.connector.run_query(f"SELECT * FROM {_q(view)} LIMIT {MAX_ROWS + 1}")
                if len(qr.rows) > MAX_ROWS:
                    raise ValueError(f"table exceeds workbench limit ({MAX_ROWS} rows)")
                import pandas as pd
                df = pd.DataFrame(qr.rows, columns=qr.columns)
                meta["source_file"] = None
            if df is None or df.empty:
                raise ValueError("source produced no rows")
            ses.con.register("_incoming", df)
            ses.con.execute('CREATE TABLE "work" AS SELECT * FROM _incoming')
            ses.con.execute('CREATE TABLE "pristine" AS SELECT * FROM "work"')
            ses.meta = meta
            ses._save()
            return ses
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise
