"""
Orchestrator — the agent loop tying both arms together (DEcntAI loop.js analog).

Flow (matches the doc's reference architecture):
  question
    -> route()                       intent: structured / unstructured / both
    -> schema-RAG (if structured)    inject ONLY the top-K relevant tables
    -> LLM tool loop:
         run_sql          -> rows
         search_documents -> grounded passages (with sources)
         make_chart       -> neutral spec -> validate -> Vega-Lite
    -> final grounded answer + charts + citations + sql_log

The model is selectable per call (thesis comparison): pass model_name through.

SCAFFOLDING is the thesis independent variable. Each config.settings.scaffold_* flag
flips one deterministic layer on/off so the eval can measure accuracy as a
function of scaffolding-level across model sizes:
  - scaffold_router        : intent routing vs. always-structured
  - scaffold_schema_rag    : retrieve top-K tables vs. dump the ENTIRE schema (the
                             "no retrieval" baseline that stresses the scaling claim)
  - scaffold_glossary      : inject metric definitions vs. not
  - scaffold_validate_chart: reject invalid chart specs vs. pass them through
  - scaffold_repair        : feed tool errors back for a retry vs. not
"""
from __future__ import annotations

import json
import os
from typing import Any

import config
from connectors.base import StructuredConnector
from core.llm import get_provider
from core.router import route
from core.tools import TOOLS
from index.doc_index import DocIndex
from index.schema_index import SchemaIndex
from viz.render_vegalite import to_vegalite
from viz.spec import validate_spec

SYSTEM = """You are an analytics agent for a business-intelligence product.
You answer questions about a company's data using the tools provided.

Tables you may query:
{schema}
{glossary}
Rules:
- Write correct, read-only SQL (SELECT/WITH only) over the tables above. Aggregate in SQL.
- For visualizations call make_chart with a neutral spec (no data field; rows are bound).
- You MAY produce more than one chart (up to 4) when the question warrants it: e.g.
  the same data two ways ("as a bar and a pie"), or a broad/"overview" question broken
  into a few distinct query+chart pairs. make_chart charts the MOST RECENT query's
  rows, so INTERLEAVE strictly: run_sql -> make_chart -> run_sql -> make_chart (never
  run two queries before charting the first). Prefer one clear chart unless multiple
  genuinely add value; do not pad.
- For qualitative/"why"/policy questions call search_documents and ground your answer
  in the returned passages, citing sources.
- Keep the final answer concise and grounded strictly in tool results. Do not invent numbers.
"""


def _load_glossary() -> str:
    """Optional metric definitions (source-of-truth C). Returns a prompt block."""
    if not config.settings.scaffold_glossary or not os.path.exists(config.settings.glossary_path):
        return ""
    try:
        with open(config.settings.glossary_path, encoding="utf-8") as f:
            g = json.load(f)
        if not g:
            return ""
        lines = "\n".join(f"  - {k} = {v}" for k, v in g.items())
        return f"\nMetric definitions (use these exactly):\n{lines}\n"
    except Exception:
        return ""


