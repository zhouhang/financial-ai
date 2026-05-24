from __future__ import annotations
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import auth.db as auth_db
import auth.jwt_utils as jwt_utils
from tools.data_sources import (
    _handle_browser_handoff_session_create,
    _handle_browser_handoff_session_describe,
)


def _system_token() -> str:
    # 用校验方实际使用的密钥签名(jwt_utils 在 import 时捕获 JWT_SECRET,
    # 避免 load_dotenv 时序导致的签名/校验密钥不一致)。
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": "sys", "role": "system", "iat": now, "exp": now + timedelta(hours=1), "jti": str(uuid.uuid4())},
        jwt_utils.JWT_SECRET,
        algorithm="HS256",
    )


def test_create_then_describe_by_token():
    auth_db.ensure_browser_handoff_schema()
    sj = str(uuid.uuid4())
    created = asyncio.run(
        _handle_browser_handoff_session_create(
            {
                "worker_token": _system_token(),
                "company_id": "00000000-0000-0000-0000-000000000001",
                "sync_job_id": sj,
                "agent_id": "browser-agent-local",
                "profile_key": "shop-x",
                "reason": "RISK_VERIFICATION",
            }
        )
    )
    assert created["success"] is True
    token = created["handoff_token"]
    assert token and created["handoff_session_id"]

    described = asyncio.run(_handle_browser_handoff_session_describe({"token": token}))
    assert described["success"] is True
    assert described["session"]["reason"] == "RISK_VERIFICATION"
    assert described["session"]["status"] == "pending"
    assert "credential" not in str(described).lower()


def test_describe_rejects_bad_token():
    described = asyncio.run(_handle_browser_handoff_session_describe({"token": "garbage"}))
    assert described["success"] is False


def test_create_reads_channel_and_owner_from_sync_job(monkeypatch):
    auth_db.ensure_browser_handoff_schema()
    import uuid as _uuid
    import auth.db as _db
    sj = str(_uuid.uuid4())
    fake_job = {"request_payload": {"params": {
        "handoff_channel_config_id": "11111111-1111-1111-1111-111111111111",
        "handoff_owner": {"name": "周行", "identifier": "u-zhou"},
    }}}
    monkeypatch.setattr(_db, "get_sync_job", lambda *, sync_job_id: fake_job)
    created = asyncio.run(_handle_browser_handoff_session_create({
        "worker_token": _system_token(),
        "company_id": "00000000-0000-0000-0000-000000000001",
        "sync_job_id": sj, "agent_id": "browser-agent-local",
        "profile_key": "shop-x", "reason": "RISK_VERIFICATION",
    }))
    assert created["success"] is True
    assert created["channel_config_id"] == "11111111-1111-1111-1111-111111111111"
    assert created["owner"]["identifier"] == "u-zhou"


def test_create_without_sync_job_payload_has_empty_owner(monkeypatch):
    auth_db.ensure_browser_handoff_schema()
    import uuid as _uuid
    import auth.db as _db
    monkeypatch.setattr(_db, "get_sync_job", lambda *, sync_job_id: None)
    created = asyncio.run(_handle_browser_handoff_session_create({
        "worker_token": _system_token(),
        "company_id": "00000000-0000-0000-0000-000000000001",
        "sync_job_id": str(_uuid.uuid4()), "agent_id": "a", "profile_key": "s", "reason": "RISK_VERIFICATION",
    }))
    assert created["success"] is True and created["owner"] == {}
