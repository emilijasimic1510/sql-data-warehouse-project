# SQL Data Warehouse

A SQL Server warehouse for CRM and ERP sales data, with Python load runners, data quality checks, a historical sales mart, and Power BI reporting.

The Bronze, Silver, and Gold layers build on the **Data with Baraa** data warehouse tutorial. The project extends that foundation with CSV validation, audit logging, coordinated loads, persistent mart keys, an incremental CRM demo, and local Airflow orchestration.

```text
CRM / ERP CSV files
    -> Bronze: raw imports
    -> Silver: cleaned and standardized data
        -> Gold: analytical views
        -> Mart: physical dimensions and sales facts -> Power BI
```

## Getting started

Use SQL Server 2017 or later on Windows, SSMS, and Python with the dependencies in `requirements-dev.txt`. SQL connections use a Microsoft ODBC driver; the Windows CLI defaults to Driver 17. Docker Desktop is only needed for Airflow.

```powershell
git clone https://github.com/emilijasimic1510/sql-data-warehouse-project.git
cd sql-data-warehouse-project
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q --ignore=tests/integration
.\.venv\Scripts\python.exe -m e2e_pipeline --dataset-root .\datasets --dry-run
```

Dry-run validates the six CSV files without connecting to SQL Server. Follow the [Windows setup guide](docs/QUICKSTART_WINDOWS.md) to install the database and run a load.

## Components

| Component | Purpose |
| --- | --- |
| `scripts/bronze`, `scripts/silver`, `scripts/gold` | SQL tables, transformations, and analytical views |
| `csv_validation` | CSV headers, record structure, encoding, and newline checks |
| `warehouse_pipeline` | Full loads, 28 SQL quality checks, audit records, and JSON reports |
| `mart_pipeline` | Persistent customer/product keys, product history, date dimension, and sales facts |
| `e2e_pipeline` | Warehouse-to-mart execution under a shared SQL application lock |
| `crm_demo`, `crm_incremental` | Synthetic customer events and an isolated SCD Type 1 loader |
| `orchestration/airflow` | Local Docker deployment with one manually triggered DAG |
| `powerbi` | PBIX/PBIP report, DAX definitions, SQL reference queries, and model documentation |

## Data model and limits

Gold exposes customer and current-product views with keys calculated by `ROW_NUMBER()`. The mart stores persistent dimension keys and maps sales to the product version valid on the order date.

The supplied data contains 60,398 sales rows. Some sales predate available product history; others have no order date. These rows remain in totals and use an unknown dimension member. Currency is not provided by the source, and current product cost should not be used to estimate historical margin.

Bronze and Silver use full reloads with statement-level commits. A failure can leave partial data. The mart publishes in a separate transaction after reconciliation. See [execution and recovery](docs/E2E_PIPELINE.md) before retrying a failed load.

## Documentation

- [Windows setup and daily commands](docs/QUICKSTART_WINDOWS.md)
- [Warehouse pipeline](docs/PIPELINE.md) and [CSV validation](docs/CSV_VALIDATION.md)
- [Quality checks](docs/QUALITY_CHECKS.md), [Gold catalog](docs/DATA_CATALOG_GOLD.md), and [naming conventions](docs/DATA_CATALOG_CONVENTIONS.md)
- [Sales mart](docs/MART.md) and [end-to-end execution](docs/E2E_PIPELINE.md)
- [Synthetic CRM data](docs/CRM_DEMO.md) and [incremental loading](docs/CRM_INCREMENTAL.md)
- [Local Airflow](docs/AIRFLOW.md)
- [Power BI report](powerbi/README.md)

## License

[MIT](LICENSE).
