from __future__ import annotations

import asyncio
import sys
from pathlib import Path

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from connectors.factory import build_connector
from connectors.providers import BrowserPlaybookRemoteConnector
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


def test_factory_builds_browser_playbook_provider_alias_connector() -> None:
    connector = build_connector(
        {
            "id": "source-001",
            "company_id": "company-001",
            "source_kind": "browser_playbook",
            "provider_code": "browser_playbook",
            "execution_mode": "deterministic",
            "auth_config": {},
            "connection_config": {},
            "extract_config": {},
            "mapping_config": {},
            "runtime_config": {},
        }
    )

    assert isinstance(connector, BrowserPlaybookRemoteConnector)
    assert connector.ctx.provider_code == "browser_playbook"
    assert connector.source_kind == "browser_playbook"
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
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_shop_runtime_binding_for_source",
        lambda *, company_id, data_source_id: {
            "shop_id": "shop-001",
            "profile_status": "active",
            "playbook_status": "ok",
        },
    )
    monkeypatch.setattr(data_sources.auth_db, "find_inflight_dataset_collection_sync_job", lambda **kwargs: None)
    monkeypatch.setattr(data_sources.auth_db, "find_success_dataset_collection_sync_job", lambda **kwargs: None)

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


def test_browser_playbook_collection_reuses_waiting_handoff_job(monkeypatch) -> None:
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
    waiting_job = {
        "id": "job-waiting",
        "company_id": "company-001",
        "data_source_id": "source-001",
        "resource_key": "daily_bill",
        "job_status": "waiting_human_verification",
        "current_attempt": 1,
        "request_payload": {
            "dataset_id": "dataset-001",
            "biz_date": "2026-05-19",
            "collection_driver": data_sources.COLLECTION_DRIVER_BROWSER_PLAYBOOK,
        },
    }

    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda *, company_id, data_source_id: source,
    )
    monkeypatch.setattr(
        data_sources,
        "_resolve_dataset_row",
        lambda *, company_id, arguments: dataset,
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_shop_runtime_binding_for_source",
        lambda *, company_id, data_source_id: {
            "shop_id": "shop-001",
            "profile_status": "risk_blocked",
            "playbook_status": "ok",
            "cron_pause_reason": "RISK_VERIFICATION",
        },
    )
    monkeypatch.setattr(data_sources.auth_db, "get_latest_source_dataset_checkpoint", lambda **kwargs: {})
    monkeypatch.setattr(
        data_sources.auth_db,
        "find_inflight_dataset_collection_sync_job",
        lambda **kwargs: waiting_job,
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "create_or_reuse_dataset_collection_sync_job",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("unavailable binding must only reuse existing jobs")),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "create_unified_sync_job_attempt",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("reused browser job must not create attempt")),
    )

    result = asyncio.run(
        data_sources.trigger_dataset_collection_for_company(
            company_id="company-001",
            source_id="source-001",
            dataset_id="dataset-001",
            trigger_mode="auto",
            params={"biz_date": "2026-05-19"},
        )
    )

    assert result["success"] is True
    assert result["reused"] is True
    assert result["queued"] is True
    assert result["reuse_reason"] == "inflight"
    assert result["collection_driver"] == data_sources.COLLECTION_DRIVER_BROWSER_PLAYBOOK
    assert result["job"]["id"] == "job-waiting"
    assert result["job"]["job_status"] == "waiting_human_verification"


