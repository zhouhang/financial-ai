"""Platform OAuth connector capability declaration."""

from __future__ import annotations

import re
from typing import Any

from connectors.base import BaseDataSourceConnector

_DATASET_CODE_PATTERN = re.compile(r"[^a-z0-9_]+")

_DEFAULT_FIXED_DATASETS = (
    {"resource_key": "orders", "dataset_name": "订单", "dataset_kind": "api_endpoint"},
    {"resource_key": "payments", "dataset_name": "支付单", "dataset_kind": "api_endpoint"},
    {"resource_key": "refunds", "dataset_name": "退款单", "dataset_kind": "api_endpoint"},
    {"resource_key": "settlements", "dataset_name": "结算单", "dataset_kind": "api_endpoint"},
)

_PLATFORM_FIXED_DATASET_OVERRIDES: dict[str, tuple[dict[str, str], ...]] = {
    "taobao": (
        {"resource_key": "tb_trades", "dataset_name": "淘宝交易单", "dataset_kind": "api_endpoint"},
        {"resource_key": "tb_payments", "dataset_name": "淘宝支付单", "dataset_kind": "api_endpoint"},
        {"resource_key": "tb_refunds", "dataset_name": "淘宝退款单", "dataset_kind": "api_endpoint"},
        {"resource_key": "tb_settlements", "dataset_name": "淘宝结算单", "dataset_kind": "api_endpoint"},
    ),
    "tmall": (
        {"resource_key": "tm_orders", "dataset_name": "天猫订单", "dataset_kind": "api_endpoint"},
        {"resource_key": "tm_payments", "dataset_name": "天猫支付单", "dataset_kind": "api_endpoint"},
        {"resource_key": "tm_refunds", "dataset_name": "天猫退款单", "dataset_kind": "api_endpoint"},
        {"resource_key": "tm_settlements", "dataset_name": "天猫结算单", "dataset_kind": "api_endpoint"},
    ),
    "douyin_shop": (
        {"resource_key": "dy_orders", "dataset_name": "抖店订单", "dataset_kind": "api_endpoint"},
        {"resource_key": "dy_payments", "dataset_name": "抖店支付单", "dataset_kind": "api_endpoint"},
        {"resource_key": "dy_refunds", "dataset_name": "抖店退款单", "dataset_kind": "api_endpoint"},
        {"resource_key": "dy_settlements", "dataset_name": "抖店结算单", "dataset_kind": "api_endpoint"},
    ),
}


def _sanitize_dataset_code(*parts: str) -> str:
    text = "_".join(part.strip().lower() for part in parts if part and part.strip())
    text = _DATASET_CODE_PATTERN.sub("_", text).strip("_")
    if not text:
        return "platform_dataset"
    return text[:120]


class PlatformOAuthConnector(BaseDataSourceConnector):
    source_kind = "platform_oauth"
    execution_mode = "deterministic"

    @property
    def capabilities(self) -> list[str]:
        return [
            "test",
            "authorize",
            "callback",
            "discover",
            "sync",
            "preview",
            "collection_records",
        ]

    def test_connection(self, arguments):
        return {
            "success": True,
            "source_id": self.ctx.source_id,
            "provider_code": self.ctx.provider_code,
            "message": "平台连接器可用，测试动作由 platform_* 工具执行",
        }

    def discover_datasets(self, arguments: dict[str, Any]) -> dict[str, Any]:
        provider_code = str(self.ctx.provider_code or "").strip().lower()
        templates = _PLATFORM_FIXED_DATASET_OVERRIDES.get(provider_code) or _DEFAULT_FIXED_DATASETS
        datasets: list[dict[str, Any]] = []
        for item in templates:
            resource_key = str(item.get("resource_key") or "").strip()
            dataset_name = str(item.get("dataset_name") or resource_key).strip()
            dataset_kind = str(item.get("dataset_kind") or "api_endpoint").strip()
            datasets.append(
                {
                    "dataset_code": _sanitize_dataset_code(provider_code, resource_key),
                    "dataset_name": dataset_name[:255],
                    "resource_key": resource_key or dataset_name,
                    "dataset_kind": dataset_kind,
                    "origin_type": "fixed",
                    "extract_config": {
                        "provider_code": provider_code,
                        "resource_key": resource_key,
                    },
                    "schema_summary": {
                        "source": "platform_fixed_template",
                        "columns": [],
                    },
                    "sync_strategy": {"mode": "incremental"},
                    "meta": {"discovered_by": "platform_oauth_connector"},
                }
            )

        return {
            "success": True,
            "source_id": self.ctx.source_id,
            "provider_code": provider_code,
            "datasets": datasets,
            "dataset_count": len(datasets),
            "message": f"已生成 {len(datasets)} 个平台固定数据集模板",
        }
