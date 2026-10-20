# SQL Data Warehouse Project

A SQL Server learning project based on the **Data with Baraa** data warehouse tutorial,
being developed into a junior Data Engineering / Data Analyst portfolio project.
Phase 1 prepares the existing project for repeatable manual setup and full reloads.
Phase 2A adds a read-only Python/Pandas CSV structure validator.
Phase 2B connects that validator to the existing SQL loaders, with dry-run as the default.
Phase 2C adds 28 registered SQL checks, a quality gate, audit history, quality-only mode and JSON reports.
Phase 3A adds a separate deterministic synthetic CRM event simulator for future incremental-load tests.
It does not connect to SQL or change the full-load pipeline. See the [demo contract and commands](docs/CRM_DEMO.md).
Phase 3B adds an isolated, transactional SCD Type 1 loader in the `crm_incremental` schema,
with persistent batch/event ledgers. It is not connected to Gold and does not change full-load behavior.
See [incremental deployment and CLI](docs/CRM_INCREMENTAL.md) and [real SQL verification](docs/PHASE_3B_VERIFICATION.md).
Phase 4A adds physical `mart` dimensions with persistent keys and source product history, a date
dimension and a full-refresh sales fact. Gold views remain the baseline; the CRM demo is separate.
See [mart model and commands](docs/MART.md) and [Phase 4A verification](docs/PHASE_4A_VERIFICATION.md).
Phase 4B composes warehouse and mart into one protected Python run, with a shared session writer lock,
linked parent/child audit results and a final aggregate report. See [daily E2E operation](docs/E2E_PIPELINE.md).
See the [current pipeline guide](docs/PIPELINE.md) and [Phase 2C verification](docs/PHASE_2C_VERIFICATION.md).

`CRM / ERP CSV files -> Bronze tables -> Silver tables -> Gold views`

Bronze imports six CSV files into typed tables. Silver cleans and standardizes them.
Gold exposes `gold.dim_customers`, `gold.dim_products`, and `gold.fact_sales` as views.
Business transformations follow the tutorial; independent Phase 1 improvements are listed below.

## Requirements

- **SQL Server 2017 or newer on Windows**, including Express, and SQL Server Management Studio (SSMS).
  The scripts use T-SQL, `GO`, `CREATE OR ALTER`, `TRIM`, and `BULK INSERT`; other database engines are not supported.
- Permissions to create the database/schemas/objects during installation. Loading needs the appropriate
  table permissions for `TRUNCATE`/`INSERT` and permission to perform bulk operations.
  Executing the procedure alone does not necessarily grant its dynamic SQL those permissions.
- Six supplied CSV files, kept in the subdirectories below. Field values are preserved; Phase 1C adds the missing final CRLF to two CSV files.

## Repository layout

```text
sql-data-warehouse-project/
  csv_validation/{__init__.py,config.py,validator.py,__main__.py}
  crm_demo/{__init__.py,config.py,generator.py,validation.py,__main__.py}
  crm_incremental/{__init__.py,inputs.py,database.py,runner.py,deploy.py,verification.py,__main__.py}
  mart_pipeline/{__init__.py,runner.py,deploy.py,__main__.py}
  e2e_pipeline/{__init__.py,runner.py,summary.py,migrate.py,verification.py,__main__.py}
  warehouse_pipeline/{__init__.py,connection.py,runner.py,quality.py,audit.py,reporting.py,__main__.py}
  datasets/
    source_crm/{cust_info.csv,prd_info.csv,sales_details.csv}
    source_erp/{CUST_AZ12.csv,LOC_A101.csv,PX_CAT_G1V2.csv}
  docs/
    CSV_VALIDATION.md
    PIPELINE.md
    PHASE_2B_RESULTS.json
    PHASE_2C_RESULTS.json
    PHASE_2C_VERIFICATION.md
    CRM_DEMO.md
    PHASE_3A_VERIFICATION.md
    PHASE_3A_RESULTS.json
    CRM_INCREMENTAL.md
    PHASE_3B_VERIFICATION.md
    PHASE_3B_RESULTS.json
    MART_SOURCE_FINDINGS.md
    MART.md
    PHASE_4A_VERIFICATION.md
    PHASE_4A_RESULTS.json
    E2E_PIPELINE.md
    PHASE_4B_VERIFICATION.md
    PHASE_4B_RESULTS.json
    DATA_CATALOG_CONVENTIONS.md
    DATA_CATALOG_GOLD.md
    QUALITY_CHECKS.md
    PHASE_1_VERIFICATION.md
    PHASE_1B_VERIFICATION.md
    PHASE_1C_VERIFICATION.md
    PHASE_1C_RESULTS.json
    data_layers.pdf
  scripts/
    init_database.sql
    bronze/{ddl_bronze.sql,load_bronze.sql}
    silver/{ddl_silver.sql,load_silver.sql}
    gold/ddl_gold.sql
    audit/ddl_audit.sql
    audit/phase4b_migration.sql
    crm_incremental/deploy.sql
    mart/{schema.sql,load.sql,quality.sql}
  tests/
    quality_checks_silver.sql
    quality_checks_gold.sql
    test_csv_validation.py
    test_pipeline.py
    test_quality_pipeline.py
    test_crm_demo.py
    test_crm_incremental.py
    integration/test_crm_incremental_sql.py
    test_mart_pipeline.py
    integration/test_mart_sql.py
    test_e2e_pipeline.py
    integration/test_project_lock_sql.py
  requirements.txt
  requirements-dev.txt
  .gitignore
  README.md
  LICENSE
```

