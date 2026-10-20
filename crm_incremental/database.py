"""One explicit T-SQL transaction, while pyodbc remains autocommit=True."""

from uuid import uuid4

from warehouse_pipeline.connection import check_target, connect
from warehouse_pipeline.reporting import PipelineError

LOCK = "crm_incremental.loader.v1"
BEGIN = """
SET XACT_ABORT ON;
IF @@TRANCOUNT <> 0 THROW 51100, 'Unexpected outer transaction', 1;
BEGIN TRANSACTION;
DECLARE @lock_result int;
EXEC @lock_result = sys.sp_getapplock @Resource=N'crm_incremental.loader.v1',
    @LockMode='Exclusive', @LockOwner='Transaction', @LockTimeout=10000;
IF @lock_result < 0 BEGIN ROLLBACK; THROW 51101, 'Incremental loader lock unavailable', 1; END;
"""
STAGE = """INSERT INTO crm_incremental.staging
 (attempt_id, ordinal, event_id, event_hash, business_hash, source_updated_at,
  cst_id, cst_key, cst_firstname, cst_lastname, cst_marital_status, cst_gndr, cst_create_date)
 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
RESULT_COLUMNS = ("status", "input_events", "inserted_customers", "updated_customers", "insert_events",
                  "update_events", "no_change_events", "stale_events", "duplicate_events")


def drain(cursor):
    while cursor.nextset():
        pass


def sql_error(exc):
    # Only our numeric error IDs are extracted; raw ODBC text can contain input values.
    import re
    from warehouse_pipeline.reporting import safe_error
    codes = re.findall(r"\((511\d{2})\)", str(exc))
    return safe_error(exc) + (f" Demo error {codes[-1]}." if codes else "")


def execute_package(settings, manifest, events):
    connection = cursor = None
    attempt_id = str(uuid4())
    try:
        connection = connect(settings)
        if not connection.autocommit:
            raise PipelineError("Incremental loader requires autocommit=True with explicit SQL transaction.")
        cursor = connection.cursor()
        check_target(cursor, settings, require_procedures=False)
        cursor.execute(BEGIN)
        drain(cursor)
        cursor.execute("""INSERT INTO crm_incremental.attempts
            (attempt_id, batch_id, content_sha256, package_type, input_events)
            VALUES (?, ?, ?, ?, ?)""", attempt_id, manifest["batch_id"], manifest["sha256"],
                       manifest["package_type"], len(events))
        for ordinal, event in enumerate(events, 1):
            cursor.execute(STAGE, attempt_id, ordinal, *(event[key] for key in (
                "event_id", "event_hash", "business_hash", "source_updated_at", "cst_id", "cst_key",
                "cst_firstname", "cst_lastname", "cst_marital_status", "cst_gndr", "cst_create_date")))
        cursor.execute("EXEC crm_incremental.apply_batch @attempt_id=?", attempt_id)
        row = cursor.fetchone()
        if row is None:
            raise PipelineError("Incremental procedure returned no outcome.")
        result = dict(zip(RESULT_COLUMNS, row))
        drain(cursor)  # late SQL errors must be observed BEFORE commit
        cursor.execute("COMMIT TRANSACTION;")
        drain(cursor)
        return dict(attempt_id=attempt_id, **result)
    except Exception:
        if cursor is not None:
            try:
                cursor.execute("IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;")
                drain(cursor)
            except Exception:
                pass  # disconnection rolls back uncommitted work; original error is retained
        raise
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()
