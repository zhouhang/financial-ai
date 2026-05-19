from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from auth import db as auth_db
from unified_mcp_server import main as server_main


def test_server_startup_uses_schema_wrapper(monkeypatch) -> None:
    calls: list[str] = []

    def fake_ensure_schema() -> list[str]:
        calls.append("ensure_schema")
        return ["019_recon_execution_queue.sql", "031_browser_playbook_collection.sql"]

    def fail_if_unified_called() -> list[str]:
        raise AssertionError("main() should use ensure_schema() instead of ensure_unified_data_source_schema()")

    async def fake_list_tools() -> list[SimpleNamespace]:
        return [SimpleNamespace(name="tool_a", description="desc")]

    class FakeServer:
        def __init__(self, config) -> None:
            self.config = config

        async def serve(self) -> None:
            calls.append("serve")

    monkeypatch.setattr(auth_db, "ensure_schema", fake_ensure_schema)
    monkeypatch.setattr(auth_db, "ensure_unified_data_source_schema", fail_if_unified_called)
    monkeypatch.setattr("unified_mcp_server.list_tools", fake_list_tools)
    monkeypatch.setattr("unified_mcp_server.uvicorn.Server", FakeServer)

    asyncio.run(server_main())

    assert calls == ["ensure_schema", "serve"]


def test_schema_bootstrap_runs_recon_queue_before_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    state = {"ready": False}

    monkeypatch.setattr(auth_db, "ensure_unified_data_source_schema", lambda: [])
    monkeypatch.setattr(auth_db, "ensure_recon_execution_queue_schema", lambda: calls.append("recon") or ["019"])
    monkeypatch.setattr(auth_db, "_browser_playbook_collection_schema_ready", lambda: state["ready"])
    monkeypatch.setattr(
        auth_db,
        "_execute_sql_script",
        lambda script_path: (calls.append(script_path.name), state.__setitem__("ready", True)),
    )
    monkeypatch.setattr(auth_db, "_migration_path", lambda filename: Path(filename))
    monkeypatch.setattr(auth_db, "_table_exists", lambda table_name, schema="public": True)
    monkeypatch.setattr(auth_db, "_column_exists", lambda table_name, column_name, schema="public": True)
    monkeypatch.setattr(
        auth_db,
        "_constraint_definition",
        lambda table_name, constraint_name, schema="public": "draft replayed approved canary active deprecated",
    )
    monkeypatch.setattr(auth_db, "_constraint_exists", lambda *args, **kwargs: True)

    assert auth_db.ensure_schema() == ["019", "031_browser_playbook_collection.sql"]
    assert calls == ["recon", "031_browser_playbook_collection.sql"]


def test_browser_collection_records_schema_has_required_columns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        auth_db,
        "_table_columns",
        lambda table_name, schema="public": [
            "company_id",
            "data_source_id",
            "dataset_id",
            "biz_date",
            "item_key",
            "item_hash",
            "payload",
            "record_status",
        ]
        if table_name == "browser_collection_records"
        else [],
    )

    assert {
        "company_id",
        "data_source_id",
        "dataset_id",
        "biz_date",
        "item_key",
        "item_hash",
        "payload",
        "record_status",
    }.issubset(set(auth_db._table_columns("browser_collection_records")))  # noqa: SLF001


def test_shop_runtime_bindings_schema_has_required_status_columns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        auth_db,
        "_table_columns",
        lambda table_name, schema="public": [
            "profile_status",
            "playbook_status",
            "cron_pause_reason",
        ]
        if table_name == "shop_runtime_bindings"
        else [],
    )

    assert {
        "profile_status",
        "playbook_status",
        "cron_pause_reason",
    }.issubset(set(auth_db._table_columns("shop_runtime_bindings")))  # noqa: SLF001


