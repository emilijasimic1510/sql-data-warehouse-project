"""SQL connection with Windows default, optional runtime SQL credentials and target checks."""

from dataclasses import dataclass, field
from pathlib import Path

import pyodbc


@dataclass(frozen=True)
class Settings:
    server: str
    database: str
    dataset_root: Path
    sql_dataset_root: str
    driver: str = "ODBC Driver 17 for SQL Server"
    expected_server: str | None = None
    trust_server_certificate: bool = False
    auth_mode: str = "windows"
    username: str | None = field(default=None, repr=False)
    password: str | None = field(default=None, repr=False)


def odbc_value(value: str) -> str:
    # Escape connection-string values; do not accept raw connection strings.
    return "{" + value.replace("}", "}}") + "}"


def connect(settings: Settings):
    if settings.auth_mode == "windows":
        authentication = "Trusted_Connection=yes;"
    elif settings.auth_mode == "sql" and settings.username and settings.password:
        authentication = f"UID={odbc_value(settings.username)};PWD={odbc_value(settings.password)};"
    else:
        raise ValueError("Invalid authentication configuration.")
    connection_string = (
        f"DRIVER={odbc_value(settings.driver)};"
        f"SERVER={odbc_value(settings.server)};"
        f"DATABASE={odbc_value(settings.database)};"
        f"{authentication}Encrypt=yes;"
        f"TrustServerCertificate={'yes' if settings.trust_server_certificate else 'no'};"
    )
    # Keep the SQL procedures' existing statement-by-statement commit behavior.
    return pyodbc.connect(connection_string, autocommit=True, timeout=10)


def check_target(cursor, settings: Settings, require_procedures=True) -> tuple[str, str]:
    row = cursor.execute("SELECT CAST(@@SERVERNAME AS nvarchar(128)), DB_NAME()").fetchone()
    server, database = row
    if database.casefold() != settings.database.casefold():
        raise ValueError("Connected database differs from the requested database.")
    if database.casefold() in {"master", "model", "msdb", "tempdb"}:
        raise ValueError("System databases cannot be pipeline targets.")
    if settings.expected_server and server.casefold() != settings.expected_server.casefold():
        raise ValueError("Connected instance differs from --expected-server.")
    for procedure in (("bronze.load_bronze", "silver.load_silver") if require_procedures else ()):
        row = cursor.execute("SELECT OBJECT_ID(?, N'P')", procedure).fetchone()
        if row[0] is None:
            raise ValueError(f"Required procedure missing or not visible: {procedure}")
    return server, database
