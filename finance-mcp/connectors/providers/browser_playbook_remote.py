"""Deterministic browser playbook connector declaration."""

from __future__ import annotations

from connectors.base import BaseDataSourceConnector


class BrowserPlaybookRemoteConnector(BaseDataSourceConnector):
    source_kind = "browser_playbook"
    provider_code = "qianniu"
    execution_mode = "deterministic"

    @property
    def capabilities(self) -> list[str]:
        return ["test", "discover", "sync", "collection_records"]

    def test_connection(self, arguments: dict) -> dict:
        return {
            "success": True,
            "source_id": self.ctx.source_id,
            "source_kind": self.source_kind,
            "provider_code": self.provider_code,
            "execution_mode": self.execution_mode,
            "message": "browser_playbook 数据源已配置，实际采集由 Production Push Dispatcher 执行",
        }

    def trigger_sync(self, arguments: dict) -> dict:
        return {
            "success": True,
            "source_id": self.ctx.source_id,
            "queued": True,
            "message": "browser_playbook sync job 已创建，等待 Dispatcher 执行",
        }

