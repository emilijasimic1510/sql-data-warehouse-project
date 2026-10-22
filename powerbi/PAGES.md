# Report page specification

The four pages below describe the full reference report. Check the saved PBIX/PBIP for the pages and measures currently implemented.

Use a 16:9 canvas, a light background, and the [report theme](sales-reliability.theme.json). Show filter context and brief explanatory footnotes. Amounts have two decimals and no currency symbol. Label unknown values explicitly rather than relying on color alone.

## Sales Overview

Show sales volume and dated sales trends.

| Visual | Fields or measures |
| --- | --- |
| KPI cards | Sales Amount, Orders, Quantity, Average Order Value |
| Monthly line chart | Calendar.Year Month, Sales Amount; Orders and Sales MoM Rate in tooltips |
| Yearly matrix | Calendar.Year, Sales Amount, Sales YoY Rate |
| Undated cards | Sales Without Order Date, Sales Amount Without Order Date |
| Slicers | Calendar and current customer country; start with all dates |

The trend excludes unknown order dates. Label the undated cards "All dates / undated" and BLANK period comparisons "Not comparable". Avoid a relative-date filter based on today for this historical dataset.

## Products & Markets

Show contributions by historical product category and current customer country.

| Visual | Fields or measures |
| --- | --- |
| KPI cards | Sales Amount, Unknown Product Sales Amount, Unknown Product Sales Rate |
| Category bar chart | Product category label, Sales Amount, including Unknown historical category |
| Country chart | Current customer country, Sales Amount |
| Unknown-reason table | `product_match_reason`, Sales Rows, Sales Amount; filter `product_key=0` |
| Slicers | Calendar, category label, current customer country |

Unknown means a missing historical relationship, not necessarily an unidentified product. Country reflects current customer data. Do not label it purchase location or estimate historical margin from current product cost.

## Customers

Show purchasing customers and repeat orders within the selection.

| Visual | Fields or measures |
| --- | --- |
| KPI cards | Purchasing Customers, Repeat Customers, Repeat Customer Rate |
| Country matrix | Orders, Purchasing Customers, Repeat Customers, Repeat Customer Rate, Average Order Value |
| Slicers | Calendar, current customer country, category label |

Repeat means at least two distinct orders with visible lines in the same selection. Exclude unknown customer key 0 from customer counts. Recalculate totals rather than adding distinct counts across groups. Names and birthdates are unnecessary for these visuals.

## Data Reliability

Show the latest run, confirmed mart completion, and source limitations.

| Visual | Fields or measures |
| --- | --- |
| Operational cards | Latest E2E Status, Last Successful E2E UTC, Last Successful E2E Seconds, Last Confirmed Mart Completion UTC |
| Refresh timestamp | BI Refresh Observed UTC |
| Run family table | Parent/child status and start/end times |
| Step and quality tables | Step status/duration; check severity, status, anomaly count, and metric value |
| Data limitations | Unknown-product amount and undated sales |

Keep operational cards independent of business slicers. Label timestamps UTC and mart completion as a proxy. Warehouse audit quality rows do not contain every mart check; use the child JSON and reconciliation SQL for mart details. RUNNING is an unconfirmed completion, and FAIL does not imply a global rollback.
