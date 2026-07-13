"""
Neutral chart spec + capability schema + validator.

The doc's key insight (Step 4-6): the LLM emits a NEUTRAL internal chart spec, NOT
a Vega-Lite or Grafana payload. A renderer adapter then converts it to whichever
surface. This keeps the model simple and makes the viz backend swappable
(Vega-Lite now, Grafana later) without re-prompting.

CAPABILITY is the doc's "dashboard capability schema" — declared, not learned. The
validator rejects anything the LLM proposes that violates these rules, so an
invalid chart is caught before it renders (the doc's critical validation layer).

Statistical chart types (histogram/boxplot/heatmap/density/stacked_*/rolling_line
and scatter trend overlays) are declarative-only: every statistic is computed by a
Vega-Lite transform or by DuckDB SQL. The LLM still emits ONLY a neutral spec — it
never writes code and never fabricates data points, so the fabrication invariant
holds. New types are added primitive-by-primitive, each gated by the eval grid.
"""
from __future__ import annotations

# --- declared capability (source-of-truth B) -------------------------------
CAPABILITY = {
    "chart_types": [
        "bar", "line", "area", "scatter", "pie", "table",
        # statistical (Phase A) — stats via Vega-Lite/DuckDB transforms, spec stays declarative
        "histogram", "boxplot", "heatmap", "density",
        "stacked_bar", "stacked_area", "rolling_line",
        # geographic (Phase B) — region names resolved to topojson ids deterministically
        # (index/region_lookup.py); the LLM names a COLUMN, never a region code.
        "choropleth", "geo_points",
    ],
    "rules": {
        "line_requires": ["x", "y"],
        "area_requires": ["x", "y"],
        "bar_requires": ["x", "y"],
        "scatter_requires": ["x", "y"],
        "pie_requires": ["category", "value"],
        "table_requires": [],
        # statistical types
        "histogram_requires": ["value"],       # one numeric column, binned by Vega-Lite
        "density_requires": ["value"],         # one numeric column, KDE by Vega-Lite
        "boxplot_requires": ["y"],             # numeric y; optional x = category
        "heatmap_requires": ["x", "y", "color"],
        "stacked_bar_requires": ["x", "y", "series"],
        "stacked_area_requires": ["x", "y", "series"],
        "rolling_line_requires": ["x", "y"],   # optional window (int, default 3)
        # geographic types
        "choropleth_requires": ["region", "value"],  # region column + numeric value; region_level modifier
        "geo_points_requires": ["lat", "lon"],       # lat/lon columns; optional size, color
    },
}

# scatter may carry an optional deterministic trend overlay (Vega-Lite transform)
_TREND_METHODS = ("linear", "loess")

# choropleth region granularity -> topojson basemap (see index/region_lookup.BASEMAPS)
_REGION_LEVELS = ("country", "us_state")


def validate_spec(spec: dict) -> None:
    """Raise ValueError if the neutral spec violates the declared capability."""
    if not isinstance(spec, dict):
        raise ValueError("Chart spec must be an object.")
    ctype = spec.get("type")
    if ctype not in CAPABILITY["chart_types"]:
        raise ValueError(f"Unsupported chart type {ctype!r}. Allowed: {CAPABILITY['chart_types']}")
    required = CAPABILITY["rules"].get(f"{ctype}_requires", [])
    enc = spec.get("encoding", {})
    if not isinstance(enc, dict):
        raise ValueError("Chart 'encoding' must be an object mapping roles to column names.")
    missing = [r for r in required if r not in enc]
    if missing:
        raise ValueError(f"Chart type {ctype!r} requires encoding fields {missing}.")

    # optional scatter trend overlay must name a supported deterministic method
    trend = spec.get("trend")
    if ctype == "scatter" and trend is not None and trend not in _TREND_METHODS:
        raise ValueError(f"scatter trend {trend!r} not supported. Allowed: {list(_TREND_METHODS)}")

    # optional rolling_line window must be a positive int
    if ctype == "rolling_line":
        w = spec.get("window", 3)
        if not isinstance(w, int) or isinstance(w, bool) or w < 2:
            raise ValueError("rolling_line 'window' must be an integer >= 2.")

    # choropleth region_level must name a supported basemap (default country)
    if ctype == "choropleth":
        level = spec.get("region_level", "country")
        if level not in _REGION_LEVELS:
            raise ValueError(f"choropleth region_level {level!r} not supported. "
                             f"Allowed: {list(_REGION_LEVELS)}")


# neutral spec shape (what the LLM emits via the make_chart tool):
# {
#   "type": "line",
#   "title": "Sales vs Spendings vs Production",
#   "encoding": {"x": "month", "y": "value", "series": "metric"}  # column names
# }
# statistical examples:
#   {"type": "histogram", "encoding": {"value": "order_total"}}
#   {"type": "boxplot",   "encoding": {"y": "order_total", "x": "region"}}
#   {"type": "heatmap",   "encoding": {"x": "day", "y": "hour", "color": "orders"}}
#   {"type": "scatter",   "encoding": {"x": "spend", "y": "revenue"}, "trend": "linear"}
#   {"type": "rolling_line", "encoding": {"x": "day", "y": "revenue"}, "window": 7}
# geographic examples (region values resolved to topojson ids deterministically):
#   {"type": "choropleth", "encoding": {"region": "country", "value": "revenue"},
#    "region_level": "country"}
#   {"type": "choropleth", "encoding": {"region": "state", "value": "sales"},
#    "region_level": "us_state"}
#   {"type": "geo_points", "encoding": {"lat": "latitude", "lon": "longitude",
#    "size": "sales", "color": "segment"}}
