"""
Tool registry — the model's callable capabilities (DEcntAI registry.js analog).

Structured arm: run_sql, make_chart.
Unstructured arm: search_documents.
Schema for the structured arm is injected into the system prompt via schema-RAG,
so there's no inspect_schema tool — the relevant tables are already in context.
Add a capability (e.g. build_presentation, forecast) = one entry + one handler.
"""
from __future__ import annotations

from viz.spec import CAPABILITY, LLM_CHART_TYPES

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_sql",
            "description": ("Run ONE read-only SQL query (SELECT/WITH only) against the "
                            "tables shown in the system prompt. Aggregate in SQL."),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "make_chart",
            "description": (
                "Visualize the most recent query results. Provide a NEUTRAL chart spec "
                "(never raw Vega-Lite). The latest query rows are bound automatically. "
                f"Allowed types: {LLM_CHART_TYPES}. Encoding uses COLUMN NAMES:\n"
                "- line/bar/area/scatter: x, y (optional series). pie: category, value.\n"
                "- histogram/density: value (one numeric column; binning/KDE are automatic).\n"
                "- boxplot: y (numeric); optional x = category to compare distributions.\n"
                "- heatmap: x, y, color (color is the numeric cell value).\n"
                "- stacked_bar/stacked_area: x, y, series (set normalize:true for 100%-stacked).\n"
                "- rolling_line: x, y, optional window (int N, moving average).\n"
                "- choropleth: region, value + region_level:\"country\"|\"us_state\" (shaded map;\n"
                "  region is a column of country names/ISO codes or US state names/abbreviations —\n"
                "  codes are resolved automatically, so query the real region column, not a bucket).\n"
                "- geo_points: lat, lon (+ optional size, color) to plot points on a world map.\n"
                "For a scatter, add trend:\"linear\" or trend:\"loess\" for a fitted trend line.\n"
                "Aggregate/compute in SQL first (GROUP BY, or DuckDB stats: corr, regr_slope, "
                "regr_r2, stddev, quantile_cont); the chart only draws what the query returns."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": LLM_CHART_TYPES},
                    "title": {"type": "string"},
                    "encoding": {
                        "type": "object",
                        "description": "Map roles to column names, e.g. {\"x\":\"month\",\"y\":\"revenue\",\"series\":\"metric\"} or {\"value\":\"order_total\"} for a histogram.",
                    },
                    "trend": {"type": "string", "enum": ["linear", "loess"],
                              "description": "Optional fitted trend line for scatter only."},
                    "window": {"type": "integer",
                               "description": "Moving-average window (rolling_line only), e.g. 7."},
                    "normalize": {"type": "boolean",
                                  "description": "100%-stacked (stacked_bar/stacked_area only)."},
                    "region_level": {"type": "string", "enum": ["country", "us_state"],
                                     "description": "Map granularity for choropleth (default country)."},
                },
                "required": ["type", "encoding"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_documents",
            "description": ("Search the company's unstructured documents for relevant passages "
                            "to ground a qualitative answer. Returns passages with sources."),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
]
