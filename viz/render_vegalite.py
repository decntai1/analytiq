"""
Vega-Lite renderer adapter.

Converts a validated NEUTRAL chart spec + data rows into a portable Vega-Lite v5
spec the frontend renders with vega-embed (or vl-convert -> PNG for slides).
This is one adapter behind viz/spec.py; render_grafana.py is the sibling for later.

Statistical types (histogram/boxplot/heatmap/density/stacked_*/rolling_line and
scatter trend overlays) are emitted as declarative Vega-Lite transforms — bin,
boxplot, rect, density, stack, window, regression/loess. NO statistic is computed
here in Python and none is invented; Vega-Lite computes them from the bound rows,
so the fabrication invariant is untouched.
"""
from __future__ import annotations

from index.region_lookup import BASEMAPS, resolve_choropleth

_MARK = {"bar": "bar", "line": "line", "area": "area", "scatter": "point", "pie": "arc"}

_LABEL_COLOR = "#3a525c"
_TREND_COLOR = "#d4453f"
_POINT_COLOR = "#2b6b7a"
_LAND_FILL = "#eef3f4"
_LAND_STROKE = "#d6e0e2"
_GEO_HEIGHT = 360               # maps need an explicit height (geoshape has no implicit extent)
_GEO_RESOLVE_MIN = 0.8          # <80% of region values resolve -> honest refusal, not a wrong map


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


def _table(title: str, rows: list[dict]) -> dict:
    return {"_kind": "table", "title": title,
            "columns": list(rows[0].keys()) if rows else [], "rows": rows}


