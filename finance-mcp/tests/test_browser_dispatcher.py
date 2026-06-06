from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) in sys.path:
    sys.path.remove(str(FINANCE_MCP_ROOT))
sys.path.insert(0, str(FINANCE_MCP_ROOT))

from browser_playbook.agent_connection import FakeAgentConnectionManager
from browser_playbook.dispatcher import BrowserPlaybookDispatcher


def _import_mcp_data_sources():
    import importlib
    import types

    saved_tool_modules = {
        module_name: module
        for module_name, module in sys.modules.items()
        if module_name == "tools" or module_name.startswith("tools.")
    }
    for module_name in list(saved_tool_modules):
        if module_name == "tools" or module_name.startswith("tools."):
            del sys.modules[module_name]
    tools_module = types.ModuleType("tools")
    tools_module.__path__ = [str(FINANCE_MCP_ROOT / "tools")]
    sys.modules["tools"] = tools_module
    if str(FINANCE_MCP_ROOT) in sys.path:
        sys.path.remove(str(FINANCE_MCP_ROOT))
    sys.path.insert(0, str(FINANCE_MCP_ROOT))
    importlib.invalidate_caches()
    try:
        return importlib.import_module("tools.data_sources")
    finally:
        for module_name in list(sys.modules):
            if module_name == "tools" or module_name.startswith("tools."):
                del sys.modules[module_name]
        sys.modules.update(saved_tool_modules)


class FakeDb:
    def __init__(self) -> None:
        self.dispatched: list[dict[str, Any]] = []
        self.failures: list[dict[str, Any]] = []
        self.successes: list[dict[str, Any]] = []
        self.binding: dict[str, Any] = {
            "shop_id": "shop-001",
            "agent_id": "agent-001",
            "playbook_id": "qianniu-daily-bill-export",
            "egress_group": "wan-1",
            "credential_ref": "cred-001",
            "profile_status": "active",
            "playbook_status": "ok",
        }

    def claim_next_browser_sync_job(self, *, agent_max_concurrency: int = 2) -> dict[str, Any]:
        return {
            "id": "job-001",
            "company_id": "company-001",
            "data_source_id": "source-001",
            "resource_key": "qianniu-daily-bill-export@1.0.0",
            "request_payload": {
                "dataset_id": "dataset-001",
                "dataset_code": "qianniu_fund_bill",
                "biz_date": "2026-05-18",
            },
        }

    def get_shop_runtime_binding_for_source(self, *, company_id: str, data_source_id: str) -> dict[str, Any]:
        return self.binding

    def get_active_playbook(self, *, company_id: str, playbook_id: str) -> dict[str, Any]:
        return {
            "playbook_id": playbook_id,
            "version": "1.0.0",
            "playbook_body": {
                "schema_version": "1.0",
                "playbook_id": playbook_id,
                "title": "千牛资金日账单导出",
                "target": {
                    "platform": "qianniu",
                    "business_object": "fund_bill",
                    "timezone": "Asia/Shanghai",
                },
                "params_schema": {
                    "required": ["biz_date"],
                    "properties": {"biz_date": {"type": "date", "format": "YYYY-MM-DD"}},
                },
                "steps": [
                    {
                        "id": "read_summary",
                        "action": "extract_summary",
                        "mapping": {"row_count": "#row-count", "amount_total": "#amount-total"},
                    }
                ],
                "output": {
                    "record_type": "browser_collection_records",
                    "item_key_fields": ["bill_no"],
                    "columns": [
                        {"name": "bill_no", "type": "string", "required": True},
                        {"name": "amount", "type": "decimal", "required": True},
                        {"name": "biz_date", "type": "date", "required": True},
                    ],
                },
                "quality_gate": {
                    "date_field": "biz_date",
                    "amount_field": "amount",
                    "summary_step_id": "read_summary",
                },
                "accounting_policy": {
                    "date_basis": "账务日期/入账日期",
                    "amount_sign": "source_signed",
                    "included_business_types": ["千牛日汇总口径内全部明细"],
                },
                "failure_mapping": {
                    "selector_missing": "PAGE_CHANGED",
                    "auth_redirect": "AUTH_EXPIRED",
                    "risk_verification": "RISK_VERIFICATION",
                    "quality_mismatch": "DATA_MISMATCH",
                },
            },
        }

    def upsert_browser_collection_records(self, **kwargs: Any) -> dict[str, Any]:
        self.dispatched.append(kwargs)
        return {
            "inserted_count": 1,
            "updated_count": 0,
            "unchanged_count": 0,
            "input_count": 1,
        }

    def mark_browser_sync_job_success(self, *, sync_job_id: str, summary: dict[str, Any]) -> dict[str, Any]:
        self.successes.append({"sync_job_id": sync_job_id, "summary": summary})
        return {"id": sync_job_id, "job_status": "success"}

    def mark_browser_sync_job_failed(
        self,
        *,
        sync_job_id: str,
        error_message: str,
        fail_reason: str,
    ) -> dict[str, Any]:
        self.failures.append(
            {
                "sync_job_id": sync_job_id,
                "error_message": error_message,
                "fail_reason": fail_reason,
            }
        )
        return {"id": sync_job_id, "job_status": "failed"}

    def insert_browser_capture_files(self, **kwargs: Any) -> dict[str, Any]:
        if not hasattr(self, "capture_files"):
            self.capture_files = []
        self.capture_files.append(kwargs)
        return {"inserted_count": len(kwargs.get("capture_files") or [])}


