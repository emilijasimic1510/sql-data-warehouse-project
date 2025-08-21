/*===============================================================================
Quality Checks (aligned to current Silver/Gold naming)
===============================================================================
- Check uniqueness of surrogate keys in dimension tables
- Check referential integrity between fact and dimension tables
- Additional validations of critical columns (NULLs, duplicate business keys)
===============================================================================*/

-----------------------------
-- gold.dim_customers
-----------------------------
-- 1) Uniqueness of surrogate key (customer_key)  => EXPECTED: 0 rows
SELECT 
    customer_key,
    COUNT(*) AS duplicate_count
FROM gold.dim_customers
GROUP BY customer_key
HAVING COUNT(*) > 1;

-- 2) (Optional) Uniqueness of natural key (customer_id)  => EXPECTED: 0 rows
SELECT 
    customer_id,
    COUNT(*) AS duplicate_count
FROM gold.dim_customers
GROUP BY customer_id
HAVING COUNT(*) > 1;

-- 3) (Data hygiene) Critical columns should not be NULL  => EXPECTED: 0 rows
SELECT *
FROM gold.dim_customers
WHERE customer_key IS NULL
   OR customer_id  IS NULL
   OR customer_number IS NULL;


-----------------------------
-- gold.dim_products
-----------------------------
-- 4) Uniqueness of surrogate key (product_key)  => EXPECTED: 0 rows
SELECT 
    product_key,
    COUNT(*) AS duplicate_count
FROM gold.dim_products
GROUP BY product_key
HAVING COUNT(*) > 1;

-- 5) (Optional) Uniqueness of business key (product_number)  => EXPECTED: 0 rows
SELECT 
    product_number,
    COUNT(*) AS duplicate_count
FROM gold.dim_products
GROUP BY product_number
HAVING COUNT(*) > 1;

-- 6) (Data hygiene) Critical columns should not be NULL  => EXPECTED: 0 rows
SELECT *
FROM gold.dim_products
WHERE product_key    IS NULL
   OR product_number IS NULL
   OR product_id     IS NULL;


-----------------------------
-- gold.fact_sales
-----------------------------
-- 7) Fact → Dimension relationship check (customer surrogate key)  => EXPECTED: 0 rows
SELECT f.*
FROM gold.fact_sales AS f
LEFT JOIN gold.dim_customers AS c
       ON c.customer_key = f.customer_key
WHERE c.customer_key IS NULL;

-- 8) Fact → Dimension relationship check (product surrogate key)  => EXPECTED: 0 rows
SELECT f.*
FROM gold.fact_sales AS f
LEFT JOIN gold.dim_products AS p
       ON p.product_key = f.product_key
WHERE p.product_key IS NULL;

-- 9) (Data hygiene) NULLs in fact table critical columns  => EXPECTED: 0 rows
SELECT *
FROM gold.fact_sales
WHERE order_number IS NULL
   OR customer_key IS NULL
   OR product_key  IS NULL;

-- 10) (Business logic) Date consistency checks (shipping and due date)  => EXPECTED: 0 rows
SELECT *
FROM gold.fact_sales
WHERE shipping_date < order_date
   OR due_date      < order_date;

-- 11) (Business logic) No negative values allowed  => EXPECTED: 0 rows
SELECT *
FROM gold.fact_sales
WHERE sales_amount < 0
   OR quantity     < 0
   OR price        < 0;
