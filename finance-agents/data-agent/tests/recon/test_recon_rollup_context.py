from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(ROOT))

execution_service = importlib.import_module("graphs.recon.execution_service")
auto_nodes = importlib.import_module("graphs.recon.auto_scheme_run.nodes")


@pytest.mark.asyncio
async def test_run_recon_execution_passes_run_context(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    async def fake_execute_recon(**kwargs):
        seen.update(kwargs)
        return {"success": True, "results": []}

    monkeypatch.setattr(execution_service, "execute_recon", fake_execute_recon)

    result, error = await execution_service.run_recon_execution(
        {
            "rule_code": "rule-001",
            "rule_id": "r1",
            "auth_token": "token",
            "validated_inputs": [],
            "validated_files": [],
            "run_context": {"biz_date": "2026-06-05", "rollup": {"enabled": True}},
        }
    )

    assert error is None
    assert result["success"] is True
    assert seen["run_context"] == {"biz_date": "2026-06-05", "rollup": {"enabled": True}}


def test_build_auto_run_context_merges_plan_meta_rollup() -> None:
    state = {
        "recon_ctx": {
            "biz_date": "2026-06-05",
            "run_plan_code": "FY-FUND-001",
            "scheme_code": "scheme-001",
            "run_plan": {
                "plan_name": "福游资金对账",
                "plan_meta_json": {
                    "rollup": {
                        "enabled": True,
                        "domain": "ecom",
                        "recon_type": "fund",
                        "stuck_days_n": 5,
                        "field_mapping": {"domain": "ecom", "canonical": {}},
                    }
                },
            },
        }
    }

    result = auto_nodes.build_auto_run_context_node(state)
    run_context = result["recon_ctx"]["run_context"]

    assert run_context["rollup"]["plan_code"] == "FY-FUND-001"
    assert run_context["rollup"]["plan_name_snapshot"] == "福游资金对账"
    assert run_context["rollup"]["biz_date"] == "2026-06-05"
    assert run_context["rollup"]["recon_type"] == "fund"
    assert run_context["biz_date"] == "2026-06-05"
