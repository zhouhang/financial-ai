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


def test_browser_playbook_retry_route_dispatches_existing_task(monkeypatch) -> None:
    calls: list[dict] = []

    async def fake_retry(
        auth_token: str,
        source_id: str,
        *,
        verification_biz_date: str = "",
        dataset_id: str = "",
        force_collection: bool = False,
    ):
        calls.append(
            {
                "auth_token": auth_token,
                "source_id": source_id,
                "verification_biz_date": verification_biz_date,
                "dataset_id": dataset_id,
                "force_collection": force_collection,
            }
        )
        return {
            "success": True,
            "status": "verification_pending",
            "source_id": source_id,
            "verification_sync_job_id": "sync-retry-1",
            "verification_biz_date": "2026-05-20",
            "source": {"id": source_id, "name": "千牛每日资金账单"},
            "dataset": {"id": "dataset-1", "dataset_name": "千牛每日资金账单"},
            "message": "浏览器任务已重新下发到采集机",
        }

    monkeypatch.setattr(api, "data_source_retry_browser_playbook_verification", fake_retry)

    response = _client().post(
        "/data-sources/source-1/browser-playbook/retry",
        headers={"Authorization": "Bearer token-1"},
        json={},
    )

    assert response.status_code == 200
    assert calls == [
        {
            "auth_token": "token-1",
            "source_id": "source-1",
            "verification_biz_date": "",
            "dataset_id": "",
            "force_collection": True,
        }
    ]
    assert response.json() == {
        "success": True,
        "status": "verification_pending",
        "source_id": "source-1",
        "verification_sync_job_id": "sync-retry-1",
        "verification_biz_date": "2026-05-20",
        "source": {"id": "source-1", "name": "千牛每日资金账单"},
        "dataset": {"id": "dataset-1", "dataset_name": "千牛每日资金账单"},
        "playbook": None,
        "binding": None,
        "message": "浏览器任务已重新下发到采集机",
    }


