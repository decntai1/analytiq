# Glossary→table pinning A/B  (labels ON, embedder=model2vec)

Deterministic retrieval scaffold: a question naming a glossary metric pins the tables in that metric's formula into the schema context. Same model-independent table-recall measurement as the labels A/B; pinning is measured ON TOP of labels+embedder.

## Headline

- recall  **pin OFF 0.700  →  pin ON 0.900**  (banked labels ceiling: 0.70)
- vs the 0.70 labels ceiling: **CLEARED**
- model-independence: by construction — store.search + pin never see the LLM

## Traps

| trap | needs | pin OFF | pin ON |
|------|-------|:-------:|:------:|
| q5_margin | sales | ❌ | ✅ |
| q4_why_q3_weak | produced_items | ❌ | ❌ |

q2 net_revenue — pin fires but is a **no-op** (tables already retrieved): **True**  → pinning doesn't distort what already works.

## Per-question

| qid | expected | matched metric | pinned | recall OFF | recall ON |
|-----|----------|----------------|--------|:----------:|:---------:|
| q1_monthly_revenue | sales | — | — | 1.00 | 1.00 |
| q2_net_revenue_trap | sales,returns | net_revenue | sales,returns | 1.00 | 1.00 |
| q3_top_products | sales | — | — | 1.00 | 1.00 |
| q4_why_q3_weak | sales,produced_items | — | — | 0.50 | 0.50 |
| q5_margin | sales | gross_margin | sales | 0.00 | 1.00 |

## Determinism boundary (so it can't be called fuzzy)

1. **table extraction** — every `identifier.column` in a formula → `identifier` as a table.
2. **metric match** — key normalized (`_`→space), case-insensitive substring of the question. No stemming, embeddings, or synonyms.

Glossary metrics: net_revenue, gross_margin, active_customers, production_volume. top_k=6, n_tables=27.

