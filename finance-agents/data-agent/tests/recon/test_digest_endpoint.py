"""Tests for POST /recon/runs/{run_id}/diff-digestion endpoint.

TDD: tests written first, RED verified, then GREEN implemented.
"""
from __future__ import annotations

import asyncio
import importlib
import sys
import types
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ── 路径注入 ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]  # finance-agents/data-agent
RECON_DIR = ROOT / "graphs" / "recon"
TESTS_DIR = ROOT / "tests"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from _import_isolation import prefer_data_agent_imports

prefer_data_agent_imports(__file__)


def _ensure_package(name: str, path: Path) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        module.__path__ = [str(path)]
        sys.modules[name] = module
    return module


_ensure_package("graphs.recon", RECON_DIR)

auto_run_api = importlib.import_module("graphs.recon.auto_run_api")


def _auth_header() -> str:
    token = jwt.encode(
        {
            "sub": "user-001",
            "username": "admin",
            "company_id": "company-001",
        },
        auto_run_api.JWT_SECRET,
        algorithm=auto_run_api.JWT_ALGORITHM,
    )
    return f"Bearer {token}"


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(auto_run_api.router, prefix="/api")
    return TestClient(app)


def test_diff_digestion_sweep_route_accepts_json_body(client, monkeypatch) -> None:
    """/diff-digestion-sweep 必须由 body 版处理器(token 取 company + body.since_date)接管。

    回归 2026-06-26 线上 bug:@router.post 装饰器误装到后台 helper(company_id/since_date
    走 query),导致 finance-cron 发 JSON body 被 422 拒绝,凌晨自动差异消化全部失败。
    """
    monkeypatch.setattr(
        auto_run_api,
        "sweep_diff_digestion",
        AsyncMock(return_value={"success": True, "scanned": 0, "enqueued": 0, "skipped": 0}),
    )
    resp = client.post(
        "/api/recon/diff-digestion-sweep",
        headers={"Authorization": _auth_header()},
        json={"since_date": "2026-06-11"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("started") is True
    assert data.get("since_date") == "2026-06-11"


def _make_run(
    run_id: str = "run-abc",
    biz_date_in_run_context: str = "2026-06-01",
    biz_date_in_source_snapshot: str = "",
    plan_code: str = "plan-001",
) -> dict[str, Any]:
    """Construct a fake execution_run dict as returned by execution_run_get."""
    run_context_json: dict[str, Any] = {}
    if biz_date_in_run_context:
        run_context_json["biz_date"] = biz_date_in_run_context

    source_snapshot_json: dict[str, Any] = {}
    if biz_date_in_source_snapshot:
        source_snapshot_json["biz_date"] = biz_date_in_source_snapshot

    return {
        "id": run_id,
        "plan_code": plan_code,
        "scheme_code": "scheme-001",
        "run_context_json": run_context_json,
        "source_snapshot_json": source_snapshot_json,
        "execution_status": "success",
    }


def _make_execution_run_for_rerun(status: str = "failed") -> dict[str, object]:
    return {
        "id": "run-failed-1",
        "plan_code": "plan-1",
        "biz_date": "2026-06-10",
        "execution_status": status,
        "failed_stage": "recon",
        "failed_reason": "原失败原因",
        "finished_at": "2026-06-10T09:00:00+08:00",
        "run_context_json": {
            "biz_date": "2026-06-10",
            "run_plan_code": "plan-1",
        },
    }


# ════════════════════════════════════════════════════════════════════════════
# Part 1: _resolve_run_biz_date 单测
# ════════════════════════════════════════════════════════════════════════════

def test_resolve_run_biz_date_prefers_run_context() -> None:
    """run_context_json.biz_date 有值时取它。"""
    run = _make_run(
        biz_date_in_run_context="2026-05-31",
        biz_date_in_source_snapshot="2026-05-30",
    )
    result = auto_run_api._resolve_run_biz_date(run)
    assert result == "2026-05-31"


def test_resolve_run_biz_date_falls_back_to_source_snapshot() -> None:
    """run_context_json.biz_date 为空时回退到 source_snapshot_json.biz_date。"""
    run = _make_run(
        biz_date_in_run_context="",
        biz_date_in_source_snapshot="2026-05-30",
    )
    result = auto_run_api._resolve_run_biz_date(run)
    assert result == "2026-05-30"


def test_resolve_run_biz_date_returns_empty_string_when_both_missing() -> None:
    """两容器都没有 biz_date 时返回空字符串。"""
    run = _make_run(
        biz_date_in_run_context="",
        biz_date_in_source_snapshot="",
    )
    result = auto_run_api._resolve_run_biz_date(run)
    assert result == ""


def test_resolve_run_biz_date_handles_none_containers() -> None:
    """run_context_json / source_snapshot_json 为 None 时安全返回 ""。"""
    run = {"id": "run-x", "run_context_json": None, "source_snapshot_json": None}
    result = auto_run_api._resolve_run_biz_date(run)
    assert result == ""


# ════════════════════════════════════════════════════════════════════════════
# Part 2: 端点 POST /runs/{run_id}/diff-digestion
# ════════════════════════════════════════════════════════════════════════════

def _make_enqueue_result(job_id: str = "job-999") -> dict[str, Any]:
    return {"success": True, "job": {"id": job_id}}


def test_digest_run_diffs_api_queues_resolve_job(monkeypatch: pytest.MonkeyPatch) -> None:
    """biz_date < today → 入队 trigger_mode='resolve' + run_context.target_run_id 正确,返回 queued。"""
    run = _make_run(run_id="run-abc", biz_date_in_run_context="2026-06-01")
    enqueue_calls: list[dict[str, Any]] = []

    async def fake_get(auth_token: str, run_id: str) -> dict[str, Any]:
        return {"success": True, "run": run}

    async def fake_find_active(company_id: str, trigger_mode: str, target_run_id: str) -> dict[str, Any]:
        return {"success": True, "found": False}

    async def fake_enqueue(
        company_id: str,
        run_plan_code: str,
        biz_date: str = "",
        trigger_mode: str = "schedule",
        run_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        enqueue_calls.append({
            "company_id": company_id,
            "run_plan_code": run_plan_code,
            "biz_date": biz_date,
            "trigger_mode": trigger_mode,
            "run_context": run_context,
        })
        return _make_enqueue_result("job-777")

    monkeypatch.setattr(auto_run_api, "execution_run_get", fake_get)
    monkeypatch.setattr(auto_run_api, "recon_queue_find_active", fake_find_active)
    monkeypatch.setattr(auto_run_api, "recon_queue_enqueue", fake_enqueue)

    result = asyncio.run(
        auto_run_api.digest_run_diffs_api("run-abc", authorization=_auth_header())
    )

    assert result["queued"] is True
    assert result["status"] == "queued"
    assert result["job_id"] == "job-777"
    assert result["run_id"] == "run-abc"
    assert result["biz_date"] == "2026-06-01"

    assert len(enqueue_calls) == 1
    call = enqueue_calls[0]
    assert call["trigger_mode"] == "resolve"
    assert call["run_plan_code"] == "plan-001"
    assert call["biz_date"] == "2026-06-01"
    assert call["run_context"]["target_run_id"] == "run-abc"


def test_digest_run_diffs_api_queues_same_day_biz_date(monkeypatch: pytest.MonkeyPatch) -> None:
    """biz_date == today 也应入队；当天差异可能已能与已有对侧数据消化。"""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
    run = _make_run(run_id="run-today", biz_date_in_run_context=today)
    enqueue_calls: list[dict[str, Any]] = []

    async def fake_get(auth_token: str, run_id: str) -> dict[str, Any]:
        return {"success": True, "run": run}

    async def fake_find_active(company_id: str, trigger_mode: str, target_run_id: str) -> dict[str, Any]:
        return {"success": True, "found": False}

    async def fake_enqueue(
        company_id: str,
        run_plan_code: str,
        biz_date: str = "",
        trigger_mode: str = "schedule",
        run_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        enqueue_calls.append({
            "company_id": company_id,
            "run_plan_code": run_plan_code,
            "biz_date": biz_date,
            "trigger_mode": trigger_mode,
            "run_context": run_context,
        })
        return _make_enqueue_result("job-today")

    monkeypatch.setattr(auto_run_api, "execution_run_get", fake_get)
    monkeypatch.setattr(auto_run_api, "recon_queue_find_active", fake_find_active)
    monkeypatch.setattr(auto_run_api, "recon_queue_enqueue", fake_enqueue)

    result = asyncio.run(
        auto_run_api.digest_run_diffs_api("run-today", authorization=_auth_header())
    )

    assert result["queued"] is True
    assert result["job_id"] == "job-today"
    assert result["biz_date"] == today
    assert len(enqueue_calls) == 1
    call = enqueue_calls[0]
    assert call["trigger_mode"] == "resolve"
    assert call["biz_date"] == today
    assert call["run_context"]["target_run_id"] == "run-today"


def test_digest_run_diffs_api_rejects_missing_biz_date(monkeypatch: pytest.MonkeyPatch) -> None:
    """run 无 biz_date(两容器都空)→ 400 no_biz_date。"""
    run = _make_run(run_id="run-no-date", biz_date_in_run_context="", biz_date_in_source_snapshot="")
    enqueue_calls: list[Any] = []

    async def fake_get(auth_token: str, run_id: str) -> dict[str, Any]:
        return {"success": True, "run": run}

    async def fake_enqueue(*args: Any, **kwargs: Any) -> dict[str, Any]:
        enqueue_calls.append(kwargs)
        return _make_enqueue_result()

    monkeypatch.setattr(auto_run_api, "execution_run_get", fake_get)
    monkeypatch.setattr(auto_run_api, "recon_queue_enqueue", fake_enqueue)

    with pytest.raises(auto_run_api.HTTPException) as exc:
        asyncio.run(
            auto_run_api.digest_run_diffs_api("run-no-date", authorization=_auth_header())
        )

    assert exc.value.status_code == 400
    detail = exc.value.detail
    assert isinstance(detail, dict)
    assert detail["status"] == "no_biz_date"
    assert "业务日期" in detail["message"] or "biz_date" in detail["message"]
    assert len(enqueue_calls) == 0, "无业务日期不应入队"


def test_digest_run_diffs_api_rejects_already_running_resolve_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """已有 active resolve job → 409,未重复入队。"""
    run = _make_run(run_id="run-abc", biz_date_in_run_context="2026-06-01")
    enqueue_calls: list[Any] = []

    async def fake_get(auth_token: str, run_id: str) -> dict[str, Any]:
        return {"success": True, "run": run}

    async def fake_find_active(company_id: str, trigger_mode: str, target_run_id: str) -> dict[str, Any]:
        return {"success": True, "found": True, "job": {"id": "job-already", "status": "queued"}}

    async def fake_enqueue(*args: Any, **kwargs: Any) -> dict[str, Any]:
        enqueue_calls.append(kwargs)
        return _make_enqueue_result()

    monkeypatch.setattr(auto_run_api, "execution_run_get", fake_get)
    monkeypatch.setattr(auto_run_api, "recon_queue_find_active", fake_find_active)
    monkeypatch.setattr(auto_run_api, "recon_queue_enqueue", fake_enqueue)

    with pytest.raises(auto_run_api.HTTPException) as exc:
        asyncio.run(
            auto_run_api.digest_run_diffs_api("run-abc", authorization=_auth_header())
        )

    assert exc.value.status_code == 409
    detail = exc.value.detail
    assert isinstance(detail, dict)
    assert detail["status"] == "already_running"
    assert "差异消化" in detail["message"]
    assert len(enqueue_calls) == 0, "已有 active job 不应再次入队"


def test_digest_run_diffs_api_returns_404_for_missing_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run 不存在 → 404。"""
    async def fake_get(auth_token: str, run_id: str) -> dict[str, Any]:
        return {"success": False, "error": "运行记录不存在"}

    monkeypatch.setattr(auto_run_api, "execution_run_get", fake_get)

    with pytest.raises(auto_run_api.HTTPException) as exc:
        asyncio.run(
            auto_run_api.digest_run_diffs_api("run-missing", authorization=_auth_header())
        )

    assert exc.value.status_code == 404


def test_rerun_execution_run_rejects_active_duplicate(client, monkeypatch):
    async def fake_prepare_execution_run_rerun(**kwargs):
        return {
            "success": True,
            "run_plan_code": "plan-1",
            "biz_date": "2026-06-10",
            "source_run": _make_execution_run_for_rerun(),
            "run_context": {
                "target_run_id": "run-failed-1",
                "execution_run_id": "run-failed-1",
                "retry_from_failed_run_id": "run-failed-1",
                "retry_reason": "用户触发重试",
                "trigger_type": "rerun",
            },
        }

    async def fake_recon_queue_find_active(**kwargs):
        return {"success": True, "job": {"id": "job-1", "status": "queued"}}

    async def fake_recon_queue_enqueue(**kwargs):
        raise AssertionError("duplicate active retry must not enqueue")

    monkeypatch.setattr(auto_run_api, "prepare_execution_run_rerun", fake_prepare_execution_run_rerun)
    monkeypatch.setattr(auto_run_api, "recon_queue_find_active", fake_recon_queue_find_active)
    monkeypatch.setattr(auto_run_api, "recon_queue_enqueue", fake_recon_queue_enqueue)

    response = client.post(
        "/api/recon/runs/rerun",
        headers={"Authorization": _auth_header()},
        json={"original_run_id": "run-failed-1", "reason": "用户触发重试"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["message"] == "该运行记录正在重试,请稍后"


def test_rerun_execution_run_fails_closed_when_active_lookup_fails(client, monkeypatch):
    enqueue_calls = []
    update_calls = []

    async def fake_prepare_execution_run_rerun(**kwargs):
        return {
            "success": True,
            "run_plan_code": "plan-1",
            "biz_date": "2026-06-10",
            "source_run": _make_execution_run_for_rerun(),
            "run_context": {
                "target_run_id": "run-failed-1",
                "execution_run_id": "run-failed-1",
                "retry_from_failed_run_id": "run-failed-1",
                "retry_reason": "用户触发重试",
                "trigger_type": "rerun",
            },
        }

    async def fake_recon_queue_find_active(**kwargs):
        return {"success": False, "error": "queue lookup failed"}

    async def fake_recon_queue_enqueue(**kwargs):
        enqueue_calls.append(kwargs)
        return {"success": True, "job": {"id": "job-1"}}

    async def fake_execution_run_update(auth_token, run_id, payload):
        update_calls.append(payload)
        return {"success": True, "run": {"id": run_id}}

    monkeypatch.setattr(auto_run_api, "prepare_execution_run_rerun", fake_prepare_execution_run_rerun)
    monkeypatch.setattr(auto_run_api, "recon_queue_find_active", fake_recon_queue_find_active)
    monkeypatch.setattr(auto_run_api, "recon_queue_enqueue", fake_recon_queue_enqueue)
    monkeypatch.setattr(auto_run_api, "execution_run_update", fake_execution_run_update)

    response = client.post(
        "/api/recon/runs/rerun",
        headers={"Authorization": _auth_header()},
        json={"original_run_id": "run-failed-1", "reason": "用户触发重试"},
    )

    assert response.status_code == 500
    assert "queue lookup failed" in str(response.json()["detail"])
    assert enqueue_calls == []
    assert update_calls == []


def test_rerun_execution_run_update_failure_does_not_enqueue(client, monkeypatch):
    enqueue_calls = []

    async def fake_prepare_execution_run_rerun(**kwargs):
        return {
            "success": True,
            "run_plan_code": "plan-1",
            "biz_date": "2026-06-10",
            "source_run": _make_execution_run_for_rerun(),
            "run_context": {
                "target_run_id": "run-failed-1",
                "execution_run_id": "run-failed-1",
                "retry_from_failed_run_id": "run-failed-1",
                "retry_reason": "用户触发重试",
                "trigger_type": "rerun",
            },
        }

    async def fake_recon_queue_find_active(**kwargs):
        return {"success": True, "job": None}

    async def fake_execution_run_update(auth_token, run_id, payload):
        return {"success": False, "error": "update failed"}

    async def fake_recon_queue_enqueue(**kwargs):
        enqueue_calls.append(kwargs)
        return {"success": True, "job": {"id": "job-1"}}

    monkeypatch.setattr(auto_run_api, "prepare_execution_run_rerun", fake_prepare_execution_run_rerun)
    monkeypatch.setattr(auto_run_api, "recon_queue_find_active", fake_recon_queue_find_active)
    monkeypatch.setattr(auto_run_api, "execution_run_update", fake_execution_run_update)
    monkeypatch.setattr(auto_run_api, "recon_queue_enqueue", fake_recon_queue_enqueue)

    response = client.post(
        "/api/recon/runs/rerun",
        headers={"Authorization": _auth_header()},
        json={"original_run_id": "run-failed-1", "reason": "用户触发重试"},
    )

    assert response.status_code == 500
    assert "update failed" in str(response.json()["detail"])
    assert enqueue_calls == []


def test_rerun_execution_run_marks_original_run_running(client, monkeypatch):
    captured_enqueue = {}
    captured_update = {}
    call_order = []

    async def fake_prepare_execution_run_rerun(**kwargs):
        return {
            "success": True,
            "run_plan_code": "plan-1",
            "biz_date": "2026-06-10",
            "source_run": _make_execution_run_for_rerun(),
            "run_context": {
                "target_run_id": "run-failed-1",
                "execution_run_id": "run-failed-1",
                "retry_from_failed_run_id": "run-failed-1",
                "retry_reason": "用户触发重试",
                "trigger_type": "rerun",
            },
        }

    async def fake_recon_queue_find_active(**kwargs):
        return {"success": True, "job": None}

    async def fake_recon_queue_enqueue(**kwargs):
        call_order.append("enqueue")
        captured_enqueue.update(kwargs)
        return {"success": True, "job": {"id": "job-1", "status": "queued"}}

    async def fake_execution_run_update(auth_token, run_id, payload):
        call_order.append("update")
        captured_update.update({"auth_token": auth_token, "run_id": run_id, "payload": payload})
        return {"success": True, "run": {"id": run_id, "execution_status": "running"}}

    monkeypatch.setattr(auto_run_api, "prepare_execution_run_rerun", fake_prepare_execution_run_rerun)
    monkeypatch.setattr(auto_run_api, "recon_queue_find_active", fake_recon_queue_find_active)
    monkeypatch.setattr(auto_run_api, "recon_queue_enqueue", fake_recon_queue_enqueue)
    monkeypatch.setattr(auto_run_api, "execution_run_update", fake_execution_run_update)

    response = client.post(
        "/api/recon/runs/rerun",
        headers={"Authorization": _auth_header()},
        json={"original_run_id": "run-failed-1", "reason": "用户触发重试"},
    )

    assert response.status_code == 200
    assert response.json()["queued"] is True
    assert call_order == ["update", "enqueue"]
    assert captured_enqueue["trigger_mode"] == "rerun"
    assert captured_enqueue["run_context"]["target_run_id"] == "run-failed-1"
    assert captured_enqueue["run_context"]["execution_run_id"] == "run-failed-1"
    assert captured_update["run_id"] == "run-failed-1"
    assert captured_update["payload"]["execution_status"] == "running"
    assert captured_update["payload"]["failed_stage"] == ""
    assert captured_update["payload"]["failed_reason"] == ""
    assert captured_update["payload"]["restart_started_at_now"] is True
    assert captured_update["payload"]["reset_finished_at"] is True
    assert captured_update["payload"]["run_context_json"]["retry_history"][-1]["previous_status"] == "failed"


def test_rerun_execution_run_enqueue_failure_restores_failed_state(client, monkeypatch):
    update_calls = []

    async def fake_prepare_execution_run_rerun(**kwargs):
        source = _make_execution_run_for_rerun()
        source["failed_stage"] = "recon"
        source["failed_reason"] = "原失败原因"
        return {
            "success": True,
            "run_plan_code": "plan-1",
            "biz_date": "2026-06-10",
            "source_run": source,
            "run_context": {
                "target_run_id": "run-failed-1",
                "execution_run_id": "run-failed-1",
                "retry_from_failed_run_id": "run-failed-1",
                "retry_reason": "用户触发重试",
                "trigger_type": "rerun",
            },
        }

    async def fake_recon_queue_find_active(**kwargs):
        return {"success": True, "job": None}

    async def fake_execution_run_update(auth_token, run_id, payload):
        update_calls.append(payload)
        return {
            "success": True,
            "run": {"id": run_id, "execution_status": payload["execution_status"]},
        }

    async def fake_recon_queue_enqueue(**kwargs):
        return {"success": False, "error": "enqueue failed"}

    monkeypatch.setattr(auto_run_api, "prepare_execution_run_rerun", fake_prepare_execution_run_rerun)
    monkeypatch.setattr(auto_run_api, "recon_queue_find_active", fake_recon_queue_find_active)
    monkeypatch.setattr(auto_run_api, "execution_run_update", fake_execution_run_update)
    monkeypatch.setattr(auto_run_api, "recon_queue_enqueue", fake_recon_queue_enqueue)

    response = client.post(
        "/api/recon/runs/rerun",
        headers={"Authorization": _auth_header()},
        json={"original_run_id": "run-failed-1", "reason": "用户触发重试"},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == {"message": "enqueue failed", "restore_error": ""}
    assert len(update_calls) == 2
    assert update_calls[0]["execution_status"] == "running"
    assert update_calls[1]["execution_status"] == "failed"
    assert update_calls[1]["failed_stage"] == "recon"
    assert update_calls[1]["failed_reason"] == "原失败原因"
    assert update_calls[1]["finished_at_now"] is True
    assert update_calls[1]["run_context_json"]["retry_history"][-1]["previous_status"] == "failed"


def test_rerun_execution_run_enqueue_failure_restore_uses_fallback_reason(
    client,
    monkeypatch,
):
    update_calls = []

    async def fake_prepare_execution_run_rerun(**kwargs):
        source = _make_execution_run_for_rerun()
        source["failed_stage"] = ""
        source["failed_reason"] = ""
        return {
            "success": True,
            "run_plan_code": "plan-1",
            "biz_date": "2026-06-10",
            "source_run": source,
            "run_context": {
                "target_run_id": "run-failed-1",
                "execution_run_id": "run-failed-1",
                "retry_from_failed_run_id": "run-failed-1",
                "retry_reason": "用户触发重试",
                "trigger_type": "rerun",
            },
        }

    async def fake_recon_queue_find_active(**kwargs):
        return {"success": True, "job": None}

    async def fake_execution_run_update(auth_token, run_id, payload):
        update_calls.append(payload)
        return {"success": True, "run": {"id": run_id}}

    async def fake_recon_queue_enqueue(**kwargs):
        return {"success": False, "error": "enqueue failed"}

    monkeypatch.setattr(auto_run_api, "prepare_execution_run_rerun", fake_prepare_execution_run_rerun)
    monkeypatch.setattr(auto_run_api, "recon_queue_find_active", fake_recon_queue_find_active)
    monkeypatch.setattr(auto_run_api, "execution_run_update", fake_execution_run_update)
    monkeypatch.setattr(auto_run_api, "recon_queue_enqueue", fake_recon_queue_enqueue)

    response = client.post(
        "/api/recon/runs/rerun",
        headers={"Authorization": _auth_header()},
        json={"original_run_id": "run-failed-1", "reason": "用户触发重试"},
    )

    assert response.status_code == 500
    assert len(update_calls) == 2
    assert update_calls[1]["failed_stage"] == "rerun_enqueue"
    assert update_calls[1]["failed_reason"] == "enqueue failed"
