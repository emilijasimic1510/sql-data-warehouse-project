-- Read-only; all-time includes unknown keys and undated sales. Amount has no known currency.
USE DataWarehouse;
GO
SELECT COUNT_BIG(*) AS sales_rows, COUNT(DISTINCT order_number) AS orders,
 SUM(CAST(sales_amount AS decimal(38,2))) AS sales_amount,
 SUM(CAST(quantity AS decimal(38,0))) AS quantity,
 COUNT(DISTINCT CASE WHEN customer_key<>0 THEN customer_key END) AS purchasing_customers,
 SUM(sales_amount)/NULLIF(CAST(COUNT(DISTINCT order_number) AS decimal(19,4)),0) AS average_order_value,
 MIN(source_order_date) AS first_order_date, MAX(source_order_date) AS last_order_date,
 MIN(source_shipping_date) AS first_shipping_date,MAX(source_shipping_date) AS last_shipping_date,
 MIN(source_due_date) AS first_due_date,MAX(source_due_date) AS last_due_date,
 SUM(CASE WHEN order_date_key=0 THEN CAST(1 AS bigint) ELSE 0 END) AS sales_without_order_date,
 SUM(CASE WHEN order_date_key=0 THEN sales_amount ELSE 0 END) AS amount_without_order_date,
 SUM(CASE WHEN product_key=0 THEN sales_amount ELSE 0 END) AS unknown_product_sales_amount,
 100.0*SUM(CASE WHEN product_key=0 THEN sales_amount ELSE 0 END)/NULLIF(SUM(sales_amount),0) AS unknown_product_pct
FROM mart.fact_sales;
GO
-- Repeat means >=2 distinct orders IN THE SAME selected context, not lifetime status.
-- NULL bounds mean all-time (including undated). Set BOTH bounds to restrict order dates.
DECLARE @start date=NULL, @end_exclusive date=NULL;
WITH customer_orders AS (
 SELECT customer_key,COUNT(DISTINCT order_number) AS orders
 FROM mart.fact_sales WHERE customer_key<>0
 AND (@start IS NULL OR source_order_date>=@start)
 AND (@end_exclusive IS NULL OR source_order_date<@end_exclusive)
 GROUP BY customer_key
)
SELECT COUNT_BIG(*) AS purchasing_customers,
 SUM(CASE WHEN orders>=2 THEN 1 ELSE 0 END) AS repeat_customers,
 100.0*SUM(CASE WHEN orders>=2 THEN 1 ELSE 0 END)/NULLIF(COUNT_BIG(*),0) AS repeat_customer_pct
FROM customer_orders;
GO
SELECT product_match_reason,COUNT_BIG(*) AS sales_rows,SUM(sales_amount) AS sales_amount,
 SUM(quantity) AS quantity
FROM mart.fact_sales WHERE product_key=0 GROUP BY product_match_reason ORDER BY product_match_reason;
GO
-- LEFT JOIN and explicit labels retain unknown categories. No current-version filter.
SELECT CASE WHEN f.product_key=0 THEN N'Unknown historical category'
 ELSE COALESCE(p.category,N'Unspecified category') END AS category,
 COUNT_BIG(*) AS sales_rows,SUM(f.sales_amount) AS sales_amount
FROM mart.fact_sales f LEFT JOIN mart.dim_product p ON p.product_key=f.product_key
GROUP BY CASE WHEN f.product_key=0 THEN N'Unknown historical category' ELSE COALESCE(p.category,N'Unspecified category') END
ORDER BY sales_amount DESC;
GO
-- Country is CURRENT SCD1 customer country, not verified historical purchase location.
SELECT COALESCE(c.country,N'Unknown current country') AS current_customer_country,
 COUNT_BIG(*) AS sales_rows,SUM(f.sales_amount) AS sales_amount
FROM mart.fact_sales f LEFT JOIN mart.dim_customer c ON c.customer_key=f.customer_key
GROUP BY COALESCE(c.country,N'Unknown current country') ORDER BY sales_amount DESC;
GO
SELECT YEAR(source_order_date) AS order_year,MONTH(source_order_date) AS order_month,
 COUNT_BIG(*) AS sales_rows,COUNT(DISTINCT order_number) AS orders,SUM(sales_amount) AS sales_amount
FROM mart.fact_sales GROUP BY YEAR(source_order_date),MONTH(source_order_date)
ORDER BY order_year,order_month;
