# Report model reference

This is the reference model for the full Sales Performance & Data Reliability report. The checked-in PBIP currently contains the core business model, additional automatic date tables, and a subset of the measures. Audit tables and the full relationship configuration below are extension specifications.

Use the separate SELECT blocks in [business imports](sql/06_business_import.sql) and [audit imports](sql/05_audit_import.sql).

## Table grain

| Table | One row represents |
| --- | --- |
| `fact_sales` | One Silver sales record, preserving multiplicity |
| `dim_customer` | One customer, plus unknown key 0; current SCD Type 1 attributes |
| `dim_product` | One source product version, plus unknown key 0 |
| `dim_date` | One SQL calendar date, plus unknown; Power Query staging only |
| `Calendar` | One non-NULL date, extended to full calendar years |
| `audit_families` | One root run |
| `audit_runs` | One parent or child run |
| `audit_steps` | One `(run_id, ordinal)` |
| `audit_quality` | One `(run_id, check_id)`; warehouse checks |
| `audit_snapshot` | One disconnected operational summary |

Keys and quantity use Whole number, amounts use Fixed decimal number, source dates use Date, audit timestamps use Date/Time, and UUIDs use Text. Hide technical keys and use explicit measures for totals.

## Reference relationships

All relationships are one-to-many with single-direction filtering from the dimension or parent table.

| One side | Many side | Active |
| --- | --- | --- |
| `dim_customer.customer_key` | `fact_sales.customer_key` | Yes |
| `dim_product.product_key` | `fact_sales.product_key` | Yes |
| `Calendar.Date` | `fact_sales.source_order_date` | Yes |
| `Calendar.Date` | `fact_sales.source_shipping_date` | No |
| `Calendar.Date` | `fact_sales.source_due_date` | No |
| `audit_families.family_id` | `audit_runs.family_id` | Yes |
| `audit_runs.run_id` | `audit_steps.run_id` | Yes |
| `audit_runs.run_id` | `audit_quality.run_id` | Yes |

Keep audit disconnected from sales and Calendar. Do not filter products to `is_current=1`: that removes historical versions and unknown sales. `product_number` repeats across versions; the unique key is `product_key`.

## Dates and missing history

Build [Calendar](Calendar.m) from `dim_date`, mark `Calendar.Date` as the date column, and sort Month by Month Number. The SQL date dimension cannot serve directly as a marked date table because its unknown member has a NULL date. Disable automatic date/time in the report when adopting this calendar configuration.

Undated sales retain NULL source dates. Unfiltered sales totals include them, while date trends exclude them. Display **Sales Without Order Date** and **Sales Amount Without Order Date** with an "All dates / undated" label: these measures ignore Calendar but retain customer/product filters.

Some orders have both dated and undated lines. Orders are distinct within the current context, so totals across date or product groups cannot be added together. Unknown product sales stay in the fact table without assigning a current category or cost.

## Audit interpretation

Operational cards use disconnected `audit_snapshot`. Do not join quality or step rows to sales, or sum overlapping anomaly counts.

Last Confirmed Mart Completion UTC is the last successful mart child's completion time, a publication proxy rather than an exact commit timestamp. A later parent failure does not undo that child commit. Standalone mart runs and interrupted audit writes may not have a corresponding successful audit record. RUNNING does not prove that a process is still active.

BI Refresh Observed UTC records the import query time. It is separate from source event dates and warehouse load times. Label all operational timestamps as UTC.

## Validation

Compare the report against [KPI SQL](sql/01_kpis.sql) and [reconciliation SQL](sql/03_reconciliation.sql):

1. Check unfiltered totals, including unknown-product and undated amounts.
2. Apply a year, category, and country selection and repeat the same filters in SQL.
3. Confirm repeat customers are recalculated within the selection and distinct totals are not sums of groups.
4. Check that partial and boundary-period comparisons return BLANK, labelled "Not comparable".
5. Confirm audit cards do not change under business slicers, and the latest failed attempt is not hidden by an older success.

These are validation steps for Desktop; the presence of the reference files does not establish that all measures or pages have been implemented and refreshed.
