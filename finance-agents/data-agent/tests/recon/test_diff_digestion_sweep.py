"""sweep_diff_digestion:回填消化编排——列出窗口内待重判 run,去重后逐个入队 resolve。"""
from typing import Any

import pytest

from graphs.recon import auto_run_service


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_enqueues_resolve_for_each_pending_run(monkeypatch: pytest.MonkeyPatch) -> None:
    enqueued: list[dict[str, Any]] = []

    async def fake_list(*, company_id: str, since_date: str) -> dict[str, Any]:
        assert company_id == "co-1"
        assert since_date == "2026-06-09"
        return {
            "success": True,
            "runs": [
                {"run_id": "run-A", "plan_code": "plan-A", "biz_date": "2026-06-20"},
                {"run_id": "run-B", "plan_code": "plan-B", "biz_date": "2026-06-21"},
            ],
        }

    async def fake_find_active(*, company_id: str, trigger_mode: str, target_run_id: str) -> dict[str, Any]:
        return {"success": True, "found": False}

    async def fake_enqueue(*, company_id: str, run_plan_code: str, biz_date: str,
                           trigger_mode: str, run_context: dict[str, Any]) -> dict[str, Any]:
        enqueued.append({
            "run_plan_code": run_plan_code,
            "trigger_mode": trigger_mode,
            "target_run_id": run_context.get("target_run_id"),
            "biz_date": biz_date,
        })
        return {"success": True, "job": {"id": "job-x"}}

    monkeypatch.setattr(auto_run_service, "recon_runs_pending_redigestion", fake_list)
    monkeypatch.setattr(auto_run_service, "recon_queue_find_active", fake_find_active)
    monkeypatch.setattr(auto_run_service, "recon_queue_enqueue", fake_enqueue)

    result = await auto_run_service.sweep_diff_digestion(company_id="co-1", since_date="2026-06-09")

    assert result["success"] is True
    assert result["scanned"] == 2
    assert result["enqueued"] == 2
    assert result["skipped"] == 0
    assert len(enqueued) == 2
    assert all(e["trigger_mode"] == "resolve" for e in enqueued)
    assert {e["target_run_id"] for e in enqueued} == {"run-A", "run-B"}
    assert enqueued[0]["run_plan_code"] == "plan-A"
    assert enqueued[0]["biz_date"] == "2026-06-20"


@pytest.mark.anyio
async def test_skips_run_with_active_resolve_job(monkeypatch: pytest.MonkeyPatch) -> None:
    enqueued: list[Any] = []

    async def fake_list(*, company_id: str, since_date: str) -> dict[str, Any]:
        return {"success": True, "runs": [{"run_id": "run-A", "plan_code": "plan-A", "biz_date": "2026-06-20"}]}

    async def fake_find_active(*, company_id: str, trigger_mode: str, target_run_id: str) -> dict[str, Any]:
        return {"success": True, "found": True, "job": {"id": "already"}}

    async def fake_enqueue(**kwargs: Any) -> dict[str, Any]:
        enqueued.append(kwargs)
        return {"success": True}

    monkeypatch.setattr(auto_run_service, "recon_runs_pending_redigestion", fake_list)
    monkeypatch.setattr(auto_run_service, "recon_queue_find_active", fake_find_active)
    monkeypatch.setattr(auto_run_service, "recon_queue_enqueue", fake_enqueue)

    result = await auto_run_service.sweep_diff_digestion(company_id="co-1", since_date="2026-06-09")

    assert result["enqueued"] == 0
    assert result["skipped"] == 1
    assert enqueued == [], "已有在途 resolve job 的 run 不应重复入队"


@pytest.mark.anyio
async def test_listing_failure_returns_error_without_enqueue(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_list(*, company_id: str, since_date: str) -> dict[str, Any]:
        return {"success": False, "error": "boom"}

    async def fake_enqueue(**kwargs: Any) -> dict[str, Any]:
        raise AssertionError("列出失败不应入队")

    monkeypatch.setattr(auto_run_service, "recon_runs_pending_redigestion", fake_list)
    monkeypatch.setattr(auto_run_service, "recon_queue_enqueue", fake_enqueue)

    result = await auto_run_service.sweep_diff_digestion(company_id="co-1", since_date="2026-06-09")

    assert result["success"] is False
    assert result["enqueued"] == 0
