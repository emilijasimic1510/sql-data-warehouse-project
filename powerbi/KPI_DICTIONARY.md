# KPI definitions

Reference measures are in [measures.dax](measures.dax). Business measures respect Calendar, customer, and product filters unless stated otherwise. Compare SQL and DAX under the same selection.

| Measure | Definition |
| --- | --- |
| Sales Amount | Sum of visible `sales_amount` |
| Quantity | Sum of visible `quantity`; saved PBIP measure is named Total Quantity |
| Sales Rows | Count of visible fact rows |
| Orders | Distinct `order_number`, not number of lines |
| Average Order Value | Sales Amount / Orders in the same context |
| Purchasing Customers | Distinct customers with visible sales and `customer_key > 0` |
| Repeat Customers | Customers with at least two distinct orders in the current selection |
| Repeat Customer Rate | Repeat Customers / Purchasing Customers |
| Sales MoM Rate | Full-month change from the preceding supported month |
| Sales YoY Rate | Full-year change from the preceding supported year |
| Unknown Product Sales Amount | Visible amount where `product_key = 0` |
| Unknown Product Sales Rate | Unknown amount / total visible amount, including unknown |
| Sales Without Order Date | Rows with `order_date_key = 0`; ignores Calendar, retains customer/product filters |
| Sales Amount Without Order Date | Amount for those same undated rows |
| Sales by Shipping/Due Date | Sales Amount through the corresponding inactive Calendar relationship |
| Last Confirmed Mart Completion UTC | Latest successful mart execute completion, used as a publication proxy |
| Last Successful E2E UTC | Completion of the latest successful E2E execute run |
| Last Successful E2E Seconds | End minus start for that run, not a sum of child durations |
| Latest E2E Status / Started UTC | Latest attempt, including failures |
| BI Refresh Observed UTC | `SYSUTCDATETIME()` observed by the import query |

Use two decimals for amounts, no currency symbol; whole numbers for counts; two decimal places for percentages; and three for duration in seconds. SQL all-time percentage columns use 0–100, while DAX rates and period-comparison SQL use 0–1.

Sales Amount is not profit or a defined net/gross measure. Current customer country is not necessarily the purchase location. Repeat Customer Rate is not retention or churn. Orders, customers, averages, and rates are non-additive: totals must recalculate the measure. A missing denominator produces BLANK; an empty unknown numerator is zero.

## Period coverage

MoM requires a complete selected calendar month; YoY requires a complete selected year. Both the current and preceding periods must lie strictly inside the global observed order-date range, independent of business slicers. Partial selections, boundary periods, and multi-year totals return BLANK.

The source has no completeness watermark. Interior periods are supported by the observed date range but are not guaranteed complete. Label BLANK comparisons "Not comparable", not 0%.

## SQL references

- [01_kpis.sql](sql/01_kpis.sql): amounts, counts, repeat customers, unknown sales, and monthly totals.
- [04_period_comparisons.sql](sql/04_period_comparisons.sql): month/year coverage and comparisons.
- [02_audit.sql](sql/02_audit.sql) and [05_audit_import.sql](sql/05_audit_import.sql): operational metrics.

Date filters use `source_order_date >= @start AND source_order_date < @end_exclusive`. Apply country/category filters before aggregation, using the same labels as [business imports](sql/06_business_import.sql). Round only for display.
