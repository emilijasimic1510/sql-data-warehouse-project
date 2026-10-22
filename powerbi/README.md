# Sales Performance

Open [Sales Performance.pbix](Sales%20Performance.pbix) in Power BI Desktop, or use [Sales Performance.pbip](Sales%20Performance.pbip) with its report and semantic-model folders for source-based editing.

The checked-in model includes sales, customer and product tables, a Calendar, and core sales measures. The SQL queries and DAX file below also describe a broader four-page report with audit metrics. Those reference definitions are not all present in the saved model; compare the model before adding them.

## Connect and refresh

Use the existing `DataWarehouse` database and its `mart` schema. Set the SQL Server source to your instance in Power BI's data source settings and use the appropriate credentials. The saved project currently references the development SQL instance.

Refresh when no warehouse writer is active. Importing several tables does not guarantee one SQL snapshot; if reconciliation differs or a load overlaps the refresh, wait for the load to finish and refresh again. Reading existing data does not require another E2E load.

## Reference files

| File | Purpose |
| --- | --- |
| [MODEL.md](MODEL.md) | Table grain, reference relationships, date handling, and validation |
| [KPI_DICTIONARY.md](KPI_DICTIONARY.md) | Measure definitions and filter behavior |
| [PAGES.md](PAGES.md) | Four-page report layout specification |
| [measures.dax](measures.dax) | Individual measure definitions for manual authoring |
| [Calendar.m](Calendar.m) | Power Query calendar built from `dim_date` |
| [sales-reliability.theme.json](sales-reliability.theme.json) | Report theme |
| [sql/06_business_import.sql](sql/06_business_import.sql) | Separate SELECT blocks for business tables |
| [sql/05_audit_import.sql](sql/05_audit_import.sql) | Separate SELECT blocks for audit tables |
| [sql/01_kpis.sql](sql/01_kpis.sql) | Independent KPI calculations |
| [sql/03_reconciliation.sql](sql/03_reconciliation.sql) | Mart checks and report diagnostics |
| [sql/04_period_comparisons.sql](sql/04_period_comparisons.sql) | Month/year comparison references |

When building from these sources, import each SELECT as its own named query, without `USE` or `GO`. Use `dim_date` as a staging query with load disabled, then create `Calendar` from the M file. Add DAX measures individually; the file is not one executable query.

Amounts have no currency symbol because the source does not identify a currency. Keep unknown-product sales in totals and show undated sales separately. Validate measures against SQL using the same filters before relying on the report.
