# Warehouse pipeline

The [end-to-end runner](E2E_PIPELINE.md) coordinates warehouse and mart loading with a shared writer lock.
Standalone warehouse runs now include a ninth `coordination` step and acquire the same database-scoped
session application lock used by standalone mart and E2E. The existing validation/load/quality rules
and full-load autocommit boundary are retained. `run_pipeline` still returns an exit code;
`run_report` exposes the structured child result for direct Python composition.

The current command validates CSV -> confirms target -> starts audit -> loads Bronze -> loads Silver ->
checks SQL quality -> reads row counts -> finalizes audit and JSON. Gold objects remain views.


## Responsibilities and deployment

- `warehouse_pipeline/quality.py`: the single registry of 28 checks, aggregate execution, 15 row counts,
  and generation of the two SSMS quality scripts. See [QUALITY_CHECKS.md](QUALITY_CHECKS.md).
- `runner.py`: ordered steps, stop-on-load-error, quality gate and final status.
- `reporting.py`: UTC timestamps, privacy-safe summaries and exclusive JSON-file creation.
- `audit.py`: parameterized INSERT/UPDATE only. Three normalized tables: one run, ordered steps,
  and check outcomes. Definitions/descriptions remain in the registry and local JSON, not repeated in SQL.
- `connection.py`: Windows authentication, encrypted ODBC connection with autocommit, target checks.
- `scripts/audit/ddl_audit.sql`: explicitly deploy once in SSMS to the confirmed project instance and
  DataWarehouse. It creates only missing audit objects. It never drops objects or modifies business tables.
  It is not a migration tool for incompatible pre-existing audit tables.

Normal execution never creates schemas/tables. An audit-start failure stops before loading. Permissions
must allow SELECT on business objects, INSERT on all three audit tables, UPDATE on audit.pipeline_runs,
and, for execute only, the existing loader/TRUNCATE/BULK INSERT permissions.

## Commands (PowerShell, repository root)

Use the project `.venv`. Each command chooses a fresh report filename:

```powershell
$target = @('--server', 'YOUR-PC\SQLEXPRESS', '--expected-server', 'YOUR-PC\SQLEXPRESS', '--database', 'DataWarehouse')

.\.venv\Scripts\python.exe -m warehouse_pipeline @target --dataset-root .\datasets --dry-run --report-path ('.\reports\dry-' + [guid]::NewGuid() + '.json')

.\.venv\Scripts\python.exe -m warehouse_pipeline @target --trust-server-certificate --quality-only --report-path ('.\reports\quality-' + [guid]::NewGuid() + '.json')

.\.venv\Scripts\python.exe -m warehouse_pipeline @target --dataset-root .\datasets --trust-server-certificate --execute --report-path ('.\reports\execute-' + [guid]::NewGuid() + '.json')
$LASTEXITCODE
```

Every execute command deliberately reloads Bronze/Silver.
`--dry-run` is optional because it is the default. The three mode flags are mutually exclusive;
quality-only is itself explicit permission to connect, so it must not be combined with --execute.
Quality-only performs no CSV validation, no procedure existence requirement and no loader calls.
Its business queries are read-only; it still writes its own audit record. A dataset path is unnecessary.

Existing CLI/environment mappings are preserved: `--server`/`DW_SERVER`, `--database`/`DW_DATABASE`,
`--dataset-root`/`DW_DATASET_ROOT`, `--sql-dataset-root`/`DW_SQL_DATASET_ROOT`,
`--driver`/`DW_ODBC_DRIVER` (default ODBC Driver 17 for SQL Server),
`--expected-server`/`DW_EXPECTED_SERVER`. Flags selecting real execution have no environment equivalent.
The optional expected server is compared with `@@SERVERNAME`; system databases are rejected.

`--dataset-root` is Python's local path. `--sql-dataset-root` is an absolute Windows/UNC path visible
from SQL Server, defaulting to the resolved local dataset path. No remote upload or cross-host hash
comparison is performed. `--trust-server-certificate` affects this connection only. Windows process
credentials are used; no password or connection string is saved in reports.

## Status and failure semantics