## Get the project and configure file access

```bash
git clone https://github.com/emilijasimic1510/sql-data-warehouse-project.git
cd sql-data-warehouse-project
```

The corrected directory is `datasets`, without a trailing space. Older revisions contain
`datasets `, which can prevent a normal Windows checkout. These Phase 1 changes must be committed
and published by the repository owner before a new clone includes the correction; this work does not push them.

Copy or expose `datasets` to the **computer running SQL Server**, for example `C:\data\datasets`.
Keep `source_crm` and `source_erp` beneath it. The procedure takes this absolute base directory as
`@dataset_root`; a trailing separator is optional, and a Windows drive path or UNC path is supported.
Use a SQL Unicode literal (`N'...'`); write an apostrophe in the path as two apostrophes.

**BULK INSERT reads files on the SQL Server host, not on the SSMS client.**
The SQL Server service must have access to these files. Depending on authentication, the effective
Windows security context also matters; for a UNC share, both share and filesystem permissions must
allow access. A drive letter mapped only in your interactive session may not be visible to the service.
The procedure validates the path's basic form, but does not preflight file existence or permissions.

## First installation in SSMS

Connect to the intended SQL Server instance. Open and execute each file **separately, in this order**,
checking Messages after each one. Stop if any step reports an error.
Each script explicitly selects its database; execute complete files so SSMS processes the `GO` separators.

| Step | File | Effect |
| --- | --- | --- |
| 1 | `scripts/init_database.sql` | Creates `DataWarehouse` and missing schemas; keeps an existing database intact. |
| 2 | `scripts/bronze/ddl_bronze.sql` | Creates six Bronze tables. **Drops existing Bronze tables and their data.** |
| 3 | `scripts/silver/ddl_silver.sql` | Creates six Silver tables. **Drops existing Silver tables and their data.** |
| 4 | `scripts/bronze/load_bronze.sql` | Defines/updates the Bronze procedure; does not load data. |
| 5 | `scripts/silver/load_silver.sql` | Defines/updates the Silver procedure; does not load data. |
| 6 | `scripts/gold/ddl_gold.sql` | Creates/recreates the three Gold views; no data is loaded. |
| 7 | Run the load commands below | Replaces Bronze and Silver data. |
| 8 | Run the quality scripts below | Returns diagnostic result sets for manual inspection. |

Steps 2 and 3 are for an initial installation, or an explicitly approved table rebuild.
For an existing installation matching these definitions, skip them: updating procedure definitions
requires only steps 4 and 5. The initialization script does not migrate existing table structures.
Gold DDL drops/recreates views and can remove object-specific grants; run it only for installation or intended view changes.

## Initial load and subsequent full reloads

After installation, use the same commands for every reload. **Do not rerun table DDL or reset the database.**
Run from a normal SSMS session with implicit transactions OFF and no open explicit transaction.
A reload intentionally replaces the current Bronze and Silver contents; do not run concurrent loads.

