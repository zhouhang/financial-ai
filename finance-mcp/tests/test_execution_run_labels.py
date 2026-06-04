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
        self.fetchone_results: list[dict[str, object] | None] = []
        self.fetchall_results: list[list[dict[str, object]]] = []

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str, params: tuple | None = None) -> None:
        self.sql.append(sql)
        self.params.append(params or ())

    def fetchall(self) -> list[dict[str, object]]:
        if self.fetchall_results:
            return self.fetchall_results.pop(0)
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

    def fetchone(self) -> dict[str, object] | None:
        if self.fetchone_results:
            return self.fetchone_results.pop(0)
        return None


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


def test_run_exceptions_returns_current_run_scheme_for_display(monkeypatch) -> None:
    from tools import execution_runs

    cursor = FakeCursor()
    cursor.fetchone_results = [
        {
            "id": "run-001",
            "company_id": "company-001",
            "scheme_code": "scheme-outside-first-page",
            "run_context_json": {},
        },
        {
            "id": "scheme-001",
            "company_id": "company-001",
            "scheme_code": "scheme-outside-first-page",
            "scheme_name": "tb0131100248订单对账",
            "scheme_type": "recon",
            "description": "",
            "file_rule_code": "",
            "proc_rule_code": "",
            "recon_rule_code": "",
            "scheme_meta_json": {
                "dataset_bindings": {
                    "left": [{"business_name": "交易订单明细表"}],
                    "right": [{"business_name": "tb0131100248-店铺订单"}],
                }
            },
            "is_enabled": True,
            "created_by": "user-001",
            "created_at": None,
            "updated_at": None,
        },
    ]
    cursor.fetchall_results = [
        [
            {
                "id": "exception-001",
                "company_id": "company-001",
                "run_id": "run-001",
                "scheme_code": "scheme-outside-first-page",
                "anomaly_key": "source-only-001",
                "anomaly_type": "source_only",
                "summary": "",
                "detail_json": {},
                "owner_name": "",
                "owner_identifier": "",
                "owner_contact_json": {},
                "reminder_status": "pending",
                "processing_status": "pending",
                "fix_status": "pending",
                "latest_feedback": "",
                "feedback_json": {},
                "is_closed": False,
                "created_at": None,
                "updated_at": None,
            }
        ],
    ]
    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConnManager(cursor))
    monkeypatch.setattr(
        execution_runs,
        "_require_user",
        lambda _token: {"company_id": "company-001"},
    )
    monkeypatch.setattr(
        execution_runs,
        "hydrate_execution_exception_details",
        lambda *, run, scheme, exceptions: exceptions,
    )

    result = execution_runs._run_exceptions({"auth_token": "token", "run_id": "run-001"})

    assert result["success"] is True
    assert result["scheme"]["scheme_code"] == "scheme-outside-first-page"
    assert result["scheme"]["scheme_meta_json"]["dataset_bindings"]["left"][0]["business_name"] == "交易订单明细表"
