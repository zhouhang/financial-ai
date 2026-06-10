"""Tests for execution_run_exception_bulk_create MCP tool handler.

TDD RED phase: these tests must fail until the implementation is added.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from tools import execution_runs


def _make_exception_payload(idx: int) -> dict[str, object]:
    return {
        "anomaly_key": f"key-{idx}",
        "anomaly_type": "source_only",
        "summary": f"差异摘要 {idx}",
        "detail_json": {"订单号": f"ORD-{idx}"},
        "owner_name": "财务负责人",
        "owner_identifier": f"ding-user-{idx % 3}",
    }


@pytest.mark.asyncio
async def test_bulk_create_tool_is_routable(monkeypatch) -> None:
    """execution_run_exception_bulk_create 工具必须在 handle_tool_call 中可路由。"""
    # 即便鉴权失败，也不应返回 "未知工具"
    result = await execution_runs.handle_tool_call(
        "execution_run_exception_bulk_create",
        {"auth_token": "bad-token", "run_id": "run-001", "exceptions": []},
    )
    assert result.get("error") != "未知工具: execution_run_exception_bulk_create", (
        "bulk_create 工具未注册到 handle_tool_call 路由"
    )


@pytest.mark.asyncio
async def test_bulk_create_tool_validates_missing_run_id(monkeypatch) -> None:
    """缺 run_id 时应返回 success=False 及错误信息。"""
    monkeypatch.setattr(
        execution_runs,
        "_require_user",
        lambda token: {"company_id": "company-001", "id": "user-001"},
    )

    result = await execution_runs.handle_tool_call(
        "execution_run_exception_bulk_create",
        {"auth_token": "token", "exceptions": [_make_exception_payload(1)]},
    )

    assert result["success"] is False
    assert "run_id" in result.get("error", "").lower() or "run_id" in str(result)


@pytest.mark.asyncio
async def test_bulk_create_tool_calls_db_bulk_function(monkeypatch) -> None:
    """正常调用时，handler 应调用 auth_db.bulk_create_execution_run_exceptions。"""
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        execution_runs,
        "_require_user",
        lambda token: {"company_id": "company-001", "id": "user-001"},
    )
    monkeypatch.setattr(
        execution_runs.auth_db,
        "get_execution_run",
        lambda company_id, run_id: {
            "id": run_id,
            "scheme_code": "scheme-001",
            "company_id": company_id,
        },
    )
    monkeypatch.setattr(
        execution_runs.auth_db,
        "bulk_create_execution_run_exceptions",
        lambda **kwargs: (
            captured.update(kwargs) or len(kwargs["exceptions"])
        ),
    )

    exceptions = [_make_exception_payload(i) for i in range(1, 251)]

    result = await execution_runs.handle_tool_call(
        "execution_run_exception_bulk_create",
        {
            "auth_token": "token",
            "run_id": "run-001",
            "scheme_code": "scheme-001",
            "exceptions": exceptions,
        },
    )

    assert result["success"] is True
    assert result["created"] == 250
    assert captured["company_id"] == "company-001"
    assert captured["run_id"] == "run-001"
    assert len(captured["exceptions"]) == 250


@pytest.mark.asyncio
async def test_bulk_create_tool_is_in_tool_names_set(monkeypatch) -> None:
    """execution_run_exception_bulk_create 应在 _EXECUTION_TOOL_NAMES 中（以便 unified_mcp 路由）。"""
    import unified_mcp_server

    assert "execution_run_exception_bulk_create" in unified_mcp_server._EXECUTION_TOOL_NAMES, (
        "bulk_create 工具未添加到 _EXECUTION_TOOL_NAMES"
    )
