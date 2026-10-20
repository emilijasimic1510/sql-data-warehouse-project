import copy
import json
from pathlib import Path
from unittest.mock import MagicMock

import pyodbc
import pytest

from crm_demo.generator import generate, build_suite
from crm_incremental import database, runner
from crm_incremental.__main__ import main
from crm_incremental.inputs import canonical_event, read_package
from warehouse_pipeline.connection import Settings


@pytest.fixture
def demo(tmp_path):
    return generate(tmp_path / "demo")


@pytest.fixture
def settings(tmp_path):
    return Settings("host", "DataWarehouse", tmp_path / "datasets", "", expected_server="host")


def test_canonical_event_ignores_dict_order_and_equivalent_time(demo):
    import csv
    with (demo / "00_snapshot/customers.csv").open(newline="") as f:
        row = next(csv.DictReader(f))
    same = dict(reversed(list(row.items())))
    same["source_updated_at"] = "2026-01-01T10:00:00.000000+01:00"
    assert canonical_event(row) == canonical_event(same)
    # Strict v1 CSV validation remains unchanged; canonicalization also supports typed equivalent inputs.
    changed = {**row, "cst_lastname": row["cst_lastname"] + "_new"}
    assert canonical_event(row)["event_hash"] != canonical_event(changed)["event_hash"]


def test_new_event_identity_same_content_has_same_payload_hash(demo):
    _, _, events = read_package(demo / "00_snapshot")
    assert len(events) == 3
    import csv
    rows = list(csv.DictReader((demo / "00_snapshot/customers.csv").read_text().splitlines()))
    raw = rows[0]
    assert canonical_event(raw)["event_hash"] == canonical_event({**raw, "event_id": "evt-" + "f" * 64})["event_hash"]


def test_dry_run_and_negative_never_connect(demo, settings, monkeypatch, tmp_path):
    call = MagicMock()
    monkeypatch.setattr(database, "connect", call)
    report = runner.run(settings, package_dir=demo / "01_changes", report_path=tmp_path / "dry.json")
    assert report["status"] == "PASS" and report["packages"][0]["status"] == "VALIDATED"
    report = runner.run(settings, package_dir=demo / "06_negative", execute=True, report_path=tmp_path / "bad.json")
    assert report["status"] == "FAIL" and report["packages"][0]["status"] == "REJECTED"
    call.assert_not_called()


def test_bad_manifest_no_mutations(demo, settings, monkeypatch):
    path = demo / "01_changes/manifest.json"
    manifest = json.loads(path.read_bytes()); manifest["sha256"] = "0" * 64
    path.write_text(json.dumps(manifest))
    call = MagicMock(); monkeypatch.setattr(runner, "execute_package", call)
    report = runner.run(settings, package_dir=path.parent, execute=True)
    assert report["packages"][0]["status"] == "REJECTED"
    call.assert_not_called()


def test_frozen_input_not_changed_after_validation(demo, monkeypatch):
    import crm_incremental.inputs as inputs
    original = inputs.validate_package
    def validate(frozen):
        result = original(frozen)
        (demo / "00_snapshot/customers.csv").write_bytes(b"changed after read")
        return result
    monkeypatch.setattr(inputs, "validate_package", validate)
    _, validation, events = read_package(demo / "00_snapshot")
    assert validation["status"] == "PASS" and len(events) == 3


@pytest.fixture
def mock_sql(monkeypatch):
    cursor = MagicMock(); cursor.execute.return_value = cursor; cursor.nextset.return_value = False
    cursor.fetchone.return_value = ("APPLIED",3,3,0,3,0,0,0,0)
    connection = MagicMock(autocommit=True); connection.cursor.return_value = cursor
    monkeypatch.setattr(database, "connect", MagicMock(return_value=connection))
    monkeypatch.setattr(database, "check_target", MagicMock(return_value=("host","DataWarehouse")))
    return connection,cursor


