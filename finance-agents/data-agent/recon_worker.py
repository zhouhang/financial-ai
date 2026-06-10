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

from graphs.recon.auto_run_service import execute_run_plan_run, finalize_and_deliver_daily_digest
from tools.mcp_client import (
    execution_run_update,
    recon_queue_complete,
    recon_queue_dequeue,
    recon_queue_fail,
    recon_queue_fail_expired_waiting,
    recon_queue_reclaim_stale,
    recon_queue_requeue_ready_waiting,
    recon_queue_waiting_data,
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


def _queue_duration_seconds(started_at: object, finished_at: object) -> float | None:
    try:
        start = datetime.fromisoformat(str(started_at or "").replace("Z", "+00:00"))
        finish = datetime.fromisoformat(str(finished_at or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return round(max(0.0, (finish - start).total_seconds()), 6)


async def _process_job(job: dict, system_token: str) -> None:
    job_id = str(job["id"])
    company_id = str(job["company_id"])
    run_plan_code = str(job["run_plan_code"])
    logger.info("[recon-worker] 开始处理 job_id=%s run_plan_code=%s", job_id, run_plan_code)
    try:
        auth_token = _create_worker_token(company_id)
        result = await execute_run_plan_run(
            auth_token=auth_token,
            run_plan_code=run_plan_code,
            biz_date=str(job.get("biz_date") or ""),
            trigger_mode=str(job.get("trigger_mode") or "schedule"),
            run_context={
                **dict(job.get("run_context") or {}),
                "queue_job_id": job_id,
                "queue_started_at": str(job.get("started_at") or ""),
                "queue_created_at": str(job.get("created_at") or ""),
            },
        )
        if result.get("status") == "data_waiting":
            run = dict(result.get("run") or {})
            execution_run_id = str(run.get("id") or "")
            waiting_result = await recon_queue_waiting_data(
                system_token,
                job_id,
                {
                    "waiting_reason": str(result.get("error") or "browser_collection_pending"),
                    "waiting_datasets": list(result.get("waiting_datasets") or []),
                    "collection_job_ids": [str(v) for v in result.get("collection_job_ids") or [] if str(v)],
                    "execution_run_id": execution_run_id,
                    "wait_minutes": int(os.getenv("RECON_WAITING_DATA_TIMEOUT_MINUTES", "90")),
                },
            )
            if not bool(waiting_result.get("success")):
                error = str(
                    waiting_result.get("error")
                    or waiting_result.get("message")
                    or "recon_queue_waiting_data 返回失败"
                )
                await recon_queue_fail(system_token, job_id, f"waiting_data 更新失败: {error}"[:2000])
                logger.error("[recon-worker] job_id=%s waiting_data 更新失败: %s", job_id, error)
                return
            logger.info("[recon-worker] job_id=%s 进入 waiting_data", job_id)
            return
        complete_result = await recon_queue_complete(system_token, job_id)
        completed_job = dict(complete_result.get("job") or {})
        run = dict(result.get("run") or {})
        run_id = str(run.get("id") or "")
        artifacts = dict(run.get("artifacts_json") or {})
        runtime_summary = dict(artifacts.get("runtime_summary") or {})
        queue = dict(runtime_summary.get("queue") or {})
        queue["finished_at"] = str(completed_job.get("finished_at") or queue.get("finished_at") or "")
        queue["duration_seconds"] = _queue_duration_seconds(queue.get("started_at"), queue.get("finished_at"))
        runtime_summary["queue"] = queue
        artifacts["runtime_summary"] = runtime_summary
        if run_id:
            await execution_run_update(auth_token, run_id, {"artifacts_json": artifacts})
        if bool(result.get("success")) and str(run.get("execution_status") or "") == "success":
            biz_date = str(result.get("biz_date") or job.get("biz_date") or "").strip()
            if biz_date:
                digest_result = await finalize_and_deliver_daily_digest(
                    auth_token=auth_token,
                    company_id=company_id,
                    biz_date=biz_date,
                )
                if bool(digest_result.get("success")):
                    logger.info(
                        "[recon-worker] digest finalizer 完成: job_id=%s biz_date=%s ready=%s delivered=%s blocked=%s",
                        job_id,
                        biz_date,
                        digest_result.get("ready_count"),
                        digest_result.get("delivered_count"),
                        digest_result.get("blocked_count"),
                    )
                else:
                    logger.warning(
                        "[recon-worker] digest finalizer 失败: job_id=%s biz_date=%s error=%s",
                        job_id,
                        biz_date,
                        digest_result.get("error"),
                    )
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

        # Waiting-data 调和(requeue ready / fail expired / fail failed)从 v2 起由
        # browser-agent 的 _waiting_reconciler 单点拥有,这里不再 per-worker 重复轮询。
        # recon-worker 只负责 dequeue 自己的 queued job、跑、必要时 park 到 waiting_data。
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
