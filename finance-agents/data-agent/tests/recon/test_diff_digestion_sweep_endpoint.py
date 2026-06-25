"""/recon/diff-digestion-sweep 端点:立即返回 started,sweep 放后台跑。

修复线上 cron 假失败——端点同步跑 21 分钟超 HTTP 超时,误报失败。
改 BackgroundTasks 后立即返回,后台慢慢入队。
"""
import asyncio
import importlib
import sys
from pathlib import Path

import jwt
import pytest
from fastapi import BackgroundTasks

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

auto_run_api = importlib.import_module("graphs.recon.auto_run_api")


def _auth_header() -> str:
    token = jwt.encode(
        {"sub": "u-1", "username": "admin", "company_id": "company-001"},
        auto_run_api.JWT_SECRET,
        algorithm=auto_run_api.JWT_ALGORITHM,
    )
    return f"Bearer {token}"


def test_sweep_endpoint_returns_immediately_and_schedules_background(monkeypatch):
    called: list[tuple[str, str]] = []

    async def fake_sweep(*, company_id: str, since_date: str):
        called.append((company_id, since_date))
        return {"success": True, "scanned": 3, "enqueued": 2, "skipped": 1}

    monkeypatch.setattr(auto_run_api, "sweep_diff_digestion", fake_sweep)

    bg = BackgroundTasks()
    body = auto_run_api.DiffDigestionSweepRequest(since_date="2026-06-10")
    result = asyncio.run(
        auto_run_api.diff_digestion_sweep(body, bg, authorization=_auth_header())
    )

    # 立即返回 started,不内联 await sweep(否则会阻塞 21 分钟)
    assert result["started"] is True
    assert called == [], "sweep 不应在请求内联执行"
    # sweep 已登记为后台任务
    assert len(bg.tasks) == 1

    # 跑后台任务:用正确的 company(来自 token)+ since_date 调 sweep
    asyncio.run(bg())
    assert called == [("company-001", "2026-06-10")]


def test_sweep_endpoint_rejects_empty_since_date():
    bg = BackgroundTasks()
    body = auto_run_api.DiffDigestionSweepRequest(since_date="")
    with pytest.raises(Exception):
        asyncio.run(auto_run_api.diff_digestion_sweep(body, bg, authorization=_auth_header()))
