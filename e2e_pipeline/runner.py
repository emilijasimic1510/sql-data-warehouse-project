"""Call existing functions, share one lock-owning connection, retain child reports."""

from time import perf_counter
from uuid import uuid4

from warehouse_pipeline import audit
from warehouse_pipeline.runner import run_report as run_warehouse
from warehouse_pipeline.coordination import ProjectSession, RESOURCE
from warehouse_pipeline.reporting import PipelineError, reserve_report, write_report, utc_now, safe_error
from mart_pipeline.runner import run as run_mart
from .summary import collect_summary


def run(settings, *, execute=False, report_path=None, overwrite=False, lock_timeout_ms=10000):
    report = dict(schema_version=1, run_id=str(uuid4()), component="e2e", mode="execute" if execute else "dry-run",
                  status="RUNNING", started_at_utc=utc_now(), ended_at_utc=None, failure_stage=None,
                  errors=[], audit_errors=[], audit_status="NOT_STARTED" if execute else "NOT_APPLICABLE",
                  children={"warehouse": None, "mart": None}, summary=None, findings=[], checks=[],
                  steps=[dict(name=n, status="SKIPPED", started_at_utc=None, ended_at_utc=None,
                              duration_seconds=0, error=None, child_run_id=None)
                         for n in ("warehouse", "mart", "summary")],
                  coordination=dict(resource=RESOURCE, timeout_ms=lock_timeout_ms, status="NOT_ACQUIRED"))
    handle = None
    audit_started = False

    def ready(cursor):
        nonlocal audit_started
        report["target"] = dict(zip(("server", "database"), session.target))
        audit.start_run(cursor, report)
        audit_started = True
        report["audit_status"] = "RUNNING"

    session = ProjectSession(timeout_ms=lock_timeout_ms, on_ready=ready if execute else None)

    def stage(name, operation):
        item = next(s for s in report["steps"] if s["name"] == name)
        started = perf_counter()
        item.update(status="RUNNING", started_at_utc=utc_now())
        try:
            value = operation()
            if name != "summary":
                report["children"][name] = value
                item["child_run_id"] = value["run_id"]
                if value["parent_run_id"] != report["run_id"]:
                    raise PipelineError("Child parent identity mismatch.")
                if value["status"] != "PASS":
                    item["error"] = (value.get("errors") or value.get("audit_errors") or ["Child stage failed."])[0]
                    raise PipelineError(f"{name} stage failed; see child results.")
            item["status"] = "PASS"
            return value
        except Exception as exc:
            item["status"] = "FAIL"
            item["error"] = item["error"] or safe_error(exc)
            if name == "warehouse" and report["children"][name]:
                child = report["children"][name]
                failed = next((s["name"] for s in child["steps"] if s["status"] == "FAIL"), "finalization")
                report["failure_stage"] = "warehouse." + failed
            else:
                report["failure_stage"] = name
            raise
        finally:
            item.update(ended_at_utc=utc_now(), duration_seconds=round(perf_counter() - started, 6))

    try:
        handle = reserve_report(report_path, settings.dataset_root, overwrite)
        if handle:
            write_report(handle, report)
        stage("warehouse", lambda: run_warehouse(settings, execute=execute, session=session, parent_run_id=report["run_id"]))
        child = stage("mart", lambda: run_mart(settings, execute=execute, session=session, parent_run_id=report["run_id"]))
        if execute:
            cursor = session.connection.cursor()
            try:
                report["summary"] = stage("summary", lambda: collect_summary(cursor))
            finally:
                cursor.close()
        report["status"] = "PASS"
    except Exception as exc:
        report["status"] = "FAIL"
        report["failure_stage"] = report["failure_stage"] or "configuration_or_report"
        report["errors"].append(safe_error(exc))
    finally:
        report["ended_at_utc"] = utc_now()
        warehouse = report["children"]["warehouse"]
        mart = report["children"]["mart"]
        if warehouse:
            report["findings"].extend(dict(component="warehouse", check_id=q["check_id"], severity=q["severity"],
                                            status=q["status"], anomaly_count=q["anomaly_count"])
                                      for q in warehouse["checks"] if q["status"] in ("WARNING", "ERROR"))
        if mart:
            report["findings"].extend(dict(component="mart", check_id=q["check_id"], severity=q["severity"],
                                            status=q["severity"], anomaly_count=q["anomaly_count"])
                                      for q in mart["checks"] if q["anomaly_count"] is not None and q["anomaly_count"] > 0)
        if audit_started:
            cursor = session.connection.cursor()
            try:
                if mart:
                    child_audit = dict(run_id=mart["run_id"], parent_run_id=report["run_id"], component="mart", mode=mart["mode"],
                                       status=mart["status"], started_at_utc=mart["started_at_utc"], ended_at_utc=mart["ended_at_utc"],
                                       errors=mart["errors"], audit_errors=[], checks=[],
                                       steps=[{k: v for k, v in report["steps"][1].items() if k != "child_run_id"}])
                    audit.start_run(cursor, child_audit)
                    audit.finish_run(cursor, child_audit)
                audit.finish_run(cursor, report)
                report["audit_status"] = "PASS"
            except Exception as exc:
                report["status"] = "FAIL"
                report["failure_stage"] = report["failure_stage"] or "audit"
                report["audit_status"] = "FAIL"
                report["audit_errors"].append(safe_error(exc))
                try:
                    audit.update_run(cursor, report)
                except Exception as update_exc:
                    report["audit_errors"].append(safe_error(update_exc))
            finally:
                cursor.close()
        try:
            session.release()
        except Exception as exc:
            report["status"] = "FAIL"
            report["failure_stage"] = report["failure_stage"] or "coordination_release"
            report["errors"].append(safe_error(exc))
            if audit_started:
                cursor = session.connection.cursor()
                try:
                    audit.update_run(cursor, report)
                except Exception as update_exc:
                    report["audit_errors"].append(safe_error(update_exc))
                finally:
                    cursor.close()
        report["coordination"]["status"] = session.status
        if handle:
            try:
                write_report(handle, report)
            except Exception as exc:
                report["status"] = "FAIL"
                report["failure_stage"] = report["failure_stage"] or "report"
                report["errors"].append(safe_error(exc))
                if audit_started:
                    cursor = session.connection.cursor()
                    try:
                        audit.update_run(cursor, report)
                    except Exception as update_exc:
                        report["audit_errors"].append(safe_error(update_exc))
                    finally:
                        cursor.close()
            finally:
                handle.close()
        session.disconnect()
    return report
