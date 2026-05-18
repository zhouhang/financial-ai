from __future__ import annotations

import sys
from pathlib import Path

import pytest

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from tools import data_sources


def test_resolve_collection_driver_prefers_explicit_collection_config() -> None:
    source = {"source_kind": "platform_oauth", "provider_code": "alipay"}
    dataset = {
        "extract_config": {"collection_driver": "wrong_driver"},
        "meta": {
            "catalog_profile": {
                "collection_config": {
                    "collection_driver": "alipay_bill_download_import",
                },
            }
        },
    }

    assert data_sources._resolve_collection_driver(source, dataset) == "alipay_bill_download_import"


def test_resolve_collection_driver_keeps_taobao_platform_order_lines_compatibility() -> None:
    source = {"source_kind": "platform_oauth", "provider_code": "taobao"}
    dataset = {
        "extract_config": {
            "storage": "platform_order_lines",
            "platform_code": "taobao",
        },
    }

    assert data_sources._resolve_collection_driver(source, dataset) == "taobao_order_api"


def test_resolve_collection_driver_defaults_database_to_db_query() -> None:
    source = {"source_kind": "database", "provider_code": "postgres"}
    dataset = {"extract_config": {"storage": "dataset_collection_records"}}

    assert data_sources._resolve_collection_driver(source, dataset) == "db_query"


def test_resolve_collection_driver_defaults_alipay_platform_oauth() -> None:
    source = {"source_kind": "platform_oauth", "provider_code": "alipay"}
    dataset = {"extract_config": {"storage": "alipay_bill_lines"}}

    assert data_sources._resolve_collection_driver(source, dataset) == "alipay_bill_download_import"


