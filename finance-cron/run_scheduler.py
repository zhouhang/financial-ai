#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import logging
import signal
from pathlib import Path

from dotenv import load_dotenv

from scheduler_service import FinanceCronSchedulerService, load_cron_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("finance-cron")


def load_env() -> None:
    project_root = Path(__file__).resolve().parents[1]
    load_dotenv(project_root / ".env")
    load_dotenv(Path(__file__).resolve().parent / ".env", override=True)


async def _main(config_path: Path) -> int:
    config = load_cron_config(config_path)
    service = FinanceCronSchedulerService(config)
    stop_event = asyncio.Event()

    def _stop() -> None:
        if not stop_event.is_set():
            logger.info("收到停止信号，正在关闭 finance-cron")
            stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            pass

    await service.start()
    try:
        await stop_event.wait()
    finally:
        await service.shutdown()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run finance-cron scheduler service.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parent / "config" / "cron_config.yaml",
        help="scheduler config path",
    )
    args = parser.parse_args()

    load_env()
    return asyncio.run(_main(args.config))


if __name__ == "__main__":
    raise SystemExit(main())
