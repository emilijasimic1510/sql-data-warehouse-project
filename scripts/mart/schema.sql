-- Explicit deployment component; run through python -m mart_pipeline.deploy.
-- Existing objects are validated by the deployment wrapper, never dropped/rebuilt.
IF SCHEMA_ID(N'mart') IS NULL EXEC(N'CREATE SCHEMA mart');
CREATE TABLE mart.dim_customer (
 customer_key int IDENTITY(1,1) NOT NULL CONSTRAINT PK_mart_customer PRIMARY KEY,
 customer_id int NULL,
 customer_number nvarchar(50) NULL,
 first_name nvarchar(50) NULL,last_name nvarchar(50) NULL,country nvarchar(50) NULL,
 marital_status nvarchar(50) NULL,gender nvarchar(50) NULL,birthdate date NULL,create_date date NULL,
 is_in_source bit NOT NULL,
 CONSTRAINT CK_mart_customer_unknown CHECK ((customer_key=0 AND customer_id IS NULL AND is_in_source=0)
   OR (customer_key>0 AND customer_id IS NOT NULL))
);
CREATE UNIQUE INDEX UQ_mart_customer_business ON mart.dim_customer(customer_id) WHERE customer_id IS NOT NULL;
CREATE TABLE mart.dim_product (
 product_key int IDENTITY(1,1) NOT NULL CONSTRAINT PK_mart_product PRIMARY KEY,
 product_number nvarchar(50) NULL,source_product_id int NULL,
 product_name nvarchar(50) NULL,category_id nvarchar(50) NULL,category nvarchar(50) NULL,
 subcategory nvarchar(50) NULL,maintenance nvarchar(50) NULL,product_line nvarchar(50) NULL,cost decimal(19,2) NULL,
 valid_from date NULL,valid_to date NULL,is_current bit NOT NULL,is_in_source bit NOT NULL,
 CONSTRAINT CK_mart_product_unknown CHECK ((product_key=0 AND product_number IS NULL AND valid_from IS NULL
   AND valid_to IS NULL AND is_current=0 AND is_in_source=0) OR (product_key>0 AND product_number IS NOT NULL AND valid_from IS NOT NULL)),
 CONSTRAINT CK_mart_product_interval CHECK (valid_to IS NULL OR valid_to>=valid_from),
 CONSTRAINT CK_mart_product_current CHECK (is_current=CASE WHEN product_key>0 AND is_in_source=1 AND valid_to IS NULL THEN 1 ELSE 0 END)
);
CREATE UNIQUE INDEX UQ_mart_product_version ON mart.dim_product(product_number,valid_from) WHERE product_number IS NOT NULL;
CREATE UNIQUE INDEX UQ_mart_product_current ON mart.dim_product(product_number) WHERE is_current=1;
CREATE INDEX IX_mart_product_time ON mart.dim_product(product_number,valid_from,valid_to) INCLUDE(product_key,is_in_source);
CREATE TABLE mart.dim_date (
 date_key int NOT NULL CONSTRAINT PK_mart_date PRIMARY KEY,calendar_date date NULL,
 calendar_year smallint NULL,calendar_quarter tinyint NULL,calendar_month tinyint NULL,calendar_day tinyint NULL,
 CONSTRAINT CK_mart_date_values CHECK ((date_key=0 AND calendar_date IS NULL AND calendar_year IS NULL
  AND calendar_quarter IS NULL AND calendar_month IS NULL AND calendar_day IS NULL) OR
  (date_key>0 AND calendar_date IS NOT NULL AND calendar_year IS NOT NULL AND calendar_quarter IS NOT NULL
   AND calendar_month IS NOT NULL AND calendar_day IS NOT NULL AND date_key=CONVERT(int,CONVERT(char(8),calendar_date,112))
   AND calendar_year=YEAR(calendar_date) AND calendar_quarter=DATEPART(quarter,calendar_date)
   AND calendar_month=MONTH(calendar_date) AND calendar_day=DAY(calendar_date)))
);
CREATE UNIQUE INDEX UQ_mart_calendar_date ON mart.dim_date(calendar_date) WHERE calendar_date IS NOT NULL;
CREATE TABLE mart.fact_sales (
 fact_key bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_mart_fact PRIMARY KEY,
 order_number nvarchar(50) NOT NULL,source_customer_id int NULL,source_product_number nvarchar(50) NULL,
 customer_key int NOT NULL REFERENCES mart.dim_customer(customer_key),
 product_key int NOT NULL REFERENCES mart.dim_product(product_key),
 order_date_key int NOT NULL REFERENCES mart.dim_date(date_key),
 shipping_date_key int NOT NULL REFERENCES mart.dim_date(date_key),
 due_date_key int NOT NULL REFERENCES mart.dim_date(date_key),
 source_order_date date NULL,source_shipping_date date NULL,source_due_date date NULL,
 sales_amount decimal(19,2) NOT NULL,quantity bigint NOT NULL,price decimal(19,2) NOT NULL,
 customer_match_reason varchar(24) NOT NULL CHECK (customer_match_reason IN ('MATCHED','MISSING_CUSTOMER_KEY','NOT_IN_SOURCE')),
 product_match_reason varchar(24) NOT NULL CHECK (product_match_reason IN ('MATCHED','MISSING_ORDER_DATE','MISSING_PRODUCT_KEY','BEFORE_HISTORY','AFTER_HISTORY','INTERVAL_GAP')),
 CHECK ((customer_key=0 AND customer_match_reason<>'MATCHED') OR (customer_key>0 AND customer_match_reason='MATCHED')),
 CHECK ((product_key=0 AND product_match_reason<>'MATCHED') OR (product_key>0 AND product_match_reason='MATCHED')),
 CHECK (sales_amount>=0 AND quantity>=0 AND price>=0)
);
CREATE INDEX IX_mart_fact_product_date ON mart.fact_sales(product_key,order_date_key) INCLUDE(sales_amount,quantity);
CREATE INDEX IX_mart_fact_customer ON mart.fact_sales(customer_key,order_date_key) INCLUDE(sales_amount,quantity);
CREATE INDEX IX_mart_fact_order ON mart.fact_sales(order_number);
