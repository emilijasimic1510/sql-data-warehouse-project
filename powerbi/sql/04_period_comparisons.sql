USE DataWarehouse;
GO
-- Conservative coverage proxy: ONLY complete calendar months strictly inside the observed
-- order-date range, and a similarly eligible preceding month. This cannot prove source completeness.
WITH bounds AS (SELECT MIN(source_order_date) lo,MAX(source_order_date) hi FROM mart.fact_sales),
months AS (SELECT DATEFROMPARTS(calendar_year,calendar_month,1) period_start
 FROM mart.dim_date WHERE calendar_date IS NOT NULL GROUP BY calendar_year,calendar_month),
totals AS (SELECT m.period_start,COALESCE(SUM(f.sales_amount),0) amount
 FROM months m LEFT JOIN mart.fact_sales f ON f.source_order_date>=m.period_start
 AND f.source_order_date<DATEADD(month,1,m.period_start) GROUP BY m.period_start)
SELECT t.period_start,t.amount,p.amount AS previous_amount,
 CASE WHEN DATEADD(month,-1,t.period_start)>b.lo AND EOMONTH(t.period_start)<b.hi
 THEN (t.amount-p.amount)/NULLIF(p.amount,0) END AS mom_rate
FROM totals t LEFT JOIN totals p ON p.period_start=DATEADD(month,-1,t.period_start)
CROSS JOIN bounds b ORDER BY t.period_start;
GO
WITH bounds AS (SELECT MIN(source_order_date) lo,MAX(source_order_date) hi FROM mart.fact_sales),
years AS (SELECT DISTINCT calendar_year y FROM mart.dim_date WHERE calendar_date IS NOT NULL),
totals AS (SELECT y.y,COALESCE(SUM(f.sales_amount),0) amount FROM years y
 LEFT JOIN mart.fact_sales f ON YEAR(f.source_order_date)=y.y GROUP BY y.y)
SELECT t.y,t.amount,p.amount AS previous_amount,
 CASE WHEN DATEFROMPARTS(t.y-1,1,1)>b.lo AND DATEFROMPARTS(t.y,12,31)<b.hi
 THEN (t.amount-p.amount)/NULLIF(p.amount,0) END AS yoy_rate
FROM totals t LEFT JOIN totals p ON p.y=t.y-1 CROSS JOIN bounds b ORDER BY t.y;
