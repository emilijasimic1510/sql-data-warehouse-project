/*===============================================================================
DDL Script: Create Gold Views (aligned to provided Silver tables)
===============================================================================*/

-- (Optional) ensure schema exists
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'gold')
    EXEC('CREATE SCHEMA gold');
GO

/* =============================================================================
   Dimension: gold.dim_customers
   - Izvori: silver.crm_cust_info + silver.erp_customer_info + silver.erp_location_info
   ============================================================================= */
IF OBJECT_ID('gold.dim_customers', 'V') IS NOT NULL
    DROP VIEW gold.dim_customers;
GO

CREATE VIEW gold.dim_customers AS
SELECT
    ROW_NUMBER() OVER (ORDER BY ci.cst_id)              AS customer_key,      -- surrogate key
    ci.cst_id                                           AS customer_id,       -- natural key (CRM)
    ci.cst_key                                          AS customer_number,   -- alternativni ključ (CRM)
    ci.cst_firstname                                    AS first_name,
    ci.cst_lastname                                     AS last_name,
    la.cntry                                            AS country,
    ci.cst_marital_status                               AS marital_status,
    CASE 
        WHEN ci.cst_gndr <> 'n/a' THEN ci.cst_gndr      -- primarni izvor: CRM
        ELSE COALESCE(ca.gen, 'n/a')                    -- fallback: ERP
    END                                                 AS gender,
    ca.bdate                                            AS birthdate,
    ci.cst_create_date                                  AS create_date
FROM silver.crm_cust_info       AS ci
LEFT JOIN silver.erp_customer_info AS ca
       ON ci.cst_key = ca.cid
LEFT JOIN silver.erp_location_info AS la
       ON ci.cst_key = la.cid;
GO


/* =============================================================================
   Dimension: gold.dim_products
   - Izvori: silver.crm_product_info + silver.erp_product_category
   - Filtrira aktivne proizvode (prd_end_dt IS NULL)
   ============================================================================= */
IF OBJECT_ID('gold.dim_products', 'V') IS NOT NULL
    DROP VIEW gold.dim_products;
GO

CREATE VIEW gold.dim_products AS
SELECT
    ROW_NUMBER() OVER (ORDER BY pn.prd_start_dt, pn.prd_key) AS product_key,  -- surrogate key
    pn.prd_id         AS product_id,
    pn.prd_key        AS product_number,
    pn.prd_nm         AS product_name,
    pn.cat_id         AS category_id,
    pc.cat            AS category,
    pc.subcat         AS subcategory,
    pc.maintenance    AS maintenance,
    pn.prd_cost       AS cost,
    pn.prd_line       AS product_line,
    pn.prd_start_dt   AS start_date
FROM silver.crm_product_info      AS pn
LEFT JOIN silver.erp_product_category AS pc
       ON pn.cat_id = pc.id
WHERE pn.prd_end_dt IS NULL;  -- isključi istorijske/redove sa krajem važnosti
GO


/* =============================================================================
   Fact: gold.fact_sales
   - Izvor: silver.crm_sales_info
   - Dimensional joins: gold.dim_products (po product_number) i gold.dim_customers (po customer_id)
   ============================================================================= */
IF OBJECT_ID('gold.fact_sales', 'V') IS NOT NULL
    DROP VIEW gold.fact_sales;
GO

CREATE VIEW gold.fact_sales AS
SELECT
    sd.sls_ord_num     AS order_number,
    pr.product_key     AS product_key,
    cu.customer_key    AS customer_key,
    sd.sls_order_dt    AS order_date,
    sd.sls_ship_dt     AS shipping_date,
    sd.sls_due_dt      AS due_date,
    sd.sls_sales       AS sales_amount,
    sd.sls_quantity    AS quantity,
    sd.sls_price       AS price
FROM silver.crm_sales_info AS sd
LEFT JOIN gold.dim_products  AS pr
       ON sd.sls_prd_key = pr.product_number
LEFT JOIN gold.dim_customers AS cu
       ON sd.sls_cust_id = cu.customer_id;
GO
