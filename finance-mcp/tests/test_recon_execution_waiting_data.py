from __future__ import annotations

import sys
from pathlib import Path

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from auth import db as auth_db


def test_recon_execution_queue_schema_has_waiting_data_columns(monkeypatch) -> None:
    monkeypatch.setattr(auth_db, "_table_exists", lambda table_name, schema="public": table_name == "recon_execution_queue")
    monkeypatch.setattr(
        auth_db,
        "_column_exists",
        lambda table_name, column_name, schema="public": column_name
        in {
            "next_retry_at",
            "wait_deadline_at",
            "waiting_reason",
            "waiting_datasets",
            "collection_job_ids",
        },
    )
    monkeypatch.setattr(auth_db, "_constraint_exists", lambda *args, **kwargs: True)

    assert auth_db._recon_execution_queue_schema_ready()  # noqa: SLF001
