"""Tests for bulk_create_execution_run_exceptions in auth/db.py.

TDD RED phase: these tests must fail until the implementation is added.
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
# Fake DB plumbing (same pattern as test_recon_rollup_db.py)
# ---------------------------------------------------------------------------

class _FakeCursor:
    def __init__(self, captured: dict[str, Any]) -> None:
        self.captured = captured
        self._row_counter = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None) -> None:
        self.captured.setdefault("queries", []).append(
            {"sql": str(sql), "params": params}
        )

    def executemany(self, sql, seq_of_params) -> None:
        self.captured.setdefault("executemany_calls", []).append(
            {"sql": str(sql), "params": list(seq_of_params)}
        )
        self._row_counter += len(list.__new__(list))  # noop – count tracked elsewhere

    def fetchall(self) -> list[dict[str, object]]:
        return self.captured.get("_fetchall_return", [])

    def fetchone(self):
        return None


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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

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


def test_bulk_create_returns_created_count_equal_to_input_length(monkeypatch) -> None:
    """bulk_create_execution_run_exceptions 返回的 created 数量等于输入条数。"""
    exceptions = [_make_exception(i) for i in range(1, 251)]  # 250 条
    captured: dict[str, Any] = {}
    # executemany 无法 RETURNING，所以函数应返回 len(exceptions)
    _patch_conn(monkeypatch, captured)

    created = auth_db.bulk_create_execution_run_exceptions(
        company_id="company-001",
        run_id="run-001",
        scheme_code="scheme-001",
        exceptions=exceptions,
    )

    assert created == 250, f"期望 250，实际 {created}"


def test_bulk_create_uses_executemany_not_individual_executes(monkeypatch) -> None:
    """批量函数必须使用 executemany（或等价批量 INSERT），不能逐条 execute。"""
    exceptions = [_make_exception(i) for i in range(1, 6)]  # 5 条
    captured: dict[str, Any] = {}
    _patch_conn(monkeypatch, captured)

    auth_db.bulk_create_execution_run_exceptions(
        company_id="company-001",
        run_id="run-001",
        scheme_code="scheme-001",
        exceptions=exceptions,
    )

    # 必须有 executemany 调用
    calls = captured.get("executemany_calls", [])
    assert len(calls) >= 1, "bulk_create 必须调用 executemany，不能只用逐条 execute"


def test_bulk_create_splits_into_batches_of_1000(monkeypatch) -> None:
    """超过 1000 条时应分批，每批 <= 1000 条。"""
    # 2500 条应分 3 批
    exceptions = [_make_exception(i) for i in range(1, 2501)]
    captured: dict[str, Any] = {}

    # 为让分批逻辑可验证，executemany 需要能被我们数到行数
    executemany_batches: list[int] = []

    class _CountingCursor(_FakeCursor):
        def executemany(self, sql, seq_of_params) -> None:  # type: ignore[override]
            rows = list(seq_of_params)
            executemany_batches.append(len(rows))
            captured.setdefault("executemany_calls", []).append(
                {"sql": str(sql), "params": rows}
            )

    class _CountingConn(_FakeConn):
        def __init__(self, c):
            super().__init__(c)
            self._cursor = _CountingCursor(c)

    monkeypatch.setattr(auth_db, "get_conn", lambda: _CountingConn(captured))

    created = auth_db.bulk_create_execution_run_exceptions(
        company_id="company-001",
        run_id="run-001",
        scheme_code="scheme-001",
        exceptions=exceptions,
    )

    assert created == 2500
    assert len(executemany_batches) == 3, (
        f"2500 条应分 3 批，实际 {len(executemany_batches)} 批: {executemany_batches}"
    )
    assert all(b <= 1000 for b in executemany_batches), (
        f"每批不超过 1000 条，实际: {executemany_batches}"
    )
    assert sum(executemany_batches) == 2500


def test_bulk_create_empty_list_returns_zero(monkeypatch) -> None:
    """空列表时不应报错，直接返回 0。"""
    captured: dict[str, Any] = {}
    _patch_conn(monkeypatch, captured)

    created = auth_db.bulk_create_execution_run_exceptions(
        company_id="company-001",
        run_id="run-001",
        scheme_code="scheme-001",
        exceptions=[],
    )

    assert created == 0
    assert captured.get("executemany_calls") is None, "空列表不应调用 executemany"
