"""Caller-owned transaction: dimensions + full fact refresh + quality before COMMIT."""

import re
from pathlib import Path
from uuid import uuid4

from warehouse_pipeline.connection import connect, check_target
from warehouse_pipeline.reporting import PipelineError, reserve_report, write_report, utc_now, safe_error
from warehouse_pipeline.coordination import ProjectSession

BEGIN = """SET XACT_ABORT ON;
IF @@TRANCOUNT<>0 THROW 51200, 'Unexpected outer transaction', 1;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
BEGIN TRANSACTION;
DECLARE @lock int;
EXEC @lock=sys.sp_getapplock @Resource=N'mart.loader.v1',@LockMode='Exclusive',
    @LockOwner='Transaction',@LockTimeout=10000;
IF @lock<0 BEGIN ROLLBACK; THROW 51201, 'Mart loader lock unavailable', 1; END;"""


def drain(cursor):
    while cursor.nextset():
        pass


def error_message(exc):
    codes = re.findall(r"\((512\d{2})\)", str(exc))
    return safe_error(exc) + (f" Mart error {codes[-1]}." if codes else "")


def run(settings, *, execute=False, report_path=None, overwrite=False, session=None, parent_run_id=None):
    report = dict(run_id=str(uuid4()), parent_run_id=parent_run_id, mode="execute" if execute else "dry-run", status="RUNNING",
                  started_at_utc=utc_now(), ended_at_utc=None, committed=False, checks=[], counts={}, errors=[])
    handle = connection = cursor = None
    owned_session = session is None
    session = session or ProjectSession()
    try:
        handle = reserve_report(report_path, settings.dataset_root, overwrite)
        if handle:
            write_report(handle, report)
        if execute:
            if session.connection is None:
                session.connection = connect(settings)
            connection = session.connection
            if not connection.autocommit:
                raise PipelineError("Mart loader requires autocommit=True and explicit SQL transaction.")
            cursor = connection.cursor()
            server, database = check_target(cursor, settings, require_procedures=False)
            report["target"] = dict(server=server, database=database)
            session.acquire(cursor, (server, database))
            cursor.execute(BEGIN); drain(cursor)
            cursor.execute("EXEC mart.load_model;"); drain(cursor)
            cursor.execute("EXEC mart.check_quality;")
            columns = [c[0] for c in cursor.description]
            report["checks"] = [dict(zip(columns, row)) for row in cursor.fetchall()]
            drain(cursor)
            if not report["checks"] or any(c["severity"] == "ERROR" and c["anomaly_count"] != 0 for c in report["checks"]):
                raise PipelineError("Mart quality/reconciliation failed before COMMIT; inspect check results.")
            for table in ("dim_customer", "dim_product", "dim_date", "fact_sales"):
                report["counts"][table] = cursor.execute(f"SELECT COUNT_BIG(*) FROM mart.{table}").fetchone()[0]
                drain(cursor)
            cursor.execute("COMMIT TRANSACTION;"); drain(cursor)
            report["committed"] = True
        else:
            report["plan"] = "Verify target; serializable transaction; persistent dimensions; fact refresh; quality gate; commit. No SQL connection in dry-run."
        report["status"] = "PASS"
    except Exception as exc:
        report["status"] = "FAIL"
        report["errors"].append(error_message(exc))
        if cursor is not None:
            report["committed"] = None
            try:
                cursor.execute("IF XACT_STATE()<>0 ROLLBACK TRANSACTION;"); drain(cursor)
            except Exception:
                pass
            report["commit_note"] = "Connection loss near COMMIT can make acknowledgement uncertain; inspect mart before rerun."
    finally:
        report["ended_at_utc"] = utc_now()
        if owned_session:
            try:
                session.release()
            except Exception as exc:
                report["status"] = "FAIL"; report["errors"].append(error_message(exc))
        report["coordination_status"] = session.status
        if handle:
            try:
                write_report(handle, report)
            except Exception as exc:
                report["status"] = "FAIL"; report["errors"].append(error_message(exc))
            finally:
                handle.close()
        if cursor is not None:
            cursor.close()
        if owned_session:
            session.disconnect()
    return report
