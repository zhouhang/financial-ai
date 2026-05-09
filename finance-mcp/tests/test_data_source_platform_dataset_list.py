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
