from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import jwt
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from graphs.recon.scheme_design.service import (
    JWT_ALGORITHM,
    JWT_SECRET,
    StartSessionInput,
    SchemeDesignService,
    UseExistingRuleInput,
)
from graphs.recon.scheme_design.session_store import InMemorySchemeDesignSessionStore
from graphs.recon.scheme_design.executor import FallbackSchemeDesignExecutor


def _auth_token() -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": "user_1",
            "username": "tester",
            "company_id": "company_1",
            "iat": now,
            "exp": now + timedelta(minutes=30),
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def _dataset(*, side: str, table_name: str, rows: list[dict[str, object]]) -> dict[str, object]:
    return {
        "side": side,
        "dataset_name": table_name,
        "table_name": table_name,
        "resource_key": table_name,
        "source_id": f"source_{side}",
        "sample_rows": rows,
    }


def test_trial_proc_step_prefers_request_sample_datasets(monkeypatch: pytest.MonkeyPatch) -> None:
    asyncio.run(_run_trial_proc_step_prefers_request_sample_datasets(monkeypatch))


async def _run_trial_proc_step_prefers_request_sample_datasets(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def fake_compatibility(auth_token: str, payload: dict[str, object]) -> dict[str, object]:
        return {
            "success": True,
            "compatible": True,
            "normalized_rule": payload["proc_rule_json"],
        }

    async def fake_proc_trial(auth_token: str, payload: dict[str, object]) -> dict[str, object]:
        captured["sample_datasets"] = payload["sample_datasets"]
        return {
            "success": True,
            "ready_for_confirm": True,
            "normalized_rule": payload["proc_rule_json"],
            "output_samples": [
                {
                    "side": "left",
                    "target_table": "left_recon_ready",
                    "rows": [{"biz_key": "LEFT-REQUEST"}],
                    "row_count": 1,
                },
                {
                    "side": "right",
                    "target_table": "right_recon_ready",
                    "rows": [{"biz_key": "RIGHT-REQUEST"}],
                    "row_count": 1,
                },
            ],
        }

    monkeypatch.setattr(
        "graphs.recon.scheme_design.service.execution_proc_rule_compatibility_check",
        fake_compatibility,
    )
    monkeypatch.setattr(
        "graphs.recon.scheme_design.service.execution_proc_draft_trial",
        fake_proc_trial,
    )

    service = SchemeDesignService(
        store=InMemorySchemeDesignSessionStore(),
        executor=FallbackSchemeDesignExecutor(),
    )

    async def fake_target_samples(session: object, *, auth_token: str) -> list[dict[str, object]]:
        return [dict(item) for item in getattr(session, "sample_datasets", [])]

    monkeypatch.setattr(service, "_build_target_sample_datasets", fake_target_samples)
    token = _auth_token()
    session = await service.start_session(
        auth_token=token,
        payload=StartSessionInput(
            scheme_name="样例沿用测试",
            sample_datasets=[
                _dataset(side="left", table_name="left_source", rows=[{"order_no": "LEFT-SESSION"}]),
                _dataset(side="right", table_name="right_source", rows=[{"order_no": "RIGHT-SESSION"}]),
            ],
        ),
    )
    proc_rule = {
        "steps": [
            {"action": "create_schema", "target_table": "left_recon_ready", "schema": {"columns": []}},
            {"action": "write_dataset", "target_table": "left_recon_ready", "sources": [{"table": "left_source"}]},
            {"action": "create_schema", "target_table": "right_recon_ready", "schema": {"columns": []}},
            {"action": "write_dataset", "target_table": "right_recon_ready", "sources": [{"table": "right_source"}]},
        ],
    }
    await service.use_existing_proc_rule(
        auth_token=token,
        session_id=session.session_id,
        payload=UseExistingRuleInput(rule_json=proc_rule),
    )

    await service.trial_proc_step(
        auth_token=token,
        session_id=session.session_id,
        sample_datasets=[
            _dataset(side="left", table_name="left_source", rows=[{"order_no": "LEFT-REQUEST"}]),
            _dataset(side="right", table_name="right_source", rows=[{"order_no": "RIGHT-REQUEST"}]),
        ],
    )

    sample_rows = [
        row
        for dataset in captured["sample_datasets"]  # type: ignore[index]
        for row in dataset["sample_rows"]  # type: ignore[index]
    ]
    assert {"order_no": "LEFT-REQUEST"} in sample_rows
    assert {"order_no": "RIGHT-REQUEST"} in sample_rows
    assert {"order_no": "LEFT-SESSION"} not in sample_rows
    assert {"order_no": "RIGHT-SESSION"} not in sample_rows
