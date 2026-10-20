import ast
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from airflow_orchestration.adapter import execute_task
from warehouse_pipeline.connection import Settings, connect


@pytest.fixture
def config(tmp_path):
    c = SimpleNamespace(host='host.docker.internal', port=1433, schema='DataWarehouse',
                        login='demo-user', password='top-secret', extra_dejson={
                            'expected_server': r'DESKTOP-N1402MQ\SQLEXPRESS',
                            'sql_dataset_root': r'C:\warehouse\datasets', 'auth_mode': 'sql'})
    env = {'DW_DATASET_ROOT': str(tmp_path / 'datasets'), 'DW_REPORT_ROOT': str(tmp_path / 'reports')}
    return c, env


def invoke(config, runner, **kwargs):
    c, env = config
    return execute_task(c, environment=env, identity='dag/manual/task', attempt=1, runner=runner, **kwargs)


def test_success_configuration_small_xcom_unique_paths(config, caplog):
    caplog.set_level(logging.INFO)
    runner = Mock(return_value={'run_id': 'run-123', 'status': 'PASS', 'mode': 'dry-run', 'children': ['large']})
    first = invoke(config, runner)
    second = invoke(config, runner)
    settings = runner.call_args.args[0]
    assert settings.server == 'host.docker.internal,1433'
    assert settings.sql_dataset_root == r'C:\warehouse\datasets'
    assert settings.dataset_root != Path(settings.sql_dataset_root)
    assert settings.password == 'top-secret' and settings.auth_mode == 'sql'
    assert runner.call_args.kwargs['execute'] is False
    assert runner.call_args.kwargs['lock_timeout_ms'] == 10000
    assert first['report_path'] != second['report_path']
    assert set(first) == {'run_id', 'status', 'mode', 'report_path'}
    assert 'top-secret' not in caplog.text and 'demo-user' not in repr(settings)


def test_explicit_execute(config):
    config[1]['DW_AIRFLOW_EXECUTE'] = 'true'
    runner = Mock(return_value={'run_id': 'r', 'status': 'PASS', 'mode': 'execute'})
    assert invoke(config, runner)['mode'] == 'execute'
    assert runner.call_args.kwargs['execute'] is True


def test_failed_report_fails_task(config):
    runner = Mock(return_value={'run_id': 'r', 'status': 'FAIL', 'mode': 'execute'})
    with pytest.raises(RuntimeError, match='run r failed'):
        invoke(config, runner)


def test_raw_exception_never_exposes_credentials(config, caplog):
    with pytest.raises(RuntimeError) as error:
        invoke(config, Mock(side_effect=ValueError('top-secret')))
    assert 'top-secret' not in str(error.value) + caplog.text
    assert error.value.__suppress_context__


@pytest.mark.parametrize('field,value', [('schema', 'master'), ('host', '')])
def test_invalid_target_never_calls_runner(config, field, value):
    setattr(config[0], field, value)
    runner = Mock()
    with pytest.raises(RuntimeError):
        invoke(config, runner)
    runner.assert_not_called()


@pytest.mark.parametrize('value', ['yes', 'TRUE', '1', ''])
def test_mode_requires_explicit_boolean(config, value):
    config[1]['DW_AIRFLOW_EXECUTE'] = value
    runner = Mock()
    with pytest.raises(RuntimeError):
        invoke(config, runner)
    runner.assert_not_called()


def test_dag_source_has_no_parse_time_connection():
    # Static guard only; the real DagBag check runs separately inside the image.
    tree = ast.parse(Path('orchestration/airflow/dags/warehouse_e2e.py').read_text())
    top = [n for n in tree.body if not isinstance(n, ast.FunctionDef)]
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'get'
                   for node in top for n in ast.walk(node))


def test_optional_sql_auth_escapes_and_hides_secret(monkeypatch, tmp_path):
    driver = Mock()
    monkeypatch.setattr('warehouse_pipeline.connection.pyodbc.connect', driver)
    settings = Settings('host', 'DataWarehouse', tmp_path, 'C:\\data', auth_mode='sql',
                        username='u;name', password='p};secret')
    connect(settings)
    cs = driver.call_args.args[0]
    assert 'UID={u;name};PWD={p}};secret};' in cs
    assert 'Trusted_Connection' not in cs and 'p};secret' not in repr(settings)
    assert driver.call_args.kwargs == {'autocommit': True, 'timeout': 10}


def test_windows_auth_unchanged(monkeypatch, tmp_path):
    driver = Mock()
    monkeypatch.setattr('warehouse_pipeline.connection.pyodbc.connect', driver)
    connect(Settings('host', 'DataWarehouse', tmp_path, 'C:\\data'))
    assert 'Trusted_Connection=yes;' in driver.call_args.args[0]
    assert 'PWD=' not in driver.call_args.args[0]


@pytest.mark.parametrize('mode,user,password', [('sql', None, 'p'), ('sql', 'u', None), ('other', 'u', 'p')])
def test_invalid_auth_never_connects(monkeypatch, tmp_path, mode, user, password):
    driver = Mock()
    monkeypatch.setattr('warehouse_pipeline.connection.pyodbc.connect', driver)
    with pytest.raises(ValueError):
        connect(Settings('host', 'DataWarehouse', tmp_path, 'C:\\data', auth_mode=mode, username=user, password=password))
    driver.assert_not_called()

def test_actual_dry_run_never_opens_sql(config, monkeypatch):
    sql = Mock(side_effect=AssertionError('Dry-run must not connect'))
    monkeypatch.setattr('warehouse_pipeline.runner.connect', sql)
    monkeypatch.setattr('mart_pipeline.runner.connect', sql)
    # Actual validator/runner using original CSVs; no SQL and no business writes.
    config[1]['DW_DATASET_ROOT'] = str(Path('datasets').resolve())
    result = invoke(config, None)
    assert result['status'] == 'PASS' and result['mode'] == 'dry-run'
    sql.assert_not_called()


def test_preflight_checks_target_and_closes(monkeypatch, config, capsys):
    import json
    from airflow_orchestration import preflight
    c, _ = config
    monkeypatch.setenv('AIRFLOW_CONN_WAREHOUSE_SQLSERVER', json.dumps(dict(
        host=c.host, port=c.port, schema=c.schema, login=c.login, password=c.password, extra=c.extra_dejson)))
    db = Mock()
    target = Mock(return_value=(r'DESKTOP-N1402MQ\SQLEXPRESS', 'DataWarehouse'))
    monkeypatch.setattr(preflight, 'connect', Mock(return_value=db))
    monkeypatch.setattr(preflight, 'check_target', target)
    preflight.main()
    target.assert_called_once()
    db.cursor.return_value.close.assert_called_once()
    db.close.assert_called_once()
    assert 'top-secret' not in capsys.readouterr().out


def test_preflight_error_sanitized_and_closed(monkeypatch, config, capsys):
    import json
    from airflow_orchestration import preflight
    c, _ = config
    monkeypatch.setenv('AIRFLOW_CONN_WAREHOUSE_SQLSERVER', json.dumps(dict(
        host=c.host, schema=c.schema, login=c.login, password=c.password, extra=c.extra_dejson)))
    db = Mock()
    monkeypatch.setattr(preflight, 'connect', Mock(return_value=db))
    monkeypatch.setattr(preflight, 'check_target', Mock(side_effect=ValueError('top-secret')))
    with pytest.raises(SystemExit) as error:
        preflight.main()
    assert 'top-secret' not in str(error.value) + capsys.readouterr().out
    db.close.assert_called_once()
