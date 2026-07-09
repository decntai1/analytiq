# Analytiq — Thesis Positioning & Strategy

_The research framing and strategic conclusions. Read for "why this, what's novel,
what's the claim." Code state lives in PROJECT_codebase-map.md._

## Research question
How do LLMs make data visualization easier via natural-language prompts instead of
manually clicking metrics together? Studied as an interaction paradigm AND a systems
question.

## The thesis spine (the central, measurable claim)
**Deterministic scaffolding can substitute for model capability — measurably.**

Not "LLMs can make charts" (commoditized — ChatGPT/Claude do this free). The novel,
publishable claim is: *how much deterministic scaffolding (schema-RAG, validation,
error-repair, a metric glossary, intent routing) lets a small/local open-source model
do what people assume needs a frontier cloud model — quantified as an accuracy curve
across model sizes.*

This single claim does triple duty:
1. **Research:** an open, measurable question (scaffolding-level vs. accuracy vs. model size).
2. **Product foundation:** it's what makes on-prem open-source models *viable*.
3. **USP justification:** it's why the privacy USP doesn't require a frontier model.

The eval rig (`eval/score.py` + `gold/gold_set.json` + scaffolding flags) is built to
produce exactly this curve. Metrics: **table-recall** (did it retrieve every table the
answer needs?), chart-validity, doc-grounding, error count, latency. Levels swept:
`none → rag → rag+val+rep → full`.

## What's novel vs. NOT
- NOT novel: prompt → chart (ChatGPT/Claude code-interpreter already do this well, free).
- Novel/defensible: (a) the scaffolding-vs-model-size tradeoff, measured; (b) silent-miss
  failure characterization (the "what if it misses a table?" problem made visible +
  quantified via table-recall); (c) the architecture that surfaces its own uncertainty
  (shows retrieved tables, SQL, arm) rather than answering confidently from partial data.

## Charts: deterministic, never image-generated
The LLM emits a chart **spec / plotting code**; a library renders real data. Image models
(SDXL etc.) draw plausible-but-false charts — fine for media, disqualifying for data.
The failed SDXL-graph experiment is evidence for a design principle:
**generate code/specs for data fidelity, not pixels.** Worth a paragraph in the thesis.

## Grafana vs. Vega-Lite (resolved)
Vega-Lite for inline ad-hoc answer-charts (LLM emits a neutral spec, renders instantly,
zero infra). Grafana later as the embeddable persistent-dashboard surface (chat-on-top /
panel-below) via the stubbed adapter — same neutral spec, no re-prompting. Not either/or;
different surfaces.

## Product USP (separate from the thesis, but reinforced by it)
**On-prem + open-source LLM for private company data** is the strongest differentiator,
because:
- It accesses a market cloud LLMs are structurally locked out of (regulated /
  data-sovereign / security-conservative companies that legally can't send data to OpenAI).
- The moat is architectural (data never leaves the building), not a copyable feature.
- It's the one USP that leverages the builder's actual rare skill — LLM/GPU hardware
  deployment (from the DEcntAI work) — which most application-layer competitors lack.
- The thesis finding (scaffolding > model size) is the technical enabler: it's what makes
  a weaker on-prem open model good enough.

Honest limits: open models are weaker at causal reasoning / correct SQL (the scaffolding
hedges this — and measuring *where the hedge stops working* is itself a thesis result);
on-prem is a higher-touch enterprise sale (the friction is also part of the moat).

The low-friction wedge: **upload/copy-paste tables into a locally-run instance** — same
privacy moat, far less integration than full ERP connectors. NOT "just what ChatGPT does"
*if* the model behind it is local. A real first-sale on-ramp, not the weak product.

## What transfers from DEcntAI (and what doesn't)
Transfers as patterns: the orchestration loop (plan→execute→reason), the
propose-validate-execute discipline (→ read-only SQL safety), tool-registry onboarding,
intent→specific-format translation. Transfers as *skill*: on-prem LLM/GPU deployment —
the rare thing that makes the USP real. Does NOT transfer: the decentralized-marketplace
thesis (private company data can't go to random GPU nodes — the opposite deployment),
and the media tools themselves. Rough reuse: orchestration philosophy high; data layer,
SQL safety, connectors, private deployment all new.

## Thesis ↔ product discipline
The thesis must be built (it's the PhD; bounded; mostly done). The product is optional and
waits behind the eval numbers — once you know how good on-prem-open-source actually is,
the product decision makes itself. Don't let product ambition distort thesis scope:
the PhD is graded on research rigor (the eval, the failure-mode analysis), not commercial
polish. Keep Analytiq and DEcntAI in separate Projects.
