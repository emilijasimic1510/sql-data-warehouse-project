"""CLI configuration; execute is deliberately never enabled by an environment variable."""

import argparse
import logging
import os
from pathlib import Path

from .connection import Settings
from .runner import run_pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CSV -> Bronze -> Silver -> SQL quality + audit (default: dry-run)")
    parser.add_argument("--server", default=os.getenv("DW_SERVER"))
    parser.add_argument("--database", default=os.getenv("DW_DATABASE"))
    parser.add_argument("--dataset-root", type=Path, default=os.getenv("DW_DATASET_ROOT"))
    parser.add_argument("--sql-dataset-root", default=os.getenv("DW_SQL_DATASET_ROOT"))
    parser.add_argument("--driver", default=os.getenv("DW_ODBC_DRIVER", "ODBC Driver 17 for SQL Server"))
    parser.add_argument("--expected-server", default=os.getenv("DW_EXPECTED_SERVER"))
    parser.add_argument("--trust-server-certificate", action="store_true",
                        help="Skip certificate identity validation for this connection only.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true", help="Explicitly allow full Bronze and Silver reloads.")
    mode.add_argument("--quality-only", action="store_true", help="Read existing business data; write audit only. No CSV or loaders.")
    mode.add_argument("--dry-run", action="store_true", help="Validate CSV only, with no SQL connection (default).")
    parser.add_argument("--report-path", type=Path, help="New JSON file outside datasets.")
    parser.add_argument("--overwrite-report", action="store_true", help="Explicitly replace the selected JSON report.")
    args = parser.parse_args(argv)
    if not args.server or not args.database or (not args.quality_only and not args.dataset_root):
        parser.error("server and database are required; dataset-root is required except for quality-only.")
    if args.overwrite_report and not args.report_path:
        parser.error("--overwrite-report requires --report-path.")
    root = Path(args.dataset_root).expanduser().resolve() if args.dataset_root else Path("datasets").resolve()
    settings = Settings(
        server=args.server, database=args.database, dataset_root=root,
        sql_dataset_root=args.sql_dataset_root or str(root), driver=args.driver,
        expected_server=args.expected_server, trust_server_certificate=args.trust_server_certificate,
    )
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return run_pipeline(settings, execute=args.execute, quality_only=args.quality_only,
                        report_path=args.report_path, overwrite_report=args.overwrite_report)


if __name__ == "__main__":
    raise SystemExit(main())
