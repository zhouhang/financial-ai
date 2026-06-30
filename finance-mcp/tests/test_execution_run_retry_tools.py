from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from tools import execution_runs


def _fake_user() -> dict[str, str]:
    return {"company_id": "company-1", "user_id": "user-1"}


def test_execution_run_list_schema_includes_keyword() -> None:
    tools = {tool.name: tool for tool in execution_runs.create_tools()}

    schema = tools["execution_run_list"].inputSchema

    assert schema["properties"]["keyword"] == {"type": "string"}
    assert "keyword" not in schema["required"]


def test_run_list_passes_keyword_to_list_and_count(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, dict[str, Any]] = {}

    def fake_require_user(auth_token: str) -> dict[str, str]:
        assert auth_token == "token"
        return _fake_user()

    def fake_list_execution_runs(**kwargs: Any) -> list[dict[str, Any]]:
        captured["list"] = kwargs
        return [{"id": "run-1"}]

    def fake_count_execution_runs(**kwargs: Any) -> int:
        captured["count"] = kwargs
        return 7

    monkeypatch.setattr(execution_runs, "_require_user", fake_require_user)
    monkeypatch.setattr(execution_runs.auth_db, "list_execution_runs", fake_list_execution_runs)
    monkeypatch.setattr(execution_runs.auth_db, "count_execution_runs", fake_count_execution_runs)

    result = execution_runs._run_list(
        {
            "auth_token": "token",
            "scheme_code": "scheme-1",
            "plan_code": "plan-1",
            "keyword": "履冰",
            "started_at_from": "2026-06-01",
            "started_at_to": "2026-06-22",
            "limit": 20,
            "offset": 40,
        }
    )

    assert result == {"success": True, "count": 1, "total": 7, "runs": [{"id": "run-1"}]}
    assert captured["list"]["keyword"] == "履冰"
    assert captured["count"]["keyword"] == "履冰"


def test_run_update_passes_retry_time_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_require_user(auth_token: str) -> dict[str, str]:
        assert auth_token == "token"
        return _fake_user()

    def fake_update_execution_run(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"id": kwargs["run_id"], "execution_status": kwargs["execution_status"]}

    monkeypatch.setattr(execution_runs, "_require_user", fake_require_user)
    monkeypatch.setattr(execution_runs.auth_db, "update_execution_run", fake_update_execution_run)

    result = execution_runs._run_update(
        {
            "auth_token": "token",
            "run_id": "run-1",
            "execution_status": "running",
            "restart_started_at_now": True,
            "reset_finished_at": True,
        }
    )

    assert result == {"success": True, "run": {"id": "run-1", "execution_status": "running"}}
    assert captured["company_id"] == "company-1"
    assert captured["run_id"] == "run-1"
    assert captured["execution_status"] == "running"
    assert captured["restart_started_at_now"] is True
    assert captured["reset_finished_at"] is True


def test_exception_clear_by_run_delegates_to_auth_db(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_require_user(auth_token: str) -> dict[str, str]:
        assert auth_token == "token"
        return _fake_user()

    def fake_delete_execution_run_exceptions_by_run_id(**kwargs: Any) -> int:
        captured.update(kwargs)
        return 7

    monkeypatch.setattr(execution_runs, "_require_user", fake_require_user)
    monkeypatch.setattr(
        execution_runs.auth_db,
        "delete_execution_run_exceptions_by_run_id",
        fake_delete_execution_run_exceptions_by_run_id,
    )

    result = execution_runs._run_exception_clear_by_run(
        {"auth_token": "token", "run_id": "run-1"}
    )

    assert result == {"success": True, "deleted_count": 7}
    assert captured == {"company_id": "company-1", "run_id": "run-1"}


@pytest.mark.asyncio
async def test_exception_clear_by_run_failure_returns_tool_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_require_user(auth_token: str) -> dict[str, str]:
        assert auth_token == "token"
        return _fake_user()

    def fake_delete_execution_run_exceptions_by_run_id(**kwargs: Any) -> int:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(execution_runs, "_require_user", fake_require_user)
    monkeypatch.setattr(
        execution_runs.auth_db,
        "delete_execution_run_exceptions_by_run_id",
        fake_delete_execution_run_exceptions_by_run_id,
    )

    result = await execution_runs.handle_tool_call(
        "execution_run_exception_clear_by_run",
        {"auth_token": "token", "run_id": "run-1"},
    )

    assert result["success"] is False
    assert "database unavailable" in result["error"]
