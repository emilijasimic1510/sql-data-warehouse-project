"""Opt-in real SQL tests: only crm_incremental synthetic data is mutated.

DW_RUN_SQL_INTEGRATION=1 is required. Demo results are retained. Test IDs 1900000900-999
are exclusive to this run and removed by exact recorded batch/event/customer identifiers.
"""
import copy
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pyodbc
import pytest

from crm_demo.generator import batch_id, csv_bytes, sha256
from crm_incremental import database, runner
from crm_incremental.deploy import deploy
from crm_incremental.inputs import canonical_event
from crm_incremental.verification import business_snapshot, customers, expected_customers
from warehouse_pipeline.connection import Settings, connect, check_target

pytestmark = pytest.mark.skipif(os.getenv("DW_RUN_SQL_INTEGRATION") != "1", reason="Opt-in local SQL integration tests")
ROOT = Path(__file__).resolve().parents[2]
TABLES = ("staging", "events", "batches", "attempts", "customers")


def counts(cursor):
    return {name:cursor.execute(f"SELECT COUNT_BIG(*) FROM crm_incremental.{name}").fetchone()[0] for name in TABLES}


@pytest.fixture(scope="module")
def sql(request):
    settings = Settings(r"DESKTOP-N1402MQ\SQLEXPRESS", "DataWarehouse", ROOT/"datasets", "",
                        expected_server=r"DESKTOP-N1402MQ\SQLEXPRESS", trust_server_certificate=True)
    conn=connect(settings); cursor=conn.cursor()
    assert check_target(cursor,settings,require_procedures=False)==(settings.expected_server,settings.database)
    assert cursor.execute("SELECT COUNT(*) FROM crm_incremental.customers WHERE cst_id BETWEEN 1900000900 AND 1900000999").fetchone()[0]==0
    evidence={"demo":[],"replay":[],"checks":{},"cleanup":False}
    tracked={"batches":set(),"events":set(),"customers":set()}
    yield settings,cursor,evidence,tracked
    # Remove only identifiers registered by these test helpers; retain all seed-42 demo results.
    try:
        cursor.execute(database.BEGIN); database.drain(cursor)
        for bid in tracked["batches"]:
            cursor.execute("DELETE s FROM crm_incremental.staging s JOIN crm_incremental.attempts a ON a.attempt_id=s.attempt_id WHERE a.batch_id=?",bid)
        for event_id in tracked["events"]:
            cursor.execute("DELETE FROM crm_incremental.events WHERE event_id=?",event_id)
        for bid in tracked["batches"]:
            cursor.execute("DELETE FROM crm_incremental.batches WHERE batch_id=?",bid)
            cursor.execute("DELETE FROM crm_incremental.attempts WHERE batch_id=?",bid)
        for customer_id in tracked["customers"]:
            cursor.execute("DELETE FROM crm_incremental.customers WHERE cst_id=?",customer_id)
        cursor.execute("COMMIT TRANSACTION;"); database.drain(cursor)
        assert cursor.execute("SELECT COUNT(*) FROM crm_incremental.customers WHERE cst_id BETWEEN 1900000900 AND 1900000999").fetchone()[0]==0
        evidence["cleanup"]=True
        before=json.loads((ROOT/"reports/phase3b-business-before.json").read_text())
        after=business_snapshot(cursor)
        evidence["business_objects_unchanged"]=before==after
        assert before==after
        evidence["final_counts"]=counts(cursor)
        evidence["pytest_failures_at_teardown"]=request.session.testsfailed
        path=ROOT/"reports"/f"phase3b-sql-evidence-{uuid4()}.json"
        path.write_text(json.dumps(evidence,indent=2),encoding="utf-8")
        print(f"SQL evidence: {path}")
    finally:
        cursor.close(); conn.close()


def make(sql, rows, kind="delta", register=True):
    _,_,_,tracked=sql
    content=csv_bytes(rows)
    manifest=dict(batch_id=batch_id(kind,sha256(content)),sha256=sha256(content),package_type=kind,record_count=len(rows))
    if register:
        tracked["batches"].add(manifest["batch_id"])
        tracked["events"].update(row["event_id"] for row in rows)
        tracked["customers"].update(int(row["cst_id"]) for row in rows)
    return manifest,[canonical_event(row) for row in rows]


