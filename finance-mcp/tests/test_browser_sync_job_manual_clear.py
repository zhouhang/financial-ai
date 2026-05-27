from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from auth import db as auth_db
from tools import data_sources


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
    assert "EXISTS" in sql
    assert "FROM data_sources ds" in sql
    assert "ds.id = sync_jobs.data_source_id" in sql
    assert "ds.source_kind = 'browser_playbook'" in sql
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


def test_data_source_clear_browser_sync_job_clears_valid_browser_job(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    monkeypatch.setattr(
        data_sources,
        "_require_user",
        lambda token: {"company_id": "company-001", "id": "user-001"},
    )
    monkeypatch.setattr(
        auth_db,
        "get_sync_job_with_data_source",
        lambda **kwargs: {
            "id": "sync-001",
            "company_id": "company-001",
            "data_source_id": "source-001",
            "job_status": "waiting_human_verification",
            "source_kind": "browser_playbook",
        },
    )

    def fake_clear(**kwargs):
        calls.append({"clear": kwargs})
        return {
            "id": kwargs["sync_job_id"],
            "company_id": kwargs["company_id"],
            "data_source_id": "source-001",
            "job_status": "cancelled",
            "browser_fail_reason": "MANUAL_CLEARED",
            "error_message": "MANUAL_CLEARED: operator cleared stuck browser task",
        }

    monkeypatch.setattr(auth_db, "clear_browser_sync_job_manually", fake_clear)
    monkeypatch.setattr(
        auth_db,
        "cancel_open_handoff_sessions_for_sync_job",
        lambda **kwargs: calls.append({"handoff": kwargs}) or 1,
    )

    result = asyncio.run(
        data_sources.handle_tool_call(
            "data_source_clear_browser_sync_job",
            {"auth_token": "token-1", "sync_job_id": "sync-001"},
        )
    )

    assert result["success"] is True
    assert result["job"]["job_status"] == "cancelled"
    assert result["job"]["browser_fail_reason"] == "MANUAL_CLEARED"
    assert result["message"] == "当前浏览器任务已清除，可重新下发或等待后续任务执行"
    assert calls == [
        {
            "clear": {
                "sync_job_id": "sync-001",
                "company_id": "company-001",
                "reason": "operator cleared stuck browser task",
            }
        },
        {
            "handoff": {
                "sync_job_id": "sync-001",
                "reason": "operator cleared stuck browser task",
            }
        },
    ]


def test_data_source_clear_browser_sync_job_rejects_non_browser_job(monkeypatch) -> None:
    monkeypatch.setattr(
        data_sources,
        "_require_user",
        lambda token: {"company_id": "company-001", "id": "user-001"},
    )
    monkeypatch.setattr(
        auth_db,
        "get_sync_job_with_data_source",
        lambda **kwargs: {
            "id": "sync-001",
            "company_id": "company-001",
            "data_source_id": "source-001",
            "job_status": "pending",
            "source_kind": "database",
        },
    )

    result = asyncio.run(
        data_sources.handle_tool_call(
            "data_source_clear_browser_sync_job",
            {"auth_token": "token-1", "sync_job_id": "sync-001"},
        )
    )

    assert result == {"success": False, "error": "只能清除浏览器采集任务"}


def test_data_source_clear_browser_sync_job_rejects_terminal_job(monkeypatch) -> None:
    monkeypatch.setattr(
        data_sources,
        "_require_user",
        lambda token: {"company_id": "company-001", "id": "user-001"},
    )
    monkeypatch.setattr(
        auth_db,
        "get_sync_job_with_data_source",
        lambda **kwargs: {
            "id": "sync-001",
            "company_id": "company-001",
            "data_source_id": "source-001",
            "job_status": "success",
            "source_kind": "browser_playbook",
        },
    )

    result = asyncio.run(
        data_sources.handle_tool_call(
            "data_source_clear_browser_sync_job",
            {"auth_token": "token-1", "sync_job_id": "sync-001"},
        )
    )

    assert result == {"success": False, "error": "当前任务状态不允许清除: success"}


def test_browser_worker_complete_does_not_overwrite_cancelled_job(monkeypatch) -> None:
    monkeypatch.setattr(data_sources, "_require_scheduler_user", lambda token: {"role": "system"})
    monkeypatch.setattr(
        auth_db,
        "get_unified_sync_job_by_id",
        lambda sync_job_id: {
            "id": sync_job_id,
            "company_id": "company-001",
            "data_source_id": "source-001",
            "resource_key": "browser@1",
            "job_status": "cancelled",
            "browser_fail_reason": "MANUAL_CLEARED",
            "error_message": "MANUAL_CLEARED: operator cleared stuck browser task",
            "request_payload": {"dataset_id": "dataset-001", "biz_date": "2026-05-20"},
        },
    )
    success_calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        auth_db,
        "mark_browser_sync_job_success",
        lambda **kwargs: success_calls.append(kwargs) or {"id": kwargs["sync_job_id"]},
    )

    result = asyncio.run(
        data_sources.handle_tool_call(
            "browser_sync_job_complete",
            {"worker_token": "worker", "sync_job_id": "sync-001", "records": []},
        )
    )

    assert result["success"] is True
    assert result["ignored"] is True
    assert result["job"]["job_status"] == "cancelled"
    assert success_calls == []


