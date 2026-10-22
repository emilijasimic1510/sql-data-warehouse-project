# End-to-end pipeline

`e2e_pipeline` runs CSV validation, Bronze and Silver loads, warehouse quality checks, mart refresh, mart reconciliation, and a final summary. It calls the warehouse and mart Python runners directly. The incremental CRM demo is separate.

## Commands

Install the warehouse, audit tables, and mart using the [setup guide](QUICKSTART_WINDOWS.md). Apply the additive audit migration once with `python -m e2e_pipeline.migrate` and your SQL target options.

```powershell
$target = @('--server', '.\SQLEXPRESS', '--expected-server', 'YOUR-PC\SQLEXPRESS', '--database', 'DataWarehouse')
.\.venv\Scripts\python.exe -m e2e_pipeline --dataset-root .\datasets --dry-run --report-path ('.\reports\dry-' + [guid]::NewGuid() + '.json')
.\.venv\Scripts\python.exe -m e2e_pipeline @target --dataset-root .\datasets --execute --report-path ('.\reports\run-' + [guid]::NewGuid() + '.json')
```

Dry-run is the default and does not connect to SQL Server. Execute requires the server, expected server, and database. `--sql-dataset-root` supplies the path visible to SQL Server when it differs from Python's dataset path. Normal runs never deploy objects.

## Coordination and transactions

The parent holds one SQL session and the exclusive application lock `datawarehouse.pipeline.v1` through both child runs, the summary, and audit finalization. Standalone warehouse and mart runners use the same lock. `--lock-timeout-ms` accepts 0–60000, with a default of 10000. Failure to acquire the lock stops loading.

Bronze and Silver run in autocommit mode. A failure can leave completed statements committed and a truncated table empty. The mart uses its own SERIALIZABLE transaction and commits only after its quality checks pass. A warehouse ERROR skips the mart; WARNING findings allow it to run. There is no whole-pipeline rollback or automatic retry.

The mart's transaction lock is acquired after the project session lock. The parent releases the session lock and closes the connection in cleanup. Direct SSMS calls that do not acquire the same project lock are outside this coordination protocol.

## Audit and reports

The parent and children have separate UUIDs linked by `parent_run_id`. SQL audit stores runs, steps, and warehouse checks; detailed mart findings remain in the embedded child JSON. Reports also include UTC timestamps, durations, `failure_stage`, skipped steps, and sales totals with unknown-product reasons.

Reports must be new `.json` files outside the datasets directory, unless `--overwrite-report` is specified. Files under `reports/` are ignored by Git. Connection, validation, or lock failures may leave only a local report. An interrupted process may leave RUNNING records.

A summary, audit, or report failure after a mart commit does not undo the publication. Check the child `committed` value. A lost connection during commit can leave the outcome unknown; inspect SQL before repeating work.

## Recovery

| Failure | Next step |
| --- | --- |
| CSV validation | Correct the input or path and repeat dry-run |
| Connection, target, or lock | Verify the instance, authentication, and other running writers |
| Bronze or Silver | Inspect partial data and the failed statement before choosing a full reload |
| Warehouse quality | Investigate the failed rule; the mart was skipped |
| Mart after warehouse PASS | Confirm source quality, then refresh only the mart if appropriate |
| Summary, audit, or JSON after commit | Check the published data and child outcome before reloading |

With `$target` configured above:

```powershell
# Checks business data and writes audit records.
.\.venv\Scripts\python.exe -m warehouse_pipeline @target --quality-only --report-path ('.\reports\quality-' + [guid]::NewGuid() + '.json')
# Refreshes only the mart.
.\.venv\Scripts\python.exe -m mart_pipeline @target --execute --report-path ('.\reports\mart-' + [guid]::NewGuid() + '.json')
```

Inspect the latest family in SSMS:

```sql
USE DataWarehouse;
DECLARE @parent uniqueidentifier = (
    SELECT TOP (1) run_id FROM audit.pipeline_runs
    WHERE component = 'e2e' ORDER BY started_at_utc DESC
);
SELECT * FROM audit.pipeline_runs
WHERE run_id = @parent OR parent_run_id = @parent ORDER BY started_at_utc;
SELECT * FROM audit.pipeline_steps WHERE run_id = @parent ORDER BY ordinal;
```

Unknown-product sales remain in total amounts but do not have reliable historical product attributes or cost. Warning counts can overlap and should not be added together as distinct bad rows.
