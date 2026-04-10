"""Connector factory for unified data_source tools."""

from __future__ import annotations

from typing import Any

from connectors.base import BaseDataSourceConnector, ConnectorContext
from connectors.providers import (
    ApiConnector,
    BrowserConnector,
    DatabaseConnector,
    DesktopCliConnector,
    FileConnector,
    PlatformOAuthConnector,
)

_DEFAULT_CONNECTOR_BY_KIND: dict[str, type[BaseDataSourceConnector]] = {
    "platform_oauth": PlatformOAuthConnector,
    "database": DatabaseConnector,
    "api": ApiConnector,
    "file": FileConnector,
    "browser": BrowserConnector,
    "desktop_cli": DesktopCliConnector,
}

# Provider-level registry for future expansion.
# Phase-1 currently uses generic connectors for each source_kind.
_CONNECTOR_BY_KIND_PROVIDER: dict[tuple[str, str], type[BaseDataSourceConnector]] = {}


def build_connector(source_record: dict[str, Any]) -> BaseDataSourceConnector:
    source_kind = str(source_record.get("source_kind") or "").strip()
    provider_code = str(source_record.get("provider_code") or "").strip()
    execution_mode = str(source_record.get("execution_mode") or "").strip() or _default_execution_mode(source_kind)
    ctx = ConnectorContext(
        source_id=str(source_record.get("id") or ""),
        company_id=str(source_record.get("company_id") or ""),
        source_kind=source_kind,
        provider_code=provider_code,
        execution_mode=execution_mode,
        config={
            "auth_config": source_record.get("auth_config") or {},
            "connection_config": source_record.get("connection_config") or {},
            "extract_config": source_record.get("extract_config") or {},
            "mapping_config": source_record.get("mapping_config") or {},
            "runtime_config": source_record.get("runtime_config") or {},
        },
    )

    connector_cls = _CONNECTOR_BY_KIND_PROVIDER.get((source_kind, provider_code))
    if not connector_cls:
        connector_cls = _DEFAULT_CONNECTOR_BY_KIND.get(source_kind)
    if connector_cls:
        return connector_cls(ctx)
    raise ValueError(f"不支持的 source_kind: {source_kind}")


def _default_execution_mode(source_kind: str) -> str:
    if source_kind in {"browser", "desktop_cli"}:
        return "agent_assisted"
    return "deterministic"
