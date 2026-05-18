from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from tools import data_sources


def _dataset_row() -> dict[str, Any]:
    return {
        "id": "dataset-1",
        "dataset_code": "orders",
        "resource_key": "public.orders",
        "extract_config": {
            "storage": "dataset_collection_records",
            "collection_driver": "db_query",
            "key_fields": ["order_no"],
        },
        "meta": {
            "catalog_profile": {
                "collection_config": {
                    "mode": "date_field",
                    "date_field": "order_finish_time",
                    "date_format": "native",
                }
            }
        },
        "sync_strategy": {},
    }


def _base_kwargs() -> dict[str, Any]:
    return {
        "company_id": "company-1",
        "source_id": "source-1",
        "dataset_id": "dataset-1",
        "dataset_code": "",
        "resource_key": "public.orders",
        "trigger_mode": "manual",
        "idempotency_key": "",
        "background": False,
        "params": {"biz_date": "2026-05-17"},
        "passthrough_arguments": {},
    }


def _install_common(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(data_sources, "_resolve_dataset_row", lambda **kwargs: _dataset_row())
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_latest_source_dataset_checkpoint",
        lambda **kwargs: {},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda company_id, data_source_id: {
            "id": data_source_id,
            "company_id": company_id,
            "source_kind": "database",
            "provider_code": "postgresql",
            "status": "active",
            "is_enabled": True,
        },
    )
    monkeypatch.setattr(
        data_sources,
        "_load_runtime_source",
        lambda source_row, include_secret=False: {
            "source_kind": "database",
            "provider_code": "postgresql",
        },
    )


@pytest.mark.anyio
async def test_trigger_dataset_collection_reuses_recent_success_within_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_common(monkeypatch)
    recent_job = {
        "id": "job-recent-success",
        "company_id": "company-1",
        "data_source_id": "source-1",
        "resource_key": "public.orders",
        "job_status": "success",
    }

    monkeypatch.setattr(
        data_sources.auth_db,
        "create_or_reuse_dataset_collection_sync_job",
        lambda **kwargs: {
            "job": recent_job,
            "reused": True,
            "reuse_reason": "recent_success_ttl",
        },
    )

    monkeypatch.setattr(
        data_sources.auth_db,
        "create_unified_sync_job_attempt",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("recent success should not create attempt")),
    )

    result = await data_sources._trigger_dataset_collection_resolved(**_base_kwargs())

    assert result["success"] is True
    assert result["reused"] is True
    assert result["reuse_reason"] == "recent_success_ttl"
    assert result["job"]["id"] == "job-recent-success"
    assert result["dataset_id"] == "dataset-1"
    assert result["biz_date"] == "2026-05-17"


@pytest.mark.anyio
async def test_trigger_dataset_collection_waits_for_inflight_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_common(monkeypatch)
    calls: dict[str, Any] = {"sleep": 0}
    running_job = {
        "id": "job-running",
        "company_id": "company-1",
        "data_source_id": "source-1",
        "resource_key": "public.orders",
        "job_status": "running",
    }
    completed_job = {**running_job, "job_status": "success"}
    polled_jobs = [running_job, completed_job]

    monkeypatch.setattr(
        data_sources.auth_db,
        "create_or_reuse_dataset_collection_sync_job",
        lambda **kwargs: {
            "job": running_job,
            "reused": True,
            "reuse_reason": "inflight",
        },
    )

    def fake_get_job(sync_job_id: str) -> dict[str, Any]:
        assert sync_job_id == "job-running"
        return polled_jobs.pop(0)

    async def fake_sleep(seconds: float) -> None:
        calls["sleep"] += 1

    monkeypatch.setattr(data_sources.auth_db, "get_unified_sync_job_by_id", fake_get_job)
    monkeypatch.setattr(data_sources.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(
        data_sources.auth_db,
        "create_unified_sync_job_attempt",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("inflight reuse should not create attempt")),
    )

    result = await data_sources._trigger_dataset_collection_resolved(**_base_kwargs())

    assert result["success"] is True
    assert result["reused"] is True
    assert result["reuse_reason"] == "inflight_completed"
    assert result["job"]["id"] == "job-running"
    assert result["job"]["job_status"] == "success"
    assert calls["sleep"] == 1