def test_dispatcher_writes_success_records() -> None:
    fake_db = FakeDb()
    manager = FakeAgentConnectionManager()
    manager.register_result(
        "agent-001",
        {
            "job_id": "job-001",
            "status": "success",
            "records": [
                {
                    "item_key": "BILL-001",
                    "item_key_values": {"bill_no": "BILL-001"},
                    "payload": {"bill_no": "BILL-001", "amount": "10.00", "biz_date": "2026-05-18"},
                }
            ],
            "capture_files": [],
            "quality_summary": {"row_count": 1},
        },
    )

    dispatcher = BrowserPlaybookDispatcher(db=fake_db, connections=manager, agent_max_concurrency=2)
    result = dispatcher.run_once()

    assert result["status"] == "success"
    assert fake_db.dispatched[0]["shop_id"] == "shop-001"
    assert fake_db.dispatched[0]["dataset_id"] == "dataset-001"
    assert fake_db.successes[0]["sync_job_id"] == "job-001"
    assert manager.messages[0]["message"]["company_id"] == "company-001"
    assert manager.messages[0]["message"]["params"]["biz_date"] == "2026-05-18"


def test_dispatcher_fails_unhealthy_binding_without_dispatch() -> None:
    fake_db = FakeDb()
    fake_db.binding["profile_status"] = "needs_reauth"
    manager = FakeAgentConnectionManager()

    dispatcher = BrowserPlaybookDispatcher(db=fake_db, connections=manager)
    result = dispatcher.run_once()

    assert result["status"] == "failed"
    assert result["reason"] == "unhealthy_binding"
    assert manager.messages == []
    assert fake_db.failures[0]["fail_reason"] == "unhealthy_binding"


def test_dispatcher_marks_runner_failure() -> None:
    fake_db = FakeDb()
    manager = FakeAgentConnectionManager()
    manager.register_result(
        "agent-001",
        {
            "job_id": "job-001",
            "status": "failed",
            "fail_reason": "PAGE_CHANGED",
            "error_info": {"message": "selector missing"},
        },
    )

    dispatcher = BrowserPlaybookDispatcher(db=fake_db, connections=manager)
    result = dispatcher.run_once()

    assert result["status"] == "failed"
    assert result["reason"] == "PAGE_CHANGED"
    assert fake_db.failures[0]["fail_reason"] == "PAGE_CHANGED"


def test_claim_next_browser_sync_job_filters_by_source_kind_agent_and_binding_health(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql: str, params=None):
            captured["sql"] = sql

        def fetchone(self):
            return None

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return _Cursor()

        def commit(self):
            return None

    class _ConnManager:
        def __enter__(self):
            return _Conn()

        def __exit__(self, exc_type, exc, tb):
            return None

    from auth import db as auth_db

    monkeypatch.setattr(auth_db, "get_conn", lambda: _ConnManager())

    auth_db.claim_next_browser_sync_job(agent_id="agent-001")

    sql = captured["sql"]
    assert "JOIN data_sources ds ON ds.id = sync_jobs.data_source_id" in sql
    assert "JOIN shop_runtime_bindings srb" in sql
    assert "ds.source_kind = 'browser_playbook'" in sql
    assert "srb.agent_id = %s" in sql
    assert (
        "sync_jobs.is_verification = TRUE AND srb.profile_status IN "
        "('verifying', 'active', 'needs_reauth', 'risk_blocked')"
    ) in sql
    assert (
        "sync_jobs.is_verification = FALSE AND srb.profile_status = 'active' "
        "AND srb.playbook_status = 'ok'"
    ) in sql
    assert "running_for_agent.running_count < %s" in sql
    assert "running_for_agent AS (" in sql
    assert "JOIN LATERAL" not in sql
    assert "sync_jobs.is_verification = TRUE AND p.status IN ('draft', 'active')" in sql
    assert "sync_jobs.is_verification = FALSE AND p.status = 'active'" in sql
    assert "request_payload ->" not in sql