1. Execute Bronze first, replacing the example path with the directory on your SQL Server host:

   ```sql
   USE DataWarehouse;
   GO
   EXEC bronze.load_bronze @dataset_root = N'C:\data\datasets';
   ```

2. Only after Bronze succeeds, execute Silver as a separate action:

   ```sql
   USE DataWarehouse;
   GO
   EXEC silver.load_silver;
   ```

3. Run `tests/quality_checks_silver.sql`, then `tests/quality_checks_gold.sql`.
   Inspect every result set using [the quality-check guide](docs/QUALITY_CHECKS.md).
   Gold views reflect Silver immediately; there is no Gold load procedure.

`GO` separates batches in SSMS; it is not a success condition. Do not combine separate load batches
and assume a failure prevents SSMS from submitting later batches.
With unchanged input, the transformation rules are the same, but Silver load timestamps are refreshed.
Gold keys are calculated by `ROW_NUMBER()` and are not persistent identifiers across source changes.

## Errors and partial loads

Both load procedures print context and use `THROW` to return the original caught error to the caller.
They stop at that error. They do **not** wrap all tables, or both layers, in a single transaction.
In normal autocommit mode, completed statements remain committed: if an insert/bulk load fails after
its table was truncated, that table may be empty; earlier tables may contain the new load and later
ones may still contain old data. A failed Bronze load does not update Silver automatically.
A failed Silver load can immediately expose mixed or incomplete data through Gold views.
Caller-owned transactions can change rollback behavior; these procedures do not manage those transactions.

After an error, stop downstream work, fix the reported cause, and rerun the full Bronze load if Bronze
failed, followed by Silver. If only Silver failed and Bronze is complete and unchanged, rerun Silver.
Then inspect all quality results again before using Gold. `THROW` makes SQL errors visible; it does not
make a full reload atomic or turn data-quality findings into failures. Bulk parsing can also tolerate
some rejected rows under SQL Server defaults, so review Messages and reconcile row counts where needed.

## Independently implemented improvements: Phase 1

- Normalized the dataset directory from `datasets ` to `datasets`, preserving CSV contents in Phase 1.
- Phase 1C: appended the missing final CRLF to `cust_info.csv` and `CUST_AZ12.csv` after runtime reconciliation showed their last records were skipped; field values are unchanged.
- Corrected the clone URL, real filenames, SQL Server requirements, installation order and reload instructions.
- Made database/schema initialization non-destructive; documented destructive table DDL separately.
- Parameterized the Bronze dataset root and escaped path literals in dynamic SQL; documented server-side file access.
- Separated procedure definitions from execution, with explicit database context and `GO` batch boundaries.
- Added error rethrowing to both loaders and corrected the Silver error label.
- Fixed the Silver reference `cst_material_status` to the actual Bronze column `cst_marital_status`.
- Fixed whitespace diagnostics to detect trailing spaces with `DATALENGTH`; explained all existing quality checks.
- Replaced the duplicate catalog in the conventions document and corrected Gold generated-key types to `BIGINT`.

These are incremental changes to the tutorial foundation, not a claim that the original warehouse design is independent work.
No Python ingestion, orchestration, cloud services, Kafka, incremental loads, or new SCD Type 2 implementation is included.

## Phase 2A: validate CSV structure before SQL loading

The optional Python validator reads all six configured files without modifying them or connecting to SQL Server.
It checks readable UTF-8 files, exact column names/order, duplicate headers, field counts and nonempty datasets.
A missing final newline is a warning, not an automatic repair. Business-quality rules remain in later layers.

