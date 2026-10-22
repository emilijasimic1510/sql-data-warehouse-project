# Local Airflow

The Docker Compose deployment runs one manually triggered DAG, `warehouse_e2e`, with one task, `run_warehouse_to_mart`. It calls the existing E2E runner. The CRM demo is separate.

LocalExecutor runs tasks in the scheduler container. PostgreSQL stores Airflow metadata; the API server exposes the UI at `http://localhost:18080`. The deployment uses Airflow 3.3.2 with Python 3.12, PostgreSQL 16.10, and Microsoft ODBC Driver 18. Exact pins and image digests are in the Dockerfile and Compose file.

## First setup

Start Docker Desktop with Linux containers. Run from the repository root:

```powershell
.\orchestration\airflow\setup.ps1
docker --context desktop-linux compose -f orchestration/airflow/compose.yaml config --quiet
docker --context desktop-linux compose -f orchestration/airflow/compose.yaml build airflow-scheduler
docker --context desktop-linux compose -f orchestration/airflow/compose.yaml --profile init run --rm airflow-init
docker --context desktop-linux compose -f orchestration/airflow/compose.yaml --profile validate run --rm airflow-validate
docker --context desktop-linux compose -f orchestration/airflow/compose.yaml up -d --wait --wait-timeout 300 airflow-api-server airflow-scheduler airflow-dag-processor
```

Setup creates protected runtime files and refuses to overwrite existing secrets. The UI user is `operator`; its password is stored in `orchestration/airflow/runtime/ui-passwords.json`. Runtime files are excluded from Git and the build context. SimpleAuthManager is intended for this local demo.

For an existing installation, use the final `up` command without repeating setup or metadata initialization. Rebuild the image after changing Python code or the DAG.

## Connection and paths

The scheduler receives `AIRFLOW_CONN_WAREHOUSE_SQLSERVER` from `runtime/worker.env`. The task resolves the connection at runtime, not during DAG parsing. An environment-defined connection does not appear in the UI connection list.

| Setting | Purpose |
| --- | --- |
| Connection host / port | TCP endpoint reachable from Linux, such as `host.docker.internal` and a configured port |
| Connection schema | `DataWarehouse` |
| `extra.expected_server` | Exact `@@SERVERNAME` expected before loading |
| `extra.auth_mode` | `windows` or `sql`; SQL mode requires Connection login/password |
| `extra.driver` | `ODBC Driver 18 for SQL Server` |
| `extra.trust_server_certificate` | Boolean, false by default |
| `extra.sql_dataset_root` | Windows path SQL Server reads with BULK INSERT |
| `DW_DATASET_ROOT` | `/opt/project/datasets`, a read-only Linux mount |
| `DW_REPORT_ROOT` | `/opt/project/reports/airflow`, persisted on the host |
| `DW_AIRFLOW_EXECUTE` | `false` for dry-run; `true` for loading |

Linux does not inherit the Windows desktop login. Integrated authentication requires Kerberos configuration; SQL authentication requires a configured SQL login. The supplied template supports CSV dry-run but is not a working Linux SQL connection by itself. Configure the TCP endpoint, authentication, permissions, and certificate before execution. The SQL Server service also needs read access to the Windows dataset path.

The local deployment has recorded a successful DAG dry-run. SQL loading from the Linux worker remains unverified.

## Dry-run

Confirm the scheduler's effective mode:

```powershell
docker --context desktop-linux compose -f orchestration/airflow/compose.yaml exec airflow-scheduler python -c "import os; print('execute=' + os.environ.get('DW_AIRFLOW_EXECUTE','MISSING'))"
```

With `execute=false`, trigger a run:

```powershell
docker --context desktop-linux compose -f orchestration/airflow/compose.yaml exec airflow-scheduler airflow dags unpause warehouse_e2e
docker --context desktop-linux compose -f orchestration/airflow/compose.yaml exec airflow-scheduler airflow dags trigger warehouse_e2e
```

Inspect the task log and JSON report under `reports/airflow`. A successful dry-run has SQL stages SKIPPED and `committed=false` for the mart. XCom contains the run ID, status, mode, and report path.

## SQL execution

After configuring the connection, run the read-only preflight from the worker environment:

```powershell
docker --context desktop-linux compose -f orchestration/airflow/compose.yaml run --rm --no-deps airflow-scheduler python -m airflow_orchestration.preflight
```

Preflight checks server identity, database, and required procedures. It does not prove all load permissions. Once the configuration is ready, set `DW_AIRFLOW_EXECUTE=true` in the protected worker environment and recreate the scheduler while no task is active:

```powershell
docker --context desktop-linux compose -f orchestration/airflow/compose.yaml up -d --no-deps --force-recreate airflow-scheduler
docker --context desktop-linux compose -f orchestration/airflow/compose.yaml exec airflow-scheduler airflow dags trigger warehouse_e2e
```

Restore `false` and recreate the idle scheduler when returning to dry-run use. Do not recreate it during a load.

## Logs, shutdown, and recovery

```powershell
docker --context desktop-linux compose -f orchestration/airflow/compose.yaml logs --tail 100 airflow-scheduler airflow-api-server airflow-dag-processor
docker --context desktop-linux compose -f orchestration/airflow/compose.yaml exec airflow-scheduler airflow dags pause warehouse_e2e
# Run after active tasks finish; retains volumes and reports.
docker --context desktop-linux compose -f orchestration/airflow/compose.yaml stop --timeout 60
```

The DAG has no schedule, no retries, one active run/task, and a 30-minute timeout. The SQL project lock still coordinates standalone Python writers. Airflow's concurrency setting alone does not protect against other writers.

Bronze/Silver remain autocommit; only the mart has an atomic publication transaction. An interrupted task can leave partial loads and RUNNING audit records. Review SQL state and parent/child reports before retrying, following the [E2E recovery guide](E2E_PIPELINE.md).
