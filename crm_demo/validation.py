"""Read-only demo validation. Replays and late timestamps are not CSV corruption."""

import csv
import io
import json
import re
from datetime import date, datetime
from pathlib import Path

from .config import COLUMNS, ID_MAX, ID_MIN, PACKAGE_DIRS, VERSION
from .generator import batch_id, build_suite, sha256


def validate_csv(content):
    result = dict(record_count=None, structure_errors=[], contract_errors=[], repeated_event_rows=0)
    try:
        text = content.decode("utf-8")
        parsed = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    except (UnicodeError, csv.Error):
        result["structure_errors"].append("CSV must be valid UTF-8 with well-formed quoting")
        return result
    if not parsed or parsed[0] != list(COLUMNS):
        result["structure_errors"].append("Header must match the ordered demo columns exactly")
        return result
    result["record_count"] = len(parsed) - 1
    if len(parsed) == 1:
        result["structure_errors"].append("At least one data record is required")
    if not content.endswith(b"\n"):
        result["structure_errors"].append("Demo CSV must end with newline")
    seen = set()
    for line, fields in enumerate(parsed[1:], 2):
        if len(fields) != len(COLUMNS):
            result["structure_errors"].append(f"row {line}: wrong field count")
            continue
        row = dict(zip(COLUMNS, fields))

        def error(message):
            result["contract_errors"].append(f"row {line}: {message}")

        key = row["cst_id"]
        valid_key = bool(re.fullmatch(r"[0-9]{10}", key)) and ID_MIN <= int(key) <= ID_MAX
        if not valid_key:
            error("cst_id must be a demo integer")
        if valid_key and row["cst_key"] != f"DEMOCRM{int(key) - ID_MIN:04d}":
            error("cst_key must match the demo customer number")
        elif not re.fullmatch(r"DEMOCRM[0-9]{4}", row["cst_key"]):
            error("cst_key must be a demo customer number")
        for column, prefix in (("cst_firstname", "DemoFirst_"), ("cst_lastname", "DemoFamily_")):
            value = row[column]
            if not value.startswith(prefix) or len(value) > 50 or not re.fullmatch(r"[A-Za-z0-9_]+", value):
                error(f"{column} must be synthetic ASCII text of at most 50 characters")
        if row["cst_marital_status"] not in ("S", "M", "n/a"):
            error("cst_marital_status must be S, M or n/a")
        if row["cst_gndr"] not in ("F", "M", "n/a"):
            error("cst_gndr must be F, M or n/a")
        event_id = row["event_id"]
        if not re.fullmatch(r"evt-[0-9a-f]{64}", event_id):
            error("event_id must be evt- followed by 64 lowercase hex characters")
        if event_id in seen:
            result["repeated_event_rows"] += 1
        seen.add(event_id)
        created = updated = None
        try:
            created = date.fromisoformat(row["cst_create_date"])
            if created.isoformat() != row["cst_create_date"]:
                raise ValueError
        except ValueError:
            error("cst_create_date must be a valid YYYY-MM-DD date")
        try:
            value = row["source_updated_at"]
            if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value):
                raise ValueError
            updated = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            error("source_updated_at must be a valid UTC YYYY-MM-DDTHH:MM:SSZ timestamp")
        if created and updated and created > updated.date():
            error("customer creation cannot follow source update")
    return result


def validate_package(package_dir):
    """Any invalid package fails, including a manifest labeled 'negative'."""
    root = Path(package_dir)
    result = dict(status="FAIL", record_count=None, structure_errors=[], contract_errors=[],
                  integrity_errors=[], repeated_event_rows=0)
    try:
        content = (root / "customers.csv").read_bytes()
        result.update(validate_csv(content))
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("Manifest must be an object")
        kind = manifest.get("package_type")
        digest = sha256(content)
        if kind not in ("snapshot", "delta", "negative"):
            result["integrity_errors"].append("Unknown package type")
        if type(manifest.get("contract_version")) is not int or manifest["contract_version"] != VERSION:
            result["integrity_errors"].append("Unsupported contract version")
        if manifest.get("simulator") != "SYNTHETIC CRM DEMO ONLY":
            result["integrity_errors"].append("Missing synthetic-demo label")
        if type(manifest.get("seed")) is not int:
            result["integrity_errors"].append("Manifest seed must be an integer")
        start = manifest.get("start_date")
        if not isinstance(start, str) or date.fromisoformat(start).isoformat() != start:
            result["integrity_errors"].append("Manifest start_date must be YYYY-MM-DD")
        if manifest.get("data_file") != "customers.csv":
            result["integrity_errors"].append("Manifest data_file must be customers.csv")
        if type(manifest.get("record_count")) is not int or manifest["record_count"] != result["record_count"]:
            result["integrity_errors"].append("Manifest record count differs from CSV")
        if manifest.get("sha256") != digest:
            result["integrity_errors"].append("Manifest SHA-256 differs from CSV bytes")
        if manifest.get("batch_id") != batch_id(kind, digest):
            result["integrity_errors"].append("Manifest batch_id differs from content identity")
    except (OSError, UnicodeError, ValueError, TypeError):
        result["integrity_errors"].append("Package files unreadable or manifest malformed")
    if not any(result[k] for k in ("structure_errors", "contract_errors", "integrity_errors")):
        result["status"] = "PASS"
    return result


def verify_suite(directory):
    """Verify the specific fixture suite, including its deliberately invalid package.

    Exact specification comparison detects edited expectations, omitted deliveries and seed drift.
    It is not a database integration test or a production event consumer.
    """
    root = Path(directory)
    summary = dict(status="FAIL", packages=[], errors=[])
    try:
        spec = json.loads((root / "expectations.json").read_text(encoding="utf-8"))
        expected_files = build_suite(spec["seed"], spec["start_date"])
        actual_files = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
        if actual_files != set(expected_files):
            summary["errors"].append("Fixture file inventory differs from the versioned specification")
        for name, expected in expected_files.items():
            if (root / name).read_bytes() != expected:
                summary["errors"].append(f"Specification mismatch: {name}")
        for i, name in enumerate(PACKAGE_DIRS):
            result = validate_package(root / name)
            expected_valid = i != 6
            observed_valid = result["status"] == "PASS"
            matches = observed_valid == expected_valid
            if not expected_valid:
                matches = matches and not result["structure_errors"] and not result["integrity_errors"] and (
                    result["contract_errors"] == ["row 2: cst_id must be a demo integer"])
            summary["packages"].append(dict(directory=name, expected_valid=expected_valid,
                                            matches_expectation=matches, **result))
            if not matches:
                summary["errors"].append(f"Unexpected validation outcome: {name}")
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, OverflowError):
        summary["errors"].append("Fixture suite missing, unreadable or malformed")
    if not summary["errors"]:
        summary["status"] = "PASS"
    return summary
