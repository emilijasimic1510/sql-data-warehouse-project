import json
from unittest.mock import MagicMock

import pyodbc
import pytest

from csv_validation.validator import FileResult
from e2e_pipeline import runner
from e2e_pipeline.__main__ import main
from warehouse_pipeline import runner as warehouse
from mart_pipeline import runner as mart
from warehouse_pipeline.connection import Settings
from warehouse_pipeline.coordination import ProjectSession, ACQUIRE, RELEASE


@pytest.fixture
def flow(monkeypatch, tmp_path):
    settings = Settings("host", "DataWarehouse", tmp_path / "datasets", "sql sources", expected_server="host")
    cursor = MagicMock(); cursor.execute.return_value = cursor; cursor.nextset.return_value = False
    cursor.description = [(name,) for name in ("check_id", "severity", "description", "anomaly_count", "metric_value")]
    cursor.fetchall.return_value = [("M12", "ERROR", "Multisets", 0, None), ("U02", "WARNING", "Unknown date", 19, None)]
    current = {"sql": ""}
    def execute(sql, *parameters):
        current["sql"] = sql
        return cursor
    def fetchone():
        if "@@SERVERNAME" in current["sql"]: return ("host", "DataWarehouse")
        if "OBJECT_ID" in current["sql"]: return (1,)
        if current["sql"] in (ACQUIRE, RELEASE): return (0,)
        return (10,)
    cursor.execute.side_effect = execute; cursor.fetchone.side_effect = fetchone
    connection = MagicMock(autocommit=True); connection.cursor.return_value = cursor
    connect = MagicMock(return_value=connection)
    monkeypatch.setattr(warehouse, "connect", connect)
    mart_connect = MagicMock(side_effect=AssertionError("Second connection must not open"))
    monkeypatch.setattr(mart, "connect", mart_connect)
    monkeypatch.setattr(warehouse, "validate_dataset", MagicMock(return_value=[FileResult("source", record_count=1)]))
    def checks(cursor, output):
        output.append(dict(check_id="S12", severity="WARNING", status="WARNING", anomaly_count=15,
                           metric_value=None, duration_seconds=0.01, error=None))
    monkeypatch.setattr(warehouse, "run_checks", checks)
    monkeypatch.setattr(warehouse, "collect_counts", MagicMock(return_value=[]))
    monkeypatch.setattr(runner.audit, "start_run", MagicMock())
    monkeypatch.setattr(runner.audit, "finish_run", MagicMock())
    monkeypatch.setattr(runner.audit, "update_run", MagicMock())
    monkeypatch.setattr(runner, "collect_summary", MagicMock(return_value={"sales_rows": 60398, "revenue": "29356250.00"}))
    return settings, cursor, connection, connect, mart_connect


def commands(cursor): return [c.args[0] for c in cursor.execute.call_args_list]


def test_order_warning_continues_single_connection_and_parent_links(flow, tmp_path):
    settings, cursor, connection, connect, mart_connect = flow
    path = tmp_path / "parent.json"
    report = runner.run(settings, execute=True, report_path=path)
    assert report["status"] == "PASS" and report["audit_status"] == "PASS"
    sql = commands(cursor)
    assert sql.index("EXEC bronze.load_bronze @dataset_root = ?;") < sql.index("EXEC silver.load_silver;") < sql.index("EXEC mart.load_model;")
    assert sql.count(ACQUIRE) == sql.count(RELEASE) == 1
    connect.assert_called_once(); mart_connect.assert_not_called(); connection.close.assert_called_once()
    assert report["coordination"]["status"] == "RELEASED"
    stored = json.loads(path.read_text())
    for name in ("warehouse", "mart"):
        child = stored["children"][name]
        assert child["parent_run_id"] == stored["run_id"]
        assert next(s for s in stored["steps"] if s["name"] == name)["child_run_id"] == child["run_id"]
    assert {f["component"] for f in report["findings"]} == {"warehouse", "mart"}


@pytest.mark.parametrize("failed", ["bronze", "silver", "quality"])
def test_warehouse_failure_skips_mart_releases_lock(flow, monkeypatch, failed):
    settings, cursor, connection, _, _ = flow
    execute = cursor.execute.side_effect
    def fail(sql, *args):
        if sql.startswith("EXEC " + failed + "."):
            raise pyodbc.Error("42000", "PRIVATE source value")
        return execute(sql, *args)
    if failed == "quality":
        def bad(cursor, output):
            output.append(dict(check_id="S01", severity="ERROR", status="ERROR", anomaly_count=1, metric_value=None, duration_seconds=0, error=None))
        monkeypatch.setattr(warehouse, "run_checks", bad)
    else:
        cursor.execute.side_effect = fail
    result = runner.run(settings, execute=True)
    assert result["status"] == "FAIL" and result["failure_stage"] == "warehouse." + failed
    assert result["children"]["mart"] is None
    assert next(s for s in result["steps"] if s["name"] == "mart")["status"] == "SKIPPED"
    assert "EXEC mart.load_model;" not in commands(cursor) and commands(cursor).count(RELEASE) == 1
    assert "PRIVATE" not in json.dumps(result)


