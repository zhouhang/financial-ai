from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import jwt
import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from data_agent_client import trigger_run_plan
from mcp_client import (
    aclose_mcp_session,
    execution_scheduler_get_slot_run,
    execution_scheduler_list_run_plans,
)

logger = logging.getLogger(__name__)

_WEEKDAY_MAP = {
    "MON": "mon",
    "TUE": "tue",
    "WED": "wed",
    "THU": "thu",
    "FRI": "fri",
    "SAT": "sat",
    "SUN": "sun",
}


@dataclass(slots=True)
class FinanceCronConfig:
    timezone: str = "Asia/Shanghai"
    refresh_interval_seconds: int = 30
    plan_page_size: int = 200
    misfire_grace_seconds: int = 60


def load_cron_config(path: Path | None = None) -> FinanceCronConfig:
    data: dict[str, Any] = {}
    if path and path.exists():
        with path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}

    scheduler = dict(data.get("scheduler") or {})
    return FinanceCronConfig(
        timezone=str(
            os.getenv("RECON_SCHEDULER_TIMEZONE")
            or scheduler.get("timezone")
            or "Asia/Shanghai"
        ),
        refresh_interval_seconds=max(
            int(
                os.getenv("FINANCE_CRON_REFRESH_INTERVAL_SECONDS")
                or scheduler.get("refresh_interval_seconds")
                or 30
            ),
            5,
        ),
        plan_page_size=max(
            int(
                os.getenv("FINANCE_CRON_PLAN_PAGE_SIZE")
                or scheduler.get("plan_page_size")
                or 200
            ),
            1,
        ),
        misfire_grace_seconds=max(
            int(
                os.getenv("FINANCE_CRON_MISFIRE_GRACE_SECONDS")
                or scheduler.get("misfire_grace_seconds")
                or 60
            ),
            1,
        ),
    )


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _parse_hhmm(expr: str) -> tuple[int, int] | None:
    text = _as_text(expr)
    try:
        hour_text, minute_text = text.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except (ValueError, TypeError):
        return None
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None
    return hour, minute


def _parse_weekly_expr(expr: str) -> tuple[str, int, int] | None:
    parts = _as_text(expr).split()
    if len(parts) != 2:
        return None
    weekday = _WEEKDAY_MAP.get(parts[0].upper())
    hhmm = _parse_hhmm(parts[1])
    if weekday is None or hhmm is None:
        return None
    return weekday, hhmm[0], hhmm[1]


def _parse_monthly_expr(expr: str) -> tuple[int, int, int] | None:
    parts = _as_text(expr).split()
    if len(parts) != 2:
        return None
    try:
        day = int(parts[0])
    except ValueError:
        return None
    hhmm = _parse_hhmm(parts[1])
    if hhmm is None or day < 1 or day > 31:
        return None
    return day, hhmm[0], hhmm[1]


def build_schedule_slot(schedule_type: str, due_at: datetime) -> str:
    return f"{schedule_type}:{due_at.strftime('%Y-%m-%dT%H:%M')}"


def create_scheduler_auth_token(*, company_id: str = "") -> str:
    jwt_secret = os.getenv("JWT_SECRET", "tally-secret-change-in-production")
    now = datetime.now(timezone.utc)
    payload = {
        "sub": f"finance-cron:{company_id or 'system'}",
        "username": "finance-cron",
        "role": "system",
        "company_id": company_id or None,
        "department_id": None,
        "iat": now,
        "exp": now + timedelta(minutes=30),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, jwt_secret, algorithm="HS256")


def build_job_id(plan: dict[str, Any]) -> str:
    return f"run-plan:{_as_text(plan.get('company_id'))}:{_as_text(plan.get('plan_code'))}"


def build_plan_signature(plan: dict[str, Any]) -> str:
    return "|".join(
        [
            _as_text(plan.get("company_id")),
            _as_text(plan.get("plan_code")),
            _as_text(plan.get("schedule_type")),
            _as_text(plan.get("schedule_expr")),
        ]
    )


def build_trigger_from_plan(plan: dict[str, Any], *, tz: ZoneInfo) -> CronTrigger | None:
    schedule_type = _as_text(plan.get("schedule_type")).lower()
    schedule_expr = _as_text(plan.get("schedule_expr"))

    if schedule_type == "manual_trigger":
        return None
    if schedule_type == "daily":
        hhmm = _parse_hhmm(schedule_expr)
        if hhmm is None:
            return None
        return CronTrigger(hour=hhmm[0], minute=hhmm[1], timezone=tz)
    if schedule_type == "weekly":
        parsed = _parse_weekly_expr(schedule_expr)
        if parsed is None:
            return None
        weekday, hour, minute = parsed
        return CronTrigger(day_of_week=weekday, hour=hour, minute=minute, timezone=tz)
    if schedule_type == "monthly":
        parsed = _parse_monthly_expr(schedule_expr)
        if parsed is None:
            return None
        day, hour, minute = parsed
        return CronTrigger(day=day, hour=hour, minute=minute, timezone=tz)
    if schedule_type == "cron":
        return CronTrigger.from_crontab(schedule_expr, timezone=tz)
    return None


