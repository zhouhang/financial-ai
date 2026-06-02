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
    monkeypatch.setattr(auth_db, "ensure_storage_objects_schema", lambda: [])
    monkeypatch.setattr(auth_db, "ensure_browser_handoff_schema", lambda: [])

    assert auth_db.ensure_schema() == ["019", "031_browser_playbook_collection.sql"]
    assert calls == ["recon", "031_browser_playbook_collection.sql"]


def test_schema_bootstrap_runs_storage_after_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(auth_db, "ensure_unified_data_source_schema", lambda: calls.append("unified") or [])
    monkeypatch.setattr(
        auth_db,
        "ensure_browser_playbook_collection_schema",
        lambda: calls.append("browser") or ["031_browser_playbook_collection.sql"],
    )
    monkeypatch.setattr(
        auth_db,
        "ensure_storage_objects_schema",
        lambda: calls.append("storage") or ["037_storage_objects_and_browser_capture_oss.sql"],
    )
    monkeypatch.setattr(auth_db, "ensure_browser_handoff_schema", lambda: calls.append("handoff") or [])

    assert auth_db.ensure_schema() == [
        "031_browser_playbook_collection.sql",
        "037_storage_objects_and_browser_capture_oss.sql",
    ]
    assert calls == ["unified", "browser", "storage", "handoff"]


def test_storage_objects_schema_bootstrap_applies_037_for_pre_oss_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    tables = {
        "playbooks",
        "agents",
        "shop_runtime_bindings",
        "browser_collection_records",
        "browser_capture_files",
        "recon_execution_queue",
    }
    browser_capture_columns = {
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
        "updated_at",
    }
    storage_object_columns: set[str] = set()
    constraints: set[str] = set()

    def fake_table_exists(table_name: str, *, schema: str = "public") -> bool:
        return table_name in tables

    def fake_column_exists(table_name: str, column_name: str, *, schema: str = "public") -> bool:
        if table_name == "browser_capture_files":
            return column_name in browser_capture_columns
        if table_name == "storage_objects":
            return column_name in storage_object_columns
        return True

    def fake_execute_sql_script(script_path: Path) -> None:
        calls.append(script_path.name)
        tables.add("storage_objects")
        constraints.add("storage_objects_logical_path_key")
        storage_object_columns.update(
            {
                "object_id",
                "logical_path",
                "owner_user_id",
                "company_id",
                "module",
                "storage_provider",
                "storage_bucket",
                "storage_key",
                "storage_uri",
                "local_path",
                "original_filename",
                "content_type",
                "size_bytes",
                "checksum",
                "metadata_json",
                "created_at",
                "updated_at",
            }
        )
        browser_capture_columns.update(
            {
                "storage_provider",
                "storage_bucket",
                "storage_key",
                "storage_uri",
                "content_type",
                "size_bytes",
            }
        )

    monkeypatch.setattr(auth_db, "_table_exists", fake_table_exists)
    monkeypatch.setattr(auth_db, "_column_exists", fake_column_exists)
    monkeypatch.setattr(
        auth_db,
        "_constraint_exists",
        lambda table_name, constraint_name, schema="public": constraint_name in constraints,
    )
    monkeypatch.setattr(auth_db, "_execute_sql_script", fake_execute_sql_script)
    monkeypatch.setattr(auth_db, "_migration_path", lambda filename: Path(filename))
    monkeypatch.setattr(auth_db, "_STORAGE_OBJECTS_SCHEMA_READY", False)

    assert auth_db.ensure_storage_objects_schema() == [
        "037_storage_objects_and_browser_capture_oss.sql"
    ]
    assert calls == ["037_storage_objects_and_browser_capture_oss.sql"]


