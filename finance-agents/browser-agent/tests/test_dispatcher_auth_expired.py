"""Unit tests for AUTH_EXPIRED auto-handoff notification in BrowserDispatcherLoop.

Verifies:
- AUTH_EXPIRED runner result triggers exactly one report_risk_waiting call.
- A second AUTH_EXPIRED job for the same shop on the same day is deduped.
- RISK_VERIFICATION path is unaffected (no extra notification beyond the existing
  on_risk_waiting callback mechanism tested elsewhere).
"""
from __future__ import annotations

import asyncio
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from finance_browser_agent import dispatcher_loop as dl_module
from finance_browser_agent.dispatcher_loop import BrowserDispatcherLoop


def _make_job(
    *,
    job_id: str = "job-1",
    shop_id: str = "shop-42",
    company_id: str = "company-99",
) -> dict[str, Any]:
    return {
        "id": job_id,
        "shop_id": shop_id,
        "company_id": company_id,
        "data_source_id": "ds-1",
        "playbook_id": "pb-1",
        "playbook_body": {},
        "playbook_version": "1",
        "runtime_profile_ref": "",
        "egress_group": "",
        "credential_ref": "",
        "request_payload": {"params": {}},
    }


def _make_loop(runner_result: dict[str, Any]) -> tuple[BrowserDispatcherLoop, AsyncMock, list[dict]]:
    """Return (loop, mock_client, recorded_risk_waiting_calls)."""
    risk_calls: list[dict] = []

    async def fake_report_risk_waiting(
        *, sync_job_id: str, reason: str, company_id: str = "",
        shop_id: str = "", data_source_id: str = "",
    ) -> dict:
        risk_calls.append({
            "sync_job_id": sync_job_id,
            "reason": reason,
            "company_id": company_id,
            "shop_id": shop_id,
        })
        return {"success": True}

    client = AsyncMock()
    client.claim_browser_job = AsyncMock(return_value={"job": _make_job()})
    client.mark_browser_job_failed = AsyncMock(return_value={"success": True})
    client.mark_browser_job_success = AsyncMock(return_value={"success": True})
    client.report_risk_waiting = fake_report_risk_waiting
    client.handoff_coordinator = None
    client.handoff_backend_factory = None

    def sync_runner(message: dict[str, Any]) -> dict[str, Any]:
        return runner_result

    loop = BrowserDispatcherLoop(client=client, runner=sync_runner, max_concurrency=1)
    return loop, client, risk_calls


@pytest.fixture(autouse=True)
def reset_notified_dict():
    """Isolate _AUTH_EXPIRED_NOTIFIED between tests."""
    dl_module._AUTH_EXPIRED_NOTIFIED.clear()
    yield
    dl_module._AUTH_EXPIRED_NOTIFIED.clear()


# ---------------------------------------------------------------------------
# Test 1: AUTH_EXPIRED triggers exactly one notification
# ---------------------------------------------------------------------------

async def test_auth_expired_triggers_notification():
    result = {
        "status": "failed",
        "fail_reason": "AUTH_EXPIRED",
        "error_info": {"message": "login.taobao.com redirect"},
    }
    loop, client, risk_calls = _make_loop(result)

    outcome = await loop.run_once()

    assert outcome["status"] == "failed"
    assert len(risk_calls) == 1
    assert risk_calls[0]["reason"] == "AUTH_EXPIRED"
    assert risk_calls[0]["shop_id"] == "shop-42"
    assert risk_calls[0]["company_id"] == "company-99"
    client.mark_browser_job_failed.assert_called_once()


async def test_auth_expired_not_renotified_after_live_handoff_callback():
    risk_calls: list[dict] = []

    async def fake_report_risk_waiting(
        *, sync_job_id: str, reason: str, company_id: str = "",
        shop_id: str = "", data_source_id: str = "",
    ) -> dict:
        risk_calls.append({
            "sync_job_id": sync_job_id,
            "reason": reason,
            "company_id": company_id,
            "shop_id": shop_id,
        })
        return {"success": True}

    client = AsyncMock()
    client.claim_browser_job = AsyncMock(return_value={"job": _make_job()})
    client.mark_browser_job_failed = AsyncMock(return_value={"success": True})
    client.mark_browser_job_success = AsyncMock(return_value={"success": True})
    client.report_risk_waiting = fake_report_risk_waiting
    client.handoff_coordinator = None
    client.handoff_backend_factory = None

    def runner(message: dict[str, Any]) -> dict[str, Any]:
        message["on_risk_waiting"]("AUTH_EXPIRED")
        return {
            "status": "failed",
            "fail_reason": "AUTH_EXPIRED",
            "error_info": {"message": "manual handoff timed out"},
        }

    loop = BrowserDispatcherLoop(client=client, runner=runner, max_concurrency=1)

    outcome = await loop.run_once()

    assert outcome["status"] == "failed"
    assert len(risk_calls) == 1
    assert risk_calls[0]["reason"] == "AUTH_EXPIRED"
    client.mark_browser_job_failed.assert_called_once()


