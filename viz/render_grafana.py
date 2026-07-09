"""
Grafana renderer adapter — STUB / later wire-up.

Same neutral spec as render_vegalite.py, different target. When you want the
chat-on-top / embeddable-panel-below experience from the thesis doc, implement
this adapter:

  1. Translate the neutral spec + the executed SQL into a Grafana panel JSON.
  2. POST to the Grafana OSS HTTP API to create/UPDATE a panel (reuse one panel
     per session — the doc's "Pattern A" — to avoid dashboard clutter).
  3. Return the d-solo embed URL for the frontend to iframe under the chat.

Auth: a read-only Grafana viewer token server-side, or SSO shared with the app.
Nothing here changes the LLM or the orchestrator — Grafana is purely a new output
surface selected by config (RENDERER=grafana), proving the neutral-spec design.
"""
from __future__ import annotations


def to_grafana_panel(spec: dict, sql: str, datasource_uid: str) -> dict:
    """Placeholder: map neutral spec -> Grafana panel JSON. Implement when wiring Grafana."""
    raise NotImplementedError(
        "Grafana adapter not wired yet. The neutral spec from viz/spec.py is the input; "
        "build panel JSON + call the Grafana OSS API here, return the d-solo embed URL."
    )