def test_claim_next_browser_sync_job_normalize_preserves_enriched_fields(monkeypatch) -> None:
    """Safeguard: _normalize_record must pass through enriched browser fields untouched.

    Hardening adds top-level shop_id/playbook_body/runtime_profile_ref/browser_binding into the
    RETURNING clause. If _normalize_record ever gains a whitelist filter, browser-agent would
    silently get an empty job. This test pins the passthrough behavior.
    """
    enriched_row = {
        "id": "sync-001",
        "company_id": "company-001",
        "data_source_id": "source-001",
        "shop_id": "shop-001",
        "playbook_id": "qianniu-daily-bill-export",
        "playbook_version": "1.0.0",
        "playbook_body": {"steps": [], "output": {}},
        "runtime_profile_ref": "profiles/shop-001",
        "egress_group": "wan-1",
        "credential_ref": "cred-001",
        "browser_binding": {"shop_id": "shop-001", "profile_status": "active"},
    }

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql, params=None):
            return None

        def fetchone(self):
            return enriched_row

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return _Cursor()

        def commit(self):
            return None

    class _ConnManager:
        def __enter__(self):
            return _Conn()

        def __exit__(self, exc_type, exc, tb):
            return None

    from auth import db as auth_db

    monkeypatch.setattr(auth_db, "get_conn", lambda: _ConnManager())

    row = auth_db.claim_next_browser_sync_job(agent_id="agent-001")

    assert row is not None
    assert row["shop_id"] == "shop-001"
    assert row["playbook_body"] == {"steps": [], "output": {}}
    assert row["runtime_profile_ref"] == "profiles/shop-001"
    assert row["browser_binding"]["shop_id"] == "shop-001"


def test_get_and_list_unified_sync_jobs_select_browser_diagnostics(monkeypatch) -> None:
    captured_sql: list[str] = []

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql, params=None):
            captured_sql.append(sql)

        def fetchone(self):
            return None

        def fetchall(self):
            return []

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return _Cursor()

    class _ConnManager:
        def __enter__(self):
            return _Conn()

        def __exit__(self, exc_type, exc, tb):
            return None

    from auth import db as auth_db

    monkeypatch.setattr(auth_db, "get_conn", lambda: _ConnManager())

    auth_db.get_unified_sync_job_by_id("sync-001")
    auth_db.list_unified_sync_jobs(company_id="company-001")

    assert len(captured_sql) == 2
    for sql in captured_sql:
        assert "next_retry_at" in sql
        assert "browser_fail_reason" in sql
        assert "max_attempts" in sql
        assert "is_verification" in sql


def test_mark_browser_sync_job_failed_retryable_reschedules_pending(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _Cursor:
        rowcount = 1

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql, params=None):
            captured["sql"] = sql
            captured["params"] = params

        def fetchone(self):
            return {"id": "sync-001", "job_status": "pending"}

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return _Cursor()

        def commit(self):
            return None

    class _ConnManager:
        def __enter__(self):
            return _Conn()

        def __exit__(self, exc_type, exc, tb):
            return None

    from auth import db as auth_db

    monkeypatch.setattr(auth_db, "get_conn", lambda: _ConnManager())

    auth_db.mark_browser_sync_job_failed(
        sync_job_id="sync-001",
        error_message="timeout",
        fail_reason="TIMEOUT",
        retryable=True,
        max_attempts=3,
        retry_delay_seconds=1800,
    )

    sql = captured["sql"]
    assert "job_status = CASE" in sql
    assert "next_retry_at = CASE" in sql
    assert "browser_fail_reason" in sql


def test_mark_browser_sync_job_failed_prefixes_error_exactly_once(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _Cursor:
        rowcount = 1

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql, params=None):
            captured["params"] = params

        def fetchone(self):
            return {"id": "sync-001", "job_status": "failed"}

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return _Cursor()

        def commit(self):
            return None

    class _ConnManager:
        def __enter__(self):
            return _Conn()

        def __exit__(self, exc_type, exc, tb):
            return None

    from auth import db as auth_db

    monkeypatch.setattr(auth_db, "get_conn", lambda: _ConnManager())
    # Suppress side-effect call into binding transition (different cursor)
    monkeypatch.setattr(auth_db, "apply_browser_binding_failure_transition", lambda **kw: 0)

    # Plain message → gets prefixed.
    auth_db.mark_browser_sync_job_failed(
        sync_job_id="sync-001",
        error_message="login expired",
        fail_reason="AUTH_EXPIRED",
    )
    params = captured["params"]
    assert "AUTH_EXPIRED: login expired" in params

    # Already-prefixed message → not double-prefixed.
    auth_db.mark_browser_sync_job_failed(
        sync_job_id="sync-001",
        error_message="AUTH_EXPIRED: login expired",
        fail_reason="AUTH_EXPIRED",
    )
    params = captured["params"]
    assert "AUTH_EXPIRED: AUTH_EXPIRED: login expired" not in params
    assert "AUTH_EXPIRED: login expired" in params


