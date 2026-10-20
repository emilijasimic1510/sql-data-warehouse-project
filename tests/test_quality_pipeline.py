"""Behavioral tests: no live SQL connection or real warehouse mutations."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pyodbc
import pytest

from csv_validation.validator import FileResult
from warehouse_pipeline import audit, quality, runner
from warehouse_pipeline.connection import Settings
from warehouse_pipeline.__main__ import main


@pytest.fixture
def pipeline(monkeypatch, tmp_path):
    settings = Settings("test-host", "TestWarehouse", tmp_path / "datasets", "sql datasets")
    cursor = MagicMock()
    cursor.execute.return_value = cursor
    cursor.nextset.return_value = False
    response = {"sql": ""}

    def execute(sql, *parameters):
        response["sql"] = sql
        return cursor

    def fetchone():
        sql = response["sql"]
        if "@@SERVERNAME" in sql:
            return ("test-host", "TestWarehouse")
        if "OBJECT_ID" in sql:
            return (1,)
        if sql in [c.sql for c in quality.CHECKS]:
            return (0,)
        return (10,)

    cursor.execute.side_effect = execute
    cursor.fetchone.side_effect = fetchone
    conn = MagicMock()
    conn.cursor.return_value = cursor
    connect = MagicMock(return_value=conn)
    validation = MagicMock(return_value=[FileResult("source.csv", record_count=10, count_complete=True)])
    monkeypatch.setattr(runner, "connect", connect)
    monkeypatch.setattr(runner.ProjectSession, "acquire", MagicMock())
    monkeypatch.setattr(runner, "validate_dataset", validation)
    path = tmp_path / "result.json"
    return settings, cursor, connect, validation, path, response


def run(pipeline, **options):
    settings, _, _, _, path, _ = pipeline
    code = runner.run_pipeline(settings, report_path=path, **options)
    return code, json.loads(path.read_text(encoding="utf-8"))


def test_error_findings_fail_and_are_audited(pipeline):
    _, cursor, _, _, _, response = pipeline
    fetch = cursor.fetchone.side_effect
    cursor.fetchone.side_effect = lambda: (2,) if response["sql"] == quality.CHECKS[0].sql else fetch()
    code, report = run(pipeline, execute=True)
    assert code == 1
    assert report["checks"][0]["anomaly_count"] == 2
    assert report["checks"][0]["status"] == "ERROR"
    assert len(report["checks"]) == len(quality.CHECKS)
    assert len(report["row_counts"]) == 15
    updates = [c.args for c in cursor.execute.call_args_list if c.args[0].startswith("UPDATE audit")]
    assert updates[-1][2] == "FAIL"


def test_warning_and_metric_allow_success(pipeline):
    _, cursor, _, _, _, response = pipeline
    fetch = cursor.fetchone.side_effect
    warning = next(c for c in quality.CHECKS if c.check_id == "S12")
    metric = next(c for c in quality.CHECKS if c.rule == "metric")
    cursor.fetchone.side_effect = lambda: (15,) if response["sql"] in (warning.sql, metric.sql) else fetch()
    code, report = run(pipeline, execute=True)
    assert code == 0
    assert report["status"] == "PASS"
    assert next(c for c in report["checks"] if c["check_id"] == "S12")["status"] == "WARNING"
    info = next(c for c in report["checks"] if c["check_id"] == "S14")
    assert info["status"] == "INFO" and info["anomaly_count"] is None and info["metric_value"] == 15


@pytest.mark.parametrize("late", [False, True])
def test_sql_check_execution_error_is_not_zero(pipeline, late):
    _, cursor, _, _, _, response = pipeline
    execute = cursor.execute.side_effect
    sql = next(c.sql for c in quality.CHECKS if c.check_id == "S12")
    if late:
        def nextset():
            if response["sql"] == sql:
                raise pyodbc.Error("42000", "SECRET row")
            return False
        cursor.nextset.side_effect = nextset
    else:
        def fail(statement, *params):
            if statement == sql:
                raise pyodbc.Error("42000", "SECRET row")
            return execute(statement, *params)
        cursor.execute.side_effect = fail
    code, report = run(pipeline, quality_only=True)
    check = next(c for c in report["checks"] if c["check_id"] == "S12")
    assert code == 1 and check["status"] == "ERROR" and check["anomaly_count"] is None
    assert "SECRET" not in json.dumps(report)


def test_quality_only_skips_csv_loaders_and_procedure_lookup(pipeline):
    _, cursor, _, validation, _, _ = pipeline
    code, report = run(pipeline, quality_only=True)
    assert code == 0
    validation.assert_not_called()
    sql = [c.args[0] for c in cursor.execute.call_args_list]
    assert not any(s.startswith("EXEC") or "OBJECT_ID" in s for s in sql)
    assert sum(s.startswith("INSERT INTO audit.pipeline_runs") for s in sql) == 1
    assert report["csv_results"] is None
    assert all(s["status"] == "SKIPPED" for s in report["steps"] if s["name"] in ("validation", "bronze", "silver"))


def test_dry_run_has_report_but_no_sql_or_audit(pipeline):
    _, cursor, connect, _, _, _ = pipeline
    code, report = run(pipeline)
    assert code == 0 and report["mode"] == "dry-run"
    connect.assert_not_called()
    cursor.execute.assert_not_called()
    assert report["checks"] == [] and report["audit_status"] == "NOT_APPLICABLE"


@pytest.mark.parametrize("failed_step", ["bronze", "silver"])
def test_load_failure_survives_audit_failure(pipeline, failed_step, caplog):
    _, cursor, _, _, _, _ = pipeline
    execute = cursor.execute.side_effect
    def fail(sql, *params):
        if sql.startswith(f"EXEC {failed_step}"):
            raise pyodbc.Error("22018", "PRIVATE customer")
        if sql.startswith("INSERT INTO audit.pipeline_steps"):
            raise pyodbc.Error("42000", "PRIVATE audit")
        return execute(sql, *params)
    cursor.execute.side_effect = fail
    code, report = run(pipeline, execute=True)
    assert code == 1 and report["audit_status"] == "FAIL"
    step = next(s for s in report["steps"] if s["name"] == failed_step)
    assert step["status"] == "FAIL" and "22018" in step["error"]
    assert "22018" in report["errors"][0] and "42000" in report["audit_errors"][0]
    assert report["checks"] == []
    assert "PRIVATE" not in json.dumps(report) + caplog.text
    if failed_step == "bronze":
        assert not any(c.args[0].startswith("EXEC silver") for c in cursor.execute.call_args_list)


def test_audit_only_failure_changes_success_to_failure(pipeline):
    _, cursor, _, _, _, _ = pipeline
    execute = cursor.execute.side_effect
    def fail(sql, *params):
        if sql.startswith("INSERT INTO audit.quality_results"):
            raise pyodbc.Error("42000", "bad audit")
        return execute(sql, *params)
    cursor.execute.side_effect = fail
    code, report = run(pipeline, quality_only=True)
    assert code == 1 and report["status"] == "FAIL"
    assert report["errors"] == [] and report["audit_errors"]
    assert report["audit_status"] == "FAIL"


def test_missing_audit_stops_before_load(pipeline):
    _, cursor, _, _, _, _ = pipeline
    execute = cursor.execute.side_effect
    def fail(sql, *params):
        if sql.startswith("INSERT INTO audit.pipeline_runs"):
            raise pyodbc.Error("42S02", "missing table")
        return execute(sql, *params)
    cursor.execute.side_effect = fail
    code, report = run(pipeline, execute=True)
    assert code == 1 and report["audit_status"] == "FAIL"
    assert not any(c.args[0].startswith("EXEC") for c in cursor.execute.call_args_list)


def test_connection_failure_still_writes_report(pipeline):
    _, _, connect, _, _, _ = pipeline
    connect.side_effect = pyodbc.Error("08001", "SECRET credentials")
    code, report = run(pipeline, execute=True)
    assert code == 1 and report["status"] == "FAIL"
    assert report["ended_at_utc"].endswith("Z")
    assert "SECRET" not in json.dumps(report)
    assert report["audit_status"] == "NOT_STARTED"


def test_validation_failure_report_has_no_untrusted_header_values(pipeline):
    _, _, connect, validation, _, _ = pipeline
    validation.return_value = [FileResult("PRIVATE.csv", columns=["PRIVATE"], errors=["Unexpected PRIVATE"])]
    code, report = run(pipeline, execute=True)
    assert code == 1 and report["csv_results"][0]["error_count"] == 1
    assert "PRIVATE" not in json.dumps(report)
    connect.assert_not_called()


def test_report_existing_is_preserved_unless_explicit(pipeline):
    settings, _, connect, _, path, _ = pipeline
    path.write_text('{"previous": true}', encoding="utf-8")
    assert runner.run_pipeline(settings, execute=True, report_path=path) == 1
    assert json.loads(path.read_text()) == {"previous": True}
    connect.assert_not_called()
    assert runner.run_pipeline(settings, report_path=path, overwrite_report=True) == 0
    assert json.loads(path.read_text())["mode"] == "dry-run"


def test_report_inside_dataset_rejected(pipeline):
    settings, _, connect, _, _, _ = pipeline
    assert runner.run_pipeline(settings, execute=True, report_path=settings.dataset_root / "out.json") == 1
    connect.assert_not_called()


def test_row_count_failure_retains_available_counts(pipeline):
    _, cursor, _, _, _, _ = pipeline
    execute = cursor.execute.side_effect
    def fail(sql, *params):
        if sql == "SELECT COUNT_BIG(*) FROM gold.dim_products":
            raise pyodbc.Error("42000", "SECRET")
        return execute(sql, *params)
    cursor.execute.side_effect = fail
    code, report = run(pipeline, quality_only=True)
    assert code == 1
    assert report["row_counts"]["gold.dim_products"] is None
    assert report["row_counts"]["gold.fact_sales"] == 10


@pytest.mark.parametrize("flags", [("--execute", "--quality-only"), ("--dry-run", "--quality-only"), ("--dry-run", "--execute"), ("--overwrite-report",)])
def test_ambiguous_cli_rejected(flags):
    with pytest.raises(SystemExit) as exc:
        main(["--server", "host", "--database", "warehouse", "--dataset-root", "datasets", *flags])
    assert exc.value.code == 2


def test_quality_only_cli_needs_no_dataset(monkeypatch):
    for name in ("DW_DATASET_ROOT", "DW_SQL_DATASET_ROOT"):
        monkeypatch.delenv(name, raising=False)
    import warehouse_pipeline.__main__ as cli
    call = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "run_pipeline", call)
    assert main(["--server", "host", "--database", "warehouse", "--quality-only"]) == 0
    assert call.call_args.kwargs["quality_only"] is True


def test_generated_sql_matches_registry():
    root = Path(__file__).resolve().parents[1]
    assert len({c.check_id for c in quality.CHECKS}) == len(quality.CHECKS) == 28
    for layer in ("silver", "gold"):
        assert (root / "tests" / f"quality_checks_{layer}.sql").read_text(encoding="utf-8") == quality.render_sql(layer)
    assert all(c.severity in ("ERROR", "WARNING") for c in quality.CHECKS)
