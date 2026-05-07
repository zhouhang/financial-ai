from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

spec = importlib.util.spec_from_file_location(
    "finance_cron_scheduler_service",
    PROJECT_ROOT / "scheduler_service.py",
)
assert spec and spec.loader
scheduler_service = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = scheduler_service
spec.loader.exec_module(scheduler_service)


def test_build_trigger_from_plan_daily_weekly_monthly():
    tz = scheduler_service.ZoneInfo("Asia/Shanghai")

    daily = scheduler_service.build_trigger_from_plan(
        {"schedule_type": "daily", "schedule_expr": "09:30"},
        tz=tz,
    )
    weekly = scheduler_service.build_trigger_from_plan(
        {"schedule_type": "weekly", "schedule_expr": "MON 10:15"},
        tz=tz,
    )
    monthly = scheduler_service.build_trigger_from_plan(
        {"schedule_type": "monthly", "schedule_expr": "15 08:05"},
        tz=tz,
    )

    assert daily is not None
    assert weekly is not None
    assert monthly is not None
    assert "hour='9'" in str(daily)
    assert "day_of_week='mon'" in str(weekly)
    assert "day='15'" in str(monthly)


def test_two_hour_cron_trigger_is_supported():
    tz = scheduler_service.ZoneInfo("Asia/Shanghai")
    trigger = scheduler_service.build_trigger_from_plan(
        {"schedule_type": "cron", "schedule_expr": "0 */2 * * *"},
        tz=tz,
    )

    assert trigger is not None


def test_refresh_run_plans_registers_jobs(monkeypatch):
    service = scheduler_service.FinanceCronSchedulerService(
        scheduler_service.FinanceCronConfig(refresh_interval_seconds=30)
    )

    async def fake_load_enabled_run_plans(scheduler_token: str):
        return [
            {
                "company_id": "company_001",
                "plan_code": "plan_daily",
                "schedule_type": "daily",
                "schedule_expr": "09:30",
            },
            {
                "company_id": "company_001",
                "plan_code": "plan_manual",
                "schedule_type": "manual_trigger",
                "schedule_expr": "",
            },
        ]

    monkeypatch.setattr(service, "_load_enabled_run_plans", fake_load_enabled_run_plans)
    asyncio.run(service.refresh_run_plans())

    job_ids = {job.id for job in service.scheduler.get_jobs()}
    assert "run-plan:company_001:plan_daily" in job_ids
    assert "run-plan:company_001:plan_manual" not in job_ids


def test_execute_run_plan_job_avoids_duplicate_slot(monkeypatch):
    triggered: list[tuple[str, str]] = []
    existing_slots: set[str] = set()

    async def fake_get_slot_run(
        auth_token: str,
        *,
        company_id: str,
        plan_code: str,
        schedule_slot: str,
    ):
        return {
            "success": True,
            "exists": schedule_slot in existing_slots,
        }

    async def fake_trigger_run_plan(
        auth_token: str,
        *,
        run_plan_code: str,
        biz_date: str = "",
        trigger_mode: str = "schedule",
        run_context: dict | None = None,
    ):
        schedule_slot = str((run_context or {}).get("schedule_slot") or "")
        existing_slots.add(schedule_slot)
        triggered.append((run_plan_code, schedule_slot))
        return {"success": True}

    monkeypatch.setattr(scheduler_service, "execution_scheduler_get_slot_run", fake_get_slot_run)
    monkeypatch.setattr(scheduler_service, "trigger_run_plan", fake_trigger_run_plan)

    async def _run() -> None:
        service = scheduler_service.FinanceCronSchedulerService(
            scheduler_service.FinanceCronConfig(refresh_interval_seconds=30)
        )
        await service.execute_run_plan_job(
            company_id="company_001",
            run_plan_code="plan_001",
            schedule_type="daily",
            schedule_expr="09:30",
        )
        await service.execute_run_plan_job(
            company_id="company_001",
            run_plan_code="plan_001",
            schedule_type="daily",
            schedule_expr="09:30",
        )

    asyncio.run(_run())

    assert len(triggered) == 1
    assert triggered[0][0] == "plan_001"