def test_mark_browser_sync_job_success_updates_binding_last_collection(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_update_unified_sync_job_status(**kwargs):
        captured["status_kwargs"] = kwargs
        return {
            "id": kwargs["sync_job_id"],
            "company_id": "company-001",
            "data_source_id": "source-001",
            "job_status": kwargs["job_status"],
        }

    class _Cursor:
        rowcount = 1

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql, params=None):
            captured["binding_sql"] = sql
            captured["binding_params"] = params

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return _Cursor()

        def commit(self):
            return None

    class _ConnManager:
        def __enter__(self):
            return _Conn()

        def __exit__(self, exc_type, exc, tb):
            return None

    from auth import db as auth_db

    monkeypatch.setattr(auth_db, "update_unified_sync_job_status", fake_update_unified_sync_job_status)
    monkeypatch.setattr(auth_db, "get_conn", lambda: _ConnManager())

    row = auth_db.mark_browser_sync_job_success(
        sync_job_id="sync-001",
        summary={"record_count": 3},
    )

    assert row["job_status"] == "success"
    assert "last_collection_at = CURRENT_TIMESTAMP" in captured["binding_sql"]
    assert "profile_status = 'active'" in captured["binding_sql"]
    assert "playbook_status = 'ok'" in captured["binding_sql"]
    assert "cron_pause_reason = NULL" in captured["binding_sql"]
    assert captured["binding_params"] == ("sync-001",)


def test_apply_browser_binding_failure_transition_maps_reasons(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class _Cursor:
        rowcount = 1

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql, params=None):
            captured["sql"] = sql

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return _Cursor()

        def commit(self):
            return None

    class _ConnManager:
        def __enter__(self):
            return _Conn()

        def __exit__(self, exc_type, exc, tb):
            return None

    from auth import db as auth_db

    monkeypatch.setattr(auth_db, "get_conn", lambda: _ConnManager())

    auth_db.apply_browser_binding_failure_transition(sync_job_id="sync-001", fail_reason="AUTH_EXPIRED")

    sql = captured["sql"]
    assert "profile_status = CASE" in sql
    assert "playbook_status = CASE" in sql
    assert "cron_pause_reason" in sql


def test_upsert_browser_agent_heartbeat_marks_online(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _Cursor:
        rowcount = 1

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql, params=None):
            captured["sql"] = sql
            captured["params"] = params

        def fetchone(self):
            return {
                "id": "agent-row-001",
                "company_id": "company-001",
                "agent_id": "browser-agent-local",
                "status": "online",
            }

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return _Cursor()

        def commit(self):
            return None

    class _ConnManager:
        def __enter__(self):
            return _Conn()

        def __exit__(self, exc_type, exc, tb):
            return None

    from auth import db as auth_db

    monkeypatch.setattr(auth_db, "get_conn", lambda: _ConnManager())

    row = auth_db.upsert_browser_agent_heartbeat(
        company_id="company-001",
        agent_id="browser-agent-local",
        hostname="collector-01",
        version="v1",
        capabilities={"browser": "chrome"},
    )

    assert row["status"] == "online"
    assert "INSERT INTO agents" in captured["sql"]
    assert "last_heartbeat_at" in captured["sql"]
    assert captured["params"][0] == "company-001"
    assert captured["params"][1] == "browser-agent-local"


def test_list_browser_agents_computes_online_status(monkeypatch) -> None:
    from browser_playbook import assignment

    now = datetime(2026, 6, 6, 10, 0, tzinfo=timezone.utc)
    rows = [
        {
            "agent_id": "collector-win-1",
            "hostname": "win-host",
            "version": "v1",
            "status": "online",
            "capabilities": {"max_concurrency": 2},
            "last_heartbeat_at": now - timedelta(seconds=30),
        },
        {
            "agent_id": "collector-mac-1",
            "hostname": "mac-host",
            "version": "v1",
            "status": "online",
            "capabilities": {},
            "last_heartbeat_at": now - timedelta(seconds=240),
        },
    ]
    captured: dict[str, object] = {}

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql, params=None):
            captured["sql"] = sql
            captured["params"] = params

        def fetchall(self):
            return rows

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return _Cursor()

    class _ConnManager:
        def __enter__(self):
            return _Conn()

        def __exit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr(assignment, "get_conn", lambda: _ConnManager())
    monkeypatch.setattr(assignment, "_now_utc", lambda: now)

    result = assignment.list_browser_agents(
        company_id="company-001",
        online_threshold_seconds=180,
    )

    assert result["success"] is True
    assert result["count"] == 2
    assert result["agents"][0]["agent_id"] == "collector-win-1"
    assert result["agents"][0]["is_online"] is True
    assert result["agents"][1]["agent_id"] == "collector-mac-1"
    assert result["agents"][1]["is_online"] is False
    assert "FROM agents" in captured["sql"]
    assert captured["params"] == ("company-001",)


def test_list_browser_bindings_includes_running_job_flags(monkeypatch) -> None:
    from browser_playbook import assignment

    rows = [
        {
            "data_source_id": "source-001",
            "data_source_code": "shop-code-001",
            "data_source_name": "Shop 001",
            "shop_id": "shop-001",
            "playbook_id": "qianniu-daily",
            "agent_id": "collector-mac-1",
            "profile_status": "active",
            "playbook_status": "ok",
            "running_sync_job_ids": ["sync-001"],
            "has_running_job": True,
        }
    ]
    captured: dict[str, object] = {}

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql, params=None):
            captured["sql"] = sql
            captured["params"] = params

        def fetchall(self):
            return rows

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return _Cursor()

    class _ConnManager:
        def __enter__(self):
            return _Conn()

        def __exit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr(assignment, "get_conn", lambda: _ConnManager())

    result = assignment.list_browser_bindings(
        company_id="company-001",
        agent_id="collector-mac-1",
    )

    assert result["success"] is True
    assert result["count"] == 1
    assert result["bindings"][0]["data_source_id"] == "source-001"
    assert result["bindings"][0]["has_running_job"] is True
    assert result["bindings"][0]["running_sync_job_ids"] == ["sync-001"]
    assert "JOIN data_sources ds" in captured["sql"]
    assert "srb.agent_id = %s" in captured["sql"]
    assert captured["params"] == ("company-001", "collector-mac-1")


