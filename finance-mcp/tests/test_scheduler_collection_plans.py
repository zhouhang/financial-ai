from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from tools import data_sources


@pytest.mark.anyio
async def test_scheduler_collection_plans_include_taobao_two_hour_cron(monkeypatch) -> None:
    monkeypatch.setattr(
        data_sources,
        "_require_scheduler_user",
        lambda token: {"role": "system", "company_id": "company-1"},
    )
    monkeypatch.setattr(
        data_sources,
        "_list_datasets_with_compat",
        lambda **kwargs: [
            {
                "id": "dataset-1",
                "data_source_id": "source-1",
                "dataset_code": "taobao_order_lines_shop_1",
                "dataset_name": "淘宝/天猫订单明细 - 旗舰店",
                "resource_key": "taobao_order_lines:shop-1",
                "extract_config": {
                    "storage": "platform_order_lines",
                    "date_field": "biz_date",
                },
                "sync_strategy": {
                    "schedule_type": "cron",
                    "schedule_expr": "0 */2 * * *",
                },
                "publish_status": "published",
                "is_enabled": True,
            }
        ],
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda company_id, data_source_id: {
            "id": data_source_id,
            "status": "active",
            "is_enabled": True,
        },
    )
    monkeypatch.setattr(
        data_sources,
        "_build_dataset_view",
        lambda row, include_heavy=False: {"business_name": row["dataset_name"]},
    )

    result = await data_sources._handle_data_source_scheduler_list_collection_plans(
        {"auth_token": "scheduler-token"}
    )

    assert result["success"] is True
    assert result["count"] == 1
    plan = result["collection_plans"][0]
    assert plan["dataset_id"] == "dataset-1"
    assert plan["resource_key"] == "taobao_order_lines:shop-1"
    assert plan["schedule_type"] == "cron"
    assert plan["schedule_expr"] == "0 */2 * * *"
    assert plan["date_field"] == "biz_date"