def test_mark_browser_sync_job_success_uses_mutable_status_guard(monkeypatch) -> None:
    cursor = FakeCursor(
        rows=[
            {
                "id": "sync-001",
                "company_id": "company-001",
                "data_source_id": "source-001",
                "job_status": "success",
            }
        ]
    )
    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConnManager(cursor))
    monkeypatch.setattr(auth_db, "mark_browser_binding_collection_seen", lambda **kwargs: 1)

    row = auth_db.mark_browser_sync_job_success(
        sync_job_id="sync-001",
        summary={},
        allowed_current_statuses=("running", "waiting_human_verification", "resuming"),
    )

    assert row is not None
    sql = "\n".join(cursor.sql)
    assert "UPDATE sync_jobs" in sql
    assert "job_status = ANY(%s::text[])" in sql
    flattened_params = [item for params in cursor.params for item in params]
    assert ["running", "waiting_human_verification", "resuming"] in flattened_params


def test_browser_worker_complete_ignores_when_guarded_success_write_loses_race(monkeypatch) -> None:
    monkeypatch.setattr(data_sources, "_require_scheduler_user", lambda token: {"role": "system"})
    jobs = [
        {
            "id": "sync-001",
            "company_id": "company-001",
            "data_source_id": "source-001",
            "resource_key": "browser@1",
            "job_status": "running",
            "request_payload": {"dataset_id": "dataset-001", "biz_date": "2026-05-20"},
        },
        {
            "id": "sync-001",
            "company_id": "company-001",
            "data_source_id": "source-001",
            "resource_key": "browser@1",
            "job_status": "cancelled",
            "browser_fail_reason": "MANUAL_CLEARED",
            "error_message": "MANUAL_CLEARED: operator cleared stuck browser task",
            "request_payload": {"dataset_id": "dataset-001", "biz_date": "2026-05-20"},
        },
    ]

    def fake_get_job(sync_job_id):
        return jobs.pop(0)

    success_calls: list[dict[str, Any]] = []
    monkeypatch.setattr(auth_db, "get_unified_sync_job_by_id", fake_get_job)
    monkeypatch.setattr(
        auth_db,
        "get_shop_runtime_binding_for_source",
        lambda **kwargs: {"shop_id": "shop-001", "playbook_id": "playbook-001"},
    )
    monkeypatch.setattr(
        auth_db,
        "mark_browser_sync_job_success",
        lambda **kwargs: success_calls.append(kwargs) or None,
    )

    result = asyncio.run(
        data_sources.handle_tool_call(
            "browser_sync_job_complete",
            {"worker_token": "worker", "sync_job_id": "sync-001", "records": []},
        )
    )

    assert result["success"] is True
    assert result["ignored"] is True
    assert result["job"]["job_status"] == "cancelled"
    assert result["message"] == "browser sync_job already left active state: cancelled"
    assert success_calls[0]["allowed_current_statuses"] == tuple(
        data_sources.BROWSER_SYNC_WORKER_MUTABLE_STATUSES
    )