def test_reassign_browser_bindings_dry_run_does_not_update(monkeypatch) -> None:
    from browser_playbook import assignment

    now = datetime(2026, 6, 6, 10, 0, tzinfo=timezone.utc)
    calls: list[str] = []

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql, params=None):
            calls.append(sql)
            self.sql = sql

        def fetchone(self):
            if "FROM agents" in self.sql:
                return {"agent_id": "collector-win-1", "last_heartbeat_at": now, "status": "online"}
            return None

        def fetchall(self):
            return [
                {
                    "data_source_id": "source-001",
                    "data_source_code": "shop-code-001",
                    "data_source_name": "Shop 001",
                    "shop_id": "shop-001",
                    "playbook_id": "qianniu-daily",
                    "agent_id": "collector-mac-1",
                    "profile_status": "active",
                    "playbook_status": "ok",
                    "running_sync_job_ids": [],
                    "has_running_job": False,
                }
            ]

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return _Cursor()

        def commit(self):
            calls.append("commit")

    class _ConnManager:
        def __enter__(self):
            return _Conn()

        def __exit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr(assignment, "get_conn", lambda: _ConnManager())
    monkeypatch.setattr(assignment, "_now_utc", lambda: now)

    result = assignment.reassign_browser_bindings(
        company_id="company-001",
        from_agent_id="collector-mac-1",
        to_agent_id="collector-win-1",
        dry_run=True,
    )

    assert result["success"] is True
    assert result["dry_run"] is True
    assert result["matched_count"] == 1
    assert result["updated_count"] == 0
    assert "blocked_reason" not in result
    assert not any("UPDATE shop_runtime_bindings" in sql for sql in calls)


def test_reassign_browser_bindings_dry_run_reports_offline_target(monkeypatch) -> None:
    from browser_playbook import assignment

    now = datetime(2026, 6, 6, 10, 0, tzinfo=timezone.utc)

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql, params=None):
            self.sql = sql

        def fetchone(self):
            if "FROM agents" in self.sql:
                return {
                    "agent_id": "collector-win-1",
                    "last_heartbeat_at": now - timedelta(minutes=10),
                    "status": "online",
                }
            return None

        def fetchall(self):
            return [
                {
                    "data_source_id": "source-001",
                    "data_source_code": "shop-code-001",
                    "data_source_name": "Shop 001",
                    "shop_id": "shop-001",
                    "playbook_id": "qianniu-daily",
                    "agent_id": "collector-mac-1",
                    "profile_status": "active",
                    "playbook_status": "ok",
                    "running_sync_job_ids": [],
                    "has_running_job": False,
                }
            ]

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return _Cursor()

    class _ConnManager:
        def __enter__(self):
            return _Conn()

        def __exit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr(assignment, "get_conn", lambda: _ConnManager())
    monkeypatch.setattr(assignment, "_now_utc", lambda: now)

    result = assignment.reassign_browser_bindings(
        company_id="company-001",
        from_agent_id="collector-mac-1",
        to_agent_id="collector-win-1",
        dry_run=True,
        require_online=True,
    )

    assert result["success"] is True
    assert result["dry_run"] is True
    assert result["matched_count"] == 1
    assert result["updated_count"] == 0
    assert result["would_block"] is True
    assert result["blocked_reason"] == "target_agent_offline"


def test_reassign_browser_bindings_updates_when_safe(monkeypatch) -> None:
    from browser_playbook import assignment

    now = datetime(2026, 6, 6, 10, 0, tzinfo=timezone.utc)
    captured: dict[str, object] = {"commit_count": 0}

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql, params=None):
            self.sql = sql
            captured["last_sql"] = sql
            captured["last_params"] = params

        def fetchone(self):
            if "FROM agents" in self.sql:
                return {"agent_id": "collector-win-1", "last_heartbeat_at": now, "status": "online"}
            return None

        def fetchall(self):
            if "RETURNING" in self.sql and "UPDATE shop_runtime_bindings" in self.sql:
                return [{"data_source_id": "source-001", "agent_id": "collector-win-1"}]
            return [
                {
                    "data_source_id": "source-001",
                    "data_source_code": "shop-code-001",
                    "data_source_name": "Shop 001",
                    "shop_id": "shop-001",
                    "playbook_id": "qianniu-daily",
                    "agent_id": "collector-mac-1",
                    "profile_status": "active",
                    "playbook_status": "ok",
                    "running_sync_job_ids": [],
                    "has_running_job": False,
                }
            ]

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return _Cursor()

        def commit(self):
            captured["commit_count"] = int(captured["commit_count"]) + 1

    class _ConnManager:
        def __enter__(self):
            return _Conn()

        def __exit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr(assignment, "get_conn", lambda: _ConnManager())
    monkeypatch.setattr(assignment, "_now_utc", lambda: now)

    result = assignment.reassign_browser_bindings(
        company_id="company-001",
        from_agent_id="collector-mac-1",
        to_agent_id="collector-win-1",
        dry_run=False,
    )

    assert result["success"] is True
    assert result["dry_run"] is False
    assert result["matched_count"] == 1
    assert result["updated_count"] == 1
    assert captured["commit_count"] == 1
    assert "UPDATE shop_runtime_bindings" in str(captured["last_sql"])


