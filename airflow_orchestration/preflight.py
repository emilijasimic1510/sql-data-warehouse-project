"""Container-side read-only SQL target check. No loads, migrations or lock writes."""
import json
import os
from types import SimpleNamespace

from airflow_orchestration.adapter import settings_from_connection
from warehouse_pipeline.connection import check_target, connect


def main():
    connection = None
    try:
        value = json.loads(os.environ['AIRFLOW_CONN_WAREHOUSE_SQLSERVER'])
        config = SimpleNamespace(host=value.get('host'), port=value.get('port'),
                                 schema=value.get('schema'), login=value.get('login'),
                                 password=value.get('password'), extra_dejson=value.get('extra', {}))
        settings = settings_from_connection(config, os.environ)
        connection = connect(settings)
        cursor = connection.cursor()
        try:
            server, database = check_target(cursor, settings)
            print(json.dumps(dict(status='PASS', server=server, database=database)))
        finally:
            cursor.close()
    except Exception:
        raise SystemExit('SQL preflight FAIL; no loading attempted; verify protected connection configuration.') from None
    finally:
        if connection is not None:
            connection.close()


if __name__ == '__main__':
    main()
