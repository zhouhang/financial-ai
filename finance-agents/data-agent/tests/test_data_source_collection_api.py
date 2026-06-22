from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


DATA_AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(DATA_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(DATA_AGENT_ROOT))

data_source_api = importlib.import_module("graphs.data_source.api")
mcp_client = importlib.import_module("tools.mcp_client")


@pytest.mark.anyio
async def test_trigger_dataset_collection_uses_params_biz_date_before_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_trigger_dataset_collection(*args: object, **kwargs: object) -> dict[str, object]:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return {"success": True}

    monkeypatch.setattr(
        data_source_api,
        "data_source_trigger_dataset_collection",
        fake_trigger_dataset_collection,
    )
    monkeypatch.setattr(data_source_api, "_default_collection_biz_date", lambda: "2026-05-11")

    body = data_source_api.DataSourceDatasetCollectionTriggerRequest(
        resource_key="public.ods_yxst_trd_order_di_o",
        trigger_mode="manual",
        idempotency_key="manual-date-collection:source-1:dataset-1:2026-04-01",
        params={
            "resource_key": "public.ods_yxst_trd_order_di_o",
            "biz_date": "2026-04-01",
            "query": {"resource_key": "public.ods_yxst_trd_order_di_o"},
        },
    )

    result = await data_source_api.trigger_dataset_collection(
        "source-1",
        "dataset-1",
        body,
        authorization="Bearer token",
    )

    assert result["success"] is True
    kwargs = captured["kwargs"]
    assert kwargs["biz_date"] == "2026-04-01"
    assert kwargs["idempotency_key"] == "manual-date-collection:source-1:dataset-1:2026-04-01"


@pytest.mark.anyio
async def test_mcp_client_forwards_dataset_collection_idempotency_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_call_mcp_tool(tool_name: str, payload: dict[str, object]) -> dict[str, object]:
        captured["tool_name"] = tool_name
        captured["payload"] = payload
        return {"success": True}

    monkeypatch.setattr(mcp_client, "call_mcp_tool", fake_call_mcp_tool)

    result = await mcp_client.data_source_trigger_dataset_collection(
        "token",
        "source-1",
        dataset_id="dataset-1",
        resource_key="public.ods_yxst_trd_order_di_o",
        biz_date="2026-04-01",
        idempotency_key="manual-date-collection:source-1:dataset-1:2026-04-01",
        trigger_mode="manual",
        params={"biz_date": "2026-04-01"},
    )

    assert result["success"] is True
    assert captured["tool_name"] == "data_source_trigger_dataset_collection"
    payload = captured["payload"]
    assert payload["biz_date"] == "2026-04-01"
    assert payload["idempotency_key"] == "manual-date-collection:source-1:dataset-1:2026-04-01"


@pytest.mark.anyio
async def test_mcp_client_forwards_execution_run_started_date_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_call_mcp_tool(tool_name: str, payload: dict[str, object]) -> dict[str, object]:
        captured["tool_name"] = tool_name
        captured["payload"] = payload
        return {"success": True, "runs": [], "total": 0}

    monkeypatch.setattr(mcp_client, "call_mcp_tool", fake_call_mcp_tool)

    result = await mcp_client.execution_run_list(
        "token",
        scheme_code="scheme-001",
        plan_code="plan-001",
        started_at_from="2026-06-01",
        started_at_to="2026-06-22",
        limit=20,
        offset=40,
    )

    assert result["success"] is True
    assert captured["tool_name"] == "execution_run_list"
    payload = captured["payload"]
    assert payload["scheme_code"] == "scheme-001"
    assert payload["plan_code"] == "plan-001"
    assert payload["started_at_from"] == "2026-06-01"
    assert payload["started_at_to"] == "2026-06-22"
    assert payload["limit"] == 20
    assert payload["offset"] == 40


def test_mcp_session_http_clients_ignore_proxy_environment() -> None:
    client = mcp_client._new_mcp_async_client(mcp_client._HTTP_TIMEOUT)
    try:
        assert client.trust_env is False
    finally:
        import anyio

        anyio.run(client.aclose)


@pytest.mark.anyio
async def test_preview_api_forwards_resource_key_and_dataset_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_preview(*args: object, **kwargs: object) -> dict[str, object]:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return {"success": True, "rows": [{"id": 1}], "count": 1}

    monkeypatch.setattr(data_source_api, "data_source_preview", fake_preview)

    body = data_source_api.DataSourcePreviewRequest(
        limit=10,
        resource_key="public.orders",
        dataset_id="dataset-1",
    )
    result = await data_source_api.preview_data_source(
        "source-db-1",
        body,
        authorization="Bearer token",
    )

    assert result.rows == [{"id": 1}]
    assert captured["kwargs"]["resource_key"] == "public.orders"
    assert captured["kwargs"]["dataset_id"] == "dataset-1"


@pytest.mark.anyio
async def test_dataset_detail_api_forwards_to_mcp_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_detail(*args: object, **kwargs: object) -> dict[str, object]:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return {
            "success": True,
            "source_id": "source-db-1",
            "resource_key": "public.orders",
            "dataset": {"id": "dataset-1"},
            "field_groups": [],
            "preview_sample": {"rows": [{"id": 1}]},
            "rows": [{"id": 1}],
            "sample_limit": 10,
            "row_count": 1,
            "message": "已获取数据集详情",
        }

    monkeypatch.setattr(data_source_api, "data_source_get_dataset_detail", fake_detail)

    result = await data_source_api.get_dataset_detail(
        "source-db-1",
        "dataset-1",
        resource_key="public.orders",
        sample_limit=10,
        refresh=False,
        authorization="Bearer token",
    )

    assert result.rows == [{"id": 1}]
    assert result.preview_sample == {"rows": [{"id": 1}]}
    assert captured["kwargs"]["resource_key"] == "public.orders"
    assert captured["kwargs"]["sample_limit"] == 10


@pytest.mark.anyio
async def test_mcp_client_preview_forwards_resource_key_and_dataset_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_call_mcp_tool(tool_name: str, payload: dict[str, object]) -> dict[str, object]:
        captured["tool_name"] = tool_name
        captured["payload"] = payload
        return {"success": True, "rows": []}

    monkeypatch.setattr(mcp_client, "call_mcp_tool", fake_call_mcp_tool)

    result = await mcp_client.data_source_preview(
        "token",
        "source-db-1",
        resource_key="public.orders",
        dataset_id="dataset-1",
        limit=10,
    )

    assert result["success"] is True
    assert captured["tool_name"] == "data_source_preview"
    assert captured["payload"]["resource_key"] == "public.orders"
    assert captured["payload"]["dataset_id"] == "dataset-1"
