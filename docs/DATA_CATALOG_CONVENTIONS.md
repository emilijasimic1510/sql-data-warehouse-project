# Naming conventions

The Gold data catalog is maintained in [DATA_CATALOG_GOLD.md](DATA_CATALOG_GOLD.md).
This file documents naming instead of duplicating that catalog.

- Schemas: `bronze` (source data), `silver` (cleaned data), `gold` (analytical views).
- Bronze/Silver tables use the source prefix: `crm_` or `erp_`.
- Source column names are retained where possible; Silver adds derived columns and `dwh_create_date`.
- Procedures: `bronze.load_bronze` and `silver.load_silver`.
- Gold dimensions: `gold.dim_customers`, `gold.dim_products`; sales view: `gold.fact_sales`.
- `ddl_*.sql` defines tables/views; `load_*.sql` defines procedures only.
- Dataset filenames keep their original spelling and case. The directory is `datasets`, without a trailing space.
- SQL identifiers use snake_case. Use schema-qualified names in queries.
