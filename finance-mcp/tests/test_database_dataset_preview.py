from __future__ import annotations

import sys
from datetime import date, datetime
from decimal import Decimal
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
async def test_preview_refresh_normalizes_cached_rows_to_json_safe_values(monkeypatch):
    updated_meta: dict[str, Any] = {}

    class FakeConnector:
        def preview(self, arguments: dict[str, Any]) -> dict[str, Any]:
            return {
                "success": True,
                "rows": [
                    {
                        "id": 5,
                        "updated_at": datetime(2026, 6, 14, 9, 30, 1),
                        "biz_date": date(2026, 6, 14),
                        "amount": Decimal("123.4500"),
                        "nested": {"settled_at": datetime(2026, 6, 15, 10, 1, 2)},
                    }
                ],
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

    cached_row = updated_meta["preview_sample"]["rows"][0]
    assert result["success"] is True
    assert cached_row["updated_at"] == "2026-06-14T09:30:01"
    assert cached_row["biz_date"] == "2026-06-14"
    assert cached_row["amount"] == "123.4500"
    assert cached_row["nested"]["settled_at"] == "2026-06-15T10:01:02"


@pytest.mark.anyio
async def test_preview_refresh_normalizes_non_finite_floats_to_none(monkeypatch):
    updated_meta: dict[str, Any] = {}

    class FakeConnector:
        def preview(self, arguments: dict[str, Any]) -> dict[str, Any]:
            return {
                "success": True,
                "rows": [{"nan_value": float("nan"), "pos_inf": float("inf"), "neg_inf": float("-inf")}],
                "count": 1,
                "preview_order": {"order": "connector_default", "order_field": ""},
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

    cached_row = updated_meta["preview_sample"]["rows"][0]
    assert result["success"] is True
    assert cached_row == {"nan_value": None, "pos_inf": None, "neg_inf": None}


@pytest.mark.anyio
async def test_dataset_detail_refresh_failure_surfaces_top_level_error(monkeypatch):
    cached_preview_sample = {
        "rows": [{"id": 6, "updated_at": "2026-06-15"}],
        "limit": 10,
        "row_count": 1,
        "resource_key": "public.orders",
        "source": "dataset_discover",
        "order": "date_field_desc",
        "order_field": "updated_at",
    }

    class FakeConnector:
        def preview(self, arguments: dict[str, Any]) -> dict[str, Any]:
            return {
                "success": False,
                "rows": [],
                "error": "query failed",
                "message": "查询失败",
                "preview_order": {"order": "date_field_desc", "order_field": "updated_at"},
            }

    monkeypatch.setattr(data_sources, "_require_user", lambda token: {"company_id": "company-1"})
    monkeypatch.setattr(data_sources.auth_db, "get_unified_data_source_by_id", lambda **kwargs: _source())
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_dataset_by_id",
        lambda **kwargs: _dataset({"preview_sample": cached_preview_sample}),
    )
    monkeypatch.setattr(data_sources, "build_connector", lambda runtime_source: FakeConnector())

    def fake_update_dataset_meta(*, dataset_id: str, meta: dict[str, Any]):
        row = _dataset(meta)
        row["id"] = dataset_id
        return row

    monkeypatch.setattr(data_sources.auth_db, "update_unified_data_source_dataset_meta", fake_update_dataset_meta)

    result = await data_sources._handle_data_source_get_dataset_detail(
        {
            "auth_token": "token",
            "source_id": "source-db-1",
            "dataset_id": "dataset-1",
            "resource_key": "public.orders",
            "sample_limit": 10,
            "refresh": True,
        }
    )

    assert result["success"] is False
    assert result["preview_success"] is False
    assert result["error"] == "query failed"
    assert result["preview_sample"]["error"] == "query failed"
    assert result["rows"] == [{"id": 6, "updated_at": "2026-06-15"}]


@pytest.mark.anyio
async def test_preview_refresh_failure_preserves_cached_rows_in_dataset_meta(monkeypatch):
    updated_meta: dict[str, Any] = {}
    cached_preview_sample = {
        "rows": [{"id": 7, "updated_at": "2026-06-16"}],
        "limit": 10,
        "row_count": 1,
        "fetched_at": "2026-06-16T00:00:00+00:00",
        "resource_key": "public.orders",
        "source": "dataset_discover",
        "order": "date_field_desc",
        "order_field": "updated_at",
    }

    class FakeConnector:
        def preview(self, arguments: dict[str, Any]) -> dict[str, Any]:
            return {
                "success": False,
                "rows": [],
                "error": "query failed",
                "preview_order": {"order": "date_field_desc", "order_field": "updated_at"},
            }

    monkeypatch.setattr(data_sources, "_require_user", lambda token: {"company_id": "company-1"})
    monkeypatch.setattr(data_sources.auth_db, "get_unified_data_source_by_id", lambda **kwargs: _source())
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_dataset_by_id",
        lambda **kwargs: _dataset({"preview_sample": cached_preview_sample}),
    )
    monkeypatch.setattr(data_sources, "build_connector", lambda runtime_source: FakeConnector())

    def fake_update_dataset_meta(*, dataset_id: str, meta: dict[str, Any]):
        updated_meta.update(meta)
        row = _dataset(meta)
        row["id"] = dataset_id
        return row

    monkeypatch.setattr(data_sources.auth_db, "update_unified_data_source_dataset_meta", fake_update_dataset_meta)

    result = await data_sources._handle_data_source_get_dataset_detail(
        {
            "auth_token": "token",
            "source_id": "source-db-1",
            "dataset_id": "dataset-1",
            "resource_key": "public.orders",
            "sample_limit": 10,
            "refresh": True,
        }
    )

    preview_sample = updated_meta["preview_sample"]
    assert result["success"] is False
    assert preview_sample["rows"] == [{"id": 7, "updated_at": "2026-06-16"}]
    assert preview_sample["row_count"] == 1
    assert preview_sample["fetched_at"] == "2026-06-16T00:00:00+00:00"
    assert preview_sample["error"] == "query failed"


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
async def test_dataset_detail_rejects_conflicting_dataset_id_and_resource_key(monkeypatch):
    preview_sample = {
        "rows": [{"id": 8, "updated_at": "2026-06-17"}],
        "limit": 10,
        "row_count": 1,
        "resource_key": "public.orders",
    }

    monkeypatch.setattr(data_sources, "_require_user", lambda token: {"company_id": "company-1"})
    monkeypatch.setattr(data_sources.auth_db, "get_unified_data_source_by_id", lambda **kwargs: _source())
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_dataset_by_id",
        lambda **kwargs: _dataset({"preview_sample": preview_sample}),
    )

    result = await data_sources._handle_data_source_get_dataset_detail(
        {
            "auth_token": "token",
            "source_id": "source-db-1",
            "dataset_id": "dataset-1",
            "resource_key": "public.other_orders",
        }
    )

    assert result["success"] is False
    assert result["error"] == "数据集标识不一致"


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