def test_browser_playbook_collection_reuses_success_same_biz_date_when_binding_unavailable(
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
    success_job = {
        "id": "job-recent-success",
        "company_id": "company-001",
        "data_source_id": "source-001",
        "resource_key": "daily_bill",
        "job_status": "success",
        "request_payload": {"dataset_id": "dataset-001", "biz_date": "2026-05-19"},
    }

    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda *, company_id, data_source_id: source,
    )
    monkeypatch.setattr(data_sources, "_resolve_dataset_row", lambda *, company_id, arguments: dataset)
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_shop_runtime_binding_for_source",
        lambda *, company_id, data_source_id: {
            "shop_id": "shop-001",
            "profile_status": "risk_blocked",
            "playbook_status": "ok",
            "cron_pause_reason": "RISK_VERIFICATION",
        },
    )
    monkeypatch.setattr(data_sources.auth_db, "get_latest_source_dataset_checkpoint", lambda **kwargs: {})
    monkeypatch.setattr(data_sources.auth_db, "find_inflight_dataset_collection_sync_job", lambda **kwargs: None)
    monkeypatch.setattr(
        data_sources.auth_db,
        "find_success_dataset_collection_sync_job",
        lambda **kwargs: success_job,
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_browser_collection_records",
        lambda **kwargs: [{"id": "record-001"}],
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "create_or_reuse_dataset_collection_sync_job",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("same biz-date success reuse must not create job")),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "create_unified_sync_job_attempt",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("same biz-date success reuse must not create attempt")),
    )

    result = asyncio.run(
        data_sources.trigger_dataset_collection_for_company(
            company_id="company-001",
            source_id="source-001",
            dataset_id="dataset-001",
            trigger_mode="auto",
            params={"biz_date": "2026-05-19"},
        )
    )

    assert result["success"] is True
    assert result["reused"] is True
    assert result["queued"] is False
    assert result["reuse_reason"] == "browser_biz_date_success"
    assert result["message"] == "同一浏览器数据集该账期已有成功采集结果，已复用"
    assert result["job"]["id"] == "job-recent-success"


def test_register_browser_playbook_upserts_playbook_and_binding(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda *, company_id, data_source_id: {
            "id": data_source_id,
            "company_id": company_id,
            "code": "qianniu-shop-001",
            "source_kind": "browser_playbook",
            "provider_code": "qianniu",
        },
    )

    def fake_upsert_playbook(**kwargs):
        calls.append(("playbook", dict(kwargs)))
        return {"id": "playbook-001", **kwargs}

    def fake_upsert_binding(**kwargs):
        calls.append(("binding", dict(kwargs)))
        return {"id": "binding-001", **kwargs}

    monkeypatch.setattr(data_sources.auth_db, "upsert_playbook", fake_upsert_playbook)
    monkeypatch.setattr(data_sources.auth_db, "upsert_shop_runtime_binding", fake_upsert_binding)
    monkeypatch.setattr(data_sources, "_require_user", lambda auth_token: {"company_id": "company-001"})
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_unified_data_source_datasets",
        lambda **kw: [
            {
                "id": "dataset-001",
                "dataset_code": "qianniu_fund_bill",
                "source_type": "browser_collection_records",
                "publish_status": "published",
            }
        ],
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "_seal_json_payload",
        lambda payload: f"sealed:{payload['username']}",
    )

    inserted_verification: dict[str, object] = {}

    def fake_insert_verification(**kwargs):
        inserted_verification.update(kwargs)
        return {"id": "verif-sync-001", "job_status": "pending", "is_verification": True}

    monkeypatch.setattr(
        data_sources.auth_db,
        "insert_browser_verification_sync_job",
        fake_insert_verification,
    )

    # Operator does NOT pass shop_id or agent_id — backend derives both. v1 UI never asks.
    result = asyncio.run(
        data_sources._handle_data_source_register_browser_playbook(
            {
                "auth_token": "token",
                "source_id": "source-001",
                "playbook_id": "qianniu-daily-bill-export",
                "version": "1.0.0",
                "title": "千牛资金日账单",
                "playbook_body": {"schema_version": "1.0"},
                "credential_username": "biz-sub-001",
                "credential_password": "p@ss",
                "verification_biz_date": "2026-05-19",
                "egress_group": "wan-1",
            }
        )
    )

    assert result["success"] is True
    assert result["status"] == "verification_pending"
    assert result["verification_sync_job_id"] == "verif-sync-001"
    # playbook must land as draft, binding as verifying — atomic activation comes later via finalize.
    playbook_kwargs = next(item for kind, item in calls if kind == "playbook")
    binding_kwargs = next(item for kind, item in calls if kind == "binding")
    assert playbook_kwargs["status"] == "draft"
    assert binding_kwargs["profile_status"] == "verifying"
    # shop_id derived from data_source.code; agent_id from env default.
    assert binding_kwargs["shop_id"] == "qianniu-shop-001"
    assert binding_kwargs["agent_id"] == "browser-agent-local"
    # Credentials encrypted, not stored as plaintext anywhere in the call args.
    assert binding_kwargs["credential_ref"].startswith("sealed:")
    assert "p@ss" not in str(binding_kwargs)
    assert inserted_verification["request_payload"]["verification"] is True
    assert inserted_verification["request_payload"]["playbook_id"] == "qianniu-daily-bill-export"


