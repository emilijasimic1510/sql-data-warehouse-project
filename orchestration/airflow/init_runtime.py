"""Create only project-local runtime files; do not print credentials."""
import base64
import json
from pathlib import Path
import secrets

root = Path(__file__).resolve().parent
runtime = root / 'runtime'
if not runtime.is_dir():
    raise SystemExit('Run setup.ps1 first to establish a protected directory.')
if any(runtime.iterdir()):
    raise SystemExit('Runtime exists: refusing to replace credentials or configuration.')
password = secrets.token_urlsafe(32)
(runtime / 'postgres.env').write_text(
    f'POSTGRES_USER=airflow\nPOSTGRES_DB=airflow\nPOSTGRES_PASSWORD={password}\n', encoding='utf-8')
values = {
    'AIRFLOW__CORE__EXECUTOR': 'LocalExecutor',
    'AIRFLOW__CORE__PARALLELISM': '1',
    'AIRFLOW__CORE__LOAD_EXAMPLES': 'False',
    'AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION': 'True',
    'AIRFLOW__CORE__FERNET_KEY': base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
    'AIRFLOW__API_AUTH__JWT_SECRET': secrets.token_urlsafe(48),
    'AIRFLOW__API__SECRET_KEY': secrets.token_urlsafe(48),
    'AIRFLOW__API__WORKERS': '1',
    'AIRFLOW__DAG_PROCESSOR__PARSING_PROCESSES': '1',
    'AIRFLOW__CORE__EXECUTION_API_SERVER_URL': 'http://airflow-api-server:8080/execution/',
    'AIRFLOW__DATABASE__SQL_ALCHEMY_CONN': f'postgresql+psycopg2://airflow:{password}@postgres/airflow',
    'AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_USERS': 'operator:admin',
    'AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_PASSWORDS_FILE': '/run/project/ui-passwords.json',
}
(runtime / 'airflow.env').write_text(''.join(f'{k}={v}\n' for k, v in values.items()), encoding='utf-8')
(runtime / 'ui-passwords.json').write_text(json.dumps({'operator': secrets.token_urlsafe(24)}), encoding='utf-8')
connection = dict(conn_type='generic', host='host.docker.internal', schema='DataWarehouse', extra=dict(
    expected_server=r'DESKTOP-N1402MQ\SQLEXPRESS', auth_mode='windows',
    sql_dataset_root=str(root.parents[1] / 'datasets'), trust_server_certificate=False))
# Single quoted dotenv value preserves Windows backslashes and dollar signs in later credentials.
(runtime / 'worker.env').write_text(
    'DW_AIRFLOW_EXECUTE=false\nAIRFLOW_CONN_WAREHOUSE_SQLSERVER=\'' + json.dumps(connection) + "'\n", encoding='utf-8')
(root.parents[1] / 'reports' / 'airflow').mkdir(parents=True, exist_ok=True)
print('Protected runtime configuration created; execute=false. No credentials printed.')
