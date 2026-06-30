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

    def fetchall(self) -> list[tuple[str, str, str]]:
        return [("queue-001", "company-001", "AGENT_INTERRUPTED: browser-agent restarted")]


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


def test_requeue_ready_waiting_requires_non_empty_collection_jobs(monkeypatch) -> None:
    cursor = FakeCursor()
    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConnManager(cursor))

    auth_db.requeue_ready_waiting_recon_runs()

    sql = "\n".join(cursor.sql)
    assert "jsonb_array_length(collection_job_ids) > 0" in sql
    assert "status = 'waiting_data'" in sql
    # Resume metadata must be bumped independently of business retry budget.
    assert "data_wait_resume_count" in sql
    assert "last_data_wait_resumed_at" in sql
    assert "updated_at = CURRENT_TIMESTAMP" in sql


def test_mark_waiting_data_persists_collection_job_ids_and_timestamp(monkeypatch) -> None:
    cursor = FakeCursor()
    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConnManager(cursor))
    monkeypatch.setattr(auth_db, "_RECON_WAITING_DATA_RETRY_SECONDS", 30)

    auth_db.mark_recon_run_waiting_data(
        job_id="queue-001",
        waiting_reason="browser_collection_pending",
        waiting_datasets=[{"dataset_id": "dataset-001"}],
        collection_job_ids=["sync-001"],
        wait_minutes=90,
    )

    sql = "\n".join(cursor.sql)
    assert "status = 'waiting_data'" in sql
    assert "jsonb_set(run_context, '{execution_run_id}'" in sql
    assert "collection_job_ids = %s::jsonb" in sql
    assert "updated_at = CURRENT_TIMESTAMP" in sql
    assert "INTERVAL '5 minutes'" not in sql
    assert "INTERVAL '1 second'" in sql
    assert cursor.params[0][2] == 30


def test_fail_waiting_recon_runs_with_failed_browser_jobs_uses_collection_job_ids(monkeypatch) -> None:
    cursor = FakeCursor()
    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConnManager(cursor))

    auth_db.fail_waiting_recon_runs_with_failed_collection_jobs()

    sql = "\n".join(cursor.sql)
    assert "status = 'waiting_data'" in sql
    assert "jsonb_array_elements_text(collection_job_ids)" in sql
    assert "s.job_status IN ('failed', 'cancelled')" in sql
    assert "s.error_message" in sql
    assert "UPDATE execution_runs" in sql
    assert "failed_stage = 'data_waiting'" in sql


def test_fail_expired_waiting_exempts_empty_result_retry(monkeypatch) -> None:
    cursor = FakeCursor()
    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConnManager(cursor))

    auth_db.fail_expired_waiting_recon_runs()

    sql = "\n".join(cursor.sql)
    assert "wait_deadline_at <= CURRENT_TIMESTAMP" in sql
    assert "EMPTY_RESULT" in sql
    assert "next_retry_at IS NOT NULL" in sql
    assert "BROWSER_EMPTY_RETRY_CUTOFF_GRACE_SECONDS" not in sql
    assert "TIME '18:30'" in sql


def test_fail_expired_waiting_keeps_empty_result_active_after_cutoff(monkeypatch) -> None:
    cursor = FakeCursor()
    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConnManager(cursor))

    auth_db.fail_expired_waiting_recon_runs()

    sql = "\n".join(cursor.sql)
    assert "s.browser_fail_reason = 'EMPTY_RESULT'" in sql
    assert "s.job_status IN ('pending', 'queued', 'running')" in sql
    # The collection job owns the cutoff decision, but waiting_data only gives a bounded
    # post-cutoff grace period so an offline collector cannot keep the recon run forever.
    empty_result_guard = sql.split("s.browser_fail_reason = 'EMPTY_RESULT'", 1)[0]
    assert "CURRENT_TIMESTAMP < (CURRENT_DATE + TIME '18:30')" not in empty_result_guard
    assert "CURRENT_DATE + TIME '18:30' + (%s * INTERVAL '1 second')" in sql


def test_success_collection_job_lookup_excludes_verification_jobs(monkeypatch) -> None:
    cursor = FakeCursor()
    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConnManager(cursor))

    auth_db.find_success_dataset_collection_sync_job(
        company_id="company-001",
        data_source_id="source-001",
        dataset_id="dataset-001",
        resource_key="browser-orders",
        biz_date="2026-06-15",
    )

    sql = "\n".join(cursor.sql)
    assert "COALESCE(is_verification, FALSE) IS FALSE" in sql
