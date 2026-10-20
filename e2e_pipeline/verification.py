"""Explicit read-only multiset snapshots, excluding only expected technical fields."""

import hashlib
import json

from warehouse_pipeline.quality import OBJECTS

CRM_OBJECTS = tuple("crm_incremental." + t for t in ("customers", "staging", "attempts", "batches", "events"))
MART_OBJECTS = tuple("mart." + t for t in ("dim_customer", "dim_product", "dim_date", "fact_sales"))


def fingerprint(cursor, name):
    rows = cursor.execute("SELECT * FROM " + name).fetchall()
    columns = [c[0] for c in cursor.description]
    omit = "dwh_create_date" if name.startswith("silver.") else "fact_key" if name == "mart.fact_sales" else None
    indices = [i for i, c in enumerate(columns) if c != omit]
    encoded = sorted(json.dumps([r[i] for i in indices], default=str, ensure_ascii=False,
                                separators=(",", ":")).encode("utf-8") for r in rows)
    digest = hashlib.sha256()
    for item in encoded:
        digest.update(len(item).to_bytes(8, "big")); digest.update(item)
    return dict(rows=len(rows), sha256=digest.hexdigest(), omitted_column=omit)


def snapshot(cursor):
    return {name: fingerprint(cursor, name) for name in (*OBJECTS, *CRM_OBJECTS, *MART_OBJECTS)}
