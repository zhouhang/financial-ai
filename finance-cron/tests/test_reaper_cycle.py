from __future__ import annotations

import sys
from pathlib import Path

import pytest

CRON_ROOT = Path(__file__).resolve().parents[1]
if str(CRON_ROOT) not in sys.path:
    sys.path.insert(0, str(CRON_ROOT))

import scheduler_service
from scheduler_service import FinanceCronSchedulerService, load_cron_config


@pytest.mark.asyncio
async def test_run_reaper_cycle_calls_tools_in_order(monkeypatch) -> None:
    calls: list[str] = []

    async def _reap(token, *, stale_after_seconds=180):
        calls.append("reap_stale_agents")
        return {"success": True, "failed_count": 0}

    async def _fail_failed(token):
        calls.append("fail_failed")
        return {"success": True}

    async def _requeue(token):
        calls.append("requeue_ready")
        return {"success": True}

    async def _fail_expired(token):
        calls.append("fail_expired")
        return {"success": True}

    monkeypatch.setattr(scheduler_service, "browser_sync_job_reap_stale_agents", _reap)
    monkeypatch.setattr(scheduler_service, "recon_queue_fail_failed_collection_waiting", _fail_failed)
    monkeypatch.setattr(scheduler_service, "recon_queue_requeue_ready_waiting", _requeue)
    monkeypatch.setattr(scheduler_service, "recon_queue_fail_expired_waiting", _fail_expired)

    service = FinanceCronSchedulerService(load_cron_config(None))
    await service.run_reaper_cycle()

    assert calls == ["reap_stale_agents", "fail_failed", "requeue_ready", "fail_expired"]