def test_browser_playbook_retry_requires_authorization(monkeypatch) -> None:
    calls: list[dict] = []

    async def fake_retry(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return {"success": True}

    monkeypatch.setattr(api, "data_source_retry_browser_playbook_verification", fake_retry)

    response = _client().post(
        "/data-sources/source-1/browser-playbook/retry",
        json={},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "未提供认证 token，请先登录"}
    assert calls == []


def test_browser_playbook_retry_returns_400_when_wrapper_fails(monkeypatch) -> None:
    calls: list[dict] = []

    async def fake_retry(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return {"success": False, "error": "浏览器任务缺少运行时绑定，无法重试"}

    monkeypatch.setattr(api, "data_source_retry_browser_playbook_verification", fake_retry)

    response = _client().post(
        "/data-sources/source-1/browser-playbook/retry",
        headers={"Authorization": "Bearer token-1"},
        json={},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "浏览器任务缺少运行时绑定，无法重试"}
    assert len(calls) == 1


def test_browser_playbook_detail_route_returns_safe_task_detail(monkeypatch) -> None:
    calls: list[dict] = []

    async def fake_detail(
        auth_token: str,
        source_id: str,
        *,
        record_limit: int = 100,
        mode: str = "",
    ):
        calls.append(
            {
                "auth_token": auth_token,
                "source_id": source_id,
                "record_limit": record_limit,
                "mode": mode,
            }
        )
        return {
            "success": True,
            "mode": "real",
            "source": {"id": source_id, "name": "千牛每日资金账单"},
            "browser_verification": {"sync_job_id": "sync-1", "job_status": "success"},
            "record_count": 1,
            "latest_records": [
                {
                    "id": "record-1",
                    "biz_date": "2026-05-21",
                    "item_key": "bill-1",
                    "payload": {"账单号": "bill-1", "金额": "12.30"},
                }
            ],
            "playbook": {
                "playbook_id": "browser-collection-qn",
                "version": "1",
                "title": "千牛每日资金账单",
                "status": "active",
                "playbook_body": {"schema_version": "1.0", "steps": []},
            },
            "credential": {
                "username": "finance_ops@example.com",
                "password_saved": True,
            },
            "message": "",
        }

    monkeypatch.setattr(api, "data_source_get_browser_playbook_detail", fake_detail)

    response = _client().get(
        "/data-sources/source-1/browser-playbook/detail?record_limit=3&mode=real",
        headers={"Authorization": "Bearer token-1"},
    )

    assert response.status_code == 200
    assert calls == [
        {
            "auth_token": "token-1",
            "source_id": "source-1",
            "record_limit": 3,
            "mode": "real",
        }
    ]
    body = response.json()
    assert body["success"] is True
    assert body["source"]["id"] == "source-1"
    assert body["record_count"] == 1
    assert body["latest_records"][0]["payload"]["账单号"] == "bill-1"
    assert body["playbook"]["playbook_body"] == {"schema_version": "1.0", "steps": []}
    assert body["credential"] == {
        "username": "finance_ops@example.com",
        "password_saved": True,
    }
    assert "secret" not in str(body)


def test_browser_playbook_credential_update_route_does_not_echo_password(monkeypatch) -> None:
    calls: list[dict] = []

    async def fake_update(
        auth_token: str,
        source_id: str,
        *,
        credential_username: str,
        credential_password: str,
    ):
        calls.append(
            {
                "auth_token": auth_token,
                "source_id": source_id,
                "credential_username": credential_username,
                "credential_password": credential_password,
            }
        )
        return {
            "success": True,
            "source_id": source_id,
            "credential": {
                "username": credential_username,
                "password_saved": True,
            },
            "binding": {
                "profile_status": "verifying",
                "playbook_status": "ok",
                "cron_pause_reason": None,
            },
            "message": "浏览器任务凭证已保存",
        }

    monkeypatch.setattr(api, "data_source_update_browser_playbook_credential", fake_update)

    response = _client().post(
        "/data-sources/source-1/browser-playbook/credential",
        headers={"Authorization": "Bearer token-1"},
        json={
            "credential_username": "shop:ai财务",
            "credential_password": "secret-password",
        },
    )

    assert response.status_code == 200
    assert calls == [
        {
            "auth_token": "token-1",
            "source_id": "source-1",
            "credential_username": "shop:ai财务",
            "credential_password": "secret-password",
        }
    ]
    body = response.json()
    assert body == {
        "success": True,
        "source_id": "source-1",
        "credential": {
            "username": "shop:ai财务",
            "password_saved": True,
        },
        "binding": {
            "profile_status": "verifying",
            "playbook_status": "ok",
            "cron_pause_reason": None,
        },
        "message": "浏览器任务凭证已保存",
    }
    assert "secret-password" not in str(body)


def test_browser_playbook_credential_update_requires_authorization(monkeypatch) -> None:
    calls: list[dict] = []

    async def fake_update(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return {"success": True}

    monkeypatch.setattr(api, "data_source_update_browser_playbook_credential", fake_update)

    response = _client().post(
        "/data-sources/source-1/browser-playbook/credential",
        json={
            "credential_username": "shop:ai财务",
            "credential_password": "secret-password",
        },
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "未提供认证 token，请先登录"}
    assert calls == []


def test_browser_playbook_credential_update_returns_400_when_wrapper_fails(monkeypatch) -> None:
    async def fake_update(*args, **kwargs):
        return {"success": False, "error": "密码不能为空"}

    monkeypatch.setattr(api, "data_source_update_browser_playbook_credential", fake_update)

    response = _client().post(
        "/data-sources/source-1/browser-playbook/credential",
        headers={"Authorization": "Bearer token-1"},
        json={
            "credential_username": "shop:ai财务",
            "credential_password": "",
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "密码不能为空"}


def test_clear_browser_sync_job_route_dispatches_mcp_wrapper(monkeypatch) -> None:
    calls: list[dict] = []

    async def fake_clear(
        auth_token: str,
        sync_job_id: str,
        *,
        reason: str = "",
        mode: str = "",
    ):
        calls.append(
            {
                "auth_token": auth_token,
                "sync_job_id": sync_job_id,
                "reason": reason,
                "mode": mode,
            }
        )
        return {
            "success": True,
            "mode": "real",
            "job": {
                "id": sync_job_id,
                "job_status": "cancelled",
                "browser_fail_reason": "MANUAL_CLEARED",
            },
            "message": "当前浏览器任务已清除，可重新下发或等待后续任务执行",
        }

    monkeypatch.setattr(api, "data_source_clear_browser_sync_job", fake_clear)

    response = _client().post(
        "/sync-jobs/sync-001/clear",
        headers={"Authorization": "Bearer token-1"},
        json={"reason": "dev cleanup"},
    )

    assert response.status_code == 200
    assert calls == [
        {
            "auth_token": "token-1",
            "sync_job_id": "sync-001",
            "reason": "dev cleanup",
            "mode": "",
        }
    ]
    assert response.json()["success"] is True
    assert response.json()["job"]["job_status"] == "cancelled"
    assert response.json()["message"] == "当前浏览器任务已清除，可重新下发或等待后续任务执行"


def test_clear_browser_sync_job_route_requires_authorization(monkeypatch) -> None:
    calls: list[dict] = []

    async def fake_clear(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return {"success": True}

    monkeypatch.setattr(api, "data_source_clear_browser_sync_job", fake_clear)

    response = _client().post("/sync-jobs/sync-001/clear", json={})

    assert response.status_code == 401
    assert response.json() == {"detail": "未提供认证 token，请先登录"}
    assert calls == []


def test_clear_browser_sync_job_route_returns_400_when_wrapper_fails(monkeypatch) -> None:
    async def fake_clear(*args, **kwargs):
        return {"success": False, "error": "当前任务状态不允许清除: success"}

    monkeypatch.setattr(api, "data_source_clear_browser_sync_job", fake_clear)

    response = _client().post(
        "/sync-jobs/sync-001/clear",
        headers={"Authorization": "Bearer token-1"},
        json={},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "当前任务状态不允许清除: success"}
