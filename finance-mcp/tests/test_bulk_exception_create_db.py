"""Tests for bulk_create_execution_run_exceptions in auth/db.py.

Uses monkeypatching on psycopg2.extras.execute_values (same pattern as
test_recon_rollup_db.py) so these tests don't need a real DB connection.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

import psycopg2.extras

from auth import db as auth_db


# ---------------------------------------------------------------------------
# Fake DB plumbing
# ---------------------------------------------------------------------------

class _FakeCursor:
    def __init__(self, captured: dict[str, Any]) -> None:
        self.captured = captured

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None) -> None:
        self.captured.setdefault("queries", []).append({"sql": str(sql), "params": params})

    def fetchall(self) -> list[dict[str, object]]:
        return self.captured.get("_fetchall_return", [])


class _FakeConn:
    def __init__(self, captured: dict[str, Any]) -> None:
        self.captured = captured
        self._cursor = _FakeCursor(captured)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self, *args, **kwargs):
        return self._cursor

    def commit(self) -> None:
        self.captured["committed"] = True


def _patch_conn(monkeypatch, captured: dict[str, Any] | None = None) -> dict[str, Any]:
    if captured is None:
        captured = {}
    monkeypatch.setattr(auth_db, "get_conn", lambda: _FakeConn(captured))
    return captured


def _make_exception(idx: int) -> dict[str, object]:
    return {
        "anomaly_key": f"key-{idx}",
        "anomaly_type": "source_only",
        "summary": f"差异摘要 {idx}",
        "detail_json": {"订单号": f"ORD-{idx}"},
        "owner_name": "财务负责人",
        "owner_identifier": f"ding-user-{idx % 3}",
        "owner_contact_json": {},
        "reminder_status": "pending",
        "processing_status": "pending",
        "fix_status": "pending",
        "latest_feedback": "",
        "feedback_json": {},
        "is_closed": False,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_bulk_create_returns_list_of_id_and_anomaly_key(monkeypatch) -> None:
    """bulk_create_execution_run_exceptions 返回 [{id, anomaly_key}] 列表。"""
    exceptions = [_make_exception(i) for i in range(1, 4)]
    returning_rows = [
        {"id": str(i), "anomaly_key": f"key-{i}"} for i in range(1, 4)
    ]
    captured: dict[str, Any] = {}
    _patch_conn(monkeypatch, captured)

    def fake_execute_values(cur, sql, values, template=None, page_size=None, fetch=False):
        captured["execute_values_called"] = True
        captured["fetch"] = fetch
        if fetch:
            return returning_rows
        return None

    monkeypatch.setattr(auth_db.psycopg2.extras, "execute_values", fake_execute_values)

    result = auth_db.bulk_create_execution_run_exceptions(
        company_id="company-001",
        run_id="run-001",
        scheme_code="scheme-001",
        exceptions=exceptions,
    )

    assert isinstance(result, list), f"应返回列表，实际 {type(result)}"
    assert len(result) == 3, f"期望 3 条，实际 {len(result)}"
    for row in result:
        assert "id" in row
        assert "anomaly_key" in row
    assert captured.get("execute_values_called") is True
    assert captured.get("fetch") is True


def test_bulk_create_uses_execute_values_not_executemany(monkeypatch) -> None:
    """批量函数必须使用 execute_values（带 fetch=True），不能再用 executemany。"""
    exceptions = [_make_exception(i) for i in range(1, 6)]
    execute_values_calls: list[dict] = []
    captured: dict[str, Any] = {}
    _patch_conn(monkeypatch, captured)

    def fake_execute_values(cur, sql, values, template=None, page_size=None, fetch=False):
        execute_values_calls.append({"fetch": fetch, "value_count": len(list(values))})
        return [{"id": str(i), "anomaly_key": f"key-{i}"} for i in range(1, 6)] if fetch else None

    monkeypatch.setattr(auth_db.psycopg2.extras, "execute_values", fake_execute_values)

    auth_db.bulk_create_execution_run_exceptions(
        company_id="company-001",
        run_id="run-001",
        scheme_code="scheme-001",
        exceptions=exceptions,
    )

    assert len(execute_values_calls) >= 1, "bulk_create 应调用 execute_values"
    assert all(call["fetch"] is True for call in execute_values_calls), (
        "execute_values 必须以 fetch=True 调用以获取 RETURNING 行"
    )
    # 不应调用 executemany
    assert captured.get("executemany_calls") is None, (
        "bulk_create 已改用 execute_values，不应再调用 executemany"
    )


def test_bulk_create_splits_into_batches_of_1000(monkeypatch) -> None:
    """超过 1000 条时应分批，每批 <= 1000 条。"""
    n = 2500
    exceptions = [_make_exception(i) for i in range(1, n + 1)]
    execute_values_calls: list[int] = []
    captured: dict[str, Any] = {}
    _patch_conn(monkeypatch, captured)

    def fake_execute_values(cur, sql, values, template=None, page_size=None, fetch=False):
        batch = list(values)
        execute_values_calls.append(len(batch))
        return [{"id": str(i), "anomaly_key": f"k-{i}"} for i in range(len(batch))] if fetch else None

    monkeypatch.setattr(auth_db.psycopg2.extras, "execute_values", fake_execute_values)

    result = auth_db.bulk_create_execution_run_exceptions(
        company_id="company-001",
        run_id="run-001",
        scheme_code="scheme-001",
        exceptions=exceptions,
    )

    assert isinstance(result, list)
    # 2500 条应分 3 批（1000+1000+500）
    assert len(execute_values_calls) == 3, (
        f"2500 条应分 3 批，实际 {len(execute_values_calls)} 批: {execute_values_calls}"
    )
    assert all(b <= 1000 for b in execute_values_calls), (
        f"每批不超过 1000 条，实际: {execute_values_calls}"
    )
    assert sum(execute_values_calls) == 2500


def test_bulk_create_empty_list_returns_empty(monkeypatch) -> None:
    """空列表时不应报错，直接返回 []。"""
    captured: dict[str, Any] = {}
    _patch_conn(monkeypatch, captured)
    execute_values_calls: list = []

    def fake_execute_values(cur, sql, values, template=None, page_size=None, fetch=False):
        execute_values_calls.append(True)
        return []

    monkeypatch.setattr(auth_db.psycopg2.extras, "execute_values", fake_execute_values)

    result = auth_db.bulk_create_execution_run_exceptions(
        company_id="company-001",
        run_id="run-001",
        scheme_code="scheme-001",
        exceptions=[],
    )

    assert result == []
    assert len(execute_values_calls) == 0, "空列表不应调用 execute_values"
