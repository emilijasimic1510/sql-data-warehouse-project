"""Read-only preflight by default; one transaction per valid package in execute mode."""

import re
from pathlib import Path
from uuid import uuid4

from crm_demo.config import PACKAGE_DIRS, PROJECT_ROOT
from crm_demo.validation import verify_suite
from warehouse_pipeline.reporting import PipelineError, reserve_report, utc_now, write_report
from .database import execute_package, sql_error
from .inputs import read_package


def run(settings, *, package_dir=None, suite_dir=None, execute=False, report_path=None, overwrite=False):
    report = dict(run_id=str(uuid4()), mode="execute" if execute else "dry-run", status="RUNNING",
                  started_at_utc=utc_now(), ended_at_utc=None, packages=[], errors=[])
    handle = None
    try:
        if (package_dir is None) == (suite_dir is None):
            raise PipelineError("Choose exactly one package or suite.")
        input_root = Path(suite_dir or package_dir).resolve()
        if report_path and Path(report_path).resolve().is_relative_to(PROJECT_ROOT / "datasets"):
            raise PipelineError("Report cannot be written inside original datasets.")
        handle = reserve_report(report_path, input_root, overwrite)
        if handle:
            write_report(handle, report)
        if suite_dir:
            verified = verify_suite(suite_dir)
            if verified["status"] != "PASS":
                raise PipelineError("Demo suite differs from Phase 3A specification; nothing executed.")
            paths = [Path(suite_dir) / name for name in PACKAGE_DIRS]
        else:
            paths = [Path(package_dir)]
        for number, path in enumerate(paths, 1):
            result = dict(package_number=number, batch_id=None, status="FAIL", started_at_utc=utc_now(),
                          ended_at_utc=None, error=None, input_events=None, inserted_customers=0,
                          updated_customers=0, insert_events=0, update_events=0, no_change_events=0,
                          stale_events=0, duplicate_events=0, committed=False)
            report["packages"].append(result)
            try:
                manifest, validation, events = read_package(path)
                identity = manifest.get("batch_id")
                if isinstance(identity, str) and re.fullmatch(r"batch-[0-9a-f]{64}", identity):
                    result["batch_id"] = identity
                result["input_events"] = validation["record_count"]
                if validation["status"] != "PASS":
                    result["status"] = "REJECTED"
                    raise PipelineError("Demo contract/manifest validation failed before SQL connection.")
                if execute:
                    result.update(execute_package(settings, manifest, events), committed=True)
                else:
                    result["status"] = "VALIDATED"
            except Exception as exc:
                result["error"] = sql_error(exc)
                # A commit acknowledgement can be lost; do not claim rollback from a connection error.
                if result["status"] != "REJECTED":
                    result["status"] = "FAIL"
                    result["committed"] = None if execute else False
                result["commit_note"] = "On connection loss, reconcile batch_id in SQL before retry; replay is idempotent."
            finally:
                result["ended_at_utc"] = utc_now()
            if result["status"] in ("FAIL", "REJECTED"):
                break
        report["status"] = "FAIL" if any(p["status"] in ("FAIL", "REJECTED") for p in report["packages"]) else "PASS"
    except Exception as exc:
        report["status"] = "FAIL"
        report["errors"].append(sql_error(exc))
    finally:
        report["ended_at_utc"] = utc_now()
        if handle:
            try:
                write_report(handle, report)
            except Exception as exc:
                report["status"] = "FAIL"
                report["errors"].append(sql_error(exc))
            finally:
                handle.close()
    return report
