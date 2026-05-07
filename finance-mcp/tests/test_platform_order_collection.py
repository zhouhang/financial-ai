from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from tools import data_sources


def _platform_order_dataset(**overrides: Any) -> dict[str, Any]:
    dataset = {
        "id": "dataset-1",
        "data_source_id": "source-1",
        "dataset_code": "taobao_order_lines_shop_1",
        "resource_key": "taobao_order_lines:shop-1",
        "extract_config": {
            "storage": "platform_order_lines",
            "platform_code": "taobao",
            "shop_connection_id": "shop-1",
            "external_shop_id": "seller-1",
            "date_field": "biz_date",
        },
        "sync_strategy": {
            "mode": "full_then_incremental",
            "lookback_minutes": 10,
            "page_size": 100,
        },
        "schema_summary": {"storage": "platform_order_lines"},
        "meta": {"shop_name": "旗舰店"},
    }
    dataset.update(overrides)
    return dataset


def test_dataset_uses_platform_order_lines_detects_storage_markers() -> None:
    assert data_sources._dataset_uses_platform_order_lines(_platform_order_dataset())
    assert data_sources._dataset_uses_platform_order_lines(
        {"schema_summary": {"source": "platform_order_lines"}}
    )
    assert not data_sources._dataset_uses_platform_order_lines(
        {"extract_config": {"storage": "dataset_collection_records"}}
    )


def test_resolve_taobao_collection_window_uses_checkpoint_for_incremental() -> None:
    window = data_sources._resolve_taobao_collection_window(
        dataset_row=_platform_order_dataset(),
        params={},
        checkpoint_before={"last_window_end": "2026-05-06T12:00:00+08:00"},
        now=datetime(2026, 5, 6, 13, 0, tzinfo=timezone.utc),
    )

    assert window["mode"] == "incremental"
    assert window["window_start"] == "2026-05-06 11:50:00"
    assert window["window_end"] == "2026-05-06 21:00:00"


def test_resolve_taobao_collection_window_force_initial_uses_biz_date() -> None:
    window = data_sources._resolve_taobao_collection_window(
        dataset_row=_platform_order_dataset(),
        params={"biz_date": "2026-05-06", "force_mode": "initial"},
        checkpoint_before={"last_window_end": "2026-05-07T12:00:00+08:00"},
        now=datetime(2026, 5, 7, 0, 0, tzinfo=timezone.utc),
    )

    assert window == {
        "mode": "initial",
        "window_start": "2026-05-06 00:00:00",
        "window_end": "2026-05-06 23:59:59",
        "biz_date": "2026-05-06",
    }


@pytest.mark.anyio
async def test_trigger_dataset_collection_for_company_does_not_require_auth_token(
    monkeypatch,
) -> None:
    calls: dict[str, Any] = {}

    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_dataset_by_id",
        lambda company_id, dataset_id: _platform_order_dataset(),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_latest_source_dataset_checkpoint",
        lambda **kwargs: {"last_window_end": "2026-05-06T12:00:00+08:00"},
    )

    async def fake_trigger_sync(
        arguments: dict[str, Any],
        *,
        trusted_company_id: str = "",
    ) -> dict[str, Any]:
        calls["arguments"] = arguments
        calls["trusted_company_id"] = trusted_company_id
        return {"success": True, "job": {"id": "job-1"}}

    monkeypatch.setattr(data_sources, "_handle_data_source_trigger_sync", fake_trigger_sync)

    result = await data_sources.trigger_dataset_collection_for_company(
        company_id="company-1",
        source_id="source-1",
        dataset_id="dataset-1",
        resource_key="taobao_order_lines:shop-1",
        idempotency_key="caller-key",
        params={"biz_date": "2026-05-06", "force_mode": "initial"},
    )

    assert result["success"] is True
    assert calls["trusted_company_id"] == "company-1"
    assert calls["arguments"]["idempotency_key"] == "caller-key"
    assert "auth_token" not in calls["arguments"]
    assert calls["arguments"]["params"]["checkpoint_before"] == {
        "last_window_end": "2026-05-06T12:00:00+08:00"
    }


