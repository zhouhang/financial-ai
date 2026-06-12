"""Tests for diff_digestion_service and recon_worker resolve branch."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

# ── 路径注入 ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]  # finance-agents/data-agent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
TESTS_DIR = ROOT / "tests"
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from _import_isolation import prefer_data_agent_imports

prefer_data_agent_imports(__file__)

diff_digestion_service = importlib.import_module("graphs.recon.diff_digestion_service")
recon_worker = importlib.import_module("recon_worker")


# ════════════════════════════════════════════════════════════════════════════
# Part 1: run_diff_digestion
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_run_diff_digestion_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """MCP 返回 success=True → ok=True, summary 透传。"""
    mcp_result = {
        "success": True,
        "resolved": 5,
        "reclassified": 2,
        "kept": 1,
        "open_counts": {"source_only": 1},
        "fetch_degraded": False,
    }
    mock_call = AsyncMock(return_value=mcp_result)
    monkeypatch.setattr(diff_digestion_service, "call_mcp_tool", mock_call)

    result = await diff_digestion_service.run_diff_digestion(
        auth_token="test-token",
        run_id="run-001",
        biz_date="2026-06-10",
    )

    assert result["ok"] is True
    assert result["summary"] == mcp_result
    assert result["collection_refreshed"] is False
    assert result["error"] == ""

    mock_call.assert_awaited_once_with(
        "recon_diff_digestion",
        {"worker_token": "test-token", "run_id": "run-001"},
    )


@pytest.mark.anyio
async def test_run_diff_digestion_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """MCP 返回 success=False → ok=False, error 透传。"""
    mcp_result = {"success": False, "error": "run_id 对应执行记录不存在"}
    mock_call = AsyncMock(return_value=mcp_result)
    monkeypatch.setattr(diff_digestion_service, "call_mcp_tool", mock_call)

    result = await diff_digestion_service.run_diff_digestion(
        auth_token="test-token",
        run_id="run-not-found",
        biz_date="2026-06-10",
    )

    assert result["ok"] is False
    assert result["summary"] == mcp_result
    assert result["collection_refreshed"] is False
    assert result["error"] == "run_id 对应执行记录不存在"


@pytest.mark.anyio
async def test_run_diff_digestion_empty_run_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """run_id 为空时直接返回 ok=False，不调 MCP。"""
    mock_call = AsyncMock()
    monkeypatch.setattr(diff_digestion_service, "call_mcp_tool", mock_call)

    result = await diff_digestion_service.run_diff_digestion(
        auth_token="test-token",
        run_id="",
        biz_date="2026-06-10",
    )

    assert result["ok"] is False
    assert "run_id" in result["error"]
    mock_call.assert_not_awaited()


# ════════════════════════════════════════════════════════════════════════════
# Part 2: worker _process_job resolve 分支
# ════════════════════════════════════════════════════════════════════════════

def _make_resolve_job(
    target_run_id: str = "run-999",
    biz_date: str = "2026-06-10",
) -> dict[str, Any]:
    return {
        "id": "queue-resolve-001",
        "company_id": "company-001",
        "run_plan_code": "plan-001",
        "trigger_mode": "resolve",
        "biz_date": biz_date,
        "run_context": {"target_run_id": target_run_id},
        "started_at": "2026-06-10T08:00:00+00:00",
        "created_at": "2026-06-10T07:59:00+00:00",
    }


@pytest.mark.anyio
async def test_worker_resolve_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """trigger_mode='resolve' 成功：只调 run_diff_digestion，调 recon_queue_complete；
    不调 execute_run_plan_run；不调 finalize_and_deliver_daily_digest。"""
    calls: list[tuple[str, Any]] = []

    async def fake_digestion(**kwargs: Any) -> dict[str, Any]:
        calls.append(("digestion", kwargs))
        return {
            "ok": True,
            "summary": {"success": True, "resolved": 3, "reclassified": 1, "kept": 0, "open_counts": {}},
            "collection_refreshed": False,
            "error": "",
        }

    async def fake_complete(token: str, job_id: str) -> dict[str, Any]:
        calls.append(("complete", job_id))
        return {"success": True, "job": {"finished_at": "2026-06-10T09:00:00+00:00"}}

    async def fake_execute(**kwargs: Any) -> dict[str, Any]:
        calls.append(("execute_run_plan_run", kwargs))
        return {"success": True}

    async def fake_finalize(**kwargs: Any) -> dict[str, Any]:
        calls.append(("finalize", kwargs))
        return {"success": True}

    monkeypatch.setattr(recon_worker, "run_diff_digestion", fake_digestion)
    monkeypatch.setattr(recon_worker, "recon_queue_complete", fake_complete)
    monkeypatch.setattr(recon_worker, "execute_run_plan_run", fake_execute)
    monkeypatch.setattr(recon_worker, "finalize_and_deliver_daily_digest", fake_finalize)

    await recon_worker._process_job(_make_resolve_job(), "system-token")

    call_names = [c[0] for c in calls]
    assert "digestion" in call_names, "run_diff_digestion 应被调用"
    assert "complete" in call_names, "recon_queue_complete 应被调用"
    assert "execute_run_plan_run" not in call_names, "resolve 不应走全量对账路径"
    assert "finalize" not in call_names, "resolve 不应调 finalize_and_deliver_daily_digest"

    # 验证传入 run_diff_digestion 的参数
    digestion_kwargs = next(c[1] for c in calls if c[0] == "digestion")
    assert digestion_kwargs["run_id"] == "run-999"
    assert digestion_kwargs["biz_date"] == "2026-06-10"


@pytest.mark.anyio
async def test_worker_resolve_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """消化失败 → recon_queue_fail 被调用，不调 recon_queue_complete。"""
    calls: list[tuple[str, Any]] = []

    async def fake_digestion(**kwargs: Any) -> dict[str, Any]:
        calls.append(("digestion", kwargs))
        return {
            "ok": False,
            "summary": {"success": False, "error": "方案缺少 proc_rule_code"},
            "collection_refreshed": False,
            "error": "方案缺少 proc_rule_code",
        }

    async def fake_fail(token: str, job_id: str, error: str = "") -> dict[str, Any]:
        calls.append(("fail", job_id, error))
        return {"success": True}

    async def fake_complete(token: str, job_id: str) -> dict[str, Any]:
        calls.append(("complete", job_id))
        return {"success": True}

    monkeypatch.setattr(recon_worker, "run_diff_digestion", fake_digestion)
    monkeypatch.setattr(recon_worker, "recon_queue_fail", fake_fail)
    monkeypatch.setattr(recon_worker, "recon_queue_complete", fake_complete)

    await recon_worker._process_job(_make_resolve_job(), "system-token")

    call_names = [c[0] for c in calls]
    assert "fail" in call_names, "消化失败时 recon_queue_fail 应被调用"
    assert "complete" not in call_names, "消化失败时不应调 recon_queue_complete"

    fail_call = next(c for c in calls if c[0] == "fail")
    assert "proc_rule_code" in fail_call[2]


@pytest.mark.anyio
async def test_worker_resolve_missing_target_run_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """target_run_id 为空 → 直接 recon_queue_fail，不调消化。"""
    calls: list[tuple[str, Any]] = []

    async def fake_digestion(**kwargs: Any) -> dict[str, Any]:
        calls.append(("digestion", kwargs))
        return {"ok": True, "summary": {}, "collection_refreshed": False, "error": ""}

    async def fake_fail(token: str, job_id: str, error: str = "") -> dict[str, Any]:
        calls.append(("fail", job_id, error))
        return {"success": True}

    monkeypatch.setattr(recon_worker, "run_diff_digestion", fake_digestion)
    monkeypatch.setattr(recon_worker, "recon_queue_fail", fake_fail)

    job_no_run_id = _make_resolve_job(target_run_id="")
    await recon_worker._process_job(job_no_run_id, "system-token")

    call_names = [c[0] for c in calls]
    assert "fail" in call_names, "缺 target_run_id 时应 fail"
    assert "digestion" not in call_names, "缺 target_run_id 时不应调消化"

    fail_call = next(c for c in calls if c[0] == "fail")
    assert "target_run_id" in fail_call[2]


@pytest.mark.anyio
async def test_worker_resolve_no_finalize(monkeypatch: pytest.MonkeyPatch) -> None:
    """明确断言：resolve job 成功后 finalize_and_deliver_daily_digest 绝对不被调用。"""
    finalize_called = False

    async def fake_digestion(**kwargs: Any) -> dict[str, Any]:
        return {"ok": True, "summary": {"success": True}, "collection_refreshed": False, "error": ""}

    async def fake_complete(token: str, job_id: str) -> dict[str, Any]:
        return {"success": True, "job": {}}

    async def fake_finalize(**kwargs: Any) -> dict[str, Any]:
        nonlocal finalize_called
        finalize_called = True
        return {"success": True}

    monkeypatch.setattr(recon_worker, "run_diff_digestion", fake_digestion)
    monkeypatch.setattr(recon_worker, "recon_queue_complete", fake_complete)
    monkeypatch.setattr(recon_worker, "finalize_and_deliver_daily_digest", fake_finalize)

    await recon_worker._process_job(_make_resolve_job(), "system-token")

    assert not finalize_called, "resolve 分支严禁调用 finalize_and_deliver_daily_digest"


@pytest.mark.anyio
async def test_worker_non_resolve_still_uses_execute_run_plan_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非 resolve job（schedule）仍走原来的 execute_run_plan_run 路径。"""
    calls: list[str] = []

    async def fake_execute(**kwargs: Any) -> dict[str, Any]:
        calls.append("execute_run_plan_run")
        return {
            "success": True,
            "biz_date": "2026-06-10",
            "run": {"id": "run-001", "execution_status": "success", "artifacts_json": {}},
        }

    async def fake_digestion(**kwargs: Any) -> dict[str, Any]:
        calls.append("digestion")
        return {"ok": True, "summary": {}, "collection_refreshed": False, "error": ""}

    async def fake_complete(token: str, job_id: str) -> dict[str, Any]:
        return {"success": True, "job": {"finished_at": "2026-06-10T09:00:00+00:00"}}

    async def fake_update(token: str, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {"success": True}

    async def fake_finalize(**kwargs: Any) -> dict[str, Any]:
        return {"success": True, "ready_count": 0, "delivered_count": 0, "blocked_count": 0}

    monkeypatch.setattr(recon_worker, "execute_run_plan_run", fake_execute)
    monkeypatch.setattr(recon_worker, "run_diff_digestion", fake_digestion)
    monkeypatch.setattr(recon_worker, "recon_queue_complete", fake_complete)
    monkeypatch.setattr(recon_worker, "execution_run_update", fake_update)
    monkeypatch.setattr(recon_worker, "finalize_and_deliver_daily_digest", fake_finalize)

    await recon_worker._process_job(
        {
            "id": "queue-schedule-001",
            "company_id": "company-001",
            "run_plan_code": "plan-001",
            "trigger_mode": "schedule",
            "biz_date": "2026-06-10",
            "run_context": {},
        },
        "system-token",
    )

    assert "execute_run_plan_run" in calls, "schedule job 应走原路径"
    assert "digestion" not in calls, "schedule job 不应调差异消化"


@pytest.mark.anyio
async def test_worker_rerun_passes_execution_run_id_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """rerun job 应保留原 run_context 中的 in-place retry 标识，并补充 queue_job_id。"""
    captured: dict[str, Any] = {}

    async def fake_execute_run_plan_run(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "success": True,
            "biz_date": "2026-06-10",
            "run": {"id": "run-1", "execution_status": "success", "artifacts_json": {}},
        }

    async def fake_complete(token: str, job_id: str) -> dict[str, Any]:
        return {"success": True, "job": {"finished_at": "2026-06-10T09:00:00+00:00"}}

    async def fake_update(token: str, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {"success": True}

    async def fake_finalize(**kwargs: Any) -> dict[str, Any]:
        return {"success": True, "ready_count": 0, "delivered_count": 0, "blocked_count": 0}

    monkeypatch.setattr(recon_worker, "execute_run_plan_run", fake_execute_run_plan_run)
    monkeypatch.setattr(recon_worker, "recon_queue_complete", fake_complete)
    monkeypatch.setattr(recon_worker, "execution_run_update", fake_update)
    monkeypatch.setattr(recon_worker, "finalize_and_deliver_daily_digest", fake_finalize)

    await recon_worker._process_job(
        {
            "id": "job-1",
            "company_id": "company-1",
            "run_plan_code": "plan-1",
            "biz_date": "2026-06-10",
            "trigger_mode": "rerun",
            "status": "queued",
            "run_context": {
                "target_run_id": "run-1",
                "execution_run_id": "run-1",
                "retry_from_failed_run_id": "run-1",
            },
        },
        "system-token",
    )

    assert captured["run_plan_code"] == "plan-1"
    assert captured["trigger_mode"] == "rerun"
    assert captured["run_context"]["target_run_id"] == "run-1"
    assert captured["run_context"]["execution_run_id"] == "run-1"
    assert captured["run_context"]["retry_from_failed_run_id"] == "run-1"
    assert captured["run_context"]["queue_job_id"] == "job-1"
