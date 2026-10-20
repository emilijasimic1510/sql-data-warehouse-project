"""Explicit source headers, in the positional order used by Bronze BULK INSERT.

ERP headers are uppercase in the files; their order matches the lowercase DDL.
Update this contract deliberately when a source schema changes.
"""

EXPECTED_FILES = {
    "source_crm/cust_info.csv": [
        "cst_id", "cst_key", "cst_firstname", "cst_lastname",
        "cst_marital_status", "cst_gndr", "cst_create_date",
    ],
    "source_crm/prd_info.csv": [
        "prd_id", "prd_key", "prd_nm", "prd_cost", "prd_line",
        "prd_start_dt", "prd_end_dt",
    ],
    "source_crm/sales_details.csv": [
        "sls_ord_num", "sls_prd_key", "sls_cust_id", "sls_order_dt",
        "sls_ship_dt", "sls_due_dt", "sls_sales", "sls_quantity", "sls_price",
    ],
    "source_erp/CUST_AZ12.csv": ["CID", "BDATE", "GEN"],
    "source_erp/LOC_A101.csv": ["CID", "CNTRY"],
    "source_erp/PX_CAT_G1V2.csv": ["ID", "CAT", "SUBCAT", "MAINTENANCE"],
}
