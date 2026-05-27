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
