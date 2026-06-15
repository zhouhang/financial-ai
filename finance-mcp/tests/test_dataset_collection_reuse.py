from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from tools import data_sources
from auth import db as auth_db


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


def test_create_or_reuse_dataset_collection_treats_handoff_statuses_as_inflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_sql: list[str] = []

    class FakeCursor:
        def __enter__(self) -> "FakeCursor":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def execute(self, sql: str, params: tuple | None = None) -> None:
            captured_sql.append(sql)

        def fetchone(self) -> dict[str, Any]:
            return {
                "id": "job-waiting",
                "company_id": "company-1",
                "data_source_id": "source-1",
                "resource_key": "public.orders",
                "job_status": "waiting_human_verification",
                "request_payload": {"dataset_id": "dataset-1", "biz_date": "2026-05-17"},
            }

    class FakeConn:
        def __enter__(self) -> "FakeConn":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def cursor(self, *args, **kwargs) -> FakeCursor:
            return FakeCursor()

        def commit(self) -> None:
            return None

    class FakeConnManager:
        def __enter__(self) -> FakeConn:
            return FakeConn()

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConnManager())

    result = auth_db.create_or_reuse_dataset_collection_sync_job(
        company_id="company-1",
        data_source_id="source-1",
        trigger_mode="auto",
        resource_key="public.orders",
        dataset_id="dataset-1",
        biz_date="2026-05-17",
        ttl_seconds=600,
    )

    assert result["reused"] is True
    assert result["reuse_reason"] == "inflight"
    sql = "\n".join(captured_sql)
    assert "waiting_human_verification" in sql
    assert "resuming" in sql


def test_find_success_dataset_collection_sync_job_has_no_completed_at_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_sql: list[str] = []
    captured_params: list[tuple] = []

    class FakeCursor:
        def __enter__(self) -> "FakeCursor":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def execute(self, sql: str, params: tuple | None = None) -> None:
            captured_sql.append(sql)
            captured_params.append(params or ())

        def fetchone(self) -> dict[str, Any]:
            return {
                "id": "job-success-old",
                "company_id": "company-1",
                "data_source_id": "source-browser-1",
                "resource_key": "playbook-1@1",
                "job_status": "success",
                "request_payload": {
                    "dataset_id": "dataset-browser-1",
                    "biz_date": "2026-05-25",
                },
            }

    class FakeConn:
        def __enter__(self) -> "FakeConn":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def cursor(self, *args, **kwargs) -> FakeCursor:
            return FakeCursor()

    class FakeConnManager:
        def __enter__(self) -> FakeConn:
            return FakeConn()

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConnManager())

    result = auth_db.find_success_dataset_collection_sync_job(
        company_id="company-1",
        data_source_id="source-browser-1",
        dataset_id="dataset-browser-1",
        resource_key="playbook-1@1",
        biz_date="2026-05-25",
    )

    assert result
    assert result["id"] == "job-success-old"
    sql = "\n".join(captured_sql)
    assert "job_status = 'success'" in sql
    assert "completed_at >=" not in sql
    assert captured_params[-1] == (
        "company-1",
        "source-browser-1",
        "playbook-1@1",
        "dataset-browser-1",
        "2026-05-25",
    )