def test_mart_failure_parent_fail_warehouse_remains_success(flow):
    settings, cursor, _, _, _ = flow
    execute = cursor.execute.side_effect
    def fail(sql, *args):
        if sql == "EXEC mart.load_model;": raise pyodbc.Error("42000", "PRIVATE (51213)")
        return execute(sql, *args)
    cursor.execute.side_effect = fail
    result = runner.run(settings, execute=True)
    assert result["status"] == "FAIL" and result["failure_stage"] == "mart"
    assert result["children"]["warehouse"]["status"] == "PASS"
    assert result["children"]["mart"]["status"] == "FAIL"
    assert "COMMIT TRANSACTION;" not in commands(cursor) and RELEASE in commands(cursor)


def test_dry_run_has_no_connection_audit_or_summary(flow):
    settings, cursor, _, connect, mart_connect = flow
    result = runner.run(settings)
    assert result["status"] == "PASS" and result["audit_status"] == "NOT_APPLICABLE"
    connect.assert_not_called(); mart_connect.assert_not_called(); cursor.execute.assert_not_called()
    assert result["summary"] is None and result["children"]["mart"]["committed"] is False


def test_invalid_csv_never_connects(flow, monkeypatch):
    settings, _, _, connect, _ = flow
    monkeypatch.setattr(warehouse, "validate_dataset", lambda root: [FileResult("source", errors=["bad"] )])
    result = runner.run(settings, execute=True)
    assert result["failure_stage"] == "warehouse.validation" and result["children"]["mart"] is None
    connect.assert_not_called()


def test_busy_lock_stops_before_audit_and_load(flow):
    settings, cursor, _, _, _ = flow
    original = cursor.fetchone.side_effect
    def fetch():
        last = cursor.execute.call_args.args[0]
        return (-1,) if last == ACQUIRE else original()
    cursor.fetchone.side_effect = fetch
    result = runner.run(settings, execute=True, lock_timeout_ms=0)
    assert result["status"] == "FAIL" and result["failure_stage"] == "warehouse.coordination"
    assert not any(s.startswith("EXEC bronze") for s in commands(cursor))


def test_report_existing_prevents_work(flow, tmp_path):
    settings, _, _, connect, _ = flow
    path = tmp_path / "old.json"; path.write_text('{"old":true}')
    result = runner.run(settings, execute=True, report_path=path)
    assert result["status"] == "FAIL" and json.loads(path.read_text()) == {"old":True}
    connect.assert_not_called()


def test_parent_audit_failure_is_fail_after_committed_mart(flow, monkeypatch):
    settings, _, _, _, _ = flow
    calls = {"n": 0}
    def finish(cursor, report):
        if report.get("component") == "e2e": raise pyodbc.Error("42000", "PRIVATE audit")
    monkeypatch.setattr(runner.audit, "finish_run", finish)
    result = runner.run(settings, execute=True)
    assert result["status"] == "FAIL" and result["failure_stage"] == "audit"
    assert result["children"]["mart"]["committed"] is True and result["audit_errors"]
    assert result["coordination"]["status"] == "RELEASED"


def test_release_error_closes_connection_and_fails_parent(flow):
    settings, cursor, connection, _, _ = flow
    original = cursor.execute.side_effect
    def execute(sql, *args):
        if sql == RELEASE: raise pyodbc.Error("08003", "PRIVATE disconnection")
        return original(sql, *args)
    cursor.execute.side_effect = execute
    result = runner.run(settings, execute=True)
    assert result["status"] == "FAIL" and result["failure_stage"] == "coordination_release"
    connection.close.assert_called_once()


@pytest.mark.parametrize("component", ["warehouse", "mart"])
def test_standalone_writers_take_same_project_lock_before_mutation(flow, monkeypatch, component):
    settings, cursor, _, connect, _ = flow
    if component == "warehouse":
        result = warehouse.run_report(settings, execute=True)
        mutation = "EXEC bronze.load_bronze @dataset_root = ?;"
    else:
        monkeypatch.setattr(mart, "connect", connect)
        result = mart.run(settings, execute=True)
        mutation = mart.BEGIN
    assert result["status"] == "PASS"
    sql = commands(cursor)
    assert sql.index(ACQUIRE) < sql.index(mutation) < sql.index(RELEASE)
    assert sql.count(ACQUIRE) == sql.count(RELEASE) == 1


def test_summary_keeps_unknown_in_total_revenue():
    from decimal import Decimal
    from e2e_pipeline.summary import collect_summary
    cursor = MagicMock(); cursor.execute.return_value = cursor
    cursor.fetchone.side_effect = [(10, Decimal(12), Decimal("100.00")), (8, 3)]
    cursor.fetchall.return_value = [("BEFORE_HISTORY", 1, Decimal(1), Decimal("20.00")),
                                   ("MISSING_ORDER_DATE", 1, Decimal(1), Decimal("5.00"))]
    result = collect_summary(cursor)
    assert result["revenue"] == "100.00" and result["unknown_product_rows"] == 2
    assert result["historical_share_of_all_sales_pct"] == "30.00"
    assert sum(Decimal(x["revenue"]) for x in result["unknown_by_reason"]) == Decimal("25.00")


@pytest.mark.parametrize("options", [["--execute"], ["--execute", "--dry-run"], ["--lock-timeout-ms", "-1"], ["--overwrite-report"]])
def test_cli_invalid_options(options, tmp_path):
    from e2e_pipeline.__main__ import main
    with pytest.raises(SystemExit) as error: main(["--dataset-root", str(tmp_path), *options])
    assert error.value.code == 2
