# Windows setup and daily use

Run PowerShell commands from the repository root. An existing installation only needs the daily commands below.

## Python environment

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q --ignore=tests/integration
```

Use the existing `.venv` if it is already configured. Airflow has its own Linux environment.

## First SQL installation

Connect in SSMS to the intended SQL Server instance with Windows authentication. Execute each complete file separately, in order, and stop on errors.

| Order | File | Effect |
| --- | --- | --- |
| 1 | `scripts/init_database.sql` | Creates `DataWarehouse` and missing schemas |
| 2 | `scripts/bronze/ddl_bronze.sql` | Creates Bronze tables; drops existing tables and their data |
| 3 | `scripts/silver/ddl_silver.sql` | Creates Silver tables; drops existing tables and their data |
| 4 | `scripts/bronze/load_bronze.sql` | Defines the Bronze loader |
| 5 | `scripts/silver/load_silver.sql` | Defines the Silver loader |
| 6 | `scripts/gold/ddl_gold.sql` | Recreates Gold views; object-specific grants may need restoring |
| 7 | `scripts/audit/ddl_audit.sql` | Creates audit objects |

Table DDL is for installation or an intentional rebuild, not daily loading. The initialization script does not migrate existing table structures.

Configure the target below using the name returned by `SELECT @@SERVERNAME`. The example assumes a local named instance; replace it for your installation.

```powershell
$target = @('--server', '.\SQLEXPRESS', '--expected-server', 'YOUR-PC\SQLEXPRESS', '--database', 'DataWarehouse')
.\.venv\Scripts\python.exe -m mart_pipeline.deploy @target
.\.venv\Scripts\python.exe -m e2e_pipeline.migrate @target
```

For a local development certificate, `--trust-server-certificate` skips certificate identity validation for that connection. Use a trusted certificate for remote connections.

`BULK INSERT` reads files on the SQL Server host. Its service account needs access to the dataset directory, containing both `source_crm` and `source_erp`. For a remote SQL host, pass its Windows or UNC path through `--sql-dataset-root`; `--dataset-root` remains the path Python reads locally.

## Validate and load

```powershell
.\.venv\Scripts\python.exe -m csv_validation --dataset-root .\datasets
.\.venv\Scripts\python.exe -m e2e_pipeline --dataset-root .\datasets --dry-run --report-path ('.\reports\dry-' + [guid]::NewGuid() + '.json')

# Replaces Bronze/Silver data and refreshes the mart.
.\.venv\Scripts\python.exe -m e2e_pipeline @target --dataset-root .\datasets --execute --report-path ('.\reports\run-' + [guid]::NewGuid() + '.json')
$LASTEXITCODE
```

Dry-run does not check SQL connectivity, type conversions, or SQL Server file permissions. Execution returns 0 for PASS, 1 for a runtime failure, and 2 for invalid options. Inspect the report before retrying: Bronze/Silver changes are not rolled back as a single load. See [recovery](E2E_PIPELINE.md).

## Inspect existing data

In SSMS, select `DataWarehouse` and confirm the target:

```sql
SELECT @@SERVERNAME AS server_name, DB_NAME() AS database_name;
```

Run these read-only queries:

- `tests/quality_checks_silver.sql` and `tests/quality_checks_gold.sql`: warehouse quality counts.
- `powerbi/sql/03_reconciliation.sql`: mart reconciliation and date diagnostics.
- `powerbi/sql/01_kpis.sql`: sales and customer metrics.
- `powerbi/sql/02_audit.sql`: run status and parent/child audit records.

`warehouse_pipeline --quality-only` also writes audit records. `scripts/mart/quality.sql` defines a procedure; use `EXEC mart.check_quality` to run the installed checks.

## Integration tests

Integration tests target the local instance configured in their source files. Review those settings first. Mart tests refresh data, and CRM tests change the isolated demo tables. The CRM suite also requires the documented empty demo ID ranges; see [CRM loading](CRM_INCREMENTAL.md).

| Test file | Opt-in environment variable |
| --- | --- |
| `tests/integration/test_project_lock_sql.py` | `DW_RUN_PROJECT_LOCK_INTEGRATION` |
| `tests/integration/test_mart_sql.py` | `DW_RUN_MART_INTEGRATION` |
| `tests/integration/test_crm_incremental_sql.py` | `DW_RUN_SQL_INTEGRATION` |

Set only the variable for the selected test:

```powershell
try {
    $env:DW_RUN_PROJECT_LOCK_INTEGRATION = '1'
    .\.venv\Scripts\python.exe -m pytest -q tests/integration/test_project_lock_sql.py
} finally {
    Remove-Item Env:DW_RUN_PROJECT_LOCK_INTEGRATION -ErrorAction SilentlyContinue
}
```

For scheduling and reporting, continue with [Airflow](AIRFLOW.md) or [Power BI](../powerbi/README.md). Viewing existing data in Power BI does not require another warehouse load.
