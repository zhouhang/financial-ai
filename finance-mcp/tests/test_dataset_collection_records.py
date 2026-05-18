from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from auth import db as auth_db


class FakeCursor:
    def __init__(self) -> None:
        self.executed_sql: list[str] = []

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        self.executed_sql.append(sql)

    def fetchone(self) -> dict[str, Any]:
        return {"inserted": False, "record_status": "updated"}


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor_obj = cursor
        self.committed = False

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def cursor(self, *args: Any, **kwargs: Any) -> FakeCursor:
        return self.cursor_obj

    def commit(self) -> None:
        self.committed = True


def _install_fake_connection(monkeypatch: Any) -> tuple[FakeConnection, FakeCursor]:
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    monkeypatch.setattr(auth_db, "get_conn", lambda: connection)
    return connection, cursor


def _sample_records() -> list[dict[str, Any]]:
    return [
        {
            "item_key": "order-1",
            "item_key_values": {"order_no": "order-1"},
            "item_hash": "hash-1",
            "payload": {"order_no": "order-1", "amount": "12.30"},
        },
        {
            "item_key": "order-2",
            "item_key_values": {"order_no": "order-2"},
            "item_hash": "hash-2",
            "payload": {"order_no": "order-2", "amount": "45.60"},
        },
        {
            "item_key": "order-3",
            "item_key_values": {"order_no": "order-3"},
            "item_hash": "hash-3",
            "payload": {"order_no": "order-3", "amount": "78.90"},
        },
    ]


def test_upsert_dataset_collection_records_uses_batch_execute_values(monkeypatch: Any) -> None:
    connection, _cursor = _install_fake_connection(monkeypatch)
    execute_values_call: dict[str, Any] = {}

    def fake_execute_values(
        cur: FakeCursor,
        sql: str,
        values: list[tuple[Any, ...]],
        template: str | None = None,
        page_size: int | None = None,
        fetch: bool = False,
    ) -> list[dict[str, Any]]:
        execute_values_call.update(
            {
                "sql": sql,
                "values": values,
                "template": template,
                "page_size": page_size,
                "fetch": fetch,
            }
        )
        return [
            {"action": "inserted"},
            {"action": "updated"},
            {"action": "unchanged"},
        ]

    monkeypatch.setattr(auth_db.psycopg2.extras, "execute_values", fake_execute_values)

    result = auth_db.upsert_dataset_collection_records(
        company_id="00000000-0000-0000-0000-000000000001",
        data_source_id="00000000-0000-0000-0000-000000000002",
        dataset_id="00000000-0000-0000-0000-000000000003",
        dataset_code="orders",
        resource_key="orders:source",
        biz_date="2026-05-16",
        sync_job_id="00000000-0000-0000-0000-000000000004",
        records=_sample_records(),
    )

    assert execute_values_call["fetch"] is True
    assert execute_values_call["page_size"] == 1000
    assert len(execute_values_call["values"]) == 3
    assert connection.committed is True
    assert result == {
        "input_count": 3,
        "upserted_count": 3,
        "inserted_count": 1,
        "updated_count": 1,
        "unchanged_count": 1,
    }


def test_upsert_dataset_collection_records_keeps_heavy_json_for_unchanged_rows(
    monkeypatch: Any,
) -> None:
    _install_fake_connection(monkeypatch)
    execute_values_call: dict[str, Any] = {}

    def fake_execute_values(
        cur: FakeCursor,
        sql: str,
        values: list[tuple[Any, ...]],
        template: str | None = None,
        page_size: int | None = None,
        fetch: bool = False,
    ) -> list[dict[str, Any]]:
        execute_values_call["sql"] = sql
        return [{"action": "unchanged"}]

    monkeypatch.setattr(auth_db.psycopg2.extras, "execute_values", fake_execute_values)

    auth_db.upsert_dataset_collection_records(
        company_id="00000000-0000-0000-0000-000000000001",
        data_source_id="00000000-0000-0000-0000-000000000002",
        dataset_id="00000000-0000-0000-0000-000000000003",
        dataset_code="orders",
        resource_key="orders:source",
        biz_date="2026-05-16",
        sync_job_id="00000000-0000-0000-0000-000000000004",
        records=_sample_records()[:1],
    )

    sql = " ".join(execute_values_call["sql"].split())
    assert (
        "item_key_values = CASE WHEN dataset_collection_records.item_hash = "
        "EXCLUDED.item_hash THEN dataset_collection_records.item_key_values "
        "ELSE EXCLUDED.item_key_values END"
    ) in sql
    assert (
        "payload = CASE WHEN dataset_collection_records.item_hash = EXCLUDED.item_hash "
        "THEN dataset_collection_records.payload ELSE EXCLUDED.payload END"
    ) in sql