class FinanceCronSchedulerService:
    def __init__(self, config: FinanceCronConfig) -> None:
        self.config = config
        self.timezone = ZoneInfo(config.timezone)
        self.scheduler = AsyncIOScheduler(timezone=self.timezone)
        self._plan_signatures: dict[str, str] = {}
        self._inflight_slots: set[tuple[str, str, str]] = set()

    async def start(self) -> None:
        self.scheduler.add_job(
            self.refresh_run_plans,
            trigger="interval",
            seconds=self.config.refresh_interval_seconds,
            id="refresh-run-plans",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=self.config.misfire_grace_seconds,
        )
        await self.refresh_run_plans()
        self.scheduler.start()
        logger.info(
            "[finance-cron] 已启动 APScheduler: timezone=%s refresh_interval_seconds=%s",
            self.config.timezone,
            self.config.refresh_interval_seconds,
        )

    async def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        await aclose_mcp_session()

    async def refresh_run_plans(self) -> None:
        scheduler_token = create_scheduler_auth_token()
        plans = await self._load_enabled_run_plans(scheduler_token)

        active_job_ids: set[str] = set()
        for plan in plans:
            job_id = build_job_id(plan)
            signature = build_plan_signature(plan)
            trigger = build_trigger_from_plan(plan, tz=self.timezone)
            if trigger is None:
                self._remove_plan_job(job_id)
                continue

            active_job_ids.add(job_id)
            existing_job = self.scheduler.get_job(job_id)
            if existing_job and self._plan_signatures.get(job_id) == signature:
                continue

            self.scheduler.add_job(
                self.execute_run_plan_job,
                trigger=trigger,
                id=job_id,
                replace_existing=True,
                kwargs={
                    "company_id": _as_text(plan.get("company_id")),
                    "run_plan_code": _as_text(plan.get("plan_code")),
                    "schedule_type": _as_text(plan.get("schedule_type")),
                    "schedule_expr": _as_text(plan.get("schedule_expr")),
                },
                coalesce=True,
                max_instances=1,
                misfire_grace_time=self.config.misfire_grace_seconds,
            )
            self._plan_signatures[job_id] = signature

        for job_id in list(self._plan_signatures.keys()):
            if job_id == "refresh-run-plans":
                continue
            if job_id not in active_job_ids:
                self._remove_plan_job(job_id)

    async def execute_run_plan_job(
        self,
        *,
        company_id: str,
        run_plan_code: str,
        schedule_type: str,
        schedule_expr: str,
    ) -> None:
        company_id = _as_text(company_id)
        run_plan_code = _as_text(run_plan_code)
        if not company_id or not run_plan_code:
            return

        due_at = datetime.now(self.timezone).replace(second=0, microsecond=0)
        schedule_slot = build_schedule_slot(schedule_type, due_at)
        slot_key = (company_id, run_plan_code, schedule_slot)
        if slot_key in self._inflight_slots:
            return

        self._inflight_slots.add(slot_key)
        try:
            scheduler_token = create_scheduler_auth_token()
            exists_result = await execution_scheduler_get_slot_run(
                scheduler_token,
                company_id=company_id,
                plan_code=run_plan_code,
                schedule_slot=schedule_slot,
            )
            if not bool(exists_result.get("success")):
                logger.warning(
                    "[finance-cron] 查询调度窗口失败: run_plan_code=%s error=%s",
                    run_plan_code,
                    exists_result.get("error"),
                )
                return
            if bool(exists_result.get("exists")):
                return

            company_token = create_scheduler_auth_token(company_id=company_id)
            result = await trigger_run_plan(
                company_token,
                run_plan_code=run_plan_code,
                trigger_mode="schedule",
                run_context={
                    "schedule_slot": schedule_slot,
                    "scheduler_time_zone": self.config.timezone,
                    "scheduler_triggered_at": due_at.isoformat(),
                    "schedule_type": schedule_type,
                    "schedule_expr": schedule_expr,
                    "operator": "finance-cron",
                },
            )
            if bool(result.get("success")):
                logger.info(
                    "[finance-cron] 运行计划触发成功: run_plan_code=%s schedule_slot=%s",
                    run_plan_code,
                    schedule_slot,
                )
                return
            logger.warning(
                "[finance-cron] 运行计划触发失败: run_plan_code=%s schedule_slot=%s error=%s",
                run_plan_code,
                schedule_slot,
                result.get("error"),
            )
        finally:
            self._inflight_slots.discard(slot_key)

    async def _load_enabled_run_plans(self, scheduler_token: str) -> list[dict[str, Any]]:
        offset = 0
        plans: list[dict[str, Any]] = []
        while True:
            result = await execution_scheduler_list_run_plans(
                scheduler_token,
                limit=self.config.plan_page_size,
                offset=offset,
            )
            if not bool(result.get("success")):
                raise RuntimeError(str(result.get("error") or "查询运行计划失败"))
            batch = [item for item in (result.get("run_plans") or []) if isinstance(item, dict)]
            plans.extend(batch)
            if len(batch) < self.config.plan_page_size:
                break
            offset += self.config.plan_page_size
        return plans

    def _remove_plan_job(self, job_id: str) -> None:
        with suppress_job_lookup_error():
            self.scheduler.remove_job(job_id)
        self._plan_signatures.pop(job_id, None)


class suppress_job_lookup_error:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc, tb) -> bool:
        from apscheduler.jobstores.base import JobLookupError

        return exc_type is not None and issubclass(exc_type, JobLookupError)
