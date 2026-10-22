# Synthetic CRM events

`crm_demo` generates deterministic customer-event fixtures for the [incremental loader](CRM_INCREMENTAL.md). It uses only the Python standard library and does not connect to SQL Server or change the warehouse datasets.

## Generate and validate

```powershell
.\.venv\Scripts\python.exe -m crm_demo generate --output-dir .\demo_output\seed42 --seed 42 --start-date 2026-01-01
.\.venv\Scripts\python.exe -m crm_demo verify --output-dir .\demo_output\seed42
.\.venv\Scripts\python.exe -m crm_demo validate --package-dir .\demo_output\seed42\01_changes
```

Generation requires a new output directory. The same generator version, seed, and start date produce identical bytes and identifiers. Each package contains `customers.csv` and `manifest.json`; `expectations.json` defines the delivery order and expected state. Generated output is ignored by Git.

`validate` returns 1 for a rejected package. `verify` expects the deliberately invalid final package, so a correct complete fixture returns 0. Syntax errors return 2.

## CSV contract

UTF-8 without BOM, LF line endings including the final line, comma delimiters, and these nine columns in order:

| Column | Meaning |
| --- | --- |
| `event_id` | Immutable event identifier: `evt-` plus 64 lowercase hex characters |
| `source_updated_at` | Source version timestamp in UTC, `YYYY-MM-DDTHH:MM:SSZ` |
| `cst_id` | Customer business key in reserved range 1900000000–1900000999 |
| `cst_key` | Matching synthetic CRM number, such as `DEMOCRM0001` |
| `cst_firstname` | Synthetic ASCII name, at most 50 characters |
| `cst_lastname` | Synthetic ASCII name, at most 50 characters |
| `cst_marital_status` | `S`, `M`, or `n/a` |
| `cst_gndr` | `F`, `M`, or `n/a` |
| `cst_create_date` | ISO date, no later than the source version date |

The scenario uses five customers, 1900000001–1900000005. Different seeds represent alternative scenarios and should not be mixed into the same populated demo target.

The manifest records contract version, seed, start date, package type, record count, CSV SHA-256, and batch ID. The hash covers exact CSV bytes. Event IDs derive from the scenario parameters and event tag; batch IDs derive from package type and CSV hash. Hashes detect content changes, not source authenticity.

## Deliveries

| Package | Rows | Scenario |
| --- | ---: | --- |
| `00_snapshot` | 3 | Initial customer state |
| `01_changes` | 3 | New customer, changed customer, and a no-change event |
| `02_versions` | 2 | Two versions of one customer in reverse CSV order |
| `03_late_arrival` | 3 | Duplicate event plus late new/updated customers |
| `04_stale` | 2 | Older event and newer no-change event |
| `05_replay` | 3 | Exact replay of `01_changes`, including its batch ID |
| `06_negative` | 1 | Missing required `cst_id`; rejected |

Ordering uses `source_updated_at`, not `cst_create_date` or delivery time. Repeated event IDs retain the same payload. A newer no-change event still advances the customer's accepted source timestamp.
