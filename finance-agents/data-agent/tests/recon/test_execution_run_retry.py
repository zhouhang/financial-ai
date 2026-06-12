from __future__ import annotations

from datetime import datetime, timezone
import sys
import types
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
RECON_DIR = ROOT / "graphs" / "recon"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ensure_package(name: str, path: Path) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        module.__path__ = [str(path)]
        sys.modules[name] = module
    return module


_ensure_package("graphs.recon", RECON_DIR)

from graphs.recon import auto_run_service
from graphs.recon.auto_scheme_run import nodes


def _source_run(
    status: str = "failed",
    retry_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": "run-1",
        "plan_code": "plan-1",
        "biz_date": "2026-06-10",
        "execution_status": status,
        "failed_stage": "recon",
        "failed_reason": "left dataset missing",
        "finished_at": "2026-06-10T09:00:00+08:00",
        "run_context_json": {
            "biz_date": "2026-06-10",
            "run_plan_code": "plan-1",
            "retry_history": retry_history or [],
        },
    }


@pytest.mark.asyncio
async def test_prepare_execution_run_rerun_rejects_non_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_execution_run_get(auth_token: str, run_id: str) -> dict[str, Any]:
        return {"success": True, "run": _source_run(status="success")}

    monkeypatch.setattr(auto_run_service, "execution_run_get", fake_execution_run_get)

    result = await auto_run_service.prepare_execution_run_rerun(
        auth_token="token",
        original_run_id="run-1",
        reason="用户触发重试",
    )

    assert result["success"] is False
    assert result["status"] == "invalid_request"
    assert result["error"] == "只有执行失败的运行记录可以重试"


@pytest.mark.asyncio
async def test_prepare_execution_run_rerun_builds_in_place_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_execution_run_get(auth_token: str, run_id: str) -> dict[str, Any]:
        return {"success": True, "run": _source_run(status="failed")}

    monkeypatch.setattr(auto_run_service, "execution_run_get", fake_execution_run_get)

    result = await auto_run_service.prepare_execution_run_rerun(
        auth_token="token",
        original_run_id="run-1",
        reason="用户触发重试",
    )

    assert result["success"] is True
    assert result["run_plan_code"] == "plan-1"
    assert result["biz_date"] == "2026-06-10"
    assert result["run_context"]["target_run_id"] == "run-1"
    assert result["run_context"]["execution_run_id"] == "run-1"
    assert result["run_context"]["retry_from_failed_run_id"] == "run-1"
    assert result["run_context"]["retry_reason"] == "用户触发重试"
    assert result["run_context"]["trigger_type"] == "rerun"
    assert result["source_run"]["id"] == "run-1"


def test_append_retry_history_keeps_latest_20() -> None:
    source_run = _source_run(
        retry_history=[{"attempt": index} for index in range(25)],
    )
    run_context = dict(source_run["run_context_json"])

    result = auto_run_service.append_execution_run_retry_history(
        run_context,
        source_run=source_run,
        reason="用户触发重试",
        trigger_user={"user_id": "u1", "username": "张三", "role": "admin"},
        attempted_at=datetime(2026, 6, 12, 10, 30, tzinfo=timezone.utc),
    )

    history = result["retry_history"]
    assert len(history) == 20
    assert history[-1]["reason"] == "用户触发重试"
    assert history[-1]["previous_status"] == "failed"
    assert history[-1]["previous_failed_stage"] == "recon"
    assert history[-1]["previous_failed_reason"] == "left dataset missing"
    assert history[-1]["trigger_user"]["username"] == "张三"
    assert history[0] == {"attempt": 6}


def test_append_retry_history_uses_context_reason_then_default() -> None:
    source_run = _source_run()

    from_context = auto_run_service.append_execution_run_retry_history(
        {"retry_reason": "上下文原因"},
        source_run=source_run,
        reason="",
        trigger_user={"user_id": "u1"},
        attempted_at=datetime(2026, 6, 12, 10, 30, tzinfo=timezone.utc),
    )
    assert from_context["retry_history"][-1]["reason"] == "上下文原因"

    defaulted = auto_run_service.append_execution_run_retry_history(
        {},
        source_run=source_run,
        reason="",
        trigger_user={"user_id": "u1"},
        attempted_at=datetime(2026, 6, 12, 10, 30, tzinfo=timezone.utc),
    )
    assert defaulted["retry_history"][-1]["reason"] == "用户触发重试"


