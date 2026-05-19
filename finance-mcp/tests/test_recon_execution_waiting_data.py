from __future__ import annotations

import sys
from pathlib import Path

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from auth import db as auth_db


def test_recon_execution_queue_schema_has_waiting_data_columns() -> None:
    auth_db.ensure_schema()

    assert {
        "next_retry_at",
        "wait_deadline_at",
        "waiting_reason",
        "waiting_datasets",
        "collection_job_ids",
    }.issubset(set(auth_db._table_columns("recon_execution_queue")))  # noqa: SLF001
