import json
from unittest.mock import MagicMock

import pyodbc
import pytest

from mart_pipeline import runner
from mart_pipeline.__main__ import main
from warehouse_pipeline.connection import Settings


@pytest.fixture
def sql(monkeypatch,tmp_path):
    settings=Settings("host","DataWarehouse",tmp_path/"datasets","",expected_server="host")
    cursor=MagicMock();cursor.execute.return_value=cursor;cursor.nextset.return_value=False
    cursor.description=[(x,) for x in ("check_id","severity","description","anomaly_count","metric_value")]
    cursor.fetchall.return_value=[("M12","ERROR","Business multisets",0,None),("U02","WARNING","Unknown order",19,None)]
    cursor.fetchone.return_value=(5,)
    connection=MagicMock(autocommit=True);connection.cursor.return_value=cursor
    call=MagicMock(return_value=connection)
    monkeypatch.setattr(runner,"connect",call)
    monkeypatch.setattr(runner.ProjectSession,"acquire",MagicMock())
    monkeypatch.setattr(runner,"check_target",MagicMock(return_value=("host","DataWarehouse")))
    return settings,cursor,connection,call


def test_default_dry_no_connection(sql,tmp_path):
    settings,_,_,call=sql
    report=runner.run(settings,report_path=tmp_path/"dry.json")
    assert report["status"]=="PASS" and not report["committed"]
    call.assert_not_called()


def test_warnings_commit_once_after_quality(sql):
    settings,cursor,connection,_=sql
    report=runner.run(settings,execute=True)
    assert report["status"]=="PASS" and report["committed"] is True
    commands=[c.args[0] for c in cursor.execute.call_args_list]
    assert commands.index("EXEC mart.check_quality;")<commands.index("COMMIT TRANSACTION;")
    assert sum("BEGIN TRANSACTION" in x for x in commands)==1
    assert "SERIALIZABLE" in commands[0]
    connection.commit.assert_not_called()


def test_reconciliation_failure_rolls_back_and_report(sql,tmp_path):
    settings,cursor,_,_=sql
    cursor.fetchall.return_value=[("M12","ERROR","Multiplicity difference",2,None)]
    path=tmp_path/"fail.json"; report=runner.run(settings,execute=True,report_path=path)
    assert report["status"]=="FAIL" and report["checks"][0]["anomaly_count"]==2
    commands=[c.args[0] for c in cursor.execute.call_args_list]
    assert "COMMIT TRANSACTION;" not in commands
    assert "IF XACT_STATE()<>0 ROLLBACK TRANSACTION;" in commands
    assert json.loads(path.read_text())["status"]=="FAIL"


@pytest.mark.parametrize("late",[False,True])
def test_sql_error_cannot_commit(sql,late):
    settings,cursor,_,_=sql
    state={"sql":""}
    def execute(statement,*parameters):
        state["sql"]=statement
        if not late and statement=="EXEC mart.load_model;":raise pyodbc.Error("42000","PRIVATE (51213)")
        return cursor
    cursor.execute.side_effect=execute
    def nextset():
        if late and state["sql"]=="EXEC mart.load_model;":raise pyodbc.Error("42000","PRIVATE late")
        return False
    cursor.nextset.side_effect=nextset
    report=runner.run(settings,execute=True)
    assert report["status"]=="FAIL" and "PRIVATE" not in json.dumps(report)
    assert not any(c.args[0]=="COMMIT TRANSACTION;" for c in cursor.execute.call_args_list)


def test_existing_report_prevents_load(sql,tmp_path):
    settings,_,_,call=sql
    path=tmp_path/"existing.json";path.write_text('{"old":true}')
    assert runner.run(settings,execute=True,report_path=path)["status"]=="FAIL"
    assert json.loads(path.read_text())=={"old":True};call.assert_not_called()


def test_connection_failure_local_report(sql,tmp_path):
    settings,_,_,call=sql;call.side_effect=pyodbc.Error("08001","PRIVATE credentials")
    path=tmp_path/"connection.json";result=runner.run(settings,execute=True,report_path=path)
    assert result["status"]=="FAIL" and path.exists() and "PRIVATE" not in path.read_text()


@pytest.mark.parametrize("options",[["--execute"],["--execute","--dry-run"],["--overwrite-report"]])
def test_invalid_cli_modes(options):
    with pytest.raises(SystemExit) as error:main(options)
    assert error.value.code==2


def test_cli_default(capsys):
    assert main([])==0
    assert json.loads(capsys.readouterr().out)["mode"]=="dry-run"


def test_deployment_drift_rejected(sql,monkeypatch):
    from mart_pipeline import deploy
    settings,cursor,connection,call=sql
    monkeypatch.setattr(deploy,"connect",call)
    monkeypatch.setattr(deploy,"check_target",MagicMock(return_value=("host","DataWarehouse")))
    monkeypatch.setattr(deploy,"schema_signature",MagicMock(return_value="changed"))
    monkeypatch.setattr(deploy,"property_value",lambda c,n:{"contract_version":"1","schema_signature":"original","source_signature":"bad"}[n])
    with pytest.raises(Exception,match="Incompatible mart"):deploy.deploy(settings)
    assert not any("CREATE TABLE" in c.args[0] for c in cursor.execute.call_args_list)
