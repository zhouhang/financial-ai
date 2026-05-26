from __future__ import annotations

import asyncio
import importlib
import sys
import types
from pathlib import Path

import pytest

DATA_AGENT_ROOT = Path(__file__).resolve().parents[1]
RECON_DIR = DATA_AGENT_ROOT / "graphs" / "recon"
AUTO_SCHEME_DIR = RECON_DIR / "auto_scheme_run"

if str(DATA_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(DATA_AGENT_ROOT))


def _ensure_package(name: str, path: Path) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        module.__path__ = [str(path)]
        sys.modules[name] = module
    return module


_ensure_package("graphs.recon", RECON_DIR)
auto_scheme_package = _ensure_package("graphs.recon.auto_scheme_run", AUTO_SCHEME_DIR)


async def _unused_run_auto_scheme_run_graph(*args: object, **kwargs: object) -> dict[str, object]:
    raise AssertionError("run_auto_scheme_run_graph should not be called in this test module")


auto_scheme_package.run_auto_scheme_run_graph = _unused_run_auto_scheme_run_graph

nodes = importlib.import_module("graphs.recon.auto_scheme_run.nodes")
auto_run_service = importlib.import_module("graphs.recon.auto_run_service")


def test_auto_scheme_collection_trigger_carries_handoff_channel_and_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_collect(auth_token: str, source_id: str, **kwargs: object) -> dict[str, object]:
        captured["collect"] = {"auth_token": auth_token, "source_id": source_id, **kwargs}
        return {
            "success": True,
            "queued": True,
            "collection_driver": "browser_playbook_remote",
            "job": {"id": "sync-job-001", "job_status": "queued"},
        }

    async def stale_collection_lookup(*args: object, **kwargs: object) -> dict[str, object]:
        raise AssertionError("browser queued collection should not list stale collection records")

    monkeypatch.setattr(nodes, "data_source_trigger_dataset_collection", fake_collect)
    monkeypatch.setattr(nodes, "data_source_list_collection_records", stale_collection_lookup)

    state = {
        "auth_token": "token",
        "recon_ctx": {
            "biz_date": "2026-05-24",
            "run_context": {"trigger_type": "schedule"},
            "run_plan": {
                "channel_config_id": "chan-001",
                "owner_mapping_json": {
                    "default_owner": {"name": "周行", "identifier": "u-zhou"},
                },
            },
            "plan_input_bindings": [
                {
                    "data_source_id": "source-001",
                    "dataset_id": "dataset-001",
                    "resource_key": "orders",
                    "table_name": "orders",
                    "required": True,
                    "collection_driver": "browser_playbook_remote",
                    "dataset_source_type": "collection_records",
                }
            ],
        },
    }

    result = asyncio.run(nodes.check_dataset_ready_node(state))

    assert result["recon_ctx"]["missing_bindings"][0]["waiting_data"] is True
    assert captured["collect"]["params"] == {
        "handoff_channel_config_id": "chan-001",
        "handoff_owner": {"name": "周行", "identifier": "u-zhou"},
    }


def test_auto_task_collection_trigger_carries_handoff_channel_and_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_task_get(auth_token: str, auto_task_id: str) -> dict[str, object]:
        return {
            "success": True,
            "task": {
                "id": auto_task_id,
                "task_name": "日结对账",
                "rule_code": "merchant_recon_rule",
                "channel_config_id": "chan-001",
                "owner_mapping_json": {
                    "default_owner": {"name": "周行", "identifier": "u-zhou"},
                },
                "input_bindings": [
                    {
                        "data_source_id": "source-001",
                        "dataset_id": "dataset-001",
                        "table_name": "orders_ready",
                        "resource_key": "orders",
                        "required": True,
                    }
                ],
            },
        }

    async def fake_collect(auth_token: str, source_id: str, **kwargs: object) -> dict[str, object]:
        captured["collect"] = {"auth_token": auth_token, "source_id": source_id, **kwargs}
        return {"success": True, "job": {"id": "job-001"}}

    async def fake_list(auth_token: str, source_id: str, **kwargs: object) -> dict[str, object]:
        return {
            "success": True,
            "dataset_id": "dataset-001",
            "resource_key": "orders",
            "record_count": 1,
            "records": [{"item_key": "1"}],
        }

    async def fake_run_create(auth_token: str, payload: dict[str, object]) -> dict[str, object]:
        return {"success": True, "run": {"id": "run-001"}}

    async def fake_run_job_create(auth_token: str, payload: dict[str, object]) -> dict[str, object]:
        return {"success": True, "run_job": {"id": "job-001"}}

    async def fake_run_update(
        auth_token: str,
        auto_run_id: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        return {"success": True, "run": {"id": auto_run_id, **payload}}

    async def fake_rule(auth_token: str, rule_code: str) -> dict[str, object]:
        return {"success": True, "data": {"rule": {"rule_name": "商户对账规则", "rules": []}}}

    async def fake_pipeline(**kwargs: object) -> dict[str, object]:
        return {
            "ok": True,
            "execution_result": {"success": True},
            "recon_observation": {"summary": {}, "anomaly_items": []},
        }

    async def fake_run_get(auth_token: str, auto_run_id: str) -> dict[str, object]:
        return {"success": True, "run": {"id": auto_run_id}}

    async def fake_run_job_update(
        auth_token: str,
        run_job_id: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        return {"success": True, "run_job": {"id": run_job_id, **payload}}

    monkeypatch.setattr(auto_run_service, "recon_auto_task_get", fake_task_get)
    monkeypatch.setattr(auto_run_service, "data_source_trigger_dataset_collection", fake_collect)
    monkeypatch.setattr(auto_run_service, "data_source_list_collection_records", fake_list)
    monkeypatch.setattr(auto_run_service, "recon_auto_run_create", fake_run_create)
    monkeypatch.setattr(auto_run_service, "recon_auto_run_job_create", fake_run_job_create)
    monkeypatch.setattr(auto_run_service, "recon_auto_run_update", fake_run_update)
    monkeypatch.setattr(auto_run_service, "get_file_validation_rule", fake_rule)
    monkeypatch.setattr(auto_run_service, "execute_headless_recon_pipeline", fake_pipeline)
    monkeypatch.setattr(auto_run_service, "recon_auto_run_get", fake_run_get)
    monkeypatch.setattr(auto_run_service, "recon_auto_run_job_update", fake_run_job_update)

    result = asyncio.run(
        auto_run_service.execute_auto_task_run(
            auth_token="token",
            auto_task_id="task-001",
            biz_date="2026-05-24",
            trigger_mode="schedule",
        )
    )

    assert result["success"] is True
    assert captured["collect"]["params"] == {
        "handoff_channel_config_id": "chan-001",
        "handoff_owner": {"name": "周行", "identifier": "u-zhou"},
    }
