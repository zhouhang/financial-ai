from __future__ import annotations

import sys
from pathlib import Path
import pytest

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from tools import data_sources
from auth import db as auth_db


@pytest.mark.anyio
async def test_data_source_list_includes_platform_fixed_datasets(monkeypatch) -> None:
    monkeypatch.setattr(
        data_sources,
        "_require_user",
        lambda auth_token: {"company_id": "company-1", "user_id": "user-1", "role": "admin"},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_unified_data_sources",
        lambda **kwargs: [
            {
                "id": "source-alipay-1",
                "company_id": "company-1",
                "code": "platform_oauth_alipay_shop_alipay_1",
                "name": "支付宝授权 - 对对科技",
                "source_kind": "platform_oauth",
                "domain_type": "ecommerce",
                "provider_code": "alipay",
                "execution_mode": "deterministic",
                "status": "active",
                "is_enabled": True,
                "health_status": "unknown",
                "meta": {"shop_connection_id": "shop-alipay-1"},
            }
        ],
        raising=False,
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_unified_data_source_datasets",
        lambda **kwargs: [
            {
                "id": "dataset-trade",
                "company_id": "company-1",
                "data_source_id": "source-alipay-1",
                "dataset_code": "alipay_trade_bill_shop_alipay_1",
                "dataset_name": "交易账单 - 对对科技",
                "resource_key": "alipay_bill:trade:shop-alipay-1",
                "dataset_kind": "api_endpoint",
                "origin_type": "fixed",
                "status": "active",
                "is_enabled": True,
                "publish_status": "unpublished",
                "business_domain": "ecommerce",
                "business_object_type": "payment_trade",
                "grain": "bill_line",
                "health_status": "unknown",
                "meta": {"shop_connection_id": "shop-alipay-1"},
            }
        ],
        raising=False,
    )
    monkeypatch.setattr(data_sources.auth_db, "get_unified_data_source_credentials", lambda **kwargs: None)
    monkeypatch.setattr(data_sources, "_load_source_configs", lambda source_id: {})
    monkeypatch.setattr(data_sources.auth_db, "list_unified_sync_jobs", lambda **kwargs: [], raising=False)

    result = await data_sources._handle_data_source_list({"auth_token": "token"})

    assert result["success"] is True
    datasets = result["sources"][0]["datasets"]
    assert len(datasets) == 1
    assert datasets[0]["id"] == "dataset-trade"
    assert datasets[0]["data_source_id"] == "source-alipay-1"
    assert datasets[0]["dataset_code"] == "alipay_trade_bill_shop_alipay_1"
    assert datasets[0]["dataset_name"] == "交易账单 - 对对科技"
    assert datasets[0]["resource_key"] == "alipay_bill:trade:shop-alipay-1"
    assert datasets[0]["origin_type"] == "fixed"
    assert datasets[0]["business_object_type"] == "payment_trade"


@pytest.mark.anyio
async def test_data_source_list_includes_browser_verification_summary(monkeypatch) -> None:
    monkeypatch.setattr(
        data_sources,
        "_require_user",
        lambda auth_token: {"company_id": "company-1", "user_id": "user-1", "role": "admin"},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_unified_data_sources",
        lambda **kwargs: [
            {
                "id": "source-browser-1",
                "company_id": "company-1",
                "code": "browser-collection-qn",
                "name": "单枪旗舰店-收支明细",
                "source_kind": "browser_playbook",
                "domain_type": "ecommerce",
                "provider_code": "browser_playbook",
                "execution_mode": "deterministic",
                "status": "active",
                "is_enabled": True,
                "health_status": "unknown",
                "meta": {"registration_title": "单枪旗舰店-收支明细"},
            }
        ],
        raising=False,
    )
    monkeypatch.setattr(data_sources.auth_db, "list_unified_data_source_datasets", lambda **kwargs: [])
    monkeypatch.setattr(data_sources.auth_db, "get_unified_data_source_credentials", lambda **kwargs: None)
    monkeypatch.setattr(data_sources, "_load_source_configs", lambda source_id: {})
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_unified_sync_jobs",
        lambda **kwargs: [
            {
                "id": "sync-verify-1",
                "job_status": "failed",
                "is_verification": True,
                "browser_fail_reason": "PAGE_CHANGED",
                "error_message": "PAGE_CHANGED: login selector missing",
                "updated_at": "2026-05-22T13:32:56+08:00",
            }
        ],
        raising=False,
    )

    result = await data_sources._handle_data_source_list({"auth_token": "token"})

    assert result["success"] is True
    summary = result["sources"][0]["browser_verification"]
    assert summary["sync_job_id"] == "sync-verify-1"
    assert summary["job_status"] == "failed"
    assert summary["browser_fail_reason"] == "PAGE_CHANGED"
    assert summary["error_message"] == "PAGE_CHANGED: login selector missing"


