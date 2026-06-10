from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

recon_worker = importlib.import_module("recon_worker")


@pytest.mark.anyio
async def test_process_job_fails_queue_when_waiting_data_update_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, object]] = []

    async def fake_execute_run_plan_run(**_: object) -> dict[str, object]:
        return {
            "status": "data_waiting",
            "error": "浏览器采集任务已创建，等待采集完成后继续对账",
            "run": {"id": "run-001"},
            "waiting_datasets": [{"dataset_id": "dataset-001"}],
            "collection_job_ids": ["sync-001"],
        }

    async def fake_waiting_data(_token: str, _job_id: str, payload: dict[str, object]) -> dict[str, object]:
        calls.append(("execution_run_id", payload.get("execution_run_id", "")))
        return {"success": False, "error": "column updated_at does not exist"}

    async def fake_fail(_system_token: str, job_id: str, error: str = "") -> dict[str, object]:
        calls.append((job_id, error))
        return {"success": True}

    monkeypatch.setattr(recon_worker, "execute_run_plan_run", fake_execute_run_plan_run)
    monkeypatch.setattr(recon_worker, "recon_queue_waiting_data", fake_waiting_data)
    monkeypatch.setattr(recon_worker, "recon_queue_fail", fake_fail)

    await recon_worker._process_job(
        {
            "id": "queue-001",
            "company_id": "company-001",
            "run_plan_code": "plan-001",
            "trigger_mode": "schedule",
            "run_context": {},
        },
        "system-token",
    )

    assert calls == [
        ("execution_run_id", "run-001"),
        ("queue-001", "waiting_data 更新失败: column updated_at does not exist"),
    ]


@pytest.mark.anyio
async def test_process_job_triggers_digest_finalizer_only_after_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, object]] = []

    async def fake_execute_run_plan_run(**_: object) -> dict[str, object]:
        return {
            "success": True,
            "biz_date": "2026-06-05",
            "run": {
                "id": "run-001",
                "execution_status": "success",
                "artifacts_json": {},
            },
        }

    async def fake_complete(_token: str, job_id: str) -> dict[str, object]:
        calls.append(("complete", job_id))
        return {"success": True, "job": {"finished_at": "2026-06-06T09:00:00+08:00"}}

    async def fake_update(_token: str, run_id: str, payload: dict[str, object]) -> dict[str, object]:
        calls.append(("update", run_id, payload))
        return {"success": True}

    async def fake_finalize(**kwargs: object) -> dict[str, object]:
        calls.append(("finalize", kwargs))
        return {"success": True, "ready_count": 1, "delivered_count": 1, "blocked_count": 0}

    monkeypatch.setattr(recon_worker, "execute_run_plan_run", fake_execute_run_plan_run)
    monkeypatch.setattr(recon_worker, "recon_queue_complete", fake_complete)
    monkeypatch.setattr(recon_worker, "execution_run_update", fake_update)
    monkeypatch.setattr(recon_worker, "finalize_and_deliver_daily_digest", fake_finalize)

    await recon_worker._process_job(
        {
            "id": "queue-001",
            "company_id": "company-001",
            "run_plan_code": "plan-001",
            "trigger_mode": "schedule",
            "run_context": {},
        },
        "system-token",
    )

    assert calls[0] == ("complete", "queue-001")
    assert calls[-1][0] == "finalize"
    finalize_kwargs = calls[-1][1]
    assert isinstance(finalize_kwargs, dict)
    assert finalize_kwargs["company_id"] == "company-001"
    assert finalize_kwargs["biz_date"] == "2026-06-05"
    assert isinstance(finalize_kwargs["auth_token"], str) and finalize_kwargs["auth_token"]