From the repository root in Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m csv_validation --dataset-root .\datasets
$LASTEXITCODE
```

If `.venv` already exists, reuse it and skip the creation step. Activation is not required.
For validation only, install `requirements.txt` instead. An optional JSON report can be created with:

```powershell
.\.venv\Scripts\python.exe -m csv_validation --dataset-root .\datasets --report-path .\reports\my-run.validation.json
```

Choose a new report filename for each run: existing files are never overwritten. Reports must be outside
`--dataset-root`. `reports/`, `*.validation.json`, `.venv` and Python caches are ignored by Git.
Other custom report filenames outside those ignored locations require an additional ignore rule.
Exit code is **0** when all structures pass (warnings allowed), **1** for structural failures and **2** for
invalid CLI usage/report-write errors. All six files are checked even when one fails.

Implementation: `config.py` contains the explicit ordered contract; `validator.py` checks CSV records
before reading values as text with Pandas; `__main__.py` prints results and optionally writes JSON.
The `csv` precheck prevents Pandas from silently padding short records or renaming duplicate columns.
Text such as `NA`, empty strings and leading zeros is preserved.

Verified on **2026-10-11**, using the project virtual environment:
**Python 3.14.3, Pandas 3.0.6, pytest 9.1.1**. All **17 tests passed**, with zero failures.
Separate CLI subprocess checks returned 0 for six valid temporary files and 1 after one temporary file
was removed; all six results were still printed. No real dataset was changed for these checks.

| Source file | Records (excluding header) | Result |
| --- | ---: | --- |
| `source_crm/cust_info.csv` | 18,494 | PASS |
| `source_crm/prd_info.csv` | 397 | PASS |
| `source_crm/sales_details.csv` | 60,398 | PASS |
| `source_erp/CUST_AZ12.csv` | 18,484 | PASS |
| `source_erp/LOC_A101.csv` | 18,484 | PASS |
| `source_erp/PX_CAT_G1V2.csv` | 37 | PASS; final newline missing |

The real-data command returned **0**, with **6/6 passed, zero errors and one warning**.
All six counts match the final Bronze counts recorded in Phase 1C. SHA-256 checks also confirm that all
six CSV files remain byte-identical to their final Phase 1C versions. The category file's last record is
counted despite its missing newline; the warning was retained and the file was not edited.
The generated local evidence is `reports/phase2a.validation.json` (intentionally not committed).

For `cust_info.csv`, the validator obtains its seven expected names from the configuration, builds the
path beneath the supplied root, reads the bytes, checks the header and every record's seven fields,
counts 18,494 records, and then verifies that Pandas reads the same structure as text. It prints PASS
and adds the result to the optional report. Duplicate customers and empty IDs are not structural failures.

This does not validate SQL type conversions, business correctness, SQL Server file permissions or loading.
See [the validator guide](docs/CSV_VALIDATION.md) for file responsibilities, limitations and report semantics.

## Phase 2C: validation, loaders, SQL quality, audit and JSON

[Pipeline guide](docs/PIPELINE.md) explains modes, reports, audit inspection, errors and limitations.
The existing project `.venv` is sufficient. Before the first real run, explicitly execute
`scripts/audit/ddl_audit.sql` in SSMS on the confirmed project instance and database. Normal runs never
create audit objects. This deployment was completed during the local Phase 2C verification.

Dry-run validates all CSV files and prints the plan; it opens no SQL connection:

```powershell
.\.venv\Scripts\python.exe -m warehouse_pipeline --server 'DESKTOP-N1402MQ\SQLEXPRESS' --expected-server 'DESKTOP-N1402MQ\SQLEXPRESS' --database DataWarehouse --dataset-root .\datasets
```

Only the explicit `--execute` flag permits the existing full TRUNCATE/load operations:

```powershell
.\.venv\Scripts\python.exe -m warehouse_pipeline --server 'DESKTOP-N1402MQ\SQLEXPRESS' --expected-server 'DESKTOP-N1402MQ\SQLEXPRESS' --database DataWarehouse --dataset-root .\datasets --trust-server-certificate --execute
```

This local development connection needs explicit certificate trust; encryption stays enabled but
certificate identity verification is skipped for this connection only. Defaults validate certificates.
Windows authentication is used. For a remote server supply `--sql-dataset-root` separately: the default
assumes Python and SQL Server see the same absolute directory on the same computer.
Server/database/path settings can also come from `DW_*` environment variables documented in the guide.

The runner calls the existing validator function, verifies the actual database and required procedures,
then runs Bronze before Silver with bound SQL parameters, followed by registered SQL checks and row counts.
Errors stop dependent steps and close the connection.
`autocommit=True` preserves existing partial-load behavior: there is no rollback of the whole pipeline.
Structural validation does not check SQL conversions. SQL ERROR findings or execution failures now fail
the pipeline. WARNING findings alone allow success. The old-date review remains WARNING.

Use `--quality-only` without `--execute` to inspect existing data without CSV validation or reloads;
it writes only audit data. Add `--report-path .\reports\new-run.json` to any mode for local evidence,
including failure details. Existing reports require explicit `--overwrite-report`. See the guide for
complete copyable commands that automatically choose fresh report names.

Phase 2C verification: **51 tests passed**; actual dry-run, quality-only, and exactly one full reload
returned **0**. Both SQL runs had **zero ERROR checks**, **15 old birthdates as WARNING**, and country
distinct count **7** as INFO. Each real run has 8 audit step records and 28 check records, verified against
JSON. All 15 row counts match Phase 2B. Source CSVs, business SQL files and Git index were preserved.
See [Phase 2C evidence](docs/PHASE_2C_RESULTS.json).

Historical Phase 2B, verified 2026-10-11: **30 tests passed**, dry-run exit code **0**, and **one authorized execute run** returned
**0** on the existing local project database. pyodbc **5.3.0** was added to the Phase 2A environment.
All six CSV hashes were unchanged. All 15 table/view row counts and complete business contents match
Phase 1C using stable keys and excluding load timestamps/generated dimension keys. All 27 manually
executed quality result sets match too, including the 15 retained old birthdates.
See [recorded comparison results](docs/PHASE_2B_RESULTS.json). Phase 2C adds the single reload documented above.

## Phase 3A: synthetic CRM event fixtures

The separate `crm_demo` package generates deterministic snapshot/delta packages, per-package SHA-256
manifests and explicit expected customer states. It includes new customers, changes, no-change events,
duplicates, reversed event order, late arrivals, stale updates, an identical batch replay and a negative
contract fixture. Only synthetic names and reserved demo IDs are used; no database connection is made.

```powershell
.\.venv\Scripts\python.exe -m crm_demo generate --output-dir .\demo_output\phase3a-seed42 --seed 42 --start-date 2026-01-01
.\.venv\Scripts\python.exe -m crm_demo verify --output-dir .\demo_output\phase3a-seed42
```

The verified local directory already exists; choose a new output name to generate again. Output is
ignored by Git and never overwritten. The complete suite passed **94 tests** (51 previous + 43 new).
Actual fixture verification passed: six valid packages and the expected rejection of the negative one.
These source-state expectations are not SQL integration results. See the [contract and next-phase plan](docs/CRM_DEMO.md)
and [Phase 3A verification](docs/PHASE_3A_VERIFICATION.md). Phase 3A itself contains no SQL loader;
the subsequent isolated implementation is described below.

## Phase 3B: isolated incremental CRM loading

`python -m crm_incremental` validates and stages a single package or the ordered demo suite. Dry-run is
the default. Explicit `--execute` uses one transaction for staging, SCD Type 1 customer changes and
successful ledgers. An application lock serializes the small demo; replays are idempotent, older events
are retained as stale without reverting customers, and conflicting IDs/equal-time values reject the package.

Deployment is explicit: `python -m crm_incremental.deploy` with the target options in the
[incremental guide](docs/CRM_INCREMENTAL.md). Normal runs never create objects. The new schema is
separate from Bronze/Silver/Gold; no existing business SQL or full-load Python module was edited.

Verification: **111 unit tests passed**, plus **7 opt-in real SQL integration tests passed**. All seven
Phase 3A deliveries matched expected customer state, including rejection of the negative package.
Replaying the six valid deliveries changed no customer state. Real SQL failures proved whole-package
rollback; a concurrent same-batch test produced one APPLIED and one REPLAY. All 15 original business
objects retained identical full-content hashes. Five demo customers remain; only dedicated test data
was removed. See [Phase 3B evidence](docs/PHASE_3B_RESULTS.json).

The complete demo suite intentionally ends in a rejected negative package, so the incremental suite
command returns exit 1 while retaining the successful earlier per-package commits. This differs from
the fixture-only `crm_demo verify` command, which expects that rejection and returns 0.

## Phase 4A: physical sales mart

`mart_pipeline` is a separate default-dry-run command. Explicit deployment creates only the new
`mart` schema objects. Execute preserves customer/product dimension keys, imports all 397 source
product versions using inclusive date intervals, extends the date dimension and publishes all
60,398 sales records in one transaction. Quality/reconciliation runs before commit, including full
business-row multiset comparison with multiplicity. A fact identity is not a source line identifier.

Observed mart counts include unknown members: dim_customer 18,485; dim_product 398; dim_date 1,140;
fact_sales 60,398. Quantity 60,423 and amount 29,356,250.00 reconcile exactly with Silver. Unknown
products are explicit: 18,410 sales precede available source history and 19 have no order date.
No arbitrary historical/current product version is assigned to those sales; 8,246 sales correctly
map to closed historical versions. Gold retains its original current-version behavior.

Verification: **123 unit tests passed**; all **4 new SQL integration test cases** were verified after
correcting a missing alias in a read-only test query. Two pairs of unchanged-source loads showed stable
dimension keys and complete fact business multisets. A real precommit reconciliation failure restored
the prior mart. All original 15 business objects and the five CRM-demo tables were unchanged.
See [model, deployment and analysis SQL](docs/MART.md) and [detailed evidence](docs/PHASE_4A_RESULTS.json).

## Phase 4B: coordinated warehouse-to-mart run

The thin `e2e_pipeline` runner calls the existing warehouse and mart Python functions directly. One
lock-owning SQL session protects warehouse loads, their quality gate, mart publication and the summary.
Standalone warehouse and mart writers use the same bounded project lock. The full-load autocommit
boundary and separate atomic mart transaction remain; there is no whole-E2E rollback or automatic retry.
Parent/child run UUIDs, skipped stages, durations, warnings and failure stage are retained in audit/JSON.

An explicit additive audit migration is in `scripts/audit/phase4b_migration.sql`; normal runs never
deploy it. [Daily commands and recovery](docs/E2E_PIPELINE.md) includes dry-run, execute and targeted
mart-only recovery. Direct manual SQL without the shared lock protocol is not coordinated.

Verification: **141 unit tests passed**, and both new real two-session SQL lock scenarios were verified.
Exactly **one full end-to-end run** returned PASS / exit 0. All 24 warehouse/CRM-demo/mart business
multisets matched the Phase 4A baseline, excluding Silver load times and mart fact technical identity.
The independent CRM demo is unchanged; parent and child audit records match the JSON reports.

Sales remain 60,398 rows, quantity 60,423 and revenue 29,356,250.00. Historical product coverage is
8,246 rows (13.65% of all sales). Unknown sales stay in total revenue: 18,410 BEFORE_HISTORY rows with
8,649,691.00 and 19 MISSING_ORDER_DATE rows with 4,992.00. They have no reliable historical attributes
or cost; no source history was invented. See [Phase 4B evidence](docs/PHASE_4B_RESULTS.json).

## Verification and documentation

See [Phase 1C runtime verification](docs/PHASE_1C_VERIFICATION.md) and its
[recorded results](docs/PHASE_1C_RESULTS.json). The new DataWarehouse database was installed on
`.\SQLEXPRESS`, loaded, and fully reloaded once. All final Bronze counts match CSV records.
All eleven Gold checks returned zero rows; Silver retained 15 source birthdates before 1924 for review.
The reload validated a two-file CSV EOF repair: eleven objects were identical and four had only the
expected repaired-record differences. The subsequent Phase 2B comparison tested unchanged-input business content.
Phase 2C generates the SSMS aggregate scripts from the same registry used by the Python quality gate.
The earlier [Phase 1](docs/PHASE_1_VERIFICATION.md) and [Phase 1B](docs/PHASE_1B_VERIFICATION.md)
reports are historical records. No performance benchmark is claimed.

- [Quality checks and expected results](docs/QUALITY_CHECKS.md)
- [Gold data catalog](docs/DATA_CATALOG_GOLD.md)
- [Naming conventions](docs/DATA_CATALOG_CONVENTIONS.md)
- [Existing architecture diagram](docs/data_layers.pdf)

## License

[MIT](LICENSE).

### Faza 5: lokalni Airflow

Jedan DAG/task poziva postojeći E2E runner. Uputstva, runtime konfiguracija i bezbedan oporavak: [docs/AIRFLOW.md](docs/AIRFLOW.md). Stvarno stanje verifikacije: [docs/PHASE_5_VERIFICATION.md](docs/PHASE_5_VERIFICATION.md).


Faza 5B: stvarni Airflow build, import, UI i DAG dry-run potvrđeni su u [docs/PHASE_5B_VERIFICATION.md](docs/PHASE_5B_VERIFICATION.md). SQL učitavanje još nije izvršeno iz Airflow-a.
