from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import jwt


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from graphs.recon.scheme_design import service as scheme_service
from graphs.recon.scheme_design.semantic_utils import ensure_dataset_semantic_context
from graphs.recon.scheme_design.service import JWT_ALGORITHM, JWT_SECRET, SchemeDesignService
from graphs.recon.scheme_design.session_store import InMemorySchemeDesignSessionStore
from graphs.recon.scheme_design.executor import FallbackSchemeDesignExecutor


def _auth_token() -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": "user_1",
            "user_id": "user_1",
            "username": "tester",
            "company_id": "company_1",
            "iat": now,
            "exp": now + timedelta(minutes=30),
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def test_browser_collection_technical_schema_does_not_become_semantic_fields() -> None:
    normalized = ensure_dataset_semantic_context(
        {
            "source_kind": "browser_playbook",
            "schema_summary": {
                "storage": "browser_collection_records",
                "source_type": "browser_collection_records",
            },
            "sample_rows": [
                {
                    "账期": "2026-05-25",
                    "订单号": "ORDER-001",
                }
            ],
        }
    )

    assert "storage" not in normalized["field_label_map"]
    assert "source_type" not in normalized["field_label_map"]
    assert [field["raw_name"] for field in normalized["fields"]] == ["账期", "订单号"]


def test_dataset_field_preview_filters_browser_collection_technical_fields(
    monkeypatch,
) -> None:
    async def fake_get_dataset(*args, **kwargs):
        return {
            "success": True,
            "dataset": {
                "id": "dataset-browser-1",
                "source_kind": "browser_playbook",
                "extract_config": {
                    "source_type": "browser_collection_records",
                    "storage": "browser_collection_records",
                },
                "schema_summary": {
                    "storage": "browser_collection_records",
                    "source_type": "browser_collection_records",
                },
                "field_label_map": {
                    "storage": "storage",
                    "source_type": "source_type",
                    "账期": "账期",
                },
                "fields": [
                    {"raw_name": "storage", "display_name": "storage"},
                    {"raw_name": "source_type", "display_name": "source_type"},
                    {"raw_name": "账期", "display_name": "账期"},
                ],
            },
        }

    monkeypatch.setattr(scheme_service, "data_source_get_dataset", fake_get_dataset)
    service = SchemeDesignService(
        store=InMemorySchemeDesignSessionStore(),
        executor=FallbackSchemeDesignExecutor(),
    )

    result = asyncio.run(
        service.get_dataset_field_preview(
            auth_token=_auth_token(),
            source_id="source-browser-1",
            dataset_id="dataset-browser-1",
        )
    )

    assert result["success"] is True
    assert result["fields"] == [{"raw_name": "账期", "display_name": "账期"}]
