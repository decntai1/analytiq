# Aggregate-before-join fan-out fix — A/B (offline replay)

offline replay of banked ladder SQL, OFF vs ON, paired on identical model outputs; deterministic; model-independent by construction

Derived relationships (schema-only, no declared FKs):
  - orders -1:N-> order_items on order_id
  - orders -1:N-> payments on order_id
  - orders -1:N-> refunds on order_id
  - orders -1:N-> sales on order_id
  - orders -1:N-> shipments on order_id
  - sales -1:N-> returns on sale_id

## Per-model success (x/10): OFF -> ON

| model | L2b OFF | L2b ON | L5b OFF | L5b ON |
|---|---|---|---|---|
| devstral-123b | 0/10 | 10/10 | 0/10 | 10/10 |
| devstral-small-24b | 0/10 | 10/10 | 0/10 | 10/10 |
| gpt-oss-20b | 2/10 | 10/10 | 1/10 | 10/10 |
| ministral-8b | 0/10 | 10/10 | 10/10 | 10/10 |
| ollama-cloud | 2/10 | 10/10 | 2/10 | 10/10 |
| qwen3-coder | 2/10 | 10/10 | 4/10 | 9/10 |
| qwen3-coder-next | 0/10 | 10/10 | 5/10 | 10/10 |

- **L2b_net_revenue**: OFF 6/70  ->  ON 70/70
- **L5b_return_rate_by_product**: OFF 22/70  ->  ON 69/70
- regressions (ON worse than OFF): **0**  
- rewrite fired: {'L2b_net_revenue:no-op': 6, 'L2b_net_revenue:fired': 64, 'L5b_return_rate_by_product:no-op': 23, 'L5b_return_rate_by_product:fired': 47}

## Residual misses after ON (honest boundary — non-fan-out model errors)
  - qwen3-coder L5b_return_rate_by_product fired=False (no recognised fan-out pattern)

## Example rewrite — L2b_net_revenue
- original : `SELECT SUM(sales.revenue) - COALESCE(SUM(returns.amount), 0) AS net_revenue FROM sales LEFT JOIN returns ON sales.sale_id = returns.sale_id;`
- rewritten: `SELECT __abj_one.__a0 - COALESCE(__abj_many.__b0, 0) AS net_revenue FROM (SELECT SUM(revenue) AS __a0 FROM sales) AS __abj_one CROSS JOIN (SELECT SUM(amount) AS __b0 FROM returns) AS __abj_many`

## Example rewrite — L5b_return_rate_by_product
- original : `SELECT s.product, SUM(s.revenue) AS total_revenue, COALESCE(SUM(r.amount),0) AS total_returns, COALESCE(SUM(r.amount),0)/SUM(s.revenue) AS return_fraction FROM sales s LEFT JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ORDER BY return_fraction DESC;`
- rewritten: `SELECT __abj_one.product, __abj_one.__a0 AS total_revenue, COALESCE(__abj_many.__b0, 0) AS total_returns, COALESCE(__abj_many.__b0, 0) / __abj_one.__a0 AS return_fraction FROM (SELECT product, SUM(revenue) AS __a0 FROM sales GROUP BY product) AS __abj_one LEFT JOIN (SELECT sales.product, SUM(amount) AS __b0 FROM sales LEFT JOIN returns ON sales.sale_id = returns.sale_id GROUP BY sales.product) AS __abj_many ON __abj_one.product = __abj_many.product ORDER BY return_fraction DESC`
