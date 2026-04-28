from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx

_TIMEOUT = httpx.Timeout(120.0, connect=10.0)
_RETRYABLE_STATUS_CODES = {502, 503, 504}


def _data_agent_base_url() -> str:
    # 使用 127.0.0.1 避免本机代理/安全软件拦截 localhost 导致的 502。
    return os.getenv("DATA_AGENT_BASE_URL", "http://127.0.0.1:8100").rstrip("/")


def _get_local_request_retry_count() -> int:
    raw = str(os.getenv("FINANCE_CRON_LOCAL_REQUEST_MAX_RETRIES", "3")).strip()
    try:
        return max(int(raw), 1)
    except ValueError:
        return 3


def _get_local_request_retry_delay_seconds() -> float:
    raw = str(os.getenv("FINANCE_CRON_LOCAL_REQUEST_RETRY_DELAY_SECONDS", "1")).strip()
    try:
        return max(float(raw), 0.0)
    except ValueError:
        return 1.0


async def trigger_run_plan(
    auth_token: str,
    *,
    run_plan_code: str,
    biz_date: str = "",
    trigger_mode: str = "schedule",
    run_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "biz_date": biz_date,
        "trigger_mode": trigger_mode,
        "run_context": dict(run_context or {}),
    }
    response: httpx.Response | None = None
    retry_count = _get_local_request_retry_count()
    retry_delay_seconds = _get_local_request_retry_delay_seconds()
    request_url = f"{_data_agent_base_url()}/recon/run-plans/{run_plan_code}/run"

    async with httpx.AsyncClient(timeout=_TIMEOUT, trust_env=False) as client:
        for attempt in range(1, retry_count + 1):
            try:
                response = await client.post(
                    request_url,
                    headers=headers,
                    json=payload,
                )
            except httpx.HTTPError as exc:
                if attempt >= retry_count:
                    return {"success": False, "error": str(exc)}
                if retry_delay_seconds > 0:
                    await asyncio.sleep(retry_delay_seconds)
                continue

            if response.status_code not in _RETRYABLE_STATUS_CODES:
                break
            if attempt >= retry_count:
                break
            if retry_delay_seconds > 0:
                await asyncio.sleep(retry_delay_seconds)

    if response is None:
        return {"success": False, "error": "data-agent 本地调用失败，未获得响应"}
    try:
        body = response.json()
    except Exception:
        body = {"success": False, "error": response.text}
    if response.status_code >= 400:
        detail = body.get("detail") if isinstance(body, dict) else None
        return {"success": False, "error": str(detail or body or response.text)}
    if isinstance(body, dict):
        if "success" not in body and bool(body.get("queued")):
            return {**body, "success": True}
        return body
    return {"success": True, "result": body}
