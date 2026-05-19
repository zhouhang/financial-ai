from __future__ import annotations

import sys
from pathlib import Path

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from auth import db as auth_db


def test_browser_collection_records_schema_has_required_columns() -> None:
    auth_db.ensure_schema()

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


def test_shop_runtime_bindings_schema_has_required_status_columns() -> None:
    auth_db.ensure_schema()

    assert {
        "profile_status",
        "playbook_status",
        "cron_pause_reason",
    }.issubset(set(auth_db._table_columns("shop_runtime_bindings")))  # noqa: SLF001


def test_playbooks_schema_has_lifecycle_and_audit_columns() -> None:
    auth_db.ensure_schema()

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
