from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

DATA_AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(DATA_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(DATA_AGENT_ROOT))

from graphs.data_source import api


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app)


def _valid_registration_payload() -> dict:
    return {
        "title": "千牛每日资金账单",
        "credential_username": "finance_ops@example.com",
        "credential_password": "secret",
        "playbook_body": {"schema_version": "1.0", "steps": []},
    }


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

    client = _client()
    response = client.post(
        "/data-sources/browser-playbook/registrations",
        headers={"Authorization": "Bearer token-1"},
        json=_valid_registration_payload(),
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


def test_source_less_browser_registration_rejects_hidden_fields(monkeypatch) -> None:
    calls: list[dict] = []

    async def fake_register(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return {"success": True}

    monkeypatch.setattr(api, "data_source_register_browser_collection", fake_register)

    payload = {
        **_valid_registration_payload(),
        "source_id": "source-hidden",
        "playbook_id": "playbook-hidden",
        "version": "99",
        "verification_biz_date": "2026-05-20",
        "dataset_id": "dataset-hidden",
        "egress_group": "egress-hidden",
    }
    response = _client().post(
        "/data-sources/browser-playbook/registrations",
        headers={"Authorization": "Bearer token-1"},
        json=payload,
    )

    assert response.status_code == 422
    assert calls == []


def test_source_less_browser_registration_requires_authorization(monkeypatch) -> None:
    calls: list[dict] = []

    async def fake_register(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return {"success": True}

    monkeypatch.setattr(api, "data_source_register_browser_collection", fake_register)

    response = _client().post(
        "/data-sources/browser-playbook/registrations",
        json=_valid_registration_payload(),
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "未提供认证 token，请先登录"}
    assert calls == []


def test_source_less_browser_registration_returns_400_when_wrapper_fails(monkeypatch) -> None:
    calls: list[dict] = []

    async def fake_register(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return {"success": False, "error": "后端拒绝注册"}

    monkeypatch.setattr(api, "data_source_register_browser_collection", fake_register)

    response = _client().post(
        "/data-sources/browser-playbook/registrations",
        headers={"Authorization": "Bearer token-1"},
        json=_valid_registration_payload(),
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "后端拒绝注册"}
    assert len(calls) == 1