def test_update_browser_playbook_credential_returns_safe_summary(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(data_sources, "_require_user", lambda auth_token: {"company_id": "company-001"})
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda *, company_id, data_source_id: {
            "id": data_source_id,
            "company_id": company_id,
            "code": "browser-collection-qn",
            "name": "千牛每日资金账单",
            "source_kind": "browser_playbook",
            "provider_code": "browser_playbook",
            "domain_type": "ecommerce",
            "execution_mode": "deterministic",
        },
    )

    def fake_update(**kwargs):
        captured.update(kwargs)
        return {
            "success": True,
            "source_id": kwargs["data_source_id"],
            "credential": {
                "username": kwargs["credential_username"],
                "password_saved": True,
            },
            "binding": {
                "profile_status": "verifying",
                "playbook_status": "ok",
                "cron_pause_reason": None,
            },
            "message": "浏览器任务凭证已保存",
        }

    monkeypatch.setattr(data_sources, "update_browser_playbook_credential", fake_update)

    monkeypatch.setattr(
        data_sources,
        "_build_data_source_view",
        lambda source_row, datasets=None, include_dataset_details=False: {
            "id": source_row["id"],
            "datasets": datasets or [],
        },
    )

    async def fake_retry_verification(arguments):
        return {
            "success": True,
            "status": "verification_pending",
            "verification_sync_job_id": "sync-retry-1",
            "verification_biz_date": "2026-05-20",
            "source": {"id": "source-001"},
        }

    monkeypatch.setattr(
        data_sources,
        "_handle_data_source_retry_browser_playbook_verification",
        fake_retry_verification,
    )

    result = asyncio.run(
        data_sources._handle_data_source_update_browser_playbook_credential(
            {
                "auth_token": "token",
                "source_id": "source-001",
                "credential_username": "shop:ai财务",
                "credential_password": "secret-password",
            }
        )
    )

    assert result["success"] is True
    assert result["credential"] == {
        "username": "shop:ai财务",
        "password_saved": True,
    }
    assert result["binding"]["profile_status"] == "verifying"
    assert result["verification_sync_job_id"] == "sync-retry-1"
    assert captured["credential_password"] == "secret-password"
    assert "secret-password" not in str(result)


def test_normalize_qianniu_browser_playbook_expands_refund_safe_item_key_fields() -> None:
    playbook_body = {
        "schema_version": "1.0",
        "target": {"platform": "qianniu"},
        "steps": [{"id": "parse_detail_file", "action": "parse_table"}],
        "output": {
            "columns": [
                {"name": "业务流水号", "type": "string", "required": True},
                {"name": "退款单号", "type": "string", "required": False},
                {"name": "订单实际金额（元）", "type": "decimal", "required": True},
                {"name": "退款金额（元）", "type": "decimal", "required": False},
            ],
            "item_key_fields": ["业务流水号"],
        },
    }

    normalized, error = data_sources._normalize_browser_playbook_body(playbook_body)

    assert error == ""
    assert normalized["output"]["item_key_fields"] == ["业务流水号", "退款单号"]