class Orchestrator:
    def __init__(
        self,
        connector: StructuredConnector,
        schema_index: SchemaIndex,
        doc_index: DocIndex | None = None,
    ) -> None:
        self.connector = connector
        self.schema_index = schema_index
        self.doc_index = doc_index

    def _schema_context(self, question: str, tables: list[str] | None = None) -> str:
        """User table-scope (deterministic) > schema-RAG top-K > dump-everything baseline."""
        by = self.connector.schema_by_table()
        if tables:
            # user forced which tables this question sees — exact, no retrieval guessing
            chosen = [t for t in tables if t in by]
            ctx = "\n".join(by[t] for t in chosen)
        elif config.settings.scaffold_schema_rag:
            ctx = self.schema_index.relevant_tables(question, config.settings.schema_top_k)
        else:
            # no-retrieval baseline: dump everything (what breaks at 100 tables)
            ctx = "\n".join(by.values())
        # record which tables ended up in context (for the table-recall metric)
        self._last_tables = [ln.split()[1] for ln in ctx.splitlines() if ln.startswith("TABLE")]
        return ctx

    def ask(self, question: str, model_name: str | None = None,
            history: list[dict] | None = None,
            spec_override: Any = None,
            tables: list[str] | None = None) -> dict[str, Any]:
        # reset per question: unstructured-arm runs must report NO retrieved tables,
        # not the previous question's (would corrupt the eval's table-recall metric
        # when one Orchestrator instance is reused, as eval/score.py does).
        self._last_tables: list[str] = []
        provider = get_provider(model_name, spec_override=spec_override)

        # router ON: classify intent. OFF: assume structured+chart.
        if config.settings.scaffold_router:
            plan = route(provider, question)
        else:
            plan = {"arm": "structured", "wants_chart": True, "router": "off"}

        schema_ctx = ""
        if plan["arm"] in ("structured", "both"):
            schema_ctx = self._schema_context(question, tables)

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM.format(
                schema=schema_ctx or "(none retrieved)", glossary=_load_glossary())},
        ]
        # session memory (plan-gated by the caller): prior turns are re-fed here
        # because the model itself is stateless — the app owns the memory.
        for m in (history or []):
            if m.get("role") in ("user", "assistant") and m.get("content"):
                messages.append({"role": m["role"], "content": m["content"]})
        messages.append({"role": "user", "content": question})
        charts: list[dict] = []
        citations: list[dict] = []
        sql_log: list[str] = []
        errors: list[str] = []
        last_rows: list[dict] | None = None

        for _ in range(config.settings.max_steps):
            resp = provider.chat(messages, tools=TOOLS)
            if not resp.tool_calls:
                return self._result(resp.content or "", plan, charts, citations,
                                    sql_log, errors, model_name)

            messages.append({
                "role": "assistant",
                "content": resp.content,
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.name, "arguments": tc.arguments}}
                    for tc in resp.tool_calls
                ],
            })
            for tc in resp.tool_calls:
                try:
                    args = json.loads(tc.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                content, last_rows, err = self._dispatch(tc.name, args, last_rows,
                                                         charts, citations, sql_log)
                if err:
                    errors.append(err)
                    # repair ON: tell the model what went wrong so it can retry.
                    # repair OFF: still return a neutral message but no corrective hint.
                    content = (f"ERROR: {err}. Fix and try again."
                               if config.settings.scaffold_repair else "Tool call failed.")
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})

        return self._result("Step limit reached; partial results.", plan, charts,
                            citations, sql_log, errors, model_name)

    def _result(self, answer, plan, charts, citations, sql_log, errors, model_name):
        return {"answer": answer, "plan": plan, "charts": charts, "citations": citations,
                "sql_log": sql_log, "errors": errors,
                "tables_retrieved": getattr(self, "_last_tables", []),
                "scaffold": config.settings.scaffold_label(),
                "model": model_name or config.settings.default_model}

    def _dispatch(self, name, args, last_rows, charts, citations, sql_log):
        """Returns (content_for_model, last_rows, error_or_None)."""
        if name == "run_sql":
            q = args.get("query", "")
            sql_log.append(q)
            try:
                qr = self.connector.run_query(q)
            except Exception as e:
                return "", last_rows, f"SQL error: {e}"
            note = " (truncated)" if qr.truncated else ""
            return (json.dumps({"columns": qr.columns, "rows": qr.rows[:50],
                                "row_count": len(qr.rows)}) + note, qr.rows, None)

        if name == "make_chart":
            if not last_rows:
                return "", last_rows, "No query results to chart yet. Run a query first."
            if len(charts) >= 4:   # deterministic cap — a vague prompt can't spawn a wall of charts
                return "Chart limit reached (4). Summarise instead of adding more charts.", last_rows, None
            spec = {"type": args.get("type"), "title": args.get("title", ""),
                    "encoding": args.get("encoding", {})}
            try:
                # validate ON: enforce capability rules. OFF: render whatever was asked.
                if config.settings.scaffold_validate_chart:
                    validate_spec(spec)
                rendered = to_vegalite(spec, last_rows)
            except Exception as e:
                return "", last_rows, f"Chart error: {e}"
            charts.append(rendered)
            return "Chart rendered.", last_rows, None

        if name == "search_documents":
            if not self.doc_index:
                return "", last_rows, "No document index configured."
            hits = self.doc_index.retrieve(args.get("query", ""), config.settings.doc_top_k)
            for h in hits:
                citations.append({"source": h["source"], "score": h["score"]})
            return json.dumps({"passages": hits}), last_rows, None

        return "", last_rows, f"Unknown tool: {name}"