@pytest.mark.anyio
async def test_data_source_list_scans_recent_jobs_for_browser_verification_summary(monkeypatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        data_sources,
        "_require_user",
        lambda auth_token: {"company_id": "company-1", "user_id": "user-1", "role": "admin"},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_unified_data_sources",
        lambda **kwargs: [
            {
                "id": "source-browser-1",
                "company_id": "company-1",
                "code": "browser-collection-qn",
                "name": "单枪旗舰店-收支账单",
                "source_kind": "browser_playbook",
                "domain_type": "ecommerce",
                "provider_code": "browser_playbook",
                "execution_mode": "deterministic",
                "status": "active",
                "is_enabled": True,
                "health_status": "unknown",
                "meta": {"registration_title": "单枪旗舰店-收支账单"},
            }
        ],
        raising=False,
    )
    monkeypatch.setattr(data_sources.auth_db, "list_unified_data_source_datasets", lambda **kwargs: [])
    monkeypatch.setattr(data_sources.auth_db, "get_unified_data_source_credentials", lambda **kwargs: None)
    monkeypatch.setattr(data_sources, "_load_source_configs", lambda source_id: {})

    def fake_list_jobs(**kwargs):
        captured["limit"] = kwargs.get("limit")
        return [
            {
                "id": "sync-non-verification-latest",
                "job_status": "success",
                "is_verification": False,
                "updated_at": "2026-05-25T15:40:00+08:00",
            },
            {
                "id": "sync-verify-success",
                "job_status": "success",
                "is_verification": True,
                "updated_at": "2026-05-25T15:31:51+08:00",
                "completed_at": "2026-05-25T15:31:51+08:00",
            },
        ]

    monkeypatch.setattr(data_sources.auth_db, "list_unified_sync_jobs", fake_list_jobs, raising=False)

    result = await data_sources._handle_data_source_list({"auth_token": "token"})

    assert result["success"] is True
    assert captured["limit"] > 1
    summary = result["sources"][0]["browser_verification"]
    assert summary["sync_job_id"] == "sync-verify-success"
    assert summary["job_status"] == "success"


@pytest.mark.anyio
async def test_browser_playbook_detail_returns_safe_credential_and_latest_records(monkeypatch) -> None:
    monkeypatch.setattr(
        data_sources,
        "_require_user",
        lambda auth_token: {"company_id": "company-1", "user_id": "user-1", "role": "admin"},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda **kwargs: {
            "id": "source-browser-1",
            "company_id": "company-1",
            "code": "browser-collection-qn",
            "name": "单枪旗舰店-收支明细",
            "source_kind": "browser_playbook",
            "domain_type": "ecommerce",
            "provider_code": "browser_playbook",
            "execution_mode": "deterministic",
            "status": "active",
            "is_enabled": True,
            "health_status": "unknown",
            "meta": {"registration_title": "单枪旗舰店-收支明细"},
        },
        raising=False,
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_unified_data_source_datasets",
        lambda **kwargs: [
            {
                "id": "dataset-browser-1",
                "data_source_id": "source-browser-1",
                "dataset_code": "browser-collection-qn",
                "dataset_name": "单枪旗舰店-收支明细",
                "resource_key": "browser-collection-qn@1",
                "source_type": "browser_collection_records",
                "publish_status": "published",
                "meta": {"source_type": "browser_collection_records"},
            }
        ],
        raising=False,
    )
    monkeypatch.setattr(data_sources.auth_db, "get_unified_data_source_credentials", lambda **kwargs: None)
    monkeypatch.setattr(data_sources, "_load_source_configs", lambda source_id: {})
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_unified_sync_jobs",
        lambda **kwargs: [
            {
                "id": "sync-verify-1",
                "job_status": "success",
                "is_verification": True,
                "updated_at": "2026-05-22T13:32:56+08:00",
                "completed_at": "2026-05-22T13:33:01+08:00",
            }
        ],
        raising=False,
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_shop_runtime_binding_for_source",
        lambda **kwargs: {
            "id": "binding-1",
            "playbook_id": "browser-collection-qn",
            "shop_id": "browser-collection-qn",
            "agent_id": "browser-agent-local",
            "profile_status": "active",
            "playbook_status": "ok",
            "credential_ref": "sealed-credential-ref",
        },
        raising=False,
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "_open_json_payload",
        lambda value: {"username": "finance_ops@example.com", "password": "secret"},
        raising=False,
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_active_playbook",
        lambda **kwargs: {
            "playbook_id": "browser-collection-qn",
            "version": "1",
            "title": "单枪旗舰店-收支明细",
            "status": "active",
            "playbook_body": {"schema_version": "1.0", "steps": [{"action": "click"}]},
            "updated_at": "2026-05-22T13:31:00+08:00",
        },
        raising=False,
    )
    record_query: dict[str, object] = {}

    def fake_list_browser_collection_records(**kwargs):
        record_query.update(kwargs)
        return [
            {
                "id": "record-1",
                "dataset_id": "dataset-browser-1",
                "biz_date": "2026-05-21",
                "item_key": "bill-1",
                "payload": {"账单号": "bill-1", "金额": "12.30"},
                "captured_at": "2026-05-22T13:30:00+08:00",
            }
        ]

    monkeypatch.setattr(
        data_sources.auth_db,
        "list_browser_collection_records",
        fake_list_browser_collection_records,
        raising=False,
    )

    result = await data_sources._handle_data_source_get_browser_playbook_detail(
        {"auth_token": "token", "source_id": "source-browser-1"}
    )

    assert result["success"] is True
    assert result["source"]["id"] == "source-browser-1"
    assert record_query["limit"] == 100
    assert result["record_count"] == 1
    assert result["playbook"]["playbook_body"] == {
        "schema_version": "1.0",
        "steps": [{"action": "click"}],
    }
    assert result["latest_records"][0]["payload"]["账单号"] == "bill-1"
    assert result["credential"] == {
        "username": "finance_ops@example.com",
        "password_saved": True,
    }
    assert "credential_ref" not in str(result)
    assert "secret" not in str(result)


