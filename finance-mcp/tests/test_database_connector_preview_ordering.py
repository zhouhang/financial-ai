from __future__ import annotations

import sys
from pathlib import Path

MCP_ROOT = Path(__file__).resolve().parents[1]
if str(MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_ROOT))

from connectors.base import ConnectorContext
from connectors.providers.database import DatabaseConnector


def _connector() -> DatabaseConnector:
    return DatabaseConnector(
        ConnectorContext(
            source_id="source-db-1",
            company_id="company-1",
            source_kind="database",
            provider_code="postgresql",
            execution_mode="deterministic",
            config={
                "connection_config": {
                    "db_type": "postgresql",
                    "host": "localhost",
                    "port": 5432,
                    "database": "tally",
                    "username": "user",
                    "password": "pass",
                }
            },
        )
    )


def test_preview_orders_by_configured_date_field(monkeypatch):
    captured: dict[str, object] = {}
    connector = _connector()

    def fake_preview_postgresql(cfg, schema_name, table_name, limit, order_field=None):
        captured.update(
            {
                "schema_name": schema_name,
                "table_name": table_name,
                "limit": limit,
                "order_field": order_field,
            }
        )
        return [{"id": 2, "updated_at": "2026-06-11"}]

    monkeypatch.setattr(connector, "_preview_postgresql", fake_preview_postgresql)

    result = connector.preview(
        {
            "resource_key": "public.orders",
            "limit": 10,
            "dataset": {
                "schema_summary": {"fields": ["id", "updated_at"]},
                "collection_config": {"date_field": "updated_at"},
            },
        }
    )

    assert result["success"] is True
    assert result["rows"] == [{"id": 2, "updated_at": "2026-06-11"}]
    assert result["preview_order"] == {
        "order": "date_field_desc",
        "order_field": "updated_at",
    }
    assert captured["schema_name"] == "public"
    assert captured["table_name"] == "orders"
    assert captured["limit"] == 10
    assert captured["order_field"] == "updated_at"


def test_preview_marks_default_order_when_no_sort_field(monkeypatch):
    connector = _connector()
    monkeypatch.setattr(
        connector,
        "_preview_postgresql",
        lambda cfg, schema_name, table_name, limit, order_field=None: [{"name": "A"}],
    )

    result = connector.preview(
        {
            "resource_key": "public.lookup_values",
            "limit": 10,
            "dataset": {"schema_summary": {"fields": [{"name": "name", "type": "text"}]}},
        }
    )

    assert result["success"] is True
    assert result["preview_order"] == {
        "order": "connector_default",
        "order_field": "",
    }
