CREATE OR ALTER PROCEDURE mart.load_model AS
BEGIN
 SET NOCOUNT ON; SET XACT_ABORT ON;
 BEGIN TRY
  IF @@TRANCOUNT<>1 OR XACT_STATE()<>1 THROW 51200,'One caller-owned transaction required',1;
  DECLARE @lock int;
  EXEC @lock=sys.sp_getapplock @Resource=N'mart.loader.v1',@LockMode='Exclusive',@LockOwner='Transaction',@LockTimeout=10000;
  IF @lock<0 THROW 51201,'Mart lock unavailable',1;
  -- HOLDLOCKs persist until caller commit. Source capture never changes Silver.
  SELECT * INTO #crm FROM silver.crm_cust_info WITH(HOLDLOCK);
  SELECT * INTO #erp FROM silver.erp_customer_info WITH(HOLDLOCK);
  SELECT * INTO #location FROM silver.erp_location_info WITH(HOLDLOCK);
  SELECT * INTO #category FROM silver.erp_product_category WITH(HOLDLOCK);
  SELECT * INTO #products FROM silver.crm_product_info WITH(HOLDLOCK);
  SELECT * INTO #sales FROM silver.crm_sales_info WITH(HOLDLOCK);
  IF EXISTS(SELECT cst_id FROM #crm GROUP BY cst_id HAVING cst_id IS NULL OR COUNT_BIG(*)>1)
   OR EXISTS(SELECT 1 FROM #crm WHERE cst_key IS NULL)
   THROW 51210,'Invalid customer business keys',1;
  IF EXISTS(SELECT cid FROM #erp GROUP BY cid HAVING COUNT_BIG(*)>1)
   OR EXISTS(SELECT cid FROM #location GROUP BY cid HAVING COUNT_BIG(*)>1)
   OR EXISTS(SELECT id FROM #category GROUP BY id HAVING COUNT_BIG(*)>1)
   THROW 51211,'Ambiguous enrichment joins',1;
  IF EXISTS(SELECT prd_key,prd_start_dt FROM #products GROUP BY prd_key,prd_start_dt
             HAVING prd_key IS NULL OR prd_start_dt IS NULL OR COUNT_BIG(*)>1)
   OR EXISTS(SELECT 1 FROM #products WHERE prd_end_dt<prd_start_dt)
   THROW 51212,'Invalid product version keys or intervals',1;
  IF EXISTS(SELECT 1 FROM #products a JOIN #products b ON a.prd_key=b.prd_key AND a.prd_start_dt<b.prd_start_dt
             WHERE b.prd_start_dt<=COALESCE(a.prd_end_dt,CONVERT(date,'99991231')))
   THROW 51213,'Overlapping product versions',1;
  IF EXISTS(SELECT 1 FROM #sales WHERE sls_ord_num IS NULL OR sls_sales IS NULL OR sls_quantity IS NULL
             OR sls_price IS NULL OR sls_sales<0 OR sls_quantity<0 OR sls_price<0)
   THROW 51214,'Invalid fact measures or order number',1;

  IF NOT EXISTS(SELECT 1 FROM mart.dim_customer WHERE customer_key=0)
  BEGIN
   SET IDENTITY_INSERT mart.dim_customer ON;
   INSERT mart.dim_customer(customer_key,customer_id,customer_number,is_in_source) VALUES(0,NULL,N'Unknown',0);
   SET IDENTITY_INSERT mart.dim_customer OFF;
  END;
  IF NOT EXISTS(SELECT 1 FROM mart.dim_product WHERE product_key=0)
  BEGIN
   SET IDENTITY_INSERT mart.dim_product ON;
   INSERT mart.dim_product(product_key,product_number,product_name,is_current,is_in_source) VALUES(0,NULL,N'Unknown',0,0);
   SET IDENTITY_INSERT mart.dim_product OFF;
  END;
  IF NOT EXISTS(SELECT 1 FROM mart.dim_date WHERE date_key=0) INSERT mart.dim_date(date_key) VALUES(0);

  SELECT c.cst_id customer_id,c.cst_key customer_number,c.cst_firstname first_name,c.cst_lastname last_name,
    l.cntry country,c.cst_marital_status marital_status,
    CASE WHEN c.cst_gndr<>'n/a' THEN c.cst_gndr ELSE COALESCE(e.gen,'n/a') END gender,
    e.bdate birthdate,c.cst_create_date create_date INTO #customer_source
  FROM #crm c LEFT JOIN #erp e ON e.cid=c.cst_key LEFT JOIN #location l ON l.cid=c.cst_key;
  UPDATE mart.dim_customer SET is_in_source=0 WHERE customer_key>0;
  UPDATE d SET customer_number=s.customer_number,first_name=s.first_name,last_name=s.last_name,country=s.country,
    marital_status=s.marital_status,gender=s.gender,birthdate=s.birthdate,create_date=s.create_date,is_in_source=1
  FROM mart.dim_customer d JOIN #customer_source s ON s.customer_id=d.customer_id;
  INSERT mart.dim_customer(customer_id,customer_number,first_name,last_name,country,marital_status,gender,birthdate,create_date,is_in_source)
   SELECT s.customer_id,s.customer_number,s.first_name,s.last_name,s.country,s.marital_status,s.gender,s.birthdate,s.create_date,1
   FROM #customer_source s WHERE NOT EXISTS(SELECT 1 FROM mart.dim_customer d WHERE d.customer_id=s.customer_id);

  SELECT p.prd_key product_number,p.prd_id source_product_id,p.prd_nm product_name,p.cat_id category_id,
   c.cat category,c.subcat subcategory,c.maintenance,p.prd_line product_line,CAST(p.prd_cost AS decimal(19,2)) cost,
   p.prd_start_dt valid_from,p.prd_end_dt valid_to INTO #product_source
  FROM #products p LEFT JOIN #category c ON c.id=p.cat_id;
  UPDATE mart.dim_product SET is_in_source=0,is_current=0 WHERE product_key>0;
  UPDATE d SET source_product_id=s.source_product_id,product_name=s.product_name,category_id=s.category_id,
   category=s.category,subcategory=s.subcategory,maintenance=s.maintenance,product_line=s.product_line,cost=s.cost,
   valid_to=s.valid_to,is_current=CASE WHEN s.valid_to IS NULL THEN 1 ELSE 0 END,is_in_source=1
  FROM mart.dim_product d JOIN #product_source s ON s.product_number=d.product_number AND s.valid_from=d.valid_from;
  INSERT mart.dim_product(product_number,source_product_id,product_name,category_id,category,subcategory,maintenance,product_line,cost,
    valid_from,valid_to,is_current,is_in_source)
   SELECT s.product_number,s.source_product_id,s.product_name,s.category_id,s.category,s.subcategory,s.maintenance,s.product_line,s.cost,
     s.valid_from,s.valid_to,CASE WHEN s.valid_to IS NULL THEN 1 ELSE 0 END,1
   FROM #product_source s WHERE NOT EXISTS(SELECT 1 FROM mart.dim_product d WHERE d.product_number=s.product_number AND d.valid_from=s.valid_from);

  DECLARE @min_date date,@max_date date;
  SELECT @min_date=MIN(d),@max_date=MAX(d) FROM
   (SELECT sls_order_dt d FROM #sales UNION ALL SELECT sls_ship_dt FROM #sales UNION ALL SELECT sls_due_dt FROM #sales) x;
  IF @min_date IS NOT NULL
  BEGIN
   ;WITH dates AS(SELECT @min_date d UNION ALL SELECT DATEADD(day,1,d) FROM dates WHERE d<@max_date)
   INSERT mart.dim_date(date_key,calendar_date,calendar_year,calendar_quarter,calendar_month,calendar_day)
    SELECT CONVERT(int,CONVERT(char(8),d,112)),d,YEAR(d),DATEPART(quarter,d),MONTH(d),DAY(d)
    FROM dates WHERE NOT EXISTS(SELECT 1 FROM mart.dim_date m WHERE m.calendar_date=dates.d) OPTION(MAXRECURSION 0);
  END;

  DELETE FROM mart.fact_sales; -- no identity reseed; fact identity is NOT a stable source line ID
  INSERT mart.fact_sales(order_number,source_customer_id,source_product_number,customer_key,product_key,
   order_date_key,shipping_date_key,due_date_key,source_order_date,source_shipping_date,source_due_date,
   sales_amount,quantity,price,customer_match_reason,product_match_reason)
   SELECT s.sls_ord_num,s.sls_cust_id,s.sls_prd_key,COALESCE(c.customer_key,0),COALESCE(p.product_key,0),
    COALESCE(od.date_key,0),COALESCE(sd.date_key,0),COALESCE(dd.date_key,0),s.sls_order_dt,s.sls_ship_dt,s.sls_due_dt,
    CAST(s.sls_sales AS decimal(19,2)),CAST(s.sls_quantity AS bigint),CAST(s.sls_price AS decimal(19,2)),
    CASE WHEN c.customer_key IS NOT NULL THEN 'MATCHED' WHEN s.sls_cust_id IS NULL THEN 'MISSING_CUSTOMER_KEY' ELSE 'NOT_IN_SOURCE' END,
    CASE WHEN p.product_key IS NOT NULL THEN 'MATCHED' WHEN s.sls_order_dt IS NULL THEN 'MISSING_ORDER_DATE'
     WHEN bounds.first_date IS NULL THEN 'MISSING_PRODUCT_KEY' WHEN s.sls_order_dt<bounds.first_date THEN 'BEFORE_HISTORY'
     WHEN bounds.open_versions=0 AND s.sls_order_dt>bounds.last_date THEN 'AFTER_HISTORY' ELSE 'INTERVAL_GAP' END
   FROM #sales s
   LEFT JOIN mart.dim_customer c ON c.customer_id=s.sls_cust_id AND c.is_in_source=1
   LEFT JOIN mart.dim_product p ON p.product_number=s.sls_prd_key AND p.is_in_source=1
      AND s.sls_order_dt>=p.valid_from AND (p.valid_to IS NULL OR s.sls_order_dt<=p.valid_to)
   LEFT JOIN mart.dim_date od ON od.calendar_date=s.sls_order_dt
   LEFT JOIN mart.dim_date sd ON sd.calendar_date=s.sls_ship_dt
   LEFT JOIN mart.dim_date dd ON dd.calendar_date=s.sls_due_dt
   OUTER APPLY(SELECT MIN(valid_from) first_date,MAX(valid_to) last_date,
                     SUM(CASE WHEN valid_to IS NULL THEN 1 ELSE 0 END) open_versions
    FROM mart.dim_product b WHERE b.product_number=s.sls_prd_key AND b.is_in_source=1) bounds;
 END TRY
 BEGIN CATCH
  IF XACT_STATE()<>0 ROLLBACK TRANSACTION;
  THROW;
 END CATCH
END;