@pytest.mark.anyio
async def test_execute_sync_job_streams_database_collection_records_in_batches(
    monkeypatch,
) -> None:
    calls: dict[str, object] = {"upserts": []}

    class FakeDatabaseConnector:
        def iter_sync_batches(self, arguments, batch_size: int = 5000):
            calls["batch_size"] = batch_size
            yield [{"order_no": "A001", "amount": "12.30"}]
            yield [{"order_no": "A002", "amount": "45.60"}]

    monkeypatch.setattr(
        data_sources,
        "_resolve_dataset_row",
        lambda **kwargs: {
            "id": "dataset-1",
            "dataset_code": "orders",
            "resource_key": "public.orders",
            "extract_config": {
                "storage": "dataset_collection_records",
                "key_fields": ["order_no"],
            },
            "sync_strategy": {},
            "source_kind": "database",
            "provider_code": "postgresql",
        },
    )
    monkeypatch.setattr(data_sources, "build_connector", lambda source: FakeDatabaseConnector())

    def fake_upsert(**kwargs):
        calls["upserts"].append(kwargs)
        return {
            "input_count": len(kwargs["records"]),
            "upserted_count": len(kwargs["records"]),
            "inserted_count": len(kwargs["records"]),
            "updated_count": 0,
            "unchanged_count": 0,
        }

    monkeypatch.setattr(data_sources.auth_db, "upsert_dataset_collection_records", fake_upsert)
    monkeypatch.setattr(
        data_sources.auth_db,
        "update_unified_sync_job_attempt",
        lambda **kwargs: calls.setdefault("attempt_update", kwargs),
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
    monkeypatch.setattr(
        data_sources.auth_db,
        "update_unified_data_source_health",
        lambda **kwargs: calls.setdefault("source_health", kwargs),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda **kwargs: {"source_kind": "database", "provider_code": "postgresql"},
    )
    monkeypatch.setattr(
        data_sources,
        "_update_dataset_health_by_resource",
        lambda **kwargs: calls.setdefault("dataset_health", kwargs),
    )
    monkeypatch.setattr(
        data_sources,
        "_refresh_platform_dataset_semantic_profile_after_collection",
        lambda **kwargs: calls.setdefault("semantic_refresh", kwargs),
    )

    result = await data_sources._execute_sync_job(
        company_id="company-1",
        source_id="source-1",
        resource_key="public.orders",
        runtime_source={"source_kind": "database", "provider_code": "postgresql"},
        arguments={
            "source_id": "source-1",
            "dataset_id": "dataset-1",
            "resource_key": "public.orders",
            "params": {
                "biz_date": "2026-05-16",
                "dataset_id": "dataset-1",
                "dataset_code": "orders",
                "key_fields": ["order_no"],
                "source_batch_size": 1,
            },
        },
        job={"id": "job-1", "current_attempt": 1},
        attempt={"id": "attempt-1"},
        checkpoint_before={},
        window_start=None,
        window_end=None,
    )

    assert result["success"] is True
    assert calls["batch_size"] == 1
    assert len(calls["upserts"]) == 2
    assert [call["records"][0]["payload"]["order_no"] for call in calls["upserts"]] == [
        "A001",
        "A002",
    ]
    metrics = calls["attempt_update"]["metrics"]
    assert metrics["row_count"] == 2
    assert metrics["collection_input"] == 2
    assert metrics["collection_upserted"] == 2
    assert metrics["collection_batch_count"] == 2
    assert metrics["collection_max_batch_size"] == 1
    assert metrics["collection_streaming"] is True


@pytest.mark.anyio
async def test_execute_sync_job_routes_alipay_to_registered_driver(monkeypatch) -> None:
    calls: dict[str, object] = {}

    monkeypatch.setattr(
        data_sources,
        "_resolve_dataset_row",
        lambda **kwargs: {
            "id": "dataset-alipay-1",
            "dataset_code": "alipay_bill_lines",
            "resource_key": "alipay_bill_lines:merchant-1",
            "extract_config": {
                "storage": "alipay_bill_lines",
                "collection_driver": "alipay_bill_download_import",
                "key_fields": ["trade_no"],
                "date_field": "bill_date",
            },
            "sync_strategy": {},
            "source_kind": "platform_oauth",
            "provider_code": "alipay",
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "update_unified_sync_job_attempt",
        lambda **kwargs: calls.setdefault("attempt_update", kwargs),
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
    monkeypatch.setattr(
        data_sources.auth_db,
        "update_unified_data_source_health",
        lambda **kwargs: calls.setdefault("source_health", kwargs),
    )
    monkeypatch.setattr(
        data_sources,
        "_update_dataset_health_by_resource",
        lambda **kwargs: calls.setdefault("dataset_health", kwargs),
    )

    def fake_driver(**kwargs):
        calls["driver"] = kwargs
        return {
            "success": True,
            "healthy": True,
            "rows": [],
            "collection_summary": {"upserted_count": 1, "storage": "alipay_bill_lines"},
            "message": "支付宝账单采集成功",
        }

    monkeypatch.setattr(data_sources, "_run_alipay_bill_download_import", fake_driver)

    result = await data_sources._execute_sync_job(
        company_id="company-1",
        source_id="source-alipay-1",
        resource_key="alipay_bill_lines:merchant-1",
        runtime_source={"source_kind": "platform_oauth", "provider_code": "alipay"},
        arguments={
            "source_id": "source-alipay-1",
            "dataset_id": "dataset-alipay-1",
            "resource_key": "alipay_bill_lines:merchant-1",
            "params": {"biz_date": "2026-05-06"},
        },
        job={"id": "job-1", "current_attempt": 1},
        attempt={"id": "attempt-1"},
        checkpoint_before={},
        window_start=None,
        window_end=None,
    )

    assert result["success"] is True
    assert result["collection_driver"] == "alipay_bill_download_import"
    driver_call = calls["driver"]
    assert driver_call["company_id"] == "company-1"
    assert driver_call["source_id"] == "source-alipay-1"
    assert driver_call["dataset_id"] == "dataset-alipay-1"
    assert driver_call["resource_key"] == "alipay_bill_lines:merchant-1"
    assert calls["attempt_update"]["metrics"]["collection_driver"] == "alipay_bill_download_import"
    assert calls["event"]["event_payload"]["collection_driver"] == "alipay_bill_download_import"


@pytest.mark.anyio
async def test_execute_sync_job_reports_unavailable_alipay_driver(monkeypatch) -> None:
    calls: dict[str, object] = {}

    monkeypatch.setattr(
        data_sources,
        "_resolve_dataset_row",
        lambda **kwargs: {
            "id": "dataset-alipay-1",
            "dataset_code": "alipay_bill_lines",
            "resource_key": "alipay_bill_lines:merchant-1",
            "extract_config": {
                "collection_driver": "alipay_bill_download_import",
                "key_fields": ["trade_no"],
            },
            "source_kind": "platform_oauth",
            "provider_code": "alipay",
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "update_unified_sync_job_attempt",
        lambda **kwargs: calls.setdefault("attempt_update", kwargs),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "update_unified_sync_job_status",
        lambda **kwargs: calls.setdefault("job_update", kwargs),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "update_unified_data_source_health",
        lambda **kwargs: calls.setdefault("source_health", kwargs),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "create_unified_data_source_event",
        lambda **kwargs: calls.setdefault("event", kwargs),
    )
    monkeypatch.setattr(
        data_sources,
        "_update_dataset_health_by_resource",
        lambda **kwargs: calls.setdefault("dataset_health", kwargs),
    )

    def missing_driver(**kwargs):
        raise NotImplementedError("支付宝采集器尚未注册")

    monkeypatch.setattr(data_sources, "_run_alipay_bill_download_import", missing_driver)

    result = await data_sources._execute_sync_job(
        company_id="company-1",
        source_id="source-alipay-1",
        resource_key="alipay_bill_lines:merchant-1",
        runtime_source={"source_kind": "platform_oauth", "provider_code": "alipay"},
        arguments={
            "source_id": "source-alipay-1",
            "dataset_id": "dataset-alipay-1",
            "resource_key": "alipay_bill_lines:merchant-1",
            "params": {"biz_date": "2026-05-06"},
        },
        job={"id": "job-1", "current_attempt": 1},
        attempt={"id": "attempt-1"},
        checkpoint_before={},
        window_start=None,
        window_end=None,
    )

    assert result["success"] is False
    assert result["collection_driver"] == "alipay_bill_download_import"
    assert "支付宝采集器尚未注册" in result["error"]
    assert calls["attempt_update"]["metrics"]["collection_driver"] == "alipay_bill_download_import"
    assert calls["job_update"]["job_status"] == "failed"
    assert calls["event"]["event_type"] == "sync_failed"
    assert calls["event"]["event_payload"]["collection_driver"] == "alipay_bill_download_import"


@pytest.mark.anyio
async def test_execute_sync_job_records_collection_timing_for_collection_records(
    monkeypatch,
) -> None:
    calls: dict[str, object] = {}

    monkeypatch.setattr(
        data_sources,
        "_resolve_dataset_row",
        lambda **kwargs: {
            "id": "dataset-1",
            "dataset_code": "orders",
            "resource_key": "public.orders",
            "extract_config": {
                "storage": "dataset_collection_records",
                "key_fields": ["order_no"],
            },
            "sync_strategy": {},
            "source_kind": "api",
            "provider_code": "mock_api",
        },
    )
    async def fake_connector_sync(source, arguments):
        return {
            "success": True,
            "healthy": True,
            "rows": [{"order_no": "A001", "amount": "12.30"}],
            "message": "ok",
        }

    monkeypatch.setattr(data_sources, "_run_connector_sync", fake_connector_sync)
    monkeypatch.setattr(
        data_sources.auth_db,
        "upsert_dataset_collection_records",
        lambda **kwargs: {
            "input_count": len(kwargs["records"]),
            "upserted_count": len(kwargs["records"]),
            "inserted_count": 0,
            "updated_count": 0,
            "unchanged_count": len(kwargs["records"]),
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "update_unified_sync_job_attempt",
        lambda **kwargs: calls.setdefault("attempt_update", kwargs),
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
    monkeypatch.setattr(
        data_sources.auth_db,
        "update_unified_data_source_health",
        lambda **kwargs: calls.setdefault("source_health", kwargs),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda **kwargs: {"source_kind": "api", "provider_code": "mock_api"},
    )
    monkeypatch.setattr(
        data_sources,
        "_update_dataset_health_by_resource",
        lambda **kwargs: calls.setdefault("dataset_health", kwargs),
    )
    monkeypatch.setattr(
        data_sources,
        "_refresh_platform_dataset_semantic_profile_after_collection",
        lambda **kwargs: calls.setdefault("semantic_refresh", kwargs),
    )

    result = await data_sources._execute_sync_job(
        company_id="company-1",
        source_id="source-1",
        resource_key="public.orders",
        runtime_source={"source_kind": "api", "provider_code": "mock_api"},
        arguments={
            "source_id": "source-1",
            "dataset_id": "dataset-1",
            "resource_key": "public.orders",
            "params": {
                "biz_date": "2026-05-16",
                "dataset_id": "dataset-1",
                "dataset_code": "orders",
                "key_fields": ["order_no"],
            },
        },
        job={"id": "job-1", "current_attempt": 1},
        attempt={"id": "attempt-1"},
        checkpoint_before={},
        window_start=None,
        window_end=None,
    )

    assert result["success"] is True
    metrics = calls["attempt_update"]["metrics"]
    timing = metrics["collection_timing"]
    assert set(timing) == {
        "total_seconds",
        "connector_sync_seconds",
        "build_collection_records_seconds",
        "data_hash_seconds",
        "upsert_collection_records_seconds",
        "finalize_job_seconds",
    }
    assert all(isinstance(value, float) for value in timing.values())
    assert all(value >= 0 for value in timing.values())
