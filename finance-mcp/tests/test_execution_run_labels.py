from __future__ import annotations

import sys
from pathlib import Path

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from auth import db as auth_db


class FakeCursor:
    def __init__(self) -> None:
        self.sql: list[str] = []
        self.params: list[tuple] = []

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str, params: tuple | None = None) -> None:
        self.sql.append(sql)
        self.params.append(params or ())

    def fetchall(self) -> list[dict[str, object]]:
        return [
            {
                "id": "run-001",
                "company_id": "company-001",
                "run_code": "run-code-001",
                "scheme_code": "scheme-001",
                "plan_code": "plan-001",
                "scheme_type": "recon",
                "trigger_type": "schedule",
                "entry_mode": "dataset",
                "execution_status": "running",
                "failed_stage": "",
                "failed_reason": "",
                "run_context_json": {},
                "source_snapshot_json": {},
                "subtasks_json": [],
                "proc_result_json": {},
                "recon_result_summary_json": {},
                "artifacts_json": {},
                "anomaly_count": 0,
                "started_at": None,
                "finished_at": None,
                "created_at": None,
                "updated_at": None,
                "plan_name": "店铺资金对账",
                "scheme_name": "店铺资金对账方案",
            }
        ]


class FakeConn:
    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor_obj = cursor

    def __enter__(self) -> "FakeConn":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def cursor(self, *args, **kwargs) -> FakeCursor:
        return self.cursor_obj


class FakeConnManager:
    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor = cursor

    def __enter__(self) -> FakeConn:
        return FakeConn(self.cursor)

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_list_execution_runs_returns_plan_and_scheme_names(monkeypatch) -> None:
    cursor = FakeCursor()
    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConnManager(cursor))

    runs = auth_db.list_execution_runs(company_id="company-001")

    sql = "\n".join(cursor.sql)
    assert "LEFT JOIN execution_run_plans" in sql
    assert "LEFT JOIN execution_schemes" in sql
    assert "plan.plan_name" in sql
    assert "scheme.scheme_name" in sql
    assert runs[0]["plan_name"] == "店铺资金对账"
    assert runs[0]["scheme_name"] == "店铺资金对账方案"
