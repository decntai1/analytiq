"""
Tool registry — the model's callable capabilities (DEcntAI registry.js analog).

Structured arm: run_sql, make_chart.
Unstructured arm: search_documents.
Schema for the structured arm is injected into the system prompt via schema-RAG,
so there's no inspect_schema tool — the relevant tables are already in context.
Add a capability (e.g. build_presentation, forecast) = one entry + one handler.
"""
from __future__ import annotations

from viz.spec import CAPABILITY

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
                "Visualize the most recent query results. Provide a NEUTRAL chart spec. "
                f"Allowed types: {CAPABILITY['chart_types']}. Encoding uses column names: "
                "line/bar/area/scatter need x,y (optional series); pie needs category,value. "
                "The latest query rows are bound automatically."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": CAPABILITY["chart_types"]},
                    "title": {"type": "string"},
                    "encoding": {
                        "type": "object",
                        "description": "Map roles to column names, e.g. {\"x\":\"month\",\"y\":\"revenue\",\"series\":\"metric\"}",
                    },
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
