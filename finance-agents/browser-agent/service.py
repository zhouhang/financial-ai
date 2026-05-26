"""Browser-agent long-running service entrypoint.

Runs on the collection machine, packages dispatcher + runner together. Tally Cloud remains the
queue and data source of truth; this process polls finance-mcp via MCP SSE only.

Two coroutines run side by side:

  - ``_dispatcher`` spawns ``BROWSER_AGENT_MAX_CONCURRENCY`` worker coroutines via
    ``BrowserDispatcherLoop.create_worker_tasks()``. Each worker claims, runs (in a thread to
    avoid blocking the event loop), and reports.
  - ``_waiting_reconciler`` periodically calls the three recon-queue helpers to (a) fast-fail
    waiting jobs whose collection sync_job already failed, (b) requeue waiting jobs whose
    collection succeeded, (c) fail waiting jobs that exceeded their deadline. This replaces the
    per-worker polling that used to live in recon-worker.

SIGTERM/SIGINT cleanly cancels both coroutines.
"""

from __future__ import annotations

import asyncio
import logging
import signal

from finance_browser_agent.dispatcher_loop import BrowserDispatcherLoop
from finance_browser_agent.tally_client import BrowserAgentConfig, BrowserAgentTallyClient
from runner import run_message  # type: ignore[import-not-found]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("browser-agent")

_shutdown = False


def _handle_signal(signum, frame) -> None:
    global _shutdown
    _shutdown = True
    logger.info("收到停止信号: %s", signum)


async def _waiting_reconciler(client: BrowserAgentTallyClient, interval_seconds: float) -> None:
    while not _shutdown:
        try:
            await client.fail_failed_waiting()
            await client.requeue_ready_waiting()
            await client.fail_expired_waiting()
        except Exception:
            logger.exception("waiting-data 调和异常")
        await asyncio.sleep(interval_seconds)


async def _heartbeat(client: BrowserAgentTallyClient, config: BrowserAgentConfig) -> None:
    while not _shutdown:
        try:
            if config.company_id:
                await client.heartbeat()
            else:
                logger.warning("未配置 BROWSER_AGENT_COMPANY_ID，跳过 browser-agent 心跳上报")
        except Exception:
            logger.exception("browser-agent 心跳上报异常")
        await asyncio.sleep(config.heartbeat_interval_seconds)


async def _cleanup_interrupted_jobs(client: BrowserAgentTallyClient) -> None:
    try:
        result = await client.startup_cleanup()
    except Exception:
        logger.exception("browser-agent 启动清理旧任务异常")
        return
    if not bool(result.get("success", False)):
        logger.warning("browser-agent 启动清理旧任务失败: %s", result.get("error") or result)
        return
    failed_count = int(result.get("failed_count") or 0)
    if failed_count:
        logger.warning(
            "browser-agent 启动清理旧 running 任务: failed_count=%s sync_job_ids=%s",
            failed_count,
            result.get("sync_job_ids") or [],
        )


async def _dispatcher(client: BrowserAgentTallyClient, config: BrowserAgentConfig) -> None:
    loop = BrowserDispatcherLoop(
        client=client,
        runner=run_message,
        max_concurrency=config.max_concurrency,
    )
    workers = loop.create_worker_tasks()
    try:
        while not _shutdown:
            await asyncio.sleep(config.poll_interval_seconds)
    finally:
        for task in workers:
            task.cancel()
        await asyncio.gather(*workers, return_exceptions=True)


async def main() -> None:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    config = BrowserAgentConfig.from_env()
    client = BrowserAgentTallyClient(config=config)
    logger.info(
        "browser-agent 启动: agent_id=%s company_id=%s max_concurrency=%s data_agent_ws=%s",
        config.agent_id,
        config.company_id or "<missing>",
        config.max_concurrency,
        config.data_agent_ws_url,
    )
    await _cleanup_interrupted_jobs(client)
    await asyncio.gather(
        _heartbeat(client, config),
        _dispatcher(client, config),
        _waiting_reconciler(client, config.waiting_poll_interval_seconds),
    )


if __name__ == "__main__":
    asyncio.run(main())
