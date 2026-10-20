"""Check the CSV contract before reading it as text with Pandas."""

import csv
from collections import Counter
from dataclasses import asdict, dataclass, field
from io import StringIO
from pathlib import Path

import pandas as pd

from .config import EXPECTED_FILES


@dataclass
class FileResult:
    path: str
    columns: list[str] = field(default_factory=list)
    record_count: int | None = None
    count_complete: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "FAIL" if self.errors else "PASS"

    def to_dict(self) -> dict:
        return {**asdict(self), "status": self.status}


def read_text_frame(text: str) -> pd.DataFrame:
    """Keep empty fields, NA, leading zeros and dates as literal text."""
    return pd.read_csv(
        StringIO(text),
        sep=",",
        dtype=str,
        keep_default_na=False,
        na_filter=False,
        skip_blank_lines=False,
        on_bad_lines="error",
    )


def validate_file(path: Path, expected_columns: list[str]) -> FileResult:
    result = FileResult(path=str(path))
    try:
        # Read once: both parsers inspect exactly the same bytes.
        raw = path.read_bytes()
        text = raw.decode("utf-8-sig")
    except (OSError, UnicodeError) as exc:
        result.errors.append(f"Cannot read UTF-8 CSV: {exc}")
        return result

    if raw and not raw.endswith((b"\n", b"\r")):
        result.warnings.append(
            "No final newline: SQL BULK INSERT may omit the last record "
            "(observed in Phase 1C). The validator does not modify the file."
        )

    reader = csv.reader(StringIO(text, newline=""), strict=True)
    result.record_count = 0
    try:
        result.columns = next(reader, [])
        counts = Counter(result.columns)
        duplicate = [name for name, count in counts.items() if count > 1]
        missing = [name for name in expected_columns if name not in counts]
        unexpected = [name for name in counts if name not in expected_columns]
        if duplicate:
            result.errors.append(f"Duplicate columns: {duplicate}")
        if missing:
            result.errors.append(f"Missing columns: {missing}")
        if unexpected:
            result.errors.append(f"Unexpected columns: {unexpected}")
        if not (duplicate or missing or unexpected) and result.columns != expected_columns:
            result.errors.append(f"Wrong column order; expected: {expected_columns}")

        # Pandas can pad short rows or rename duplicate headers. Check first.
        for row in reader:
            result.record_count += 1
            if len(row) != len(expected_columns):
                result.errors.append(
                    f"Record {result.record_count} (ends at line {reader.line_num}): "
                    f"expected {len(expected_columns)} fields, found {len(row)}."
                )
        result.count_complete = True
    except csv.Error as exc:
        result.errors.append(f"Invalid CSV near line {reader.line_num}: {exc}")

    if result.record_count == 0:
        result.errors.append("No data records; at least one is required.")

    if not result.errors:
        try:
            frame = read_text_frame(text)
            if list(frame.columns) != expected_columns or len(frame) != result.record_count:
                result.errors.append("Pandas and CSV structure/counts disagree.")
        except (pd.errors.ParserError, pd.errors.EmptyDataError, ValueError) as exc:
            result.errors.append(f"Pandas could not read the CSV: {exc}")
    return result


def validate_dataset(dataset_root: Path) -> list[FileResult]:
    return [
        validate_file(dataset_root / relative_path, columns)
        for relative_path, columns in EXPECTED_FILES.items()
    ]