def test_reassign_browser_bindings_rejects_same_agent() -> None:
    from browser_playbook import assignment

    result = assignment.reassign_browser_bindings(
        company_id="company-001",
        from_agent_id="collector-win-1",
        to_agent_id="collector-win-1",
        dry_run=False,
    )

    assert result["success"] is False
    assert result["error"] == "source and target agent are the same"
    assert result["error_code"] == "same_agent"


def test_reassign_browser_bindings_rejects_offline_target_unless_forced(monkeypatch) -> None:
    from browser_playbook import assignment

    now = datetime(2026, 6, 6, 10, 0, tzinfo=timezone.utc)

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql, params=None):
            self.sql = sql

        def fetchone(self):
            if "FROM agents" in self.sql:
                return {
                    "agent_id": "collector-win-1",
                    "last_heartbeat_at": now - timedelta(minutes=10),
                    "status": "online",
                }
            return None

        def fetchall(self):
            return []

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return _Cursor()

    class _ConnManager:
        def __enter__(self):
            return _Conn()

        def __exit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr(assignment, "get_conn", lambda: _ConnManager())
    monkeypatch.setattr(assignment, "_now_utc", lambda: now)

    result = assignment.reassign_browser_bindings(
        company_id="company-001",
        from_agent_id="collector-mac-1",
        to_agent_id="collector-win-1",
        dry_run=False,
        require_online=True,
        force_offline_target=False,
    )

    assert result["success"] is False
    assert result["error_code"] == "target_agent_offline"


def test_reassign_browser_bindings_blocks_running_jobs(monkeypatch) -> None:
    from browser_playbook import assignment

    now = datetime(2026, 6, 6, 10, 0, tzinfo=timezone.utc)

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql, params=None):
            self.sql = sql

        def fetchone(self):
            if "FROM agents" in self.sql:
                return {"agent_id": "collector-win-1", "last_heartbeat_at": now, "status": "online"}
            return None

        def fetchall(self):
            return [
                {
                    "data_source_id": "source-001",
                    "data_source_code": "shop-code-001",
                    "data_source_name": "Shop 001",
                    "shop_id": "shop-001",
                    "playbook_id": "qianniu-daily",
                    "agent_id": "collector-mac-1",
                    "profile_status": "active",
                    "playbook_status": "ok",
                    "running_sync_job_ids": ["sync-running-001"],
                    "has_running_job": True,
                }
            ]

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return _Cursor()

    class _ConnManager:
        def __enter__(self):
            return _Conn()

        def __exit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr(assignment, "get_conn", lambda: _ConnManager())
    monkeypatch.setattr(assignment, "_now_utc", lambda: now)

    result = assignment.reassign_browser_bindings(
        company_id="company-001",
        from_agent_id="collector-mac-1",
        to_agent_id="collector-win-1",
        dry_run=False,
    )

    assert result["success"] is False
    assert result["error_code"] == "running_jobs_present"
    assert result["running_sync_job_ids"] == ["sync-running-001"]


def test_browser_sync_job_claim_returns_job(monkeypatch) -> None:
    import asyncio

    data_sources = _import_mcp_data_sources()

    expected_job = {"id": "sync-001", "shop_id": "shop-001", "playbook_body": {}}
    monkeypatch.setattr(
        data_sources,
        "_require_scheduler_user",
        lambda token: {"role": "system"},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "claim_next_browser_sync_job",
        lambda *, agent_id, agent_max_concurrency: expected_job,
    )

    result = asyncio.run(
        data_sources.handle_tool_call(
            "browser_sync_job_claim",
            {"worker_token": "tok", "agent_id": "agent-001", "max_concurrency": 2},
        )
    )

    assert result["success"] is True
    assert result["job"] == expected_job


