from __future__ import annotations

import sys
from pathlib import Path

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from auth import db as auth_db


class FakeCursor:
    def __init__(self) -> None:
        self.sql: list[str] = []
        self.params: list[tuple] = []
        self.rowcount = 0

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str, params: tuple | None = None) -> None:
        self.sql.append(sql)
        self.params.append(params or ())

    def fetchall(self) -> list[dict]:
        return [{"id": "sync-stale-1"}]


class FakeConn:
    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor_obj = cursor

    def __enter__(self) -> "FakeConn":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def cursor(self, *args, **kwargs) -> FakeCursor:
        return self.cursor_obj

    def commit(self) -> None:
        return None


class FakeConnManager:
    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor = cursor

    def __enter__(self) -> FakeConn:
        return FakeConn(self.cursor)

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_reap_stale_agent_running_jobs_filters_and_threshold(monkeypatch) -> None:
    cursor = FakeCursor()
    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConnManager(cursor))

    result = auth_db.reap_stale_agent_running_jobs(stale_after_seconds=180)

    sql = "\n".join(cursor.sql)
    assert "job_status = 'running'" in sql
    assert "source_kind = 'browser_playbook'" in sql
    assert "AGENT_HEARTBEAT_LOST" in sql
    assert "last_heartbeat_at" in sql
    assert cursor.params[0][0] == 180
    assert result["failed_count"] == 1
    assert result["sync_job_ids"] == ["sync-stale-1"]


class TupleCursor(FakeCursor):
    def fetchall(self):  # fail_waiting iterates (queue_id, company_id, failed_error)
        return [("queue-001", "company-001", "AGENT_HEARTBEAT_LOST: stale")]


class TupleConnManager(FakeConnManager):
    def __enter__(self) -> FakeConn:
        return FakeConn(self.cursor)


def test_stale_agent_running_job_is_reaped_then_cascaded(monkeypatch) -> None:
    # 1) reap marks the stale agent's running job failed (dict cursor from Task 3)
    reap_cursor = FakeCursor()
    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConnManager(reap_cursor))
    reaped = auth_db.reap_stale_agent_running_jobs(stale_after_seconds=180)
    assert reaped["failed_count"] >= 1

    # 2) the fail_failed reaper targets waiting_data queue rows whose sync_job is now failed
    fail_cursor = TupleCursor()
    monkeypatch.setattr(auth_db, "get_conn", lambda: TupleConnManager(fail_cursor))
    auth_db.fail_waiting_recon_runs_with_failed_collection_jobs()
    sql = "\n".join(fail_cursor.sql)
    assert "status = 'waiting_data'" in sql
    assert "job_status IN ('failed', 'cancelled')" in sql


def test_reap_long_running_browser_jobs_marks_retryable(monkeypatch) -> None:
    # SELECT returns one stuck running job id
    cursor = FakeCursor()
    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConnManager(cursor))

    calls: list[dict] = []

    def _fake_fail(**kwargs):
        calls.append(kwargs)
        return {"id": kwargs.get("sync_job_id")}

    monkeypatch.setattr(auth_db, "mark_browser_sync_job_failed", _fake_fail)

    result = auth_db.reap_long_running_browser_jobs(max_runtime_seconds=1200)

    sql = "\n".join(cursor.sql)
    assert "job_status IN ('running', 'resuming')" in sql
    assert "source_kind = 'browser_playbook'" in sql
    assert "started_at <" in sql
    assert cursor.params[0][0] == 1200  # threshold passed to the interval

    # each stuck job goes through the canonical failure handler as RETRYABLE
    assert len(calls) == 1
    assert calls[0]["sync_job_id"] == "sync-stale-1"
    assert calls[0]["retryable"] is True
    assert calls[0]["fail_reason"] == "STALE_RUNNING_TIMEOUT"
    assert calls[0]["allowed_current_statuses"] == ("running", "resuming")
    assert result["reaped_count"] == 1
    assert result["sync_job_ids"] == ["sync-stale-1"]


def test_reap_long_running_browser_jobs_min_threshold(monkeypatch) -> None:
    cursor = FakeCursor()
    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConnManager(cursor))
    monkeypatch.setattr(auth_db, "mark_browser_sync_job_failed", lambda **kw: {"id": "x"})
    # values below the 60s floor are clamped up to 60
    auth_db.reap_long_running_browser_jobs(max_runtime_seconds=5)
    assert cursor.params[0][0] == 60


def test_reap_long_running_sync_jobs_all_sources_retryable(monkeypatch) -> None:
    cursor = FakeCursor()
    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConnManager(cursor))
    calls: list[dict] = []
    monkeypatch.setattr(
        auth_db, "mark_browser_sync_job_failed",
        lambda **kw: (calls.append(kw) or {"id": kw.get("sync_job_id")}),
    )

    result = auth_db.reap_long_running_sync_jobs(max_idle_seconds=5400)

    sql = "\n".join(cursor.sql)
    assert "job_status IN ('running', 'resuming')" in sql
    assert "source_kind" not in sql           # catch-all: NOT scoped to browser
    assert "started_at <" in sql and "updated_at <" in sql  # both timestamps (resume-safe)
    assert cursor.params[0] == (5400, 5400)    # threshold applied to both intervals

    assert len(calls) == 1
    assert calls[0]["retryable"] is True
    assert calls[0]["fail_reason"] == "STALE_RUNNING_TIMEOUT"
    assert calls[0]["allowed_current_statuses"] == ("running", "resuming")
    assert result["reaped_count"] == 1


def test_reap_long_running_sync_jobs_min_threshold(monkeypatch) -> None:
    cursor = FakeCursor()
    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConnManager(cursor))
    monkeypatch.setattr(auth_db, "mark_browser_sync_job_failed", lambda **kw: {"id": "x"})
    auth_db.reap_long_running_sync_jobs(max_idle_seconds=10)  # below 300s floor
    assert cursor.params[0] == (300, 300)
