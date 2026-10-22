# Naming conventions

The Gold data catalog is maintained in [DATA_CATALOG_GOLD.md](DATA_CATALOG_GOLD.md).

- Schemas: `bronze` (source data), `silver` (cleaned data), `gold` (analytical views), `mart` (physical analytical tables), `audit` (run records), and `crm_incremental` (isolated demo).
- Bronze/Silver tables use the source prefix: `crm_` or `erp_`.
- Source column names are retained where possible; Silver adds derived columns and `dwh_create_date`.
- Procedures: `bronze.load_bronze` and `silver.load_silver`.
- Gold dimensions: `gold.dim_customers`, `gold.dim_products`; sales view: `gold.fact_sales`.
- `ddl_*.sql` defines tables/views; `load_*.sql` defines procedures only.
- Dataset filenames keep their original spelling and case under `datasets`.
- SQL identifiers use snake_case. Use schema-qualified names in queries.
- Mart dimensions use singular names: `dim_customer`, `dim_product`, and `dim_date`; the fact table is `fact_sales`.
