"""Read-only helpers for explicit integration verification; never invoked by loading."""

import hashlib
import json

from warehouse_pipeline.quality import OBJECTS
from .inputs import canonical_event


def business_snapshot(cursor):
    result = {}
    for name in OBJECTS:
        rows = cursor.execute(f"SELECT * FROM {name}").fetchall()
        # Retain duplicate rows and every column, including load timestamps and Gold keys.
        encoded = sorted(json.dumps(list(row), default=str, ensure_ascii=False, separators=(",", ":")).encode("utf-8") for row in rows)
        digest = hashlib.sha256()
        for row in encoded:
            digest.update(len(row).to_bytes(8, "big"))
            digest.update(row)
        definition = cursor.execute("SELECT OBJECT_DEFINITION(OBJECT_ID(?))", name).fetchone()[0]
        result[name] = dict(rows=len(rows), sha256=digest.hexdigest(),
                            definition_sha256=hashlib.sha256((definition or "").encode()).hexdigest())
    return result


CUSTOMER_COLUMNS = ("cst_id", "cst_key", "cst_firstname", "cst_lastname", "cst_marital_status", "cst_gndr",
                    "cst_create_date", "source_updated_at", "last_event_id", "business_hash")


def customers(cursor, low=1900000000, high=1900000899):
    rows = cursor.execute("SELECT " + ",".join(CUSTOMER_COLUMNS) +
                          " FROM crm_incremental.customers WHERE cst_id BETWEEN ? AND ? ORDER BY cst_id", low, high).fetchall()
    values = []
    for row in rows:
        item = dict(zip(CUSTOMER_COLUMNS, row))
        item["cst_create_date"] = item["cst_create_date"].isoformat()
        item["business_hash"] = bytes(item["business_hash"])
        values.append(item)
    return values


def expected_customers(rows):
    result = []
    for raw in rows:
        event = canonical_event(raw)
        event["last_event_id"] = event["event_id"]
        result.append({key: event[key] for key in CUSTOMER_COLUMNS})
    return sorted(result, key=lambda row: row["cst_id"])
