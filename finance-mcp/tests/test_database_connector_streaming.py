from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from connectors.base import ConnectorContext
from connectors.providers.database import DatabaseConnector


class FakeCursor:
    def __init__(self) -> None:
        self.fetchmany_sizes: list[int] = []
        self.executed = False
        self.itersize: int | None = None
        self._batches = [
            [{"order_no": "A001"}],
            [{"order_no": "A002"}],
            [],
        ]

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def execute(self, query: object, params: list[Any]) -> None:
        self.executed = True

    def fetchmany(self, size: int) -> list[dict[str, Any]]:
        self.fetchmany_sizes.append(size)
        return self._batches.pop(0)

    def fetchall(self) -> list[dict[str, Any]]:
        raise AssertionError("streaming sync must not call fetchall")


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor_obj = cursor
        self.closed = False

    def cursor(self, *args: Any, **kwargs: Any) -> FakeCursor:
        return self.cursor_obj

    def close(self) -> None:
        self.closed = True


class FakeMysqlDiscoverCursor:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.params: list[tuple[Any, ...]] = []
        self.fetchall_calls = 0

    def __enter__(self) -> "FakeMysqlDiscoverCursor":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def execute(self, query: str, params: tuple[Any, ...]) -> None:
        normalized_query = " ".join(query.split())
        assert "IN ()" not in normalized_query
        self.queries.append(normalized_query)
        self.params.append(params)

    def fetchone(self) -> dict[str, Any]:
        return {"TOTAL_COUNT": 1}

    def fetchall(self) -> list[dict[str, Any]]:
        self.fetchall_calls += 1
        if self.fetchall_calls == 1:
            return [
                {
                    "TABLE_SCHEMA": "fuyou",
                    "TABLE_NAME": "orders",
                    "TABLE_TYPE": "BASE TABLE",
                }
            ]
        if self.fetchall_calls == 2:
            return [
                {
                    "TABLE_SCHEMA": "fuyou",
                    "TABLE_NAME": "orders",
                    "COLUMN_NAME": "id",
                    "DATA_TYPE": "bigint",
                    "IS_NULLABLE": "NO",
                    "ORDINAL_POSITION": 1,
                },
                {
                    "TABLE_SCHEMA": "fuyou",
                    "TABLE_NAME": "orders",
                    "COLUMN_NAME": "amount",
                    "DATA_TYPE": "decimal",
                    "IS_NULLABLE": "YES",
                    "ORDINAL_POSITION": 2,
                },
            ]
        if self.fetchall_calls == 3:
            return [
                {
                    "TABLE_SCHEMA": "fuyou",
                    "TABLE_NAME": "orders",
                    "COLUMN_NAME": "id",
                    "ORDINAL_POSITION": 1,
                }
            ]
        raise AssertionError("unexpected fetchall call")


class FakeMysqlDiscoverConnection:
    def __init__(self, cursor: FakeMysqlDiscoverCursor) -> None:
        self.cursor_obj = cursor
        self.closed = False

    def cursor(self) -> FakeMysqlDiscoverCursor:
        return self.cursor_obj

    def close(self) -> None:
        self.closed = True


def test_database_connector_iter_sync_batches_uses_fetchmany(monkeypatch: Any) -> None:
    connector = DatabaseConnector(
        ConnectorContext(
            source_id="source-1",
            company_id="company-1",
            source_kind="database",
            provider_code="postgresql",
            execution_mode="deterministic",
            config={
                "connection_config": {
                    "db_type": "postgresql",
                    "host": "localhost",
                    "port": "5432",
                    "database": "tally",
                    "username": "user",
                    "password": "pass",
                }
            },
        )
    )
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    monkeypatch.setattr(connector, "_connect_postgresql", lambda cfg: connection)

    batches = list(
        connector.iter_sync_batches(
            {
                "resource_key": "public.orders",
                "params": {
                    "query": {
                        "resource_key": "public.orders",
                    }
                },
            },
            batch_size=1,
        )
    )

    assert batches == [[{"order_no": "A001"}], [{"order_no": "A002"}]]
    assert cursor.executed is True
    assert cursor.fetchmany_sizes == [1, 1, 1]
    assert cursor.itersize == 1
    assert connection.closed is True


def test_database_connector_discovers_mysql_metadata_with_uppercase_keys(
    monkeypatch: Any,
) -> None:
    connector = DatabaseConnector(
        ConnectorContext(
            source_id="source-1",
            company_id="company-1",
            source_kind="database",
            provider_code="mysql",
            execution_mode="deterministic",
            config={
                "connection_config": {
                    "db_type": "mysql",
                    "host": "localhost",
                    "port": "3306",
                    "database": "fuyou",
                    "username": "user",
                    "password": "pass",
                }
            },
        )
    )
    cursor = FakeMysqlDiscoverCursor()
    connection = FakeMysqlDiscoverConnection(cursor)
    monkeypatch.setattr(connector, "_connect_mysql", lambda cfg: connection)

    result = connector.discover_datasets({"limit": 10, "offset": 0})

    assert result["success"] is True
    assert result["scan_summary"]["total_count"] == 1
    assert result["dataset_count"] == 1
    assert result["datasets"][0]["resource_key"] == "fuyou.orders"
    assert result["datasets"][0]["schema_summary"]["columns"] == [
        {"name": "id", "data_type": "bigint", "nullable": False},
        {"name": "amount", "data_type": "decimal", "nullable": True},
    ]
    assert result["datasets"][0]["schema_summary"]["primary_keys"] == ["id"]
    assert connection.closed is True