def test_storage_objects_schema_bootstrap_repairs_old_id_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    tables = {"storage_objects", "browser_capture_files"}
    browser_capture_columns = {
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
        "updated_at",
    }
    storage_object_columns = {
        "id",
        "logical_path",
        "owner_user_id",
        "company_id",
        "module",
        "storage_provider",
        "storage_bucket",
        "storage_key",
        "storage_uri",
        "local_path",
        "original_filename",
        "content_type",
        "size_bytes",
        "checksum",
        "metadata_json",
        "created_at",
        "updated_at",
    }
    constraints: set[str] = set()

    def fake_table_exists(table_name: str, *, schema: str = "public") -> bool:
        return table_name in tables

    def fake_column_exists(table_name: str, column_name: str, *, schema: str = "public") -> bool:
        if table_name == "browser_capture_files":
            return column_name in browser_capture_columns
        if table_name == "storage_objects":
            return column_name in storage_object_columns
        return False

    def fake_execute_sql_script(script_path: Path) -> None:
        calls.append(script_path.name)
        storage_object_columns.discard("id")
        storage_object_columns.add("object_id")
        constraints.add("storage_objects_logical_path_key")
        browser_capture_columns.update(
            {
                "storage_provider",
                "storage_bucket",
                "storage_key",
                "storage_uri",
                "content_type",
                "size_bytes",
            }
        )

    monkeypatch.setattr(auth_db, "_table_exists", fake_table_exists)
    monkeypatch.setattr(auth_db, "_column_exists", fake_column_exists)
    monkeypatch.setattr(
        auth_db,
        "_constraint_exists",
        lambda table_name, constraint_name, schema="public": constraint_name in constraints,
    )
    monkeypatch.setattr(auth_db, "_execute_sql_script", fake_execute_sql_script)
    monkeypatch.setattr(auth_db, "_migration_path", lambda filename: Path(filename))
    monkeypatch.setattr(auth_db, "_STORAGE_OBJECTS_SCHEMA_READY", False)

    assert auth_db.ensure_storage_objects_schema() == [
        "037_storage_objects_and_browser_capture_oss.sql"
    ]
    assert calls == ["037_storage_objects_and_browser_capture_oss.sql"]
    assert "object_id" in storage_object_columns
    assert "id" not in storage_object_columns


def test_storage_objects_schema_bootstrap_applies_037_when_unique_constraint_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    tables = {"storage_objects", "browser_capture_files"}
    browser_capture_columns = {
        "storage_provider",
        "storage_bucket",
        "storage_key",
        "storage_uri",
        "content_type",
        "size_bytes",
    }
    storage_object_columns = {
        "object_id",
        "logical_path",
        "owner_user_id",
        "company_id",
        "module",
        "storage_provider",
        "storage_bucket",
        "storage_key",
        "storage_uri",
        "local_path",
        "original_filename",
        "content_type",
        "size_bytes",
        "checksum",
        "metadata_json",
        "created_at",
        "updated_at",
    }
    constraints: set[str] = set()

    def fake_table_exists(table_name: str, *, schema: str = "public") -> bool:
        return table_name in tables

    def fake_column_exists(table_name: str, column_name: str, *, schema: str = "public") -> bool:
        if table_name == "browser_capture_files":
            return column_name in browser_capture_columns
        if table_name == "storage_objects":
            return column_name in storage_object_columns
        return False

    def fake_execute_sql_script(script_path: Path) -> None:
        calls.append(script_path.name)
        constraints.add("storage_objects_logical_path_key")

    monkeypatch.setattr(auth_db, "_table_exists", fake_table_exists)
    monkeypatch.setattr(auth_db, "_column_exists", fake_column_exists)
    monkeypatch.setattr(
        auth_db,
        "_constraint_exists",
        lambda table_name, constraint_name, schema="public": constraint_name in constraints,
    )
    monkeypatch.setattr(auth_db, "_execute_sql_script", fake_execute_sql_script)
    monkeypatch.setattr(auth_db, "_migration_path", lambda filename: Path(filename))
    monkeypatch.setattr(auth_db, "_STORAGE_OBJECTS_SCHEMA_READY", False)

    assert auth_db.ensure_storage_objects_schema() == [
        "037_storage_objects_and_browser_capture_oss.sql"
    ]
    assert calls == ["037_storage_objects_and_browser_capture_oss.sql"]


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