def test_register_browser_playbook_respects_env_default_agent_id(monkeypatch) -> None:
    """BROWSER_AGENT_DEFAULT_AGENT_ID env var overrides the built-in 'browser-agent-local' fallback."""
    monkeypatch.setenv("BROWSER_AGENT_DEFAULT_AGENT_ID", "browser-agent-prod-1")

    captured: dict[str, object] = {}

    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda *, company_id, data_source_id: {
            "id": data_source_id,
            "code": "qianniu-shop-xyz",
            "source_kind": "browser_playbook",
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_unified_data_source_datasets",
        lambda **kw: [{"id": "dataset-001", "source_type": "browser_collection_records"}],
    )
    monkeypatch.setattr(data_sources, "_require_user", lambda auth_token: {"company_id": "company-001"})
    monkeypatch.setattr(data_sources.auth_db, "_seal_json_payload", lambda p: "sealed")
    monkeypatch.setattr(data_sources.auth_db, "upsert_playbook", lambda **kw: {"id": "p1"})
    monkeypatch.setattr(
        data_sources.auth_db,
        "upsert_shop_runtime_binding",
        lambda **kw: captured.update(kw) or {"id": "b1"},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "insert_browser_verification_sync_job",
        lambda **kw: {"id": "v1"},
    )

    asyncio.run(
        data_sources._handle_data_source_register_browser_playbook(
            {
                "auth_token": "tok",
                "source_id": "source-001",
                "playbook_id": "pb",
                "version": "1.0.0",
                "title": "t",
                "playbook_body": {"schema_version": "1.0"},
                "credential_username": "u",
                "credential_password": "p",
                "verification_biz_date": "2026-05-19",
            }
        )
    )

    assert captured["agent_id"] == "browser-agent-prod-1"
    assert captured["shop_id"] == "qianniu-shop-xyz"


def test_browser_dataset_collection_rejects_unhealthy_binding_before_sync_job(monkeypatch) -> None:
    """Trigger-time health gate must run before create_or_reuse_dataset_collection_sync_job."""
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
        "data_source_id": "source-001",
        "dataset_code": "qianniu_daily_bill",
        "resource_key": "daily_bill",
        "source_kind": "browser_playbook",
        "provider_code": "qianniu",
        "sync_strategy": {},
        "publish_status": "published",
    }

    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda *, company_id, data_source_id: source,
    )
    monkeypatch.setattr(
        data_sources,
        "_resolve_dataset_row",
        lambda *, company_id, arguments: dataset,
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_shop_runtime_binding_for_source",
        lambda *, company_id, data_source_id: {
            "shop_id": "shop-001",
            "profile_status": "risk_blocked",
            "playbook_status": "ok",
            "cron_pause_reason": "RISK_VERIFICATION",
        },
    )
    monkeypatch.setattr(data_sources.auth_db, "get_latest_source_dataset_checkpoint", lambda **kwargs: {})
    monkeypatch.setattr(data_sources.auth_db, "find_inflight_dataset_collection_sync_job", lambda **kwargs: None)
    monkeypatch.setattr(data_sources.auth_db, "find_success_dataset_collection_sync_job", lambda **kwargs: None)

    def fail_if_created(**kwargs):
        raise AssertionError("unhealthy browser binding must not create sync job")

    monkeypatch.setattr(data_sources.auth_db, "create_or_reuse_dataset_collection_sync_job", fail_if_created)

    result = asyncio.run(
        data_sources.trigger_dataset_collection_for_company(
            company_id="company-001",
            source_id="source-001",
            dataset_id="dataset-001",
            trigger_mode="manual",
            params={"biz_date": "2026-05-19"},
        )
    )

    assert result["success"] is False
    assert result["queued"] is False
    assert result["failure_type"] == "browser_binding_unavailable"
    assert result["error_code"] == "RISK_VERIFICATION"


