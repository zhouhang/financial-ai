from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

MCP_ROOT = Path(__file__).resolve().parents[1]
if str(MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_ROOT))

import unified_mcp_server
from tools import data_sources


def _source(source_id: str = "source-db-1") -> dict[str, Any]:
    return {
        "id": source_id,
        "company_id": "company-1",
        "source_kind": "database",
        "provider_code": "postgresql",
        "config": {
            "connection_config": {
                "db_type": "postgresql",
                "host": "localhost",
                "port": 5432,
                "database": "tally",
                "username": "user",
                "password": "pass",
            },
        },
        "meta": {},
    }


def _dataset(meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": "dataset-1",
        "data_source_id": "source-db-1",
        "dataset_code": "public_orders",
        "dataset_name": "Orders",
        "resource_key": "public.orders",
        "dataset_kind": "table",
        "origin_type": "discovered",
        "extract_config": {"schema": "public", "table": "orders"},
        "schema_summary": {"fields": [{"name": "id"}, {"name": "updated_at"}]},
        "sync_strategy": {},
        "status": "active",
        "is_enabled": True,
        "health_status": "healthy",
        "meta": dict(meta or {}),
    }


@pytest.mark.anyio
async def test_dataset_detail_returns_cached_preview_without_collection_jobs(monkeypatch):
    preview_sample = {
        "rows": [{"id": 2, "updated_at": "2026-06-11"}],
        "limit": 10,
        "row_count": 1,
        "resource_key": "public.orders",
        "source": "dataset_discover",
        "order": "date_field_desc",
        "order_field": "updated_at",
    }

    monkeypatch.setattr(data_sources, "_require_user", lambda token: {"company_id": "company-1"})
    monkeypatch.setattr(data_sources.auth_db, "get_unified_data_source_by_id", lambda **kwargs: _source())
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_dataset_by_id",
        lambda company_id, dataset_id: _dataset({"preview_sample": preview_sample}),
    )

    result = await data_sources._handle_data_source_get_dataset_detail(
        {
            "auth_token": "token",
            "source_id": "source-db-1",
            "dataset_id": "dataset-1",
            "resource_key": "public.orders",
            "sample_limit": 10,
        }
    )

    assert result["success"] is True
    assert result["rows"] == [{"id": 2, "updated_at": "2026-06-11"}]
    assert result["preview_sample"]["order_field"] == "updated_at"
    assert "jobs" not in result
    assert "collection_status" not in result


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("selector_key", "selector_value"),
    [
        ("resource_key", "public.orders"),
        ("dataset_code", "public_orders"),
    ],
)
async def test_dataset_detail_returns_cached_preview_by_non_id_selector(
    monkeypatch,
    selector_key: str,
    selector_value: str,
):
    preview_sample = {
        "rows": [{"id": 4, "updated_at": "2026-06-13"}],
        "limit": 10,
        "row_count": 1,
        "resource_key": "public.orders",
        "source": "dataset_discover",
        "order": "date_field_desc",
        "order_field": "updated_at",
    }

    def fail_id_lookup(**kwargs):
        raise AssertionError("non-id selector must not use dataset_id lookup")

    monkeypatch.setattr(data_sources, "_require_user", lambda token: {"company_id": "company-1"})
    monkeypatch.setattr(data_sources.auth_db, "get_unified_data_source_by_id", lambda **kwargs: _source())
    monkeypatch.setattr(data_sources.auth_db, "get_unified_data_source_dataset_by_id", fail_id_lookup)
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_unified_data_source_datasets",
        lambda **kwargs: [_dataset({"preview_sample": preview_sample})],
    )

    result = await data_sources._handle_data_source_get_dataset_detail(
        {
            "auth_token": "token",
            "source_id": "source-db-1",
            selector_key: selector_value,
            "sample_limit": 10,
        }
    )

    assert result["success"] is True
    assert result["rows"] == [{"id": 4, "updated_at": "2026-06-13"}]
    assert result["preview_sample"]["order_field"] == "updated_at"
    assert "jobs" not in result
    assert "collection_status" not in result


@pytest.mark.anyio
async def test_preview_refresh_updates_dataset_meta_preview_sample(monkeypatch):
    updated_meta: dict[str, Any] = {}

    class FakeConnector:
        def preview(self, arguments: dict[str, Any]) -> dict[str, Any]:
            assert arguments["resource_key"] == "public.orders"
            assert arguments["limit"] == 10
            return {
                "success": True,
                "rows": [{"id": 3, "updated_at": "2026-06-12"}],
                "count": 1,
                "preview_order": {"order": "date_field_desc", "order_field": "updated_at"},
            }

    monkeypatch.setattr(data_sources, "_require_user", lambda token: {"company_id": "company-1"})
    monkeypatch.setattr(data_sources.auth_db, "get_unified_data_source_by_id", lambda **kwargs: _source())
    monkeypatch.setattr(data_sources.auth_db, "get_unified_data_source_dataset_by_id", lambda **kwargs: _dataset())
    monkeypatch.setattr(data_sources, "build_connector", lambda runtime_source: FakeConnector())

    def fake_update_dataset_meta(*, dataset_id: str, meta: dict[str, Any]):
        updated_meta.update(meta)
        row = _dataset(meta)
        row["id"] = dataset_id
        return row

    monkeypatch.setattr(data_sources.auth_db, "update_unified_data_source_dataset_meta", fake_update_dataset_meta)

    result = await data_sources._handle_data_source_preview(
        {
            "auth_token": "token",
            "source_id": "source-db-1",
            "dataset_id": "dataset-1",
            "resource_key": "public.orders",
            "limit": 10,
            "refresh": True,
        }
    )

    assert result["success"] is True
    assert result["rows"] == [{"id": 3, "updated_at": "2026-06-12"}]
    assert updated_meta["preview_sample"]["rows"] == [{"id": 3, "updated_at": "2026-06-12"}]
    assert updated_meta["preview_sample"]["order_field"] == "updated_at"