@pytest.mark.anyio
async def test_discover_datasets_caps_database_preview_refresh(monkeypatch):
    upserted_rows: list[dict[str, Any]] = []
    refreshed_keys: list[str] = []

    class FakeConnector:
        capabilities: list[str] = []

        def discover_datasets(self, arguments: dict[str, Any]) -> dict[str, Any]:
            datasets = []
            for index in range(3):
                datasets.append(
                    {
                        "dataset_code": f"public_orders_{index}",
                        "dataset_name": f"Orders {index}",
                        "resource_key": f"public.orders_{index}",
                        "dataset_kind": "table",
                        "origin_type": "discovered",
                        "extract_config": {"schema": "public", "table": f"orders_{index}"},
                        "schema_summary": {"fields": [{"name": "id"}]},
                        "sync_strategy": {},
                        "status": "active",
                        "is_enabled": True,
                        "health_status": "healthy",
                        "meta": {},
                    }
                )
            return {"success": True, "datasets": datasets}

    def fake_upsert_dataset(**kwargs):
        row = _dataset(dict(kwargs.get("meta") or {}))
        row["id"] = f"dataset-{len(upserted_rows)}"
        row["dataset_code"] = kwargs["dataset_code"]
        row["dataset_name"] = kwargs["dataset_name"]
        row["resource_key"] = kwargs["resource_key"]
        row["extract_config"] = dict(kwargs.get("extract_config") or {})
        row["schema_summary"] = dict(kwargs.get("schema_summary") or {})
        row["sync_strategy"] = dict(kwargs.get("sync_strategy") or {})
        upserted_rows.append(row)
        return row

    def fake_preview_refresh(source_row, dataset_row, arguments, limit, source):
        refreshed_keys.append(dataset_row["resource_key"])
        return {"rows": [], "resource_key": dataset_row["resource_key"]}

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
    monkeypatch.setattr(data_sources, "_refresh_database_preview_sample", fake_preview_refresh)

    result = await data_sources._handle_data_source_discover_datasets(
        {
            "auth_token": "token",
            "source_id": "source-db-1",
            "persist": True,
            "preview_refresh_limit": 2,
        }
    )

    assert result["success"] is True
    assert result["dataset_count"] == 3
    assert len(upserted_rows) == 3
    assert refreshed_keys == ["public.orders_0", "public.orders_1"]