def to_vegalite(spec: dict, rows: list[dict]) -> dict:
    ctype = spec["type"]
    enc = spec.get("encoding", {})
    title = spec.get("title", "")

    if ctype == "table":
        # tables aren't Vega-Lite; return a typed payload the UI renders as a grid
        return _table(title, rows)

    # empty / non-plottable fallback: no rows, or the measure column has no numeric
    # data (e.g. charting a text column) -> show the rows as a table, not an empty
    # chart frame. Keeps the answer honest instead of rendering a blank plot. The
    # "measure" is the role carrying the numeric magnitude, which is TYPE-DEPENDENT:
    # heatmap's y is a nominal axis, so its measure is `color`.
    if ctype == "heatmap":
        measure = enc.get("color")
    elif ctype in ("histogram", "density"):
        measure = enc.get("value")
    elif ctype == "choropleth":
        measure = enc.get("value")
    elif ctype == "geo_points":
        measure = enc.get("lat")   # lat/lon must be numeric; non-numeric -> honest table fallback
    else:
        measure = enc.get("y") or enc.get("value") or enc.get("color")
    if not rows or not _has_numeric(rows, measure):
        t = (f"{title} — no chartable data, showing rows".strip(" —")) or "No chartable data"
        return _table(t, rows)

    base = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "title": title,
        "width": "container",
        "data": {"values": rows},
        # neutral type tag: the rendered Vega mark is lossy (histogram->bar,
        # rolling_line->line, density->area all collide), so carry the neutral name
        # for the eval scorer + trace. Vega-Lite ignores unknown top-level keys.
        "_neutral": ctype,
    }

    # --- geographic types (topojson basemap + deterministic id resolution) ---
    # Region names are resolved to topojson feature ids SERVER-SIDE via the frozen
    # index/region_lookup table; the model never emits a region code, and Vega-Lite
    # only shades ids we resolved -> no fabricated geography. The topojson is loaded
    # by same-origin URL (vendored, air-gap safe), not inlined into every response.
    if ctype == "choropleth":
        level = spec.get("region_level", "country")
        bm = BASEMAPS[level]
        values, rate = resolve_choropleth(rows, enc["region"], enc["value"], level)
        if rate < _GEO_RESOLVE_MIN:
            pretty = level.replace("_", " ")
            raise ValueError(
                f"Only {round(rate * 100)}% of the '{enc['region']}' values match known "
                f"{pretty} names or codes (need ≥{round(_GEO_RESOLVE_MIN * 100)}%). "
                f"Region buckets (EMEA/APAC) or unrecognized labels can't be placed on a "
                f"{pretty} map — use a bar chart, or map by a real {pretty} column.")
        if not values:
            raise ValueError(f"No numeric '{enc['value']}' values to place on the map.")
        base.pop("data", None)  # topojson is the geometry source; resolved values are joined in
        base["projection"] = {"type": bm["projection"]}
        base["height"] = _GEO_HEIGHT
        base["data"] = {"url": bm["url"], "format": {"type": "topojson", "feature": bm["feature"]}}
        base["transform"] = [{
            "lookup": "id",
            "from": {"data": {"values": values}, "key": "id", "fields": ["value", "label"]},
        }]
        base["mark"] = {"type": "geoshape", "stroke": "#ffffff", "strokeWidth": 0.5}
        base["encoding"] = {
            "color": {"field": "value", "type": "quantitative",
                      "scale": {"scheme": "teals"},
                      "legend": {"title": title or enc["value"]}},
            "tooltip": [{"field": "label", "type": "nominal", "title": enc["region"]},
                        {"field": "value", "type": "quantitative", "title": enc["value"]}],
        }
        return base

    if ctype == "geo_points":
        lat_f, lon_f = enc["lat"], enc["lon"]
        if not _has_numeric(rows, lon_f):   # lat covered by the measure guard above
            t = (f"{title} — longitude column '{lon_f}' isn't numeric, showing rows").strip(" —")
            return _table(t, rows)
        pt_enc = {
            "longitude": {"field": lon_f, "type": "quantitative"},
            "latitude": {"field": lat_f, "type": "quantitative"},
            "tooltip": [{"field": c} for c in rows[0].keys()],
        }
        mark = {"type": "circle", "opacity": 0.75}
        if enc.get("size"):
            pt_enc["size"] = {"field": enc["size"], "type": "quantitative",
                              "title": enc["size"], "scale": {"range": [20, 400]}}
        if enc.get("color"):
            pt_enc["color"] = {"field": enc["color"], "type": "nominal"}
        else:
            mark["color"] = _POINT_COLOR
        base.pop("data", None)  # each layer carries its own data (basemap vs. points)
        base["projection"] = {"type": "equalEarth"}
        base["height"] = _GEO_HEIGHT
        base["layer"] = [
            {"data": {"url": "/static/vendor/world-110m.json",
                      "format": {"type": "topojson", "feature": "countries"}},
             "mark": {"type": "geoshape", "fill": _LAND_FILL,
                      "stroke": _LAND_STROKE, "strokeWidth": 0.4}},
            {"data": {"values": rows}, "mark": mark, "encoding": pt_enc},
        ]
        return base

    # --- statistical types (declarative transforms) ------------------------
    if ctype == "histogram":
        maxbins = spec.get("maxbins", 20)
        base["mark"] = {"type": "bar", "tooltip": True, "cornerRadiusEnd": 2}
        base["encoding"] = {
            "x": {"field": enc["value"], "type": "quantitative", "bin": {"maxbins": maxbins}},
            "y": {"aggregate": "count", "type": "quantitative", "title": "count"},
        }
        return base

    if ctype == "density":
        field = enc["value"]
        base["transform"] = [{"density": field}]
        base["mark"] = {"type": "area", "tooltip": True, "opacity": 0.75, "line": True}
        base["encoding"] = {
            "x": {"field": "value", "type": "quantitative", "title": field},
            "y": {"field": "density", "type": "quantitative", "title": "density"},
        }
        return base

    if ctype == "boxplot":
        base["mark"] = {"type": "boxplot", "extent": "min-max"}
        enc_obj = {"y": {"field": enc["y"], "type": "quantitative"}}
        if enc.get("x"):
            enc_obj["x"] = {"field": enc["x"], "type": "nominal",
                            "axis": {"labelAngle": -40, "labelLimit": 140}}
            enc_obj["color"] = {"field": enc["x"], "type": "nominal", "legend": None}
        base["encoding"] = enc_obj
        return base

    if ctype == "heatmap":
        base["mark"] = {"type": "rect", "tooltip": True}
        base["encoding"] = {
            "x": {"field": enc["x"], "type": "nominal",
                  "axis": {"labelAngle": -40, "labelLimit": 140}},
            "y": {"field": enc["y"], "type": "nominal"},
            "color": {"field": enc["color"], "type": "quantitative",
                      "scale": {"scheme": "teals"}},
        }
        return base

    if ctype in ("stacked_bar", "stacked_area"):
        # Vega-Lite stacks bar/area by default when a color channel is present and no
        # xOffset is set. Optional normalize -> 100%-stacked.
        temporal = _looks_temporal(enc["x"], rows)
        mark_type = "bar" if ctype == "stacked_bar" else "area"
        stack = "normalize" if spec.get("normalize") else True
        base["mark"] = {"type": mark_type, "tooltip": True}
        base["encoding"] = {
            "x": _x_enc(enc["x"], temporal),
            "y": {"field": enc["y"], "type": "quantitative", "stack": stack},
            "color": {"field": enc["series"], "type": "nominal"},
        }
        return base

    if ctype == "rolling_line":
        window = spec.get("window", 3)
        temporal = _looks_temporal(enc["x"], rows)
        base["transform"] = [{
            "sort": [{"field": enc["x"]}],
            "window": [{"op": "mean", "field": enc["y"], "as": "_rolling"}],
            "frame": [-(window - 1), 0],
        }]
        x_enc = _x_enc(enc["x"], temporal)
        base["layer"] = [
            {"mark": {"type": "line", "color": "#b9cdd2", "opacity": 0.7},
             "encoding": {"x": x_enc, "y": {"field": enc["y"], "type": "quantitative"}}},
            {"mark": {"type": "line", "point": True, "tooltip": True},
             "encoding": {"x": x_enc,
                          "y": {"field": "_rolling", "type": "quantitative",
                                "title": f"{enc['y']} ({window}-pt mean)"}}},
        ]
        return base

    # --- original core types ----------------------------------------------
    if ctype == "pie":
        base["mark"] = {"type": "arc", "tooltip": True, "stroke": "#fff", "strokeWidth": 1}
        base["encoding"] = {"theta": {"field": enc["value"], "type": "quantitative"},
                            "color": {"field": enc["category"], "type": "nominal"}}
        return base

    temporal = _looks_temporal(enc["x"], rows)
    x_enc = _x_enc(enc["x"], temporal)
    y_enc = {"field": enc["y"], "type": "quantitative"}
    series = enc.get("series")

    # scatter with an optional deterministic trend overlay (regression / loess)
    if ctype == "scatter" and spec.get("trend") in ("linear", "loess"):
        pt = {"type": "point", "tooltip": True}
        pt_enc = {"x": x_enc, "y": y_enc}
        if series:
            pt_enc["color"] = {"field": series, "type": "nominal"}
        tkey = "regression" if spec["trend"] == "linear" else "loess"
        base["layer"] = [
            {"mark": pt, "encoding": pt_enc},
            {"transform": [{tkey: enc["y"], "on": enc["x"]}],
             "mark": {"type": "line", "color": _TREND_COLOR},
             "encoding": {"x": x_enc, "y": y_enc}},
        ]
        return base

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
            {"mark": {"type": "text", "dy": -7, "fontSize": 10, "color": _LABEL_COLOR},
             "encoding": {**enc_obj,
                          "text": {"field": enc["y"], "type": "quantitative", "format": ".3~s"}}},
        ]
    else:
        base["mark"] = mark
        base["encoding"] = enc_obj
    return base


def _x_enc(field: str, temporal: bool) -> dict:
    x_enc = {"field": field, "type": "temporal" if temporal else "nominal"}
    if not temporal:                       # rotate labels so many categories don't cram/overlap
        x_enc["axis"] = {"labelAngle": -40, "labelLimit": 140}
    return x_enc


def _looks_temporal(field: str, rows: list[dict]) -> bool:
    if any(k in field.lower() for k in ("date", "month", "year", "day", "time", "week")):
        return True
    return False
