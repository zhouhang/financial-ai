from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from auth import db as auth_db


class FakeCursor:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.sql: list[str] = []
        self.params: list[tuple[Any, ...]] = []
        self.rows = rows or []
        self.fetchone_index = 0
        self.rowcount = 0

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        self.sql.append(sql)
        self.params.append(params or ())
        if "UPDATE sync_jobs" in sql or "UPDATE browser_handoff_sessions" in sql:
            self.rowcount = 1

    def fetchone(self) -> dict[str, Any] | None:
        if self.fetchone_index >= len(self.rows):
            return None
        row = self.rows[self.fetchone_index]
        self.fetchone_index += 1
        return row

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows


class FakeConn:
    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor_obj = cursor
        self.committed = False

    def __enter__(self) -> "FakeConn":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def cursor(self, *args, **kwargs) -> FakeCursor:
        return self.cursor_obj

    def commit(self) -> None:
        self.committed = True


class FakeConnManager:
    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor = cursor
        self.conn = FakeConn(cursor)

    def __enter__(self) -> FakeConn:
        return self.conn

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_clear_browser_sync_job_marks_active_job_cancelled(monkeypatch) -> None:
    cursor = FakeCursor(
        rows=[
            {
                "id": "sync-001",
                "company_id": "company-001",
                "data_source_id": "source-001",
                "job_status": "cancelled",
                "browser_fail_reason": "MANUAL_CLEARED",
                "error_message": "MANUAL_CLEARED: operator cleared stuck browser task",
            }
        ]
    )
    manager = FakeConnManager(cursor)
    monkeypatch.setattr(auth_db, "get_conn", lambda: manager)

    row = auth_db.clear_browser_sync_job_manually(
        sync_job_id="sync-001",
        company_id="company-001",
        reason="operator cleared stuck browser task",
    )

    assert row is not None
    assert row["job_status"] == "cancelled"
    assert row["browser_fail_reason"] == "MANUAL_CLEARED"
    sql = "\n".join(cursor.sql)
    assert "UPDATE sync_jobs" in sql
    assert "job_status = 'cancelled'" in sql
    assert "browser_fail_reason = 'MANUAL_CLEARED'" in sql
    assert "completed_at = CURRENT_TIMESTAMP" in sql
    assert "next_retry_at = NULL" in sql
    assert "job_status IN ('pending', 'queued', 'running', 'waiting_human_verification', 'resuming')" in sql
    assert cursor.params[-1][-2:] == ("sync-001", "company-001")
    assert manager.conn.committed is True


def test_clear_related_handoff_sessions_marks_non_final_sessions_cancelled(monkeypatch) -> None:
    cursor = FakeCursor()
    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConnManager(cursor))

    count = auth_db.cancel_open_handoff_sessions_for_sync_job(
        sync_job_id="sync-001",
        reason="operator cleared stuck browser task",
    )

    assert count == 1
    sql = "\n".join(cursor.sql)
    assert "UPDATE browser_handoff_sessions" in sql
    assert "status = 'cancelled'" in sql
    assert "manual_clear" in sql
    assert "status <> ALL" in sql
    assert "sync_job_id = %s" in sql


def test_get_browser_sync_job_with_source_filters_company_and_source_kind(monkeypatch) -> None:
    cursor = FakeCursor(
        rows=[
            {
                "id": "sync-001",
                "company_id": "company-001",
                "data_source_id": "source-001",
                "job_status": "pending",
                "source_kind": "browser_playbook",
            }
        ]
    )
    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConnManager(cursor))

    row = auth_db.get_sync_job_with_data_source(
        sync_job_id="sync-001",
        company_id="company-001",
    )

    assert row is not None
    assert row["source_kind"] == "browser_playbook"
    sql = "\n".join(cursor.sql)
    assert "FROM sync_jobs s" in sql
    assert "JOIN data_sources ds" in sql
    assert "s.id = %s" in sql
    assert "s.company_id = %s" in sql
