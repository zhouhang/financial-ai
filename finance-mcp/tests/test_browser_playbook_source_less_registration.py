from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from auth import db as auth_db
from tools import data_sources


def test_slug_from_browser_registration_title_handles_chinese_and_collisions() -> None:
    assert data_sources._browser_registration_slug("千牛每日资金账单") == "browser-collection"
    assert data_sources._browser_registration_slug("Daily Fund Bill") == "daily-fund-bill"


def test_browser_registration_code_is_unique_and_bounded() -> None:
    title = "千牛每日资金账单" * 20

    first = data_sources._browser_registration_code(title=title)
    second = data_sources._browser_registration_code(title=title)

    assert first != second
    assert first.startswith("browser-collection-")
    assert second.startswith("browser-collection-")
    assert len(first) <= 100
    assert len(second) <= 100


def test_unified_schema_bootstrap_upgrades_browser_playbook_source_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    state = {"constraint_def": "platform_oauth database api file browser desktop_cli"}

    monkeypatch.setattr(auth_db, "_UNIFIED_DATA_SOURCE_SCHEMA_READY", False)
    monkeypatch.setattr(
        auth_db,
        "_table_exists",
        lambda table_name, schema="public": table_name
        not in {
            "dataset_snapshots",
            "dataset_snapshot_items",
            "raw_ingestion_records",
            "raw_ingestion_batches",
            "sync_checkpoints",
        },
    )
    monkeypatch.setattr(
        auth_db,
        "_column_exists",
        lambda table_name, column_name, schema="public": not (
            table_name == "platform_alipay_bill_lines"
            and column_name in auth_db._PLATFORM_ALIPAY_BILL_LINES_DERIVED_BUSINESS_COLUMNS
        ),
    )
    monkeypatch.setattr(
        auth_db,
        "_constraint_definition",
        lambda table_name, constraint_name, schema="public": state["constraint_def"],
    )
    monkeypatch.setattr(auth_db, "_platform_alipay_bill_lines_schema_ready", lambda: True)
    monkeypatch.setattr(auth_db, "_alipay_semantic_profiles_need_hidden_field_cleanup", lambda: False)
    monkeypatch.setattr(auth_db, "ensure_sync_jobs_trigger_modes_schema", lambda: [])

    def fake_execute_sql_script(script_path: Path) -> None:
        calls.append(script_path.name)
        if script_path.name == "032_data_sources_browser_playbook_source_kind.sql":
            state["constraint_def"] = f"{state['constraint_def']} browser_playbook"

    monkeypatch.setattr(auth_db, "_execute_sql_script", fake_execute_sql_script)
    monkeypatch.setattr(auth_db, "_migration_path", lambda filename: Path(filename))

    assert "032_data_sources_browser_playbook_source_kind.sql" in auth_db.ensure_unified_data_source_schema()
    assert calls == ["032_data_sources_browser_playbook_source_kind.sql"]


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
    created_source_codes: list[str] = []
    created_dataset_codes: list[str] = []
    created_origin_types: list[str] = []
    created_extract_configs: list[dict] = []

    def fake_upsert_source(**kwargs):
        calls.append(("source", kwargs))
        created_source_codes.append(kwargs["code"])
        return {
            "id": "source-1",
            "company_id": kwargs["company_id"],
            "code": kwargs["code"],
            "name": kwargs["name"],
            "source_kind": kwargs["source_kind"],
            "domain_type": kwargs["domain_type"],
            "provider_code": kwargs["provider_code"],
            "execution_mode": kwargs["execution_mode"],
            "status": kwargs["status"],
            "is_enabled": kwargs["is_enabled"],
            "meta": kwargs["meta"],
        }

    def fake_upsert_dataset(**kwargs):
        calls.append(("dataset", kwargs))
        created_dataset_codes.append(kwargs["dataset_code"])
        created_origin_types.append(kwargs["origin_type"])
        created_extract_configs.append(kwargs["extract_config"])
        return {
            "id": "dataset-1",
            "company_id": kwargs["company_id"],
            "data_source_id": kwargs["data_source_id"],
            "dataset_code": kwargs["dataset_code"],
            "dataset_name": kwargs["dataset_name"],
            "resource_key": kwargs["resource_key"],
            "source_type": "browser_collection_records",
            "origin_type": kwargs["origin_type"],
            "extract_config": kwargs["extract_config"],
            "schema_summary": kwargs["schema_summary"],
            "sync_strategy": kwargs["sync_strategy"],
            "publish_status": kwargs["publish_status"],
            "meta": kwargs["meta"],
        }

    monkeypatch.setattr(
        data_sources,
        "_require_user",
        lambda token: {"company_id": "company-1", "id": "user-1"},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "upsert_unified_data_source",
        fake_upsert_source,
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "upsert_unified_data_source_dataset",
        fake_upsert_dataset,
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda **kwargs: {
            "id": "source-1",
            "company_id": "company-1",
            "code": created_source_codes[-1],
            "name": "千牛每日资金账单",
            "source_kind": "browser_playbook",
            "domain_type": "ecommerce",
            "provider_code": "browser_playbook",
            "execution_mode": "deterministic",
            "status": "active",
            "is_enabled": True,
            "meta": {},
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_unified_data_source_datasets",
        lambda **kwargs: [
            {
                "id": "dataset-1",
                "dataset_code": created_dataset_codes[-1],
                "dataset_name": "千牛每日资金账单",
                "source_type": "browser_collection_records",
                "origin_type": created_origin_types[-1],
                "extract_config": created_extract_configs[-1],
                "publish_status": "published",
                "meta": {"source_type": "browser_collection_records"},
            }
        ],
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_unified_sync_jobs",
        lambda **kwargs: [],
    )
    monkeypatch.setattr(data_sources, "_load_source_configs", lambda source_id: {})
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_credentials",
        lambda **kwargs: None,
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
                "shop_id": "attacker-shop",
                "agent_id": "attacker-agent",
                "emergency_page_changed": True,
                "bypass_canary_reason": "skip safety",
                "dataset_id": "attacker-dataset",
                "source_id": "attacker-source",
                "playbook_id": "attacker-playbook",
                "version": "999",
                "verification_biz_date": "2099-01-01",
                "egress_group": "attacker-egress",
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
    assert source_call["code"].startswith("browser-collection-")
    assert source_call["code"] != "browser-collection"

    dataset_call = next(payload for name, payload in calls if name == "dataset")
    assert dataset_call["dataset_name"] == "千牛每日资金账单"
    assert dataset_call["publish_status"] == "published"
    assert dataset_call["dataset_code"] == source_call["code"]
    assert dataset_call["resource_key"] == f"{source_call['code']}@1"
    assert dataset_call["origin_type"] == "manual"
    assert dataset_call["extract_config"]["source_type"] == "browser_collection_records"
    assert dataset_call["extract_config"]["registration_kind"] == "browser_playbook"
    assert dataset_call["meta"]["source_type"] == "browser_collection_records"
    assert dataset_call["meta"]["registration_kind"] == "browser_playbook"

    playbook_call = next(payload for name, payload in calls if name == "playbook")
    assert playbook_call["playbook_id"] == source_call["code"]
    assert playbook_call["version"] == "1"
    assert playbook_call["title"] == "千牛每日资金账单"
    assert playbook_call["emergency_page_changed"] is False
    assert playbook_call["bypass_canary_reason"] == ""

    binding_call = next(payload for name, payload in calls if name == "binding")
    assert binding_call["data_source_id"] == "source-1"
    assert binding_call["shop_id"] == source_call["code"]
    assert binding_call["agent_id"] == "browser-agent-local"
    assert binding_call["egress_group"] == ""

    sync_call = next(payload for name, payload in calls if name == "sync_job")
    assert sync_call["request_payload"]["dataset_id"] == "dataset-1"
    assert sync_call["request_payload"]["dataset_code"] == source_call["code"]
    assert sync_call["request_payload"]["playbook_id"] == source_call["code"]
    assert sync_call["request_payload"]["params"]["biz_date"] == "2026-05-20"


def test_register_browser_collection_rejects_non_dict_playbook_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        data_sources,
        "_require_user",
        lambda token: {"company_id": "company-1", "id": "user-1"},
    )

    result = asyncio.run(
        data_sources._handle_data_source_register_browser_collection(
            {
                "auth_token": "token",
                "title": "千牛每日资金账单",
                "credential_username": "finance_ops@example.com",
                "credential_password": "secret",
                "playbook_body": ["not", "a", "dict"],
            }
        )
    )

    assert result == {"success": False, "error": "Playbook JSON 必须是对象"}