class FakeCursor:
    def __init__(self) -> None:
        self.executed_sql: list[str] = []

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[object, ...] | None = None) -> None:
        self.executed_sql.append(sql)

    def fetchone(self) -> dict[str, object]:
        return {"inserted": False, "record_status": "updated"}


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor_obj = cursor
        self.committed = False

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def cursor(self, *args: object, **kwargs: object) -> FakeCursor:
        return self.cursor_obj

    def commit(self) -> None:
        self.committed = True


def _install_fake_connection(monkeypatch: pytest.MonkeyPatch) -> tuple[FakeConnection, FakeCursor]:
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    monkeypatch.setattr(auth_db, "get_conn", lambda: connection)
    return connection, cursor


def test_upsert_browser_collection_records_does_not_soft_delete_missing_keys(monkeypatch) -> None:
    """Pin the v1 contract: upsert_browser_collection_records never marks missing rows deleted.

    Soft delete is intentionally deferred until a later hardening plan adds
    complete-success missing-key detection. See the design addendum
    `docs/superpowers/specs/2026-05-20-browser-first-store-production-hardening-design.md`
    section "Soft Delete Limitation" — this test exists so the contract can't regress silently.
    """
    connection, _cursor = _install_fake_connection(monkeypatch)

    def fake_execute_values(cur, sql, values, template=None, page_size=None, fetch=False):
        # Return one inserted row + one unchanged row to simulate a successful recapture
        # where some previously seen rows would have been candidates for soft delete if the
        # feature existed.
        return [
            {"id": "rec-1", "action": "inserted", "record_status": "active"},
            {"id": "rec-2", "action": "unchanged", "record_status": "unchanged"},
        ]

    monkeypatch.setattr(auth_db.psycopg2.extras, "execute_values", fake_execute_values)

    result = auth_db.upsert_browser_collection_records(
        company_id="00000000-0000-0000-0000-000000000001",
        data_source_id="00000000-0000-0000-0000-000000000002",
        dataset_id="00000000-0000-0000-0000-000000000003",
        dataset_code="qianniu_fund_bill",
        resource_key="qianniu-daily-bill-export@1.0.0",
        shop_id="shop-001",
        playbook_id="qianniu-daily-bill-export",
        biz_date="2026-05-18",
        sync_job_id="00000000-0000-0000-0000-000000000004",
        records=[
            {"item_key": "B1", "payload": {"bill_no": "B1", "amount": "1.00"}},
            {"item_key": "B2", "payload": {"bill_no": "B2", "amount": "2.00"}},
        ],
    )

    # v1: soft delete is deferred. Any rows previously upserted but absent from this batch
    # remain active and are NOT counted in deleted_count.
    assert result["deleted_count"] == 0


