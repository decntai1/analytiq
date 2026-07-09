"""
Neutral chart spec + capability schema + validator.

The doc's key insight (Step 4-6): the LLM emits a NEUTRAL internal chart spec, NOT
a Vega-Lite or Grafana payload. A renderer adapter then converts it to whichever
surface. This keeps the model simple and makes the viz backend swappable
(Vega-Lite now, Grafana later) without re-prompting.

CAPABILITY is the doc's "dashboard capability schema" — declared, not learned. The
validator rejects anything the LLM proposes that violates these rules, so an
invalid chart is caught before it renders (the doc's critical validation layer).
"""
from __future__ import annotations

# --- declared capability (source-of-truth B) -------------------------------
CAPABILITY = {
    "chart_types": ["bar", "line", "area", "scatter", "pie", "table"],
    "rules": {
        "line_requires": ["x", "y"],
        "area_requires": ["x", "y"],
        "bar_requires": ["x", "y"],
        "scatter_requires": ["x", "y"],
        "pie_requires": ["category", "value"],
        "table_requires": [],
    },
}


def validate_spec(spec: dict) -> None:
    """Raise ValueError if the neutral spec violates the declared capability."""
    if not isinstance(spec, dict):
        raise ValueError("Chart spec must be an object.")
    ctype = spec.get("type")
    if ctype not in CAPABILITY["chart_types"]:
        raise ValueError(f"Unsupported chart type {ctype!r}. Allowed: {CAPABILITY['chart_types']}")
    required = CAPABILITY["rules"].get(f"{ctype}_requires", [])
    enc = spec.get("encoding", {})
    missing = [r for r in required if r not in enc]
    if missing:
        raise ValueError(f"Chart type {ctype!r} requires encoding fields {missing}.")


# neutral spec shape (what the LLM emits via the make_chart tool):
# {
#   "type": "line",
#   "title": "Sales vs Spendings vs Production",
#   "encoding": {"x": "month", "y": "value", "series": "metric"}  # column names
# }