def test_finalize_activates_playbook_and_binding_on_verification_success(monkeypatch) -> None:
    activated: dict[str, object] = {}

    monkeypatch.setattr(data_sources, "_require_user", lambda auth_token: {"company_id": "company-001"})
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_sync_job_by_id",
        lambda sync_job_id: {
            "id": sync_job_id,
            "company_id": "company-001",
            "data_source_id": "source-001",
            "job_status": "success",
            "is_verification": True,
            "request_payload": {
                "playbook_id": "qianniu-daily-bill-export",
                "playbook_version": "1.0.0",
            },
        },
    )

    def fake_activate(**kwargs):
        activated.update(kwargs)
        return {
            "playbook": {"id": "pb-1", "status": "active"},
            "binding": {"id": "bind-1", "profile_status": "active"},
        }

    monkeypatch.setattr(data_sources.auth_db, "activate_browser_playbook_and_binding", fake_activate)

    result = asyncio.run(
        data_sources._handle_data_source_finalize_browser_playbook_registration(
            {"auth_token": "tok", "verification_sync_job_id": "verif-sync-001"}
        )
    )

    assert result["success"] is True
    assert result["playbook"]["status"] == "active"
    assert result["binding"]["profile_status"] == "active"
    assert activated["playbook_id"] == "qianniu-daily-bill-export"
    assert activated["data_source_id"] == "source-001"


def test_finalize_rejects_when_verification_sync_job_failed(monkeypatch) -> None:
    monkeypatch.setattr(data_sources, "_require_user", lambda auth_token: {"company_id": "company-001"})
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_sync_job_by_id",
        lambda sync_job_id: {
            "id": sync_job_id,
            "company_id": "company-001",
            "data_source_id": "source-001",
            "job_status": "failed",
            "is_verification": True,
            "browser_fail_reason": "AUTH_EXPIRED",
            "error_message": "AUTH_EXPIRED: login expired",
            "request_payload": {
                "playbook_id": "qianniu-daily-bill-export",
                "playbook_version": "1.0.0",
            },
        },
    )

    def fail_if_called(**kwargs):
        raise AssertionError("activate must not run when verification failed")

    monkeypatch.setattr(data_sources.auth_db, "activate_browser_playbook_and_binding", fail_if_called)

    result = asyncio.run(
        data_sources._handle_data_source_finalize_browser_playbook_registration(
            {"auth_token": "tok", "verification_sync_job_id": "verif-sync-001"}
        )
    )

    assert result["success"] is False
    assert result["browser_fail_reason"] == "AUTH_EXPIRED"
    assert "AUTH_EXPIRED" in result["error_message"]


def test_register_browser_playbook_rejects_when_no_published_dataset(monkeypatch) -> None:
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda *, company_id, data_source_id: {
            "id": data_source_id,
            "company_id": company_id,
            "source_kind": "browser_playbook",
            "provider_code": "qianniu",
        },
    )
    # No published browser_collection_records dataset for this source.
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_unified_data_source_datasets",
        lambda **kw: [],
    )
    monkeypatch.setattr(data_sources, "_require_user", lambda auth_token: {"company_id": "company-001"})

    def fail_if_called(**kwargs):
        raise AssertionError("upsert must not run when dataset prerequisite is missing")

    monkeypatch.setattr(data_sources.auth_db, "upsert_playbook", fail_if_called)
    monkeypatch.setattr(data_sources.auth_db, "upsert_shop_runtime_binding", fail_if_called)

    result = asyncio.run(
        data_sources._handle_data_source_register_browser_playbook(
            {
                "auth_token": "token",
                "source_id": "source-001",
                "playbook_id": "qianniu-daily-bill-export",
                "version": "1.0.0",
                "title": "千牛资金日账单",
                "playbook_body": {"schema_version": "1.0"},
                "shop_id": "shop-001",
                "agent_id": "agent-001",
            }
        )
    )

    assert result["success"] is False
    assert "browser_collection_records" in result["error"]
