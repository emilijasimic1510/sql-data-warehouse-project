"""Audit DML only; deployment is an explicit, separate SQL script."""

from datetime import datetime
import json


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None) if value else None


def start_run(cursor, report):
    if report.get("parent_run_id") or report.get("component") == "e2e":
        cursor.execute(
            "INSERT INTO audit.pipeline_runs (run_id, started_at_utc, status, mode, parent_run_id, component) VALUES (?, ?, ?, ?, ?, ?)",
            report["run_id"], timestamp(report["started_at_utc"]), "RUNNING", report["mode"],
            report.get("parent_run_id"), report.get("component", "warehouse"))
        return
    cursor.execute(
        "INSERT INTO audit.pipeline_runs (run_id, started_at_utc, status, mode) VALUES (?, ?, ?, ?)",
        report["run_id"], timestamp(report["started_at_utc"]), "RUNNING", report["mode"])


def finish_run(cursor, report):
    # Do not report success until all child inserts have succeeded.
    for ordinal, step in enumerate(report["steps"], 1):
        cursor.execute(
            "INSERT INTO audit.pipeline_steps "
            "(run_id, ordinal, name, status, started_at_utc, ended_at_utc, duration_seconds, error) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            report["run_id"], ordinal, step["name"], step["status"], timestamp(step["started_at_utc"]),
            timestamp(step["ended_at_utc"]), step["duration_seconds"], step["error"])
    for result in report["checks"]:
        cursor.execute(
            "INSERT INTO audit.quality_results "
            "(run_id, check_id, severity, status, anomaly_count, metric_value, duration_seconds, error) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            report["run_id"], result["check_id"], result["severity"], result["status"],
            result["anomaly_count"], result["metric_value"], result["duration_seconds"], result["error"])
    update_run(cursor, report)


def update_run(cursor, report):
    if report.get("parent_run_id") or report.get("component") == "e2e":
        cursor.execute(
            "UPDATE audit.pipeline_runs SET ended_at_utc=?, status=?, error=?, failure_stage=?, summary_json=? WHERE run_id=?",
            timestamp(report["ended_at_utc"]), report["status"],
            "; ".join(report["errors"] + report["audit_errors"])[:2000] or None,
            report.get("failure_stage"), json.dumps(report["summary"]) if report.get("summary") is not None else None,
            report["run_id"])
        return
    cursor.execute(
        "UPDATE audit.pipeline_runs SET ended_at_utc=?, status=?, error=? WHERE run_id=?",
        timestamp(report["ended_at_utc"]), report["status"],
        "; ".join(report["errors"] + report["audit_errors"])[:2000] or None, report["run_id"])