def row(n, tag, when="2026-02-01T09:00:00Z", suffix=""):
    return dict(event_id="evt-"+hashlib.sha256(("phase3b-test-"+tag).encode()).hexdigest(),
                source_updated_at=when,cst_id=str(1900000000+n),cst_key=f"DEMOCRM{n:04d}",
                cst_firstname=f"DemoFirst_Test{n}",cst_lastname=f"DemoFamily_Test{n}{suffix}",
                cst_marital_status="S",cst_gndr="F",cst_create_date="2026-01-01")


def apply(sql, rows, kind="delta"):
    settings,_,_,_=sql
    manifest,events=make(sql,rows,kind)
    return database.execute_package(settings,manifest,events)


def test_01_seed42_each_state_and_replay(sql):
    settings,cursor,evidence,_=sql
    suite=ROOT/"demo_output/phase3a-seed42"
    spec=json.loads((suite/"expectations.json").read_bytes())
    assert customers(cursor)==[], "First-pass verification requires untouched demo space; never delete existing demo results."
    for delivery in spec["deliveries"]:
        report=runner.run(settings,package_dir=suite/delivery["directory"],execute=True,
                          report_path=ROOT/"reports"/f"phase3b-{delivery['directory']}.json")
        result=report["packages"][0]
        assert result["status"]==delivery["batch_status"], result
        assert customers(cursor)==expected_customers(delivery["expected_source_state"])
        assert result["inserted_customers"]==len(delivery["inserted"])
        assert result["updated_customers"]==len(delivery["updated"])
        if result["committed"]:
            outcomes=cursor.execute("SELECT event_id,outcome FROM crm_incremental.staging WHERE attempt_id=?",result["attempt_id"]).fetchall()
            assert sorted(map(tuple,outcomes))==sorted((r["event_id"],r["action"]) for r in delivery["event_outcomes"])
        evidence["demo"].append({"package":delivery["directory"],"state_matches":True,**result})
    final=customers(cursor)
    ledger_before=cursor.execute("SELECT event_id,event_hash,outcome FROM crm_incremental.events ORDER BY event_id").fetchall()
    for delivery in spec["deliveries"][:-1]:
        report=runner.run(settings,package_dir=suite/delivery["directory"],execute=True)
        result=report["packages"][0]
        assert result["status"]=="REPLAY",result
        assert result["inserted_customers"]==result["updated_customers"]==0
        assert result["duplicate_events"]==result["input_events"]
        assert customers(cursor)==final
        evidence["replay"].append({"package":delivery["directory"],**result})
    assert cursor.execute("SELECT event_id,event_hash,outcome FROM crm_incremental.events ORDER BY event_id").fetchall()==ledger_before
    assert len(ledger_before)==12
    evidence["checks"]["six_package_replay_unchanged"]=True


def test_02_duplicate_event_and_identifier_conflicts(sql):
    settings,cursor,evidence,_=sql
    original=row(901,"base")
    first=apply(sql,[original]); assert first["inserted_customers"]==1
    repeated=apply(sql,[original,original]); assert repeated["duplicate_events"]==2
    before=counts(cursor)
    changed={**original,"cst_lastname":"DemoFamily_Conflicting"}
    with pytest.raises(pyodbc.Error,match="51111"):
        apply(sql,[changed])
    assert counts(cursor)==before
    manifest,events=make(sql,[original]); manifest["sha256"]="0"*64
    with pytest.raises(pyodbc.Error,match="51110"):
        database.execute_package(settings,manifest,events)
    assert counts(cursor)==before
    # The CLI catches bad content hashes earlier; this directly tests the SQL guard as defense in depth.
    evidence["checks"]["duplicate_event_and_batch_event_conflicts"]=True


