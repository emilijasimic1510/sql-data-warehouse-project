from pathlib import Path
from unittest.mock import MagicMock

import pyodbc
import pytest

from csv_validation.validator import FileResult
from warehouse_pipeline import connection, runner
from warehouse_pipeline.__main__ import main


@pytest.fixture
def setup(monkeypatch, tmp_path):
    settings = connection.Settings("test-host", "TestWarehouse", tmp_path, r"D:\server datasets")
    validation = MagicMock(return_value=[FileResult("source.csv", record_count=1)])
    cursor = MagicMock()
    cursor.execute.return_value = cursor
    cursor.fetchone.side_effect = [("test-host", "TestWarehouse"), (1,), (2,)]
    cursor.nextset.return_value = False
    conn = MagicMock()
    conn.cursor.return_value = cursor
    connect = MagicMock(return_value=conn)
    monkeypatch.setattr(runner, "validate_dataset", validation)
    monkeypatch.setattr(runner, "connect", connect)
    # Coordination is tested independently in test_e2e_pipeline.py.
    monkeypatch.setattr(runner.ProjectSession, "acquire", MagicMock())
    # Phase 2C services are covered with SQL mocks in test_quality_pipeline.py.
    monkeypatch.setattr(runner.audit, "start_run", MagicMock())
    monkeypatch.setattr(runner.audit, "finish_run", MagicMock())
    monkeypatch.setattr(runner, "run_checks", MagicMock())
    monkeypatch.setattr(runner, "collect_counts", MagicMock(return_value=[]))
    return settings, validation, connect, conn, cursor


def loader_calls(cursor):
    return [call.args for call in cursor.execute.call_args_list if call.args[0].startswith("EXEC")]


def test_bad_validation_never_connects(setup):
    settings, validation, connect, _, _ = setup
    validation.return_value = [FileResult("bad.csv", errors=["Missing columns"])]
    assert runner.run_pipeline(settings, execute=True) == 1
    connect.assert_not_called()


def test_dry_run_never_connects(setup):
    settings, validation, connect, _, _ = setup
    assert runner.run_pipeline(settings) == 0
    validation.assert_called_once_with(settings.dataset_root)
    connect.assert_not_called()


def test_success_order_parameters_and_close(setup):
    settings, _, _, conn, cursor = setup
    assert runner.run_pipeline(settings, execute=True) == 0
    assert loader_calls(cursor) == [
        ("EXEC bronze.load_bronze @dataset_root = ?;", settings.sql_dataset_root),
        ("EXEC silver.load_silver;",),
    ]
    assert cursor.nextset.call_count == 2
    cursor.close.assert_called_once()
    conn.close.assert_called_once()


@pytest.mark.parametrize("failure_step", ["bronze", "silver"])
def test_sql_failure_cli_exit_and_close(setup, failure_step, caplog):
    settings, _, _, conn, cursor = setup
    def execute(sql, *params):
        if sql.startswith(f"EXEC {failure_step}."):
            raise pyodbc.Error("42000", "SECRET failing row value")
        return cursor
    cursor.execute.side_effect = execute
    assert main(["--server", settings.server, "--database", settings.database,
                 "--dataset-root", str(settings.dataset_root), "--execute"]) == 1
    if failure_step == "bronze":
        assert len(loader_calls(cursor)) == 1
    assert "Partial data may remain" in caplog.text
    assert "SECRET" not in caplog.text
    conn.close.assert_called_once()
    cursor.close.assert_called_once()


def test_late_bronze_error_stops_silver(setup):
    settings, _, _, conn, cursor = setup
    cursor.nextset.side_effect = [True, pyodbc.Error("42000", "Late error")]
    assert runner.run_pipeline(settings, execute=True) == 1
    assert len(loader_calls(cursor)) == 1
    conn.close.assert_called_once()


@pytest.mark.parametrize("target_rows", [
    [("test-host", "WrongDatabase")],
    [("test-host", "TestWarehouse"), (None,)],
    [("test-host", "TestWarehouse"), (1,), (None,)],
])
def test_target_failure_before_loading(setup, target_rows):
    settings, _, _, conn, cursor = setup
    cursor.fetchone.side_effect = target_rows
    assert runner.run_pipeline(settings, execute=True) == 1
    assert loader_calls(cursor) == []
    conn.close.assert_called_once()


def test_expected_server_mismatch(setup):
    settings, _, _, conn, cursor = setup
    settings = connection.Settings("alias", settings.database, settings.dataset_root,
                                   settings.sql_dataset_root, expected_server="another-host")
    assert runner.run_pipeline(settings, execute=True) == 1
    assert loader_calls(cursor) == []
    conn.close.assert_called_once()


def test_connect_failure(setup):
    settings, _, connect, _, _ = setup
    connect.side_effect = pyodbc.Error("08001", "Login failed")
    assert runner.run_pipeline(settings, execute=True) == 1


def test_connection_uses_windows_auth_autocommit_and_escaped_values(monkeypatch, tmp_path):
    connect = MagicMock()
    monkeypatch.setattr(connection.pyodbc, "connect", connect)
    settings = connection.Settings("host};UID=bad", "db", tmp_path, "server path")
    connection.connect(settings)
    args, kwargs = connect.call_args
    assert "SERVER={host}};UID=bad}" in args[0]
    assert "Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=no" in args[0]
    assert kwargs["autocommit"] is True


def test_environment_defaults_do_not_enable_execute(monkeypatch, tmp_path):
    import warehouse_pipeline.__main__ as cli
    monkeypatch.setenv("DW_SERVER", "env-server")
    monkeypatch.setenv("DW_DATABASE", "env-db")
    monkeypatch.setenv("DW_DATASET_ROOT", str(tmp_path))
    monkeypatch.setenv("DW_SQL_DATASET_ROOT", r"\\server\share\datasets")
    monkeypatch.setenv("DW_EXECUTE", "true")
    run = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "run_pipeline", run)
    assert cli.main([]) == 0
    settings = run.call_args.args[0]
    assert settings.server == "env-server"
    assert settings.sql_dataset_root == r"\\server\share\datasets"
    assert run.call_args.kwargs["execute"] is False
    assert cli.main(["--server", "cli-server"]) == 0
    assert run.call_args.args[0].server == "cli-server"
