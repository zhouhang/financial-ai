from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from tools import data_sources


def test_slug_from_browser_registration_title_handles_chinese_and_collisions() -> None:
    assert data_sources._browser_registration_slug("千牛每日资金账单") == "browser-collection"
    assert data_sources._browser_registration_slug("Daily Fund Bill") == "daily-fund-bill"


def test_default_browser_verification_biz_date_is_t_minus_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeDate(data_sources.date):
        @classmethod
        def today(cls):
            return cls(2026, 5, 21)

    monkeypatch.setattr(data_sources, "date", FakeDate)

    assert data_sources._default_browser_verification_biz_date() == "2026-05-20"


def test_register_browser_collection_creates_source_dataset_and_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict]] = []

    monkeypatch.setattr(
        data_sources,
        "_require_user",
        lambda token: {"company_id": "company-1", "id": "user-1"},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "upsert_unified_data_source",
        lambda **kwargs: calls.append(("source", kwargs)) or {
            "id": "source-1",
            "company_id": kwargs["company_id"],
            "code": kwargs["code"],
            "name": kwargs["name"],
            "source_kind": kwargs["source_kind"],
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "upsert_unified_data_source_dataset",
        lambda **kwargs: calls.append(("dataset", kwargs)) or {
            "id": "dataset-1",
            "dataset_code": kwargs["dataset_code"],
            "dataset_name": kwargs["dataset_name"],
            "resource_key": kwargs["resource_key"],
            "source_type": "browser_collection_records",
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda **kwargs: {
            "id": "source-1",
            "company_id": "company-1",
            "code": "browser-collection",
            "name": "千牛每日资金账单",
            "source_kind": "browser_playbook",
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_unified_data_source_datasets",
        lambda **kwargs: [
            {
                "id": "dataset-1",
                "dataset_code": "browser-collection",
                "dataset_name": "千牛每日资金账单",
                "source_type": "browser_collection_records",
                "publish_status": "published",
                "meta": {"source_type": "browser_collection_records"},
            }
        ],
    )
    monkeypatch.setattr(data_sources.auth_db, "_seal_json_payload", lambda payload: "sealed-secret")
    monkeypatch.setattr(
        data_sources.auth_db,
        "upsert_playbook",
        lambda **kwargs: calls.append(("playbook", kwargs)) or {
            "playbook_id": kwargs["playbook_id"],
            "version": kwargs["version"],
            "title": kwargs["title"],
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "upsert_shop_runtime_binding",
        lambda **kwargs: calls.append(("binding", kwargs)) or {
            "data_source_id": kwargs["data_source_id"],
            "credential_ref": kwargs["credential_ref"],
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "insert_browser_verification_sync_job",
        lambda **kwargs: calls.append(("sync_job", kwargs)) or {"id": "sync-1"},
    )
    monkeypatch.setattr(
        data_sources,
        "_default_browser_verification_biz_date",
        lambda: "2026-05-20",
    )

    result = asyncio.run(
        data_sources._handle_data_source_register_browser_collection(
            {
                "auth_token": "token",
                "title": "千牛每日资金账单",
                "credential_username": "finance_ops@example.com",
                "credential_password": "secret",
                "playbook_body": {"schema_version": "1.0", "steps": []},
            }
        )
    )

    assert result["success"] is True
    assert result["source"]["id"] == "source-1"
    assert result["dataset"]["id"] == "dataset-1"
    assert result["verification_sync_job_id"] == "sync-1"
    assert result["verification_biz_date"] == "2026-05-20"

    source_call = next(payload for name, payload in calls if name == "source")
    assert source_call["source_kind"] == "browser_playbook"
    assert source_call["name"] == "千牛每日资金账单"
    assert source_call["is_enabled"] is True

    dataset_call = next(payload for name, payload in calls if name == "dataset")
    assert dataset_call["dataset_name"] == "千牛每日资金账单"
    assert dataset_call["publish_status"] == "published"
    assert dataset_call["meta"]["source_type"] == "browser_collection_records"

    playbook_call = next(payload for name, payload in calls if name == "playbook")
    assert playbook_call["playbook_id"] == "browser-collection"
    assert playbook_call["version"] == "1"

    sync_call = next(payload for name, payload in calls if name == "sync_job")
    assert sync_call["request_payload"]["dataset_id"] == "dataset-1"
    assert sync_call["request_payload"]["params"]["biz_date"] == "2026-05-20"