def test_03_equal_time_conflicts_and_identical_values(sql):
    _,cursor,evidence,_=sql
    with pytest.raises(pyodbc.Error,match="51112"):
        apply(sql,[row(901,"equal-conflict",suffix="_different")])
    same=apply(sql,[row(901,"equal-identical")])
    assert same["no_change_events"]==1 and same["updated_customers"]==0
    before=counts(cursor)
    with pytest.raises(pyodbc.Error,match="51112"):
        apply(sql,[row(903,"tie-a"),row(903,"tie-b",suffix="_different")])
    assert counts(cursor)==before
    first=row(904,"same-id")
    with pytest.raises(pyodbc.Error,match="51111"):
        apply(sql,[first,{**first,"cst_lastname":"DemoFamily_Other"}])
    assert counts(cursor)==before
    evidence["checks"]["equal_time_and_within_batch_conflicts"]=True


def test_04_constraint_failure_rolls_back_whole_package(sql):
    _,cursor,evidence,_=sql
    before=counts(cursor)
    # Deliberately bypass the CSV preflight at the typed SQL boundary to inject a unique-key violation.
    # First customer INSERT succeeds in the procedure, second collides on cst_key; all writes roll back.
    first=row(920,"rollback-first"); second=row(921,"rollback-second")
    second["cst_key"]=first["cst_key"]
    with pytest.raises(pyodbc.Error):
        apply(sql,[first,second])
    assert counts(cursor)==before
    assert customers(cursor,1900000920,1900000921)==[]
    evidence["checks"]["sql_unique_constraint_rollback"]=True


def test_05_observed_uncommitted_customer_then_real_sql_throw(sql,monkeypatch):
    settings,cursor,evidence,_=sql
    manifest,events=make(sql,[row(922,"precommit-fault")])
    before=counts(cursor); observation={}
    actual_connect=database.connect
    class FaultCursor:
        def __init__(self,raw): self.raw=raw
        def __getattr__(self,name): return getattr(self.raw,name)
        def execute(self,statement,*parameters):
            if statement=="COMMIT TRANSACTION;":
                observation["customer_visible_inside_transaction"]=self.raw.execute(
                    "SELECT COUNT(*) FROM crm_incremental.customers WHERE cst_id=1900000922").fetchone()[0]==1
                observation["transaction_count"]=self.raw.execute("SELECT @@TRANCOUNT").fetchone()[0]
                return self.raw.execute("THROW 51199, 'Controlled integration failure before commit', 1;")
            return self.raw.execute(statement,*parameters)
    class FaultConnection:
        def __init__(self,raw): self.raw=raw
        def __getattr__(self,name): return getattr(self.raw,name)
        def cursor(self): return FaultCursor(self.raw.cursor())
    monkeypatch.setattr(database,"connect",lambda s:FaultConnection(actual_connect(s)))
    with pytest.raises(pyodbc.Error,match="51199"):
        database.execute_package(settings,manifest,events)
    assert observation=={"customer_visible_inside_transaction":True,"transaction_count":1}
    assert counts(cursor)==before and customers(cursor,1900000922,1900000922)==[]
    evidence["checks"]["observed_precommit_sql_throw_rollback"]={**observation,"all_five_tables_restored":True}


def test_06_concurrent_same_batch_is_one_apply_one_replay(sql):
    settings,cursor,evidence,_=sql
    manifest,events=make(sql,[row(930,"concurrent")])
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(database.execute_package,settings,manifest,events) for _ in range(2)]
        results=[f.result(timeout=30) for f in futures]
    assert sorted(r["status"] for r in results)==["APPLIED","REPLAY"]
    assert len(customers(cursor,1900000930,1900000930))==1
    evidence["checks"]["concurrent_same_batch"]=[r["status"] for r in results]


def test_07_snapshot_does_not_delete_and_redeployment_preserves_data(sql):
    settings,cursor,evidence,_=sql
    previous=customers(cursor)
    result=apply(sql,[row(931,"snapshot-add")],kind="snapshot")
    assert result["inserted_customers"]==1 and customers(cursor)==previous
    before=counts(cursor)
    a=deploy(settings); b=deploy(settings)
    assert a==b and counts(cursor)==before and customers(cursor)==previous
    evidence["checks"]["snapshot_additive_redeployment_preserved"]=True
    evidence["schema_signature"]=a["schema_signature"]
