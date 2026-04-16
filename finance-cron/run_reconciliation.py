#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

from dotenv import load_dotenv

from data_agent_client import trigger_run_plan
from scheduler_service import create_scheduler_auth_token

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("finance-cron")


def load_env() -> None:
    project_root = Path(__file__).resolve().parents[1]
    load_dotenv(project_root / ".env")
    load_dotenv(Path(__file__).resolve().parent / ".env", override=True)


async def _main(args: argparse.Namespace) -> int:
    auth_token = create_scheduler_auth_token(company_id=args.company_id)
    result = await trigger_run_plan(
        auth_token,
        run_plan_code=args.run_plan_code,
        biz_date=args.biz_date,
        trigger_mode=args.trigger_mode,
        run_context={
            "operator": "finance-cron-manual",
            "requested_by": args.requested_by,
        },
    )
    logger.info("run result: %s", json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if bool(result.get("success")) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Trigger one configured run plan via data-agent internal API.")
    parser.add_argument("--run-plan-code", required=True, help="execution run plan code")
    parser.add_argument("--company-id", required=True, help="company id for service token")
    parser.add_argument("--biz-date", default="", help="optional biz date, format YYYY-MM-DD")
    parser.add_argument("--trigger-mode", default="manual", help="manual/api/schedule")
    parser.add_argument("--requested-by", default="finance-cron", help="operator label")
    args = parser.parse_args()

    load_env()
    return asyncio.run(_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
