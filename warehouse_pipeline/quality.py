"""Canonical quality rules. SSMS scripts are generated from this registry."""

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from .reporting import safe_error


@dataclass(frozen=True)
class Check:
    check_id: str
    description: str
    object: str
    sql: str
    severity: str = "ERROR"
    expectation: str = "Zero anomalies"
    rule: str = "zero"

    @property
    def layer(self):
        return self.object.split(".")[0]


def rows(check_id, description, obj, predicate, severity="ERROR"):
    return Check(check_id, description, obj,
                 f"SELECT COUNT_BIG(*) FROM {obj} WHERE {predicate}", severity)


def keys(check_id, obj, column, nulls=False):
    predicate = f"COUNT_BIG(*) > 1" + (f" OR {column} IS NULL" if nulls else "")
    return Check(check_id, f"Duplicate{' or NULL' if nulls else ''} {column} groups", obj,
                 f"SELECT COUNT_BIG(*) FROM (SELECT {column} FROM {obj} "
                 f"GROUP BY {column} HAVING {predicate}) AS anomalies")


def domain(check_id, obj, column, values, severity="ERROR"):
    literals = ", ".join("N'" + value.replace("'", "''") + "'" for value in values)
    return rows(check_id, f"{column} must be one of {', '.join(values)} (NULL invalid)", obj,
                f"{column} IS NULL OR {column} NOT IN ({literals})", severity)


CHECKS = (
    keys("S01", "silver.crm_cust_info", "cst_id", True),
    rows("S02", "Customer key has outer spaces", "silver.crm_cust_info",
         "DATALENGTH(cst_key) != DATALENGTH(TRIM(cst_key))"),
    domain("S03", "silver.crm_cust_info", "cst_marital_status", ("Single", "Married", "n/a")),
    keys("S04", "silver.crm_product_info", "prd_id", True),
    rows("S05", "Product name has outer spaces", "silver.crm_product_info",
         "DATALENGTH(prd_nm) != DATALENGTH(TRIM(prd_nm))"),
    rows("S06", "NULL or negative product cost", "silver.crm_product_info", "prd_cost < 0 OR prd_cost IS NULL"),
    domain("S07", "silver.crm_product_info", "prd_line", ("Mountain", "Road", "Other Sales", "Touring", "n/a")),
    rows("S08", "Product end precedes start", "silver.crm_product_info", "prd_end_dt < prd_start_dt"),
    rows("S09", "Source due date numeric shape/range (not calendar validity)", "bronze.crm_sales_info",
         "sls_due_dt <= 0 OR LEN(sls_due_dt) != 8 OR sls_due_dt > 20500101 OR sls_due_dt < 19000101", "WARNING"),
    rows("S10", "Order follows shipping or due date", "silver.crm_sales_info",
         "sls_order_dt > sls_ship_dt OR sls_order_dt > sls_due_dt"),
    rows("S11", "Sales equals quantity times price; all three positive and non-NULL", "silver.crm_sales_info",
         "sls_sales != CAST(sls_quantity AS bigint) * sls_price OR sls_sales IS NULL OR sls_quantity IS NULL "
         "OR sls_price IS NULL OR sls_sales <= 0 OR sls_quantity <= 0 OR sls_price <= 0"),
    rows("S12", "Birthdate before fixed review boundary 1924-01-01", "silver.erp_customer_info",
         "bdate < '19240101'", "WARNING"),
    rows("S12F", "Future birthdate", "silver.erp_customer_info", "bdate > GETDATE()"),
    domain("S13", "silver.erp_customer_info", "gen", ("Female", "Male", "n/a")),
    Check("S14", "Country distinct-value count, including NULL; no closed country domain", "silver.erp_location_info",
          "SELECT COUNT_BIG(*) FROM (SELECT DISTINCT cntry FROM silver.erp_location_info) AS countries",
          "WARNING", "Informational count; no pass/fail threshold", "metric"),
    rows("S15", "Category text has outer spaces", "silver.erp_product_category",
         "DATALENGTH(cat) != DATALENGTH(TRIM(cat)) OR DATALENGTH(subcat) != DATALENGTH(TRIM(subcat)) "
         "OR DATALENGTH(maintenance) != DATALENGTH(TRIM(maintenance))"),
    domain("S16", "silver.erp_product_category", "maintenance", ("Yes", "No"), "WARNING"),
    keys("G01", "gold.dim_customers", "customer_key"),
    keys("G02", "gold.dim_customers", "customer_id"),
    rows("G03", "NULL critical customer fields", "gold.dim_customers",
         "customer_key IS NULL OR customer_id IS NULL OR customer_number IS NULL"),
    keys("G04", "gold.dim_products", "product_key"),
    keys("G05", "gold.dim_products", "product_number"),
    rows("G06", "NULL critical product fields", "gold.dim_products",
         "product_key IS NULL OR product_number IS NULL OR product_id IS NULL"),
    Check("G07", "Sales without customer dimension match", "gold.fact_sales",
          "SELECT COUNT_BIG(*) FROM gold.fact_sales f LEFT JOIN gold.dim_customers c "
          "ON c.customer_key = f.customer_key WHERE c.customer_key IS NULL"),
    Check("G08", "Sales without product dimension match", "gold.fact_sales",
          "SELECT COUNT_BIG(*) FROM gold.fact_sales f LEFT JOIN gold.dim_products p "
          "ON p.product_key = f.product_key WHERE p.product_key IS NULL"),
    rows("G09", "NULL critical sales fields", "gold.fact_sales",
         "order_number IS NULL OR customer_key IS NULL OR product_key IS NULL"),
    rows("G10", "Shipping or due date precedes order", "gold.fact_sales",
         "shipping_date < order_date OR due_date < order_date"),
    rows("G11", "Negative sales, quantity or price", "gold.fact_sales",
         "sales_amount < 0 OR quantity < 0 OR price < 0"),
)

