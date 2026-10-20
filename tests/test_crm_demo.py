"""Fixture contract and independent in-memory expectation checks; no SQL integration claims."""

import copy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from crm_demo.__main__ import main
from crm_demo.config import COLUMNS, CRM_COLUMNS, ID_MIN, PACKAGE_DIRS, PROJECT_ROOT
from crm_demo.generator import batch_id, build_suite, csv_bytes, generate, json_bytes, sha256
from crm_demo.validation import validate_csv, validate_package, verify_suite


def files_in(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def records(content):
    return list(csv.DictReader(io.StringIO(content.decode("utf-8"), newline="")))


def write_package(path, rows):
    path.mkdir()
    content = csv_bytes(rows)
    manifest = json.loads(build_suite()["01_changes/manifest.json"])
    manifest.update(record_count=len(rows), sha256=sha256(content), batch_id=batch_id("delta", sha256(content)))
    (path / "customers.csv").write_bytes(content)
    (path / "manifest.json").write_bytes(json_bytes(manifest))
    return path


@pytest.mark.parametrize("seed,start", [(42, "2026-01-01"), (0, "2024-02-27"), (-9, "2027-12-29")])
def test_identical_seed_and_parameters_give_identical_artifacts(tmp_path, seed, start):
    first = generate(tmp_path / "a", seed, start)
    second = generate(tmp_path / "b", seed, start)
    assert files_in(first) == files_in(second)
    assert verify_suite(first)["status"] == "PASS"


def test_deterministic_across_process_hash_seed_and_without_site_packages(tmp_path):
    expected = build_suite(17)
    # -S disables installed site packages: the generator requires only the standard library.
    result = subprocess.run([sys.executable, "-S", "-m", "crm_demo", "generate", "--seed", "17",
                             "--output-dir", str(tmp_path / "separate")], cwd=PROJECT_ROOT,
                            env={**os.environ, "PYTHONHASHSEED": "73"}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert files_in(tmp_path / "separate") == expected


def test_seed_and_start_date_change_events_and_manifests():
    original = build_suite(42)
    for changed in (build_suite(43), build_suite(42, "2026-02-01")):
        assert original["00_snapshot/customers.csv"] != changed["00_snapshot/customers.csv"]
        assert original["00_snapshot/manifest.json"] != changed["00_snapshot/manifest.json"]


def test_every_manifest_matches_actual_bytes_and_replay_identity():
    files = build_suite()
    for directory in PACKAGE_DIRS:
        data = files[f"{directory}/customers.csv"]
        manifest = json.loads(files[f"{directory}/manifest.json"])
        assert manifest["sha256"] == hashlib.sha256(data).hexdigest()
        assert manifest["record_count"] == len(records(data))
        assert manifest["batch_id"] == batch_id(manifest["package_type"], manifest["sha256"])
    for name in ("customers.csv", "manifest.json"):
        assert files[f"01_changes/{name}"] == files[f"05_replay/{name}"]


def test_positive_packages_pass_negative_contract_fails(tmp_path):
    root = generate(tmp_path / "demo")
    for directory in PACKAGE_DIRS[:-1]:
        result = validate_package(root / directory)
        assert result["status"] == "PASS", result
        assert not result["structure_errors"]
    result = validate_package(root / "06_negative")
    assert result["status"] == "FAIL"
    assert result["structure_errors"] == result["integrity_errors"] == []
    assert result["contract_errors"] == ["row 2: cst_id must be a demo integer"]
    assert verify_suite(root)["status"] == "PASS"  # suite explicitly expects this one rejection


def test_repeat_event_is_not_a_structure_or_contract_error(tmp_path):
    row = records(build_suite()["01_changes/customers.csv"])[0]
    result = validate_package(write_package(tmp_path / "repeat", [row, row]))
    assert result["status"] == "PASS" and result["repeated_event_rows"] == 1


@pytest.mark.parametrize("field,value", [
    ("event_id", ""), ("source_updated_at", "2026-01-01T09:00:00+01:00"),
    ("source_updated_at", "2026-02-30T09:00:00Z"), ("cst_create_date", "2026-02-30"),
    ("cst_create_date", "2027-01-01"), ("cst_id", "2147483648"),
    ("cst_key", "real-customer"), ("cst_firstname", "NotDemo"),
    ("cst_lastname", "DemoFamily_" + "x" * 50), ("cst_marital_status", "bad"),
])
def test_contract_types_and_domains(field, value):
    rows = records(build_suite()["00_snapshot/customers.csv"])
    rows[0][field] = value
    result = validate_csv(csv_bytes(rows))
    assert result["structure_errors"] == []
    assert result["contract_errors"]


@pytest.mark.parametrize("damage", ["header", "width", "quotes", "encoding", "empty"])
def test_structural_errors_are_separate(damage):
    content = build_suite()["00_snapshot/customers.csv"]
    if damage == "header":
        content = content.replace(b"event_id", b"wrong_id", 1)
    elif damage == "width":
        content += b"short,row\n"
    elif damage == "quotes":
        content += b'"unterminated\n'
    elif damage == "encoding":
        content += b"\xff\n"
    else:
        content = b""
    assert validate_csv(content)["structure_errors"]


@pytest.mark.parametrize("damage", ["data", "count", "batch_id", "missing", "manifest"])
def test_integrity_failures(tmp_path, damage):
    root = generate(tmp_path / "demo")
    package = root / "01_changes"
    path = package / "manifest.json"
    if damage == "data":
        data = package / "customers.csv"
        data.write_bytes(data.read_bytes().replace(b"DemoFamily", b"DemoFamilyX", 1))
    elif damage in ("count", "batch_id"):
        manifest = json.loads(path.read_bytes())
        manifest["record_count" if damage == "count" else "batch_id"] = 999
        path.write_bytes(json_bytes(manifest))
    elif damage == "missing":
        path.unlink()
    else:
        path.write_text("[]", encoding="utf-8")
    assert validate_package(package)["status"] == "FAIL"
    assert verify_suite(root)["status"] == "FAIL"


def test_edited_expectations_cannot_turn_failure_into_success(tmp_path):
    root = generate(tmp_path / "demo")
    path = root / "expectations.json"
    spec = json.loads(path.read_bytes())
    spec["deliveries"][1]["updated"] = []
    path.write_bytes(json_bytes(spec))
    assert verify_suite(root)["status"] == "FAIL"


def test_unique_event_ids_identify_immutable_payloads():
    seen = {}
    for directory in PACKAGE_DIRS[:-1]:
        for row in records(build_suite()[f"{directory}/customers.csv"]):
            identity = row["event_id"]
            if identity in seen:
                assert row == seen[identity]
            seen[identity] = row
    assert len(seen) == 12


def business(row):
    return {k: row[k] for k in CRM_COLUMNS}


@pytest.mark.parametrize("seed", [42, 0, -9])
def test_explicit_expectations_match_independent_reference_rules(seed):
    """Test-only interpreter, not an incremental loader or database integration test."""
    files = build_suite(seed)
    spec = json.loads(files["expectations.json"])
    state, events, batches = {}, {}, set()
    for delivery in spec["deliveries"]:
        before = copy.deepcopy(state)
        rows = records(files[delivery["directory"] + "/customers.csv"])
        outcomes = []
        for row in sorted(rows, key=lambda r: (r["source_updated_at"], r["event_id"])):
            key, event_id = row["cst_id"], row["event_id"]
            if not delivery["expected_valid"]:
                action = "reject"
            elif delivery["batch_id"] in batches:
                action = "batch_replay"
            elif event_id in events:
                assert events[event_id] == row
                action = "duplicate"
            elif key not in state:
                action = "insert"
                state[key] = row
            elif row["source_updated_at"] < state[key]["source_updated_at"]:
                action = "stale"
            else:
                assert row["source_updated_at"] > state[key]["source_updated_at"]
                action = "no_change" if business(row) == business(state[key]) else "update"
                state[key] = row  # even a no-op advances the accepted source version
            outcomes.append(dict(cst_id=key, event_id=event_id, action=action))
            if action not in ("reject", "batch_replay"):
                events[event_id] = row
        if delivery["expected_valid"]:
            batches.add(delivery["batch_id"])
        order = lambda x: x["event_id"]
        assert sorted(outcomes, key=order) == sorted(delivery["event_outcomes"], key=order)
        assert sorted(state.values(), key=lambda x: x["cst_id"]) == delivery["expected_source_state"]
        inserted = sorted(set(state) - set(before))
        updated = sorted(k for k in before if business(before[k]) != business(state[k]))
        unchanged = sorted(set(state) - set(inserted) - set(updated))
        assert (inserted, updated, unchanged) == (delivery["inserted"], delivery["updated"], delivery["unchanged"])
    assert len(state) == 5
    assert state[str(ID_MIN + 1)]["cst_lastname"].endswith("_v4")
    assert state[str(ID_MIN + 2)]["cst_marital_status"] == "M"


def test_late_delivery_demonstrates_global_watermark_loss():
    files = build_suite()
    spec = json.loads(files["expectations.json"])
    previous = {r["cst_id"]: r for r in spec["deliveries"][2]["expected_source_state"]}
    global_max = max(r["source_updated_at"] for r in previous.values())
    late_rows = records(files["03_late_arrival/customers.csv"])[1:]
    assert all(r["source_updated_at"] < global_max for r in late_rows)
    assert late_rows[0]["cst_id"] not in previous
    assert late_rows[1]["source_updated_at"] > previous[late_rows[1]["cst_id"]]["source_updated_at"]
    versions = records(files["02_versions/customers.csv"])
    assert versions[0]["source_updated_at"] > versions[1]["source_updated_at"]
    assert len({r["cst_create_date"] for r in versions}) == 1


def test_original_sources_and_full_load_code_stay_unchanged(tmp_path):
    from csv_validation.config import EXPECTED_FILES
    paths = [PROJECT_ROOT / "datasets" / name for name in EXPECTED_FILES]
    for directory in ("csv_validation", "warehouse_pipeline", "scripts"):
        paths += [p for p in (PROJECT_ROOT / directory).rglob("*") if p.suffix in (".py", ".sql")]
    before = {p: p.read_bytes() for p in paths}
    original_config = copy.deepcopy(EXPECTED_FILES)
    root = generate(tmp_path / "demo")
    assert verify_suite(root)["status"] == "PASS"
    assert before == {p: p.read_bytes() for p in paths}
    assert EXPECTED_FILES == original_config and len(EXPECTED_FILES) == 6
    assert tuple(EXPECTED_FILES["source_crm/cust_info.csv"]) == CRM_COLUMNS
    with (PROJECT_ROOT / "datasets/source_crm/cust_info.csv").open(encoding="utf-8-sig", newline="") as handle:
        original_ids = {r["cst_id"] for r in csv.DictReader(handle)}
    generated_ids = {r["cst_id"] for r in records(build_suite()["00_snapshot/customers.csv"])}
    assert original_ids.isdisjoint(generated_ids)


@pytest.mark.parametrize("folder", ["datasets", "scripts", "warehouse_pipeline", "csv_validation", ".git"])
def test_protected_output_paths_rejected(folder):
    with pytest.raises(ValueError):
        generate(PROJECT_ROOT / folder / "never-created-demo")
    assert not (PROJECT_ROOT / folder / "never-created-demo").exists()


def test_existing_directory_never_overwritten(tmp_path):
    root = generate(tmp_path / "demo")
    before = files_in(root)
    with pytest.raises(FileExistsError):
        generate(root, seed=99)
    assert files_in(root) == before


def test_cli_generate_verify_and_negative_exit(tmp_path, capsys):
    root = tmp_path / "cli"
    assert main(["generate", "--output-dir", str(root), "--seed", "42"]) == 0
    assert main(["verify", "--output-dir", str(root)]) == 0
    assert main(["validate", "--package-dir", str(root / "06_negative")]) == 1
    assert main(["generate", "--output-dir", str(root)]) == 1
    assert main(["verify", "--output-dir", str(tmp_path / "missing")]) == 1
    assert "SYNTHETIC CRM DEMO" in capsys.readouterr().out


def test_bad_date_does_not_create_output(tmp_path):
    root = tmp_path / "bad"
    assert main(["generate", "--output-dir", str(root), "--start-date", "not-a-date"]) == 1
    assert not root.exists()
