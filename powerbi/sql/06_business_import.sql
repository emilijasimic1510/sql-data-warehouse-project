-- Read-only Import queries. Each batch is a SEPARATE Power Query query with the given name.
-- Do not paste GO into the SQL Server connector. No new SQL views or deployment required.

-- fact_sales: keep ALL rows, including product/customer/date key zero.
SELECT fact_key,order_number,customer_key,product_key,order_date_key,shipping_date_key,due_date_key,
 source_order_date,source_shipping_date,source_due_date,sales_amount,quantity,price,
 customer_match_reason,product_match_reason
FROM mart.fact_sales;
GO
-- dim_customer: no names, birthdates or free text needed for this product.
SELECT customer_key,customer_id,
 CASE WHEN customer_key=0 THEN N'Unknown customer'
      WHEN country IS NULL OR country=N'n/a' THEN N'Unknown current country'
      ELSE country END AS current_customer_country,
 gender,marital_status
FROM mart.dim_customer;
GO
-- dim_product: one row per version, not one row per product_number.
SELECT product_key,product_number,product_name,valid_from,valid_to,is_current,is_in_source,
 CASE WHEN product_key=0 THEN N'Unknown historical category'
      ELSE COALESCE(category,N'Unspecified category') END AS category_label,
 CASE WHEN product_key=0 THEN N'Unknown historical subcategory'
      ELSE COALESCE(subcategory,N'Unspecified subcategory') END AS subcategory_label,
 CASE WHEN product_key=0 THEN N'Unknown historical product'
      ELSE COALESCE(product_name,N'Unspecified product') END AS product_label
FROM mart.dim_product;
GO
-- dim_date: staging query only. Disable Enable load, then create Calendar from Calendar.m.
SELECT date_key,calendar_date FROM mart.dim_date;
