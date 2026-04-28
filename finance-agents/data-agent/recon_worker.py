"""对账执行队列 Worker。

启动方式：python recon_worker.py
并行启动多个进程（由 START_ALL_SERVICES.sh 控制数量），每个进程独立轮询队列。
SKIP LOCKED 保证多个 worker 不会重复处理同一条 job。
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import uuid
from datetime import datetime, timedelta, timezone

import jwt

from graphs.recon.auto_run_service import execute_run_plan_run
from tools.mcp_client import (
    recon_queue_complete,
    recon_queue_dequeue,
    recon_queue_fail,
    recon_queue_reclaim_stale,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [recon-worker] %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

POLL_INTERVAL = float(os.getenv("RECON_WORKER_POLL_INTERVAL", "2.0"))
STALE_TIMEOUT_MINUTES = int(os.getenv("RECON_WORKER_STALE_TIMEOUT", "15"))
JWT_SECRET = os.getenv("JWT_SECRET", "tally-secret-change-in-production")

_shutdown = False


def _handle_signal(sig, frame):  # noqa: ANN001
    global _shutdown
    logger.info("[recon-worker] 收到停止信号，等待当前任务完成后退出...")
    _shutdown = True


def _create_worker_token(company_id: str) -> str:
    """生成公司级系统令牌，供 execute_run_plan_run 使用。"""
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": f"recon-worker:{company_id}",
            "username": "recon-worker",
            "role": "system",
            "company_id": company_id,
            "department_id": None,
            "iat": now,
            "exp": now + timedelta(hours=2),
            "jti": str(uuid.uuid4()),
        },
        JWT_SECRET,
        algorithm="HS256",
    )


def _create_system_token() -> str:
    """生成无公司绑定的系统令牌，供 dequeue/complete/fail MCP 工具使用。"""
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": "recon-worker:system",
            "username": "recon-worker",
            "role": "system",
            "company_id": None,
            "department_id": None,
            "iat": now,
            "exp": now + timedelta(hours=2),
            "jti": str(uuid.uuid4()),
        },
        JWT_SECRET,
        algorithm="HS256",
    )


async def _process_job(job: dict, system_token: str) -> None:
    job_id = str(job["id"])
    company_id = str(job["company_id"])
    run_plan_code = str(job["run_plan_code"])
    logger.info("[recon-worker] 开始处理 job_id=%s run_plan_code=%s", job_id, run_plan_code)
    try:
        auth_token = _create_worker_token(company_id)
        await execute_run_plan_run(
            auth_token=auth_token,
            run_plan_code=run_plan_code,
            biz_date=str(job.get("biz_date") or ""),
            trigger_mode=str(job.get("trigger_mode") or "schedule"),
            run_context=dict(job.get("run_context") or {}),
        )
        await recon_queue_complete(system_token, job_id)
        logger.info("[recon-worker] job_id=%s 完成", job_id)
    except Exception as exc:
        logger.error("[recon-worker] job_id=%s 失败: %s", job_id, exc, exc_info=True)
        await recon_queue_fail(system_token, job_id, str(exc)[:2000])


async def main() -> None:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    system_token = _create_system_token()

    # 启动时把上次进程崩溃遗留的 running 任务重置回 queued
    try:
        result = await recon_queue_reclaim_stale(system_token, timeout_minutes=STALE_TIMEOUT_MINUTES)
        reclaimed = (result or {}).get("reclaimed", 0)
        if reclaimed:
            logger.info("[recon-worker] 重置了 %d 个卡死的 running 任务", reclaimed)
    except Exception as exc:
        logger.warning("[recon-worker] reclaim_stale 失败（非致命）: %s", exc)

    logger.info("[recon-worker] 启动，轮询间隔 %.1fs", POLL_INTERVAL)

    while not _shutdown:
        # 每 2 小时刷新一次系统令牌，避免过期
        system_token = _create_system_token()

        try:
            result = await recon_queue_dequeue(system_token)
            job = (result or {}).get("job")
            if job:
                await _process_job(job, system_token)
            else:
                await asyncio.sleep(POLL_INTERVAL)
        except Exception as exc:
            logger.error("[recon-worker] 轮询异常: %s", exc, exc_info=True)
            await asyncio.sleep(POLL_INTERVAL)

    logger.info("[recon-worker] 已退出")


if __name__ == "__main__":
    asyncio.run(main())
