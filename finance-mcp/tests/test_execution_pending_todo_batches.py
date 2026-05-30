from __future__ import annotations

import sys
from pathlib import Path

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from tools import execution_runs


def test_scheduler_list_pending_todo_batches_returns_batches(monkeypatch) -> None:
    captured: dict = {}

    monkeypatch.setattr(
        execution_runs,
        "_require_scheduler_user",
        lambda token: {"role": "system", "company_id": None},
    )

    def fake_list(*, limit: int, max_age_days: int):
        captured["limit"] = limit
        captured["max_age_days"] = max_age_days
        return [
            {
                "company_id": "company-1",
                "run_id": "run-1",
                "owner_identifier": "ding-user-1",
                "todo_id": "todo-1",
                "channel_config_id": "channel-1",
            }
        ]

    monkeypatch.setattr(
        execution_runs.auth_db, "list_pending_todo_exception_batches", fake_list
    )

    result = execution_runs._scheduler_list_pending_todo_batches(
        {"auth_token": "scheduler-token", "limit": 50, "max_age_days": 7}
    )

    assert result["success"] is True
    assert result["batches"][0]["todo_id"] == "todo-1"
    assert result["batches"][0]["company_id"] == "company-1"
    assert captured["limit"] == 50
    assert captured["max_age_days"] == 7


def test_bulk_update_uses_explicit_company_for_scheduler_token(monkeypatch) -> None:
    captured: dict = {}

    monkeypatch.setattr(
        execution_runs,
        "get_user_from_token",
        lambda token: {"role": "system", "company_id": None},
    )
    monkeypatch.setattr(
        execution_runs.auth_db,
        "get_execution_run",
        lambda *, company_id, run_id: {"id": run_id},
    )

    def fake_bulk(**kwargs):
        captured["company_id"] = kwargs["company_id"]
        captured["processing_status"] = kwargs["processing_status"]
        return [{"id": "exc-1"}, {"id": "exc-2"}]

    monkeypatch.setattr(
        execution_runs.auth_db,
        "bulk_update_execution_run_exceptions_by_owner",
        fake_bulk,
    )

    result = execution_runs._exception_bulk_update_by_owner(
        {
            "auth_token": "scheduler-token",
            "company_id": "company-1",
            "run_id": "run-1",
            "owner_identifier": "ding-user-1",
            "processing_status": "owner_done",
        }
    )

    assert result["success"] is True
    assert result["updated_count"] == 2
    assert captured["company_id"] == "company-1"
    assert captured["processing_status"] == "owner_done"


def test_bulk_update_ignores_client_company_for_normal_user(monkeypatch) -> None:
    """普通用户的 company 永远取自 token，禁止用入参跨租户写。"""
    captured: dict = {}

    monkeypatch.setattr(
        execution_runs,
        "get_user_from_token",
        lambda token: {"role": "user", "company_id": "company-A"},
    )
    monkeypatch.setattr(
        execution_runs.auth_db,
        "get_execution_run",
        lambda *, company_id, run_id: {"id": run_id},
    )

    def fake_bulk(**kwargs):
        captured["company_id"] = kwargs["company_id"]
        return [{"id": "exc-1"}]

    monkeypatch.setattr(
        execution_runs.auth_db,
        "bulk_update_execution_run_exceptions_by_owner",
        fake_bulk,
    )

    execution_runs._exception_bulk_update_by_owner(
        {
            "auth_token": "user-token",
            "company_id": "company-B",
            "run_id": "run-1",
            "processing_status": "owner_done",
        }
    )

    assert captured["company_id"] == "company-A"
