from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

DATA_AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(DATA_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(DATA_AGENT_ROOT))

from graphs.data_source import api


def test_source_less_browser_registration_route(monkeypatch) -> None:
    calls: list[dict] = []

    async def fake_register(
        auth_token: str,
        *,
        title: str,
        credential_username: str,
        credential_password: str,
        playbook_body: dict,
    ):
        calls.append(
            {
                "auth_token": auth_token,
                "title": title,
                "credential_username": credential_username,
                "credential_password": credential_password,
                "playbook_body": playbook_body,
            }
        )
        return {
            "success": True,
            "status": "verification_pending",
            "source_id": "source-1",
            "verification_sync_job_id": "sync-1",
            "verification_biz_date": "2026-05-20",
            "source": {"id": "source-1", "name": title},
            "dataset": {"id": "dataset-1", "dataset_name": title},
            "playbook": {"playbook_id": "browser-collection-abc", "version": "1"},
            "binding": {"credential_ref": "sealed"},
            "message": "ok",
        }

    monkeypatch.setattr(api, "data_source_register_browser_collection", fake_register)

    app = FastAPI()
    app.include_router(api.router)
    client = TestClient(app)
    response = client.post(
        "/data-sources/browser-playbook/registrations",
        headers={"Authorization": "Bearer token-1"},
        json={
            "title": "千牛每日资金账单",
            "credential_username": "finance_ops@example.com",
            "credential_password": "secret",
            "playbook_body": {"schema_version": "1.0", "steps": []},
        },
    )

    assert response.status_code == 200
    assert calls == [
        {
            "auth_token": "token-1",
            "title": "千牛每日资金账单",
            "credential_username": "finance_ops@example.com",
            "credential_password": "secret",
            "playbook_body": {"schema_version": "1.0", "steps": []},
        }
    ]
    assert response.json() == {
        "success": True,
        "status": "verification_pending",
        "source_id": "source-1",
        "verification_sync_job_id": "sync-1",
        "verification_biz_date": "2026-05-20",
        "source": {"id": "source-1", "name": "千牛每日资金账单"},
        "dataset": {"id": "dataset-1", "dataset_name": "千牛每日资金账单"},
        "playbook": {"playbook_id": "browser-collection-abc", "version": "1"},
        "binding": {"credential_ref": "sealed"},
        "message": "ok",
    }