async def test_dispatcher_passes_event_loop_to_runner_message():
    seen_loop: asyncio.AbstractEventLoop | None = None

    client = AsyncMock()
    client.claim_browser_job = AsyncMock(return_value={"job": _make_job()})
    client.mark_browser_job_success = AsyncMock(return_value={"success": True})
    client.handoff_coordinator = None
    client.handoff_backend_factory = None

    def runner(message: dict[str, Any]) -> dict[str, Any]:
        nonlocal seen_loop
        seen_loop = message.get("handoff_event_loop")
        return {"status": "success", "records": [], "capture_files": []}

    loop = BrowserDispatcherLoop(client=client, runner=runner, max_concurrency=1)

    outcome = await loop.run_once()

    assert outcome["status"] == "success"
    assert seen_loop is asyncio.get_running_loop()


# ---------------------------------------------------------------------------
# Test 2: Second AUTH_EXPIRED for same shop same day → deduped (no second call)
# ---------------------------------------------------------------------------

async def test_auth_expired_deduped_same_shop_same_day():
    result = {
        "status": "failed",
        "fail_reason": "AUTH_EXPIRED",
        "error_info": {"message": "login redirect"},
    }
    loop, client, risk_calls = _make_loop(result)

    # Pre-mark today's notification for this shop as already sent
    dl_module._AUTH_EXPIRED_NOTIFIED["shop-42"] = date.today()

    outcome = await loop.run_once()

    assert outcome["status"] == "failed"
    # No new notification because deduped
    assert len(risk_calls) == 0
    client.mark_browser_job_failed.assert_called_once()


# ---------------------------------------------------------------------------
# Test 3: RISK_VERIFICATION does NOT trigger the AUTH_EXPIRED notification path
# ---------------------------------------------------------------------------

async def test_risk_verification_does_not_trigger_auth_expired_notification():
    result = {
        "status": "failed",
        "fail_reason": "RISK_VERIFICATION",
        "error_info": {"message": "captcha required"},
    }
    loop, client, risk_calls = _make_loop(result)

    outcome = await loop.run_once()

    assert outcome["status"] == "failed"
    # report_risk_waiting is called by _on_risk_waiting callback from within the
    # runner (sync thread), not by our new AUTH_EXPIRED path.
    # Our new path must NOT have injected any risk_calls for RISK_VERIFICATION.
    assert len(risk_calls) == 0


# ---------------------------------------------------------------------------
# Test 4: Different shops on the same day each get their own notification
# ---------------------------------------------------------------------------

async def test_auth_expired_different_shops_each_notified():
    """Two distinct shops both fail with AUTH_EXPIRED → two notifications sent."""
    risk_calls: list[dict] = []

    async def fake_report_risk_waiting(
        *, sync_job_id: str, reason: str, company_id: str = "",
        shop_id: str = "", data_source_id: str = "",
    ) -> dict:
        risk_calls.append({"sync_job_id": sync_job_id, "shop_id": shop_id})
        return {"success": True}

    result = {
        "status": "failed",
        "fail_reason": "AUTH_EXPIRED",
        "error_info": {"message": "redirect"},
    }

    jobs = [_make_job(job_id="j1", shop_id="shop-A"), _make_job(job_id="j2", shop_id="shop-B")]
    job_iter = iter(jobs)

    client = AsyncMock()
    client.claim_browser_job = AsyncMock(side_effect=[{"job": j} for j in jobs])
    client.mark_browser_job_failed = AsyncMock(return_value={"success": True})
    client.report_risk_waiting = fake_report_risk_waiting
    client.handoff_coordinator = None
    client.handoff_backend_factory = None

    loop = BrowserDispatcherLoop(
        client=client,
        runner=lambda msg: result,
        max_concurrency=1,
    )

    await loop.run_once()  # shop-A
    await loop.run_once()  # shop-B

    notified_shops = {c["shop_id"] for c in risk_calls}
    assert "shop-A" in notified_shops
    assert "shop-B" in notified_shops
    assert len(risk_calls) == 2
