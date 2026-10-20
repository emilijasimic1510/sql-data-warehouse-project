"""Ordered pipeline, quality gate, best-effort SQL audit and local evidence."""

import logging
from contextlib import contextmanager
from time import perf_counter
from uuid import uuid4

from csv_validation.validator import validate_dataset
from .connection import Settings, check_target, connect
from . import audit
from .coordination import ProjectSession
from .quality import collect_counts, run_checks
from .reporting import PipelineError, csv_summary, reserve_report, safe_error, utc_now, write_report

LOG = logging.getLogger(__name__)
STEP_NAMES = ("validation", "connection", "target_check", "coordination", "audit_start", "bronze", "silver", "quality", "row_counts")


@contextmanager
def step(report, name):
    item = next(s for s in report["steps"] if s["name"] == name)
    start = perf_counter()
    item.update(started_at_utc=utc_now(), status="PASS")
    LOG.info("%s START", name)
    try:
        yield
    except Exception as exc:
        item.update(status="FAIL", error=safe_error(exc))
        raise
    finally:
        item.update(ended_at_utc=utc_now(), duration_seconds=round(perf_counter() - start, 6))
        LOG.info("%s %s duration=%.3fs", name, item["status"], item["duration_seconds"])


def execute_procedure(cursor, statement, *parameters):
    cursor.execute(statement, *parameters)
    while cursor.nextset():
        pass


def run_report(settings: Settings, execute=False, *, quality_only=False, report_path=None,
               overwrite_report=False, session=None, parent_run_id=None) -> dict:
    if execute and quality_only:
        raise ValueError("execute and quality_only are mutually exclusive")
    mode = "quality-only" if quality_only else "execute" if execute else "dry-run"
    report = dict(schema_version=1, run_id=str(uuid4()), parent_run_id=parent_run_id, mode=mode, status="RUNNING",
                  started_at_utc=utc_now(), ended_at_utc=None, csv_results=None, checks=[],
                  row_counts={}, row_count_errors=[], errors=[], audit_errors=[],
                  audit_status="NOT_STARTED" if execute or quality_only else "NOT_APPLICABLE",
                  target=None, steps=[dict(name=n, status="SKIPPED", started_at_utc=None,
                                          ended_at_utc=None, duration_seconds=0, error=None)
                                      for n in STEP_NAMES])
    handle = connection = cursor = None
    owned_session = session is None
    session = session or ProjectSession()
    audit_started = load_started = False
    LOG.info("pipeline START run_id=%s mode=%s", report["run_id"], mode)
    try:
        handle = reserve_report(report_path, settings.dataset_root, overwrite_report)
        if handle:
            write_report(handle, report)
        if not quality_only:
            with step(report, "validation"):
                results = validate_dataset(settings.dataset_root)
                report["csv_results"] = csv_summary(results)
                for result in report["csv_results"]:
                    LOG.info("CSV file=%s records=%s status=%s errors=%s warnings=%s",
                             result["file_index"], result["record_count"], result["status"],
                             result["error_count"], result["warning_count"])
                    for warning in result["warnings"]:
                        LOG.warning("%s", warning)
                if any(r.errors for r in results):
                    raise PipelineError("CSV validation failed before SQL connection; inspect csv_validation results.")
        if execute or quality_only:
            with step(report, "connection"):
                if session.connection is None:
                    session.connection = connect(settings)
                connection = session.connection
                cursor = connection.cursor()
            with step(report, "target_check"):
                server, database = check_target(cursor, settings, require_procedures=not quality_only)
                report["target"] = dict(server=server, database=database)
                LOG.info("Confirmed target: server=%s database=%s", server, database)
            with step(report, "coordination"):
                session.acquire(cursor, (server, database))
            with step(report, "audit_start"):
                audit.start_run(cursor, report)
                audit_started = True
                report["audit_status"] = "RUNNING"
            if execute:
                load_started = True
                with step(report, "bronze"):
                    execute_procedure(cursor, "EXEC bronze.load_bronze @dataset_root = ?;", settings.sql_dataset_root)
                with step(report, "silver"):
                    execute_procedure(cursor, "EXEC silver.load_silver;")
            # Do not abort at the first failed rule: collect all check results and available counts.
            with step(report, "quality"):
                run_checks(cursor, report["checks"])
                for result in report["checks"]:
                    LOG.log(logging.WARNING if result["status"] in ("ERROR", "WARNING") else logging.INFO,
                            "SQL %s status=%s anomalies=%s metric=%s", result["check_id"], result["status"],
                            result["anomaly_count"], result["metric_value"])
                quality_failed = any(r["status"] == "ERROR" for r in report["checks"])
                if quality_failed:
                    # Defer raising until counts are collected, but mark the quality step accurately.
                    item = next(s for s in report["steps"] if s["name"] == "quality")
                    item.update(status="FAIL", error="SQL quality gate failed; see check results.")
            with step(report, "row_counts"):
                report["row_count_errors"] = collect_counts(cursor, report["row_counts"])
                if report["row_count_errors"]:
                    raise PipelineError("One or more business-object row counts could not be read.")
            if quality_failed:
                raise PipelineError("SQL quality gate failed; see check results.")
        else:
            LOG.info("Dry-run: no SQL connection or audit; plan is validation -> target -> audit -> Bronze -> Silver -> quality -> counts.")
        report["status"] = "PASS"
    except Exception as exc:
        report["status"] = "FAIL"
        report["errors"].append(safe_error(exc))
        LOG.error("%s", report["errors"][-1])
        if load_started:
            LOG.error("Partial data may remain in Bronze/Silver and be visible through Gold. No whole-load rollback; no automatic retry.")
        if next(s for s in report["steps"] if s["name"] == "audit_start")["status"] == "FAIL":
            report["audit_status"] = "FAIL"
            report["audit_errors"].append(safe_error(exc))
    finally:
        report["ended_at_utc"] = utc_now()
        if audit_started:
            try:
                audit.finish_run(cursor, report)
                report["audit_status"] = "PASS"
            except Exception as exc:
                report["status"] = "FAIL"
                report["audit_status"] = "FAIL"
                report["audit_errors"].append(safe_error(exc))
                LOG.error("Audit finalization failed: %s", safe_error(exc))
                try:
                    audit.update_run(cursor, report)
                except Exception as update_exc:
                    report["audit_errors"].append(safe_error(update_exc))
        if owned_session:
            try:
                session.release()
            except Exception as exc:
                report["status"] = "FAIL"
                report["errors"].append(safe_error(exc))
                if audit_started:
                    try:
                        audit.update_run(cursor, report)
                    except Exception as audit_exc:
                        report["audit_errors"].append(safe_error(audit_exc))
        report["coordination_status"] = session.status
        if handle:
            try:
                write_report(handle, report)
            except Exception as exc:
                report["status"] = "FAIL"
                report["errors"].append("Local JSON report could not be finalized: " + safe_error(exc))
                LOG.error("%s", report["errors"][-1])
                if audit_started:
                    try:
                        audit.update_run(cursor, report)
                    except Exception as audit_exc:
                        LOG.error("Audit status update failed: %s", safe_error(audit_exc))
            finally:
                handle.close()
        if cursor is not None:
            cursor.close()
        if owned_session:
            session.disconnect()
    LOG.info("pipeline %s run_id=%s audit=%s", report["status"], report["run_id"], report["audit_status"])
    return report


def run_pipeline(settings: Settings, execute=False, **options) -> int:
    """Preserve the existing CLI/API exit-code contract; e2e uses structured run_report."""
    return 0 if run_report(settings, execute=execute, **options)["status"] == "PASS" else 1