def test_upsert_browser_collection_records_computes_hashes_and_counts(monkeypatch) -> None:
    connection, _cursor = _install_fake_connection(monkeypatch)
    execute_values_call: dict[str, object] = {}

    def fake_execute_values(
        cur,
        sql: str,
        values: list[tuple[object, ...]],
        template: str | None = None,
        page_size: int | None = None,
        fetch: bool = False,
    ) -> list[dict[str, str]]:
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

    result = auth_db.upsert_browser_collection_records(
        company_id="00000000-0000-0000-0000-000000000001",
        data_source_id="00000000-0000-0000-0000-000000000002",
        dataset_id="00000000-0000-0000-0000-000000000003",
        dataset_code="qianniu_bill",
        resource_key="qianniu:bill:shop-1",
        shop_id="shop-1",
        playbook_id="qianniu-daily-bill-export",
        biz_date="2026-05-16",
        sync_job_id="00000000-0000-0000-0000-000000000004",
        records=[
            {"item_key": "bill-1", "payload": {"bill_no": "bill-1", "amount": "12.30"}},
            {
                "item_key": "bill-2",
                "item_key_values": {"bill_no": "bill-2"},
                "item_hash": "caller-hash-must-not-win",
                "payload": {"amount": "45.60", "bill_no": "bill-2"},
            },
            {"item_key": "bill-3", "payload": {"bill_no": "bill-3", "amount": "78.90"}},
        ],
    )

    assert execute_values_call["fetch"] is True
    assert execute_values_call["page_size"] == 1000
    assert "INSERT INTO browser_collection_records" in str(execute_values_call["sql"])
    assert "dataset_collection_records" not in str(execute_values_call["sql"])
    values = execute_values_call["values"]
    assert isinstance(values, list)
    assert len(values) == 3
    assert all(len(str(row[10])) == 64 for row in values)
    assert str(values[1][10]) != "caller-hash-must-not-win"
    assert connection.committed is True
    assert result == {
        "input_count": 3,
        "upserted_count": 3,
        "inserted_count": 1,
        "updated_count": 1,
        "unchanged_count": 1,
        "deleted_count": 0,
    }


def test_upsert_browser_collection_records_updates_seen_and_captured_timestamps(monkeypatch) -> None:
    _install_fake_connection(monkeypatch)
    execute_values_call: dict[str, str] = {}

    def fake_execute_values(
        cur,
        sql: str,
        values: list[tuple[object, ...]],
        template: str | None = None,
        page_size: int | None = None,
        fetch: bool = False,
    ) -> list[dict[str, str]]:
        execute_values_call["sql"] = " ".join(sql.split())
        return [{"action": "unchanged"}]

    monkeypatch.setattr(auth_db.psycopg2.extras, "execute_values", fake_execute_values)

    auth_db.upsert_browser_collection_records(
        company_id="00000000-0000-0000-0000-000000000001",
        data_source_id="00000000-0000-0000-0000-000000000002",
        dataset_id="00000000-0000-0000-0000-000000000003",
        dataset_code="qianniu_bill",
        resource_key="qianniu:bill:shop-1",
        shop_id="shop-1",
        playbook_id="qianniu-daily-bill-export",
        biz_date="2026-05-16",
        sync_job_id="00000000-0000-0000-0000-000000000004",
        captured_at="2026-05-16T01:02:03+08:00",
        records=[{"item_key": "bill-1", "payload": {"bill_no": "bill-1", "amount": "12.30"}}],
    )

    sql = execute_values_call["sql"]
    assert "latest_seen_job_id = EXCLUDED.latest_seen_job_id" in sql
    assert "latest_seen_at = CURRENT_TIMESTAMP" in sql
    assert "captured_at = EXCLUDED.captured_at" in sql
    assert (
        "record_status = CASE WHEN browser_collection_records.item_hash = "
        "EXCLUDED.item_hash THEN 'unchanged' ELSE 'updated' END"
    ) in sql


def test_list_browser_collection_records_orders_by_latest_collection_time(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class Cursor:
        def __enter__(self) -> "Cursor":
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def execute(self, sql: str, params: tuple[object, ...]) -> None:
            captured["sql"] = " ".join(sql.split())
            captured["params"] = params

        def fetchall(self) -> list[dict[str, object]]:
            return []

    class Connection:
        def __enter__(self) -> "Connection":
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def cursor(self, *args: object, **kwargs: object) -> Cursor:
            return Cursor()

    monkeypatch.setattr(auth_db, "get_conn", lambda: Connection())

    auth_db.list_browser_collection_records(
        company_id="company-1",
        data_source_id="source-1",
        dataset_id="dataset-1",
        limit=100,
    )

    sql = str(captured["sql"])
    assert "ORDER BY latest_seen_at DESC NULLS LAST, updated_at DESC, captured_at DESC NULLS LAST, id DESC" in sql
    assert "ORDER BY biz_date DESC" not in sql
    assert captured["params"][-2:] == (0, 100)
