# Incremental CRM loader

`crm_incremental` applies the synthetic CRM packages to an isolated schema in `DataWarehouse`. Customers use SCD Type 1: one latest accepted state per `cst_id`. This demo is separate from the warehouse, Gold, and sales mart.

## Objects

| Object | Purpose |
| --- | --- |
| `customers` | Current normalized customer state, timestamp, last event, and business hash |
| `attempts` | Successful committed deliveries, including replay attempts |
| `batches` | One record per accepted batch ID and original content hash |
| `events` | Event IDs, canonical hashes, source timestamps, and first outcomes |
| `staging` | Input rows and outcomes per attempt and ordinal |
| `apply_batch` | Conflict checks, ordered processing, and metrics |

The ledger is delivery history, not a historical customer dimension.

## Commands

First [generate a fixture suite](CRM_DEMO.md). Then deploy once and choose a package or suite:

```powershell
$target = @('--server', '.\SQLEXPRESS', '--expected-server', 'YOUR-PC\SQLEXPRESS', '--database', 'DataWarehouse')
.\.venv\Scripts\python.exe -m crm_incremental.deploy @target
.\.venv\Scripts\python.exe -m crm_incremental --package-dir .\demo_output\seed42\00_snapshot --dry-run
.\.venv\Scripts\python.exe -m crm_incremental @target --suite-dir .\demo_output\seed42 --execute --report-path ('.\reports\crm-' + [guid]::NewGuid() + '.json')
```

Dry-run is the default. Execute requires the server, expected server, and database. The complete suite ends with a deliberately rejected package and therefore returns **FAIL / exit 1**, even when the six valid deliveries succeed. Earlier package commits remain. `crm_demo verify` instead tests the fixture's expected rejection and returns 0.

Deployment creates only the isolated schema objects. It records a contract version and metadata signature; repeat deployment rejects incompatible objects instead of repairing them silently. Normal runs do not execute DDL.

## Validation and transaction boundary

The loader freezes the package bytes in a private temporary directory and validates the CSV and manifest before connecting. It parses those validated bytes and stages parameterized values. SQL Server does not read the demo CSV files directly.

Names are trimmed, marital status maps to Single/Married, gender maps to Female/Male, and other domain values map to `n/a`.

One explicit transaction includes staging, customer changes, and successful ledgers. The transaction-owned application lock `crm_incremental.loader.v1` serializes attempts with a 10-second timeout. The Python caller reads all procedure result sets before committing. Failure rolls back the package; failed attempts remain in local JSON rather than a separately committed SQL audit.

A connection loss during commit can leave the outcome unknown. Inspect the batch ledger before retrying. JSON write failure after commit does not undo the data.

## Replays, conflicts, and ordering

| Input | Outcome |
| --- | --- |
| Same batch ID and content | REPLAY; no customer changes, new attempt/staging records |
| Same batch ID, changed content | Reject the package |
| Same event ID and canonical payload | Duplicate |
| Same event ID, different payload | Reject the package |
| Same customer timestamp, conflicting business values | Reject the package |
| New customer | Insert |
| Newer changed values | Update |
| Newer unchanged values | No change to business values; advance source timestamp |
| Older event | Stale; retain current customer state |

Events are ordered by customer, source timestamp, event ID, and ordinal. A snapshot is additive and never deletes absent customers. Canonical event hashes normalize timestamps to UTC; business hashes exclude event IDs and timestamps.

Metrics distinguish changed customers from processed events: two updates to one customer count as two update events but at most one changed customer. Reports include package and attempt identifiers, outcomes, metrics, UTC timestamps, and sanitized SQL errors.

## Inspect and test

```sql
USE DataWarehouse;
SELECT * FROM crm_incremental.batches ORDER BY committed_at_utc;
SELECT * FROM crm_incremental.attempts ORDER BY started_at_utc;
SELECT event_id, cst_id, source_updated_at, outcome, batch_id
FROM crm_incremental.events ORDER BY cst_id, source_updated_at;
```

Unit tests run without SQL. Live tests require `DW_RUN_SQL_INTEGRATION=1` and the target configured in `tests/integration/test_crm_incremental_sql.py`. The initial suite expects empty demo IDs 1900000000–1900000899; other cases reserve 1900000900–1900000999. Do not rerun the initial suite against populated demo state or delete existing demo data to satisfy its assertion.

The loader has no delete events, automatic retries, SCD Type 2, or ledger retention job. It is a small serialized example, not a production CDC service.
