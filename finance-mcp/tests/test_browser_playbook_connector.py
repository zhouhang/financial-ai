from __future__ import annotations

import asyncio
import sys
from pathlib import Path

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from connectors.factory import build_connector
from tools import data_sources


def test_browser_playbook_source_kind_is_deterministic_and_not_agent_assisted() -> None:
    assert "browser_playbook" in data_sources.SOURCE_KINDS
    assert "browser_playbook" not in data_sources.AGENT_ASSISTED_KINDS
    assert data_sources._default_execution_mode("browser_playbook") == "deterministic"


def test_factory_builds_qianniu_browser_playbook_connector() -> None:
    connector = build_connector(
        {
            "id": "source-001",
            "company_id": "company-001",
            "source_kind": "browser_playbook",
            "provider_code": "qianniu",
            "execution_mode": "deterministic",
            "auth_config": {},
            "connection_config": {},
            "extract_config": {},
            "mapping_config": {},
            "runtime_config": {},
        }
    )

    assert connector.source_kind == "browser_playbook"
    assert connector.provider_code == "qianniu"
    assert connector.execution_mode == "deterministic"


def test_browser_playbook_resolves_to_remote_collection_driver() -> None:
    assert (
        data_sources._resolve_collection_driver(
            {"source_kind": "browser_playbook", "provider_code": "qianniu"},
            {},
        )
        == data_sources.COLLECTION_DRIVER_BROWSER_PLAYBOOK
    )


def test_browser_playbook_dataset_collection_queues_sync_job_without_inline_execution(
    monkeypatch,
) -> None:
    source = {
        "id": "source-001",
        "company_id": "company-001",
        "source_kind": "browser_playbook",
        "provider_code": "qianniu",
        "status": "active",
        "is_enabled": True,
        "auth_config": {},
        "connection_config": {},
        "extract_config": {},
        "mapping_config": {},
        "runtime_config": {},
    }
    dataset = {
        "id": "dataset-001",
        "dataset_code": "qianniu_daily_bill",
        "resource_key": "daily_bill",
        "source_kind": "browser_playbook",
        "provider_code": "qianniu",
        "sync_strategy": {},
    }
    job = {
        "id": "job-001",
        "company_id": "company-001",
        "data_source_id": "source-001",
        "job_status": "pending",
        "current_attempt": 0,
    }
    attempt = {"id": "attempt-001"}
    created_request_payloads: list[dict] = []

    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_dataset_by_id",
        lambda *, company_id, dataset_id: dataset,
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda *, company_id, data_source_id: source,
    )
    monkeypatch.setattr(
        data_sources,
        "_load_runtime_source",
        lambda source_row, include_secret=False: dict(source_row),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_latest_source_dataset_checkpoint",
        lambda **kwargs: {},
    )

    def fake_create_or_reuse_dataset_collection_sync_job(**kwargs):
        created_request_payloads.append(dict(kwargs["request_payload"]))
        return {"job": job, "reused": False}

    monkeypatch.setattr(
        data_sources.auth_db,
        "create_or_reuse_dataset_collection_sync_job",
        fake_create_or_reuse_dataset_collection_sync_job,
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "create_unified_sync_job_attempt",
        lambda **kwargs: attempt,
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_sync_job_by_id",
        lambda sync_job_id: job,
    )

    async def fail_if_inline_execution(**kwargs):
        raise AssertionError("browser_playbook collection must be dispatched, not executed inline")

    monkeypatch.setattr(data_sources, "_execute_sync_job", fail_if_inline_execution)

    result = asyncio.run(
        data_sources.trigger_dataset_collection_for_company(
            company_id="company-001",
            source_id="source-001",
            dataset_id="dataset-001",
            trigger_mode="manual",
            params={"biz_date": "2026-05-19"},
        )
    )

    assert result["success"] is True
    assert result["queued"] is True
    assert result["collection_driver"] == data_sources.COLLECTION_DRIVER_BROWSER_PLAYBOOK
    assert result["job"]["id"] == "job-001"
    assert created_request_payloads[0]["collection_driver"] == data_sources.COLLECTION_DRIVER_BROWSER_PLAYBOOK