@pytest.mark.anyio
async def test_discover_datasets_preserves_cached_preview_when_warmup_skipped(monkeypatch):
    existing_preview_sample = {
        "rows": [{"id": 9, "updated_at": "2026-06-18"}],
        "limit": 10,
        "row_count": 1,
        "resource_key": "public.orders",
        "source": "dataset_discover",
    }
    upserted_meta: dict[str, Any] = {}
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
            }

    def fake_upsert_dataset(**kwargs):
        upserted_meta.update(dict(kwargs.get("meta") or {}))
        row = _dataset(upserted_meta)
        row["dataset_code"] = kwargs["dataset_code"]
        row["resource_key"] = kwargs["resource_key"]
        upserted_rows.append(row)
        return row

    preview_refresh_calls = 0

    def fake_preview_refresh(*args, **kwargs):
        nonlocal preview_refresh_calls
        preview_refresh_calls += 1
        return {"rows": [], "resource_key": "public.orders"}

    monkeypatch.setattr(data_sources, "_require_user", lambda token: {"company_id": "company-1"})
    monkeypatch.setattr(data_sources.auth_db, "get_unified_data_source_by_id", lambda **kwargs: _source())
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_dataset_by_source_resource",
        lambda **kwargs: _dataset({"preview_sample": existing_preview_sample}),
    )
    monkeypatch.setattr(data_sources, "_load_runtime_source", lambda source_row, include_secret: dict(source_row))
    monkeypatch.setattr(data_sources, "build_connector", lambda runtime_source: FakeConnector())
    monkeypatch.setattr(data_sources.auth_db, "upsert_unified_data_source_dataset", fake_upsert_dataset)
    monkeypatch.setattr(data_sources.auth_db, "list_unified_data_source_datasets", lambda **kwargs: list(upserted_rows))
    monkeypatch.setattr(data_sources.auth_db, "update_unified_data_source_health", lambda **kwargs: _source())
    monkeypatch.setattr(data_sources, "_update_source_meta", lambda source_row, meta_updates: source_row)
    monkeypatch.setattr(data_sources, "_build_data_source_view", lambda source_row, datasets: {"id": source_row["id"]})
    monkeypatch.setattr(data_sources.auth_db, "create_unified_data_source_event", lambda **kwargs: None)
    monkeypatch.setattr(data_sources, "_refresh_database_preview_sample", fake_preview_refresh)

    result = await data_sources._handle_data_source_discover_datasets(
        {
            "auth_token": "token",
            "source_id": "source-db-1",
            "persist": True,
            "preview_refresh_limit": 0,
        }
    )

    assert result["success"] is True
    assert preview_refresh_calls == 0
    assert upserted_meta["preview_sample"] == existing_preview_sample


@pytest.mark.anyio
async def test_preview_returns_cached_empty_preview_without_live_connector(monkeypatch):
    preview_sample = {
        "rows": [],
        "limit": 10,
        "row_count": 0,
        "resource_key": "public.orders",
        "source": "data_source_preview",
        "order": "date_field_desc",
        "order_field": "updated_at",
        "fetched_at": "2026-06-19T00:00:00+00:00",
    }

    def fail_build_connector(runtime_source):
        raise AssertionError("cached empty preview should not call live connector")

    monkeypatch.setattr(data_sources, "_require_user", lambda token: {"company_id": "company-1"})
    monkeypatch.setattr(data_sources.auth_db, "get_unified_data_source_by_id", lambda **kwargs: _source())
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_dataset_by_id",
        lambda **kwargs: _dataset({"preview_sample": preview_sample}),
    )
    monkeypatch.setattr(data_sources, "build_connector", fail_build_connector)

    result = await data_sources._handle_data_source_preview(
        {
            "auth_token": "token",
            "source_id": "source-db-1",
            "dataset_id": "dataset-1",
            "resource_key": "public.orders",
            "limit": 10,
        }
    )

    assert result["success"] is True
    assert result["rows"] == []
    assert result["preview_sample"] == preview_sample


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


@pytest.mark.anyio
async def test_dataset_candidates_expose_preview_sample(monkeypatch):
    """向导候选接口必须透出 preview_sample,否则前端'选中即显缓存行'是死路径。"""
    preview_sample = {
        "rows": [{"id": 7, "updated_at": "2026-06-11"}],
        "limit": 10,
        "row_count": 1,
        "resource_key": "public.orders",
        "order": "date_field_desc",
        "order_field": "updated_at",
    }
    row = _dataset({"preview_sample": preview_sample})
    row.update({"publish_status": "published", "status": "active", "is_enabled": True})

    monkeypatch.setattr(data_sources, "_require_user", lambda token: {"company_id": "company-1"})
    monkeypatch.setattr(
        data_sources,
        "_query_datasets_with_compat",
        lambda **kwargs: {"total": 1, "items": [row]},
    )

    result = await data_sources._handle_data_source_list_dataset_candidates(
        {"auth_token": "token", "keyword": "orders", "page": 1, "page_size": 10}
    )

    assert result["success"] is True
    assert result["candidates"], "应返回候选"
    got = result["candidates"][0].get("preview_sample") or {}
    assert got.get("rows") == [{"id": 7, "updated_at": "2026-06-11"}]
