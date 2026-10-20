import argparse
import json
import os
from pathlib import Path

from warehouse_pipeline.connection import Settings
from .runner import run


def main(argv=None):
    parser = argparse.ArgumentParser(description="Persistent sales mart; default dry-run, independent source loaders")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    parser.add_argument("--server", default=os.getenv("DW_SERVER"))
    parser.add_argument("--database", default=os.getenv("DW_DATABASE"))
    parser.add_argument("--expected-server", default=os.getenv("DW_EXPECTED_SERVER"))
    parser.add_argument("--driver", default=os.getenv("DW_ODBC_DRIVER", "ODBC Driver 17 for SQL Server"))
    parser.add_argument("--trust-server-certificate", action="store_true")
    parser.add_argument("--report-path", type=Path)
    parser.add_argument("--overwrite-report", action="store_true")
    args = parser.parse_args(argv)
    if args.execute and not (args.server and args.database and args.expected_server):
        parser.error("execute requires server, database and expected-server")
    if args.overwrite_report and not args.report_path:
        parser.error("overwrite-report requires report-path")
    settings = Settings(args.server, args.database, Path("datasets").resolve(), "", args.driver,
                        args.expected_server, args.trust_server_certificate)
    report = run(settings, execute=args.execute, report_path=args.report_path, overwrite=args.overwrite_report)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
