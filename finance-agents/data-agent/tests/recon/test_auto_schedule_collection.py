from __future__ import annotations

import asyncio
import importlib
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RECON_DIR = ROOT / "graphs" / "recon"
AUTO_SCHEME_DIR = RECON_DIR / "auto_scheme_run"

sys.path.insert(0, str(ROOT))


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


def test_check_dataset_ready_schedule_collects_before_recon(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    async def fake_collect(auth_token: str, source_id: str, **kwargs: object) -> dict[str, object]:
        calls.append(("collect", {"auth_token": auth_token, "source_id": source_id, **kwargs}))
        return {"success": True, "job": {"id": "job-001"}}

    async def fake_list(auth_token: str, source_id: str, **kwargs: object) -> dict[str, object]:
        calls.append(("list", {"auth_token": auth_token, "source_id": source_id, **kwargs}))
        return {
            "success": True,
            "dataset_id": "dataset-001",
            "resource_key": "orders",
            "record_count": 2,
            "records": [{"item_key": "1"}, {"item_key": "2"}],
        }

    monkeypatch.setattr(nodes, "data_source_trigger_dataset_collection", fake_collect)
    monkeypatch.setattr(nodes, "data_source_list_collection_records", fake_list)

    state = {
        "auth_token": "token",
        "recon_ctx": {
            "biz_date": "2026-04-25",
            "run_context": {"trigger_type": "schedule"},
            "plan_input_bindings": [
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

    result = asyncio.run(nodes.check_dataset_ready_node(state))
    bind_result = nodes.bind_ready_collection_node(result)
    recon_ctx = bind_result["recon_ctx"]

    assert [item[0] for item in calls] == ["collect", "list"]
    assert calls[0][1]["trigger_mode"] == "scheduled"
    assert recon_ctx["missing_bindings"] == []
    assert recon_ctx["ready_collections"][0]["collection_records"]["record_count"] == 2
    assert recon_ctx["collection_attempts"][0]["success"] is True
    assert recon_ctx["source_collection_json"]["collection_attempts"][0]["success"] is True


def test_check_dataset_ready_collection_failure_blocks_stale_records(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def fake_collect(auth_token: str, source_id: str, **kwargs: object) -> dict[str, object]:
        calls.append("collect")
        return {"success": False, "error": "upstream timeout"}

    async def fake_list(auth_token: str, source_id: str, **kwargs: object) -> dict[str, object]:
        calls.append("list")
        return {
            "success": True,
            "dataset_id": "dataset-001",
            "resource_key": "orders",
            "record_count": 9,
            "records": [{"item_key": "stale"}],
        }

    monkeypatch.setattr(nodes, "data_source_trigger_dataset_collection", fake_collect)
    monkeypatch.setattr(nodes, "data_source_list_collection_records", fake_list)

    state = {
        "auth_token": "token",
        "recon_ctx": {
            "biz_date": "2026-04-25",
            "run_context": {"trigger_type": "schedule"},
            "plan_input_bindings": [
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

    result = asyncio.run(nodes.check_dataset_ready_node(state))
    recon_ctx = result["recon_ctx"]

    assert calls == ["collect"]
    assert recon_ctx["ready_collections"] == []
    assert recon_ctx["missing_bindings"][0]["error"] == "先同步失败：upstream timeout"


def test_execute_auto_task_run_schedule_collects_before_recon(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def fake_task_get(auth_token: str, auto_task_id: str) -> dict[str, object]:
        return {
            "success": True,
            "task": {
                "id": auto_task_id,
                "task_name": "日结对账",
                "rule_code": "merchant_recon_rule",
                "auto_create_exceptions": False,
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
        captured["list"] = {"auth_token": auth_token, "source_id": source_id, **kwargs}
        return {
            "success": True,
            "dataset_id": "dataset-001",
            "resource_key": "orders",
            "record_count": 1,
            "records": [{"item_key": "1"}],
        }

    async def fake_run_create(auth_token: str, payload: dict[str, object]) -> dict[str, object]:
        captured["run_create"] = payload
        return {"success": True, "run": {"id": "run-001"}}

    async def fake_run_job_create(auth_token: str, payload: dict[str, object]) -> dict[str, object]:
        return {"success": True, "run_job": {"id": "job-001"}}

    async def fake_run_update(auth_token: str, auto_run_id: str, payload: dict[str, object]) -> dict[str, object]:
        return {"success": True, "run": {"id": auto_run_id, **payload}}

    async def fake_rule(auth_token: str, rule_code: str) -> dict[str, object]:
        return {
            "success": True,
            "data": {
                "rule": {"rule_name": "商户对账规则", "rules": []},
            },
        }

    async def fake_pipeline(**kwargs: object) -> dict[str, object]:
        return {
            "ok": True,
            "execution_result": {"success": True},
            "recon_observation": {"summary": {}, "anomaly_items": []},
        }

    async def fake_run_get(auth_token: str, auto_run_id: str) -> dict[str, object]:
        return {"success": True, "run": {"id": auto_run_id}}

    async def fake_run_job_update(auth_token: str, run_job_id: str, payload: dict[str, object]) -> dict[str, object]:
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
            biz_date="2026-04-25",
            trigger_mode="schedule",
        )
    )

    assert result["success"] is True
    assert captured["collect"]["trigger_mode"] == "scheduled"
    assert captured["run_create"]["source_snapshot_json"]["collection_attempts"][0]["success"] is True


def test_execute_auto_task_run_manual_collects_before_recon(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def fake_task_get(auth_token: str, auto_task_id: str) -> dict[str, object]:
        return {
            "success": True,
            "task": {
                "id": auto_task_id,
                "task_name": "手工对账",
                "rule_code": "merchant_recon_rule",
                "auto_create_exceptions": False,
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

    async def fake_run_update(auth_token: str, auto_run_id: str, payload: dict[str, object]) -> dict[str, object]:
        return {"success": True, "run": {"id": auto_run_id, **payload}}

    async def fake_rule(auth_token: str, rule_code: str) -> dict[str, object]:
        return {
            "success": True,
            "data": {
                "rule": {"rule_name": "商户对账规则", "rules": []},
            },
        }

    async def fake_pipeline(**kwargs: object) -> dict[str, object]:
        return {
            "ok": True,
            "execution_result": {"success": True},
            "recon_observation": {"summary": {}, "anomaly_items": []},
        }

    async def fake_run_get(auth_token: str, auto_run_id: str) -> dict[str, object]:
        return {"success": True, "run": {"id": auto_run_id}}

    async def fake_run_job_update(auth_token: str, run_job_id: str, payload: dict[str, object]) -> dict[str, object]:
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
            biz_date="2026-04-25",
            trigger_mode="manual",
        )
    )

    assert result["success"] is True
    assert captured["collect"]["trigger_mode"] == "manual"


def test_normalize_execution_trigger_type_preserves_manual_and_rerun() -> None:
    assert nodes._normalize_execution_trigger_type("manual") == "manual"
    assert nodes._normalize_execution_trigger_type("manual_trigger") == "manual"
    assert nodes._normalize_execution_trigger_type("rerun") == "rerun"
    assert nodes._normalize_execution_trigger_type("retry") == "rerun"
    assert nodes._normalize_execution_trigger_type("schedule") == "schedule"
