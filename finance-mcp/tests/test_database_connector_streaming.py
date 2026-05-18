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