@pytest.mark.anyio
async def test_execute_sync_job_routes_platform_order_rows_to_order_line_storage(
    monkeypatch,
) -> None:
    calls: dict[str, Any] = {"upsert_dataset_collection_records": 0}

    monkeypatch.setattr(
        data_sources,
        "_run_platform_order_collection",
        lambda **kwargs: {
            "success": True,
            "healthy": True,
            "rows": [{"tid": "T1", "oid": "O1"}],
            "collection_summary": {
                "input_count": 1,
                "upserted_count": 1,
                "inserted_count": 1,
                "updated_count": 0,
                "dataset_id": "dataset-1",
                "dataset_code": "taobao_order_lines_shop_1",
                "biz_date": "2026-05-06",
                "record_count": 1,
            },
            "next_checkpoint": {"last_window_end": "2026-05-06 23:59:59"},
            "message": "平台订单采集成功",
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "upsert_dataset_collection_records",
        lambda **kwargs: calls.__setitem__("upsert_dataset_collection_records", 1),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "update_unified_sync_job_attempt",
        lambda **kwargs: calls.setdefault("attempt", kwargs),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "update_unified_sync_job_status",
        lambda **kwargs: {"id": kwargs["sync_job_id"], "job_status": kwargs["job_status"]},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "create_unified_data_source_event",
        lambda **kwargs: calls.setdefault("event", kwargs),
    )
    monkeypatch.setattr(data_sources.auth_db, "update_unified_data_source_health", lambda **kwargs: None)
    monkeypatch.setattr(data_sources, "_update_dataset_health_by_resource", lambda **kwargs: None)

    result = await data_sources._execute_sync_job(
        company_id="company-1",
        source_id="source-1",
        resource_key="taobao_order_lines:shop-1",
        runtime_source={"source_kind": "platform_oauth", "provider_code": "taobao"},
        arguments={
            "params": {
                "dataset_id": "dataset-1",
                "dataset_code": "taobao_order_lines_shop_1",
                "collection_config": {"storage": "platform_order_lines"},
                "platform_order_collection": {"mode": "initial"},
            }
        },
        job={"id": "job-1", "current_attempt": 1},
        attempt={"id": "attempt-1"},
        checkpoint_before={},
        window_start="2026-05-06 00:00:00",
        window_end="2026-05-06 23:59:59",
    )

    assert result["success"] is True
    assert calls["upsert_dataset_collection_records"] == 0
    assert result["collection_summary"]["upserted_count"] == 1
    assert calls["attempt"]["metrics"]["collection_upserted"] == 1


@pytest.mark.anyio
async def test_run_platform_order_collection_uses_connector_and_upserts_lines(
    monkeypatch,
) -> None:
    connector_calls: dict[str, Any] = {}

    monkeypatch.setattr(
        data_sources.auth_db,
        "get_platform_app",
        lambda **kwargs: {
            "id": "app-1",
            "company_id": kwargs["company_id"],
            "platform_code": kwargs["platform_code"],
            "app_name": "Taobao",
            "app_key": "key",
            "app_secret": "secret",
            "app_type": "system",
            "auth_base_url": "",
            "token_url": "",
            "refresh_url": "",
            "scopes_config": [],
            "extra": {"mode": "mock"},
            "status": "active",
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_shop_connection_by_id",
        lambda shop_connection_id: {
            "id": shop_connection_id,
            "company_id": "company-1",
            "platform_code": "taobao",
            "external_shop_id": "seller-1",
            "external_shop_name": "旗舰店",
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_current_shop_authorization",
        lambda **kwargs: {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "auth_status": "authorized",
            "scope_text": "trade",
            "raw_auth_payload": {"source": "test"},
        },
    )

    class FakeConnector:
        def __init__(self, app_config: Any):
            self.app_config = app_config

        def fetch_order_lines(self, **kwargs: Any) -> dict[str, Any]:
            connector_calls["fetch_order_lines"] = kwargs
            return {
                "success": True,
                "healthy": True,
                "rows": [{"tid": "T1", "oid": "O1", "biz_date": "2026-05-06"}],
            }

    monkeypatch.setattr(data_sources, "build_platform_connector", lambda app_config: FakeConnector(app_config))
    monkeypatch.setattr(
        data_sources.auth_db,
        "upsert_platform_order_lines",
        lambda **kwargs: {"input_count": len(kwargs["rows"]), "upserted_count": len(kwargs["rows"])},
    )

    result = data_sources._run_platform_order_collection(
        company_id="company-1",
        source_id="source-1",
        dataset_id="dataset-1",
        dataset_code="taobao_order_lines_shop_1",
        resource_key="taobao_order_lines:shop-1",
        collection_config=_platform_order_dataset()["extract_config"],
        params={
            "platform_order_collection": {
                "mode": "initial",
                "window_start": "2026-05-06 00:00:00",
                "window_end": "2026-05-06 23:59:59",
                "biz_date": "2026-05-06",
            }
        },
    )

    assert result["success"] is True
    assert result["collection_summary"]["upserted_count"] == 1
    assert connector_calls["fetch_order_lines"]["company_id"] == "company-1"
    assert connector_calls["fetch_order_lines"]["data_source_id"] == "source-1"
    assert connector_calls["fetch_order_lines"]["mode"] == "initial"


@pytest.mark.anyio
async def test_collection_detail_routes_platform_order_dataset_to_order_line_helpers(
    monkeypatch,
) -> None:
    monkeypatch.setattr(data_sources, "_require_user", lambda token: {"company_id": "company-1"})
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda company_id, data_source_id: {"id": data_source_id, "source_kind": "platform_oauth"},
    )
    monkeypatch.setattr(data_sources, "_resolve_dataset_row", lambda **kwargs: _platform_order_dataset())
    monkeypatch.setattr(data_sources.auth_db, "list_unified_sync_jobs", lambda **kwargs: [])
    monkeypatch.setattr(data_sources, "_enrich_jobs_with_latest_attempts", lambda company_id, jobs: jobs)
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_platform_order_line_stats",
        lambda **kwargs: {"total_count": 2},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_platform_order_lines",
        lambda **kwargs: [{"payload": {"tid": "T1"}}, {"payload": {"tid": "T2"}}],
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_dataset_collection_records",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("wrong storage")),
    )

    result = await data_sources._handle_data_source_get_dataset_collection_detail(
        {
            "auth_token": "token",
            "source_id": "source-1",
            "dataset_id": "dataset-1",
            "sample_limit": 10,
        }
    )

    assert result["success"] is True
    assert result["collection_stats"] == {"total_count": 2}
    assert result["rows"] == [{"tid": "T1"}, {"tid": "T2"}]
