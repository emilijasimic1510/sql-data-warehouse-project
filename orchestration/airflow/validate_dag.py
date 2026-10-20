"""Run inside the actual Airflow image, never a mock import test."""
import json
from airflow.dag_processing.dagbag import DagBag
bag = DagBag('/opt/airflow/dags', safe_mode=False)
assert not bag.import_errors, 'DAG import errors'
dag = bag.dags.get('warehouse_e2e')
assert dag is not None and len(dag.tasks) == 1
assert dag.schedule is None and not dag.catchup and dag.max_active_runs == 1
assert dag.is_paused_upon_creation
assert dag.tasks[0].retries == 0
assert dag.tasks[0].execution_timeout.total_seconds() == 1800
print('Real Airflow DAG import/configuration: PASS')
print(json.dumps(dict(dag_id=dag.dag_id, import_errors=len(bag.import_errors),
                      tasks=len(dag.tasks), schedule=dag.schedule, catchup=dag.catchup,
                      paused_at_creation=dag.is_paused_upon_creation,
                      max_active_runs=dag.max_active_runs, max_active_tasks=dag.max_active_tasks,
                      retries=dag.tasks[0].retries,
                      execution_timeout_seconds=dag.tasks[0].execution_timeout.total_seconds())))