def test_browser_worker_fail_does_not_overwrite_cancelled_job(monkeypatch) -> None:
    monkeypatch.setattr(data_sources, "_require_scheduler_user", lambda token: {"role": "system"})
    monkeypatch.setattr(
        auth_db,
        "get_unified_sync_job_by_id",
        lambda sync_job_id: {
            "id": sync_job_id,
            "company_id": "company-001",
            "data_source_id": "source-001",
            "job_status": "cancelled",
            "browser_fail_reason": "MANUAL_CLEARED",
            "error_message": "MANUAL_CLEARED: operator cleared stuck browser task",
        },
    )
    fail_calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        auth_db,
        "mark_browser_sync_job_failed",
        lambda **kwargs: fail_calls.append(kwargs) or {"id": kwargs["sync_job_id"]},
    )

    result = asyncio.run(
        data_sources.handle_tool_call(
            "browser_sync_job_fail",
            {"worker_token": "worker", "sync_job_id": "sync-001", "fail_reason": "PAGE_CHANGED"},
        )
    )

    assert result["success"] is True
    assert result["ignored"] is True
    assert result["job"]["job_status"] == "cancelled"
    assert fail_calls == []


def test_mark_browser_sync_job_failed_uses_mutable_status_guard(monkeypatch) -> None:
    cursor = FakeCursor(
        rows=[
            {
                "id": "sync-001",
                "company_id": "company-001",
                "data_source_id": "source-001",
                "job_status": "failed",
            }
        ]
    )
    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConnManager(cursor))
    monkeypatch.setattr(auth_db, "apply_browser_binding_failure_transition", lambda **kwargs: 1)

    row = auth_db.mark_browser_sync_job_failed(
        sync_job_id="sync-001",
        error_message="page changed",
        fail_reason="PAGE_CHANGED",
        allowed_current_statuses=("running", "waiting_human_verification", "resuming"),
    )

    assert row is not None
    sql = "\n".join(cursor.sql)
    assert "UPDATE sync_jobs" in sql
    assert "job_status = ANY(%s::text[])" in sql
    flattened_params = [item for params in cursor.params for item in params]
    assert ["running", "waiting_human_verification", "resuming"] in flattened_params


def test_browser_worker_fail_ignores_when_guarded_failed_write_loses_race(monkeypatch) -> None:
    monkeypatch.setattr(data_sources, "_require_scheduler_user", lambda token: {"role": "system"})
    jobs = [
        {
            "id": "sync-001",
            "company_id": "company-001",
            "data_source_id": "source-001",
            "job_status": "running",
        },
        {
            "id": "sync-001",
            "company_id": "company-001",
            "data_source_id": "source-001",
            "job_status": "cancelled",
            "browser_fail_reason": "MANUAL_CLEARED",
            "error_message": "MANUAL_CLEARED: operator cleared stuck browser task",
        },
    ]

    def fake_get_job(sync_job_id):
        return jobs.pop(0)

    fail_calls: list[dict[str, Any]] = []
    monkeypatch.setattr(auth_db, "get_unified_sync_job_by_id", fake_get_job)
    monkeypatch.setattr(
        auth_db,
        "mark_browser_sync_job_failed",
        lambda **kwargs: fail_calls.append(kwargs) or None,
    )

    result = asyncio.run(
        data_sources.handle_tool_call(
            "browser_sync_job_fail",
            {"worker_token": "worker", "sync_job_id": "sync-001", "fail_reason": "PAGE_CHANGED"},
        )
    )

    assert result["success"] is True
    assert result["ignored"] is True
    assert result["job"]["job_status"] == "cancelled"
    assert result["message"] == "browser sync_job already left active state: cancelled"
    assert fail_calls[0]["allowed_current_statuses"] == tuple(
        data_sources.BROWSER_SYNC_WORKER_MUTABLE_STATUSES
    )
