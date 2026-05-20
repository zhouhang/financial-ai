from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest

DATA_AGENT_ROOT = Path(__file__).resolve().parents[2]
RECON_DIR = DATA_AGENT_ROOT / "graphs" / "recon"
AUTO_SCHEME_DIR = RECON_DIR / "auto_scheme_run"

if str(DATA_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(DATA_AGENT_ROOT))
else:
    sys.path.remove(str(DATA_AGENT_ROOT))
    sys.path.insert(0, str(DATA_AGENT_ROOT))

tools_module = sys.modules.get("tools")
if tools_module is not None:
    module_paths = [Path(item).resolve() for item in getattr(tools_module, "__path__", [])]
    if DATA_AGENT_ROOT.resolve() / "tools" not in module_paths:
        sys.modules.pop("tools", None)


def _ensure_package(name: str, path: Path) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        module.__path__ = [str(path)]
        sys.modules[name] = module
    return module


_ensure_package("graphs.recon", RECON_DIR)
auto_scheme_package = _ensure_package("graphs.recon.auto_scheme_run", AUTO_SCHEME_DIR)

nodes = importlib.import_module("graphs.recon.auto_scheme_run.nodes")
routers = importlib.import_module("graphs.recon.auto_scheme_run.routers")
auto_scheme_package.run_auto_scheme_run_graph = routers.run_auto_scheme_run_graph
auto_run_service = importlib.import_module("graphs.recon.auto_run_service")


@pytest.mark.anyio
async def test_browser_queued_collection_returns_data_waiting_without_stale_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_load_run_plan_node(state: dict[str, object]) -> dict[str, object]:
        ctx = dict(state["recon_ctx"])  # type: ignore[index]
        ctx["run_plan"] = {
            "plan_code": "plan-browser",
            "scheme_code": "scheme-browser",
            "is_active": True,
        }
        ctx["scheme_code"] = "scheme-browser"
        return {"recon_ctx": ctx}

    async def fake_load_scheme_node(state: dict[str, object]) -> dict[str, object]:
        ctx = dict(state["recon_ctx"])  # type: ignore[index]
        ctx["scheme"] = {"scheme_code": "scheme-browser", "scheme_type": "recon"}
        ctx["scheme_code"] = "scheme-browser"
        ctx["scheme_type"] = "recon"
        return {"recon_ctx": ctx}

    def fake_validate_noop(state: dict[str, object]) -> dict[str, object]:
        return {"recon_ctx": dict(state["recon_ctx"])}  # type: ignore[index]

    def fake_resolve_inputs_node(state: dict[str, object]) -> dict[str, object]:
        ctx = dict(state["recon_ctx"])  # type: ignore[index]
        ctx["plan_input_bindings"] = [
            {
                "data_source_id": "source-browser",
                "dataset_id": "dataset-browser",
                "table_name": "browser_orders",
                "resource_key": "browser_orders",
                "required": True,
                "collection_driver": "browser_playbook_remote",
                "dataset_source_type": "collection_records",
                "dataset_name": "浏览器订单",
            }
        ]
        ctx["plan_input_source"] = "dataset_bindings:execution_run_plan"
        return {"recon_ctx": ctx}

    async def fake_trigger_collection(*args: object, **kwargs: object) -> dict[str, object]:
        return {
            "success": True,
            "queued": True,
            "collection_driver": "browser_playbook_remote",
            "job": {"id": "sync-job-browser", "status": "queued"},
            "message": "浏览器采集任务已创建，等待 Production Push Dispatcher 执行",
        }

    async def stale_collection_lookup(*args: object, **kwargs: object) -> dict[str, object]:
        raise AssertionError("browser queued collection should not probe stale collection records")

    async def stale_sync_job_poll(*args: object, **kwargs: object) -> dict[str, object]:
        raise AssertionError("browser queued collection should not wait for sync job completion")

    monkeypatch.setattr(routers, "load_run_plan_node", fake_load_run_plan_node)
    monkeypatch.setattr(routers, "validate_run_plan_node", fake_validate_noop)
    monkeypatch.setattr(routers, "load_scheme_node", fake_load_scheme_node)
    monkeypatch.setattr(routers, "validate_scheme_rules_node", fake_validate_noop)
    monkeypatch.setattr(routers, "resolve_plan_inputs_node", fake_resolve_inputs_node)
    monkeypatch.setattr(auto_run_service, "run_auto_scheme_run_graph", routers.run_auto_scheme_run_graph)
    monkeypatch.setattr(nodes, "data_source_trigger_dataset_collection", fake_trigger_collection)
    monkeypatch.setattr(nodes, "data_source_list_collection_records", stale_collection_lookup)
    monkeypatch.setattr(nodes, "data_source_get_sync_job", stale_sync_job_poll)
    monkeypatch.setattr(nodes, "_persist_execution_run", stale_collection_lookup)

    result = await auto_run_service.execute_run_plan_run(
        auth_token="token",
        run_plan_code="plan-browser",
        biz_date="2026-05-20",
        trigger_mode="schedule",
        run_context={},
    )

    assert result["success"] is False
    assert result["status"] == "data_waiting"
    assert result["waiting_datasets"] == [
        {
            "data_source_id": "source-browser",
            "dataset_id": "dataset-browser",
            "resource_key": "browser_orders",
            "biz_date": "2026-05-20",
        }
    ]
    assert result["collection_job_ids"] == ["sync-job-browser"]
