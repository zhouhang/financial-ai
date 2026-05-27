from __future__ import annotations

import sys
from pathlib import Path

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from auth import db as auth_db
from tools import recon_auto_runs


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
            "data_wait_resume_count",
            "last_data_wait_resumed_at",
            "updated_at",
        },
    )
    monkeypatch.setattr(auth_db, "_constraint_exists", lambda *args, **kwargs: True)

    assert auth_db._recon_execution_queue_schema_ready()  # noqa: SLF001


def test_recon_execution_queue_schema_requires_updated_at(monkeypatch) -> None:
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
            "data_wait_resume_count",
            "last_data_wait_resumed_at",
        },
    )
    monkeypatch.setattr(auth_db, "_constraint_exists", lambda *args, **kwargs: True)

    assert not auth_db._recon_execution_queue_schema_ready()  # noqa: SLF001


def test_mark_recon_run_waiting_data_updates_queue_row(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_mark(
        *,
        job_id: str,
        waiting_reason: str,
        waiting_datasets: list[dict[str, object]],
        collection_job_ids: list[str],
        execution_run_id: str = "",
        wait_minutes: int,
    ) -> dict[str, object]:
        calls.append(
            {
                "job_id": job_id,
                "waiting_reason": waiting_reason,
                "waiting_datasets": waiting_datasets,
                "collection_job_ids": collection_job_ids,
                "execution_run_id": execution_run_id,
                "wait_minutes": wait_minutes,
            }
        )
        return {"id": job_id, "status": "waiting_data"}

    monkeypatch.setattr(auth_db, "mark_recon_run_waiting_data", fake_mark)

    row = auth_db.mark_recon_run_waiting_data(
        job_id="queue-001",
        waiting_reason="browser_collection_pending",
        waiting_datasets=[{"dataset_id": "dataset-001"}],
        collection_job_ids=["sync-001"],
        wait_minutes=90,
    )

    assert row["status"] == "waiting_data"
    assert calls[0]["collection_job_ids"] == ["sync-001"]


def test_recon_queue_waiting_data_tool_schema_accepts_execution_run_id() -> None:
    tool = next(t for t in recon_auto_runs.create_tools() if t.name == "recon_queue_waiting_data")

    assert tool.inputSchema["properties"]["execution_run_id"] == {"type": "string"}
