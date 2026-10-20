"""Versioned demo contract, separate from csv_validation's six-source configuration."""

from pathlib import Path

VERSION = 1
DEFAULT_SEED = 42
DEFAULT_START_DATE = "2026-01-01"
ID_MIN = 1_900_000_000
ID_MAX = 1_900_000_999
BUSINESS_KEY = "cst_id"
CRM_COLUMNS = (
    "cst_id", "cst_key", "cst_firstname", "cst_lastname",
    "cst_marital_status", "cst_gndr", "cst_create_date",
)
COLUMNS = ("event_id", "source_updated_at", *CRM_COLUMNS)
PACKAGE_DIRS = (
    "00_snapshot", "01_changes", "02_versions", "03_late_arrival",
    "04_stale", "05_replay", "06_negative",
)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "demo_output" / "crm-seed-42"
