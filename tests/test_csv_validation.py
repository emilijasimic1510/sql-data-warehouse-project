import json

import pytest

from csv_validation.__main__ import main
from csv_validation.config import EXPECTED_FILES
from csv_validation.validator import read_text_frame, validate_file


def write_csv(tmp_path, content):
    path = tmp_path / "input.csv"
    path.write_text(content, encoding="utf-8", newline="")
    return path


def test_valid_text_values(tmp_path):
    text = "CID,CNTRY\n001,NA\n,\n"
    result = validate_file(write_csv(tmp_path, text), ["CID", "CNTRY"])
    assert result.status == "PASS"
    assert result.record_count == 2
    assert result.columns == ["CID", "CNTRY"]
    assert read_text_frame(text).values.tolist() == [["001", "NA"], ["", ""]]


def test_missing_file(tmp_path):
    result = validate_file(tmp_path / "missing.csv", ["CID", "CNTRY"])
    assert result.status == "FAIL"
    assert result.record_count is None
    assert "Cannot read" in result.errors[0]


@pytest.mark.parametrize("header,reason", [
    ("CID,WRONG", "Unexpected columns"),
    ("CID", "Missing columns"),
    ("CID,CNTRY,CNTRY", "Duplicate columns"),
    ("CNTRY,CID", "Wrong column order"),
])
def test_bad_headers(tmp_path, header, reason):
    result = validate_file(write_csv(tmp_path, header + "\n1,France\n"), ["CID", "CNTRY"])
    assert result.status == "FAIL"
    assert any(reason in error for error in result.errors)


@pytest.mark.parametrize("row", ["1", "1,France,extra", ""])
def test_wrong_field_count(tmp_path, row):
    result = validate_file(write_csv(tmp_path, "CID,CNTRY\n" + row + "\n"), ["CID", "CNTRY"])
    assert result.status == "FAIL"
    assert result.record_count == 1
    assert any("fields" in error for error in result.errors)


def test_header_only(tmp_path):
    result = validate_file(write_csv(tmp_path, "CID,CNTRY\n"), ["CID", "CNTRY"])
    assert result.status == "FAIL"
    assert result.record_count == 0


def test_missing_final_newline(tmp_path):
    path = write_csv(tmp_path, "CID,CNTRY\n1,France\n2,")
    original = path.read_bytes()
    result = validate_file(path, ["CID", "CNTRY"])
    assert result.status == "PASS"
    assert result.record_count == 2
    assert result.count_complete
    assert len(result.warnings) == 1
    assert path.read_bytes() == original


def test_broken_quotes(tmp_path):
    result = validate_file(write_csv(tmp_path, 'CID,CNTRY\n1,"unfinished'), ["CID", "CNTRY"])
    assert result.status == "FAIL"
    assert not result.count_complete
    assert any("Invalid CSV" in error for error in result.errors)


def test_unreadable_directory(tmp_path):
    result = validate_file(tmp_path, ["CID", "CNTRY"])
    assert result.status == "FAIL"
    assert "Cannot read" in result.errors[0]


def test_invalid_encoding(tmp_path):
    path = tmp_path / "invalid.csv"
    path.write_bytes(b"CID,CNTRY\n1,\xff\n")
    result = validate_file(path, ["CID", "CNTRY"])
    assert result.status == "FAIL"
    assert "UTF-8" in result.errors[0]


def test_utf8_bom(tmp_path):
    path = write_csv(tmp_path, "\ufeffCID,CNTRY\n1,France\n")
    assert validate_file(path, ["CID", "CNTRY"]).status == "PASS"


def test_cli_checks_all_files_and_writes_report(tmp_path, capsys):
    root = tmp_path / "datasets"
    for name, columns in EXPECTED_FILES.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            ",".join(columns) + "\n" + ",".join(["NA"] * len(columns)) + "\n",
            encoding="utf-8",
        )
    assert main(["--dataset-root", str(root)]) == 0
    (root / "source_crm/cust_info.csv").unlink()
    report = tmp_path / "reports" / "result.validation.json"
    assert main(["--dataset-root", str(root), "--report-path", str(report)]) == 1
    data = json.loads(report.read_text(encoding="utf-8"))
    assert len(data["files"]) == 6
    assert data["failed_files"] == 1
    assert "5/6 passed" in capsys.readouterr().out
    original = report.read_bytes()
    assert main(["--dataset-root", str(root), "--report-path", str(report)]) == 2
    assert report.read_bytes() == original


def test_report_cannot_write_inside_dataset(tmp_path):
    target = tmp_path / "report.json"
    assert main(["--dataset-root", str(tmp_path), "--report-path", str(target)]) == 2
    assert not target.exists()