def test_playbooks_schema_has_lifecycle_and_audit_columns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        auth_db,
        "_table_columns",
        lambda table_name, schema="public": [
            "company_id",
            "playbook_id",
            "version",
            "description",
            "schema_check_result",
            "replay_result",
            "sample_data_path",
            "transcript_path",
            "canary_shop_ids",
            "emergency_page_changed",
            "bypass_canary_reason",
            "created_by",
            "approved_by",
            "approved_at",
            "canary_started_at",
            "canary_completed_at",
            "status",
        ]
        if table_name == "playbooks"
        else [],
    )
    monkeypatch.setattr(
        auth_db,
        "_constraint_definition",
        lambda table_name, constraint_name, schema="public": "draft replayed approved canary active deprecated"
        if table_name == "playbooks" and constraint_name == "playbooks_status_check"
        else "",
    )

    assert {
        "company_id",
        "playbook_id",
        "version",
        "description",
        "schema_check_result",
        "replay_result",
        "sample_data_path",
        "transcript_path",
        "canary_shop_ids",
        "emergency_page_changed",
        "bypass_canary_reason",
        "created_by",
        "approved_by",
        "approved_at",
        "canary_started_at",
        "canary_completed_at",
        "status",
    }.issubset(set(auth_db._table_columns("playbooks")))  # noqa: SLF001

    status_constraint = auth_db._constraint_definition("playbooks", "playbooks_status_check")  # noqa: SLF001
    for status in ("draft", "replayed", "approved", "canary", "active", "deprecated"):
        assert status in status_constraint


def test_browser_playbook_schema_ready_requires_browser_capture_files_and_recon_shape(monkeypatch) -> None:
    tables = {
        "playbooks",
        "agents",
        "shop_runtime_bindings",
        "browser_collection_records",
        "browser_capture_files",
        "recon_execution_queue",
    }
    columns = {
        "playbooks": {
            "company_id",
            "playbook_id",
            "version",
            "description",
            "schema_check_result",
            "replay_result",
            "sample_data_path",
            "transcript_path",
            "canary_shop_ids",
            "emergency_page_changed",
            "bypass_canary_reason",
            "created_by",
            "approved_by",
            "approved_at",
            "canary_started_at",
            "canary_completed_at",
            "status",
        },
        "browser_collection_records": {
            "company_id",
            "data_source_id",
            "dataset_id",
            "biz_date",
            "item_key",
            "item_hash",
            "payload",
            "record_status",
        },
        "shop_runtime_bindings": {
            "profile_status",
            "playbook_status",
            "cron_pause_reason",
        },
        "browser_capture_files": {
            "company_id",
            "data_source_id",
            "dataset_id",
            "sync_job_id",
            "resource_key",
            "shop_id",
            "playbook_id",
            "biz_date",
            "storage_path",
            "encoding",
            "checksum",
            "row_count",
            "created_at",
        },
        "recon_execution_queue": {
            "next_retry_at",
            "wait_deadline_at",
            "waiting_reason",
            "waiting_datasets",
            "collection_job_ids",
        },
    }

    def fake_table_exists(table_name: str, *, schema: str = "public") -> bool:
        return table_name in tables

    def fake_column_exists(table_name: str, column_name: str, *, schema: str = "public") -> bool:
        if table_name == "browser_capture_files" and column_name == "updated_at":
            return False
        return column_name in columns.get(table_name, set())

    def fake_constraint_definition(table_name: str, constraint_name: str, *, schema: str = "public") -> str:
        if table_name == "playbooks" and constraint_name == "playbooks_status_check":
            return "CHECK ((status)::text = ANY (ARRAY['draft'::character varying, 'replayed'::character varying, 'approved'::character varying, 'canary'::character varying, 'active'::character varying, 'deprecated'::character varying]))"
        if table_name == "recon_execution_queue" and constraint_name == "recon_execution_queue_status_check":
            return "CHECK ((status)::text = ANY (ARRAY['queued'::character varying, 'running'::character varying, 'done'::character varying, 'failed'::character varying]))"
        return ""

    monkeypatch.setattr(auth_db, "_table_exists", fake_table_exists)
    monkeypatch.setattr(auth_db, "_column_exists", fake_column_exists)
    monkeypatch.setattr(auth_db, "_constraint_definition", fake_constraint_definition)
    monkeypatch.setattr(auth_db, "_constraint_exists", lambda *args, **kwargs: True)
    monkeypatch.setattr(auth_db, "_index_exists", lambda *args, **kwargs: False)

    assert not auth_db._browser_playbook_collection_schema_ready()  # noqa: SLF001
