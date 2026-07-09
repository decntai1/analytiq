"""
Vega-Lite renderer adapter.

Converts a validated NEUTRAL chart spec + data rows into a portable Vega-Lite v5
spec the frontend renders with vega-embed (or vl-convert -> PNG for slides).
This is one adapter behind viz/spec.py; render_grafana.py is the sibling for later.
"""
from __future__ import annotations

_MARK = {"bar": "bar", "line": "line", "area": "area", "scatter": "point", "pie": "arc"}


def _has_numeric(rows: list[dict], field: str | None) -> bool:
    """True if `field` has at least one non-null numeric value (so a chart won't be empty)."""
    if not field:
        return True
    for r in rows:
        v = r.get(field)
        if v is None:
            continue
        try:
            float(v)
            return True
        except (TypeError, ValueError):
            continue
    return False


def to_vegalite(spec: dict, rows: list[dict]) -> dict:
    ctype = spec["type"]
    enc = spec.get("encoding", {})
    title = spec.get("title", "")

    if ctype == "table":
        # tables aren't Vega-Lite; return a typed payload the UI renders as a grid
        return {"_kind": "table", "title": title, "columns": list(rows[0].keys()) if rows else [],
                "rows": rows}

    # empty / non-plottable fallback: no rows, or the measure column (y/value) has no
    # numeric data (e.g. charting a text column) -> show the rows as a table, not an
    # empty chart frame. Keeps the answer honest instead of rendering a blank plot.
    measure = enc.get("y") or enc.get("value")
    if not rows or not _has_numeric(rows, measure):
        return {"_kind": "table",
                "title": (f"{title} — no chartable data, showing rows".strip(" —")) or "No chartable data",
                "columns": list(rows[0].keys()) if rows else [], "rows": rows}

    vl: dict = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "title": title,
        "width": "container",
        "data": {"values": rows},
        "mark": {"type": _MARK[ctype], "tooltip": True,
                 **({"point": True} if ctype == "line" else {})},
        "encoding": {},
    }
    e = vl["encoding"]
    if ctype == "pie":
        e["theta"] = {"field": enc["value"], "type": "quantitative"}
        e["color"] = {"field": enc["category"], "type": "nominal"}
        return vl

    e["x"] = {"field": enc["x"], "type": "temporal" if _looks_temporal(enc["x"], rows) else "nominal"}
    e["y"] = {"field": enc["y"], "type": "quantitative"}
    if "series" in enc:
        e["color"] = {"field": enc["series"], "type": "nominal"}
    return vl


def _looks_temporal(field: str, rows: list[dict]) -> bool:
    if any(k in field.lower() for k in ("date", "month", "year", "day", "time", "week")):
        return True
    return False
