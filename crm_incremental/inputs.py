"""Reuse the demo validator over a frozen copy, then canonicalize typed events."""

import csv
import hashlib
import io
import json
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from crm_demo.config import CRM_COLUMNS
from crm_demo.validation import validate_package
from warehouse_pipeline.reporting import PipelineError


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode("utf-8")).digest()


def canonical_event(row):
    source_time = datetime.fromisoformat(row["source_updated_at"].replace("Z", "+00:00"))
    if source_time.tzinfo is None:
        raise ValueError("Source timestamp needs an offset")
    source_time = source_time.astimezone(timezone.utc)
    raw = {key: row[key] for key in CRM_COLUMNS}
    raw["cst_id"] = int(raw["cst_id"])
    raw["cst_create_date"] = date.fromisoformat(raw["cst_create_date"]).isoformat()
    event_hash = digest({"version": 1, "source_updated_at": source_time.isoformat(timespec="microseconds"),
                         "crm": raw})
    values = {**raw, "cst_firstname": raw["cst_firstname"].strip(), "cst_lastname": raw["cst_lastname"].strip(),
              "cst_marital_status": {"S": "Single", "M": "Married"}.get(raw["cst_marital_status"].strip().upper(), "n/a"),
              "cst_gndr": {"F": "Female", "M": "Male"}.get(raw["cst_gndr"].strip().upper(), "n/a")}
    return dict(event_id=row["event_id"], event_hash=event_hash, business_hash=digest(values),
                source_updated_at=source_time.replace(tzinfo=None), **values)


def read_package(path):
    """Freeze both input files BEFORE validation; stage exactly the bytes that passed.

    The existing path-based validator is called on the private temporary copy. This avoids
    duplicating its contract/hash logic or reopening mutable originals after validation.
    """
    root = Path(path)
    content = (root / "customers.csv").read_bytes()
    manifest_bytes = (root / "manifest.json").read_bytes()
    with TemporaryDirectory(prefix="crm-incremental-") as temporary:
        frozen = Path(temporary)
        (frozen / "customers.csv").write_bytes(content)
        (frozen / "manifest.json").write_bytes(manifest_bytes)
        validation = validate_package(frozen)
    try:
        manifest = json.loads(manifest_bytes)
    except (ValueError, UnicodeError):
        manifest = {}
    if not isinstance(manifest, dict):
        manifest = {}
    events = []
    if validation["status"] == "PASS":
        if manifest["package_type"] == "negative":
            raise PipelineError("Negative packages cannot be executed.")
        events = [canonical_event(row) for row in csv.DictReader(io.StringIO(content.decode("utf-8")))]
    return manifest, validation, events
