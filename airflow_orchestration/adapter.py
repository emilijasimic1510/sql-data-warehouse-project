"""Small, secret-safe boundary around the existing end-to-end runner."""
import hashlib
import logging
from pathlib import Path
from uuid import uuid4

from e2e_pipeline.runner import run
from warehouse_pipeline.connection import Settings

LOG = logging.getLogger(__name__)


def settings_from_connection(connection, environment):
    extra = connection.extra_dejson
    if connection.schema != 'DataWarehouse' or not extra.get('expected_server'):
        raise ValueError('Explicit project target required')
    if not connection.host or not extra.get('sql_dataset_root'):
        raise ValueError('Missing target configuration')
    trust = extra.get('trust_server_certificate', False)
    if not isinstance(trust, bool):
        raise ValueError('Certificate setting must be boolean')
    auth = extra.get('auth_mode', 'windows')
    if auth not in ('windows', 'sql') or (auth == 'sql' and not (connection.login and connection.password)):
        raise ValueError('Invalid authentication')
    return Settings(
        server=connection.host + (f',{connection.port}' if connection.port else ''),
        database=connection.schema,
        dataset_root=Path(environment.get('DW_DATASET_ROOT', '/opt/project/datasets')),
        sql_dataset_root=extra['sql_dataset_root'],
        driver=extra.get('driver', 'ODBC Driver 18 for SQL Server'),
        expected_server=extra['expected_server'], trust_server_certificate=trust,
        auth_mode=auth, username=connection.login, password=connection.password,
    )


def execute_task(connection, *, environment, identity, attempt, runner=None):
    """Connection is resolved by the DAG only at task runtime, never at parse."""
    path = None
    try:
        execute_value = environment.get('DW_AIRFLOW_EXECUTE', 'false')
        if execute_value not in ('true', 'false'):
            raise ValueError('Invalid mode')
        execute = execute_value == 'true'
        settings = settings_from_connection(connection, environment)
        root = Path(environment.get('DW_REPORT_ROOT', '/opt/project/reports/airflow'))
        root.mkdir(parents=True, exist_ok=True)
        token = hashlib.sha256(identity.encode()).hexdigest()[:20]
        path = root / f'{token}-try{int(attempt)}-{uuid4().hex}.json'
        report = (runner or run)(settings, execute=execute, report_path=path, lock_timeout_ms=10000)
    except Exception:
        # Never expose a Connection repr, raw driver exception, or user configuration.
        LOG.error('Warehouse task could not complete; inspect the protected JSON report if present.')
        raise RuntimeError('Warehouse task failed; inspect the project report directory.') from None
    summary = {key: report[key] for key in ('run_id', 'status', 'mode')}
    summary['report_path'] = str(path)
    LOG.info('Warehouse run_id=%s status=%s mode=%s report=%s',
             summary['run_id'], summary['status'], summary['mode'], path.name)
    if report['status'] != 'PASS':
        raise RuntimeError(f"Warehouse run {report['run_id']} failed; inspect {path.name}.") from None
    return summary
