"""One business task retains the existing session lock and transaction boundaries."""
from datetime import datetime, timedelta, timezone
from airflow.sdk import DAG
from airflow.providers.standard.operators.python import PythonOperator


def run_warehouse():
    import os
    from airflow.sdk import Connection, get_current_context
    from airflow_orchestration.adapter import execute_task
    try:
        connection = Connection.get('warehouse_sqlserver')
    except Exception:
        raise RuntimeError('Cannot resolve warehouse_sqlserver runtime Connection.') from None
    context = get_current_context()
    ti = context['ti']
    return execute_task(connection, environment=os.environ,
                        identity=f'{ti.dag_id}/{ti.run_id}/{ti.task_id}', attempt=ti.try_number)


with DAG(
    dag_id='warehouse_e2e', start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    schedule=None, catchup=False, max_active_runs=1, max_active_tasks=1,
    is_paused_upon_creation=True, tags=['warehouse', 'local-demo'],
) as dag:
    PythonOperator(task_id='run_warehouse_to_mart', python_callable=run_warehouse,
                   retries=0, execution_timeout=timedelta(minutes=30),
                   show_return_value_in_logs=False)
