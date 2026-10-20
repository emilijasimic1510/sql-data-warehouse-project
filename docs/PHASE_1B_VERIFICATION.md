# Phase 1B: execution access and Git verification

Historical record: [Phase 1C](PHASE_1C_VERIFICATION.md) subsequently installed and loaded the database, and repaired two missing CSV final record terminators.

Date: 2026-10-10. Baseline remains local HEAD `9a0df8a`.
Scope: read-only SQL Server diagnostics, Git/file review and validation instructions.
No database, table, service, global security setting, credential or Git index was changed.
No commit, push or fetch was performed.

## Confirmed by SQL execution

Read-only SELECT statements succeeded against both installed local SQL Server service instances:

| Instance | Reported server name | Engine version | DataWarehouse |
| --- | --- | --- | --- |
| `.\SQLEXPRESS` | `DESKTOP-N1402MQ\SQLEXPRESS` | `16.0.1000.6` | Does not exist |
| `.\SQLEXPRESS01` | `DESKTOP-N1402MQ\SQLEXPRESS01` | `17.0.1000.7` | Does not exist |

`DB_ID(N'DataWarehouse')` returned NULL on both instances. A query of `sys.databases` by exact name
returned no rows. A subsequent name search containing `warehouse` also returned no rows.
`IS_SRVROLEMEMBER('sysadmin')` and `HAS_PERMS_BY_NAME(NULL,NULL,'VIEW ANY DATABASE')` both returned 1,
so the absence is not explained by metadata visibility restrictions for this connection.

There is no DataWarehouse on either inspected instance in which to inventory tables, views or procedures,
or count their rows. This means **not applicable**, not a count of zero in existing tables.
The Silver and Gold quality SELECT scripts were not executed because their target database does not exist.
Even if run against an existing loaded database, these SELECT checks would validate its current state,
not prove that the new local procedure definitions were deployed or used to produce that state.

## Connection diagnosis

The same `sqlcmd` client and Windows authentication reproduced the following errors inside the sandbox:
`Encryption not supported on the client`, `SSL Provider: No credentials are available in the security package`,
and `Client unable to establish connection`.

Reissuing the read-only connection outside that sandbox succeeded, without `-C`, changing certificates,
changing services, or changing credentials. Both explicit shared-memory addresses (`lpc:.\SQLEXPRESS`,
`lpc:.\SQLEXPRESS01`) and the ordinary `.\SQLEXPRESS` / `.\SQLEXPRESS01` addresses worked.

The controlled difference isolates the failure to the sandbox execution/security context. The original
messages are not evidence of an untrusted server certificate. The precise internal Windows security-package
failure was not traced further. No TLS or authentication policy workaround was applied.

Successful connection metadata: `net_transport = Shared memory`, `auth_scheme = NTLM`,
`encrypt_option = FALSE`. These were local shared-memory connections; this does not demonstrate a working
encrypted TCP connection. Read-only configuration inspection showed shared memory enabled, TCP disabled
and `ForceEncryption = 0` for both instances. SQL Browser was stopped; it did not prevent shared-memory access.
Those settings were only read, never changed.

Available clients/drivers inspected:

- ODBC `sqlcmd` version `16.0.1000.6`, using ODBC Driver 17 for these connections.
- ODBC Driver 17 and 18 registered for both 32-bit and 64-bit clients.
- 64-bit Driver 17 DLL file version `2017.1710.0006.01`; Driver 18 `2018.0185.0002.01`.
- SQL Server Management Studio 22, installed version `22.2.1`.
- `SQLPS.exe` is also available; it was not needed for the connection.

### If SSMS separately reports an untrusted certificate

Only for the intended local development connection, SSMS allows **Trust server certificate** with
**Mandatory** encryption (or a connection string with `Encrypt=Yes;TrustServerCertificate=Yes`).
For this installed ODBC sqlcmd client, the equivalent explicit encryption/trust flags are `-N -C`.
This keeps encryption requested but skips certificate validation: it does not authenticate the server's
identity and is not a production/remote-server certificate solution. It is a per-connection choice,
not an instruction to disable global validation or install a root certificate.
It was **not necessary or used** in the successful connections above, and it is not a demonstrated fix
for the sandbox's security-package error.