@pytest.mark.anyio
async def test_browser_trigger_reuses_success_same_biz_date_when_records_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(data_sources, "_require_user", lambda _token: {"company_id": "company-1"})
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda **_kwargs: {
            "id": "source-browser-1",
            "company_id": "company-1",
            "status": "active",
            "is_enabled": True,
            "source_kind": "browser_playbook",
            "provider_code": "browser_playbook",
            "config": {},
            "credential_ref": {},
        },
    )
    monkeypatch.setattr(
        data_sources,
        "_load_runtime_source",
        lambda _row, include_secret=False: {"source_kind": "browser_playbook"},
    )
    monkeypatch.setattr(data_sources.auth_db, "find_inflight_dataset_collection_sync_job", lambda **_kwargs: None)
    monkeypatch.setattr(
        data_sources.auth_db,
        "find_success_dataset_collection_sync_job",
        lambda **_kwargs: {
            "id": "success-job-1",
            "job_status": "success",
            "request_payload": {"dataset_id": "dataset-browser-1", "biz_date": "2026-05-25"},
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_browser_collection_records",
        lambda **_kwargs: [{"id": "record-1"}],
    )

    created = False

    def fake_create_or_reuse_dataset_collection_sync_job(**_kwargs):
        nonlocal created
        created = True
        return {"job": {"id": "new-job-1"}, "reused": False}

    monkeypatch.setattr(
        data_sources.auth_db,
        "create_or_reuse_dataset_collection_sync_job",
        fake_create_or_reuse_dataset_collection_sync_job,
    )

    result = await data_sources._handle_data_source_trigger_sync(
        {
            "auth_token": "token-1",
            "source_id": "source-browser-1",
            "resource_key": "playbook-1@1",
            "params": {
                "collection_driver": data_sources.COLLECTION_DRIVER_BROWSER_PLAYBOOK,
                "dataset_id": "dataset-browser-1",
                "biz_date": "2026-05-25",
            },
        }
    )

    assert result["success"] is True
    assert result["reused"] is True
    assert result["queued"] is False
    assert result["reuse_reason"] == "browser_biz_date_success"
    assert result["job"]["id"] == "success-job-1"
    assert created is False


@pytest.mark.anyio
async def test_browser_trigger_reuses_success_same_biz_date_when_records_are_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(data_sources, "_require_user", lambda _token: {"company_id": "company-1"})
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda **_kwargs: {
            "id": "source-browser-1",
            "company_id": "company-1",
            "status": "active",
            "is_enabled": True,
            "source_kind": "browser_playbook",
            "provider_code": "browser_playbook",
            "config": {},
            "credential_ref": {},
        },
    )
    monkeypatch.setattr(
        data_sources,
        "_load_runtime_source",
        lambda _row, include_secret=False: {"source_kind": "browser_playbook"},
    )
    monkeypatch.setattr(data_sources.auth_db, "find_inflight_dataset_collection_sync_job", lambda **_kwargs: None)
    monkeypatch.setattr(
        data_sources.auth_db,
        "find_success_dataset_collection_sync_job",
        lambda **_kwargs: {
            "id": "success-job-without-records",
            "job_status": "success",
            "request_payload": {"dataset_id": "dataset-browser-1", "biz_date": "2026-05-25"},
        },
    )
    monkeypatch.setattr(data_sources.auth_db, "list_browser_collection_records", lambda **_kwargs: [])

    created = False

    def fake_create_or_reuse_dataset_collection_sync_job(**_kwargs):
        nonlocal created
        created = True
        return {"job": {"id": "new-job-1"}, "reused": False}

    monkeypatch.setattr(
        data_sources.auth_db,
        "create_or_reuse_dataset_collection_sync_job",
        fake_create_or_reuse_dataset_collection_sync_job,
    )
    result = await data_sources._handle_data_source_trigger_sync(
        {
            "auth_token": "token-1",
            "source_id": "source-browser-1",
            "resource_key": "playbook-1@1",
            "params": {
                "collection_driver": data_sources.COLLECTION_DRIVER_BROWSER_PLAYBOOK,
                "dataset_id": "dataset-browser-1",
                "biz_date": "2026-05-25",
                "collection_reuse_ttl_seconds": 600,
            },
        }
    )

    assert result["success"] is True
    assert result["queued"] is False
    assert result["reused"] is True
    assert result["reuse_reason"] == "browser_biz_date_success"
    assert result["job"]["id"] == "success-job-without-records"
    assert created is False


@pytest.mark.anyio
async def test_browser_trigger_leaves_new_job_pending_for_agent_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(data_sources, "_require_user", lambda _token: {"company_id": "company-1"})
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda **_kwargs: {
            "id": "source-browser-1",
            "company_id": "company-1",
            "status": "active",
            "is_enabled": True,
            "source_kind": "browser_playbook",
            "provider_code": "browser_playbook",
            "config": {},
            "credential_ref": {},
        },
    )
    monkeypatch.setattr(
        data_sources,
        "_load_runtime_source",
        lambda _row, include_secret=False: {"source_kind": "browser_playbook"},
    )
    monkeypatch.setattr(data_sources.auth_db, "find_inflight_dataset_collection_sync_job", lambda **_kwargs: None)
    monkeypatch.setattr(data_sources.auth_db, "find_success_dataset_collection_sync_job", lambda **_kwargs: None)

    def fake_create_or_reuse_dataset_collection_sync_job(**kwargs):
        return {
            "job": {
                "id": "new-browser-job",
                "job_status": "pending",
                "request_payload": kwargs.get("request_payload") or {},
            },
            "reused": False,
        }

    monkeypatch.setattr(
        data_sources.auth_db,
        "create_or_reuse_dataset_collection_sync_job",
        fake_create_or_reuse_dataset_collection_sync_job,
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "create_unified_sync_job_attempt",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("browser jobs must stay pending until browser-agent claims them")
        ),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_sync_job_by_id",
        lambda _job_id: {
            "id": "new-browser-job",
            "job_status": "pending",
            "request_payload": {
                "collection_driver": data_sources.COLLECTION_DRIVER_BROWSER_PLAYBOOK,
                "dataset_id": "dataset-browser-1",
                "biz_date": "2026-05-25",
            },
        },
    )

    result = await data_sources._handle_data_source_trigger_sync(
        {
            "auth_token": "token-1",
            "source_id": "source-browser-1",
            "resource_key": "playbook-1@1",
            "params": {
                "collection_driver": data_sources.COLLECTION_DRIVER_BROWSER_PLAYBOOK,
                "dataset_id": "dataset-browser-1",
                "biz_date": "2026-05-25",
                "force_browser_collection": True,
            },
        }
    )

    assert result["success"] is True
    assert result["queued"] is True
    assert result["job"]["job_status"] == "pending"
