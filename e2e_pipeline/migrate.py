"""Explicit additive audit migration, with the same project session lock."""

import argparse
from pathlib import Path

from warehouse_pipeline.connection import Settings, connect, check_target
from warehouse_pipeline.coordination import ProjectSession
from warehouse_pipeline.reporting import safe_error

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/audit/phase4b_migration.sql"


def migrate(settings):
    session = ProjectSession()
    try:
        session.connection = connect(settings)
        cursor = session.connection.cursor()
        try:
            target = check_target(cursor, settings, require_procedures=False)
            print(f"Confirmed before migration: {target}", flush=True)
            session.acquire(cursor, target)
            cursor.execute(SCRIPT.read_text(encoding="utf-8"))
            while cursor.nextset():
                pass
        finally:
            cursor.close()
    finally:
        session.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Explicit Phase 4B additive audit migration")
    for name in ("server", "database", "expected-server"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--trust-server-certificate", action="store_true")
    parser.add_argument("--driver", default="ODBC Driver 17 for SQL Server")
    args = parser.parse_args(argv)
    settings = Settings(args.server, args.database, Path("datasets"), "", args.driver,
                        args.expected_server, args.trust_server_certificate)
    try:
        migrate(settings)
    except Exception as exc:
        print(safe_error(exc))
        return 1
    print("Phase 4B audit migration verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
