"""File source connector."""

from __future__ import annotations

from connectors.base import BaseDataSourceConnector


class FileConnector(BaseDataSourceConnector):
    source_kind = "file"
    execution_mode = "deterministic"

    @property
    def capabilities(self) -> list[str]:
        return ["test", "discover", "sync", "preview", "published_snapshot", "upload"]

    def test_connection(self, arguments):
        cfg = self.ctx.config.get("connection_config") or {}
        # For file sources, local path or upload strategy must exist.
        path = str(cfg.get("base_path") or "").strip()
        upload_mode = str(cfg.get("upload_mode") or "").strip()
        if not path and not upload_mode:
            return {"success": False, "error": "file 配置缺失: base_path 或 upload_mode"}
        return {
            "success": True,
            "source_id": self.ctx.source_id,
            "message": "文件数据源配置校验通过",
        }

    def discover_datasets(self, arguments: dict[str, object]) -> dict[str, object]:
        cfg = self.ctx.config.get("connection_config") or {}
        base_path = str(cfg.get("base_path") or "").strip()
        upload_mode = str(cfg.get("upload_mode") or "manual").strip() or "manual"
        dataset_name = str(arguments.get("dataset_name") or "文件上传数据集").strip() or "文件上传数据集"
        dataset_code = str(arguments.get("dataset_code") or "file_upload_default").strip() or "file_upload_default"
        return {
            "success": True,
            "source_id": self.ctx.source_id,
            "provider_code": self.ctx.provider_code,
            "datasets": [
                {
                    "dataset_code": dataset_code,
                    "dataset_name": dataset_name[:255],
                    "resource_key": "default",
                    "dataset_kind": "file_collection",
                    "origin_type": "manual",
                    "extract_config": {
                        "upload_mode": upload_mode,
                        "base_path": base_path,
                    },
                    "schema_summary": {"source": "file_source", "columns": []},
                    "sync_strategy": {"mode": "full"},
                    "meta": {"discovered_by": "file_connector"},
                }
            ],
            "dataset_count": 1,
            "message": "文件数据源使用单数据集占位定义，请在上层配置字段映射",
        }