TABLES = ("crm_cust_info", "crm_product_info", "crm_sales_info", "erp_customer_info",
          "erp_location_info", "erp_product_category")
OBJECTS = tuple(f"{layer}.{table}" for layer in ("bronze", "silver") for table in TABLES) + (
    "gold.dim_customers", "gold.dim_products", "gold.fact_sales")


def run_checks(cursor, results):
    """Append each outcome, retaining earlier outcomes if a later query fails."""
    for check in CHECKS:
        start = perf_counter()
        result = dict(check_id=check.check_id, description=check.description, object=check.object,
                      layer=check.layer, severity=check.severity, expectation=check.expectation,
                      rule=check.rule, status="ERROR", anomaly_count=None, metric_value=None, error=None)
        try:
            value = cursor.execute(check.sql).fetchone()[0]
            if not isinstance(value, int) or value < 0:
                raise ValueError("Invalid quality count")
            # A late driver error is also an execution failure, never a pass.
            while cursor.nextset():
                pass
            if check.rule == "metric":
                result.update(status="INFO", metric_value=value)
            else:
                result.update(anomaly_count=value, status=(check.severity if value else "PASS"))
        except Exception as exc:
            result["error"] = safe_error(exc)
        result["duration_seconds"] = round(perf_counter() - start, 6)
        results.append(result)


def collect_counts(cursor, results):
    errors = []
    for obj in OBJECTS:
        try:
            value = cursor.execute(f"SELECT COUNT_BIG(*) FROM {obj}").fetchone()[0]
            if not isinstance(value, int) or value < 0:
                raise ValueError("Invalid row count")
            while cursor.nextset():
                pass
            results[obj] = value
        except Exception as exc:
            results[obj] = None
            errors.append({"object": obj, "error": safe_error(exc)})
    return errors


def render_sql(layer):
    header = "-- GENERATED by python -m warehouse_pipeline.quality; edit quality.py only.\n"
    header += "-- Aggregate SELECTs only. See docs/QUALITY_CHECKS.md for gate semantics.\nUSE DataWarehouse;\nGO\n"
    checks = (c for c in CHECKS if c.check_id.startswith("S" if layer == "silver" else "G"))
    return header + "\n".join(
        f"\n-- {c.check_id} | {c.severity} | {c.object} | {c.description}\n"
        f"-- {c.expectation}; rule={c.rule}\n{c.sql};\n" for c in checks)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    for layer in ("silver", "gold"):
        (root / "tests" / f"quality_checks_{layer}.sql").write_text(render_sql(layer), encoding="utf-8")
