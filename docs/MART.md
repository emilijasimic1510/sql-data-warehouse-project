# Sales mart

The `mart` schema stores physical dimensions and sales facts from Silver. Gold remains a set of current-state analytical views. The incremental CRM demo is not a mart source.

## Tables

| Table | Grain and key | Load behavior |
| --- | --- | --- |
| `mart.dim_customer` | One CRM `cst_id`; persistent `customer_key` | SCD Type 1, enriched with ERP attributes |
| `mart.dim_product` | One `(product_number, valid_from)` version; persistent `product_key` | Imports product history already present in Silver |
| `mart.dim_date` | One date; `YYYYMMDD` key | Extends to cover order, shipping, and due dates |
| `mart.fact_sales` | One Silver sales record, preserving duplicates | Full refresh; `fact_key` is a technical identity |

`order_number` is not a line identifier. The source does not provide a stable sales line ID, so the loader preserves row multiplicity rather than inventing an incremental key. Amounts and prices use `DECIMAL(19,2)`; quantity uses `BIGINT`. The source provides no currency metadata.

## Product history and unknown members

Product intervals include both `valid_from` and `valid_to`; a NULL end is open-ended. Silver ends a version on the day before the next version starts. Overlapping intervals or duplicate version keys fail the load. Changing a version's end or attributes preserves its key; changing its start identifies a different version.

Dimensions missing from a later source load retain their keys with `is_in_source=0` and are excluded from new sales mapping. Keys are not recycled. Customer attributes reflect current values, not historical customer geography.

Each dimension reserves key **0** for unknown values. The unknown date has NULL date attributes.

| Condition | Mapping |
| --- | --- |
| Missing order date | Unknown order date and product; `MISSING_ORDER_DATE` |
| Product exists but no version covers the order date | Unknown product; `BEFORE_HISTORY`, `AFTER_HISTORY`, or `INTERVAL_GAP` |
| Missing product key | Unknown product; `MISSING_PRODUCT_KEY` |
| Missing or unmatched customer | Unknown customer; `MISSING_CUSTOMER_KEY` or `NOT_IN_SOURCE` |
| Missing shipping/due date | Unknown member for that date role |

Unknown rows remain in sales totals and produce warnings. Ambiguous matches fail loading. Current product attributes are not substituted for missing history.

## Deployment and loading

```powershell
$target = @('--server', '.\SQLEXPRESS', '--expected-server', 'YOUR-PC\SQLEXPRESS', '--database', 'DataWarehouse')
.\.venv\Scripts\python.exe -m mart_pipeline.deploy @target
.\.venv\Scripts\python.exe -m mart_pipeline --dry-run
.\.venv\Scripts\python.exe -m mart_pipeline @target --execute --report-path ('.\reports\mart-' + [guid]::NewGuid() + '.json')
```

Deployment runs `scripts/mart/schema.sql`, `load.sql`, and `quality.sql` in one transaction. Repeat deployment checks the contract, metadata signature, and source hashes; schema drift requires an explicit migration. Use the deployment wrapper rather than running its files separately.

Normal loading acquires the shared project lock, opens a SERIALIZABLE transaction, updates dimensions, replaces facts, and runs reconciliation before commit. Any critical finding rolls back the mart transaction. A later JSON failure cannot undo a completed commit. See [end-to-end recovery](E2E_PIPELINE.md).

## Quality checks

`mart.check_quality` is the SQL registry used by both the loader and manual inspection.

- M01–M08 check keys, foreign keys, intervals, temporal joins, and date mapping.
- M09–M11 reconcile row count, quantity, and amount with Silver.
- M12 compares all nine business fields as multisets, including duplicate counts.
- M13–M14 check unknown members and dimension counts.
- U01–U09 report unknown members and reasons as warnings.
- R01–R02 return quantity and amount metrics.

```sql
USE DataWarehouse;
EXEC mart.check_quality;
SELECT product_match_reason, COUNT_BIG(*) AS sales_rows, SUM(sales_amount) AS amount
FROM mart.fact_sales GROUP BY product_match_reason;
```

Read-only analysis and reconciliation queries are also in [powerbi/sql](../powerbi/sql).