@pytest.mark.anyio
async def test_dataset_detail_requires_dataset_identifier(monkeypatch):
    def fail_list_fallback(**kwargs):
        raise AssertionError("dataset detail must not fall back to the first dataset")

    monkeypatch.setattr(data_sources, "_require_user", lambda token: {"company_id": "company-1"})
    monkeypatch.setattr(data_sources.auth_db, "get_unified_data_source_by_id", lambda **kwargs: _source())
    monkeypatch.setattr(data_sources.auth_db, "list_unified_data_source_datasets", fail_list_fallback)

    result = await data_sources._handle_data_source_get_dataset_detail(
        {
            "auth_token": "token",
            "source_id": "source-db-1",
        }
    )

    assert result["success"] is False
    assert "数据集标识" in result["error"]


@pytest.mark.anyio
async def test_dataset_detail_missing_dataset_id_does_not_fall_back(monkeypatch):
    def fail_list_fallback(**kwargs):
        raise AssertionError("missing dataset_id must not fall back to dataset list")

    monkeypatch.setattr(data_sources, "_require_user", lambda token: {"company_id": "company-1"})
    monkeypatch.setattr(data_sources.auth_db, "get_unified_data_source_by_id", lambda **kwargs: _source())
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_dataset_by_id",
        lambda company_id, dataset_id: None,
    )
    monkeypatch.setattr(data_sources.auth_db, "list_unified_data_source_datasets", fail_list_fallback)

    result = await data_sources._handle_data_source_get_dataset_detail(
        {
            "auth_token": "token",
            "source_id": "source-db-1",
            "dataset_id": "missing-dataset",
        }
    )

    assert result["success"] is False
    assert result["error"] == "数据集不存在"


@pytest.mark.anyio
async def test_discover_datasets_keeps_success_when_preview_refresh_fails(monkeypatch):
    upserted_rows: list[dict[str, Any]] = []

    class FakeConnector:
        capabilities: list[str] = []

        def discover_datasets(self, arguments: dict[str, Any]) -> dict[str, Any]:
            return {
                "success": True,
                "datasets": [
                    {
                        "dataset_code": "public_orders",
                        "dataset_name": "Orders",
                        "resource_key": "public.orders",
                        "dataset_kind": "table",
                        "origin_type": "discovered",
                        "extract_config": {"schema": "public", "table": "orders"},
                        "schema_summary": {"fields": [{"name": "id"}]},
                        "sync_strategy": {},
                        "status": "active",
                        "is_enabled": True,
                        "health_status": "healthy",
                        "meta": {},
                    }
                ],
                "scan_summary": {"table_count": 1},
            }

    def fake_upsert_dataset(**kwargs):
        row = _dataset(dict(kwargs.get("meta") or {}))
        row["dataset_code"] = kwargs["dataset_code"]
        row["dataset_name"] = kwargs["dataset_name"]
        row["resource_key"] = kwargs["resource_key"]
        row["extract_config"] = dict(kwargs.get("extract_config") or {})
        row["schema_summary"] = dict(kwargs.get("schema_summary") or {})
        row["sync_strategy"] = dict(kwargs.get("sync_strategy") or {})
        upserted_rows.append(row)
        return row

    def fail_preview_refresh(*args, **kwargs):
        raise RuntimeError("preview unavailable")

    monkeypatch.setattr(data_sources, "_require_user", lambda token: {"company_id": "company-1"})
    monkeypatch.setattr(data_sources.auth_db, "get_unified_data_source_by_id", lambda **kwargs: _source())
    monkeypatch.setattr(data_sources, "_load_runtime_source", lambda source_row, include_secret: dict(source_row))
    monkeypatch.setattr(data_sources, "build_connector", lambda runtime_source: FakeConnector())
    monkeypatch.setattr(data_sources.auth_db, "upsert_unified_data_source_dataset", fake_upsert_dataset)
    monkeypatch.setattr(data_sources.auth_db, "list_unified_data_source_datasets", lambda **kwargs: list(upserted_rows))
    monkeypatch.setattr(data_sources.auth_db, "update_unified_data_source_health", lambda **kwargs: _source())
    monkeypatch.setattr(data_sources, "_update_source_meta", lambda source_row, meta_updates: source_row)
    monkeypatch.setattr(data_sources, "_build_data_source_view", lambda source_row, datasets: {"id": source_row["id"]})
    monkeypatch.setattr(data_sources.auth_db, "create_unified_data_source_event", lambda **kwargs: None)
    monkeypatch.setattr(data_sources, "_refresh_database_preview_sample", fail_preview_refresh)

    result = await data_sources._handle_data_source_discover_datasets(
        {
            "auth_token": "token",
            "source_id": "source-db-1",
            "persist": True,
        }
    )

    assert result["success"] is True
    assert result["dataset_count"] == 1
    assert result["datasets"][0]["resource_key"] == "public.orders"
    assert len(upserted_rows) == 1


def test_dataset_detail_tool_is_registered_and_routed():
    tools = data_sources.create_tools()
    tool_names = {tool.name for tool in tools}
    assert "data_source_get_dataset_detail" in tool_names
    assert "data_source_get_dataset_detail" in unified_mcp_server._DATA_SOURCE_TOOL_NAMES

    detail_tool = next(tool for tool in tools if tool.name == "data_source_get_dataset_detail")
    properties = detail_tool.inputSchema["properties"]
    required = set(detail_tool.inputSchema.get("required") or [])
    assert {"dataset_id", "dataset_code", "resource_key"} <= set(properties)
    assert "dataset_id" not in required
