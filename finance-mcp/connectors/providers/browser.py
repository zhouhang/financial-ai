"""Agent-assisted browser connector placeholder."""

from __future__ import annotations

from connectors.base import BaseDataSourceConnector


class BrowserConnector(BaseDataSourceConnector):
    source_kind = "browser"
    execution_mode = "agent_assisted"

    @property
    def capabilities(self) -> list[str]:
        return ["agent_assisted", "test", "discover"]

    def test_connection(self, arguments):
        return {
            "success": True,
            "source_id": self.ctx.source_id,
            "execution_mode": self.execution_mode,
            "message": "browser 数据源为 agent_assisted 占位能力，一期不执行真实抓取",
        }

    def trigger_sync(self, arguments):
        return {
            "success": False,
            "error": "agent_assisted_required",
            "execution_mode": self.execution_mode,
            "message": "browser 抓取需要 agent loop 决策后调用执行器，一期未开放固定同步",
        }

    def discover_datasets(self, arguments: dict[str, object]) -> dict[str, object]:
        dataset_name = str(arguments.get("dataset_name") or "浏览器抓取数据集").strip() or "浏览器抓取数据集"
        return {
            "success": True,
            "source_id": self.ctx.source_id,
            "provider_code": self.ctx.provider_code,
            "datasets": [
                {
                    "dataset_code": "browser_agent_collected_default",
                    "dataset_name": dataset_name[:255],
                    "resource_key": "default",
                    "dataset_kind": "agent_collected",
                    "origin_type": "manual",
                    "extract_config": {"execution_mode": self.execution_mode},
                    "schema_summary": {"source": "browser_agent_assisted", "columns": []},
                    "sync_strategy": {"mode": "agent_assisted"},
                    "meta": {"discovered_by": "browser_connector"},
                }
            ],
            "dataset_count": 1,
            "message": "browser 数据集为 agent_assisted 占位定义，需要上层 agent 执行流程驱动",
        }
