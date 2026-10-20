"""Small explicit scenario specification; deterministic bytes, no random/time/SQL I/O."""

import csv
import hashlib
import io
import json
from datetime import date, timedelta
from pathlib import Path

from .config import COLUMNS, CRM_COLUMNS, DEFAULT_START_DATE, ID_MIN, PACKAGE_DIRS, PROJECT_ROOT, VERSION


def sha256(content):
    return hashlib.sha256(content).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def csv_bytes(rows):
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return text.getvalue().encode("utf-8")


def batch_id(kind, digest):
    return "batch-" + sha256(f"crm-demo-v{VERSION}|{kind}|{digest}".encode("ascii"))


def build_suite(seed=42, start_date=DEFAULT_START_DATE):
    """Return bytes and explicit expected outcomes; this function is NOT an upsert engine."""
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    start = date.fromisoformat(start_date)
    if start.isoformat() != start_date:
        raise ValueError("start-date must be YYYY-MM-DD")
    days = [(start + timedelta(days=i)).isoformat() for i in range(7)]

    def identity(tag):
        return sha256(f"crm-demo-v{VERSION}|{seed}|{start_date}|{tag}".encode("utf-8"))

    def customer(number, created=0):
        suffix = identity(f"customer-{number}")[:8]
        return dict(cst_id=str(ID_MIN + number), cst_key=f"DEMOCRM{number:04d}",
                    cst_firstname=f"DemoFirst_{number}_{suffix}", cst_lastname=f"DemoFamily_{number}_{suffix}",
                    cst_marital_status="S", cst_gndr="F" if number % 2 else "M",
                    cst_create_date=days[created])

    def event(tag, values, day, hour):
        return dict(event_id="evt-" + identity(tag), source_updated_at=f"{days[day]}T{hour:02d}:00:00Z", **values)

    c1, c2, c3 = (customer(i) for i in (1, 2, 3))
    c4, c5 = customer(4, 1), customer(5, 1)
    c1v2 = {**c1, "cst_lastname": c1["cst_lastname"] + "_v2"}
    c1v3 = {**c1, "cst_lastname": c1["cst_lastname"] + "_v3"}
    c1v4 = {**c1, "cst_lastname": c1["cst_lastname"] + "_v4"}
    c2v2 = {**c2, "cst_marital_status": "M"}
    initial = [event(f"snapshot-{i}", c, 0, 9) for i, c in enumerate((c1, c2, c3), 1)]
    new4, change1, same2 = event("new-4", c4, 1, 8), event("change-1-v2", c1v2, 1, 10), event("same-2", c2, 1, 11)
    v3, v4 = event("change-1-v3", c1v3, 2, 9), event("change-1-v4", c1v4, 2, 15)
    late5, late2 = event("late-new-5", c5, 1, 12), event("late-change-2", c2v2, 1, 12)
    stale1 = event("stale-1", {**c1, "cst_lastname": c1["cst_lastname"] + "_stale"}, 1, 13)
    same2_later = event("same-2-later", c2v2, 4, 10)
    invalid = event("invalid-key", {**customer(6), "cst_id": ""}, 6, 9)
    # The repeated delivery is byte-for-byte identical, including its batch_id/manifest.
    rows_by_package = [initial, [new4, change1, same2], [v4, v3], [change1, late5, late2],
                       [stale1, same2_later], [new4, change1, same2], [invalid]]
    kinds = ["snapshot", "delta", "delta", "delta", "delta", "delta", "negative"]

    def outcome(row, action):
        return dict(event_id=row["event_id"], cst_id=row["cst_id"], action=action)

    actions = [
        [outcome(e, "insert") for e in initial],
        [outcome(new4, "insert"), outcome(change1, "update"), outcome(same2, "no_change")],
        [outcome(v3, "update"), outcome(v4, "update")],
        [outcome(change1, "duplicate"), outcome(late5, "insert"), outcome(late2, "update")],
        [outcome(stale1, "stale"), outcome(same2_later, "no_change")],
        [outcome(e, "batch_replay") for e in (new4, change1, same2)],
        [outcome(invalid, "reject")],
    ]
    # These explicit lists are the expected SOURCE state after each atomic delivery.
    states = [
        initial,
        [change1, same2, initial[2], new4],
        [v4, same2, initial[2], new4],
        [v4, late2, initial[2], new4, late5],
        [v4, same2_later, initial[2], new4, late5],
        [v4, same2_later, initial[2], new4, late5],
        [v4, same2_later, initial[2], new4, late5],
    ]
    # Distinct customers whose BUSINESS values differ from the preceding state.
    changes = [([1, 2, 3], [], []), ([4], [1], [2, 3]), ([], [1], [2, 3, 4]),
               ([5], [2], [1, 3, 4]), ([], [], [1, 2, 3, 4, 5]),
               ([], [], [1, 2, 3, 4, 5]), ([], [], [1, 2, 3, 4, 5])]
    files, deliveries = {}, []
    for i, (directory, rows, kind) in enumerate(zip(PACKAGE_DIRS, rows_by_package, kinds)):
        content = csv_bytes(rows)
        digest = sha256(content)
        manifest = dict(contract_version=VERSION, simulator="SYNTHETIC CRM DEMO ONLY", seed=seed,
                        start_date=start_date, batch_id=batch_id(kind, digest), package_type=kind,
                        record_count=len(rows), sha256=digest, data_file="customers.csv")
        files[f"{directory}/customers.csv"] = content
        files[f"{directory}/manifest.json"] = json_bytes(manifest)
        inserted, updated, unchanged = changes[i]
        deliveries.append(dict(
            directory=directory, batch_id=manifest["batch_id"], delivery_date=days[i],
            expected_valid=i != 6, expected_contract_errors=["row 2: cst_id must be a demo integer"] if i == 6 else [],
            batch_status="REJECTED" if i == 6 else "REPLAY" if i == 5 else "APPLIED",
            event_outcomes=actions[i],
            inserted=[str(ID_MIN + n) for n in inserted], updated=[str(ID_MIN + n) for n in updated],
            unchanged=[str(ID_MIN + n) for n in unchanged],
            expected_source_state=states[i],
        ))
    expectations = dict(contract_version=VERSION, simulator="SYNTHETIC CRM DEMO ONLY", seed=seed,
                        start_date=start_date, business_key="cst_id", deliveries=deliveries,
                        note="Declarative source-state expectations, not SQL integration evidence. No deletions.")
    files["expectations.json"] = json_bytes(expectations)
    files[".gitignore"] = b"# Generated synthetic CRM demo; exclude all runtime artifacts.\n*\n"
    files["SYNTHETIC_DEMO.txt"] = b"SYNTHETIC CRM DEMO ONLY. Never feed these files to the production full-load pipeline.\n"
    return files


def generate(output_dir, seed=42, start_date=DEFAULT_START_DATE):
    output = Path(output_dir).expanduser().resolve()
    # Resolve junctions/symlinks before checking; original data and code are never destinations.
    protected = ("datasets", "csv_validation", "warehouse_pipeline", "scripts", "tests", "docs", "crm_demo", ".git", ".venv")
    if output == PROJECT_ROOT or any(output.is_relative_to(PROJECT_ROOT / name) for name in protected):
        raise ValueError("output must be a new directory outside protected project paths")
    files = build_suite(seed, start_date)
    output.mkdir(parents=True, exist_ok=False)
    # Ignore marker first: even an interrupted generation stays out of Git.
    for name in [".gitignore", *(n for n in files if n != ".gitignore")]:
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as handle:
            handle.write(files[name])
    return output
