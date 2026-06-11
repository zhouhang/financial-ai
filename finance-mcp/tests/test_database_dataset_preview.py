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


def test_dataset_detail_tool_is_registered_and_routed():
    tool_names = {tool.name for tool in data_sources.create_tools()}
    assert "data_source_get_dataset_detail" in tool_names
    assert "data_source_get_dataset_detail" in unified_mcp_server._DATA_SOURCE_TOOL_NAMES