@pytest.mark.asyncio
async def test_retry_success_clears_old_exceptions_even_when_no_new_anomalies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    async def fake_call_mcp_tool(name: str, payload: dict[str, Any]) -> dict[str, Any]:
        calls.append((name, payload))
        if name == "execution_run_exception_clear_by_run":
            return {"success": True, "deleted_count": 3}
        raise AssertionError(f"unexpected MCP call: {name}")

    monkeypatch.setattr(nodes, "call_mcp_tool", fake_call_mcp_tool)

    state = {
        "auth_token": "token",
        "recon_ctx": {
            "scheme_code": "scheme-1",
            "execution_run_record": {"id": "run-1"},
            "run_context": {
                "trigger_type": "rerun",
                "target_run_id": "run-1",
                "execution_run_id": "run-1",
                "retry_from_failed_run_id": "run-1",
            },
            "anomaly_items": [],
        },
    }

    result = await nodes.create_exception_tasks_node(state)

    assert calls == [
        (
            "execution_run_exception_clear_by_run",
            {"auth_token": "token", "run_id": "run-1"},
        )
    ]
    assert result["recon_ctx"]["retry_previous_exceptions_cleared"] is True
    assert result["recon_ctx"]["retry_previous_exceptions_deleted_count"] == 3


@pytest.mark.asyncio
async def test_retry_success_clears_old_exceptions_before_bulk_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def fake_call_mcp_tool(name: str, payload: dict[str, Any]) -> dict[str, Any]:
        calls.append(name)
        if name == "execution_run_exception_clear_by_run":
            return {"success": True, "deleted_count": 1}
        if name == "execution_run_exception_bulk_create":
            return {
                "success": True,
                "exceptions": [{"id": "exception-1", "anomaly_key": "a1"}],
                "created": 1,
            }
        return {"success": True}

    monkeypatch.setattr(nodes, "call_mcp_tool", fake_call_mcp_tool)
    monkeypatch.setattr(nodes, "_resolve_run_plan_default_owner", lambda run_plan: ("", "", {}, False))

    state = {
        "auth_token": "token",
        "recon_ctx": {
            "scheme_code": "scheme-1",
            "run_plan": {},
            "scheme": {},
            "execution_run_record": {"id": "run-1"},
            "run_context": {
                "trigger_type": "rerun",
                "target_run_id": "run-1",
                "execution_run_id": "run-1",
                "retry_from_failed_run_id": "run-1",
            },
            "anomaly_items": [{"item_id": "a1", "anomaly_type": "source_only"}],
        },
    }

    await nodes.create_exception_tasks_node(state)

    assert calls[0] == "execution_run_exception_clear_by_run"
    assert "execution_run_exception_bulk_create" in calls[1:]


@pytest.mark.asyncio
async def test_non_retry_success_with_no_anomalies_does_not_clear(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def fake_call_mcp_tool(name: str, payload: dict[str, Any]) -> dict[str, Any]:
        calls.append(name)
        return {"success": True}

    monkeypatch.setattr(nodes, "call_mcp_tool", fake_call_mcp_tool)

    result = await nodes.create_exception_tasks_node(
        {
            "auth_token": "token",
            "recon_ctx": {
                "scheme_code": "scheme-1",
                "execution_run_record": {"id": "run-1"},
                "run_context": {"trigger_type": "schedule"},
                "anomaly_items": [],
            },
        }
    )

    assert calls == []
    assert "retry_previous_exceptions_cleared" not in result["recon_ctx"]


@pytest.mark.asyncio
async def test_retry_success_stops_bulk_create_when_clear_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def fake_call_mcp_tool(name: str, payload: dict[str, Any]) -> dict[str, Any]:
        calls.append(name)
        if name == "execution_run_exception_clear_by_run":
            return {"success": False, "error": "delete failed"}
        if name == "execution_run_exception_bulk_create":
            raise AssertionError("bulk create must not run when retry cleanup fails")
        return {"success": True}

    monkeypatch.setattr(nodes, "call_mcp_tool", fake_call_mcp_tool)

    result = await nodes.create_exception_tasks_node(
        {
            "auth_token": "token",
            "recon_ctx": {
                "scheme_code": "scheme-1",
                "run_plan": {},
                "scheme": {},
                "execution_run_record": {"id": "run-1"},
                "run_context": {
                    "trigger_type": "rerun",
                    "target_run_id": "run-1",
                    "execution_run_id": "run-1",
                    "retry_from_failed_run_id": "run-1",
                },
                "anomaly_items": [{"item_id": "a1", "anomaly_type": "source_only"}],
            },
        }
    )

    assert calls == ["execution_run_exception_clear_by_run"]
    assert result["recon_ctx"]["retry_previous_exceptions_cleared"] is False
    assert result["recon_ctx"]["retry_previous_exceptions_clear_error"] == "delete failed"
    assert (
        result["recon_ctx"]["exception_creation_skipped_reason"]
        == "retry_previous_exceptions_clear_failed"
    )
