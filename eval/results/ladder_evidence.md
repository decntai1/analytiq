# Reasoning-ladder EVIDENCE LOG

- scaffold level(s): `['full']`  · pinned tables: `True`  · repeats: `10`  · embedding: `model2vec`  · DB: `sqlite:////tmp/ladder_eval/ecommerce_ladder.db`
- Every entry below is the model's **actual** stored SQL and the **actual** rows it returned (from `sql_log` / `result_rows`). Nothing is reconstructed or paraphrased.
- `WHY` notes on failures are auto-derived from the run's own SQL + result numbers.
- Repeats with an identical query+verdict are grouped, listing their repeat numbers, so per-run provenance is preserved while the non-determinism is visible.

## Pass-rate summary (answer_correct)

| question | level | ministral-8b | gpt-oss-20b | ollama-cloud | qwen3-coder |
|---|---|---|---|---|---|
| L1a_total_revenue | L1 | 10/10 | 10/10 | 10/10 | 10/10 |
| L1b_revenue_by_quarter | L1 | 10/10 | 10/10 | 10/10 | 10/10 |
| L2a_revenue_by_channel | L2 | 10/10 | 10/10 | 10/10 | 10/10 |
| L2b_net_revenue | L2 | 0/10 | 2/10 | 2/10 | 2/10 |
| L3a_above_avg_products | L3 | 10/10 | 10/10 | 10/10 | 10/10 |
| L4a_top_product_per_quarter | L4 | 10/10 | 10/10 | 10/10 | 10/10 |
| L4b_running_monthly_total | L4 | 10/10 | 10/10 | 10/10 | 10/10 |
| L5a_mom_growth | L5 | 8/10 | 9/10 | 10/10 | 10/10 |
| L5b_return_rate_by_product | L5 | 10/10 | 1/10 | 2/10 | 4/10 |

## Full evidence — grouped by question, then model

### L1a_total_revenue  (Level 1)
**Question:** What was the total revenue across all sales?
**Expected (ground truth):** 1748224.20

#### ministral-8b — 10/10 pass

- **PASS** · repeats [1,2,3,4,5,6,7,8,9,10] (10/10)
  - SQL: `SELECT SUM(revenue) AS total_revenue FROM sales;`
  - Result: (1748224.20)

#### gpt-oss-20b — 10/10 pass

- **PASS** · repeats [1,2,3,4,5,6,7,8,9,10] (10/10)
  - SQL: `SELECT SUM(revenue) AS total_revenue FROM sales;`
  - Result: (1748224.20)

#### ollama-cloud — 10/10 pass

- **PASS** · repeats [1] (1/10)
  - SQL: `SELECT SUM(revenue) AS total_revenue FROM sales`
  - Result: (1748224.20)

- **PASS** · repeats [2,3,4,5,6,7,8,9,10] (9/10)
  - SQL: `SELECT SUM(revenue) AS total_revenue FROM sales;`
  - Result: (1748224.20)

#### qwen3-coder — 10/10 pass

- **PASS** · repeats [1,2,3,4,5,6,7,8,9,10] (10/10)
  - SQL: `SELECT SUM(revenue) AS total_revenue FROM sales`
  - Result: (1748224.20)

### L1b_revenue_by_quarter  (Level 1)
**Question:** What was total revenue per quarter?
**Expected (ground truth):** Q1=487110.25, Q2=481759.51, Q3=297354.29, Q4=482000.15

#### ministral-8b — 10/10 pass

- **PASS** · repeats [1,2,3,4,5,6,7,8,9,10] (10/10)
  - SQL: `SELECT quarter, SUM(revenue) AS total_revenue FROM sales GROUP BY quarter ORDER BY quarter;`
  - Result: (Q1, 487110.25); (Q2, 481759.51); (Q3, 297354.29); (Q4, 482000.15)

#### gpt-oss-20b — 10/10 pass

- **PASS** · repeats [1,2,3,4,5,6,7,8,9,10] (10/10)
  - SQL: `SELECT quarter, SUM(revenue) AS total_revenue FROM sales GROUP BY quarter ORDER BY quarter;`
  - Result: (Q1, 487110.25); (Q2, 481759.51); (Q3, 297354.29); (Q4, 482000.15)

#### ollama-cloud — 10/10 pass

- **PASS** · repeats [1,3,4,5,6,7,8,9,10] (9/10)
  - SQL: `SELECT quarter, SUM(revenue) AS total_revenue FROM sales GROUP BY quarter ORDER BY quarter;`
  - Result: (Q1, 487110.25); (Q2, 481759.51); (Q3, 297354.29); (Q4, 482000.15)

- **PASS** · repeats [2] (1/10)
  - SQL: `SELECT quarter, SUM(revenue) AS total_revenue FROM sales GROUP BY quarter ORDER BY quarter`
  - Result: (Q1, 487110.25); (Q2, 481759.51); (Q3, 297354.29); (Q4, 482000.15)

#### qwen3-coder — 10/10 pass

- **PASS** · repeats [1,2,3,4,5,6,7,8,9,10] (10/10)
  - SQL: `SELECT quarter, SUM(revenue) AS total_revenue FROM sales GROUP BY quarter ORDER BY quarter`
  - Result: (Q1, 487110.25); (Q2, 481759.51); (Q3, 297354.29); (Q4, 482000.15)

### L2a_revenue_by_channel  (Level 2)
**Question:** What was total revenue per sales channel? (channel is on the orders table, revenue is on sales)
**Expected (ground truth):** Wholesale=444467.27, Online=441703.91, Retail=432225.54, Partner=429827.48

#### ministral-8b — 10/10 pass

- **PASS** · repeats [1,3,4,5,6,7,8,9,10] (9/10)
  - SQL: `SELECT o.channel AS sales_channel, SUM(s.revenue) AS total_revenue FROM orders o JOIN sales s ON o.order_id = s.order_id GROUP BY o.channel`
  - Result: (Online, 441703.91); (Partner, 429827.48); (Retail, 432225.54); (Wholesale, 444467.27)

- **PASS** · repeats [2] (1/10)
  - SQL: `SELECT o.channel AS sales_channel, SUM(s.revenue) AS total_revenue FROM sales s JOIN orders o ON s.order_id = o.order_id GROUP BY o.channel`
  - Result: (Online, 441703.91); (Partner, 429827.48); (Retail, 432225.54); (Wholesale, 444467.27)

#### gpt-oss-20b — 10/10 pass

- **PASS** · repeats [1,2,3,4,5,6,7,8,9,10] (10/10)
  - SQL: `SELECT o.channel, SUM(s.revenue) AS total_revenue FROM sales s JOIN orders o ON s.order_id = o.order_id GROUP BY o.channel ORDER BY total_revenue DESC;`
  - Result: (Wholesale, 444467.27); (Online, 441703.91); (Retail, 432225.54); (Partner, 429827.48)

#### ollama-cloud — 10/10 pass

- **PASS** · repeats [1,4,5,7,9,10] (6/10)
  - SQL: `SELECT o.channel, SUM(s.revenue) AS total_revenue FROM sales s JOIN orders o ON s.order_id = o.order_id GROUP BY o.channel`
  - Result: (Online, 441703.91); (Partner, 429827.48); (Retail, 432225.54); (Wholesale, 444467.27)

- **PASS** · repeats [2,3,6] (3/10)
  - SQL: `SELECT o.channel, SUM(s.revenue) AS total_revenue FROM sales s JOIN orders o ON s.order_id = o.order_id GROUP BY o.channel ORDER BY total_revenue DESC;`
  - Result: (Wholesale, 444467.27); (Online, 441703.91); (Retail, 432225.54); (Partner, 429827.48)

- **PASS** · repeats [8] (1/10)
  - SQL: `SELECT o.channel, SUM(s.revenue) AS total_revenue FROM sales s JOIN orders o ON s.order_id = o.order_id GROUP BY o.channel ORDER BY total_revenue DESC`
  - Result: (Wholesale, 444467.27); (Online, 441703.91); (Retail, 432225.54); (Partner, 429827.48)

#### qwen3-coder — 10/10 pass

- **PASS** · repeats [1,2,3,4,5,7,8,9,10] (9/10)
  - SQL: `SELECT o.channel, SUM(s.revenue) AS total_revenue FROM sales s JOIN orders o ON s.order_id = o.order_id GROUP BY o.channel ORDER BY total_revenue DESC`
  - Result: (Wholesale, 444467.27); (Online, 441703.91); (Retail, 432225.54); (Partner, 429827.48)

- **PASS** · repeats [6] (1/10)
  - SQL: `SELECT o.channel, SUM(s.revenue) as total_revenue FROM sales s JOIN orders o ON s.order_id = o.order_id GROUP BY o.channel ORDER BY total_revenue DESC`
  - Result: (Wholesale, 444467.27); (Online, 441703.91); (Retail, 432225.54); (Partner, 429827.48)

### L2b_net_revenue  (Level 2)
**Question:** What was net revenue (sales revenue minus returned amounts) overall?
**Expected (ground truth):** 1669174.20

#### ministral-8b — 0/10 pass

