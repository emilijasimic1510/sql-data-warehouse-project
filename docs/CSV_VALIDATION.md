# Phase 2A: read-only CSV structure validation

This optional preflight checks six source files before a separate SQL load. It does not connect to
SQL Server, run SQL, change CSV data, or automatically start/stop an external pipeline.

## Files

| File | Purpose |
| --- | --- |
| `csv_validation/config.py` | Explicit filenames and ordered source headers, reviewed against Bronze DDL. |
| `csv_validation/validator.py` | Read-only CSV checks followed by a Pandas text read. |
| `csv_validation/__main__.py` | CLI, per-file results, summary, exit codes and optional JSON report. |
| `csv_validation/__init__.py` | Marks the directory as a Python package. |
| `tests/test_csv_validation.py` | Small pytest cases using temporary files only. |
| `requirements.txt` | Shared runtime dependencies: Pandas for validation, pyodbc for the optional Phase 2B runner. |
| `requirements-dev.txt` | Runtime dependencies plus pytest for tests. |
| `.gitignore` | Excludes `.venv`, Python caches, `reports/` folders and `*.validation.json`. |

The explicit configuration preserves the actual uppercase ERP headers. Bronze DDL uses lowercase
column names for ERP, but the field order is the same. Names are compared exactly, including case and
spaces; the validator never infers the expected schema from the input being checked.

## Windows setup and commands

Open PowerShell in the repository root. Python 3.14 is the version used for this phase.

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m csv_validation --dataset-root .\datasets
$LASTEXITCODE
```

No activation or execution-policy change is necessary: invoking the virtual environment's interpreter
directly ensures that its libraries are used. For validation without tests, install `requirements.txt`.
The direct dependency versions are pinned; transitive dependencies are resolved by pip rather than a lockfile.

Optional report:

```powershell
.\.venv\Scripts\python.exe -m csv_validation --dataset-root .\datasets --report-path .\reports\phase2a.validation.json
$LASTEXITCODE
```

Both absolute and relative dataset paths are supported via `pathlib`; relative paths are resolved from
the current working directory. Quote a path containing spaces. Run the module from the repository root.
Use `reports/` or a filename ending in `.validation.json` so generated reports are ignored by Git.
An arbitrary custom report name outside those locations needs its own ignore rule before future staging.

Reports are UTF-8 JSON and are never overwritten. Choose a new filename for each report run, or remove
an old generated report yourself. Reports must be outside the dataset directory and have a `.json` suffix.
The report contains paths, versions, column names, record counts, errors and warnings; it does not copy
data-row values. An existing report must not be mistaken for the result of a later failed write.

## Checks and exit codes

For each configured file, the validator:

1. Reads bytes once and decodes UTF-8, accepting an optional UTF-8 BOM. Missing/unreadable files or invalid
   encoding fail that file; the other files are still processed.
2. Warns if the file has no final newline. This alone does not fail structural validation and never
   changes the file. Phase 1C demonstrated that SQL BULK INSERT can omit a final unterminated record.
3. Uses `csv.reader(strict=True)` to inspect the original header before Pandas can rename duplicates.
   It reports missing, unexpected and duplicate columns, and checks exact positional order.
4. Counts all data records, checking the field count of every record. Short, long and blank physical
   data lines are not silently discarded. Quoted CSV fields are parsed using the standard CSV dialect.
5. Requires at least one data record. Empty fields are allowed, so an otherwise correctly sized row of
   empty fields is structurally valid. This is not a business completeness check.
6. If these checks pass, reads the same text with Pandas (`dtype=str`, `na_filter=False`,
   `keep_default_na=False`, `skip_blank_lines=False`, `on_bad_lines="error"`). `NA`, empty strings,
   leading zeros and dates remain text. Checks the Pandas headers and row count against the contract
   and CSV scan. See [Pandas read_csv documentation](https://pandas.pydata.org/docs/reference/api/pandas.read_csv.html).
7. Prints each file's status, count, actual columns and reasons, then the six-file summary.

The displayed record count excludes the header and includes structurally bad records that the CSV
reader can parse. If malformed quoting stops parsing, the count is explicitly marked partial; a count
cannot be invented for the remainder. For an unreadable file, the count is unavailable. JSON includes
`count_complete` to make that distinction machine-readable.

Exit codes:

- `0`: all six structures pass; warnings may still be present.
- `1`: at least one file fails structural validation.
- `2`: invalid CLI usage or inability to create the requested report, even if file validation passed.

Extra files beneath the dataset directory are not checked. This contract covers only the six configured files.

## Example flow: customer information

For `source_crm/cust_info.csv`, the program looks up seven expected column names in `config.py`, joins the
relative filename to `--dataset-root`, and reads the file without writing to it. It checks the header
names and their order, then checks that every CSV record has seven fields. It counts even a final record
without a newline, while warning about SQL loading. If structure is valid, Pandas reads the same content
as text. The result is printed and optionally saved with the other five results as JSON.

Duplicate customers, NULL-like/empty IDs and old birthdates are intentionally not rejected here.
The validator does not check numeric/date conversion, string lengths against SQL types, referential
integrity, sales calculations, permissions of the SQL Server service, or actual BULK INSERT success.
Python's CSV quoting support also does not certify every CSV as compatible with the existing SQL bulk
options. A structural PASS is not a promise that SQL loading or downstream quality checks will pass.
The implementation reads one file fully into memory; it is intended for these small supplied datasets.

## Verification

Executed on 2026-10-11 with Python 3.14.3, Pandas 3.0.6 and pytest 9.1.1 in the project `.venv`.
All 17 tests passed. The real-data CLI returned 0: six files passed, with one missing-final-newline warning
for `PX_CAT_G1V2.csv`; all 37 category records were counted. The six counts match the final Phase 1C
Bronze counts and all source SHA-256 hashes are unchanged. Separate CLI processes on temporary files
confirmed success exit code 0 and failure exit code 1, with all files processed.
The complete results are in the [README](../README.md) and the ignored local report
`reports/phase2a.validation.json`. No database connection was made.
