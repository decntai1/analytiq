"""
Intent router — the doc's Step 1 (intent + plan, before any SQL).

Classifies the question into which retrieval arm(s) to use:
  - "structured":   quantitative -> schema-RAG -> SQL -> (optional) chart
  - "unstructured": qualitative -> document-RAG -> grounded answer
  - "both":         needs numbers AND context (e.g. "why did revenue drop?")

We let the LLM route (one cheap classify call) rather than keyword-matching, so it
generalises. The router only decides; the orchestrator executes the chosen arms.
"""
from __future__ import annotations

import json

from core.llm import BaseProvider

_ROUTER_SYSTEM = """Classify a business question for an analytics system.
Return ONLY JSON: {"arm": "structured|unstructured|both", "wants_chart": true|false}.
- structured: answerable from database tables / metrics / numbers.
- unstructured: answerable from documents, policies, notes, free text.
- both: needs numbers AND surrounding context/explanation.
- wants_chart: true if a visualization would help or is requested.
No prose, JSON only."""


def route(provider: BaseProvider, question: str) -> dict:
    resp = provider.chat(
        [{"role": "system", "content": _ROUTER_SYSTEM},
         {"role": "user", "content": question}],
        tools=None,
    )
    try:
        data = json.loads((resp.content or "").strip().strip("`").lstrip("json").strip())
        arm = data.get("arm", "structured")
        if arm not in ("structured", "unstructured", "both"):
            arm = "structured"
        return {"arm": arm, "wants_chart": bool(data.get("wants_chart", False))}
    except Exception:
        # safe default: try structured with a chart
        return {"arm": "structured", "wants_chart": True}
