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


def test_fail_waiting_recon_runs_with_failed_browser_jobs_uses_collection_job_ids(monkeypatch) -> None:
    cursor = FakeCursor()
    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConnManager(cursor))

    auth_db.fail_waiting_recon_runs_with_failed_collection_jobs()

    sql = "\n".join(cursor.sql)
    assert "status = 'waiting_data'" in sql
    assert "jsonb_array_elements_text(collection_job_ids)" in sql
    assert "s.job_status = 'failed'" in sql
    assert "s.error_message" in sql
