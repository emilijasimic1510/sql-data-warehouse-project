"""Run from the repository root: python -m csv_validation --dataset-root datasets."""

import argparse
import json
import platform
import sys
from pathlib import Path

import pandas as pd

from .validator import validate_dataset


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate six source CSV structures (read-only).")
    parser.add_argument("--dataset-root", required=True, type=Path)
    parser.add_argument("--report-path", type=Path, help="Optional new JSON report; never overwrites a file.")
    args = parser.parse_args(argv)
    root = args.dataset_root.expanduser().resolve()
    results = validate_dataset(root)
    failed = sum(result.status == "FAIL" for result in results)
    warning_count = sum(len(result.warnings) for result in results)

    for result in results:
        count = "unavailable" if result.record_count is None else str(result.record_count)
        if result.record_count is not None and not result.count_complete:
            count += " (partial)"
        print(f"[{result.status}] {result.path} | records={count} | columns={result.columns}")
        for error in result.errors:
            print(f"  ERROR: {error}")
        for warning in result.warnings:
            print(f"  WARNING: {warning}")
    print(f"Summary: {len(results) - failed}/{len(results)} passed; {failed} failed; {warning_count} warnings.")

    if args.report_path:
        report = args.report_path.expanduser().resolve()
        try:
            # A report must never overwrite inputs or another existing file.
            if report.is_relative_to(root):
                raise ValueError("Report must be outside the dataset directory.")
            if report.suffix.lower() != ".json":
                raise ValueError("Report path must end in .json.")
            report.parent.mkdir(parents=True, exist_ok=True)
            with report.open("x", encoding="utf-8") as handle:
                json.dump(
                    {
                        "dataset_root": str(root),
                        "python_version": platform.python_version(),
                        "pandas_version": pd.__version__,
                        "passed": failed == 0,
                        "failed_files": failed,
                        "warning_count": warning_count,
                        "files": [result.to_dict() for result in results],
                    },
                    handle, indent=2, ensure_ascii=False,
                )
                handle.write("\n")
            print(f"Report: {report}")
        except (OSError, ValueError) as exc:
            print(f"Report error: {exc}", file=sys.stderr)
            return 2
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
