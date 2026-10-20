"""Privacy-safe run reports and exclusive report reservation."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pyodbc


class PipelineError(Exception):
    """Only developer-authored, data-free messages may use this exception."""


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def safe_error(exc):
    if isinstance(exc, pyodbc.Error):
        state = str(exc.args[0]) if exc.args else "unknown"
        state = state if len(state) == 5 and state.isalnum() else "unknown"
        return f"SQL operation failed (SQLSTATE={state}). Inspect the failing step in SSMS."
    if isinstance(exc, PipelineError):
        return str(exc)
    # CSV headers, filenames and driver/parser exception text may contain personal data.
    return f"{type(exc).__name__}: operation failed; raw details omitted."


def csv_summary(results):
    return [dict(file_index=i, status=r.status, record_count=r.record_count,
                 count_complete=r.count_complete, error_count=len(r.errors),
                 warning_count=len(r.warnings),
                 warnings=["Missing final newline; SQL BULK INSERT may omit the last record."
                           for w in r.warnings if w.startswith("No final newline:")])
            for i, r in enumerate(results, 1)]


def reserve_report(path, dataset_root, overwrite=False):
    if path is None:
        if overwrite:
            raise PipelineError("--overwrite-report requires --report-path.")
        return None
    path = Path(path).expanduser().resolve()
    if path.suffix.lower() != ".json":
        raise PipelineError("Report path must end in .json.")
    if dataset_root and path.is_relative_to(Path(dataset_root).resolve()):
        raise PipelineError("Report must be outside the dataset directory.")
    path.parent.mkdir(parents=True, exist_ok=True)
    # Reserve before any load: an existing report or inaccessible path prevents mutation.
    return path.open("w" if overwrite else "x", encoding="utf-8")


def write_report(handle, report):
    handle.seek(0)
    json.dump(report, handle, indent=2, ensure_ascii=False, allow_nan=False)
    handle.write("\n")
    handle.truncate()
    handle.flush()
