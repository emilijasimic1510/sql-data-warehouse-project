# Phase 1C: installation and runtime validation

Completed review: 2026-10-11 (continuation of the installation started in the preceding session).
Target: `DESKTOP-N1402MQ\SQLEXPRESS`, SQL Server `16.0.1000.6`, Windows authentication.
Only the new project database `DataWarehouse` was created/loaded. The second instance, other user databases,
services, global settings, credentials and Git index were not changed. No commit or push was made.

## What actually ran

The preflight SELECT confirmed the exact server name and `DB_ID(N'DataWarehouse') = NULL` before writing.
The installation guard checked those conditions again immediately before setup.
Executed, in order, stopping on SQL errors:

1. `scripts/init_database.sql`
2. `scripts/bronze/ddl_bronze.sql`
3. `scripts/silver/ddl_silver.sql`
4. `scripts/bronze/load_bronze.sql`
5. `scripts/silver/load_silver.sql`
6. `scripts/gold/ddl_gold.sql`
7. `bronze.load_bronze` with the actual dataset root, followed by `silver.load_silver`.
8. Both quality scripts, followed by complete read-only data snapshots.
9. One authorized full Bronze/Silver reload after the CSV line-ending repair below, then both quality
   scripts and complete snapshots again. There were **two full load executions in total**, not three.

The resulting inventory is three project schemas, 12 tables, two procedures and three Gold views.
SQL Server successfully read all six CSV files directly from:

```text
C:\Users\DELL\Desktop\data-warehouse\sql-data-warehouse-project\datasets
```

No filesystem permission changes or service-identity changes were needed.
Successful connections used the approved execution path outside the restricted sandbox.
One intervening read-only command was not executed because automatic approval review hit a usage limit;
it was retried successfully after the user requested continuation.

## Actual defect found and minimal repair

The first procedure executions completed without an SQL error, but CSV reconciliation found two missing
records. Both source files ended with an empty final field and no record terminator. Under the current
BULK INSERT options, the final record was silently skipped:

- `datasets/source_crm/cust_info.csv`: `(NULL, A01Ass, NULL, NULL, NULL, NULL, NULL)`.
- `datasets/source_erp/CUST_AZ12.csv`: `(AW00029483, 1965-06-06, NULL)`.

A temporary-table diagnostic with SQL Server's CSV format reproduced the missing ERP record; no project
rows were changed by that diagnostic. The minimal repair appended **exactly two bytes, CRLF**, to each
of those two source files. Every original byte and every field value was retained. The other four CSVs
remain byte-identical to HEAD. The next load included both records, confirming the effect of the repair.
No procedure, transformation rule, table definition or quality predicate was changed in Phase 1C.

This is a corrected import-completeness defect, not a business-rule adjustment to hide a quality finding.
Future changes to these files should preserve their final record terminators.

## Row counts: first load versus corrected reload

Counts come from reading every row in each table/view; Gold totals were also independently queried with COUNT_BIG.
Final Bronze counts match the CSV record counts excluding headers.

| Object | First | Corrected reload |
| --- | ---: | ---: |
| bronze.crm_cust_info | 18,493 | 18,494 |
| bronze.crm_product_info | 397 | 397 |
| bronze.crm_sales_info | 60,398 | 60,398 |
| bronze.erp_customer_info | 18,483 | 18,484 |
| bronze.erp_location_info | 18,484 | 18,484 |
| bronze.erp_product_category | 37 | 37 |
| silver.crm_cust_info | 18,484 | 18,484 |
| silver.crm_product_info | 397 | 397 |
| silver.crm_sales_info | 60,398 | 60,398 |
| silver.erp_customer_info | 18,483 | 18,484 |
| silver.erp_location_info | 18,484 | 18,484 |
| silver.erp_product_category | 37 | 37 |
| gold.dim_customers | 18,484 | 18,484 |
| gold.dim_products | 295 | 295 |
| gold.fact_sales | 60,398 | 60,398 |

The final CRM customer reduction is explained by four NULL IDs and six excess rows for repeated IDs:
`18,494 - 4 - 6 = 18,484`. Silver retains the latest dated row per non-NULL customer ID.
Gold products exclude 102 historical Silver rows with non-NULL end dates: `397 - 102 = 295`.
Gold customer and sales joins did not increase their input row counts.

## Every Silver check, in script order

The result sets were identical before and after the corrected reload.

