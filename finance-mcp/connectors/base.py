"""Base connector contracts for unified data sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ConnectorContext:
    source_id: str
    company_id: str
    source_kind: str
    provider_code: str
    execution_mode: str
    config: dict[str, Any] = field(default_factory=dict)


class BaseDataSourceConnector(ABC):
    """Common contract for all source-kind/provider connectors."""

    source_kind: str
    provider_code: str
    execution_mode: str = "deterministic"

    def __init__(self, ctx: ConnectorContext):
        self.ctx = ctx

    @property
    def capabilities(self) -> list[str]:
        return ["test", "discover", "sync", "preview", "published_snapshot"]

    @abstractmethod
    def test_connection(self, arguments: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def authorize(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "success": False,
            "error": "unsupported",
            "message": f"{self.source_kind}/{self.provider_code} 不支持授权动作",
        }

    def handle_callback(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "success": False,
            "error": "unsupported",
            "message": f"{self.source_kind}/{self.provider_code} 不支持回调处理",
        }

    def discover_datasets(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "success": False,
            "source_id": self.ctx.source_id,
            "provider_code": self.ctx.provider_code,
            "datasets": [],
            "dataset_count": 0,
            "error": "unsupported",
            "message": f"{self.source_kind}/{self.provider_code} 不支持自动发现数据集",
        }

    def trigger_sync(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "success": True,
            "source_id": self.ctx.source_id,
            "rows_ingested": 0,
            "payload": {},
            "message": "同步执行完成（占位实现）",
        }

    def preview(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "success": True,
            "source_id": self.ctx.source_id,
            "columns": [],
            "rows": [],
            "message": "暂无预览数据",
        }