- Exit 0: PASS, possibly with warnings. Exit 1: validation, SQL, quality ERROR, audit or report failure.
  Invalid CLI combinations return 2.
- Dry-run validates CSV and optionally writes local JSON; it never opens SQL or writes audit.
- CSV validation is a preflight before SQL. A rejected CSV run has local failure evidence but no SQL
  audit row, preserving the existing guarantee that invalid CSV never opens a database connection.
- A real database run gets one UUID run_id and one RUNNING audit row after identity/procedure checks.
  Connection/identity/procedure failures cannot safely persist an audit row; the JSON captures the failure.
- Bronze errors (including late nextset errors) prevent Silver and quality. Silver errors prevent quality.
  Unreached/inapplicable steps are SKIPPED, not PASS. Available earlier results remain in the JSON.
- Checks run after successful Silver, or directly in quality-only. All checks are attempted so a failed
  rule does not hide later findings. A SQL execution error is ERROR with NULL anomaly_count, even for a
  WARNING/metric rule. Actual zero means a successfully read zero. ERROR findings fail the gate;
  WARNING findings and INFO metrics do not. Row-count query failures also fail the run and retain other counts.
- Audit finalization writes steps/checks before setting the run to PASS/FAIL. Audit errors force FAIL in
  the local report and attempt to mark the run FAIL, while retaining the original error separately.
  A disconnected server may retain RUNNING or partial audit children. There is no automatic retry.
- UTC timestamps use `Z` in JSON and UTC datetime2 values in SQL. Durations use a monotonic clock.
  End time marks business workflow completion, before audit/report I/O.

Autocommit remains True. There is no whole-load rollback: completed changes can remain after failure.
A failed quality gate does not undo loading or prevent direct Gold reads. Supported Python writers are
serialized by the shared project lock; direct manual SQL without that protocol remains unprotected.
Quality checks and row counts are separate SELECTs, not a whole-load transaction.

## Report contract and privacy

`--report-path` is optional, requires .json outside the dataset directory, and is reserved before work.
Existing files are rejected before connecting. Only explicit `--overwrite-report` permits replacement;
that flag requires --report-path. Reports are initially RUNNING and finalized even after handled failures.
A process kill can leave RUNNING/incomplete JSON; a disk failure may prevent finalization and returns failure.

JSON includes schema_version, UUID, mode, UTC times, final status, confirmed target where available,
CSV summaries, all step statuses/durations, rule descriptions/counts, available row counts, original errors
and separate audit errors. CSV summaries use file_index in the six-file config order, counts/status and
sanitized newline warnings, not arbitrary headers, paths, row samples or parser details.
SQL selects only aggregates. Raw driver exceptions are replaced by SQLSTATE; no customer values,
birthdate samples, credentials or connection strings are recorded. Country values are not exported.
Generated reports under reports/ are ignored by Git.

## Inspect the latest audit in SSMS

Connect to the named SQLEXPRESS instance, then run:

```sql
USE DataWarehouse;
DECLARE @run_id uniqueidentifier = (
    SELECT TOP (1) run_id FROM audit.pipeline_runs ORDER BY started_at_utc DESC, run_id DESC
);
SELECT * FROM audit.pipeline_runs WHERE run_id = @run_id;
SELECT * FROM audit.pipeline_steps WHERE run_id = @run_id ORDER BY ordinal;
SELECT * FROM audit.quality_results WHERE run_id = @run_id ORDER BY check_id;
```

A PASS run can contain WARNING checks. Match run_id to the JSON for descriptions and row counts.
An audit RUNNING record is not success; investigate interruption or a failed audit finalization.

## Simple examples

Successful: CSV passes, Bronze/Silver finish, old birthdate check counts 15 WARNING rows, ERROR checks
find zero anomalies, and audit/report finish. Final PASS, exit 0; the 15 birthdates are unchanged.

Failed (mock test): Bronze raises SQLSTATE 22018. Bronze is FAIL, Silver/quality are SKIPPED, exit 1.
If audit then fails too, JSON retains both the Bronze error and separate audit error. Prior autocommitted
changes may remain. Another tested failure is a successful load followed by an ERROR check with two
anomalies: the load remains committed, but final status and audit are FAIL.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q --ignore=tests/integration
```
