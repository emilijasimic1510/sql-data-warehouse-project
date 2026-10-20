import argparse
import json
import logging
import os
from pathlib import Path

from warehouse_pipeline.connection import Settings
from .runner import run


def main(argv=None):
    parser = argparse.ArgumentParser(description="CSV -> warehouse -> mart, default dry-run")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--execute", action="store_true")
    modes.add_argument("--dry-run", action="store_true")
    parser.add_argument("--server", default=os.getenv("DW_SERVER"))
    parser.add_argument("--database", default=os.getenv("DW_DATABASE"))
    parser.add_argument("--expected-server", default=os.getenv("DW_EXPECTED_SERVER"))
    parser.add_argument("--dataset-root", type=Path, default=os.getenv("DW_DATASET_ROOT"))
    parser.add_argument("--sql-dataset-root", default=os.getenv("DW_SQL_DATASET_ROOT"))
    parser.add_argument("--driver", default=os.getenv("DW_ODBC_DRIVER", "ODBC Driver 17 for SQL Server"))
    parser.add_argument("--trust-server-certificate", action="store_true")
    parser.add_argument("--lock-timeout-ms", type=int, default=10000)
    parser.add_argument("--report-path", type=Path)
    parser.add_argument("--overwrite-report", action="store_true")
    args = parser.parse_args(argv)
    if not args.dataset_root:
        parser.error("dataset-root is required")
    if args.execute and not (args.server and args.database and args.expected_server):
        parser.error("execute requires server, database and expected-server")
    if args.overwrite_report and not args.report_path:
        parser.error("overwrite-report requires report-path")
    if not 0 <= args.lock_timeout_ms <= 60000:
        parser.error("lock-timeout-ms must be from 0 to 60000")
    root = args.dataset_root.expanduser().resolve()
    settings = Settings(args.server, args.database, root, args.sql_dataset_root or str(root), args.driver,
                        args.expected_server, args.trust_server_certificate)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    report = run(settings, execute=args.execute, report_path=args.report_path, overwrite=args.overwrite_report,
                 lock_timeout_ms=args.lock_timeout_ms)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
