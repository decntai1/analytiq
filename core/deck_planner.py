"""
Deck planner — turns a high-level report request into a finished deck.

Flow (the Director pattern, one level up):
  "Make a Q4 board deck"
    -> LLM plans a slide OUTLINE (title + a data question per content slide)
    -> for each slide: run the normal orchestrator -> answer + chart + sql
    -> assemble into a deck spec (title, summary, chart slides, audit appendix)
    -> presentation.build_deck() -> editable .pptx bytes

The audit appendix is auto-collected from every slide's SQL, so the deck carries
its own receipts. Charts are the real Vega-Lite specs the pipeline produced.
"""
from __future__ import annotations

import json

from core.llm import get_provider
from core.orchestrator import Orchestrator
from viz.presentation import build_deck

_OUTLINE_SYSTEM = """You plan a business presentation from a user's request.
Return ONLY JSON, no prose:
{
 "title": "<deck title>",
 "subtitle": "<one line>",
 "slides": [
   {"heading": "<slide title>", "question": "<a specific data question to answer for this slide>"}
 ]
}
Make 3-6 content slides. Each 'question' must be answerable from the company's data and
should produce a chart where sensible. Order them as a narrative (overview -> detail -> why -> outlook)."""


def plan_outline(provider, request: str) -> dict:
    resp = provider.chat(
        [{"role": "system", "content": _OUTLINE_SYSTEM},
         {"role": "user", "content": request}], tools=None)
    raw = (resp.content or "").strip().strip("`")
    if raw.lower().startswith("json"):
        raw = raw[4:].strip()
    try:
        data = json.loads(raw)
        assert "slides" in data and isinstance(data["slides"], list)
        return data
    except Exception:
        # fallback: single-slide deck from the raw request
        return {"title": request[:60], "subtitle": "",
                "slides": [{"heading": request[:60], "question": request}]}


def generate_presentation(
    request: str,
    orchestrator: Orchestrator,
    model_name: str | None = None,
    template_path: str | None = None,
) -> tuple[bytes, dict]:
    """Returns (pptx_bytes, plan_meta). plan_meta has the outline + per-slide trace."""
    provider = get_provider(model_name)
    outline = plan_outline(provider, request)

    deck: list[dict] = [{"type": "title", "title": outline.get("title", "Report"),
                         "subtitle": outline.get("subtitle", "")}]
    summary_bullets: list[str] = []
    appendix: list[dict] = []
    trace: list[dict] = []

    for sl in outline.get("slides", []):
        q = sl.get("question", "")
        heading = sl.get("heading", q[:50])
        res = orchestrator.ask(q, model_name=model_name)
        answer = res.get("answer", "")
        charts = res.get("charts", [])
        sqls = res.get("sql_log", [])

        if charts:
            deck.append({"type": "chart", "title": heading, "takeaway": answer,
                         "chart": charts[0]})
        else:
            # no chart -> render as a text/summary slide
            deck.append({"type": "summary", "title": heading,
                         "bullets": [answer] if answer else ["(no result)"]})
        if answer:
            summary_bullets.append(f"{heading}: {answer[:160]}")
        for sq in sqls:
            appendix.append({"title": heading, "sql": sq})
        trace.append({"heading": heading, "question": q, "charts": len(charts),
                      "sql": len(sqls), "tables": res.get("tables_retrieved", [])})

    # insert an executive summary right after the title
    if summary_bullets:
        deck.insert(1, {"type": "summary", "title": "Executive summary",
                        "bullets": summary_bullets[:6]})
    # audit appendix at the end (the defensibility slide)
    if appendix:
        deck.append({"type": "appendix", "items": appendix})

    pptx = build_deck(deck, template_path=template_path)
    return pptx, {"outline": outline, "slides": len(deck), "trace": trace}
