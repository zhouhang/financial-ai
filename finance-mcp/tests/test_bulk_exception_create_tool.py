"""Tests for execution_run_exception_bulk_create MCP tool handler."""
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
    """正常调用时，handler 应调用 auth_db.bulk_create_execution_run_exceptions 并返回 exceptions 列表。"""
    captured: dict[str, Any] = {}
    exceptions_input = [_make_exception_payload(i) for i in range(1, 251)]
    # 模拟 DB 返回 [{id, anomaly_key}] 列表
    mock_return = [
        {"id": str(i), "anomaly_key": f"key-{i}"} for i in range(1, 251)
    ]

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
            captured.update(kwargs) or mock_return
        ),
    )

    result = await execution_runs.handle_tool_call(
        "execution_run_exception_bulk_create",
        {
            "auth_token": "token",
            "run_id": "run-001",
            "scheme_code": "scheme-001",
            "exceptions": exceptions_input,
        },
    )

    assert result["success"] is True
    assert result["created"] == 250
    assert len(result["exceptions"]) == 250
    assert result["exceptions"][0]["id"] == "1"
    assert result["exceptions"][0]["anomaly_key"] == "key-1"
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


@pytest.mark.asyncio
async def test_bulk_create_tool_rejects_missing_anomaly_key(monkeypatch) -> None:
    """缺少 anomaly_key 的条目应整体拒绝，返回 success=False 并指出索引。"""
    monkeypatch.setattr(
        execution_runs,
        "_require_user",
        lambda token: {"company_id": "company-001", "id": "user-001"},
    )

    bad_exceptions = [
        _make_exception_payload(1),
        # 第 1 条（0-based index 1）缺少 anomaly_key
        {"anomaly_key": "", "anomaly_type": "source_only", "summary": "摘要"},
        _make_exception_payload(3),
    ]

    result = await execution_runs.handle_tool_call(
        "execution_run_exception_bulk_create",
        {"auth_token": "token", "run_id": "run-001", "exceptions": bad_exceptions},
    )

    assert result["success"] is False
    error_msg = result.get("error", "")
    # 应报出哪一条出问题（index 1）
    assert "1" in error_msg, f"应报告第 1 条缺失，实际错误: {error_msg!r}"
    assert "anomaly_key" in error_msg, f"应指出缺少 anomaly_key，实际错误: {error_msg!r}"


@pytest.mark.asyncio
async def test_bulk_create_tool_rejects_missing_anomaly_type(monkeypatch) -> None:
    """缺少 anomaly_type 的条目应整体拒绝。"""
    monkeypatch.setattr(
        execution_runs,
        "_require_user",
        lambda token: {"company_id": "company-001", "id": "user-001"},
    )

    bad_exceptions = [
        _make_exception_payload(1),
        {"anomaly_key": "key-2", "anomaly_type": "", "summary": "摘要"},
    ]

    result = await execution_runs.handle_tool_call(
        "execution_run_exception_bulk_create",
        {"auth_token": "token", "run_id": "run-001", "exceptions": bad_exceptions},
    )

    assert result["success"] is False
    assert "anomaly_type" in result.get("error", "")


@pytest.mark.asyncio
async def test_bulk_create_tool_rejects_missing_summary(monkeypatch) -> None:
    """缺少 summary 的条目应整体拒绝。"""
    monkeypatch.setattr(
        execution_runs,
        "_require_user",
        lambda token: {"company_id": "company-001", "id": "user-001"},
    )

    bad_exceptions = [
        {"anomaly_key": "key-0", "anomaly_type": "source_only", "summary": "   "},
    ]

    result = await execution_runs.handle_tool_call(
        "execution_run_exception_bulk_create",
        {"auth_token": "token", "run_id": "run-001", "exceptions": bad_exceptions},
    )

    assert result["success"] is False
    assert "summary" in result.get("error", "")


