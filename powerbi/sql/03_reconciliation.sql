USE DataWarehouse;
GO
-- Existing procedure: reads project tables; INSERTs only into a local table variable.
-- No audit writes, loaders, deployments or persistent mutations.
EXEC mart.check_quality;
GO
SELECT 'silver' AS layer,COUNT_BIG(*) AS sales_rows,SUM(CAST(sls_sales AS decimal(38,2))) AS amount,
 SUM(CAST(sls_quantity AS decimal(38,0))) AS quantity FROM silver.crm_sales_info
UNION ALL
SELECT 'mart',COUNT_BIG(*),SUM(CAST(sales_amount AS decimal(38,2))),SUM(CAST(quantity AS decimal(38,0))) FROM mart.fact_sales;
GO
SELECT COUNT_BIG(*) AS joined_rows,SUM(f.sales_amount) AS joined_sales_amount
FROM mart.fact_sales f LEFT JOIN mart.dim_customer c ON c.customer_key=f.customer_key
LEFT JOIN mart.dim_product p ON p.product_key=f.product_key;
GO
SELECT COUNT_BIG(*) AS nonnull_dates,COUNT(DISTINCT calendar_date) AS distinct_dates,
 MIN(calendar_date) AS min_date,MAX(calendar_date) AS max_date,
 DATEDIFF(day,MIN(calendar_date),MAX(calendar_date))+1 AS expected_contiguous_dates
FROM mart.dim_date WHERE calendar_date IS NOT NULL;
GO
-- BI diagnostic, not a new blocking pipeline rule. Mixed known/missing order dates exist.
-- Distinct orders are NOT additive across date/category groups; never sum group counts.
SELECT COUNT_BIG(*) AS inconsistent_orders FROM (
 SELECT order_number FROM mart.fact_sales GROUP BY order_number
 HAVING COUNT(DISTINCT customer_key)>1 OR COUNT(DISTINCT order_date_key)>1
) x;
GO
SELECT SUM(CASE WHEN customers>1 THEN 1 ELSE 0 END) AS multi_customer_orders,
 SUM(CASE WHEN dates>1 THEN 1 ELSE 0 END) AS multi_date_key_orders,
 SUM(CASE WHEN dates>1 AND missing_dates>0 THEN 1 ELSE 0 END) AS mixed_known_missing_date_orders
FROM (SELECT order_number,COUNT(DISTINCT customer_key) customers,COUNT(DISTINCT order_date_key) dates,
 SUM(CASE WHEN order_date_key=0 THEN 1 ELSE 0 END) missing_dates
 FROM mart.fact_sales GROUP BY order_number) x;
