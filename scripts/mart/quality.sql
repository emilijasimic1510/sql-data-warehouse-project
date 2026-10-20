CREATE OR ALTER PROCEDURE mart.check_quality AS
BEGIN
 SET NOCOUNT ON;
 DECLARE @q TABLE(check_id varchar(10) PRIMARY KEY,severity varchar(7),description nvarchar(200),anomaly_count bigint,metric_value nvarchar(100));
 INSERT @q SELECT 'M01','ERROR','Dimension primary keys and business version keys must be unique',
  (SELECT COUNT_BIG(*) FROM(SELECT customer_key k FROM mart.dim_customer GROUP BY customer_key HAVING COUNT_BIG(*)>1) a)+
  (SELECT COUNT_BIG(*) FROM(SELECT customer_id k FROM mart.dim_customer WHERE customer_key>0 GROUP BY customer_id HAVING COUNT_BIG(*)>1) b)+
  (SELECT COUNT_BIG(*) FROM(SELECT product_key k FROM mart.dim_product GROUP BY product_key HAVING COUNT_BIG(*)>1) c)+
  (SELECT COUNT_BIG(*) FROM(SELECT product_number,valid_from FROM mart.dim_product WHERE product_key>0 GROUP BY product_number,valid_from HAVING COUNT_BIG(*)>1) d)+
  (SELECT COUNT_BIG(*) FROM(SELECT date_key k FROM mart.dim_date GROUP BY date_key HAVING COUNT_BIG(*)>1) e)+
  (SELECT COUNT_BIG(*) FROM(SELECT fact_key k FROM mart.fact_sales GROUP BY fact_key HAVING COUNT_BIG(*)>1) f),NULL;
 INSERT @q SELECT 'M02','ERROR','Every fact FK must resolve',COUNT_BIG(*),NULL FROM mart.fact_sales f
  LEFT JOIN mart.dim_customer c ON c.customer_key=f.customer_key LEFT JOIN mart.dim_product p ON p.product_key=f.product_key
  LEFT JOIN mart.dim_date od ON od.date_key=f.order_date_key LEFT JOIN mart.dim_date sd ON sd.date_key=f.shipping_date_key
  LEFT JOIN mart.dim_date dd ON dd.date_key=f.due_date_key
  WHERE c.customer_key IS NULL OR p.product_key IS NULL OR od.date_key IS NULL OR sd.date_key IS NULL OR dd.date_key IS NULL;
 INSERT @q SELECT 'M03','ERROR','Present product intervals must not overlap',COUNT_BIG(*),NULL
  FROM mart.dim_product a JOIN mart.dim_product b ON a.product_number=b.product_number AND a.product_key<b.product_key
  WHERE a.is_in_source=1 AND b.is_in_source=1 AND a.valid_from<=COALESCE(b.valid_to,CONVERT(date,'99991231'))
    AND b.valid_from<=COALESCE(a.valid_to,CONVERT(date,'99991231'));
 INSERT @q SELECT 'M04','ERROR','Valid intervals and one open current version per product',
  (SELECT COUNT_BIG(*) FROM mart.dim_product WHERE valid_to<valid_from OR
     is_current<>CASE WHEN product_key>0 AND is_in_source=1 AND valid_to IS NULL THEN 1 ELSE 0 END)+
  (SELECT COUNT_BIG(*) FROM(SELECT product_number FROM mart.dim_product WHERE is_current=1 GROUP BY product_number HAVING COUNT_BIG(*)>1) x),NULL;
 INSERT @q SELECT 'M05','ERROR','Known fact product must match business key and inclusive order-date interval',COUNT_BIG(*),NULL
  FROM mart.fact_sales f JOIN mart.dim_product p ON p.product_key=f.product_key
  WHERE f.product_key>0 AND (p.is_in_source=0 OR f.source_product_number IS NULL OR p.product_number<>f.source_product_number
   OR f.source_order_date IS NULL OR f.source_order_date<p.valid_from OR f.source_order_date>p.valid_to);
 INSERT @q SELECT 'M06','ERROR','Known customer must match source business key',COUNT_BIG(*),NULL
  FROM mart.fact_sales f JOIN mart.dim_customer c ON c.customer_key=f.customer_key
  WHERE f.customer_key>0 AND (c.is_in_source=0 OR f.source_customer_id IS NULL OR c.customer_id<>f.source_customer_id);
 INSERT @q SELECT 'M07','ERROR','Role date keys must exactly preserve source dates; NULL uses key zero',COUNT_BIG(*),NULL
  FROM mart.fact_sales f JOIN mart.dim_date od ON od.date_key=f.order_date_key
  JOIN mart.dim_date sd ON sd.date_key=f.shipping_date_key JOIN mart.dim_date dd ON dd.date_key=f.due_date_key
  WHERE (f.source_order_date IS NULL AND f.order_date_key<>0) OR (f.source_order_date IS NOT NULL AND (od.calendar_date IS NULL OR od.calendar_date<>f.source_order_date))
   OR (f.source_shipping_date IS NULL AND f.shipping_date_key<>0) OR (f.source_shipping_date IS NOT NULL AND (sd.calendar_date IS NULL OR sd.calendar_date<>f.source_shipping_date))
   OR (f.source_due_date IS NULL AND f.due_date_key<>0) OR (f.source_due_date IS NOT NULL AND (dd.calendar_date IS NULL OR dd.calendar_date<>f.source_due_date));
 INSERT @q SELECT 'M08','ERROR','Unknown mapping is allowed only when no valid member exists',COUNT_BIG(*),NULL
  FROM mart.fact_sales f WHERE
   (f.product_key=0 AND EXISTS(SELECT 1 FROM mart.dim_product p WHERE p.is_in_source=1 AND p.product_number=f.source_product_number
      AND f.source_order_date>=p.valid_from AND (p.valid_to IS NULL OR f.source_order_date<=p.valid_to)))
   OR (f.customer_key=0 AND EXISTS(SELECT 1 FROM mart.dim_customer c WHERE c.is_in_source=1 AND c.customer_id=f.source_customer_id));
 INSERT @q SELECT 'M09','ERROR','Fact row count equals Silver count',
  CASE WHEN (SELECT COUNT_BIG(*) FROM mart.fact_sales)=(SELECT COUNT_BIG(*) FROM silver.crm_sales_info) THEN 0 ELSE 1 END,NULL;
 INSERT @q SELECT 'M10','ERROR','Fact total quantity equals Silver',
  CASE WHEN COALESCE((SELECT SUM(CAST(quantity AS decimal(38,0))) FROM mart.fact_sales),0)=
     COALESCE((SELECT SUM(CAST(sls_quantity AS decimal(38,0))) FROM silver.crm_sales_info),0) THEN 0 ELSE 1 END,NULL;
 INSERT @q SELECT 'M11','ERROR','Fact total amount equals Silver',
  CASE WHEN COALESCE((SELECT SUM(CAST(sales_amount AS decimal(38,2))) FROM mart.fact_sales),0)=
     COALESCE((SELECT SUM(CAST(sls_sales AS decimal(38,2))) FROM silver.crm_sales_info),0) THEN 0 ELSE 1 END,NULL;
 -- Grouped full business-row EXCEPT in both directions retains and compares multiplicity.
 ;WITH source_rows AS(SELECT sls_ord_num,sls_cust_id,sls_prd_key,sls_order_dt,sls_ship_dt,sls_due_dt,
   CAST(sls_sales AS decimal(19,2)) amount,CAST(sls_quantity AS bigint) quantity,CAST(sls_price AS decimal(19,2)) price,COUNT_BIG(*) n
   FROM silver.crm_sales_info GROUP BY sls_ord_num,sls_cust_id,sls_prd_key,sls_order_dt,sls_ship_dt,sls_due_dt,sls_sales,sls_quantity,sls_price),
 mart_rows AS(SELECT order_number,source_customer_id,source_product_number,source_order_date,source_shipping_date,source_due_date,
   sales_amount,quantity,price,COUNT_BIG(*) n FROM mart.fact_sales
   GROUP BY order_number,source_customer_id,source_product_number,source_order_date,source_shipping_date,source_due_date,sales_amount,quantity,price),
 difference AS(SELECT * FROM (SELECT * FROM source_rows EXCEPT SELECT * FROM mart_rows) a
  UNION ALL SELECT * FROM (SELECT * FROM mart_rows EXCEPT SELECT * FROM source_rows) b)
 INSERT @q SELECT 'M12','ERROR','Complete source business-row multisets must match including duplicate multiplicity',COUNT_BIG(*),NULL FROM difference;
 INSERT @q SELECT 'M13','ERROR','Unknown members exist in all dimensions',
  CASE WHEN EXISTS(SELECT 1 FROM mart.dim_customer WHERE customer_key=0) AND EXISTS(SELECT 1 FROM mart.dim_product WHERE product_key=0)
   AND EXISTS(SELECT 1 FROM mart.dim_date WHERE date_key=0 AND calendar_date IS NULL) THEN 0 ELSE 1 END,NULL;
 INSERT @q SELECT 'M14','ERROR','In-source customer and product counts reconcile with Silver',
  CASE WHEN (SELECT COUNT_BIG(*) FROM mart.dim_customer WHERE is_in_source=1)=(SELECT COUNT_BIG(*) FROM silver.crm_cust_info)
    AND (SELECT COUNT_BIG(*) FROM mart.dim_product WHERE is_in_source=1)=(SELECT COUNT_BIG(*) FROM silver.crm_product_info) THEN 0 ELSE 1 END,NULL;
 INSERT @q SELECT 'U01','WARNING','Unknown customer links',COUNT_BIG(*),NULL FROM mart.fact_sales WHERE customer_key=0;
 INSERT @q SELECT 'U02','WARNING','Unknown product: missing order date',COUNT_BIG(*),NULL FROM mart.fact_sales WHERE product_match_reason='MISSING_ORDER_DATE';
 INSERT @q SELECT 'U03','WARNING','Unknown product: missing product business key',COUNT_BIG(*),NULL FROM mart.fact_sales WHERE product_match_reason='MISSING_PRODUCT_KEY';
 INSERT @q SELECT 'U04','WARNING','Unknown product: before source history',COUNT_BIG(*),NULL FROM mart.fact_sales WHERE product_match_reason='BEFORE_HISTORY';
 INSERT @q SELECT 'U05','WARNING','Unknown product: after closed source history',COUNT_BIG(*),NULL FROM mart.fact_sales WHERE product_match_reason='AFTER_HISTORY';
 INSERT @q SELECT 'U06','WARNING','Unknown product: gap in source history',COUNT_BIG(*),NULL FROM mart.fact_sales WHERE product_match_reason='INTERVAL_GAP';
 INSERT @q SELECT 'U07','WARNING','Unknown order date',COUNT_BIG(*),NULL FROM mart.fact_sales WHERE order_date_key=0;
 INSERT @q SELECT 'U08','WARNING','Unknown shipping date',COUNT_BIG(*),NULL FROM mart.fact_sales WHERE shipping_date_key=0;
 INSERT @q SELECT 'U09','WARNING','Unknown due date',COUNT_BIG(*),NULL FROM mart.fact_sales WHERE due_date_key=0;
 INSERT @q SELECT 'R01','WARNING','Fact quantity metric; no error threshold',NULL,CONVERT(nvarchar(100),COALESCE(SUM(CAST(quantity AS decimal(38,0))),0)) FROM mart.fact_sales;
 INSERT @q SELECT 'R02','WARNING','Fact amount metric; no error threshold',NULL,CONVERT(nvarchar(100),COALESCE(SUM(CAST(sales_amount AS decimal(38,2))),0)) FROM mart.fact_sales;
 SELECT check_id,severity,description,anomaly_count,metric_value FROM @q ORDER BY check_id;
END;
