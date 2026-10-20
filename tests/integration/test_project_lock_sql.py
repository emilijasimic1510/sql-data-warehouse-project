"""Opt-in two-connection lock tests; no loaders or table mutations are executed."""

import json
import os
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import pytest

from warehouse_pipeline.connection import Settings, connect, check_target
from warehouse_pipeline.coordination import ProjectSession, RESOURCE
from warehouse_pipeline.reporting import PipelineError

pytestmark = pytest.mark.skipif(os.getenv("DW_RUN_PROJECT_LOCK_INTEGRATION") != "1", reason="Opt-in project-lock SQL tests")
ROOT = Path(__file__).resolve().parents[2]


def open_session(timeout=10000):
    settings = Settings(r"DESKTOP-N1402MQ\SQLEXPRESS", "DataWarehouse", ROOT / "datasets", "",
                        expected_server=r"DESKTOP-N1402MQ\SQLEXPRESS", trust_server_certificate=True)
    session = ProjectSession(timeout_ms=timeout)
    session.connection = connect(settings)
    cursor = session.connection.cursor()
    target = check_target(cursor, settings, require_procedures=False)
    return session, cursor, target


def test_two_connections_exclude_concurrent_writer_until_release():
    first, a, target = open_session()
    second, b, other = open_session(150)
    try:
        spids = [a.execute("SELECT @@SPID").fetchone()[0], b.execute("SELECT @@SPID").fetchone()[0]]
        assert spids[0] != spids[1] and target == other
        first.acquire(a, target)
        started = perf_counter()
        with pytest.raises(PipelineError, match="lock unavailable"):
            second.acquire(b, other)
        elapsed = perf_counter() - started
        assert first.held and not second.held
        assert a.execute("SELECT APPLOCK_MODE('public',?,'Session')", RESOURCE).fetchone()[0] == "Exclusive"
        first.release()
        second.acquire(b, other)
        assert second.held
        second.release()
        proof = dict(status="PASS", resource=RESOURCE, session_ids=spids, blocked_while_first_held=True,
                     acquired_after_release=True, timeout_ms=150, blocked_seconds=round(elapsed, 3), table_mutations=0)
        path = ROOT / "reports" / f"phase4b-lock-{uuid4()}.json"
        path.write_text(json.dumps(proof, indent=2), encoding="utf-8")
        print("Lock evidence:", path)
    finally:
        if first.connection is not None:
            a.close()
        if second.connection is not None:
            b.close()
        first.close(); second.close()


def test_exception_finally_releases_session_lock():
    first, a, target = open_session()
    second, b, other = open_session(0)
    try:
        with pytest.raises(RuntimeError, match="controlled"):
            try:
                first.acquire(a, target)
                raise RuntimeError("controlled host-side error")
            finally:
                first.close()
        second.acquire(b, other)
        assert second.held
    finally:
        if first.connection is not None:
            a.close()
        if second.connection is not None:
            b.close()
        first.close(); second.close()