@pytest.mark.anyio
async def test_browser_playbook_detail_falls_back_to_bound_draft_playbook(monkeypatch) -> None:
    monkeypatch.setattr(
        data_sources,
        "_require_user",
        lambda auth_token: {"company_id": "company-1", "user_id": "user-1", "role": "admin"},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda **kwargs: {
            "id": "source-browser-1",
            "company_id": "company-1",
            "code": "browser-collection-qn",
            "name": "单枪旗舰店-收支账单",
            "source_kind": "browser_playbook",
            "domain_type": "ecommerce",
            "provider_code": "browser_playbook",
            "execution_mode": "deterministic",
            "status": "active",
            "is_enabled": True,
            "health_status": "unknown",
            "meta": {"registration_title": "单枪旗舰店-收支账单"},
        },
        raising=False,
    )
    monkeypatch.setattr(data_sources.auth_db, "list_unified_data_source_datasets", lambda **kwargs: [])
    monkeypatch.setattr(data_sources.auth_db, "get_unified_data_source_credentials", lambda **kwargs: None)
    monkeypatch.setattr(data_sources, "_load_source_configs", lambda source_id: {})
    monkeypatch.setattr(data_sources.auth_db, "list_unified_sync_jobs", lambda **kwargs: [], raising=False)
    monkeypatch.setattr(data_sources.auth_db, "list_browser_collection_records", lambda **kwargs: [], raising=False)
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_shop_runtime_binding_for_source",
        lambda **kwargs: {
            "id": "binding-1",
            "playbook_id": "browser-collection-qn",
            "profile_status": "active",
            "playbook_status": "ok",
            "credential_ref": "",
        },
        raising=False,
    )
    monkeypatch.setattr(data_sources.auth_db, "get_active_playbook", lambda **kwargs: {}, raising=False)
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_playbook",
        lambda **kwargs: {
            "playbook_id": "browser-collection-qn",
            "version": "1",
            "title": "单枪旗舰店-收支账单",
            "status": "draft",
            "playbook_body": {"schema_version": "1.0", "steps": [{"action": "download"}]},
            "updated_at": "2026-05-25T15:00:00+08:00",
        },
        raising=False,
    )

    result = await data_sources._handle_data_source_get_browser_playbook_detail(
        {"auth_token": "token", "source_id": "source-browser-1"}
    )

    assert result["success"] is True
    assert result["playbook"]["status"] == "draft"
    assert result["playbook"]["playbook_body"] == {
        "schema_version": "1.0",
        "steps": [{"action": "download"}],
    }


def test_ensure_sync_jobs_trigger_modes_schema_runs_migration_when_initial_missing(monkeypatch) -> None:
    calls: list[str] = []
    definitions = iter(
        [
            "CHECK (((trigger_mode)::text = ANY (ARRAY['manual'::text, 'scheduled'::text, 'event'::text, 'retry'::text])))",
            "CHECK (((trigger_mode)::text = ANY (ARRAY['manual'::text, 'scheduled'::text, 'schedule'::text, 'event'::text, 'retry'::text, 'initial'::text, 'daily'::text])))",
        ]
    )

    monkeypatch.setattr(auth_db, "_SYNC_JOBS_TRIGGER_MODES_SCHEMA_READY", False, raising=False)
    monkeypatch.setattr(auth_db, "_table_exists", lambda table_name, schema="public": table_name == "sync_jobs")
    monkeypatch.setattr(
        auth_db,
        "_constraint_definition",
        lambda table_name, constraint_name, schema="public": next(definitions),
    )
    monkeypatch.setattr(auth_db, "_execute_sql_script", lambda script_path: calls.append(script_path.name))

    applied = auth_db.ensure_sync_jobs_trigger_modes_schema()

    assert applied == ["027_sync_jobs_trigger_modes_initial_schedule.sql"]
    assert calls == ["027_sync_jobs_trigger_modes_initial_schedule.sql"]