def test_browser_agent_heartbeat_tool_calls_helper(monkeypatch) -> None:
    import asyncio

    data_sources = _import_mcp_data_sources()

    captured: dict[str, object] = {}

    def fake_heartbeat(**kwargs):
        captured.update(kwargs)
        return {"agent_id": kwargs["agent_id"], "status": "online"}

    monkeypatch.setattr(
        data_sources,
        "_require_scheduler_user",
        lambda token: {"role": "system", "company_id": "company-001"},
    )
    monkeypatch.setattr(data_sources.auth_db, "upsert_browser_agent_heartbeat", fake_heartbeat)

    result = asyncio.run(
        data_sources.handle_tool_call(
            "browser_agent_heartbeat",
            {
                "worker_token": "tok",
                "company_id": "company-001",
                "agent_id": "browser-agent-local",
                "hostname": "collector-01",
                "version": "v1",
                "capabilities": {"browser": "chrome"},
            },
        )
    )

    assert result["success"] is True
    assert captured["company_id"] == "company-001"
    assert captured["agent_id"] == "browser-agent-local"
    assert captured["capabilities"] == {"browser": "chrome"}


def test_browser_sync_job_startup_cleanup_tool_calls_helper(monkeypatch) -> None:
    import asyncio

    data_sources = _import_mcp_data_sources()

    captured: dict[str, object] = {}

    def fake_cleanup(**kwargs):
        captured.update(kwargs)
        return {"failed_count": 2, "sync_job_ids": ["sync-001", "sync-002"]}

    monkeypatch.setattr(
        data_sources,
        "_require_scheduler_user",
        lambda token: {"role": "system", "company_id": "company-001"},
    )
    monkeypatch.setattr(data_sources.auth_db, "fail_running_browser_sync_jobs_for_agent", fake_cleanup)

    result = asyncio.run(
        data_sources.handle_tool_call(
            "browser_sync_job_startup_cleanup",
            {"worker_token": "tok", "agent_id": "browser-agent-local"},
        )
    )

    assert result["success"] is True
    assert result["failed_count"] == 2
    assert result["sync_job_ids"] == ["sync-001", "sync-002"]
    assert captured["agent_id"] == "browser-agent-local"


def test_fail_running_browser_sync_jobs_for_agent_updates_only_agent_browser_jobs(monkeypatch) -> None:
    captured: dict[str, object] = {}
    rows = [{"id": "sync-001"}, {"id": "sync-002"}]

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql: str, params=None):
            captured["sql"] = sql
            captured["params"] = params

        def fetchall(self):
            return rows

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return _Cursor()

        def commit(self):
            captured["committed"] = True

    class _ConnManager:
        def __enter__(self):
            return _Conn()

        def __exit__(self, exc_type, exc, tb):
            return None

    from auth import db as auth_db

    monkeypatch.setattr(auth_db, "get_conn", lambda: _ConnManager())

    result = auth_db.fail_running_browser_sync_jobs_for_agent(agent_id="browser-agent-local")

    sql = str(captured["sql"])
    assert result == {"failed_count": 2, "sync_job_ids": ["sync-001", "sync-002"]}
    assert "UPDATE sync_jobs" in sql
    assert "WHERE ds.id = sync_jobs.data_source_id" in sql
    assert "EXISTS (" in sql
    assert "JOIN shop_runtime_bindings srb" in sql
    assert "sync_jobs.job_status = 'running'" in sql
    assert "ds.source_kind = 'browser_playbook'" in sql
    assert "srb.agent_id = %s" in sql
    assert "AGENT_INTERRUPTED" in sql
    assert captured["params"] == ("browser-agent-local",)
    assert captured["committed"] is True


def test_browser_sync_job_fail_calls_helper(monkeypatch) -> None:
    import asyncio

    data_sources = _import_mcp_data_sources()

    captured: dict[str, object] = {}

    def fake_fail(**kwargs):
        captured.update(kwargs)
        return {"id": kwargs["sync_job_id"], "job_status": "pending"}

    monkeypatch.setattr(
        data_sources,
        "_require_scheduler_user",
        lambda token: {"role": "system"},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_sync_job_by_id",
        lambda sync_job_id: {"id": sync_job_id, "job_status": "running"},
    )
    monkeypatch.setattr(data_sources.auth_db, "mark_browser_sync_job_failed", fake_fail)

    result = asyncio.run(
        data_sources.handle_tool_call(
            "browser_sync_job_fail",
            {
                "worker_token": "tok",
                "sync_job_id": "sync-001",
                "fail_reason": "TIMEOUT",
                "error_message": "timeout",
                "retryable": True,
                "max_attempts": 3,
                "retry_delay_seconds": 1800,
            },
        )
    )

    assert result["success"] is True
    assert captured["fail_reason"] == "TIMEOUT"
    assert captured["retryable"] is True
    assert captured["max_attempts"] == 3
    assert captured["retry_delay_seconds"] == 1800