- **FAIL** · repeats [1,4,5] (3/10)
  - SQL: `SELECT SUM(sales.revenue) - COALESCE(SUM(returns.amount), 0) AS net_revenue FROM sales LEFT JOIN returns ON sales.sale_id = returns.sale_id;`
  - Result: (1847143.53)
  - WHY: fan-out double-count: joined sales↔returns ON sale_id, net 1,847,144 vs true 1,669,174 (Δ+177,969 = duplicated multi-return sales' revenue)

- **FAIL** · repeats [2,6] (2/10)
  - SQL: `SELECT SUM(revenue) - COALESCE(SUM(r.amount), 0) AS net_revenue FROM sales LEFT JOIN returns r ON sales.sale_id = r.sale_id;`
  - Result: (1847143.53)
  - WHY: fan-out double-count: joined sales↔returns ON sale_id, net 1,847,144 vs true 1,669,174 (Δ+177,969 = duplicated multi-return sales' revenue)

- **FAIL** · repeats [3,7,8,9,10] (5/10)
  - SQL: `SELECT SUM(sales.revenue) - COALESCE(SUM(returns.amount), 0) AS net_revenue FROM sales LEFT JOIN returns ON sales.sale_id = returns.sale_id`
  - Result: (1847143.53)
  - WHY: fan-out double-count: joined sales↔returns ON sale_id, net 1,847,144 vs true 1,669,174 (Δ+177,969 = duplicated multi-return sales' revenue)

#### gpt-oss-20b — 2/10 pass

- **FAIL** · repeats [1,10] (2/10)
  - SQL: `SELECT SUM(sales.revenue) - COALESCE(SUM(returns.amount),0) AS net_revenue FROM sales LEFT JOIN returns ON sales.sale_id = returns.sale_id;`
  - Result: (1847143.53)
  - WHY: fan-out double-count: joined sales↔returns ON sale_id, net 1,847,144 vs true 1,669,174 (Δ+177,969 = duplicated multi-return sales' revenue)

- **FAIL** · repeats [2,3,6,7,9] (5/10)
  - SQL: `SELECT SUM(sales.revenue) - COALESCE(SUM(returns.amount), 0) AS net_revenue FROM sales LEFT JOIN returns ON sales.sale_id = returns.sale_id;`
  - Result: (1847143.53)
  - WHY: fan-out double-count: joined sales↔returns ON sale_id, net 1,847,144 vs true 1,669,174 (Δ+177,969 = duplicated multi-return sales' revenue)

- **PASS** · repeats [4] (1/10)
  - SQL: `SELECT (SELECT SUM(revenue) FROM sales) AS total_sales, (SELECT SUM(amount) FROM returns) AS total_returns, (SELECT SUM(revenue) FROM sales) - COALESCE((SELECT SUM(amount) FROM returns),0) AS net_revenue;`
  - Result: (1748224.20, 79050.00, 1669174.20)

- **PASS** · repeats [5] (1/10)
  - SQL: `SELECT SUM(s.revenue) - COALESCE((SELECT SUM(amount) FROM returns),0) AS net_revenue FROM sales s;`
  - Result: (1669174.20)

- **FAIL** · repeats [8] (1/10)
  - SQL: `SELECT SUM(sales.revenue) AS total_sales, COALESCE(SUM(returns.amount),0) AS total_returns, SUM(sales.revenue) - COALESCE(SUM(returns.amount),0) AS net_revenue FROM sales LEFT JOIN returns ON sales.sale_id = returns.sale_id;`
  - Result: (1926193.53, 79050.00, 1847143.53)
  - WHY: fan-out double-count: joined sales↔returns ON sale_id, net 1,847,144 vs true 1,669,174 (Δ+177,969 = duplicated multi-return sales' revenue)

#### ollama-cloud — 2/10 pass

- **FAIL** · repeats [1,8] (2/10)
  - SQL: `SELECT SUM(sales.revenue) - COALESCE(SUM(returns.amount), 0) AS net_revenue FROM sales LEFT JOIN returns ON sales.sale_id = returns.sale_id;`
  - Result: (1847143.53)
  - WHY: fan-out double-count: joined sales↔returns ON sale_id, net 1,847,144 vs true 1,669,174 (Δ+177,969 = duplicated multi-return sales' revenue)

- **PASS** · repeats [2] (1/10)
  - SQL: `SELECT (SELECT SUM(revenue) FROM sales) - COALESCE((SELECT SUM(amount) FROM returns), 0) AS net_revenue`
  - Result: (1669174.20)

- **FAIL** · repeats [3] (1/10)
  - SQL: `SELECT (SUM(sales.revenue) - COALESCE(SUM(returns.amount), 0)) AS net_revenue FROM sales LEFT JOIN returns ON sales.sale_id = returns.sale_id;`
  - Result: (1847143.53)
  - WHY: fan-out double-count: joined sales↔returns ON sale_id, net 1,847,144 vs true 1,669,174 (Δ+177,969 = duplicated multi-return sales' revenue)

- **FAIL** · repeats [4] (1/10)
  - SQL: `SELECT SUM(sales.revenue) - COALESCE(SUM(returns.amount),0) AS net_revenue FROM sales LEFT JOIN returns ON sales.sale_id = returns.sale_id`
  - Result: (1847143.53)
  - WHY: fan-out double-count: joined sales↔returns ON sale_id, net 1,847,144 vs true 1,669,174 (Δ+177,969 = duplicated multi-return sales' revenue)

- **FAIL** · repeats [5] (1/10)
  - SQL: `SELECT SUM(sales.revenue) AS total_revenue, COALESCE(SUM(returns.amount),0) AS total_returns, SUM(sales.revenue) - COALESCE(SUM(returns.amount),0) AS net_revenue FROM sales LEFT JOIN returns ON sales.sale_id = returns.sale_id`
  - Result: (1926193.53, 79050.00, 1847143.53)
  - WHY: fan-out double-count: joined sales↔returns ON sale_id, net 1,847,144 vs true 1,669,174 (Δ+177,969 = duplicated multi-return sales' revenue)

- **FAIL** · repeats [6] (1/10)
  - SQL: `SELECT SUM(s.revenue) - COALESCE(SUM(r.amount),0) AS net_revenue FROM sales s LEFT JOIN returns r ON s.sale_id = r.sale_id;`
  - Result: (1847143.53)
  - WHY: fan-out double-count: joined sales↔returns ON sale_id, net 1,847,144 vs true 1,669,174 (Δ+177,969 = duplicated multi-return sales' revenue)

- **PASS** · repeats [7] (1/10)
  - SQL: `SELECT (SELECT COALESCE(SUM(revenue),0) FROM sales) - (SELECT COALESCE(SUM(amount),0) FROM returns) AS net_revenue;`
  - Result: (1669174.20)

- **FAIL** · repeats [9] (1/10)
  - SQL: `SELECT SUM(revenue) - COALESCE(SUM(r.amount), 0) AS net_revenue FROM sales s LEFT JOIN returns r ON s.sale_id = r.sale_id;`
  - Result: (1847143.53)
  - WHY: fan-out double-count: joined sales↔returns ON sale_id, net 1,847,144 vs true 1,669,174 (Δ+177,969 = duplicated multi-return sales' revenue)

- **FAIL** · repeats [10] (1/10)
  - SQL: `SELECT SUM(sales.revenue) AS total_revenue, COALESCE(SUM(returns.amount),0) AS total_returns, (SUM(sales.revenue) - COALESCE(SUM(returns.amount),0)) AS net_revenue FROM sales LEFT JOIN returns ON sales.sale_id = returns.sale_id`
  - Result: (1926193.53, 79050.00, 1847143.53)
  - WHY: fan-out double-count: joined sales↔returns ON sale_id, net 1,847,144 vs true 1,669,174 (Δ+177,969 = duplicated multi-return sales' revenue)

#### qwen3-coder — 2/10 pass

- **FAIL** · repeats [1,4,7,8,9] (5/10)
  - SQL: `SELECT SUM(sales.revenue) - COALESCE(SUM(returns.amount), 0) AS net_revenue FROM sales LEFT JOIN returns ON sales.sale_id = returns.sale_id`
  - Result: (1847143.53)
  - WHY: fan-out double-count: joined sales↔returns ON sale_id, net 1,847,144 vs true 1,669,174 (Δ+177,969 = duplicated multi-return sales' revenue)

- **PASS** · repeats [2,10] (2/10)
  - SQL: `SELECT (SELECT SUM(revenue) FROM sales) - (SELECT COALESCE(SUM(amount), 0) FROM returns) AS net_revenue`
  - Result: (1669174.20)

- **FAIL** · repeats [3,5,6] (3/10)
  - SQL: `SELECT SUM(sales.revenue) AS total_revenue, COALESCE(SUM(returns.amount), 0) AS total_returns, SUM(sales.revenue) - COALESCE(SUM(returns.amount), 0) AS net_revenue FROM sales LEFT JOIN returns ON sales.sale_id = returns.sale_id`
  - Result: (1926193.53, 79050.00, 1847143.53)
  - WHY: fan-out double-count: joined sales↔returns ON sale_id, net 1,847,144 vs true 1,669,174 (Δ+177,969 = duplicated multi-return sales' revenue)

### L3a_above_avg_products  (Level 3)
**Question:** Which products have total revenue above the average total revenue per product? List them.
**Expected (ground truth):** {Ivory Stand, Slate Dock, Onyx Webcam, Ember Charger, Quartz Mouse, Fable Tablet}

#### ministral-8b — 10/10 pass

- **PASS** · repeats [1,4,9] (3/10)
  - SQL: `WITH product_revenue AS ( SELECT product, SUM(revenue) AS total_revenue FROM sales GROUP BY product ) SELECT product, total_revenue FROM product_revenue WHERE total_revenue > ( SELECT AVG(total_revenue) FROM product_revenue ) ORDER BY total_revenue DESC;`
  - Result: (Ivory Stand, 194731.78); (Slate Dock, 188921.52); (Onyx Webcam, 186622.05); (Ember Charger, 174983.62); (Quartz Mouse, 157348.40); (Fable Tablet, 149597.28)

- **PASS** · repeats [2] (1/10)
  - SQL: `WITH avg_revenue_per_product AS ( SELECT AVG(revenue) AS avg_rev FROM ( SELECT product, SUM(revenue) AS revenue FROM sales GROUP BY product ) AS product_revenue ) SELECT s.product, SUM(s.revenue) AS total_revenue FROM sales s JOIN avg_revenue_per_product ar ON TRUE GROUP BY s.product HAVING SUM(s.revenue) > ar.avg_rev ORDER BY total_revenue DESC;`
  - Result: (Ivory Stand, 194731.78); (Slate Dock, 188921.52); (Onyx Webcam, 186622.05); (Ember Charger, 174983.62); (Quartz Mouse, 157348.40); (Fable Tablet, 149597.28)

- **PASS** · repeats [3,5] (2/10)
  - SQL: `WITH product_revenue AS ( SELECT product, SUM(revenue) AS total_revenue FROM sales GROUP BY product ), avg_revenue AS ( SELECT AVG(total_revenue) AS average_revenue FROM product_revenue ) SELECT p.product, p.total_revenue FROM product_revenue p, avg_revenue a WHERE p.total_revenue > a.average_revenue ORDER BY p.total_revenue DESC;`
  - Result: (Ivory Stand, 194731.78); (Slate Dock, 188921.52); (Onyx Webcam, 186622.05); (Ember Charger, 174983.62); (Quartz Mouse, 157348.40); (Fable Tablet, 149597.28)

- **PASS** · repeats [6] (1/10)
  - SQL: `WITH product_revenue AS ( SELECT product, SUM(revenue) AS total_revenue FROM sales GROUP BY product ), average_revenue AS ( SELECT AVG(total_revenue) AS avg_total_revenue FROM product_revenue ) SELECT p.product, p.total_revenue FROM product_revenue p, average_revenue a WHERE p.total_revenue > a.avg_total_revenue ORDER BY p.total_revenue DESC;`
  - Result: (Ivory Stand, 194731.78); (Slate Dock, 188921.52); (Onyx Webcam, 186622.05); (Ember Charger, 174983.62); (Quartz Mouse, 157348.40); (Fable Tablet, 149597.28)

- **PASS** · repeats [7] (1/10) · tool-errors=1
  - SQL: `WITH product_revenues AS ( SELECT product, SUM(revenue) AS total_revenue FROM sales GROUP BY product ), avg_revenue AS ( SELECT AVG(total_revenue) AS avg_rev FROM product_revenues ) SELECT pr.product, pr.total_revenue FROM product_revenues pr, avg_revenue ar WHERE pr.total_revenue > ar.avg_rev ORDER BY pr.total_revenue DESC;`
  - Result: (Ivory Stand, 194731.78); (Slate Dock, 188921.52); (Onyx Webcam, 186622.05); (Ember Charger, 174983.62); (Quartz Mouse, 157348.40); (Fable Tablet, 149597.28)

- **PASS** · repeats [8] (1/10)
  - SQL: `WITH avg_revenue_per_product AS ( SELECT AVG(revenue) AS avg_rev FROM ( SELECT product, SUM(revenue) AS revenue FROM sales GROUP BY product ) AS product_revenues ) SELECT s.product, SUM(s.revenue) AS total_revenue FROM sales s JOIN avg_revenue_per_product ar ON TRUE GROUP BY s.product HAVING SUM(s.revenue) > (SELECT avg_rev FROM avg_revenue_per_product)`
  - Result: (Ember Charger, 174983.62); (Fable Tablet, 149597.28); (Ivory Stand, 194731.78); (Onyx Webcam, 186622.05); (Quartz Mouse, 157348.40); (Slate Dock, 188921.52)

- **PASS** · repeats [10] (1/10) · tool-errors=2
  - SQL: `WITH product_revenues AS ( SELECT product, SUM(revenue) AS total_revenue FROM sales GROUP BY product ), avg_revenue AS ( SELECT AVG(total_revenue) AS avg_rev FROM product_revenues ) SELECT pr.product, pr.total_revenue FROM product_revenues pr, avg_revenue ar WHERE pr.total_revenue > ar.avg_rev;`
  - Result: (Ember Charger, 174983.62); (Fable Tablet, 149597.28); (Ivory Stand, 194731.78); (Onyx Webcam, 186622.05); (Quartz Mouse, 157348.40); (Slate Dock, 188921.52)

#### gpt-oss-20b — 10/10 pass

- **PASS** · repeats [1,3] (2/10)
  - SQL: `WITH product_totals AS ( SELECT product, SUM(revenue) AS total_revenue FROM sales GROUP BY product ), avg_total AS ( SELECT AVG(total_revenue) AS avg_revenue FROM product_totals ) SELECT pt.product FROM product_totals pt, avg_total a WHERE pt.total_revenue > a.avg_revenue;`
  - Result: (Ember Charger); (Fable Tablet); (Ivory Stand); (Onyx Webcam); (Quartz Mouse); (Slate Dock)

- **PASS** · repeats [2] (1/10)
  - SQL: `WITH product_rev AS ( SELECT product, SUM(revenue) AS total_rev FROM sales GROUP BY product ), avg_rev AS ( SELECT AVG(total_rev) AS avg_rev FROM product_rev ) SELECT product FROM product_rev, avg_rev WHERE product_rev.total_rev > avg_rev.avg_rev;`
  - Result: (Ember Charger); (Fable Tablet); (Ivory Stand); (Onyx Webcam); (Quartz Mouse); (Slate Dock)

- **PASS** · repeats [4] (1/10)
  - SQL: `WITH product_rev AS ( SELECT product, SUM(revenue) AS total_rev FROM sales GROUP BY product ), avg_rev AS ( SELECT AVG(total_rev) AS avg_total_rev FROM product_rev ) SELECT product FROM product_rev, avg_rev WHERE product_rev.total_rev > avg_rev.avg_total_rev;`
  - Result: (Ember Charger); (Fable Tablet); (Ivory Stand); (Onyx Webcam); (Quartz Mouse); (Slate Dock)

- **PASS** · repeats [5] (1/10)
  - SQL: `WITH product_totals AS ( SELECT product, SUM(revenue) AS total_revenue FROM sales GROUP BY product ), avg_total AS ( SELECT AVG(total_revenue) AS avg_total_revenue FROM product_totals ) SELECT p.product FROM product_totals p CROSS JOIN avg_total a WHERE p.total_revenue > a.avg_total_revenue;`
  - Result: (Ember Charger); (Fable Tablet); (Ivory Stand); (Onyx Webcam); (Quartz Mouse); (Slate Dock)

- **PASS** · repeats [6] (1/10)
  - SQL: `WITH product_rev AS ( SELECT product, SUM(revenue) AS total_rev FROM sales GROUP BY product ), avg_rev AS ( SELECT AVG(total_rev) AS avg_total_rev FROM product_rev ) SELECT p.product, p.total_rev FROM product_rev p, avg_rev a WHERE p.total_rev > a.avg_total_rev;`
  - Result: (Ember Charger, 174983.62); (Fable Tablet, 149597.28); (Ivory Stand, 194731.78); (Onyx Webcam, 186622.05); (Quartz Mouse, 157348.40); (Slate Dock, 188921.52)

- **PASS** · repeats [7] (1/10)
  - SQL: `WITH product_totals AS ( SELECT product, SUM(revenue) AS total_revenue FROM sales GROUP BY product ), avg_total AS ( SELECT AVG(total_revenue) AS avg_revenue FROM product_totals ) SELECT p.product FROM product_totals p JOIN avg_total a ON 1=1 WHERE p.total_revenue > a.avg_revenue;`
  - Result: (Ember Charger); (Fable Tablet); (Ivory Stand); (Onyx Webcam); (Quartz Mouse); (Slate Dock)

- **PASS** · repeats [8] (1/10)
  - SQL: `WITH prod_rev AS ( SELECT product, SUM(revenue) AS total_rev FROM sales GROUP BY product ), avg_rev AS ( SELECT AVG(total_rev) AS avg_rev FROM prod_rev ) SELECT product FROM prod_rev, avg_rev WHERE prod_rev.total_rev > avg_rev.avg_rev;`
  - Result: (Ember Charger); (Fable Tablet); (Ivory Stand); (Onyx Webcam); (Quartz Mouse); (Slate Dock)

- **PASS** · repeats [9] (1/10)
  - SQL: `WITH product_revenue AS ( SELECT product, SUM(revenue) AS total_revenue FROM sales GROUP BY product ), avg_revenue AS ( SELECT AVG(total_revenue) AS avg_rev FROM product_revenue ) SELECT pr.product, pr.total_revenue FROM product_revenue pr, avg_revenue ar WHERE pr.total_revenue > ar.avg_rev ORDER BY pr.total_revenue DESC;`
  - Result: (Ivory Stand, 194731.78); (Slate Dock, 188921.52); (Onyx Webcam, 186622.05); (Ember Charger, 174983.62); (Quartz Mouse, 157348.40); (Fable Tablet, 149597.28)

- **PASS** · repeats [10] (1/10)
  - SQL: `SELECT product FROM ( SELECT product, SUM(revenue) AS total_rev, AVG(SUM(revenue)) OVER () AS avg_rev FROM sales GROUP BY product ) t WHERE total_rev > avg_rev;`
  - Result: (Ember Charger); (Fable Tablet); (Ivory Stand); (Onyx Webcam); (Quartz Mouse); (Slate Dock)

#### ollama-cloud — 10/10 pass

- **PASS** · repeats [1] (1/10)
  - SQL: `SELECT product, SUM(revenue) AS total_revenue FROM sales GROUP BY product HAVING SUM(revenue) > ( SELECT AVG(product_rev) FROM ( SELECT SUM(revenue) AS product_rev FROM sales GROUP BY product ) );`
  - Result: (Ember Charger, 174983.62); (Fable Tablet, 149597.28); (Ivory Stand, 194731.78); (Onyx Webcam, 186622.05); (Quartz Mouse, 157348.40); (Slate Dock, 188921.52)

- **PASS** · repeats [2,6] (2/10)
  - SQL: `WITH product_rev AS ( SELECT product, SUM(revenue) AS total_rev FROM sales GROUP BY product ), avg_rev AS ( SELECT AVG(total_rev) AS avg_rev FROM product_rev ) SELECT p.product, p.total_rev FROM product_rev p, avg_rev a WHERE p.total_rev > a.avg_rev ORDER BY p.total_rev DESC;`
  - Result: (Ivory Stand, 194731.78); (Slate Dock, 188921.52); (Onyx Webcam, 186622.05); (Ember Charger, 174983.62); (Quartz Mouse, 157348.40); (Fable Tablet, 149597.28)

- **PASS** · repeats [3] (1/10)
  - SQL: `WITH product_revenue AS ( SELECT product, SUM(revenue) AS total_revenue FROM sales GROUP BY product ), avg_rev AS ( SELECT AVG(total_revenue) AS avg_total_rev FROM product_revenue ) SELECT pr.product, pr.total_revenue FROM product_revenue pr, avg_rev a WHERE pr.total_revenue > a.avg_total_rev ORDER BY pr.total_revenue DESC;`
  - Result: (Ivory Stand, 194731.78); (Slate Dock, 188921.52); (Onyx Webcam, 186622.05); (Ember Charger, 174983.62); (Quartz Mouse, 157348.40); (Fable Tablet, 149597.28)

- **PASS** · repeats [4] (1/10)
  - SQL: `WITH prod_rev AS (SELECT product, SUM(revenue) AS total_revenue FROM sales GROUP BY product), avg_rev AS (SELECT AVG(total_revenue) AS avg_revenue FROM prod_rev) SELECT p.product, p.total_revenue FROM prod_rev p, avg_rev a WHERE p.total_revenue > a.avg_revenue ORDER BY p.total_revenue DESC;`
  - Result: (Ivory Stand, 194731.78); (Slate Dock, 188921.52); (Onyx Webcam, 186622.05); (Ember Charger, 174983.62); (Quartz Mouse, 157348.40); (Fable Tablet, 149597.28)

- **PASS** · repeats [5] (1/10)
  - SQL: `WITH prod_rev AS ( SELECT product, SUM(revenue) AS total_rev FROM sales GROUP BY product ) SELECT product FROM prod_rev WHERE total_rev > (SELECT AVG(total_rev) FROM prod_rev);`
  - Result: (Ember Charger); (Fable Tablet); (Ivory Stand); (Onyx Webcam); (Quartz Mouse); (Slate Dock)

- **PASS** · repeats [7] (1/10)
  - SQL: `SELECT product, SUM(revenue) AS total_revenue FROM sales GROUP BY product HAVING total_revenue > ( SELECT AVG(product_rev) FROM ( SELECT SUM(revenue) AS product_rev FROM sales GROUP BY product ) sub );`
  - Result: (Ember Charger, 174983.62); (Fable Tablet, 149597.28); (Ivory Stand, 194731.78); (Onyx Webcam, 186622.05); (Quartz Mouse, 157348.40); (Slate Dock, 188921.52)

- **PASS** · repeats [8] (1/10)
  - SQL: `WITH product_rev AS (SELECT product, SUM(revenue) AS total_rev FROM sales GROUP BY product), avg_rev AS (SELECT AVG(total_rev) AS avg_rev FROM product_rev) SELECT pr.product FROM product_rev pr, avg_rev a WHERE pr.total_rev > a.avg_rev;`
  - Result: (Ember Charger); (Fable Tablet); (Ivory Stand); (Onyx Webcam); (Quartz Mouse); (Slate Dock)

- **PASS** · repeats [9] (1/10)
  - SQL: `WITH prod_rev AS ( SELECT product, SUM(revenue) AS total_rev FROM sales GROUP BY product ), avg_rev AS ( SELECT AVG(total_rev) AS avg_rev FROM prod_rev ) SELECT p.product FROM prod_rev p, avg_rev a WHERE p.total_rev > a.avg_rev;`
  - Result: (Ember Charger); (Fable Tablet); (Ivory Stand); (Onyx Webcam); (Quartz Mouse); (Slate Dock)

- **PASS** · repeats [10] (1/10)
  - SQL: `WITH prod_rev AS ( SELECT product, SUM(revenue) AS total_rev FROM sales GROUP BY product ), avg_rev AS ( SELECT AVG(total_rev) AS avg_total_rev FROM prod_rev ) SELECT p.product, p.total_rev FROM prod_rev p, avg_rev a WHERE p.total_rev > a.avg_total_rev ORDER BY p.total_rev DESC;`
  - Result: (Ivory Stand, 194731.78); (Slate Dock, 188921.52); (Onyx Webcam, 186622.05); (Ember Charger, 174983.62); (Quartz Mouse, 157348.40); (Fable Tablet, 149597.28)

#### qwen3-coder — 10/10 pass

- **PASS** · repeats [1,5,8] (3/10)
  - SQL: `WITH product_revenues AS ( SELECT product, SUM(revenue) AS total_revenue FROM sales GROUP BY product ), average_revenue AS ( SELECT AVG(total_revenue) AS avg_revenue FROM product_revenues ) SELECT product FROM product_revenues WHERE total_revenue > (SELECT avg_revenue FROM average_revenue) ORDER BY total_revenue DESC;`
  - Result: (Ivory Stand); (Slate Dock); (Onyx Webcam); (Ember Charger); (Quartz Mouse); (Fable Tablet)

- **PASS** · repeats [2] (1/10)
  - SQL: `WITH ProductRevenue AS ( SELECT product, SUM(revenue) AS total_revenue FROM sales GROUP BY product ), AverageRevenue AS ( SELECT AVG(total_revenue) AS avg_revenue FROM ProductRevenue ) SELECT product FROM ProductRevenue WHERE total_revenue > (SELECT avg_revenue FROM AverageRevenue) ORDER BY total_revenue DESC;`
  - Result: (Ivory Stand); (Slate Dock); (Onyx Webcam); (Ember Charger); (Quartz Mouse); (Fable Tablet)

- **PASS** · repeats [3] (1/10)
  - SQL: `WITH product_revenues AS ( SELECT product, SUM(revenue) AS total_revenue FROM sales GROUP BY product ), avg_revenue AS ( SELECT AVG(total_revenue) AS avg_total_revenue FROM product_revenues ) SELECT product FROM product_revenues WHERE total_revenue > (SELECT avg_total_revenue FROM avg_revenue)`
  - Result: (Ember Charger); (Fable Tablet); (Ivory Stand); (Onyx Webcam); (Quartz Mouse); (Slate Dock)

- **PASS** · repeats [4,6] (2/10)
  - SQL: `WITH ProductRevenue AS ( SELECT product, SUM(revenue) AS total_revenue FROM sales GROUP BY product ), AverageRevenue AS ( SELECT AVG(total_revenue) AS avg_revenue FROM ProductRevenue ) SELECT product, total_revenue FROM ProductRevenue WHERE total_revenue > (SELECT avg_revenue FROM AverageRevenue) ORDER BY total_revenue DESC;`
  - Result: (Ivory Stand, 194731.78); (Slate Dock, 188921.52); (Onyx Webcam, 186622.05); (Ember Charger, 174983.62); (Quartz Mouse, 157348.40); (Fable Tablet, 149597.28)

- **PASS** · repeats [7,9] (2/10)
  - SQL: `WITH product_revenues AS ( SELECT product, SUM(revenue) AS total_revenue FROM sales GROUP BY product ), average_revenue AS ( SELECT AVG(total_revenue) AS avg_revenue FROM product_revenues ) SELECT product, total_revenue FROM product_revenues WHERE total_revenue > (SELECT avg_revenue FROM average_revenue) ORDER BY total_revenue DESC;`
  - Result: (Ivory Stand, 194731.78); (Slate Dock, 188921.52); (Onyx Webcam, 186622.05); (Ember Charger, 174983.62); (Quartz Mouse, 157348.40); (Fable Tablet, 149597.28)

- **PASS** · repeats [10] (1/10)
  - SQL: `WITH product_revenue AS ( SELECT product, SUM(revenue) AS total_revenue FROM sales GROUP BY product ), average_revenue AS ( SELECT AVG(total_revenue) AS avg_revenue FROM product_revenue ) SELECT product FROM product_revenue WHERE total_revenue > (SELECT avg_revenue FROM average_revenue)`
  - Result: (Ember Charger); (Fable Tablet); (Ivory Stand); (Onyx Webcam); (Quartz Mouse); (Slate Dock)

### L4a_top_product_per_quarter  (Level 4)
**Question:** For each quarter, which single product had the highest revenue in that quarter, and how much?
**Expected (ground truth):** Q1->Slate Dock, Q2->Slate Dock, Q3->Ivory Stand, Q4->Ivory Stand

#### ministral-8b — 10/10 pass

- **PASS** · repeats [1] (1/10)
  - SQL: `WITH quarterly_revenue AS ( SELECT quarter, product, SUM(revenue) AS total_revenue FROM sales GROUP BY quarter, product ORDER BY quarter, total_revenue DESC ) SELECT quarter, product AS top_product, total_revenue AS revenue FROM ( SELECT quarter, product, total_revenue, ROW_NUMBER() OVER (PARTITION BY quarter ORDER BY total_revenue DESC) AS rank FROM quarterly_revenue ) ranked_products WHERE rank = 1 ORDER BY quarter;`
  - Result: (Q1, Slate Dock, 57240.97); (Q2, Slate Dock, 55183.55); (Q3, Ivory Stand, 35502.43); (Q4, Ivory Stand, 60310.53)

- **PASS** · repeats [2,6] (2/10)
  - SQL: `WITH quarterly_revenue AS ( SELECT quarter, product, SUM(revenue) AS total_revenue FROM sales GROUP BY quarter, product ORDER BY quarter, total_revenue DESC ) SELECT quarter, product AS top_product, total_revenue AS revenue_amount FROM ( SELECT quarter, product, total_revenue, ROW_NUMBER() OVER (PARTITION BY quarter ORDER BY total_revenue DESC) AS rank FROM quarterly_revenue ) ranked_products WHERE rank = 1 ORDER BY quarter;`
  - Result: (Q1, Slate Dock, 57240.97); (Q2, Slate Dock, 55183.55); (Q3, Ivory Stand, 35502.43); (Q4, Ivory Stand, 60310.53)

- **PASS** · repeats [3] (1/10)
  - SQL: `WITH ranked_products AS ( SELECT quarter, product, SUM(revenue) AS total_revenue, RANK() OVER (PARTITION BY quarter ORDER BY SUM(revenue) DESC) AS revenue_rank FROM sales GROUP BY quarter, product ) SELECT quarter, product AS top_product, total_revenue AS revenue_amount FROM ranked_products WHERE revenue_rank = 1`
  - Result: (Q1, Slate Dock, 57240.97); (Q2, Slate Dock, 55183.55); (Q3, Ivory Stand, 35502.43); (Q4, Ivory Stand, 60310.53)

- **PASS** · repeats [4,8] (2/10)
  - SQL: `WITH quarterly_revenue AS ( SELECT quarter, product, SUM(revenue) AS total_revenue FROM sales GROUP BY quarter, product ORDER BY quarter, total_revenue DESC ) SELECT quarter, product AS top_product, total_revenue AS revenue_amount FROM ( SELECT quarter, product, total_revenue, ROW_NUMBER() OVER (PARTITION BY quarter ORDER BY total_revenue DESC) AS rank FROM quarterly_revenue ) ranked_products WHERE rank = 1;`
  - Result: (Q1, Slate Dock, 57240.97); (Q2, Slate Dock, 55183.55); (Q3, Ivory Stand, 35502.43); (Q4, Ivory Stand, 60310.53)

- **PASS** · repeats [5] (1/10)
  - SQL: `WITH quarterly_revenue AS ( SELECT quarter, product, SUM(revenue) AS total_revenue FROM sales GROUP BY quarter, product ) SELECT quarter, product AS top_product, total_revenue AS revenue FROM ( SELECT quarter, product, total_revenue, RANK() OVER (PARTITION BY quarter ORDER BY total_revenue DESC) AS rank FROM quarterly_revenue ) ranked_products WHERE rank = 1`
  - Result: (Q1, Slate Dock, 57240.97); (Q2, Slate Dock, 55183.55); (Q3, Ivory Stand, 35502.43); (Q4, Ivory Stand, 60310.53)

- **PASS** · repeats [7,10] (2/10)
  - SQL: `WITH quarterly_revenue AS ( SELECT quarter, product, SUM(revenue) AS total_revenue FROM sales GROUP BY quarter, product ORDER BY quarter, total_revenue DESC ) SELECT quarter, product AS top_product, total_revenue AS revenue FROM ( SELECT quarter, product, total_revenue, ROW_NUMBER() OVER (PARTITION BY quarter ORDER BY total_revenue DESC) AS rank FROM quarterly_revenue ) ranked_products WHERE rank = 1;`
  - Result: (Q1, Slate Dock, 57240.97); (Q2, Slate Dock, 55183.55); (Q3, Ivory Stand, 35502.43); (Q4, Ivory Stand, 60310.53)

- **PASS** · repeats [9] (1/10)
  - SQL: `WITH quarterly_revenue AS ( SELECT quarter, product, SUM(revenue) AS total_revenue FROM sales GROUP BY quarter, product ) SELECT quarter, product AS top_product, total_revenue AS revenue_amount FROM ( SELECT quarter, product, total_revenue, RANK() OVER (PARTITION BY quarter ORDER BY total_revenue DESC) AS rank FROM quarterly_revenue ) ranked_products WHERE rank = 1`
  - Result: (Q1, Slate Dock, 57240.97); (Q2, Slate Dock, 55183.55); (Q3, Ivory Stand, 35502.43); (Q4, Ivory Stand, 60310.53)

#### gpt-oss-20b — 10/10 pass

- **PASS** · repeats [1,3,5,8,10] (5/10)
  - SQL: `SELECT quarter, product, revenue FROM ( SELECT quarter, product, SUM(revenue) AS revenue, RANK() OVER (PARTITION BY quarter ORDER BY SUM(revenue) DESC) AS rnk FROM sales GROUP BY quarter, product ) sub WHERE rnk = 1 ORDER BY quarter;`
  - Result: (Q1, Slate Dock, 57240.97); (Q2, Slate Dock, 55183.55); (Q3, Ivory Stand, 35502.43); (Q4, Ivory Stand, 60310.53)

- **PASS** · repeats [2] (1/10)
  - SQL: `SELECT quarter, product, revenue FROM (SELECT quarter, product, SUM(revenue) AS revenue, ROW_NUMBER() OVER (PARTITION BY quarter ORDER BY SUM(revenue) DESC) AS rn FROM sales GROUP BY quarter, product) WHERE rn = 1;`
  - Result: (Q1, Slate Dock, 57240.97); (Q2, Slate Dock, 55183.55); (Q3, Ivory Stand, 35502.43); (Q4, Ivory Stand, 60310.53)

- **PASS** · repeats [4] (1/10)
  - SQL: `WITH revenue_by_product AS ( SELECT quarter, product, SUM(revenue) AS total_revenue FROM sales GROUP BY quarter, product ), ranked AS ( SELECT *, ROW_NUMBER() OVER (PARTITION BY quarter ORDER BY total_revenue DESC) AS rn FROM revenue_by_product ) SELECT quarter, product, total_revenue FROM ranked WHERE rn = 1 ORDER BY quarter;`
  - Result: (Q1, Slate Dock, 57240.97); (Q2, Slate Dock, 55183.55); (Q3, Ivory Stand, 35502.43); (Q4, Ivory Stand, 60310.53)

- **PASS** · repeats [6] (1/10)
  - SQL: `SELECT quarter, product, revenue FROM (SELECT quarter, product, SUM(revenue) AS revenue, RANK() OVER (PARTITION BY quarter ORDER BY SUM(revenue) DESC) AS rnk FROM sales GROUP BY quarter, product) WHERE rnk = 1;`
  - Result: (Q1, Slate Dock, 57240.97); (Q2, Slate Dock, 55183.55); (Q3, Ivory Stand, 35502.43); (Q4, Ivory Stand, 60310.53)

- **PASS** · repeats [7,9] (2/10)
  - SQL: `SELECT quarter, product, revenue FROM ( SELECT quarter, product, SUM(revenue) AS revenue, RANK() OVER (PARTITION BY quarter ORDER BY SUM(revenue) DESC) AS rnk FROM sales GROUP BY quarter, product ) sub WHERE rnk = 1;`
  - Result: (Q1, Slate Dock, 57240.97); (Q2, Slate Dock, 55183.55); (Q3, Ivory Stand, 35502.43); (Q4, Ivory Stand, 60310.53)

#### ollama-cloud — 10/10 pass

- **PASS** · repeats [1,8] (2/10)
  - SQL: `WITH rev AS ( SELECT quarter, product, SUM(revenue) AS total_revenue FROM sales GROUP BY quarter, product ), ranked AS ( SELECT quarter, product, total_revenue, ROW_NUMBER() OVER (PARTITION BY quarter ORDER BY total_revenue DESC) AS rn FROM rev ) SELECT quarter, product AS top_product, total_revenue AS revenue FROM ranked WHERE rn = 1 ORDER BY quarter;`
  - Result: (Q1, Slate Dock, 57240.97); (Q2, Slate Dock, 55183.55); (Q3, Ivory Stand, 35502.43); (Q4, Ivory Stand, 60310.53)

- **PASS** · repeats [2] (1/10)
  - SQL: `WITH product_rev AS ( SELECT quarter, product, SUM(revenue) AS total_rev FROM sales GROUP BY quarter, product ), ranked AS ( SELECT quarter, product, total_rev, ROW_NUMBER() OVER (PARTITION BY quarter ORDER BY total_rev DESC) AS rn FROM product_rev ) SELECT quarter, product, total_rev FROM ranked WHERE rn = 1 ORDER BY quarter;`
  - Result: (Q1, Slate Dock, 57240.97); (Q2, Slate Dock, 55183.55); (Q3, Ivory Stand, 35502.43); (Q4, Ivory Stand, 60310.53)

- **PASS** · repeats [3] (1/10)
  - SQL: `WITH prod_rev AS ( SELECT quarter, product, SUM(revenue) AS total_rev FROM sales GROUP BY quarter, product ), ranked AS ( SELECT quarter, product, total_rev, ROW_NUMBER() OVER (PARTITION BY quarter ORDER BY total_rev DESC) AS rn FROM prod_rev ) SELECT quarter, product, total_rev AS revenue FROM ranked WHERE rn = 1 ORDER BY quarter;`
  - Result: (Q1, Slate Dock, 57240.97); (Q2, Slate Dock, 55183.55); (Q3, Ivory Stand, 35502.43); (Q4, Ivory Stand, 60310.53)

- **PASS** · repeats [4] (1/10)
  - SQL: `SELECT quarter, product, revenue_total FROM ( SELECT quarter, product, SUM(revenue) AS revenue_total, ROW_NUMBER() OVER (PARTITION BY quarter ORDER BY SUM(revenue) DESC) AS rn FROM sales GROUP BY quarter, product ) t WHERE rn = 1 ORDER BY quarter;`
  - Result: (Q1, Slate Dock, 57240.97); (Q2, Slate Dock, 55183.55); (Q3, Ivory Stand, 35502.43); (Q4, Ivory Stand, 60310.53)

- **PASS** · repeats [5,6] (2/10)
  - SQL: `WITH rev AS ( SELECT quarter, product, SUM(revenue) AS total_rev FROM sales GROUP BY quarter, product ), ranked AS ( SELECT quarter, product, total_rev, ROW_NUMBER() OVER (PARTITION BY quarter ORDER BY total_rev DESC) AS rn FROM rev ) SELECT quarter, product, total_rev FROM ranked WHERE rn = 1 ORDER BY quarter;`
  - Result: (Q1, Slate Dock, 57240.97); (Q2, Slate Dock, 55183.55); (Q3, Ivory Stand, 35502.43); (Q4, Ivory Stand, 60310.53)

- **PASS** · repeats [7] (1/10)
  - SQL: `WITH prod_rev AS ( SELECT quarter, product, SUM(revenue) AS total_rev FROM sales GROUP BY quarter, product ), ranked AS ( SELECT quarter, product, total_rev, ROW_NUMBER() OVER (PARTITION BY quarter ORDER BY total_rev DESC) AS rn FROM prod_rev ) SELECT quarter, product AS top_product, total_rev AS revenue FROM ranked WHERE rn = 1 ORDER BY quarter;`
  - Result: (Q1, Slate Dock, 57240.97); (Q2, Slate Dock, 55183.55); (Q3, Ivory Stand, 35502.43); (Q4, Ivory Stand, 60310.53)

- **PASS** · repeats [9] (1/10)
  - SQL: `WITH rev AS ( SELECT quarter, product, SUM(revenue) AS revenue_sum FROM sales GROUP BY quarter, product ), ranked AS ( SELECT quarter, product, revenue_sum, ROW_NUMBER() OVER (PARTITION BY quarter ORDER BY revenue_sum DESC) AS rn FROM rev ) SELECT quarter, product, ROUND(revenue_sum, 2) AS revenue FROM ranked WHERE rn = 1 ORDER BY quarter;`
  - Result: (Q1, Slate Dock, 57240.97); (Q2, Slate Dock, 55183.55); (Q3, Ivory Stand, 35502.43); (Q4, Ivory Stand, 60310.53)

- **PASS** · repeats [10] (1/10)
  - SQL: `WITH product_rev AS ( SELECT quarter, product, SUM(revenue) AS total_revenue FROM sales GROUP BY quarter, product ), ranked AS ( SELECT quarter, product, total_revenue, ROW_NUMBER() OVER (PARTITION BY quarter ORDER BY total_revenue DESC) AS rn FROM product_rev ) SELECT quarter, product, total_revenue AS revenue FROM ranked WHERE rn = 1 ORDER BY quarter;`
  - Result: (Q1, Slate Dock, 57240.97); (Q2, Slate Dock, 55183.55); (Q3, Ivory Stand, 35502.43); (Q4, Ivory Stand, 60310.53)

#### qwen3-coder — 10/10 pass

- **PASS** · repeats [1,6,9] (3/10)
  - SQL: `WITH quarterly_product_revenue AS ( SELECT quarter, product, SUM(revenue) as total_revenue FROM sales GROUP BY quarter, product ), ranked_products AS ( SELECT quarter, product, total_revenue, ROW_NUMBER() OVER (PARTITION BY quarter ORDER BY total_revenue DESC) as rank FROM quarterly_product_revenue ) SELECT quarter, product, total_revenue FROM ranked_products WHERE rank = 1 ORDER BY quarter`
  - Result: (Q1, Slate Dock, 57240.97); (Q2, Slate Dock, 55183.55); (Q3, Ivory Stand, 35502.43); (Q4, Ivory Stand, 60310.53)

- **PASS** · repeats [2,3] (2/10)
  - SQL: `WITH quarterly_product_revenue AS ( SELECT quarter, product, SUM(revenue) AS total_revenue FROM sales GROUP BY quarter, product ), ranked_products AS ( SELECT quarter, product, total_revenue, ROW_NUMBER() OVER (PARTITION BY quarter ORDER BY total_revenue DESC) AS rank FROM quarterly_product_revenue ) SELECT quarter, product, total_revenue FROM ranked_products WHERE rank = 1 ORDER BY quarter`
  - Result: (Q1, Slate Dock, 57240.97); (Q2, Slate Dock, 55183.55); (Q3, Ivory Stand, 35502.43); (Q4, Ivory Stand, 60310.53)

- **PASS** · repeats [4,5,7] (3/10)
  - SQL: `WITH quarterly_product_revenue AS ( SELECT quarter, product, SUM(revenue) AS total_revenue FROM sales GROUP BY quarter, product ), ranked_products AS ( SELECT quarter, product, total_revenue, ROW_NUMBER() OVER (PARTITION BY quarter ORDER BY total_revenue DESC) AS rank FROM quarterly_product_revenue ) SELECT quarter, product, total_revenue FROM ranked_products WHERE rank = 1 ORDER BY quarter;`
  - Result: (Q1, Slate Dock, 57240.97); (Q2, Slate Dock, 55183.55); (Q3, Ivory Stand, 35502.43); (Q4, Ivory Stand, 60310.53)

- **PASS** · repeats [8,10] (2/10)
  - SQL: `WITH RankedProducts AS ( SELECT quarter, product, SUM(revenue) AS total_revenue, ROW_NUMBER() OVER (PARTITION BY quarter ORDER BY SUM(revenue) DESC) AS rank FROM sales GROUP BY quarter, product ) SELECT quarter, product, total_revenue FROM RankedProducts WHERE rank = 1 ORDER BY quarter;`
  - Result: (Q1, Slate Dock, 57240.97); (Q2, Slate Dock, 55183.55); (Q3, Ivory Stand, 35502.43); (Q4, Ivory Stand, 60310.53)

### L4b_running_monthly_total  (Level 4)
**Question:** Show the cumulative (running) total of revenue by month across the year — each month's figure should include all prior months.
**Expected (ground truth):** 2024-01:163081.67, 2024-02:324830.92, 2024-03:487110.25, 2024-04:649643.89, 2024-05:810345.26, 2024-06:968869.76, 2024-07:1067208.71, 2024-08:1166572.9, 2024-09:1266224.05, 2024-10:1425984.98, 2024-11:1585942.51, 2024-12:1748224.2

#### ministral-8b — 10/10 pass

- **PASS** · repeats [1,3,4] (3/10) · tool-errors=1
  - SQL: `WITH monthly_revenue AS ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS total_revenue FROM sales GROUP BY strftime('%Y-%m', sale_date) ORDER BY strftime('%Y-%m', sale_date) ) SELECT month, SUM(total_revenue) OVER (ORDER BY month) AS cumulative_revenue FROM monthly_revenue;`
  - Result: (2024-01, 163081.67); (2024-02, 324830.92); (2024-03, 487110.25); (2024-04, 649643.89); (2024-05, 810345.26); (2024-06, 968869.76); (2024-07, 1067208.71); (2024-08, 1166572.90); (2024-09, 1266224.05); (2024-10, 1425984.98); (2024-11, 1585942.51); (2024-12, 1748224.20)

- **PASS** · repeats [2] (1/10) · tool-errors=3
  - SQL: `WITH monthly_revenue AS ( SELECT STRFTIME('%m', sale_date) AS month, SUM(revenue) AS total_revenue FROM sales GROUP BY STRFTIME('%m', sale_date) ORDER BY STRFTIME('%m', sale_date) ), cumulative_revenue AS ( SELECT month, SUM(total_revenue) OVER (ORDER BY month) AS cumulative_total_revenue FROM monthly_revenue ) SELECT month, cumulative_total_revenue, STRFTIME('%Y-%m-01', STRFTIME('%Y-%m', '2024-01-01', month || '-01')) AS month_date FROM cumulative_revenue ORDER BY month;`
  - Result: (01, 163081.67, None); (02, 324830.92, None); (03, 487110.25, None); (04, 649643.89, None); (05, 810345.26, None); (06, 968869.76, None); (07, 1067208.71, None); (08, 1166572.90, None); (09, 1266224.05, None); (10, 1425984.98, None); (11, 1585942.51, None); (12, 1748224.20, None)

- **PASS** · repeats [5] (1/10) · tool-errors=1
  - SQL: `WITH monthly_revenue AS ( SELECT STRFTIME('%m', sale_date) AS month, SUM(revenue) AS total_revenue FROM sales GROUP BY STRFTIME('%m', sale_date) ORDER BY month ), cumulative_revenue AS ( SELECT month, total_revenue, SUM(total_revenue) OVER (ORDER BY month) AS cumulative_total FROM monthly_revenue ) SELECT month, total_revenue, cumulative_total FROM cumulative_revenue ORDER BY month;`
  - Result: (01, 163081.67, 163081.67); (02, 161749.25, 324830.92); (03, 162279.33, 487110.25); (04, 162533.64, 649643.89); (05, 160701.37, 810345.26); (06, 158524.50, 968869.76); (07, 98338.95, 1067208.71); (08, 99364.19, 1166572.90); (09, 99651.15, 1266224.05); (10, 159760.93, 1425984.98); (11, 159957.53, 1585942.51); (12, 162281.69, 1748224.20)

- **PASS** · repeats [6] (1/10) · tool-errors=6
  - SQL: `WITH monthly_revenue AS ( SELECT STRFTIME('%m', sale_date) AS month, SUM(revenue) AS total_revenue FROM sales GROUP BY STRFTIME('%m', sale_date) ORDER BY STRFTIME('%m', sale_date) ), monthly_cumulative AS ( SELECT month, total_revenue, SUM(total_revenue) OVER (ORDER BY month) AS cumulative_revenue FROM monthly_revenue ) SELECT month, total_revenue AS monthly_revenue, cumulative_revenue FROM monthly_cumulative;`
  - Result: (01, 163081.67, 163081.67); (02, 161749.25, 324830.92); (03, 162279.33, 487110.25); (04, 162533.64, 649643.89); (05, 160701.37, 810345.26); (06, 158524.50, 968869.76); (07, 98338.95, 1067208.71); (08, 99364.19, 1166572.90); (09, 99651.15, 1266224.05); (10, 159760.93, 1425984.98); (11, 159957.53, 1585942.51); (12, 162281.69, 1748224.20)

- **PASS** · repeats [7] (1/10) · tool-errors=1
  - SQL: `WITH monthly_revenue AS ( SELECT STRFTIME('%m', sale_date) AS month, SUM(revenue) AS total_revenue FROM sales GROUP BY STRFTIME('%m', sale_date) ORDER BY STRFTIME('%m', sale_date) ), cumulative_revenue AS ( SELECT month, SUM(total_revenue) OVER (ORDER BY month) AS cumulative_total_revenue FROM monthly_revenue ) SELECT * FROM cumulative_revenue;`
  - Result: (01, 163081.67); (02, 324830.92); (03, 487110.25); (04, 649643.89); (05, 810345.26); (06, 968869.76); (07, 1067208.71); (08, 1166572.90); (09, 1266224.05); (10, 1425984.98); (11, 1585942.51); (12, 1748224.20)

- **PASS** · repeats [8] (1/10) · tool-errors=1
  - SQL: `WITH monthly_revenue AS ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS total_revenue FROM sales GROUP BY strftime('%Y-%m', sale_date) ORDER BY month ), cumulative_revenue AS ( SELECT month, total_revenue, SUM(total_revenue) OVER (ORDER BY month) AS cumulative_total FROM monthly_revenue ) SELECT * FROM cumulative_revenue;`
  - Result: (2024-01, 163081.67, 163081.67); (2024-02, 161749.25, 324830.92); (2024-03, 162279.33, 487110.25); (2024-04, 162533.64, 649643.89); (2024-05, 160701.37, 810345.26); (2024-06, 158524.50, 968869.76); (2024-07, 98338.95, 1067208.71); (2024-08, 99364.19, 1166572.90); (2024-09, 99651.15, 1266224.05); (2024-10, 159760.93, 1425984.98); (2024-11, 159957.53, 1585942.51); (2024-12, 162281.69, 1748224.20)

- **PASS** · repeats [9] (1/10) · tool-errors=2
  - SQL: `WITH monthly_revenue AS ( SELECT STRFTIME('%m', sale_date) AS month, SUM(revenue) AS total_revenue FROM sales GROUP BY STRFTIME('%m', sale_date) ORDER BY STRFTIME('%m', sale_date) ), monthly_cumulative AS ( SELECT month, SUM(total_revenue) OVER (ORDER BY CAST(month AS INTEGER)) AS cumulative_revenue FROM monthly_revenue ) SELECT month, cumulative_revenue FROM monthly_cumulative;`
  - Result: (01, 163081.67); (02, 324830.92); (03, 487110.25); (04, 649643.89); (05, 810345.26); (06, 968869.76); (07, 1067208.71); (08, 1166572.90); (09, 1266224.05); (10, 1425984.98); (11, 1585942.51); (12, 1748224.20)

- **PASS** · repeats [10] (1/10) · tool-errors=3
  - SQL: `WITH monthly_data AS ( SELECT strftime('%m', sale_date) AS month, SUM(revenue) AS month_revenue FROM sales GROUP BY strftime('%m', sale_date) ORDER BY month ), cumulative_data AS ( SELECT month, month_revenue, SUM(month_revenue) OVER (ORDER BY month) AS cumulative_revenue FROM monthly_data ) SELECT * FROM cumulative_data;`
  - Result: (01, 163081.67, 163081.67); (02, 161749.25, 324830.92); (03, 162279.33, 487110.25); (04, 162533.64, 649643.89); (05, 160701.37, 810345.26); (06, 158524.50, 968869.76); (07, 98338.95, 1067208.71); (08, 99364.19, 1166572.90); (09, 99651.15, 1266224.05); (10, 159760.93, 1425984.98); (11, 159957.53, 1585942.51); (12, 162281.69, 1748224.20)

#### gpt-oss-20b — 10/10 pass

- **PASS** · repeats [1,5] (2/10)
  - SQL: `SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS month_rev, SUM(SUM(revenue)) OVER (ORDER BY strftime('%Y-%m', sale_date)) AS cumulative_rev FROM sales GROUP BY month ORDER BY month;`
  - Result: (2024-01, 163081.67, 163081.67); (2024-02, 161749.25, 324830.92); (2024-03, 162279.33, 487110.25); (2024-04, 162533.64, 649643.89); (2024-05, 160701.37, 810345.26); (2024-06, 158524.50, 968869.76); (2024-07, 98338.95, 1067208.71); (2024-08, 99364.19, 1166572.90); (2024-09, 99651.15, 1266224.05); (2024-10, 159760.93, 1425984.98); (2024-11, 159957.53, 1585942.51); (2024-12, 162281.69, 1748224.20)

- **PASS** · repeats [2] (1/10)
  - SQL: `WITH monthly AS ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS month_rev FROM sales GROUP BY month ORDER BY month ), cumulative AS ( SELECT month, month_rev, SUM(month_rev) OVER (ORDER BY month) AS cum_rev FROM monthly ) SELECT month, cum_rev FROM cumulative ORDER BY month;`
  - Result: (2024-01, 163081.67); (2024-02, 324830.92); (2024-03, 487110.25); (2024-04, 649643.89); (2024-05, 810345.26); (2024-06, 968869.76); (2024-07, 1067208.71); (2024-08, 1166572.90); (2024-09, 1266224.05); (2024-10, 1425984.98); (2024-11, 1585942.51); (2024-12, 1748224.20)

- **PASS** · repeats [3,4] (2/10)
  - SQL: `SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS monthly_revenue, SUM(SUM(revenue)) OVER (ORDER BY strftime('%Y-%m', sale_date)) AS cumulative_revenue FROM sales GROUP BY month ORDER BY month;`
  - Result: (2024-01, 163081.67, 163081.67); (2024-02, 161749.25, 324830.92); (2024-03, 162279.33, 487110.25); (2024-04, 162533.64, 649643.89); (2024-05, 160701.37, 810345.26); (2024-06, 158524.50, 968869.76); (2024-07, 98338.95, 1067208.71); (2024-08, 99364.19, 1166572.90); (2024-09, 99651.15, 1266224.05); (2024-10, 159760.93, 1425984.98); (2024-11, 159957.53, 1585942.51); (2024-12, 162281.69, 1748224.20)

- **PASS** · repeats [6,7,8,9] (4/10)
  - SQL: `SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS month_revenue, SUM(SUM(revenue)) OVER (ORDER BY strftime('%Y-%m', sale_date)) AS cumulative_revenue FROM sales GROUP BY month ORDER BY month;`
  - Result: (2024-01, 163081.67, 163081.67); (2024-02, 161749.25, 324830.92); (2024-03, 162279.33, 487110.25); (2024-04, 162533.64, 649643.89); (2024-05, 160701.37, 810345.26); (2024-06, 158524.50, 968869.76); (2024-07, 98338.95, 1067208.71); (2024-08, 99364.19, 1166572.90); (2024-09, 99651.15, 1266224.05); (2024-10, 159760.93, 1425984.98); (2024-11, 159957.53, 1585942.51); (2024-12, 162281.69, 1748224.20)

- **PASS** · repeats [10] (1/10)
  - SQL: `WITH monthly AS ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS monthly_revenue FROM sales GROUP BY month ORDER BY month ), cumulative AS ( SELECT month, SUM(monthly_revenue) OVER (ORDER BY month) AS cumulative_revenue FROM monthly ) SELECT month, cumulative_revenue FROM cumulative ORDER BY month;`
  - Result: (2024-01, 163081.67); (2024-02, 324830.92); (2024-03, 487110.25); (2024-04, 649643.89); (2024-05, 810345.26); (2024-06, 968869.76); (2024-07, 1067208.71); (2024-08, 1166572.90); (2024-09, 1266224.05); (2024-10, 1425984.98); (2024-11, 1585942.51); (2024-12, 1748224.20)

#### ollama-cloud — 10/10 pass

- **PASS** · repeats [1] (1/10)
  - SQL: `SELECT month, SUM(month_rev) OVER (ORDER BY month ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_revenue FROM ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS month_rev FROM sales GROUP BY month ) AS sub ORDER BY month;`
  - Result: (2024-01, 163081.67); (2024-02, 324830.92); (2024-03, 487110.25); (2024-04, 649643.89); (2024-05, 810345.26); (2024-06, 968869.76); (2024-07, 1067208.71); (2024-08, 1166572.90); (2024-09, 1266224.05); (2024-10, 1425984.98); (2024-11, 1585942.51); (2024-12, 1748224.20)

- **PASS** · repeats [2] (1/10)
  - SQL: `WITH monthly AS ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS month_rev FROM sales GROUP BY month ) SELECT month, month_rev, SUM(month_rev) OVER (ORDER BY month ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_revenue FROM monthly ORDER BY month;`
  - Result: (2024-01, 163081.67, 163081.67); (2024-02, 161749.25, 324830.92); (2024-03, 162279.33, 487110.25); (2024-04, 162533.64, 649643.89); (2024-05, 160701.37, 810345.26); (2024-06, 158524.50, 968869.76); (2024-07, 98338.95, 1067208.71); (2024-08, 99364.19, 1166572.90); (2024-09, 99651.15, 1266224.05); (2024-10, 159760.93, 1425984.98); (2024-11, 159957.53, 1585942.51); (2024-12, 162281.69, 1748224.20)

- **PASS** · repeats [3] (1/10)
  - SQL: `WITH monthly AS ( SELECT substr(sale_date,1,7) AS month, SUM(revenue) AS month_rev FROM sales GROUP BY month ) SELECT month, month_rev, SUM(month_rev) OVER (ORDER BY month) AS cumulative_revenue FROM monthly ORDER BY month;`
  - Result: (2024-01, 163081.67, 163081.67); (2024-02, 161749.25, 324830.92); (2024-03, 162279.33, 487110.25); (2024-04, 162533.64, 649643.89); (2024-05, 160701.37, 810345.26); (2024-06, 158524.50, 968869.76); (2024-07, 98338.95, 1067208.71); (2024-08, 99364.19, 1166572.90); (2024-09, 99651.15, 1266224.05); (2024-10, 159760.93, 1425984.98); (2024-11, 159957.53, 1585942.51); (2024-12, 162281.69, 1748224.20)

- **PASS** · repeats [4] (1/10)
  - SQL: `SELECT substr(sale_date,1,7) AS year_month, SUM(revenue) AS monthly_revenue, SUM(SUM(revenue)) OVER (ORDER BY substr(sale_date,1,7) ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_revenue FROM sales GROUP BY year_month ORDER BY year_month;`
  - Result: (2024-01, 163081.67, 163081.67); (2024-02, 161749.25, 324830.92); (2024-03, 162279.33, 487110.25); (2024-04, 162533.64, 649643.89); (2024-05, 160701.37, 810345.26); (2024-06, 158524.50, 968869.76); (2024-07, 98338.95, 1067208.71); (2024-08, 99364.19, 1166572.90); (2024-09, 99651.15, 1266224.05); (2024-10, 159760.93, 1425984.98); (2024-11, 159957.53, 1585942.51); (2024-12, 162281.69, 1748224.20)

- **PASS** · repeats [5] (1/10)
  - SQL: `WITH monthly_rev AS ( SELECT substr(sale_date, 1, 7) AS month, SUM(revenue) AS month_revenue FROM sales WHERE substr(sale_date,1,4) = '2024' GROUP BY month ) SELECT month, SUM(month_revenue) OVER (ORDER BY month ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_revenue FROM monthly_rev ORDER BY month;`
  - Result: (2024-01, 163081.67); (2024-02, 324830.92); (2024-03, 487110.25); (2024-04, 649643.89); (2024-05, 810345.26); (2024-06, 968869.76); (2024-07, 1067208.71); (2024-08, 1166572.90); (2024-09, 1266224.05); (2024-10, 1425984.98); (2024-11, 1585942.51); (2024-12, 1748224.20)

- **PASS** · repeats [6] (1/10)
  - SQL: `SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS month_revenue, SUM(SUM(revenue)) OVER (ORDER BY strftime('%Y-%m', sale_date) ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_revenue FROM sales GROUP BY month ORDER BY month;`
  - Result: (2024-01, 163081.67, 163081.67); (2024-02, 161749.25, 324830.92); (2024-03, 162279.33, 487110.25); (2024-04, 162533.64, 649643.89); (2024-05, 160701.37, 810345.26); (2024-06, 158524.50, 968869.76); (2024-07, 98338.95, 1067208.71); (2024-08, 99364.19, 1166572.90); (2024-09, 99651.15, 1266224.05); (2024-10, 159760.93, 1425984.98); (2024-11, 159957.53, 1585942.51); (2024-12, 162281.69, 1748224.20)

- **PASS** · repeats [7] (1/10)
  - SQL: `WITH monthly_rev AS ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS month_revenue FROM sales GROUP BY month ORDER BY month ) SELECT month, SUM(month_revenue) OVER (ORDER BY month ROWS UNBOUNDED PRECEDING) AS cumulative_revenue FROM monthly_rev ORDER BY month;`
  - Result: (2024-01, 163081.67); (2024-02, 324830.92); (2024-03, 487110.25); (2024-04, 649643.89); (2024-05, 810345.26); (2024-06, 968869.76); (2024-07, 1067208.71); (2024-08, 1166572.90); (2024-09, 1266224.05); (2024-10, 1425984.98); (2024-11, 1585942.51); (2024-12, 1748224.20)

- **PASS** · repeats [8,10] (2/10)
  - SQL: `WITH monthly AS ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS month_rev FROM sales GROUP BY month ) SELECT month, SUM(month_rev) OVER (ORDER BY month ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_revenue FROM monthly ORDER BY month;`
  - Result: (2024-01, 163081.67); (2024-02, 324830.92); (2024-03, 487110.25); (2024-04, 649643.89); (2024-05, 810345.26); (2024-06, 968869.76); (2024-07, 1067208.71); (2024-08, 1166572.90); (2024-09, 1266224.05); (2024-10, 1425984.98); (2024-11, 1585942.51); (2024-12, 1748224.20)

- **PASS** · repeats [9] (1/10)
  - SQL: `WITH monthly AS ( SELECT substr(sale_date,1,7) AS month, revenue FROM sales WHERE substr(sale_date,1,4) = '2024' ) SELECT month, SUM(revenue) AS month_revenue, SUM(SUM(revenue)) OVER (ORDER BY month ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_revenue FROM monthly GROUP BY month ORDER BY month;`
  - Result: (2024-01, 163081.67, 163081.67); (2024-02, 161749.25, 324830.92); (2024-03, 162279.33, 487110.25); (2024-04, 162533.64, 649643.89); (2024-05, 160701.37, 810345.26); (2024-06, 158524.50, 968869.76); (2024-07, 98338.95, 1067208.71); (2024-08, 99364.19, 1166572.90); (2024-09, 99651.15, 1266224.05); (2024-10, 159760.93, 1425984.98); (2024-11, 159957.53, 1585942.51); (2024-12, 162281.69, 1748224.20)

#### qwen3-coder — 10/10 pass

- **PASS** · repeats [1,6] (2/10)
  - SQL: `WITH MonthlyRevenue AS ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS monthly_revenue FROM sales GROUP BY month ORDER BY month ) SELECT month, SUM(monthly_revenue) OVER (ORDER BY month) AS cumulative_revenue FROM MonthlyRevenue ORDER BY month`
  - Result: (2024-01, 163081.67); (2024-02, 324830.92); (2024-03, 487110.25); (2024-04, 649643.89); (2024-05, 810345.26); (2024-06, 968869.76); (2024-07, 1067208.71); (2024-08, 1166572.90); (2024-09, 1266224.05); (2024-10, 1425984.98); (2024-11, 1585942.51); (2024-12, 1748224.20)

- **PASS** · repeats [2] (1/10)
  - SQL: `WITH monthly_revenue AS ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS monthly_revenue FROM sales GROUP BY month ) SELECT month, SUM(monthly_revenue) OVER (ORDER BY month) AS cumulative_revenue FROM monthly_revenue ORDER BY month`
  - Result: (2024-01, 163081.67); (2024-02, 324830.92); (2024-03, 487110.25); (2024-04, 649643.89); (2024-05, 810345.26); (2024-06, 968869.76); (2024-07, 1067208.71); (2024-08, 1166572.90); (2024-09, 1266224.05); (2024-10, 1425984.98); (2024-11, 1585942.51); (2024-12, 1748224.20)

- **PASS** · repeats [3] (1/10)
  - SQL: `WITH monthly_revenue AS ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS monthly_revenue FROM sales GROUP BY strftime('%Y-%m', sale_date) ) SELECT month, SUM(monthly_revenue) OVER (ORDER BY month) AS cumulative_revenue FROM monthly_revenue ORDER BY month`
  - Result: (2024-01, 163081.67); (2024-02, 324830.92); (2024-03, 487110.25); (2024-04, 649643.89); (2024-05, 810345.26); (2024-06, 968869.76); (2024-07, 1067208.71); (2024-08, 1166572.90); (2024-09, 1266224.05); (2024-10, 1425984.98); (2024-11, 1585942.51); (2024-12, 1748224.20)

- **PASS** · repeats [4] (1/10)
  - SQL: `WITH monthly_revenue AS ( SELECT STRFTIME('%Y-%m', sale_date) AS month, SUM(revenue) AS revenue FROM sales GROUP BY month ) SELECT month, SUM(revenue) OVER (ORDER BY month) AS cumulative_revenue FROM monthly_revenue ORDER BY month`
  - Result: (2024-01, 163081.67); (2024-02, 324830.92); (2024-03, 487110.25); (2024-04, 649643.89); (2024-05, 810345.26); (2024-06, 968869.76); (2024-07, 1067208.71); (2024-08, 1166572.90); (2024-09, 1266224.05); (2024-10, 1425984.98); (2024-11, 1585942.51); (2024-12, 1748224.20)

- **PASS** · repeats [5] (1/10)
  - SQL: `WITH monthly_revenue AS ( SELECT strftime('%Y-%m', sale_date) as month, SUM(revenue) as monthly_revenue FROM sales GROUP BY strftime('%Y-%m', sale_date) ) SELECT month, SUM(monthly_revenue) OVER (ORDER BY month) as cumulative_revenue FROM monthly_revenue ORDER BY month`
  - Result: (2024-01, 163081.67); (2024-02, 324830.92); (2024-03, 487110.25); (2024-04, 649643.89); (2024-05, 810345.26); (2024-06, 968869.76); (2024-07, 1067208.71); (2024-08, 1166572.90); (2024-09, 1266224.05); (2024-10, 1425984.98); (2024-11, 1585942.51); (2024-12, 1748224.20)

- **PASS** · repeats [7,10] (2/10)
  - SQL: `WITH monthly_revenue AS ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS monthly_revenue FROM sales GROUP BY month ORDER BY month ) SELECT month, SUM(monthly_revenue) OVER (ORDER BY month) AS cumulative_revenue FROM monthly_revenue ORDER BY month`
  - Result: (2024-01, 163081.67); (2024-02, 324830.92); (2024-03, 487110.25); (2024-04, 649643.89); (2024-05, 810345.26); (2024-06, 968869.76); (2024-07, 1067208.71); (2024-08, 1166572.90); (2024-09, 1266224.05); (2024-10, 1425984.98); (2024-11, 1585942.51); (2024-12, 1748224.20)

- **PASS** · repeats [8] (1/10)
  - SQL: `WITH monthly_revenue AS ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS monthly_revenue FROM sales GROUP BY month ), running_totals AS ( SELECT month, SUM(monthly_revenue) OVER (ORDER BY month) AS cumulative_revenue FROM monthly_revenue ) SELECT * FROM running_totals ORDER BY month`
  - Result: (2024-01, 163081.67); (2024-02, 324830.92); (2024-03, 487110.25); (2024-04, 649643.89); (2024-05, 810345.26); (2024-06, 968869.76); (2024-07, 1067208.71); (2024-08, 1166572.90); (2024-09, 1266224.05); (2024-10, 1425984.98); (2024-11, 1585942.51); (2024-12, 1748224.20)

- **PASS** · repeats [9] (1/10)
  - SQL: `WITH monthly_revenue AS ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS monthly_total FROM sales GROUP BY strftime('%Y-%m', sale_date) ) SELECT month, SUM(monthly_total) OVER (ORDER BY month) AS cumulative_revenue FROM monthly_revenue ORDER BY month`
  - Result: (2024-01, 163081.67); (2024-02, 324830.92); (2024-03, 487110.25); (2024-04, 649643.89); (2024-05, 810345.26); (2024-06, 968869.76); (2024-07, 1067208.71); (2024-08, 1166572.90); (2024-09, 1266224.05); (2024-10, 1425984.98); (2024-11, 1585942.51); (2024-12, 1748224.20)

### L5a_mom_growth  (Level 5)
**Question:** What was the month-over-month revenue growth RATE (as a percentage) for each month? The first month has no prior month.
**Expected (ground truth):** 2024-01:None, 2024-02:-0.82, 2024-03:0.33, 2024-04:0.16, 2024-05:-1.13, 2024-06:-1.35, 2024-07:-37.97, 2024-08:1.04, 2024-09:0.29, 2024-10:60.32, 2024-11:0.12, 2024-12:1.45

#### ministral-8b — 8/10 pass

- **PASS** · repeats [1] (1/10) · tool-errors=3
  - SQL: `WITH monthly_sales AS ( SELECT STRFTIME('%Y-%m', sale_date) AS month, SUM(revenue) AS total_revenue FROM sales GROUP BY STRFTIME('%Y-%m', sale_date) ), monthly_sales_with_lag AS ( SELECT month, total_revenue, LAG(total_revenue) OVER (ORDER BY month) AS previous_month_revenue FROM monthly_sales ) SELECT month, total_revenue, previous_month_revenue, CASE WHEN previous_month_revenue IS NULL THEN NULL ELSE ROUND(((total_revenue - previous_month_revenue) / previous_month_revenue) * 100, 2) END AS month_over_month_growth_pct FROM monthly_sales_with_lag ORDER BY month;`
  - Result: (2024-01, 163081.67, None, None); (2024-02, 161749.25, 163081.67, -0.82); (2024-03, 162279.33, 161749.25, 0.33); (2024-04, 162533.64, 162279.33, 0.16); (2024-05, 160701.37, 162533.64, -1.13); (2024-06, 158524.50, 160701.37, -1.35); (2024-07, 98338.95, 158524.50, -37.97); (2024-08, 99364.19, 98338.95, 1.04); (2024-09, 99651.15, 99364.19, 0.29); (2024-10, 159760.93, 99651.15, 60.32); (2024-11, 159957.53, 159760.93, 0.12); (2024-12, 162281.69, 159957.53, 1.45)

- **PASS** · repeats [2] (1/10) · tool-errors=4
  - SQL: `WITH monthly_revenue AS ( SELECT STRFTIME('%m', sale_date) AS month_str, STRFTIME('%Y', sale_date) AS year, SUM(revenue) AS total_revenue FROM sales GROUP BY STRFTIME('%m', sale_date), STRFTIME('%Y', sale_date) ), monthly_growth AS ( SELECT month_str, year, total_revenue AS current_month_revenue, LAG(total_revenue, 1) OVER (ORDER BY year, month_str) AS previous_month_revenue, CASE WHEN LAG(total_revenue, 1) OVER (ORDER BY year, month_str) IS NULL THEN NULL ELSE ROUND( ((total_revenue - LAG(total_revenue, 1) OVER (ORDER BY year, month_str)) / LAG(total_revenue, 1) OVER (ORDER BY year, month_str)) * 100, 2 ) END AS growth_rate_percentage FROM monthly_revenue ) SELECT year, month_str AS month, current_month_revenue, growth_rate_percentage FROM monthly_growth ORDER BY year, month_str;`
  - Result: (2024, 01, 163081.67, None); (2024, 02, 161749.25, -0.82); (2024, 03, 162279.33, 0.33); (2024, 04, 162533.64, 0.16); (2024, 05, 160701.37, -1.13); (2024, 06, 158524.50, -1.35); (2024, 07, 98338.95, -37.97); (2024, 08, 99364.19, 1.04); (2024, 09, 99651.15, 0.29); (2024, 10, 159760.93, 60.32); (2024, 11, 159957.53, 0.12); (2024, 12, 162281.69, 1.45)

- **PASS** · repeats [3] (1/10) · tool-errors=5
  - SQL: `WITH monthly_revenue AS ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS total_revenue FROM sales GROUP BY strftime('%Y-%m', sale_date) ), ranked_months AS ( SELECT month, total_revenue, ROW_NUMBER() OVER (ORDER BY strftime('%Y-%m', month)) AS rn FROM monthly_revenue ), monthly_growth AS ( SELECT rm1.month AS current_month, rm1.total_revenue AS current_month_revenue, rm2.total_revenue AS previous_month_revenue, CASE WHEN rm2.total_revenue = 0 THEN NULL ELSE ROUND(((rm1.total_revenue - rm2.total_revenue) / rm2.total_revenue) * 100, 2) END AS growth_rate_percentage FROM ranked_months rm1 LEFT JOIN ranked_months rm2 ON rm1.rn = rm2.rn + 1 ) SELECT current_month, current_month_revenue, previous_month_revenue, growth_rate_percentage FROM monthly_growth ORDER BY strftime('%Y-%m', current_month);`
  - Result: (2024-01, 163081.67, None, None); (2024-02, 161749.25, 163081.67, -0.82); (2024-03, 162279.33, 161749.25, 0.33); (2024-04, 162533.64, 162279.33, 0.16); (2024-05, 160701.37, 162533.64, -1.13); (2024-06, 158524.50, 160701.37, -1.35); (2024-07, 98338.95, 158524.50, -37.97); (2024-08, 99364.19, 98338.95, 1.04); (2024-09, 99651.15, 99364.19, 0.29); (2024-10, 159760.93, 99651.15, 60.32); (2024-11, 159957.53, 159760.93, 0.12); (2024-12, 162281.69, 159957.53, 1.45)

- **PASS** · repeats [4] (1/10) · tool-errors=3
  - SQL: `WITH monthly_sales AS ( SELECT DATE(sale_date) AS sale_date, SUM(revenue) AS total_revenue FROM sales GROUP BY DATE(sale_date) ), monthly_growth AS ( SELECT sale_date, total_revenue, LAG(total_revenue) OVER (ORDER BY sale_date) AS previous_month_revenue FROM monthly_sales ) SELECT STRFTIME('%m-%Y', sale_date) AS month_year, total_revenue, previous_month_revenue, CASE WHEN previous_month_revenue IS NULL THEN NULL ELSE ROUND(((total_revenue - previous_month_revenue) / previous_month_revenue) * 100, 2) END AS month_over_month_growth_pct FROM monthly_growth ORDER BY sale_date;`
  - Result: (01-2024, 163081.67, None, None); (02-2024, 161749.25, 163081.67, -0.82); (03-2024, 162279.33, 161749.25, 0.33); (04-2024, 162533.64, 162279.33, 0.16); (05-2024, 160701.37, 162533.64, -1.13); (06-2024, 158524.50, 160701.37, -1.35); (07-2024, 98338.95, 158524.50, -37.97); (08-2024, 99364.19, 98338.95, 1.04); (09-2024, 99651.15, 99364.19, 0.29); (10-2024, 159760.93, 99651.15, 60.32); (11-2024, 159957.53, 159760.93, 0.12); (12-2024, 162281.69, 159957.53, 1.45)

- **FAIL** · repeats [5] (1/10) · tool-errors=2
  - SQL: `WITH monthly_revenue AS ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS total_revenue FROM sales GROUP BY strftime('%Y-%m', sale_date) ), ranked_months AS ( SELECT month, total_revenue, ROW_NUMBER() OVER (ORDER BY strftime('%s', month)) AS row_num FROM monthly_revenue ), monthly_growth AS ( SELECT r1.month AS current_month, r1.total_revenue AS current_month_revenue, r2.total_revenue AS previous_month_revenue, CASE WHEN r2.total_revenue = 0 THEN NULL ELSE ROUND(((r1.total_revenue - r2.total_revenue) / r2.total_revenue) * 100, 2) END AS growth_rate_percentage FROM ranked_months r1 LEFT JOIN ranked_months r2 ON r2.row_num = r1.row_num - 1 WHERE r1.row_num > 1 ) SELECT * FROM monthly_growth;`
  - Result: (2024-02, 161749.25, 163081.67, -0.82); (2024-03, 162279.33, 161749.25, 0.33); (2024-04, 162533.64, 162279.33, 0.16); (2024-05, 160701.37, 162533.64, -1.13); (2024-06, 158524.50, 160701.37, -1.35); (2024-07, 98338.95, 158524.50, -37.97); (2024-08, 99364.19, 98338.95, 1.04); (2024-09, 99651.15, 99364.19, 0.29); (2024-10, 159760.93, 99651.15, 60.32); (2024-11, 159957.53, 159760.93, 0.12); (2024-12, 162281.69, 159957.53, 1.45)
  - WHY: wrong row count 11 vs 12 (mishandled first-month null / grouping)

- **PASS** · repeats [6] (1/10) · tool-errors=2
  - SQL: `WITH ranked_months AS ( SELECT STRFTIME('%Y-%m', sale_date) AS month, SUM(revenue) AS total_revenue, ROW_NUMBER() OVER (ORDER BY STRFTIME('%s', sale_date)) AS rn FROM sales GROUP BY STRFTIME('%Y-%m', sale_date) ), monthly_growth AS ( SELECT r1.month AS current_month, r1.total_revenue AS current_month_revenue, r2.total_revenue AS previous_month_revenue, CASE WHEN r2.total_revenue = 0 THEN NULL ELSE ROUND(((r1.total_revenue - r2.total_revenue) / r2.total_revenue) * 100, 2) END AS growth_rate_percentage FROM ranked_months r1 LEFT JOIN ranked_months r2 ON r1.rn = r2.rn + 1 ) SELECT * FROM monthly_growth;`
  - Result: (2024-01, 163081.67, None, None); (2024-02, 161749.25, 163081.67, -0.82); (2024-03, 162279.33, 161749.25, 0.33); (2024-04, 162533.64, 162279.33, 0.16); (2024-05, 160701.37, 162533.64, -1.13); (2024-06, 158524.50, 160701.37, -1.35); (2024-07, 98338.95, 158524.50, -37.97); (2024-08, 99364.19, 98338.95, 1.04); (2024-09, 99651.15, 99364.19, 0.29); (2024-10, 159760.93, 99651.15, 60.32); (2024-11, 159957.53, 159760.93, 0.12); (2024-12, 162281.69, 159957.53, 1.45)

- **PASS** · repeats [7] (1/10) · tool-errors=6
  - SQL: `WITH monthly_revenue AS ( SELECT strftime('%Y', sale_date) AS year, strftime('%m', sale_date) AS month, SUM(revenue) AS total_revenue FROM sales GROUP BY strftime('%Y', sale_date), strftime('%m', sale_date) ), monthly_growth AS ( SELECT m1.year, m1.month, m1.total_revenue AS current_month_revenue, m2.total_revenue AS previous_month_revenue, CASE WHEN m2.total_revenue IS NULL THEN NULL -- No prior month for the first month ELSE ROUND(((m1.total_revenue - m2.total_revenue) / m2.total_revenue) * 100, 2) END AS growth_rate_percentage FROM monthly_revenue m1 LEFT JOIN monthly_revenue m2 ON m1.year = m2.year AND CAST(m1.month AS INTEGER) = CAST(m2.month AS INTEGER) + 1 ) SELECT * FROM monthly_growth ORDER BY year, month;`
  - Result: (2024, 01, 163081.67, None, None); (2024, 02, 161749.25, 163081.67, -0.82); (2024, 03, 162279.33, 161749.25, 0.33); (2024, 04, 162533.64, 162279.33, 0.16); (2024, 05, 160701.37, 162533.64, -1.13); (2024, 06, 158524.50, 160701.37, -1.35); (2024, 07, 98338.95, 158524.50, -37.97); (2024, 08, 99364.19, 98338.95, 1.04); (2024, 09, 99651.15, 99364.19, 0.29); (2024, 10, 159760.93, 99651.15, 60.32); (2024, 11, 159957.53, 159760.93, 0.12); (2024, 12, 162281.69, 159957.53, 1.45)

- **FAIL** · repeats [8] (1/10) · tool-errors=3
  - SQL: `WITH ranked_months AS ( SELECT strftime('%Y-%m', sale_date) AS month_year, SUM(revenue) AS total_revenue, ROW_NUMBER() OVER (ORDER BY strftime('%Y-%m', sale_date)) AS rn FROM sales GROUP BY strftime('%Y-%m', sale_date) ), monthly_revenue AS ( SELECT r1.month_year AS current_month, r1.total_revenue AS current_month_revenue, r2.total_revenue AS previous_month_revenue FROM ranked_months r1 LEFT JOIN ranked_months r2 ON r1.rn = r2.rn - 1 ) SELECT current_month, current_month_revenue, previous_month_revenue, CASE WHEN previous_month_revenue IS NULL THEN NULL ELSE ROUND(((current_month_revenue - previous_month_revenue) / previous_month_revenue) * 100, 2) END AS growth_rate_percentage FROM monthly_revenue ORDER BY current_month;`
  - Result: (2024-01, 163081.67, 161749.25, 0.82); (2024-02, 161749.25, 162279.33, -0.33); (2024-03, 162279.33, 162533.64, -0.16); (2024-04, 162533.64, 160701.37, 1.14); (2024-05, 160701.37, 158524.50, 1.37); (2024-06, 158524.50, 98338.95, 61.20); (2024-07, 98338.95, 99364.19, -1.03); (2024-08, 99364.19, 99651.15, -0.29); (2024-09, 99651.15, 159760.93, -37.62); (2024-10, 159760.93, 159957.53, -0.12); (2024-11, 159957.53, 162281.69, -1.43); (2024-12, 162281.69, None, None)
  - WHY: growth values wrong (LAG / rate / null handling)

- **PASS** · repeats [9] (1/10) · tool-errors=4
  - SQL: `WITH monthly_revenue AS ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS total_revenue FROM sales GROUP BY strftime('%Y-%m', sale_date) ORDER BY month ), ranked_months AS ( SELECT month, total_revenue, ROW_NUMBER() OVER (ORDER BY month) AS row_num FROM monthly_revenue ) SELECT r1.month AS current_month, r1.total_revenue AS current_month_revenue, r2.total_revenue AS previous_month_revenue, CASE WHEN r2.total_revenue = 0 THEN NULL -- No prior month for the first month ELSE ROUND(((r1.total_revenue - r2.total_revenue) / r2.total_revenue) * 100, 2) END AS month_over_month_growth_rate_pct FROM ranked_months r1 LEFT JOIN ranked_months r2 ON r1.row_num = r2.row_num + 1 ORDER BY r1.row_num;`
  - Result: (2024-01, 163081.67, None, None); (2024-02, 161749.25, 163081.67, -0.82); (2024-03, 162279.33, 161749.25, 0.33); (2024-04, 162533.64, 162279.33, 0.16); (2024-05, 160701.37, 162533.64, -1.13); (2024-06, 158524.50, 160701.37, -1.35); (2024-07, 98338.95, 158524.50, -37.97); (2024-08, 99364.19, 98338.95, 1.04); (2024-09, 99651.15, 99364.19, 0.29); (2024-10, 159760.93, 99651.15, 60.32); (2024-11, 159957.53, 159760.93, 0.12); (2024-12, 162281.69, 159957.53, 1.45)

- **PASS** · repeats [10] (1/10) · tool-errors=1
  - SQL: `WITH monthly_revenue AS ( SELECT STRFTIME('%Y-%m', sale_date) AS month, SUM(revenue) AS total_revenue FROM sales GROUP BY STRFTIME('%Y-%m', sale_date) ), ranked_months AS ( SELECT month, total_revenue, ROW_NUMBER() OVER (ORDER BY STRFTIME('%s', month)) AS month_rank FROM monthly_revenue ), monthly_growth AS ( SELECT r1.month AS current_month, r1.total_revenue AS current_month_revenue, r2.total_revenue AS previous_month_revenue, CASE WHEN r2.total_revenue IS NULL THEN NULL ELSE ROUND(((r1.total_revenue - r2.total_revenue) / r2.total_revenue) * 100, 2) END AS growth_rate_percentage FROM ranked_months r1 LEFT JOIN ranked_months r2 ON r1.month_rank = r2.month_rank + 1 ) SELECT current_month, current_month_revenue, previous_month_revenue, growth_rate_percentage FROM monthly_growth ORDER BY STRFTIME('%s', current_month);`
  - Result: (2024-01, 163081.67, None, None); (2024-02, 161749.25, 163081.67, -0.82); (2024-03, 162279.33, 161749.25, 0.33); (2024-04, 162533.64, 162279.33, 0.16); (2024-05, 160701.37, 162533.64, -1.13); (2024-06, 158524.50, 160701.37, -1.35); (2024-07, 98338.95, 158524.50, -37.97); (2024-08, 99364.19, 98338.95, 1.04); (2024-09, 99651.15, 99364.19, 0.29); (2024-10, 159760.93, 99651.15, 60.32); (2024-11, 159957.53, 159760.93, 0.12); (2024-12, 162281.69, 159957.53, 1.45)

#### gpt-oss-20b — 9/10 pass

- **PASS** · repeats [1] (1/10)
  - SQL: `WITH monthly_rev AS ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS revenue FROM sales GROUP BY month ) SELECT month, ROUND((revenue - LAG(revenue) OVER (ORDER BY month)) / LAG(revenue) OVER (ORDER BY month) * 100, 2) AS growth_rate FROM monthly_rev ORDER BY month;`
  - Result: (2024-01, None); (2024-02, -0.82); (2024-03, 0.33); (2024-04, 0.16); (2024-05, -1.13); (2024-06, -1.35); (2024-07, -37.97); (2024-08, 1.04); (2024-09, 0.29); (2024-10, 60.32); (2024-11, 0.12); (2024-12, 1.45)

- **PASS** · repeats [2,8] (2/10)
  - SQL: `WITH monthly_revenue AS ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS revenue FROM sales GROUP BY month ), ranked AS ( SELECT month, revenue, LAG(revenue) OVER (ORDER BY month) AS prev_revenue FROM monthly_revenue ) SELECT month, ROUND((revenue - prev_revenue) / NULLIF(prev_revenue, 0) * 100, 2) AS growth_rate FROM ranked ORDER BY month;`
  - Result: (2024-01, None); (2024-02, -0.82); (2024-03, 0.33); (2024-04, 0.16); (2024-05, -1.13); (2024-06, -1.35); (2024-07, -37.97); (2024-08, 1.04); (2024-09, 0.29); (2024-10, 60.32); (2024-11, 0.12); (2024-12, 1.45)

- **PASS** · repeats [3] (1/10)
  - SQL: `WITH monthly_rev AS ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS revenue FROM sales GROUP BY month ), monthly_growth AS ( SELECT month, revenue, LAG(revenue) OVER (ORDER BY month) AS prev_revenue FROM monthly_rev ) SELECT month, revenue, prev_revenue, CASE WHEN prev_revenue IS NULL THEN NULL ELSE (revenue - prev_revenue) / prev_revenue * 100 END AS growth_rate_pct FROM monthly_growth ORDER BY month;`
  - Result: (2024-01, 163081.67, None, None); (2024-02, 161749.25, 163081.67, -0.82); (2024-03, 162279.33, 161749.25, 0.33); (2024-04, 162533.64, 162279.33, 0.16); (2024-05, 160701.37, 162533.64, -1.13); (2024-06, 158524.50, 160701.37, -1.35); (2024-07, 98338.95, 158524.50, -37.97); (2024-08, 99364.19, 98338.95, 1.04); (2024-09, 99651.15, 99364.19, 0.29); (2024-10, 159760.93, 99651.15, 60.32); (2024-11, 159957.53, 159760.93, 0.12); (2024-12, 162281.69, 159957.53, 1.45)

- **PASS** · repeats [4] (1/10)
  - SQL: `SELECT month, ROUND((revenue - LAG(revenue) OVER (ORDER BY month)) / NULLIF(LAG(revenue) OVER (ORDER BY month), 0) * 100, 2) AS growth_rate FROM ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS revenue FROM sales GROUP BY month ) sub ORDER BY month;`
  - Result: (2024-01, None); (2024-02, -0.82); (2024-03, 0.33); (2024-04, 0.16); (2024-05, -1.13); (2024-06, -1.35); (2024-07, -37.97); (2024-08, 1.04); (2024-09, 0.29); (2024-10, 60.32); (2024-11, 0.12); (2024-12, 1.45)

- **PASS** · repeats [5] (1/10)
  - SQL: `WITH monthly_revenue AS ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS revenue FROM sales GROUP BY month ), ranked AS ( SELECT month, revenue, LAG(revenue) OVER (ORDER BY month) AS prev_revenue FROM monthly_revenue ) SELECT month, CASE WHEN prev_revenue IS NULL THEN NULL ELSE ROUND((revenue - prev_revenue) / prev_revenue * 100, 2) END AS growth_rate_percent FROM ranked ORDER BY month;`
  - Result: (2024-01, None); (2024-02, -0.82); (2024-03, 0.33); (2024-04, 0.16); (2024-05, -1.13); (2024-06, -1.35); (2024-07, -37.97); (2024-08, 1.04); (2024-09, 0.29); (2024-10, 60.32); (2024-11, 0.12); (2024-12, 1.45)

- **FAIL** · repeats [6] (1/10)
  - SQL: `WITH monthly_rev AS ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS revenue FROM sales GROUP BY month ORDER BY month ), ranked AS ( SELECT month, revenue, LAG(revenue) OVER (ORDER BY month) AS prev_rev FROM monthly_rev ) SELECT month, ROUND((revenue - prev_rev) / prev_rev * 100, 2) AS growth_rate FROM ranked WHERE prev_rev IS NOT NULL ORDER BY month;`
  - Result: (2024-02, -0.82); (2024-03, 0.33); (2024-04, 0.16); (2024-05, -1.13); (2024-06, -1.35); (2024-07, -37.97); (2024-08, 1.04); (2024-09, 0.29); (2024-10, 60.32); (2024-11, 0.12); (2024-12, 1.45)
  - WHY: wrong row count 11 vs 12 (mishandled first-month null / grouping)

- **PASS** · repeats [7] (1/10)
  - SQL: `WITH monthly AS ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS revenue FROM sales GROUP BY month ) SELECT month, revenue, lag(revenue) OVER (ORDER BY month) AS prev_revenue, CASE WHEN lag(revenue) OVER (ORDER BY month) IS NULL THEN NULL ELSE (revenue - lag(revenue) OVER (ORDER BY month)) / lag(revenue) OVER (ORDER BY month) * 100 END AS growth_rate FROM monthly ORDER BY month;`
  - Result: (2024-01, 163081.67, None, None); (2024-02, 161749.25, 163081.67, -0.82); (2024-03, 162279.33, 161749.25, 0.33); (2024-04, 162533.64, 162279.33, 0.16); (2024-05, 160701.37, 162533.64, -1.13); (2024-06, 158524.50, 160701.37, -1.35); (2024-07, 98338.95, 158524.50, -37.97); (2024-08, 99364.19, 98338.95, 1.04); (2024-09, 99651.15, 99364.19, 0.29); (2024-10, 159760.93, 99651.15, 60.32); (2024-11, 159957.53, 159760.93, 0.12); (2024-12, 162281.69, 159957.53, 1.45)

- **PASS** · repeats [9] (1/10)
  - SQL: `WITH monthly_revenue AS ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS revenue FROM sales GROUP BY month ), monthly_growth AS ( SELECT month, revenue, LAG(revenue) OVER (ORDER BY month) AS prev_revenue FROM monthly_revenue ) SELECT month, CASE WHEN prev_revenue IS NULL THEN NULL ELSE ROUND((revenue - prev_revenue) / prev_revenue * 100, 2) END AS growth_rate FROM monthly_growth ORDER BY month;`
  - Result: (2024-01, None); (2024-02, -0.82); (2024-03, 0.33); (2024-04, 0.16); (2024-05, -1.13); (2024-06, -1.35); (2024-07, -37.97); (2024-08, 1.04); (2024-09, 0.29); (2024-10, 60.32); (2024-11, 0.12); (2024-12, 1.45)

- **PASS** · repeats [10] (1/10)
  - SQL: `WITH monthly_rev AS ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS rev FROM sales GROUP BY month ), growth AS ( SELECT month, rev, (rev - LAG(rev) OVER (ORDER BY month)) / NULLIF(LAG(rev) OVER (ORDER BY month), 0) * 100 AS growth_rate FROM monthly_rev ) SELECT month, growth_rate FROM growth ORDER BY month;`
  - Result: (2024-01, None); (2024-02, -0.82); (2024-03, 0.33); (2024-04, 0.16); (2024-05, -1.13); (2024-06, -1.35); (2024-07, -37.97); (2024-08, 1.04); (2024-09, 0.29); (2024-10, 60.32); (2024-11, 0.12); (2024-12, 1.45)

#### ollama-cloud — 10/10 pass

- **PASS** · repeats [1] (1/10)
  - SQL: `SELECT month, revenue, LAG(revenue) OVER (ORDER BY month) AS prev_rev, CASE WHEN LAG(revenue) OVER (ORDER BY month) IS NULL THEN NULL ELSE (revenue - LAG(revenue) OVER (ORDER BY month)) * 100.0 / LAG(revenue) OVER (ORDER BY month) END AS growth_rate FROM ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS revenue FROM sales GROUP BY month ) ORDER BY month;`
  - Result: (2024-01, 163081.67, None, None); (2024-02, 161749.25, 163081.67, -0.82); (2024-03, 162279.33, 161749.25, 0.33); (2024-04, 162533.64, 162279.33, 0.16); (2024-05, 160701.37, 162533.64, -1.13); (2024-06, 158524.50, 160701.37, -1.35); (2024-07, 98338.95, 158524.50, -37.97); (2024-08, 99364.19, 98338.95, 1.04); (2024-09, 99651.15, 99364.19, 0.29); (2024-10, 159760.93, 99651.15, 60.32); (2024-11, 159957.53, 159760.93, 0.12); (2024-12, 162281.69, 159957.53, 1.45)

- **PASS** · repeats [2] (1/10)
  - SQL: `WITH monthly AS ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS revenue FROM sales GROUP BY month ) SELECT month, revenue, LAG(revenue) OVER (ORDER BY month) AS prev_rev, CASE WHEN LAG(revenue) OVER (ORDER BY month) IS NULL THEN NULL ELSE ROUND(((revenue - LAG(revenue) OVER (ORDER BY month)) * 100.0) / LAG(revenue) OVER (ORDER BY month), 2) END AS growth_rate_percent FROM monthly ORDER BY month;`
  - Result: (2024-01, 163081.67, None, None); (2024-02, 161749.25, 163081.67, -0.82); (2024-03, 162279.33, 161749.25, 0.33); (2024-04, 162533.64, 162279.33, 0.16); (2024-05, 160701.37, 162533.64, -1.13); (2024-06, 158524.50, 160701.37, -1.35); (2024-07, 98338.95, 158524.50, -37.97); (2024-08, 99364.19, 98338.95, 1.04); (2024-09, 99651.15, 99364.19, 0.29); (2024-10, 159760.93, 99651.15, 60.32); (2024-11, 159957.53, 159760.93, 0.12); (2024-12, 162281.69, 159957.53, 1.45)

- **PASS** · repeats [3] (1/10)
  - SQL: `WITH monthly_rev AS ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS revenue FROM sales GROUP BY month ORDER BY month ) SELECT month, revenue, LAG(revenue) OVER (ORDER BY month) AS prev_revenue, CASE WHEN LAG(revenue) OVER (ORDER BY month) IS NULL THEN NULL ELSE (revenue - LAG(revenue) OVER (ORDER BY month)) * 100.0 / LAG(revenue) OVER (ORDER BY month) END AS mom_growth_pct FROM monthly_rev ORDER BY month;`
  - Result: (2024-01, 163081.67, None, None); (2024-02, 161749.25, 163081.67, -0.82); (2024-03, 162279.33, 161749.25, 0.33); (2024-04, 162533.64, 162279.33, 0.16); (2024-05, 160701.37, 162533.64, -1.13); (2024-06, 158524.50, 160701.37, -1.35); (2024-07, 98338.95, 158524.50, -37.97); (2024-08, 99364.19, 98338.95, 1.04); (2024-09, 99651.15, 99364.19, 0.29); (2024-10, 159760.93, 99651.15, 60.32); (2024-11, 159957.53, 159760.93, 0.12); (2024-12, 162281.69, 159957.53, 1.45)

- **PASS** · repeats [4] (1/10)
  - SQL: `SELECT month, revenue, LAG(revenue) OVER (ORDER BY month) AS prior_revenue, CASE WHEN LAG(revenue) OVER (ORDER BY month) IS NULL THEN NULL ELSE (revenue - LAG(revenue) OVER (ORDER BY month)) * 100.0 / LAG(revenue) OVER (ORDER BY month) END AS mom_growth_rate FROM ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS revenue FROM sales GROUP BY month ) ORDER BY month;`
  - Result: (2024-01, 163081.67, None, None); (2024-02, 161749.25, 163081.67, -0.82); (2024-03, 162279.33, 161749.25, 0.33); (2024-04, 162533.64, 162279.33, 0.16); (2024-05, 160701.37, 162533.64, -1.13); (2024-06, 158524.50, 160701.37, -1.35); (2024-07, 98338.95, 158524.50, -37.97); (2024-08, 99364.19, 98338.95, 1.04); (2024-09, 99651.15, 99364.19, 0.29); (2024-10, 159760.93, 99651.15, 60.32); (2024-11, 159957.53, 159760.93, 0.12); (2024-12, 162281.69, 159957.53, 1.45)

- **PASS** · repeats [5] (1/10)
  - SQL: `WITH monthly AS ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS revenue FROM sales GROUP BY month ) SELECT month, revenue, LAG(revenue) OVER (ORDER BY month) AS prev_rev, CASE WHEN LAG(revenue) OVER (ORDER BY month) IS NULL THEN NULL ELSE (revenue - LAG(revenue) OVER (ORDER BY month)) * 100.0 / LAG(revenue) OVER (ORDER BY month) END AS growth_rate FROM monthly ORDER BY month;`
  - Result: (2024-01, 163081.67, None, None); (2024-02, 161749.25, 163081.67, -0.82); (2024-03, 162279.33, 161749.25, 0.33); (2024-04, 162533.64, 162279.33, 0.16); (2024-05, 160701.37, 162533.64, -1.13); (2024-06, 158524.50, 160701.37, -1.35); (2024-07, 98338.95, 158524.50, -37.97); (2024-08, 99364.19, 98338.95, 1.04); (2024-09, 99651.15, 99364.19, 0.29); (2024-10, 159760.93, 99651.15, 60.32); (2024-11, 159957.53, 159760.93, 0.12); (2024-12, 162281.69, 159957.53, 1.45)

- **PASS** · repeats [6] (1/10)
  - SQL: `WITH monthly AS ( SELECT substr(sale_date,1,7) as month, SUM(revenue) as revenue FROM sales GROUP BY month ) SELECT month, revenue, (revenue - LAG(revenue) OVER (ORDER BY month)) / LAG(revenue) OVER (ORDER BY month) * 100.0 as mom_growth_rate FROM monthly ORDER BY month;`
  - Result: (2024-01, 163081.67, None); (2024-02, 161749.25, -0.82); (2024-03, 162279.33, 0.33); (2024-04, 162533.64, 0.16); (2024-05, 160701.37, -1.13); (2024-06, 158524.50, -1.35); (2024-07, 98338.95, -37.97); (2024-08, 99364.19, 1.04); (2024-09, 99651.15, 0.29); (2024-10, 159760.93, 60.32); (2024-11, 159957.53, 0.12); (2024-12, 162281.69, 1.45)

- **PASS** · repeats [7] (1/10)
  - SQL: `WITH monthly_rev AS ( SELECT substr(sale_date, 1, 7) AS month, SUM(revenue) AS revenue FROM sales GROUP BY month ) SELECT month, ROUND( (revenue - LAG(revenue) OVER (ORDER BY month)) * 100.0 / LAG(revenue) OVER (ORDER BY month), 2) AS growth_rate_percent FROM monthly_rev ORDER BY month;`
  - Result: (2024-01, None); (2024-02, -0.82); (2024-03, 0.33); (2024-04, 0.16); (2024-05, -1.13); (2024-06, -1.35); (2024-07, -37.97); (2024-08, 1.04); (2024-09, 0.29); (2024-10, 60.32); (2024-11, 0.12); (2024-12, 1.45)

- **PASS** · repeats [8] (1/10)
  - SQL: `WITH month_rev AS ( SELECT substr(sale_date, 1, 7) AS month, SUM(revenue) AS revenue FROM sales GROUP BY month ) SELECT month, revenue, CASE WHEN LAG(revenue) OVER (ORDER BY month) IS NULL THEN NULL ELSE (revenue - LAG(revenue) OVER (ORDER BY month)) / LAG(revenue) OVER (ORDER BY month) * 100.0 END AS mom_growth_pct FROM month_rev ORDER BY month;`
  - Result: (2024-01, 163081.67, None); (2024-02, 161749.25, -0.82); (2024-03, 162279.33, 0.33); (2024-04, 162533.64, 0.16); (2024-05, 160701.37, -1.13); (2024-06, 158524.50, -1.35); (2024-07, 98338.95, -37.97); (2024-08, 99364.19, 1.04); (2024-09, 99651.15, 0.29); (2024-10, 159760.93, 60.32); (2024-11, 159957.53, 0.12); (2024-12, 162281.69, 1.45)

- **PASS** · repeats [9] (1/10)
  - SQL: `WITH monthly_rev AS ( SELECT substr(sale_date,1,7) AS month, SUM(revenue) AS revenue FROM sales GROUP BY month ORDER BY month ) SELECT month, revenue, LAG(revenue) OVER (ORDER BY month) AS prev_revenue, CASE WHEN LAG(revenue) OVER (ORDER BY month) IS NULL THEN NULL ELSE ROUND(100.0 * (revenue - LAG(revenue) OVER (ORDER BY month)) / LAG(revenue) OVER (ORDER BY month), 2) END AS mom_growth_rate_percent FROM monthly_rev ORDER BY month;`
  - Result: (2024-01, 163081.67, None, None); (2024-02, 161749.25, 163081.67, -0.82); (2024-03, 162279.33, 161749.25, 0.33); (2024-04, 162533.64, 162279.33, 0.16); (2024-05, 160701.37, 162533.64, -1.13); (2024-06, 158524.50, 160701.37, -1.35); (2024-07, 98338.95, 158524.50, -37.97); (2024-08, 99364.19, 98338.95, 1.04); (2024-09, 99651.15, 99364.19, 0.29); (2024-10, 159760.93, 99651.15, 60.32); (2024-11, 159957.53, 159760.93, 0.12); (2024-12, 162281.69, 159957.53, 1.45)

- **PASS** · repeats [10] (1/10)
  - SQL: `WITH monthly AS ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS revenue FROM sales GROUP BY month ) SELECT month, CASE WHEN LAG(revenue) OVER (ORDER BY month) IS NULL THEN NULL ELSE ROUND( (revenue - LAG(revenue) OVER (ORDER BY month)) * 100.0 / LAG(revenue) OVER (ORDER BY month), 2) END AS growth_rate_percent FROM monthly ORDER BY month;`
  - Result: (2024-01, None); (2024-02, -0.82); (2024-03, 0.33); (2024-04, 0.16); (2024-05, -1.13); (2024-06, -1.35); (2024-07, -37.97); (2024-08, 1.04); (2024-09, 0.29); (2024-10, 60.32); (2024-11, 0.12); (2024-12, 1.45)

#### qwen3-coder — 10/10 pass

- **PASS** · repeats [1] (1/10)
  - SQL: `WITH monthly_revenue AS ( SELECT strftime('%Y-%m', sale_date) as month, SUM(revenue) as revenue FROM sales GROUP BY strftime('%Y-%m', sale_date) ), monthly_growth AS ( SELECT month, revenue, LAG(revenue, 1) OVER (ORDER BY month) as previous_month_revenue FROM monthly_revenue ) SELECT month, CASE WHEN previous_month_revenue IS NOT NULL AND previous_month_revenue != 0 THEN ROUND(((revenue - previous_month_revenue) / previous_month_revenue) * 100, 2) ELSE NULL END as revenue_growth_rate_percent FROM monthly_growth ORDER BY month`
  - Result: (2024-01, None); (2024-02, -0.82); (2024-03, 0.33); (2024-04, 0.16); (2024-05, -1.13); (2024-06, -1.35); (2024-07, -37.97); (2024-08, 1.04); (2024-09, 0.29); (2024-10, 60.32); (2024-11, 0.12); (2024-12, 1.45)

- **PASS** · repeats [2] (1/10)
  - SQL: `WITH monthly_revenue AS ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS total_revenue FROM sales GROUP BY strftime('%Y-%m', sale_date) ), revenue_with_lag AS ( SELECT month, total_revenue, LAG(total_revenue, 1) OVER (ORDER BY month) AS prev_month_revenue FROM monthly_revenue ) SELECT month, CASE WHEN prev_month_revenue IS NOT NULL AND prev_month_revenue != 0 THEN ((total_revenue - prev_month_revenue) / prev_month_revenue) * 100 ELSE NULL END AS revenue_growth_rate_percent FROM revenue_with_lag ORDER BY month`
  - Result: (2024-01, None); (2024-02, -0.82); (2024-03, 0.33); (2024-04, 0.16); (2024-05, -1.13); (2024-06, -1.35); (2024-07, -37.97); (2024-08, 1.04); (2024-09, 0.29); (2024-10, 60.32); (2024-11, 0.12); (2024-12, 1.45)

- **PASS** · repeats [3] (1/10)
  - SQL: `WITH monthly_revenue AS ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS total_revenue FROM sales GROUP BY strftime('%Y-%m', sale_date) ), revenue_growth AS ( SELECT month, total_revenue, LAG(total_revenue, 1) OVER (ORDER BY month) AS prev_month_revenue FROM monthly_revenue ) SELECT month, CASE WHEN prev_month_revenue IS NOT NULL AND prev_month_revenue != 0 THEN ((total_revenue - prev_month_revenue) / prev_month_revenue) * 100 ELSE NULL END AS revenue_growth_rate_percent FROM revenue_growth ORDER BY month;`
  - Result: (2024-01, None); (2024-02, -0.82); (2024-03, 0.33); (2024-04, 0.16); (2024-05, -1.13); (2024-06, -1.35); (2024-07, -37.97); (2024-08, 1.04); (2024-09, 0.29); (2024-10, 60.32); (2024-11, 0.12); (2024-12, 1.45)

- **PASS** · repeats [4] (1/10)
  - SQL: `WITH monthly_revenue AS ( SELECT strftime('%Y-%m', sale_date) as month, SUM(revenue) as total_revenue FROM sales GROUP BY strftime('%Y-%m', sale_date) ORDER BY month ), revenue_with_lag AS ( SELECT month, total_revenue, LAG(total_revenue, 1) OVER (ORDER BY month) as prev_month_revenue FROM monthly_revenue ) SELECT month, CASE WHEN prev_month_revenue IS NULL THEN NULL ELSE ROUND(((total_revenue - prev_month_revenue) / prev_month_revenue) * 100, 2) END as revenue_growth_rate_percent FROM revenue_with_lag ORDER BY month`
  - Result: (2024-01, None); (2024-02, -0.82); (2024-03, 0.33); (2024-04, 0.16); (2024-05, -1.13); (2024-06, -1.35); (2024-07, -37.97); (2024-08, 1.04); (2024-09, 0.29); (2024-10, 60.32); (2024-11, 0.12); (2024-12, 1.45)

- **PASS** · repeats [5] (1/10)
  - SQL: `WITH monthly_revenue AS ( SELECT strftime('%Y-%m', sale_date) as month, SUM(revenue) as total_revenue FROM sales GROUP BY strftime('%Y-%m', sale_date) ORDER BY month ), monthly_growth AS ( SELECT month, total_revenue, LAG(total_revenue, 1) OVER (ORDER BY month) as previous_month_revenue FROM monthly_revenue ) SELECT month, CASE WHEN previous_month_revenue IS NULL THEN NULL ELSE ROUND(((total_revenue - previous_month_revenue) / previous_month_revenue) * 100, 2) END as month_over_month_growth_rate_percent FROM monthly_growth ORDER BY month`
  - Result: (2024-01, None); (2024-02, -0.82); (2024-03, 0.33); (2024-04, 0.16); (2024-05, -1.13); (2024-06, -1.35); (2024-07, -37.97); (2024-08, 1.04); (2024-09, 0.29); (2024-10, 60.32); (2024-11, 0.12); (2024-12, 1.45)

- **PASS** · repeats [6] (1/10)
  - SQL: `WITH monthly_revenue AS ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS total_revenue FROM sales GROUP BY strftime('%Y-%m', sale_date) ), revenue_growth AS ( SELECT month, total_revenue, LAG(total_revenue, 1, 0) OVER (ORDER BY month) AS prev_month_revenue FROM monthly_revenue ) SELECT month, CASE WHEN prev_month_revenue = 0 THEN NULL ELSE ((total_revenue - prev_month_revenue) / prev_month_revenue) * 100 END AS revenue_growth_rate FROM revenue_growth ORDER BY month`
  - Result: (2024-01, None); (2024-02, -0.82); (2024-03, 0.33); (2024-04, 0.16); (2024-05, -1.13); (2024-06, -1.35); (2024-07, -37.97); (2024-08, 1.04); (2024-09, 0.29); (2024-10, 60.32); (2024-11, 0.12); (2024-12, 1.45)

- **PASS** · repeats [7] (1/10)
  - SQL: `WITH monthly_revenue AS ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS total_revenue FROM sales GROUP BY strftime('%Y-%m', sale_date) ), monthly_growth AS ( SELECT month, total_revenue, LAG(total_revenue, 1, 0) OVER (ORDER BY month) AS previous_month_revenue, CASE WHEN LAG(total_revenue, 1, 0) OVER (ORDER BY month) = 0 THEN NULL ELSE ((total_revenue - LAG(total_revenue, 1, 0) OVER (ORDER BY month)) / LAG(total_revenue, 1, 0) OVER (ORDER BY month)) * 100 END AS growth_rate FROM monthly_revenue ) SELECT month, growth_rate FROM monthly_growth ORDER BY month;`
  - Result: (2024-01, None); (2024-02, -0.82); (2024-03, 0.33); (2024-04, 0.16); (2024-05, -1.13); (2024-06, -1.35); (2024-07, -37.97); (2024-08, 1.04); (2024-09, 0.29); (2024-10, 60.32); (2024-11, 0.12); (2024-12, 1.45)

- **PASS** · repeats [8] (1/10)
  - SQL: `WITH monthly_revenue AS ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS total_revenue FROM sales GROUP BY strftime('%Y-%m', sale_date) ), revenue_with_lag AS ( SELECT month, total_revenue, LAG(total_revenue, 1) OVER (ORDER BY month) AS prev_month_revenue FROM monthly_revenue ) SELECT month, CASE WHEN prev_month_revenue IS NOT NULL AND prev_month_revenue > 0 THEN ((total_revenue - prev_month_revenue) / prev_month_revenue) * 100 ELSE NULL END AS revenue_growth_rate_percent FROM revenue_with_lag ORDER BY month`
  - Result: (2024-01, None); (2024-02, -0.82); (2024-03, 0.33); (2024-04, 0.16); (2024-05, -1.13); (2024-06, -1.35); (2024-07, -37.97); (2024-08, 1.04); (2024-09, 0.29); (2024-10, 60.32); (2024-11, 0.12); (2024-12, 1.45)

- **PASS** · repeats [9] (1/10)
  - SQL: `WITH monthly_revenue AS ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS total_revenue FROM sales GROUP BY strftime('%Y-%m', sale_date) ), monthly_growth AS ( SELECT month, total_revenue, LAG(total_revenue, 1) OVER (ORDER BY month) AS previous_month_revenue, CASE WHEN LAG(total_revenue, 1) OVER (ORDER BY month) IS NOT NULL THEN ((total_revenue - LAG(total_revenue, 1) OVER (ORDER BY month)) / LAG(total_revenue, 1) OVER (ORDER BY month)) * 100 ELSE NULL END AS growth_rate_percent FROM monthly_revenue ) SELECT month, growth_rate_percent FROM monthly_growth ORDER BY month;`
  - Result: (2024-01, None); (2024-02, -0.82); (2024-03, 0.33); (2024-04, 0.16); (2024-05, -1.13); (2024-06, -1.35); (2024-07, -37.97); (2024-08, 1.04); (2024-09, 0.29); (2024-10, 60.32); (2024-11, 0.12); (2024-12, 1.45)

- **PASS** · repeats [10] (1/10)
  - SQL: `WITH monthly_revenue AS ( SELECT strftime('%Y-%m', sale_date) AS month, SUM(revenue) AS total_revenue FROM sales GROUP BY strftime('%Y-%m', sale_date) ), revenue_with_lag AS ( SELECT month, total_revenue, LAG(total_revenue, 1) OVER (ORDER BY month) AS prev_month_revenue FROM monthly_revenue ) SELECT month, CASE WHEN prev_month_revenue IS NOT NULL AND prev_month_revenue > 0 THEN ROUND(((total_revenue - prev_month_revenue) / prev_month_revenue) * 100, 2) ELSE NULL END AS revenue_growth_rate_percent FROM revenue_with_lag ORDER BY month`
  - Result: (2024-01, None); (2024-02, -0.82); (2024-03, 0.33); (2024-04, 0.16); (2024-05, -1.13); (2024-06, -1.35); (2024-07, -37.97); (2024-08, 1.04); (2024-09, 0.29); (2024-10, 60.32); (2024-11, 0.12); (2024-12, 1.45)

### L5b_return_rate_by_product  (Level 5)
**Question:** For each product, what fraction of its revenue was returned? (returned amount divided by that product's sales revenue). Rank products from highest return-fraction to lowest.
**Expected (ground truth):** Vertex Keyboard=14.82, Cobalt Laptop=13.1, Ivory Stand=12.06, Ember Charger=12.0, Aurora Speaker=0.0, Fable Tablet=0.0, Halo Monitor=0.0, Nimbus Router=0.0, Onyx Webcam=0.0, Pulse Earbuds=0.0, Quartz Mouse=0.0, Slate Dock=0.0

#### ministral-8b — 10/10 pass

- **PASS** · repeats [1] (1/10)
  - SQL: `WITH product_sales AS ( SELECT product, SUM(revenue) AS total_revenue FROM sales GROUP BY product ), product_returns AS ( SELECT s.product, SUM(r.amount) AS total_returned FROM sales s JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ) SELECT COALESCE(ps.product, pr.product) AS product, COALESCE(pr.total_returned, 0) AS returned_amount, COALESCE(ps.total_revenue, 0) AS total_revenue, CASE WHEN ps.total_revenue = 0 THEN 0 ELSE COALESCE(pr.total_returned, 0) / ps.total_revenue END AS return_fraction FROM product_sales ps FULL OUTER JOIN product_returns pr ON ps.product = pr.product ORDER BY return_fraction DESC;`
  - Result: (Vertex Keyboard, 16050.00, 108266.47, 0.15); (Cobalt Laptop, 18525.00, 141390.97, 0.13); (Ivory Stand, 23475.00, 194731.78, 0.12); (Ember Charger, 21000.00, 174983.62, 0.12); (Aurora Speaker, 0, 93202.30, 0.00); (Fable Tablet, 0, 149597.28, 0.00); (Halo Monitor, 0, 123596.85, 0.00); (Nimbus Router, 0, 96909.51, 0.00); (Onyx Webcam, 0, 186622.05, 0.00); (Pulse Earbuds, 0, 132653.45, 0.00); (Quartz Mouse, 0, 157348.40, 0.00); (Slate Dock, 0, 188921.52, 0.00)

- **PASS** · repeats [2] (1/10)
  - SQL: `WITH product_sales AS ( SELECT product, SUM(revenue) AS total_revenue FROM sales GROUP BY product ), product_returns AS ( SELECT s.product, SUM(r.amount) AS total_return_amount FROM sales s JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ) SELECT COALESCE(pr.product, ps.product) AS product, COALESCE(pr.total_return_amount, 0) AS total_return_amount, ps.total_revenue AS total_revenue, CASE WHEN ps.total_revenue = 0 THEN 0 ELSE COALESCE(pr.total_return_amount, 0) / ps.total_revenue END AS return_fraction FROM product_sales ps LEFT JOIN product_returns pr ON ps.product = pr.product ORDER BY return_fraction DESC;`
  - Result: (Vertex Keyboard, 16050.00, 108266.47, 0.15); (Cobalt Laptop, 18525.00, 141390.97, 0.13); (Ivory Stand, 23475.00, 194731.78, 0.12); (Ember Charger, 21000.00, 174983.62, 0.12); (Aurora Speaker, 0, 93202.30, 0.00); (Fable Tablet, 0, 149597.28, 0.00); (Halo Monitor, 0, 123596.85, 0.00); (Nimbus Router, 0, 96909.51, 0.00); (Onyx Webcam, 0, 186622.05, 0.00); (Pulse Earbuds, 0, 132653.45, 0.00); (Quartz Mouse, 0, 157348.40, 0.00); (Slate Dock, 0, 188921.52, 0.00)

- **PASS** · repeats [3] (1/10)
  - SQL: `WITH product_sales_revenue AS ( SELECT product, SUM(revenue) AS total_revenue FROM sales GROUP BY product ), product_returns AS ( SELECT s.product, SUM(r.amount) AS total_return_amount FROM sales s JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ) SELECT psr.product, COALESCE(pr.total_return_amount, 0) AS returned_amount, psr.total_revenue, CASE WHEN psr.total_revenue = 0 THEN 0 ELSE COALESCE(pr.total_return_amount, 0) / psr.total_revenue END AS return_fraction FROM product_sales_revenue psr LEFT JOIN product_returns pr ON psr.product = pr.product ORDER BY return_fraction DESC;`
  - Result: (Vertex Keyboard, 16050.00, 108266.47, 0.15); (Cobalt Laptop, 18525.00, 141390.97, 0.13); (Ivory Stand, 23475.00, 194731.78, 0.12); (Ember Charger, 21000.00, 174983.62, 0.12); (Aurora Speaker, 0, 93202.30, 0.00); (Fable Tablet, 0, 149597.28, 0.00); (Halo Monitor, 0, 123596.85, 0.00); (Nimbus Router, 0, 96909.51, 0.00); (Onyx Webcam, 0, 186622.05, 0.00); (Pulse Earbuds, 0, 132653.45, 0.00); (Quartz Mouse, 0, 157348.40, 0.00); (Slate Dock, 0, 188921.52, 0.00)

- **PASS** · repeats [4] (1/10) · tool-errors=2
  - SQL: `WITH product_sales AS ( SELECT product, SUM(revenue) AS total_revenue FROM sales GROUP BY product ), product_returns AS ( SELECT s.product, SUM(r.amount) AS total_returned_amount FROM sales s JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ) SELECT COALESCE(pr.product, ps.product) AS product, COALESCE(pr.total_returned_amount, 0) AS returned_amount, ps.total_revenue AS total_revenue, CASE WHEN ps.total_revenue = 0 THEN 0 ELSE COALESCE(pr.total_returned_amount, 0) / ps.total_revenue END AS return_fraction FROM product_sales ps LEFT JOIN product_returns pr ON ps.product = pr.product ORDER BY return_fraction DESC;`
  - Result: (Vertex Keyboard, 16050.00, 108266.47, 0.15); (Cobalt Laptop, 18525.00, 141390.97, 0.13); (Ivory Stand, 23475.00, 194731.78, 0.12); (Ember Charger, 21000.00, 174983.62, 0.12); (Aurora Speaker, 0, 93202.30, 0.00); (Fable Tablet, 0, 149597.28, 0.00); (Halo Monitor, 0, 123596.85, 0.00); (Nimbus Router, 0, 96909.51, 0.00); (Onyx Webcam, 0, 186622.05, 0.00); (Pulse Earbuds, 0, 132653.45, 0.00); (Quartz Mouse, 0, 157348.40, 0.00); (Slate Dock, 0, 188921.52, 0.00)

- **PASS** · repeats [5] (1/10)
  - SQL: `WITH product_sales_revenue AS ( SELECT product, SUM(revenue) AS total_revenue FROM sales GROUP BY product ), product_returns AS ( SELECT s.product, SUM(r.amount) AS total_return_amount FROM sales s JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ) SELECT psr.product, COALESCE(pr.total_return_amount, 0) AS returned_amount, psr.total_revenue AS sales_revenue, CASE WHEN psr.total_revenue = 0 THEN 0 ELSE COALESCE(pr.total_return_amount, 0) / psr.total_revenue END AS return_fraction FROM product_sales_revenue psr LEFT JOIN product_returns pr ON psr.product = pr.product ORDER BY return_fraction DESC;`
  - Result: (Vertex Keyboard, 16050.00, 108266.47, 0.15); (Cobalt Laptop, 18525.00, 141390.97, 0.13); (Ivory Stand, 23475.00, 194731.78, 0.12); (Ember Charger, 21000.00, 174983.62, 0.12); (Aurora Speaker, 0, 93202.30, 0.00); (Fable Tablet, 0, 149597.28, 0.00); (Halo Monitor, 0, 123596.85, 0.00); (Nimbus Router, 0, 96909.51, 0.00); (Onyx Webcam, 0, 186622.05, 0.00); (Pulse Earbuds, 0, 132653.45, 0.00); (Quartz Mouse, 0, 157348.40, 0.00); (Slate Dock, 0, 188921.52, 0.00)

- **PASS** · repeats [6] (1/10)
  - SQL: `WITH product_sales AS ( SELECT product, SUM(revenue) AS total_revenue FROM sales GROUP BY product ), product_returns AS ( SELECT s.product, SUM(r.amount) AS total_returned FROM sales s JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ) SELECT ps.product, COALESCE(pr.total_returned, 0) AS returned_amount, ps.total_revenue, COALESCE(pr.total_returned, 0) / NULLIF(ps.total_revenue, 0) AS return_fraction FROM product_sales ps LEFT JOIN product_returns pr ON ps.product = pr.product ORDER BY return_fraction DESC;`
  - Result: (Vertex Keyboard, 16050.00, 108266.47, 0.15); (Cobalt Laptop, 18525.00, 141390.97, 0.13); (Ivory Stand, 23475.00, 194731.78, 0.12); (Ember Charger, 21000.00, 174983.62, 0.12); (Aurora Speaker, 0, 93202.30, 0.00); (Fable Tablet, 0, 149597.28, 0.00); (Halo Monitor, 0, 123596.85, 0.00); (Nimbus Router, 0, 96909.51, 0.00); (Onyx Webcam, 0, 186622.05, 0.00); (Pulse Earbuds, 0, 132653.45, 0.00); (Quartz Mouse, 0, 157348.40, 0.00); (Slate Dock, 0, 188921.52, 0.00)

- **PASS** · repeats [7] (1/10)
  - SQL: `WITH product_sales AS ( SELECT product, SUM(revenue) AS total_revenue FROM sales GROUP BY product ), product_returns AS ( SELECT s.product, SUM(r.amount) AS total_return_amount FROM sales s JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ) SELECT ps.product, COALESCE(pr.total_return_amount, 0) AS total_return_amount, ps.total_revenue, CASE WHEN ps.total_revenue = 0 THEN 0 ELSE COALESCE(pr.total_return_amount, 0) / ps.total_revenue END AS return_fraction FROM product_sales ps LEFT JOIN product_returns pr ON ps.product = pr.product ORDER BY return_fraction DESC;`
  - Result: (Vertex Keyboard, 16050.00, 108266.47, 0.15); (Cobalt Laptop, 18525.00, 141390.97, 0.13); (Ivory Stand, 23475.00, 194731.78, 0.12); (Ember Charger, 21000.00, 174983.62, 0.12); (Aurora Speaker, 0, 93202.30, 0.00); (Fable Tablet, 0, 149597.28, 0.00); (Halo Monitor, 0, 123596.85, 0.00); (Nimbus Router, 0, 96909.51, 0.00); (Onyx Webcam, 0, 186622.05, 0.00); (Pulse Earbuds, 0, 132653.45, 0.00); (Quartz Mouse, 0, 157348.40, 0.00); (Slate Dock, 0, 188921.52, 0.00)

- **PASS** · repeats [8] (1/10)
  - SQL: `WITH product_sales AS ( SELECT product, SUM(revenue) AS total_revenue FROM sales GROUP BY product ), product_returns AS ( SELECT s.product, SUM(r.amount) AS total_returned FROM sales s JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ) SELECT COALESCE(ps.product, pr.product) AS product, COALESCE(pr.total_returned, 0) AS total_returned, ps.total_revenue, CASE WHEN ps.total_revenue = 0 THEN 0 ELSE (COALESCE(pr.total_returned, 0) / ps.total_revenue) * 100 END AS return_fraction_percentage FROM product_sales ps FULL OUTER JOIN product_returns pr ON ps.product = pr.product ORDER BY return_fraction_percentage DESC;`
  - Result: (Vertex Keyboard, 16050.00, 108266.47, 14.82); (Cobalt Laptop, 18525.00, 141390.97, 13.10); (Ivory Stand, 23475.00, 194731.78, 12.06); (Ember Charger, 21000.00, 174983.62, 12.00); (Aurora Speaker, 0, 93202.30, 0.00); (Fable Tablet, 0, 149597.28, 0.00); (Halo Monitor, 0, 123596.85, 0.00); (Nimbus Router, 0, 96909.51, 0.00); (Onyx Webcam, 0, 186622.05, 0.00); (Pulse Earbuds, 0, 132653.45, 0.00); (Quartz Mouse, 0, 157348.40, 0.00); (Slate Dock, 0, 188921.52, 0.00)

- **PASS** · repeats [9,10] (2/10)
  - SQL: `WITH product_sales AS ( SELECT product, SUM(revenue) AS total_revenue FROM sales GROUP BY product ), product_returns AS ( SELECT s.product, SUM(r.amount) AS total_return_amount FROM sales s JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ) SELECT ps.product, COALESCE(pr.total_return_amount, 0) AS returned_amount, ps.total_revenue, CASE WHEN ps.total_revenue = 0 THEN 0 ELSE COALESCE(pr.total_return_amount, 0) / ps.total_revenue END AS return_fraction FROM product_sales ps LEFT JOIN product_returns pr ON ps.product = pr.product ORDER BY return_fraction DESC;`
  - Result: (Vertex Keyboard, 16050.00, 108266.47, 0.15); (Cobalt Laptop, 18525.00, 141390.97, 0.13); (Ivory Stand, 23475.00, 194731.78, 0.12); (Ember Charger, 21000.00, 174983.62, 0.12); (Aurora Speaker, 0, 93202.30, 0.00); (Fable Tablet, 0, 149597.28, 0.00); (Halo Monitor, 0, 123596.85, 0.00); (Nimbus Router, 0, 96909.51, 0.00); (Onyx Webcam, 0, 186622.05, 0.00); (Pulse Earbuds, 0, 132653.45, 0.00); (Quartz Mouse, 0, 157348.40, 0.00); (Slate Dock, 0, 188921.52, 0.00)

#### gpt-oss-20b — 1/10 pass

- **FAIL** · repeats [1,4] (2/10)
  - SQL: `SELECT s.product, SUM(s.revenue) AS total_revenue, COALESCE(SUM(r.amount),0) AS total_returns, COALESCE(SUM(r.amount),0)/SUM(s.revenue) AS return_fraction FROM sales s LEFT JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ORDER BY return_fraction DESC;`
  - Result: (Vertex Keyboard, 142609.14, 16050.00, 0.11); (Cobalt Laptop, 176720.12, 18525.00, 0.10); (Ember Charger, 222970.60, 21000.00, 0.09); (Ivory Stand, 255042.31, 23475.00, 0.09); (Slate Dock, 188921.52, 0, 0.00); (Quartz Mouse, 157348.40, 0, 0.00); (Pulse Earbuds, 132653.45, 0, 0.00); (Onyx Webcam, 186622.05, 0, 0.00); (Nimbus Router, 96909.51, 0, 0.00); (Halo Monitor, 123596.85, 0, 0.00); (Fable Tablet, 149597.28, 0, 0.00); (Aurora Speaker, 93202.30, 0, 0.00)
  - WHY: fan-out double-count: sales↔returns joined ON sale_id inflates the revenue denominator

- **FAIL** · repeats [2,10] (2/10)
  - SQL: `SELECT product, SUM(sales.revenue) AS total_revenue, SUM(COALESCE(returns.amount,0)) AS total_returns, SUM(COALESCE(returns.amount,0))/SUM(sales.revenue) AS return_fraction FROM sales LEFT JOIN returns ON sales.sale_id = returns.sale_id GROUP BY product ORDER BY return_fraction DESC;`
  - Result: (Vertex Keyboard, 142609.14, 16050.00, 0.11); (Cobalt Laptop, 176720.12, 18525.00, 0.10); (Ember Charger, 222970.60, 21000.00, 0.09); (Ivory Stand, 255042.31, 23475.00, 0.09); (Slate Dock, 188921.52, 0, 0.00); (Quartz Mouse, 157348.40, 0, 0.00); (Pulse Earbuds, 132653.45, 0, 0.00); (Onyx Webcam, 186622.05, 0, 0.00); (Nimbus Router, 96909.51, 0, 0.00); (Halo Monitor, 123596.85, 0, 0.00); (Fable Tablet, 149597.28, 0, 0.00); (Aurora Speaker, 93202.30, 0, 0.00)
  - WHY: fan-out double-count: sales↔returns joined ON sale_id inflates the revenue denominator

- **FAIL** · repeats [3,5,7] (3/10)
  - SQL: `SELECT s.product, SUM(s.revenue) AS total_revenue, COALESCE(SUM(r.amount), 0) AS total_returns, COALESCE(SUM(r.amount), 0) / SUM(s.revenue) AS return_fraction FROM sales s LEFT JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ORDER BY return_fraction DESC;`
  - Result: (Vertex Keyboard, 142609.14, 16050.00, 0.11); (Cobalt Laptop, 176720.12, 18525.00, 0.10); (Ember Charger, 222970.60, 21000.00, 0.09); (Ivory Stand, 255042.31, 23475.00, 0.09); (Slate Dock, 188921.52, 0, 0.00); (Quartz Mouse, 157348.40, 0, 0.00); (Pulse Earbuds, 132653.45, 0, 0.00); (Onyx Webcam, 186622.05, 0, 0.00); (Nimbus Router, 96909.51, 0, 0.00); (Halo Monitor, 123596.85, 0, 0.00); (Fable Tablet, 149597.28, 0, 0.00); (Aurora Speaker, 93202.30, 0, 0.00)
  - WHY: fan-out double-count: sales↔returns joined ON sale_id inflates the revenue denominator

- **FAIL** · repeats [6,8] (2/10)
  - SQL: `SELECT s.product, SUM(s.revenue) AS total_rev, COALESCE(SUM(r.amount),0) AS total_ret, COALESCE(SUM(r.amount),0)/SUM(s.revenue) AS return_fraction FROM sales s LEFT JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ORDER BY return_fraction DESC;`
  - Result: (Vertex Keyboard, 142609.14, 16050.00, 0.11); (Cobalt Laptop, 176720.12, 18525.00, 0.10); (Ember Charger, 222970.60, 21000.00, 0.09); (Ivory Stand, 255042.31, 23475.00, 0.09); (Slate Dock, 188921.52, 0, 0.00); (Quartz Mouse, 157348.40, 0, 0.00); (Pulse Earbuds, 132653.45, 0, 0.00); (Onyx Webcam, 186622.05, 0, 0.00); (Nimbus Router, 96909.51, 0, 0.00); (Halo Monitor, 123596.85, 0, 0.00); (Fable Tablet, 149597.28, 0, 0.00); (Aurora Speaker, 93202.30, 0, 0.00)
  - WHY: fan-out double-count: sales↔returns joined ON sale_id inflates the revenue denominator

- **PASS** · repeats [9] (1/10)
  - SQL: `WITH sale_returns AS ( SELECT s.product, s.revenue, COALESCE(r.total_return,0) as return_amount FROM sales s LEFT JOIN ( SELECT sale_id, SUM(amount) as total_return FROM returns GROUP BY sale_id ) r ON s.sale_id = r.sale_id ) SELECT product, SUM(revenue) as total_revenue, SUM(return_amount) as total_return, SUM(return_amount)/SUM(revenue) as return_fraction FROM sale_returns GROUP BY product ORDER BY return_fraction DESC;`
  - Result: (Vertex Keyboard, 108266.47, 16050.00, 0.15); (Cobalt Laptop, 141390.97, 18525.00, 0.13); (Ivory Stand, 194731.78, 23475.00, 0.12); (Ember Charger, 174983.62, 21000.00, 0.12); (Slate Dock, 188921.52, 0, 0.00); (Quartz Mouse, 157348.40, 0, 0.00); (Pulse Earbuds, 132653.45, 0, 0.00); (Onyx Webcam, 186622.05, 0, 0.00); (Nimbus Router, 96909.51, 0, 0.00); (Halo Monitor, 123596.85, 0, 0.00); (Fable Tablet, 149597.28, 0, 0.00); (Aurora Speaker, 93202.30, 0, 0.00)

#### ollama-cloud — 2/10 pass

- **PASS** · repeats [1] (1/10)
  - SQL: `WITH rev AS ( SELECT product, SUM(revenue) AS total_rev FROM sales GROUP BY product ), ret AS ( SELECT s.product, SUM(r.amount) AS total_ret FROM sales s LEFT JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ) SELECT rev.product, rev.total_rev, COALESCE(ret.total_ret, 0) AS total_ret, COALESCE(ret.total_ret, 0) / NULLIF(rev.total_rev, 0) AS return_frac FROM rev LEFT JOIN ret ON rev.product = ret.product ORDER BY return_frac DESC;`
  - Result: (Vertex Keyboard, 108266.47, 16050.00, 0.15); (Cobalt Laptop, 141390.97, 18525.00, 0.13); (Ivory Stand, 194731.78, 23475.00, 0.12); (Ember Charger, 174983.62, 21000.00, 0.12); (Aurora Speaker, 93202.30, 0, 0.00); (Fable Tablet, 149597.28, 0, 0.00); (Halo Monitor, 123596.85, 0, 0.00); (Nimbus Router, 96909.51, 0, 0.00); (Onyx Webcam, 186622.05, 0, 0.00); (Pulse Earbuds, 132653.45, 0, 0.00); (Quartz Mouse, 157348.40, 0, 0.00); (Slate Dock, 188921.52, 0, 0.00)

- **FAIL** · repeats [2] (1/10)
  - SQL: `SELECT s.product, SUM(s.revenue) AS total_revenue, COALESCE(SUM(r.amount), 0) AS total_returns, CASE WHEN SUM(s.revenue) = 0 THEN 0 ELSE COALESCE(SUM(r.amount), 0) * 1.0 / SUM(s.revenue) END AS return_fraction FROM sales s LEFT JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ORDER BY return_fraction DESC;`
  - Result: (Vertex Keyboard, 142609.14, 16050.00, 0.11); (Cobalt Laptop, 176720.12, 18525.00, 0.10); (Ember Charger, 222970.60, 21000.00, 0.09); (Ivory Stand, 255042.31, 23475.00, 0.09); (Slate Dock, 188921.52, 0, 0.00); (Quartz Mouse, 157348.40, 0, 0.00); (Pulse Earbuds, 132653.45, 0, 0.00); (Onyx Webcam, 186622.05, 0, 0.00); (Nimbus Router, 96909.51, 0, 0.00); (Halo Monitor, 123596.85, 0, 0.00); (Fable Tablet, 149597.28, 0, 0.00); (Aurora Speaker, 93202.30, 0, 0.00)
  - WHY: fan-out double-count: sales↔returns joined ON sale_id inflates the revenue denominator

- **FAIL** · repeats [3] (1/10)
  - SQL: `SELECT s.product, COALESCE(SUM(r.amount),0) AS total_returns, SUM(s.revenue) AS total_revenue, COALESCE(SUM(r.amount),0) * 1.0 / NULLIF(SUM(s.revenue),0) AS return_fraction FROM sales s LEFT JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ORDER BY return_fraction DESC;`
  - Result: (Vertex Keyboard, 16050.00, 142609.14, 0.11); (Cobalt Laptop, 18525.00, 176720.12, 0.10); (Ember Charger, 21000.00, 222970.60, 0.09); (Ivory Stand, 23475.00, 255042.31, 0.09); (Slate Dock, 0, 188921.52, 0.00); (Quartz Mouse, 0, 157348.40, 0.00); (Pulse Earbuds, 0, 132653.45, 0.00); (Onyx Webcam, 0, 186622.05, 0.00); (Nimbus Router, 0, 96909.51, 0.00); (Halo Monitor, 0, 123596.85, 0.00); (Fable Tablet, 0, 149597.28, 0.00); (Aurora Speaker, 0, 93202.30, 0.00)
  - WHY: fan-out double-count: sales↔returns joined ON sale_id inflates the revenue denominator

- **FAIL** · repeats [4] (1/10)
  - SQL: `SELECT s.product, SUM(s.revenue) AS revenue, COALESCE(SUM(r.amount),0) AS returned, CASE WHEN SUM(s.revenue) = 0 THEN 0 ELSE COALESCE(SUM(r.amount),0) / SUM(s.revenue) END AS return_fraction FROM sales s LEFT JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ORDER BY return_fraction DESC;`
  - Result: (Vertex Keyboard, 142609.14, 16050.00, 0.11); (Cobalt Laptop, 176720.12, 18525.00, 0.10); (Ember Charger, 222970.60, 21000.00, 0.09); (Ivory Stand, 255042.31, 23475.00, 0.09); (Slate Dock, 188921.52, 0, 0.00); (Quartz Mouse, 157348.40, 0, 0.00); (Pulse Earbuds, 132653.45, 0, 0.00); (Onyx Webcam, 186622.05, 0, 0.00); (Nimbus Router, 96909.51, 0, 0.00); (Halo Monitor, 123596.85, 0, 0.00); (Fable Tablet, 149597.28, 0, 0.00); (Aurora Speaker, 93202.30, 0, 0.00)
  - WHY: fan-out double-count: sales↔returns joined ON sale_id inflates the revenue denominator

- **FAIL** · repeats [5] (1/10)
  - SQL: `SELECT s.product, SUM(s.revenue) AS total_rev, COALESCE(SUM(r.amount),0) AS total_ret, COALESCE(SUM(r.amount),0) / SUM(s.revenue) AS return_fraction FROM sales s LEFT JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ORDER BY return_fraction DESC;`
  - Result: (Vertex Keyboard, 142609.14, 16050.00, 0.11); (Cobalt Laptop, 176720.12, 18525.00, 0.10); (Ember Charger, 222970.60, 21000.00, 0.09); (Ivory Stand, 255042.31, 23475.00, 0.09); (Slate Dock, 188921.52, 0, 0.00); (Quartz Mouse, 157348.40, 0, 0.00); (Pulse Earbuds, 132653.45, 0, 0.00); (Onyx Webcam, 186622.05, 0, 0.00); (Nimbus Router, 96909.51, 0, 0.00); (Halo Monitor, 123596.85, 0, 0.00); (Fable Tablet, 149597.28, 0, 0.00); (Aurora Speaker, 93202.30, 0, 0.00)
  - WHY: fan-out double-count: sales↔returns joined ON sale_id inflates the revenue denominator

- **FAIL** · repeats [6] (1/10)
  - SQL: `SELECT s.product, SUM(s.revenue) AS revenue, COALESCE(SUM(r.amount),0) AS return_amount, CASE WHEN SUM(s.revenue) = 0 THEN 0 ELSE COALESCE(SUM(r.amount),0) * 1.0 / SUM(s.revenue) END AS return_fraction FROM sales s LEFT JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ORDER BY return_fraction DESC;`
  - Result: (Vertex Keyboard, 142609.14, 16050.00, 0.11); (Cobalt Laptop, 176720.12, 18525.00, 0.10); (Ember Charger, 222970.60, 21000.00, 0.09); (Ivory Stand, 255042.31, 23475.00, 0.09); (Slate Dock, 188921.52, 0, 0.00); (Quartz Mouse, 157348.40, 0, 0.00); (Pulse Earbuds, 132653.45, 0, 0.00); (Onyx Webcam, 186622.05, 0, 0.00); (Nimbus Router, 96909.51, 0, 0.00); (Halo Monitor, 123596.85, 0, 0.00); (Fable Tablet, 149597.28, 0, 0.00); (Aurora Speaker, 93202.30, 0, 0.00)
  - WHY: fan-out double-count: sales↔returns joined ON sale_id inflates the revenue denominator

- **FAIL** · repeats [7,9] (2/10)
  - SQL: `SELECT s.product, SUM(s.revenue) AS total_revenue, COALESCE(SUM(r.amount),0) AS total_returns, COALESCE(SUM(r.amount),0) / NULLIF(SUM(s.revenue),0) AS return_fraction FROM sales s LEFT JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ORDER BY return_fraction DESC;`
  - Result: (Vertex Keyboard, 142609.14, 16050.00, 0.11); (Cobalt Laptop, 176720.12, 18525.00, 0.10); (Ember Charger, 222970.60, 21000.00, 0.09); (Ivory Stand, 255042.31, 23475.00, 0.09); (Slate Dock, 188921.52, 0, 0.00); (Quartz Mouse, 157348.40, 0, 0.00); (Pulse Earbuds, 132653.45, 0, 0.00); (Onyx Webcam, 186622.05, 0, 0.00); (Nimbus Router, 96909.51, 0, 0.00); (Halo Monitor, 123596.85, 0, 0.00); (Fable Tablet, 149597.28, 0, 0.00); (Aurora Speaker, 93202.30, 0, 0.00)
  - WHY: fan-out double-count: sales↔returns joined ON sale_id inflates the revenue denominator

- **FAIL** · repeats [8] (1/10)
  - SQL: `SELECT s.product, SUM(s.revenue) AS total_revenue, COALESCE(SUM(r.amount),0) AS total_returns, COALESCE(SUM(r.amount),0) / SUM(s.revenue) AS return_fraction FROM sales s LEFT JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ORDER BY return_fraction DESC;`
  - Result: (Vertex Keyboard, 142609.14, 16050.00, 0.11); (Cobalt Laptop, 176720.12, 18525.00, 0.10); (Ember Charger, 222970.60, 21000.00, 0.09); (Ivory Stand, 255042.31, 23475.00, 0.09); (Slate Dock, 188921.52, 0, 0.00); (Quartz Mouse, 157348.40, 0, 0.00); (Pulse Earbuds, 132653.45, 0, 0.00); (Onyx Webcam, 186622.05, 0, 0.00); (Nimbus Router, 96909.51, 0, 0.00); (Halo Monitor, 123596.85, 0, 0.00); (Fable Tablet, 149597.28, 0, 0.00); (Aurora Speaker, 93202.30, 0, 0.00)
  - WHY: fan-out double-count: sales↔returns joined ON sale_id inflates the revenue denominator

- **PASS** · repeats [10] (1/10)
  - SQL: `WITH rev AS ( SELECT product, SUM(revenue) AS total_rev FROM sales GROUP BY product ), ret AS ( SELECT s.product, SUM(r.amount) AS total_ret FROM sales s JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ) SELECT rev.product, rev.total_rev, COALESCE(ret.total_ret, 0) AS total_ret, COALESCE(ret.total_ret, 0) / rev.total_rev AS return_fraction FROM rev LEFT JOIN ret ON rev.product = ret.product ORDER BY return_fraction DESC;`
  - Result: (Vertex Keyboard, 108266.47, 16050.00, 0.15); (Cobalt Laptop, 141390.97, 18525.00, 0.13); (Ivory Stand, 194731.78, 23475.00, 0.12); (Ember Charger, 174983.62, 21000.00, 0.12); (Aurora Speaker, 93202.30, 0, 0.00); (Fable Tablet, 149597.28, 0, 0.00); (Halo Monitor, 123596.85, 0, 0.00); (Nimbus Router, 96909.51, 0, 0.00); (Onyx Webcam, 186622.05, 0, 0.00); (Pulse Earbuds, 132653.45, 0, 0.00); (Quartz Mouse, 157348.40, 0, 0.00); (Slate Dock, 188921.52, 0, 0.00)

#### qwen3-coder — 4/10 pass

- **FAIL** · repeats [1,3,5,8] (4/10)
  - SQL: `SELECT s.product, SUM(s.revenue) as total_revenue, COALESCE(SUM(r.amount), 0) as total_returns, CASE WHEN SUM(s.revenue) = 0 THEN 0 ELSE COALESCE(SUM(r.amount), 0) / SUM(s.revenue) END as return_fraction FROM sales s LEFT JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ORDER BY return_fraction DESC`
  - Result: (Vertex Keyboard, 142609.14, 16050.00, 0.11); (Cobalt Laptop, 176720.12, 18525.00, 0.10); (Ember Charger, 222970.60, 21000.00, 0.09); (Ivory Stand, 255042.31, 23475.00, 0.09); (Slate Dock, 188921.52, 0, 0.00); (Quartz Mouse, 157348.40, 0, 0.00); (Pulse Earbuds, 132653.45, 0, 0.00); (Onyx Webcam, 186622.05, 0, 0.00); (Nimbus Router, 96909.51, 0, 0.00); (Halo Monitor, 123596.85, 0, 0.00); (Fable Tablet, 149597.28, 0, 0.00); (Aurora Speaker, 93202.30, 0, 0.00)
  - WHY: fan-out double-count: sales↔returns joined ON sale_id inflates the revenue denominator

- **PASS** · repeats [2] (1/10)
  - SQL: `WITH product_revenue AS ( SELECT product, SUM(revenue) as total_revenue FROM sales GROUP BY product ), product_returns AS ( SELECT s.product, COALESCE(SUM(r.amount), 0) as total_returns FROM sales s LEFT JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ) SELECT pr.product, pr.total_revenue, COALESCE(ptr.total_returns, 0) as total_returns, CASE WHEN pr.total_revenue = 0 THEN 0 ELSE COALESCE(ptr.total_returns, 0) / pr.total_revenue END as return_fraction FROM product_revenue pr LEFT JOIN product_returns ptr ON pr.product = ptr.product ORDER BY return_fraction DESC`
  - Result: (Vertex Keyboard, 108266.47, 16050.00, 0.15); (Cobalt Laptop, 141390.97, 18525.00, 0.13); (Ivory Stand, 194731.78, 23475.00, 0.12); (Ember Charger, 174983.62, 21000.00, 0.12); (Aurora Speaker, 93202.30, 0, 0.00); (Fable Tablet, 149597.28, 0, 0.00); (Halo Monitor, 123596.85, 0, 0.00); (Nimbus Router, 96909.51, 0, 0.00); (Onyx Webcam, 186622.05, 0, 0.00); (Pulse Earbuds, 132653.45, 0, 0.00); (Quartz Mouse, 157348.40, 0, 0.00); (Slate Dock, 188921.52, 0, 0.00)

- **PASS** · repeats [4] (1/10)
  - SQL: `WITH product_sales AS ( SELECT product, SUM(revenue) AS total_revenue FROM sales GROUP BY product ), product_returns AS ( SELECT s.product, COALESCE(SUM(r.amount), 0) AS total_returns FROM sales s LEFT JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ) SELECT ps.product, ps.total_revenue, pr.total_returns, CASE WHEN ps.total_revenue = 0 THEN 0 ELSE pr.total_returns / ps.total_revenue END AS return_fraction FROM product_sales ps JOIN product_returns pr ON ps.product = pr.product ORDER BY return_fraction DESC`
  - Result: (Vertex Keyboard, 108266.47, 16050.00, 0.15); (Cobalt Laptop, 141390.97, 18525.00, 0.13); (Ivory Stand, 194731.78, 23475.00, 0.12); (Ember Charger, 174983.62, 21000.00, 0.12); (Aurora Speaker, 93202.30, 0, 0.00); (Fable Tablet, 149597.28, 0, 0.00); (Halo Monitor, 123596.85, 0, 0.00); (Nimbus Router, 96909.51, 0, 0.00); (Onyx Webcam, 186622.05, 0, 0.00); (Pulse Earbuds, 132653.45, 0, 0.00); (Quartz Mouse, 157348.40, 0, 0.00); (Slate Dock, 188921.52, 0, 0.00)

- **FAIL** · repeats [6] (1/10)
  - SQL: `WITH product_revenue AS ( SELECT product, SUM(revenue) as total_revenue FROM sales GROUP BY product ), product_returns AS ( SELECT s.product, SUM(r.amount) as total_returns FROM sales s JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ) SELECT pr.product, COALESCE(pr.total_returns, 0) as returned_amount, prv.total_revenue as sales_revenue, CASE WHEN prv.total_revenue = 0 THEN 0 ELSE COALESCE(pr.total_returns, 0) / prv.total_revenue END as return_fraction FROM product_revenue prv LEFT JOIN product_returns pr ON prv.product = pr.product ORDER BY return_fraction DESC`
  - Result: (Vertex Keyboard, 16050.00, 108266.47, 0.15); (Cobalt Laptop, 18525.00, 141390.97, 0.13); (Ivory Stand, 23475.00, 194731.78, 0.12); (Ember Charger, 21000.00, 174983.62, 0.12); (None, 0, 93202.30, 0.00); (None, 0, 149597.28, 0.00); (None, 0, 123596.85, 0.00); (None, 0, 96909.51, 0.00); (None, 0, 186622.05, 0.00); (None, 0, 132653.45, 0.00); (None, 0, 157348.40, 0.00); (None, 0, 188921.52, 0.00)
  - WHY: fan-out double-count: sales↔returns joined ON sale_id inflates the revenue denominator

- **PASS** · repeats [7] (1/10)
  - SQL: `WITH product_revenue AS ( SELECT product, SUM(revenue) as total_revenue FROM sales GROUP BY product ), product_returns AS ( SELECT s.product, COALESCE(SUM(r.amount), 0) as total_returns FROM sales s LEFT JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ) SELECT pr.product, pr.total_revenue, COALESCE(ptr.total_returns, 0) as total_returns, CASE WHEN pr.total_revenue > 0 THEN COALESCE(ptr.total_returns, 0) / pr.total_revenue ELSE 0 END as return_fraction FROM product_revenue pr LEFT JOIN product_returns ptr ON pr.product = ptr.product ORDER BY return_fraction DESC`
  - Result: (Vertex Keyboard, 108266.47, 16050.00, 0.15); (Cobalt Laptop, 141390.97, 18525.00, 0.13); (Ivory Stand, 194731.78, 23475.00, 0.12); (Ember Charger, 174983.62, 21000.00, 0.12); (Aurora Speaker, 93202.30, 0, 0.00); (Fable Tablet, 149597.28, 0, 0.00); (Halo Monitor, 123596.85, 0, 0.00); (Nimbus Router, 96909.51, 0, 0.00); (Onyx Webcam, 186622.05, 0, 0.00); (Pulse Earbuds, 132653.45, 0, 0.00); (Quartz Mouse, 157348.40, 0, 0.00); (Slate Dock, 188921.52, 0, 0.00)

- **PASS** · repeats [9] (1/10)
  - SQL: `WITH product_sales AS ( SELECT product, SUM(revenue) as total_revenue FROM sales GROUP BY product ), product_returns AS ( SELECT s.product, SUM(r.amount) as total_returns FROM returns r JOIN sales s ON r.sale_id = s.sale_id GROUP BY s.product ) SELECT ps.product, ps.total_revenue, COALESCE(pr.total_returns, 0) as total_returns, CASE WHEN ps.total_revenue = 0 THEN 0 ELSE COALESCE(pr.total_returns, 0) / ps.total_revenue END as return_fraction FROM product_sales ps LEFT JOIN product_returns pr ON ps.product = pr.product ORDER BY return_fraction DESC`
  - Result: (Vertex Keyboard, 108266.47, 16050.00, 0.15); (Cobalt Laptop, 141390.97, 18525.00, 0.13); (Ivory Stand, 194731.78, 23475.00, 0.12); (Ember Charger, 174983.62, 21000.00, 0.12); (Aurora Speaker, 93202.30, 0, 0.00); (Fable Tablet, 149597.28, 0, 0.00); (Halo Monitor, 123596.85, 0, 0.00); (Nimbus Router, 96909.51, 0, 0.00); (Onyx Webcam, 186622.05, 0, 0.00); (Pulse Earbuds, 132653.45, 0, 0.00); (Quartz Mouse, 157348.40, 0, 0.00); (Slate Dock, 188921.52, 0, 0.00)

- **FAIL** · repeats [10] (1/10)
  - SQL: `SELECT s.product, COALESCE(SUM(r.amount), 0) / SUM(s.revenue) as return_fraction FROM sales s LEFT JOIN returns r ON s.sale_id = r.sale_id GROUP BY s.product ORDER BY return_fraction DESC`
  - Result: (Vertex Keyboard, 0.11); (Cobalt Laptop, 0.10); (Ember Charger, 0.09); (Ivory Stand, 0.09); (Slate Dock, 0.00); (Quartz Mouse, 0.00); (Pulse Earbuds, 0.00); (Onyx Webcam, 0.00); (Nimbus Router, 0.00); (Halo Monitor, 0.00); (Fable Tablet, 0.00); (Aurora Speaker, 0.00)
  - WHY: fan-out double-count: sales↔returns joined ON sale_id inflates the revenue denominator
