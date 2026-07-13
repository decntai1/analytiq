# Reasoning-ladder EVIDENCE LOG

- scaffold level(s): `['full']`  · pinned tables: `True`  · repeats: `10`  · embedding: `model2vec`  · DB: `sqlite:////tmp/ladder_eval/ecommerce_ladder.db`
- Every entry below is the model's **actual** stored SQL and the **actual** rows it returned (from `sql_log` / `result_rows`). Nothing is reconstructed or paraphrased.
- `WHY` notes on failures are auto-derived from the run's own SQL + result numbers.
- Repeats with an identical query+verdict are grouped, listing their repeat numbers, so per-run provenance is preserved while the non-determinism is visible.

## Pass-rate summary (answer_correct)

| question | level | qwen3-coder-next | devstral-small-24b | devstral-123b |
|---|---|---|---|---|
| L2b_net_revenue | L2 | 0/10 | 0/10 | 0/10 |
| L5b_return_rate_by_product | L5 | 5/10 | 0/10 | 0/10 |

## Full evidence — grouped by question, then model

### L2b_net_revenue  (Level 2)
**Question:** What was net revenue (sales revenue minus returned amounts) overall?
**Expected (ground truth):** 1669174.20

#### qwen3-coder-next — 0/10 pass

- **FAIL** · repeats [1,3,5,9,10] (5/10)
  - SQL: `SELECT SUM(sales.revenue) - COALESCE(SUM(returns.amount), 0) AS net_revenue FROM sales LEFT JOIN returns ON sales.sale_id = returns.sale_id`
  - Result: (1847143.53)
  - WHY: fan-out double-count: joined sales↔returns ON sale_id, net 1,847,144 vs true 1,669,174 (Δ+177,969 = duplicated multi-return sales' revenue)

- **FAIL** · repeats [2] (1/10)
  - SQL: `SELECT SUM(s.revenue) - COALESCE(SUM(r.amount), 0) AS net_revenue FROM sales s LEFT JOIN returns r ON s.sale_id = r.sale_id;`
  - Result: (1847143.53)
  - WHY: fan-out double-count: joined sales↔returns ON sale_id, net 1,847,144 vs true 1,669,174 (Δ+177,969 = duplicated multi-return sales' revenue)

- **FAIL** · repeats [4,8] (2/10)
  - SQL: `SELECT SUM(s.revenue) - COALESCE(SUM(r.amount), 0) AS net_revenue FROM sales s LEFT JOIN returns r ON s.sale_id = r.sale_id`
  - Result: (1847143.53)
  - WHY: fan-out double-count: joined sales↔returns ON sale_id, net 1,847,144 vs true 1,669,174 (Δ+177,969 = duplicated multi-return sales' revenue)

- **FAIL** · repeats [6,7] (2/10)
  - SQL: `SELECT SUM(sales.revenue) - COALESCE(SUM(returns.amount), 0) AS net_revenue FROM sales LEFT JOIN returns ON sales.sale_id = returns.sale_id;`
  - Result: (1847143.53)
  - WHY: fan-out double-count: joined sales↔returns ON sale_id, net 1,847,144 vs true 1,669,174 (Δ+177,969 = duplicated multi-return sales' revenue)

#### devstral-small-24b — 0/10 pass

- **FAIL** · repeats [1,2,3,4,5,6,7,8,9,10] (10/10)
  - SQL: `SELECT SUM(sales.revenue) - COALESCE(SUM(returns.amount), 0) AS net_revenue FROM sales LEFT JOIN returns ON sales.sale_id = returns.sale_id;`
  - Result: (1847143.53)
  - WHY: fan-out double-count: joined sales↔returns ON sale_id, net 1,847,144 vs true 1,669,174 (Δ+177,969 = duplicated multi-return sales' revenue)

#### devstral-123b — 0/10 pass

- **FAIL** · repeats [1,2,3,4,5,6,7,8,9,10] (10/10)
  - SQL: `SELECT SUM(sales.revenue) - COALESCE(SUM(returns.amount), 0) AS net_revenue FROM sales LEFT JOIN returns ON sales.sale_id = returns.sale_id;`
  - Result: (1847143.53)
  - WHY: fan-out double-count: joined sales↔returns ON sale_id, net 1,847,144 vs true 1,669,174 (Δ+177,969 = duplicated multi-return sales' revenue)

### L5b_return_rate_by_product  (Level 5)
**Question:** For each product, what fraction of its revenue was returned? (returned amount divided by that product's sales revenue). Rank products from highest return-fraction to lowest.
**Expected (ground truth):** Vertex Keyboard=14.82, Cobalt Laptop=13.1, Ivory Stand=12.06, Ember Charger=12.0, Aurora Speaker=0.0, Fable Tablet=0.0, Halo Monitor=0.0, Nimbus Router=0.0, Onyx Webcam=0.0, Pulse Earbuds=0.0, Quartz Mouse=0.0, Slate Dock=0.0

#### qwen3-coder-next — 5/10 pass

- **FAIL** · repeats [1] (1/10)
  - SQL: `SELECT s.product, SUM(s.revenue) AS total_revenue, COALESCE(SUM(r.amount), 0) AS total_returned_amount, CASE WHEN SUM(s.revenue) = 0 THEN 0 ELSE COALESCE(SUM(r.amount), 0) / SUM(s.revenue) END AS return_fraction FROM sales s LEFT JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ORDER BY return_fraction DESC`
  - Result: (Vertex Keyboard, 142609.14, 16050.00, 0.11); (Cobalt Laptop, 176720.12, 18525.00, 0.10); (Ember Charger, 222970.60, 21000.00, 0.09); (Ivory Stand, 255042.31, 23475.00, 0.09); (Slate Dock, 188921.52, 0, 0.00); (Quartz Mouse, 157348.40, 0, 0.00); (Pulse Earbuds, 132653.45, 0, 0.00); (Onyx Webcam, 186622.05, 0, 0.00); (Nimbus Router, 96909.51, 0, 0.00); (Halo Monitor, 123596.85, 0, 0.00); (Fable Tablet, 149597.28, 0, 0.00); (Aurora Speaker, 93202.30, 0, 0.00)
  - WHY: fan-out double-count: sales↔returns joined ON sale_id inflates the revenue denominator

- **PASS** · repeats [2] (1/10)
  - SQL: `WITH product_revenue AS ( SELECT s.product, SUM(s.revenue) AS total_revenue FROM sales s GROUP BY s.product ), product_returns AS ( SELECT s.product, COALESCE(SUM(r.amount), 0) AS total_returned FROM sales s LEFT JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ) SELECT pr.product, pr.total_revenue, COALESCE(prt.total_returned, 0) AS total_returned, CAST(COALESCE(prt.total_returned, 0) AS REAL) / pr.total_revenue AS return_fraction FROM product_revenue pr LEFT JOIN product_returns prt ON pr.product = prt.product ORDER BY return_fraction DESC, pr.product;`
  - Result: (Vertex Keyboard, 108266.47, 16050.00, 0.15); (Cobalt Laptop, 141390.97, 18525.00, 0.13); (Ivory Stand, 194731.78, 23475.00, 0.12); (Ember Charger, 174983.62, 21000.00, 0.12); (Aurora Speaker, 93202.30, 0, 0.00); (Fable Tablet, 149597.28, 0, 0.00); (Halo Monitor, 123596.85, 0, 0.00); (Nimbus Router, 96909.51, 0, 0.00); (Onyx Webcam, 186622.05, 0, 0.00); (Pulse Earbuds, 132653.45, 0, 0.00); (Quartz Mouse, 157348.40, 0, 0.00); (Slate Dock, 188921.52, 0, 0.00)

- **PASS** · repeats [3] (1/10)
  - SQL: `WITH product_revenue AS ( SELECT product, SUM(revenue) AS total_revenue FROM sales GROUP BY product ), product_returns AS ( SELECT s.product, SUM(r.amount) AS total_returned FROM returns r JOIN sales s ON r.sale_id = s.sale_id GROUP BY s.product ), return_fractions AS ( SELECT pr.product, pr.total_revenue, COALESCE(pret.total_returned, 0) AS total_returned, CASE WHEN pr.total_revenue = 0 THEN 0 ELSE CAST(COALESCE(pret.total_returned, 0) AS REAL) / pr.total_revenue END AS return_fraction FROM product_revenue pr LEFT JOIN product_returns pret ON pr.product = pret.product ) SELECT product, return_fraction FROM return_fractions ORDER BY return_fraction DESC;`
  - Result: (Vertex Keyboard, 0.15); (Cobalt Laptop, 0.13); (Ivory Stand, 0.12); (Ember Charger, 0.12); (Aurora Speaker, 0.00); (Fable Tablet, 0.00); (Halo Monitor, 0.00); (Nimbus Router, 0.00); (Onyx Webcam, 0.00); (Pulse Earbuds, 0.00); (Quartz Mouse, 0.00); (Slate Dock, 0.00)

- **FAIL** · repeats [4] (1/10)
  - SQL: `SELECT s.product, SUM(s.revenue) AS total_revenue, COALESCE(SUM(r.amount), 0) AS total_returned, CASE WHEN SUM(s.revenue) > 0 THEN COALESCE(SUM(r.amount), 0) / SUM(s.revenue) ELSE 0 END AS return_fraction FROM sales s LEFT JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ORDER BY return_fraction DESC;`
  - Result: (Vertex Keyboard, 142609.14, 16050.00, 0.11); (Cobalt Laptop, 176720.12, 18525.00, 0.10); (Ember Charger, 222970.60, 21000.00, 0.09); (Ivory Stand, 255042.31, 23475.00, 0.09); (Slate Dock, 188921.52, 0, 0.00); (Quartz Mouse, 157348.40, 0, 0.00); (Pulse Earbuds, 132653.45, 0, 0.00); (Onyx Webcam, 186622.05, 0, 0.00); (Nimbus Router, 96909.51, 0, 0.00); (Halo Monitor, 123596.85, 0, 0.00); (Fable Tablet, 149597.28, 0, 0.00); (Aurora Speaker, 93202.30, 0, 0.00)
  - WHY: fan-out double-count: sales↔returns joined ON sale_id inflates the revenue denominator

- **FAIL** · repeats [5] (1/10)
  - SQL: `SELECT s.product, SUM(s.revenue) AS total_revenue, COALESCE(SUM(r.amount), 0) AS returned_amount, COALESCE(SUM(r.amount), 0) / NULLIF(SUM(s.revenue), 0) AS return_fraction FROM sales s LEFT JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ORDER BY return_fraction DESC;`
  - Result: (Vertex Keyboard, 142609.14, 16050.00, 0.11); (Cobalt Laptop, 176720.12, 18525.00, 0.10); (Ember Charger, 222970.60, 21000.00, 0.09); (Ivory Stand, 255042.31, 23475.00, 0.09); (Slate Dock, 188921.52, 0, 0.00); (Quartz Mouse, 157348.40, 0, 0.00); (Pulse Earbuds, 132653.45, 0, 0.00); (Onyx Webcam, 186622.05, 0, 0.00); (Nimbus Router, 96909.51, 0, 0.00); (Halo Monitor, 123596.85, 0, 0.00); (Fable Tablet, 149597.28, 0, 0.00); (Aurora Speaker, 93202.30, 0, 0.00)
  - WHY: fan-out double-count: sales↔returns joined ON sale_id inflates the revenue denominator

- **PASS** · repeats [6] (1/10)
  - SQL: `WITH product_sales AS ( SELECT product, SUM(revenue) AS total_revenue FROM sales GROUP BY product ), product_returns AS ( SELECT s.product, COALESCE(SUM(r.amount), 0) AS total_returned FROM sales s LEFT JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ) SELECT ps.product, ROUND(CAST(pr.total_returned AS REAL) / ps.total_revenue, 4) AS return_fraction FROM product_sales ps JOIN product_returns pr ON ps.product = pr.product ORDER BY return_fraction DESC;`
  - Result: (Vertex Keyboard, 0.15); (Cobalt Laptop, 0.13); (Ivory Stand, 0.12); (Ember Charger, 0.12); (Aurora Speaker, 0.00); (Fable Tablet, 0.00); (Halo Monitor, 0.00); (Nimbus Router, 0.00); (Onyx Webcam, 0.00); (Pulse Earbuds, 0.00); (Quartz Mouse, 0.00); (Slate Dock, 0.00)

- **PASS** · repeats [7] (1/10)
  - SQL: `WITH product_revenue AS ( SELECT product, SUM(revenue) as total_revenue FROM sales GROUP BY product ), product_returns AS ( SELECT s.product, COALESCE(SUM(r.amount), 0) as total_returned FROM sales s LEFT JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ) SELECT pr.product, pr.total_revenue, COALESCE(pret.total_returned, 0) as returned_amount, COALESCE(pret.total_returned, 0) / pr.total_revenue as return_fraction FROM product_revenue pr LEFT JOIN product_returns pret ON pr.product = pret.product ORDER BY return_fraction DESC`
  - Result: (Vertex Keyboard, 108266.47, 16050.00, 0.15); (Cobalt Laptop, 141390.97, 18525.00, 0.13); (Ivory Stand, 194731.78, 23475.00, 0.12); (Ember Charger, 174983.62, 21000.00, 0.12); (Aurora Speaker, 93202.30, 0, 0.00); (Fable Tablet, 149597.28, 0, 0.00); (Halo Monitor, 123596.85, 0, 0.00); (Nimbus Router, 96909.51, 0, 0.00); (Onyx Webcam, 186622.05, 0, 0.00); (Pulse Earbuds, 132653.45, 0, 0.00); (Quartz Mouse, 157348.40, 0, 0.00); (Slate Dock, 188921.52, 0, 0.00)

- **FAIL** · repeats [8] (1/10)
  - SQL: `SELECT s.product, SUM(s.revenue) AS total_revenue, COALESCE(SUM(r.amount), 0) AS total_returned, COALESCE(SUM(r.amount), 0) / SUM(s.revenue) AS return_fraction FROM sales s LEFT JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ORDER BY return_fraction DESC;`
  - Result: (Vertex Keyboard, 142609.14, 16050.00, 0.11); (Cobalt Laptop, 176720.12, 18525.00, 0.10); (Ember Charger, 222970.60, 21000.00, 0.09); (Ivory Stand, 255042.31, 23475.00, 0.09); (Slate Dock, 188921.52, 0, 0.00); (Quartz Mouse, 157348.40, 0, 0.00); (Pulse Earbuds, 132653.45, 0, 0.00); (Onyx Webcam, 186622.05, 0, 0.00); (Nimbus Router, 96909.51, 0, 0.00); (Halo Monitor, 123596.85, 0, 0.00); (Fable Tablet, 149597.28, 0, 0.00); (Aurora Speaker, 93202.30, 0, 0.00)
  - WHY: fan-out double-count: sales↔returns joined ON sale_id inflates the revenue denominator

- **PASS** · repeats [9] (1/10)
  - SQL: `WITH product_revenues AS ( SELECT product, SUM(revenue) AS total_revenue FROM sales GROUP BY product ), product_returns AS ( SELECT s.product, COALESCE(SUM(r.amount), 0) AS total_returned FROM sales s LEFT JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ) SELECT pr.product, pr.total_revenue, prr.total_returned, CAST(prr.total_returned AS REAL) / pr.total_revenue AS return_fraction FROM product_revenues pr JOIN product_returns prr ON pr.product = prr.product ORDER BY return_fraction DESC;`
  - Result: (Vertex Keyboard, 108266.47, 16050.00, 0.15); (Cobalt Laptop, 141390.97, 18525.00, 0.13); (Ivory Stand, 194731.78, 23475.00, 0.12); (Ember Charger, 174983.62, 21000.00, 0.12); (Aurora Speaker, 93202.30, 0, 0.00); (Fable Tablet, 149597.28, 0, 0.00); (Halo Monitor, 123596.85, 0, 0.00); (Nimbus Router, 96909.51, 0, 0.00); (Onyx Webcam, 186622.05, 0, 0.00); (Pulse Earbuds, 132653.45, 0, 0.00); (Quartz Mouse, 157348.40, 0, 0.00); (Slate Dock, 188921.52, 0, 0.00)

- **FAIL** · repeats [10] (1/10)
  - SQL: `WITH product_summary AS ( SELECT s.product, SUM(s.revenue) AS total_revenue, COALESCE(SUM(r.amount), 0) AS total_returned FROM sales s LEFT JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ) SELECT product, ROUND(total_returned / total_revenue, 4) AS return_fraction FROM product_summary WHERE total_revenue > 0 ORDER BY return_fraction DESC;`
  - Result: (Vertex Keyboard, 0.11); (Cobalt Laptop, 0.10); (Ember Charger, 0.09); (Ivory Stand, 0.09); (Aurora Speaker, 0.00); (Fable Tablet, 0.00); (Halo Monitor, 0.00); (Nimbus Router, 0.00); (Onyx Webcam, 0.00); (Pulse Earbuds, 0.00); (Quartz Mouse, 0.00); (Slate Dock, 0.00)
  - WHY: fan-out double-count: sales↔returns joined ON sale_id inflates the revenue denominator

#### devstral-small-24b — 0/10 pass

- **FAIL** · repeats [1,2,4] (3/10)
  - SQL: `SELECT s.product, SUM(s.revenue) AS total_revenue, COALESCE(SUM(r.amount), 0) AS total_returns, COALESCE(SUM(r.amount), 0) / SUM(s.revenue) AS return_fraction FROM sales s LEFT JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ORDER BY return_fraction DESC`
  - Result: (Vertex Keyboard, 142609.14, 16050.00, 0.11); (Cobalt Laptop, 176720.12, 18525.00, 0.10); (Ember Charger, 222970.60, 21000.00, 0.09); (Ivory Stand, 255042.31, 23475.00, 0.09); (Slate Dock, 188921.52, 0, 0.00); (Quartz Mouse, 157348.40, 0, 0.00); (Pulse Earbuds, 132653.45, 0, 0.00); (Onyx Webcam, 186622.05, 0, 0.00); (Nimbus Router, 96909.51, 0, 0.00); (Halo Monitor, 123596.85, 0, 0.00); (Fable Tablet, 149597.28, 0, 0.00); (Aurora Speaker, 93202.30, 0, 0.00)
  - WHY: fan-out double-count: sales↔returns joined ON sale_id inflates the revenue denominator

- **FAIL** · repeats [3,5,6,7,8,9,10] (7/10)
  - SQL: `SELECT s.product, SUM(s.revenue) AS total_revenue, COALESCE(SUM(r.amount), 0) AS total_returns, COALESCE(SUM(r.amount), 0) / SUM(s.revenue) AS return_fraction FROM sales s LEFT JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ORDER BY return_fraction DESC;`
  - Result: (Vertex Keyboard, 142609.14, 16050.00, 0.11); (Cobalt Laptop, 176720.12, 18525.00, 0.10); (Ember Charger, 222970.60, 21000.00, 0.09); (Ivory Stand, 255042.31, 23475.00, 0.09); (Slate Dock, 188921.52, 0, 0.00); (Quartz Mouse, 157348.40, 0, 0.00); (Pulse Earbuds, 132653.45, 0, 0.00); (Onyx Webcam, 186622.05, 0, 0.00); (Nimbus Router, 96909.51, 0, 0.00); (Halo Monitor, 123596.85, 0, 0.00); (Fable Tablet, 149597.28, 0, 0.00); (Aurora Speaker, 93202.30, 0, 0.00)
  - WHY: fan-out double-count: sales↔returns joined ON sale_id inflates the revenue denominator

#### devstral-123b — 0/10 pass

- **FAIL** · repeats [1,5,8,9] (4/10)
  - SQL: `SELECT s.product, SUM(s.revenue) AS total_revenue, COALESCE(SUM(r.amount), 0) AS total_returns, COALESCE(SUM(r.amount), 0) / SUM(s.revenue) AS return_fraction FROM sales s LEFT JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ORDER BY return_fraction DESC;`
  - Result: (Vertex Keyboard, 142609.14, 16050.00, 0.11); (Cobalt Laptop, 176720.12, 18525.00, 0.10); (Ember Charger, 222970.60, 21000.00, 0.09); (Ivory Stand, 255042.31, 23475.00, 0.09); (Slate Dock, 188921.52, 0, 0.00); (Quartz Mouse, 157348.40, 0, 0.00); (Pulse Earbuds, 132653.45, 0, 0.00); (Onyx Webcam, 186622.05, 0, 0.00); (Nimbus Router, 96909.51, 0, 0.00); (Halo Monitor, 123596.85, 0, 0.00); (Fable Tablet, 149597.28, 0, 0.00); (Aurora Speaker, 93202.30, 0, 0.00)
  - WHY: fan-out double-count: sales↔returns joined ON sale_id inflates the revenue denominator

- **FAIL** · repeats [2,3,4,7] (4/10)
  - SQL: `SELECT s.product, SUM(s.revenue) AS total_revenue, COALESCE(SUM(r.amount), 0) AS total_returns, COALESCE(SUM(r.amount), 0) / SUM(s.revenue) AS return_fraction FROM sales s LEFT JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ORDER BY return_fraction DESC`
  - Result: (Vertex Keyboard, 142609.14, 16050.00, 0.11); (Cobalt Laptop, 176720.12, 18525.00, 0.10); (Ember Charger, 222970.60, 21000.00, 0.09); (Ivory Stand, 255042.31, 23475.00, 0.09); (Slate Dock, 188921.52, 0, 0.00); (Quartz Mouse, 157348.40, 0, 0.00); (Pulse Earbuds, 132653.45, 0, 0.00); (Onyx Webcam, 186622.05, 0, 0.00); (Nimbus Router, 96909.51, 0, 0.00); (Halo Monitor, 123596.85, 0, 0.00); (Fable Tablet, 149597.28, 0, 0.00); (Aurora Speaker, 93202.30, 0, 0.00)
  - WHY: fan-out double-count: sales↔returns joined ON sale_id inflates the revenue denominator

- **FAIL** · repeats [6,10] (2/10)
  - SQL: `SELECT s.product, SUM(s.revenue) AS total_revenue, COALESCE(SUM(r.amount), 0) AS total_returned, COALESCE(SUM(r.amount), 0) / SUM(s.revenue) AS return_fraction FROM sales s LEFT JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ORDER BY return_fraction DESC;`
  - Result: (Vertex Keyboard, 142609.14, 16050.00, 0.11); (Cobalt Laptop, 176720.12, 18525.00, 0.10); (Ember Charger, 222970.60, 21000.00, 0.09); (Ivory Stand, 255042.31, 23475.00, 0.09); (Slate Dock, 188921.52, 0, 0.00); (Quartz Mouse, 157348.40, 0, 0.00); (Pulse Earbuds, 132653.45, 0, 0.00); (Onyx Webcam, 186622.05, 0, 0.00); (Nimbus Router, 96909.51, 0, 0.00); (Halo Monitor, 123596.85, 0, 0.00); (Fable Tablet, 149597.28, 0, 0.00); (Aurora Speaker, 93202.30, 0, 0.00)
  - WHY: fan-out double-count: sales↔returns joined ON sale_id inflates the revenue denominator
