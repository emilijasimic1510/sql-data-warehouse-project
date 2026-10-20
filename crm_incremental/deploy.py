"""Explicit deployment only, separate from normal package execution."""

import argparse
from pathlib import Path

from warehouse_pipeline.connection import Settings, connect, check_target
from .database import drain, sql_error

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/crm_incremental/deploy.sql"


def deploy(settings):
    connection = connect(settings)
    cursor = connection.cursor()
    try:
        identity = check_target(cursor, settings, require_procedures=False)
        print(f"Confirmed before deployment: {identity}", flush=True)
        cursor.execute(SCRIPT.read_text(encoding="utf-8"))
        # The script owns its own single deployment transaction; it may return rowcount sets first.
        while cursor.description is None and cursor.nextset():
            pass
        row = cursor.fetchone()
        drain(cursor)
        return dict(status=row[0], schema_signature=row[1])
    finally:
        cursor.close()
        connection.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Explicit non-destructive crm_incremental deployment")
    parser.add_argument("--server", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--expected-server", required=True)
    parser.add_argument("--driver", default="ODBC Driver 17 for SQL Server")
    parser.add_argument("--trust-server-certificate", action="store_true")
    args = parser.parse_args(argv)
    settings = Settings(args.server, args.database, Path("datasets"), "", args.driver,
                        args.expected_server, args.trust_server_certificate)
    try:
        print(deploy(settings))
    except Exception as exc:
        print(sql_error(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
