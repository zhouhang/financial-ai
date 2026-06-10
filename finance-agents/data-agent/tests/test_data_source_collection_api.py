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


def test_mcp_session_http_clients_ignore_proxy_environment() -> None:
    client = mcp_client._new_mcp_async_client(mcp_client._HTTP_TIMEOUT)
    try:
        assert client.trust_env is False
    finally:
        import anyio

        anyio.run(client.aclose)