def test_browser_sync_job_complete_writes_records_and_files(monkeypatch) -> None:
    import asyncio
    from contextlib import nullcontext

    data_sources = _import_mcp_data_sources()

    upserted: dict[str, object] = {}
    files: dict[str, object] = {}
    success: dict[str, object] = {}
    health_updates: list[dict[str, object]] = []

    monkeypatch.setattr(
        data_sources,
        "_require_scheduler_user",
        lambda token: {"role": "system"},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_sync_job_by_id",
        lambda sync_job_id: {
            "id": sync_job_id,
            "company_id": "c1",
            "data_source_id": "s1",
            "resource_key": "qianniu-daily-bill-export@1.0.0",
            "job_status": "running",
            "request_payload": {
                "dataset_id": "d1",
                "dataset_code": "qianniu_fund_bill",
                "biz_date": "2026-05-18",
            },
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "browser_sync_job_transition_lock",
        lambda sync_job_id: nullcontext(),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "guard_browser_sync_job_worker_active",
        lambda **kw: {
            "id": kw["sync_job_id"],
            "company_id": "c1",
            "data_source_id": "s1",
            "resource_key": "qianniu-daily-bill-export@1.0.0",
            "job_status": "running",
            "request_payload": {
                "dataset_id": "d1",
                "dataset_code": "qianniu_fund_bill",
                "biz_date": "2026-05-18",
            },
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_shop_runtime_binding_for_source",
        lambda *, company_id, data_source_id: {
            "shop_id": "shop-001",
            "playbook_id": "qianniu-daily-bill-export",
        },
    )

    def fake_upsert(**kw):
        upserted.update(kw)
        return {"inserted_count": 1, "updated_count": 0, "unchanged_count": 0, "input_count": 1}

    def fake_files(**kw):
        files.update(kw)
        return {"inserted_count": 1}

    def fake_success(**kw):
        success.update(kw)
        return {
            "id": kw["sync_job_id"],
            "job_status": "success",
            "completed_at": "2026-05-25T15:31:51+08:00",
        }

    monkeypatch.setattr(data_sources.auth_db, "upsert_browser_collection_records", fake_upsert)
    monkeypatch.setattr(data_sources.auth_db, "insert_browser_capture_files", fake_files)
    monkeypatch.setattr(data_sources.auth_db, "mark_browser_sync_job_success", fake_success)
    monkeypatch.setattr(
        data_sources.auth_db,
        "update_unified_data_source_dataset_health",
        lambda **kw: health_updates.append(kw) or {"id": kw["dataset_id"]},
    )

    result = asyncio.run(
        data_sources.handle_tool_call(
            "browser_sync_job_complete",
            {
                "worker_token": "tok",
                "sync_job_id": "sync-001",
                "summary": {"quality_summary": {"row_count": 1}},
                "records": [{"item_key": "B1", "payload": {"bill_no": "B1", "amount": "1.00"}}],
                "capture_files": [{"storage_path": "/tmp/x.csv", "encoding": "utf-8"}],
            },
        )
    )

    assert result["success"] is True
    assert upserted["dataset_id"] == "d1"
    assert upserted["shop_id"] == "shop-001"
    assert files["sync_job_id"] == "sync-001"
    assert success["sync_job_id"] == "sync-001"
    assert success["summary"]["capture_file_count"] == 1
    assert health_updates == [
        {
            "dataset_id": "d1",
            "health_status": "healthy",
            "last_sync_at": "2026-05-25T15:31:51+08:00",
            "last_error_message": "",
        }
    ]


def test_dispatcher_persists_capture_files() -> None:
    fake_db = FakeDb()
    manager = FakeAgentConnectionManager()
    manager.register_result(
        "agent-001",
        {
            "job_id": "job-001",
            "status": "success",
            "records": [],
            "capture_files": [
                {
                    "storage_path": "/tmp/qn.csv",
                    "encoding": "utf-8",
                    "checksum": "sha256:abc",
                    "row_count": 0,
                }
            ],
        },
    )

    dispatcher = BrowserPlaybookDispatcher(db=fake_db, connections=manager)
    dispatcher.run_once()

    assert hasattr(fake_db, "capture_files")
    assert fake_db.capture_files[0]["sync_job_id"] == "job-001"
    assert fake_db.capture_files[0]["capture_files"][0]["storage_path"] == "/tmp/qn.csv"


def test_dispatcher_persists_oss_capture_metadata() -> None:
    fake_db = FakeDb()
    manager = FakeAgentConnectionManager()
    manager.register_result(
        "agent-001",
        {
            "job_id": "job-001",
            "status": "success",
            "records": [],
            "capture_files": [
                {
                    "storage_path": "oss://bucket-a/browser-captures/c1/qn.csv",
                    "storage_provider": "oss",
                    "storage_bucket": "bucket-a",
                    "storage_key": "browser-captures/c1/qn.csv",
                    "storage_uri": "oss://bucket-a/browser-captures/c1/qn.csv",
                    "content_type": "text/csv",
                    "size_bytes": 20,
                    "encoding": "utf-8",
                    "checksum": "sha256:abc",
                    "row_count": 0,
                }
            ],
        },
    )

    dispatcher = BrowserPlaybookDispatcher(db=fake_db, connections=manager)
    dispatcher.run_once()

    capture = fake_db.capture_files[0]["capture_files"][0]
    assert capture["storage_provider"] == "oss"
    assert capture["storage_key"] == "browser-captures/c1/qn.csv"