| # | Check | Rows / values returned | Classification |
| --- | --- | --- | --- |
| 1 | Customer NULL/duplicate ID | 0 | Pass |
| 2 | Spaces in customer key | 0 | Pass |
| 3 | Marital status DISTINCT | 2: Single, Married | Expected allowed values; pass |
| 4 | Product NULL/duplicate ID | 0 | Pass |
| 5 | Spaces in product name | 0 | Pass |
| 6 | NULL/negative product cost | 0 | Pass |
| 7 | Product line DISTINCT | 5: Mountain, Road, Other Sales, Touring, n/a | Expected allowed values; pass |
| 8 | Product end before start | 0 | Pass |
| 9 | Bronze due-date numeric range/shape | 0 | Pass for this source predicate |
| 10 | Sales order after ship/due date | 0 | Pass |
| 11 | Sales/quantity/price consistency, NULLs and nonpositive values | 0 | Pass |
| 12 | Birthdate before 1924-01-01 or after current server time | 15 distinct dates, all before 1924 | Source-quality finding retained by existing rules; not a clean pass and not an introduced transformation error |
| 13 | Gender DISTINCT | 3: Female, Male, n/a | Expected allowed values; pass |
| 14 | Country DISTINCT | 7: Australia, Canada, France, Germany, United Kingdom, United States, n/a | Expected standardized values; pass |
| 15 | Spaces in category/subcategory/maintenance | 0 | Pass |
| 16 | Maintenance DISTINCT | 2: Yes, No | Expected source values; pass |

All 15 old birthdate rows were matched back to their Bronze customer and original date with a read-only
join. They range from 1916-02-10 to 1923-11-16. The existing Silver rule only nulls future birthdates;
it does not discard dates older than the diagnostic's 1924 boundary. The values were left unchanged.
The individual dates are recorded in [PHASE_1C_RESULTS.json](PHASE_1C_RESULTS.json).

## Every Gold check, in script order

Each query returned **zero rows on both executions**:

| # | Check | Classification |
| --- | --- | --- |
| 1 | Duplicate customer surrogate key | Pass |
| 2 | Duplicate customer natural key | Pass |
| 3 | NULL critical customer fields | Pass |
| 4 | Duplicate product surrogate key | Pass |
| 5 | Duplicate product business key | Pass |
| 6 | NULL critical product fields | Pass |
| 7 | Missing sales-to-customer relationship | Pass |
| 8 | Missing sales-to-product relationship | Pass |
| 9 | NULL critical sales fields | Pass |
| 10 | Shipping/due date before order | Pass |
| 11 | Negative sales/quantity/price | Pass |

These are observed results of manual SELECT diagnostics, not a new automatic pipeline gate. Their
coverage limitations remain those described in [QUALITY_CHECKS.md](QUALITY_CHECKS.md).
The original quality checks did not detect the two omitted CSV records; source reconciliation did.

## Content comparison and repeatability limits

The comparison read **all rows and columns** of all 15 tables/views, excluding only Silver's
`dwh_create_date` because reloads intentionally refresh it. Each row was encoded with explicit NULL
markers and length-prefixed invariant values, sorted ordinally, and saved with duplicate rows retained.
SHA-256 digests of these canonical snapshots were compared, and changed objects were inspected row by row.
This was an ad hoc local validation, not a new ingestion tool or permanent test framework.

Eleven objects had identical complete business content. Exactly four differed:

- `bronze.crm_cust_info`: one added record with NULL ID and key `A01Ass`.
- `bronze.erp_customer_info`: one added `AW00029483` record with birthdate 1965-06-06.
- `silver.erp_customer_info`: that same added customer, with gender normalized to `n/a`.
- `gold.dim_customers`: the existing customer 29483 now has birthdate 1965-06-06 instead of NULL;
  its surrogate key, other fields and total customer count are unchanged.

There were no other observed business-content differences. The added NULL-ID CRM record is excluded
from Silver by the existing rule. All 27 quality result sets also matched between the two executions.
Counts and snapshot digests are preserved in [PHASE_1C_RESULTS.json](PHASE_1C_RESULTS.json).
Raw local snapshots are retained outside the repository in the workspace's `.phase1c-validation` folder.

**Strict repeatability with an unchanged, corrected input was not demonstrated:** the authorized second
full load also validated the EOF repair. It would be inaccurate to call both complete warehouse contents
identical. No third full load was run. A further unchanged-input reload would require additional authorization.
No intentional missing-file/failure test, rollback test or performance benchmark was performed.

## Git and documentation changes

Git index remains absent and was not changed; the earlier deletion/untracked presentation persists.
All original project files remain present after mapping `datasets /` to `datasets/`.
In a future staged diff, four CSV renames have identical bytes and two also contain the two-byte EOF repair.
Historical Phase 1/1B claims of identical CSV contents describe the state at those times, not this final state.

Phase 1C changes are the two CSV terminators, this report and its JSON evidence, README updates, and links
from historical verification/quality documents to these actual runtime results. No SQL business code changed.

## Inspect the data in SSMS

Connect to `DESKTOP-N1402MQ\SQLEXPRESS` using Windows Authentication, open New Query and run:

```sql
USE DataWarehouse;
GO
SELECT TOP (10) * FROM bronze.crm_cust_info ORDER BY cst_id, cst_create_date, cst_key;
SELECT TOP (10) * FROM silver.crm_cust_info ORDER BY cst_id;
SELECT TOP (10) * FROM gold.dim_customers ORDER BY customer_key;
SELECT TOP (10) * FROM gold.dim_products ORDER BY product_key;
SELECT TOP (10) * FROM gold.fact_sales ORDER BY order_number, product_key, customer_key;
```

The Bronze preview can contain dirty/duplicate/NULL-key records by design. SELECT previews and the two
quality scripts do not reload data. Stop after this phase; no later-phase components were introduced.
