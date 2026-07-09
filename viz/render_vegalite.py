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

    base = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "title": title,
        "width": "container",
        "data": {"values": rows},
    }
    if ctype == "pie":
        base["mark"] = {"type": "arc", "tooltip": True, "stroke": "#fff", "strokeWidth": 1}
        base["encoding"] = {"theta": {"field": enc["value"], "type": "quantitative"},
                            "color": {"field": enc["category"], "type": "nominal"}}
        return base

    temporal = _looks_temporal(enc["x"], rows)
    x_enc = {"field": enc["x"], "type": "temporal" if temporal else "nominal"}
    if not temporal:                       # rotate labels so many categories don't cram/overlap
        x_enc["axis"] = {"labelAngle": -40, "labelLimit": 140}
    y_enc = {"field": enc["y"], "type": "quantitative"}
    series = enc.get("series")
    enc_obj = {"x": x_enc, "y": y_enc}
    if series:
        enc_obj["color"] = {"field": series, "type": "nominal"}
        if ctype == "bar":                 # grouped (side-by-side), not overlapping/stacked
            enc_obj["xOffset"] = {"field": series, "type": "nominal"}
    mark = {"type": _MARK[ctype], "tooltip": True,
            **({"cornerRadiusEnd": 3} if ctype == "bar" else {}),
            **({"point": True} if ctype == "line" else {})}

    # selective direct value labels: only for a single series with few marks
    # (the skill's rule — never a number on every point of a crowded chart).
    if ctype in ("bar", "line") and not series and len(rows) <= 16:
        base["layer"] = [
            {"mark": mark, "encoding": enc_obj},
            {"mark": {"type": "text", "dy": -7, "fontSize": 10, "color": "#3a525c"},
             "encoding": {**enc_obj,
                          "text": {"field": enc["y"], "type": "quantitative", "format": ".3~s"}}},
        ]
    else:
        base["mark"] = mark
        base["encoding"] = enc_obj
    return base


def _looks_temporal(field: str, rows: list[dict]) -> bool:
    if any(k in field.lower() for k in ("date", "month", "year", "day", "time", "week")):
        return True
    return False