Sources: [Microsoft connection encryption guidance](https://learn.microsoft.com/en-us/sql/database-engine/configure-windows/special-cases-for-encrypting-connections-sql-server)
and [Microsoft sqlcmd options](https://learn.microsoft.com/en-us/sql/tools/sqlcmd/sqlcmd-utility).

## Git and file integrity

No AGENTS.md was found in the project, its HEAD file list or checked ancestor directories.
`.git/index` was absent before this phase and remains absent. Thus `git status` reports all 19 HEAD paths
as staged deletions and the restored working files/directories as untracked. The index was not repaired,
reset or staged. A raw `git diff HEAD` alone is misleading in this condition; each working file was instead
compared to its corresponding HEAD blob, mapping `datasets /` to `datasets/`.

All 19 original files are present after that mapping. LICENSE and `docs/data_layers.pdf` are byte-identical.
All six CSVs are byte-identical to HEAD; their SHA-256 values are:

| CSV under datasets | SHA-256 |
| --- | --- |
| `source_crm/cust_info.csv` | `5e00eca4351886386f6dd01beea91cb17ff081b97b9a02d295b84505448c8040` |
| `source_crm/prd_info.csv` | `3db1d644b424aa42599c5a00a8b1297b7b099367c180a63b141f91efac0de45b` |
| `source_crm/sales_details.csv` | `0a1e565ae2e8accec217819226d7b71104cc6075590172ed855617a8930a4369` |
| `source_erp/CUST_AZ12.csv` | `31b697a6a6022085e2f0b1a4d8fe55faae57a54a2d0c8ff91534253b8f3e64a0` |
| `source_erp/LOC_A101.csv` | `d46239d31bfa3a78e8a6cc8ee97a51e914b2db2db460bfb79a3aeadaf8e028c0` |
| `source_erp/PX_CAT_G1V2.csv` | `ef8048319a2cc23907fc6caf215d31cca5e0bf908590fd6bd7dfa81b48ac9743` |

### Expected future commit, after deliberate staging by the owner

- Six file renames from `datasets /...` to `datasets/...`, with 100% identical content.
  Git tracks files, not a directory rename; rename detection should pair the six deletions/additions.
- Eleven modified existing files: README, both original catalog/conventions documents and all eight SQL files.
- Three new documentation files: `docs/QUALITY_CHECKS.md`, `docs/PHASE_1_VERIFICATION.md`,
  and this `docs/PHASE_1B_VERIFICATION.md`.
- No deletion of LICENSE, the PDF, SQL scripts, documentation or datasets.

A suitable future commit title is `Prepare SQL Server warehouse for repeatable setup and document validation`.
After the owner chooses to stage the intended final files, inspect `git diff --cached --stat`,
`git diff --cached --name-status -M` and `git diff --cached --check` before committing.
These staging/commit operations were not performed. Do not commit the current deletion-only index state.

## Static SQL validation

Used the ScriptDom DLL already bundled with SSMS, with `TSql140Parser` (SQL Server 2017 grammar).
All eight local SQL files parsed with zero syntax errors. The six dynamic BULK INSERT templates were
also reconstructed with a sample path containing spaces and an apostrophe and parsed with zero errors.
This validates syntax only: it does not bind table/column names, deploy procedures, check file permissions,
execute transformations or prove that loading succeeds. The existing SELECT quality scripts were reviewed.
No new local SQL code defect was identified that required a change during Phase 1B.

## Exact next validation steps, with a write boundary

1. Open SSMS. Choose **Database Engine**, server `DESKTOP-N1402MQ\SQLEXPRESS`,
   **Windows Authentication**. This is the proposed SQL Server 2022 target; keep the second instance separate.
   Connect normally first. If SSMS reports a certificate-chain error specifically, use only the local
   connection setting described above, without changing server or global security settings.
2. Open New Query against master and execute only:

   ```sql
   SELECT @@SERVERNAME AS server_name,
          CAST(SERVERPROPERTY('ProductVersion') AS varchar(30)) AS engine_version,
          DB_ID(N'DataWarehouse') AS warehouse_id;
   SELECT name, state_desc
   FROM sys.databases
   WHERE name = N'DataWarehouse';
   ```

   Confirm the intended instance. Based on this review, warehouse_id should be NULL and the second
   result set empty. If a database now exists, stop: inventory it read-only before installation.
3. **STOP BEFORE WRITING:** the next operation would be `scripts/init_database.sql`, creating
   `DataWarehouse` plus `bronze`, `silver` and `gold` schemas on the chosen instance. It has not been run.
   The user must confirm the target and authorize database creation/initial loading before proceeding.
4. After that authorization, execute complete files individually in the README order: init, Bronze DDL,
   Silver DDL, Bronze procedure definition, Silver procedure definition, Gold DDL. Check Messages after
   each and stop at an error. Expected new objects: 12 tables, two procedures and three views.
   Table DDL drops/recreates matching existing tables, so it is only appropriate here if the target is
   still a new, empty installation. Procedure deployment changes definitions, not table contents.
5. Before the first load, confirm the dataset directory and SQL Server file access. If SQL Server runs
   on this same computer, the current dataset directory is:
   `C:\Users\DELL\Desktop\data-warehouse\sql-data-warehouse-project\datasets`.
   No file access permission for the SQL Server bulk operation has been tested or changed.
6. After explicit authorization to load, run `EXEC bronze.load_bronze @dataset_root = N'<absolute dataset directory>';`.
   It will TRUNCATE and bulk-load six Bronze tables. Only after success, run `EXEC silver.load_silver;`;
   it will TRUNCATE and refill six Silver tables. Gold views then expose the resulting Silver data.
7. Run the Silver then Gold quality SELECT scripts and record all result sets using QUALITY_CHECKS.md.
   For exact row counts, use `SELECT COUNT_BIG(*) FROM schema.table;` on each of these table names
   in both schemas: `crm_cust_info`, `crm_product_info`, `crm_sales_info`, `erp_customer_info`,
   `erp_location_info`, `erp_product_category`. Compare Bronze counts to parsed CSV data records
   (excluding headers), allowing for no unexplained rejects. Silver customer deduplication can reduce counts.
8. A second full reload and controlled error tests are separate write operations requiring approval.
   Compare actual results after the second load, accounting for refreshed Silver timestamps.
   A missing later CSV can test THROW/partial failure only in an approved disposable environment;
   it can leave a table empty after TRUNCATE. A syntax parse does not replace these runtime tests.

Stopped after Phase 1B. No initial installation or load was started.
