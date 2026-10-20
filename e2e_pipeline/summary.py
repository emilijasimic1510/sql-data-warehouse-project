"""Aggregate analytics only; unknown sales are retained in total revenue."""

from decimal import Decimal


def collect_summary(cursor):
    rows, quantity, revenue = cursor.execute(
        "SELECT COUNT_BIG(*),COALESCE(SUM(CAST(quantity AS decimal(38,0))),0),"
        "COALESCE(SUM(CAST(sales_amount AS decimal(38,2))),0) FROM mart.fact_sales").fetchone()
    coverage = cursor.execute(
        "SELECT COALESCE(SUM(CASE WHEN f.product_key>0 THEN CAST(1 AS bigint) ELSE 0 END),0),"
        "COALESCE(SUM(CASE WHEN f.product_key>0 AND p.is_current=0 THEN CAST(1 AS bigint) ELSE 0 END),0) "
        "FROM mart.fact_sales f JOIN mart.dim_product p ON p.product_key=f.product_key").fetchone()
    unknown = [dict(reason=r[0], rows=r[1], quantity=int(r[2]), revenue=format(r[3], ".2f"))
               for r in cursor.execute(
                   "SELECT product_match_reason,COUNT_BIG(*),SUM(CAST(quantity AS decimal(38,0))),"
                   "SUM(CAST(sales_amount AS decimal(38,2))) FROM mart.fact_sales WHERE product_key=0 "
                   "GROUP BY product_match_reason ORDER BY product_match_reason").fetchall()]
    return dict(sales_rows=rows, quantity=int(quantity), revenue=format(revenue, ".2f"),
                matched_product_rows=coverage[0], historical_product_rows=coverage[1],
                current_product_rows=coverage[0] - coverage[1], unknown_product_rows=rows - coverage[0],
                historical_share_of_all_sales_pct=format(Decimal(coverage[1]) * 100 / rows, ".2f") if rows else "0.00",
                unknown_by_reason=unknown,
                unknown_policy="Unknown products remain included in total revenue; reliable historical attributes and cost are unavailable.")