def test_single_explicit_transaction_and_parameterized_staging(demo,settings,mock_sql):
    conn, cursor = mock_sql
    manifest,_,events = read_package(demo / "00_snapshot")
    result = database.execute_package(settings,manifest,events)
    assert result["inserted_customers"] == 3
    sql = [c.args[0] for c in cursor.execute.call_args_list]
    assert sum("BEGIN TRANSACTION" in s for s in sql) == 1
    assert sum(s == "COMMIT TRANSACTION;" for s in sql) == 1
    stage = [c.args for c in cursor.execute.call_args_list if c.args[0] == database.STAGE]
    assert len(stage) == 3 and all(len(c)==14 for c in stage)
    conn.commit.assert_not_called(); conn.rollback.assert_not_called()


@pytest.mark.parametrize("failure", ["stage", "procedure", "late"])
def test_failure_rolls_back_and_never_commits(demo,settings,mock_sql,failure):
    conn,cursor = mock_sql
    current = {"sql":""}
    def execute(sql,*args):
        current["sql"] = sql
        if (failure=="stage" and sql==database.STAGE) or (failure=="procedure" and sql.startswith("EXEC crm_")):
            raise pyodbc.Error("42000","SECRET (51111)")
        return cursor
    cursor.execute.side_effect = execute
    def nextset():
        if failure=="late" and current["sql"].startswith("EXEC crm_"):
            raise pyodbc.Error("42000","SECRET late")
        return False
    cursor.nextset.side_effect = nextset
    manifest,_,events=read_package(demo / "00_snapshot")
    with pytest.raises(pyodbc.Error): database.execute_package(settings,manifest,events)
    sql=[c.args[0] for c in cursor.execute.call_args_list]
    assert "IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;" in sql
    assert "COMMIT TRANSACTION;" not in sql
    conn.close.assert_called_once()


def test_target_check_failure_precedes_begin(demo,settings,mock_sql,monkeypatch):
    _,cursor=mock_sql
    monkeypatch.setattr(database,"check_target",MagicMock(side_effect=ValueError("wrong target")))
    manifest,_,events=read_package(demo / "00_snapshot")
    with pytest.raises(ValueError): database.execute_package(settings,manifest,events)
    assert not any("BEGIN TRANSACTION" in c.args[0] for c in cursor.execute.call_args_list)


def test_error_report_keeps_safe_code(demo,settings,tmp_path,monkeypatch):
    monkeypatch.setattr(runner,"execute_package",MagicMock(side_effect=pyodbc.Error("42000","SECRET (51111)")))
    path=tmp_path/"error.json"
    report=runner.run(settings,package_dir=demo/"01_changes",execute=True,report_path=path)
    assert report["status"]=="FAIL"
    assert "51111" in path.read_text() and "SECRET" not in path.read_text()
    assert report["packages"][0]["committed"] is None


def test_existing_report_preserved(demo,settings,tmp_path,monkeypatch):
    path=tmp_path/"old.json"; path.write_text('{"old":true}')
    call=MagicMock(); monkeypatch.setattr(runner,"execute_package",call)
    assert runner.run(settings,package_dir=demo/"01_changes",execute=True,report_path=path)["status"]=="FAIL"
    assert json.loads(path.read_text())=={"old":True}; call.assert_not_called()


def test_suite_orders_packages_stops_at_negative(demo,settings,monkeypatch):
    call=MagicMock(return_value={"status":"APPLIED"}); monkeypatch.setattr(runner,"execute_package",call)
    report=runner.run(settings,suite_dir=demo,execute=True)
    assert call.call_count==6 and len(report["packages"])==7
    assert report["packages"][-1]["status"]=="REJECTED" and report["status"]=="FAIL"


def test_cli_default_is_dry_run(demo,capsys):
    assert main(["--package-dir",str(demo/"00_snapshot")])==0
    assert json.loads(capsys.readouterr().out)["mode"]=="dry-run"


@pytest.mark.parametrize("args", [["--execute","--dry-run"],["--execute"],["--overwrite-report"]])
def test_cli_rejects_ambiguous_or_missing_options(demo,args):
    with pytest.raises(SystemExit) as error:
        main(["--package-dir",str(demo/"00_snapshot"),*args])
    assert error.value.code==2