def test_register_browser_collection_rejects_falsey_non_dict_playbook_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        data_sources,
        "_require_user",
        lambda token: {"company_id": "company-1", "id": "user-1"},
    )

    result = asyncio.run(
        data_sources._handle_data_source_register_browser_collection(
            {
                "auth_token": "token",
                "title": "千牛每日资金账单",
                "credential_username": "finance_ops@example.com",
                "credential_password": "secret",
                "playbook_body": "",
            }
        )
    )

    assert result == {"success": False, "error": "Playbook JSON 必须是对象"}


def test_register_browser_collection_normalizes_action_internal_whitespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, dict] = {}

    monkeypatch.setattr(
        data_sources,
        "_require_user",
        lambda token: {"company_id": "company-1", "id": "user-1"},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "upsert_unified_data_source",
        lambda **kwargs: {
            "id": "source-1",
            "company_id": kwargs["company_id"],
            "code": kwargs["code"],
            "name": kwargs["name"],
            "source_kind": kwargs["source_kind"],
            "domain_type": kwargs["domain_type"],
            "provider_code": kwargs["provider_code"],
            "execution_mode": kwargs["execution_mode"],
            "status": kwargs["status"],
            "is_enabled": kwargs["is_enabled"],
            "meta": kwargs["meta"],
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "upsert_unified_data_source_dataset",
        lambda **kwargs: {
            "id": "dataset-1",
            "data_source_id": kwargs["data_source_id"],
            "dataset_code": kwargs["dataset_code"],
            "dataset_name": kwargs["dataset_name"],
            "resource_key": kwargs["resource_key"],
            "source_type": "browser_collection_records",
            "publish_status": "published",
            "meta": {"source_type": "browser_collection_records"},
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda **kwargs: {
            "id": "source-1",
            "company_id": "company-1",
            "code": "browser-collection-qn",
            "name": "千牛每日资金账单",
            "source_kind": "browser_playbook",
            "domain_type": "ecommerce",
            "provider_code": "browser_playbook",
            "execution_mode": "deterministic",
            "status": "active",
            "is_enabled": True,
            "meta": {},
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_unified_data_source_datasets",
        lambda **kwargs: [
            {
                "id": "dataset-1",
                "dataset_code": "browser-collection-qn",
                "dataset_name": "千牛每日资金账单",
                "source_type": "browser_collection_records",
                "publish_status": "published",
                "meta": {"source_type": "browser_collection_records"},
            }
        ],
    )
    monkeypatch.setattr(data_sources.auth_db, "list_unified_sync_jobs", lambda **kwargs: [])
    monkeypatch.setattr(data_sources, "_load_source_configs", lambda source_id: {})
    monkeypatch.setattr(data_sources.auth_db, "get_unified_data_source_credentials", lambda **kwargs: None)
    monkeypatch.setattr(data_sources.auth_db, "_seal_json_payload", lambda payload: "sealed-secret")
    monkeypatch.setattr(
        data_sources.auth_db,
        "upsert_playbook",
        lambda **kwargs: captured.setdefault("playbook", kwargs)
        or {
            "playbook_id": kwargs["playbook_id"],
            "version": kwargs["version"],
            "title": kwargs["title"],
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "upsert_shop_runtime_binding",
        lambda **kwargs: {"data_source_id": kwargs["data_source_id"]},
    )
    monkeypatch.setattr(data_sources.auth_db, "insert_browser_verification_sync_job", lambda **kwargs: {"id": "sync-1"})
    monkeypatch.setattr(data_sources, "_default_browser_verification_biz_date", lambda: "2026-05-20")

    result = asyncio.run(
        data_sources._handle_data_source_register_browser_collection(
            {
                "auth_token": "token",
                "title": "千牛每日资金账单",
                "credential_username": "finance_ops@example.com",
                "credential_password": "secret",
                "playbook_body": {
                    "schema_version": "1.0",
                    "steps": [{"id": "request_detail_file", "action": "c lick"}],
                },
            }
        )
    )

    assert result["success"] is True
    assert captured["playbook"]["playbook_body"]["steps"][0]["action"] == "click"


def test_register_browser_collection_rejects_unknown_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        data_sources,
        "_require_user",
        lambda token: {"company_id": "company-1", "id": "user-1"},
    )

    result = asyncio.run(
        data_sources._handle_data_source_register_browser_collection(
            {
                "auth_token": "token",
                "title": "千牛每日资金账单",
                "credential_username": "finance_ops@example.com",
                "credential_password": "secret",
                "playbook_body": {
                    "schema_version": "1.0",
                    "steps": [{"id": "bad", "action": "ask_llm"}],
                },
            }
        )
    )

    assert result["success"] is False
    assert "action 不支持" in result["error"]



def test_retry_browser_collection_creates_verification_job_from_active_binding(
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
        "get_unified_data_source_by_id",
        lambda **kwargs: {
            "id": "source-1",
            "company_id": "company-1",
            "code": "browser-collection-qn",
            "name": "千牛每日资金账单",
            "source_kind": "browser_playbook",
            "provider_code": "browser_playbook",
            "status": "active",
            "is_enabled": True,
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_unified_data_source_datasets",
        lambda **kwargs: [
            {
                "id": "dataset-1",
                "dataset_code": "browser-collection-qn",
                "dataset_name": "千牛每日资金账单",
                "source_type": "browser_collection_records",
                "resource_key": "browser-collection-qn@1",
                "publish_status": "published",
                "meta": {"source_type": "browser_collection_records"},
            }
        ],
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_shop_runtime_binding_for_source",
        lambda **kwargs: {
            "shop_id": "browser-collection-qn",
            "playbook_id": "browser-collection-qn",
            "agent_id": "browser-agent-local",
            "profile_status": "active",
            "playbook_status": "ok",
            "credential_ref": "sealed-secret",
        },
    )
    monkeypatch.setattr(
        data_sources,
        "_default_browser_verification_biz_date",
        lambda: "2026-05-20",
    )
    monkeypatch.setattr(data_sources.auth_db, "find_inflight_dataset_collection_sync_job", lambda **kwargs: None)
    monkeypatch.setattr(
        data_sources.auth_db,
        "insert_browser_verification_sync_job",
        lambda **kwargs: calls.append(("sync_job", kwargs)) or {"id": "sync-retry-1"},
    )

    result = asyncio.run(
        data_sources._handle_data_source_retry_browser_playbook_verification(
            {"auth_token": "token", "source_id": "source-1"}
        )
    )

    assert result["success"] is True
    assert result["status"] == "verification_pending"
    assert result["verification_sync_job_id"] == "sync-retry-1"
    assert result["verification_biz_date"] == "2026-05-20"
    sync_call = calls[0][1]
    assert sync_call["company_id"] == "company-1"
    assert sync_call["data_source_id"] == "source-1"
    assert sync_call["resource_key"] == "browser-collection-qn@1"
    assert sync_call["request_payload"] == {
        "dataset_id": "dataset-1",
        "dataset_code": "browser-collection-qn",
        "biz_date": "2026-05-20",
        "verification": True,
        "retry_verification": True,
        "force_collection": True,
        "skip_recent_success_reuse": True,
        "playbook_id": "browser-collection-qn",
        "playbook_version": "1",
        "collection_driver": "browser_playbook_remote",
        "params": {
            "biz_date": "2026-05-20",
            "playbook_id": "browser-collection-qn",
            "playbook_version": "1",
            "force_collection": True,
            "skip_recent_success_reuse": True,
        },
    }


def test_retry_browser_collection_reuses_inflight_job(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        data_sources,
        "_require_user",
        lambda token: {"company_id": "company-1", "id": "user-1"},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda **kwargs: {
            "id": "source-1",
            "company_id": "company-1",
            "code": "browser-collection-qn",
            "name": "千牛每日资金账单",
            "source_kind": "browser_playbook",
            "provider_code": "browser_playbook",
            "status": "active",
            "is_enabled": True,
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_unified_data_source_datasets",
        lambda **kwargs: [
            {
                "id": "dataset-1",
                "dataset_code": "browser-collection-qn",
                "dataset_name": "千牛每日资金账单",
                "source_type": "browser_collection_records",
                "resource_key": "browser-collection-qn@1",
                "publish_status": "published",
                "meta": {"source_type": "browser_collection_records"},
            }
        ],
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_shop_runtime_binding_for_source",
        lambda **kwargs: {
            "shop_id": "browser-collection-qn",
            "playbook_id": "browser-collection-qn",
            "agent_id": "browser-agent-local",
            "profile_status": "active",
            "playbook_status": "ok",
            "credential_ref": "sealed-secret",
        },
    )
    monkeypatch.setattr(
        data_sources,
        "_default_browser_verification_biz_date",
        lambda: "2026-05-20",
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "find_inflight_dataset_collection_sync_job",
        lambda **kwargs: {
            "id": "sync-running-1",
            "job_status": "running",
            "request_payload": {"dataset_id": "dataset-1", "biz_date": "2026-05-20"},
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "insert_browser_verification_sync_job",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("inflight retry must not insert a new job")),
    )
    monkeypatch.setattr(
        data_sources,
        "_build_data_source_view",
        lambda source_row, datasets=None, include_dataset_details=False: {
            "id": source_row["id"],
            "datasets": datasets or [],
        },
    )

    result = asyncio.run(
        data_sources._handle_data_source_retry_browser_playbook_verification(
            {"auth_token": "token", "source_id": "source-1", "force_collection": True}
        )
    )

    assert result["success"] is True
    assert result["status"] == "verification_pending"
    assert result["verification_sync_job_id"] == "sync-running-1"
    assert result["verification_biz_date"] == "2026-05-20"
    assert result["reused"] is True
    assert result["queued"] is True
    assert result["reuse_reason"] == "inflight"
    assert result["message"] == "同一浏览器任务正在执行或等待人工验证，已复用"


def test_retry_browser_collection_rejects_missing_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        data_sources,
        "_require_user",
        lambda token: {"company_id": "company-1", "id": "user-1"},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda **kwargs: {
            "id": "source-1",
            "company_id": "company-1",
            "code": "browser-collection-qn",
            "name": "千牛每日资金账单",
            "source_kind": "browser_playbook",
            "status": "active",
            "is_enabled": True,
        },
    )
    monkeypatch.setattr(data_sources.auth_db, "get_shop_runtime_binding_for_source", lambda **kwargs: {})

    result = asyncio.run(
        data_sources._handle_data_source_retry_browser_playbook_verification(
            {"auth_token": "token", "source_id": "source-1"}
        )
    )

    assert result == {"success": False, "error": "浏览器任务缺少运行时绑定，无法重试"}
