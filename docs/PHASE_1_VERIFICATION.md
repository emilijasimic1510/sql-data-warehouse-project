# Phase 1 verification

Historical record: [Phase 1C](PHASE_1C_VERIFICATION.md) subsequently installed and loaded the database, and repaired two missing CSV final record terminators.

Historical Phase 1 record. See [Phase 1B verification](PHASE_1B_VERIFICATION.md) for the later
successful read-only connections and confirmation that DataWarehouse is absent on both local instances.

Review date: 2026-10-10. Baseline: local HEAD `9a0df8a` (`Update README.md`).
The local origin matches `https://github.com/emilijasimic1510/sql-data-warehouse-project.git`.
Remote changes were not fetched, and nothing was committed or pushed.

## Local checkout state

Initially the working directory contained only `.git`, and `.git/index` was absent.
Git consequently reported every HEAD file as a staged deletion. HEAD itself contained the full project,
including the Windows-problematic `datasets ` directory. No AGENTS.md was found in the project,
HEAD file list or checked parent directories.

The project files were restored byte-for-byte from HEAD before editing, mapping `datasets /` to
`datasets/`. No existing working files were overwritten during that restoration. Git metadata/index
was not changed. Consequently, `git status` may still show baseline staged deletions alongside
untracked restored files. This is the pre-existing checkout/index condition, not intentional removal
of the SQL scripts or documentation. Review against HEAD plus the restored working files before staging;
do not commit the pre-existing staged deletions alone. Staging the intended final files is left to the owner.

## Completed static checks

- Read all eight existing SQL scripts, both existing Markdown catalogs, README and six CSV files.
  The existing PDF was preserved; its visual content was not reviewed.
- Verified all six CSV files, the PDF and LICENSE are byte-identical to their HEAD versions.
- Checked CSV headers, consistent field counts and CRLF line endings. Headers align with Bronze DDL
  in column order (case differences for ERP headers are harmless because the header is skipped).
- Checked that six Bronze file mappings exist under the normalized directory.
- Inspected dynamic SQL path escaping and reconstructed drive, spaces/apostrophe and UNC examples
  to check literal round-tripping. This does not validate actual SQL Server filesystem access.
- Checked both procedure scripts have an explicit database batch, followed by a batch starting with
  `CREATE OR ALTER PROCEDURE`, and no executable automatic loader invocation.
- Checked both CATCH blocks end with `THROW` and the Silver error message names Silver.
- Compared all Silver INSERT/SELECT statements to HEAD: unchanged except the correction from
  nonexistent `cst_material_status` to `cst_marital_status`.
- Checked initialization contains no database DROP/reset and all five existing whitespace predicates
  now compare byte lengths before/after TRIM.
- Reviewed Gold SQL and the quality predicates against their documentation, including diagnostic limits.
- Checked README file references against the final working tree.

These checks are source inspection and local file checks, not SQL compilation or executed data-quality tests.
No permanent Python ingestion or testing framework was introduced.

## SQL Server access and unexecuted checks

Local Windows services `MSSQL$SQLEXPRESS` and `MSSQL$SQLEXPRESS01` were running.
Read-only connection attempts with `sqlcmd`, Windows authentication and a five-second login timeout
failed for both `.\SQLEXPRESS` and `.\SQLEXPRESS01`. The client reported encryption not supported,
SSL/security-package credentials unavailable, and failure to establish a connection. This does not
prove that SQL Server itself is unavailable; access from this execution environment was unsuccessful.
No credentials, SQL Server settings, services or other projects were changed.

No database initialization, DDL, procedure deployment, TRUNCATE, load or quality SQL script was executed.
No SQL Server syntax compilation, successful load, actual processed-row count, execution time,
permission validation, repeated-load comparison or controlled partial-failure test is claimed.

## Next manual verification in SSMS

Use the exact installation/reload sequence in README. For an existing database, first compare its
objects to the supplied definitions; do not run destructive table DDL without explicit approval.
Check Messages after each step and inspect every diagnostic result set using QUALITY_CHECKS.md.
Runtime validation should cover first load, repeat load, service file permissions and error propagation.
Controlled missing-file tests belong in a separately approved disposable environment because a failed
load can leave previously truncated tables empty and earlier tables already updated.

## Mentor handoff

Phase 1 retains the SQL Server Bronze/Silver/Gold design and the existing business rules, fixing one
invalid column reference. It adds a configurable Bronze source root, explicit setup versus reload
instructions, procedure-only deployment, visible loader errors and accurately documented manual
quality diagnostics. Database initialization no longer deletes an existing database. Full reloads
still use per-table TRUNCATE/INSERT without a pipeline-wide transaction, and Gold keys remain
query-generated rather than persisted. Runtime validation in SSMS remains pending because the local
ODBC connection attempts failed. No Phase 2 components were added.
