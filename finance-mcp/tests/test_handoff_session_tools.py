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


def test_open_marks_controller_and_active(monkeypatch):
    import uuid as _uuid
    import auth.db as _db
    from tools.data_sources import (
        _handle_browser_handoff_session_control_open,
        _handle_browser_handoff_session_create,
    )

    monkeypatch.setattr(_db, "get_sync_job", lambda *, sync_job_id: None)
    created = asyncio.run(_handle_browser_handoff_session_create({
        "worker_token": _system_token(),
        "company_id": "00000000-0000-0000-0000-000000000001",
        "sync_job_id": str(_uuid.uuid4()),
        "agent_id": "agent-A",
        "profile_key": "店铺A",
        "reason": "RISK_VERIFICATION",
    }))

    opened = asyncio.run(_handle_browser_handoff_session_control_open({
        "token": created["handoff_token"],
        "controller_id": "ctrl-1",
        "agent_online": True,
    }))

    assert opened["success"] is True
    assert opened["session"]["status"] == "active"
    assert opened["session"]["controller_id"] == "ctrl-1"


def test_resume_requested_records_resuming_and_sync_status(monkeypatch):
    import uuid as _uuid
    import auth.db as _db
    from tools.data_sources import (
        _handle_browser_handoff_session_create,
        _handle_browser_handoff_session_event,
    )

    statuses = []
    monkeypatch.setattr(_db, "get_sync_job", lambda *, sync_job_id: None)
    monkeypatch.setattr(_db, "set_browser_sync_job_status", lambda **kwargs: statuses.append(kwargs) or 1)

    created = asyncio.run(_handle_browser_handoff_session_create({
        "worker_token": _system_token(),
        "company_id": "00000000-0000-0000-0000-000000000001",
        "sync_job_id": str(_uuid.uuid4()),
        "agent_id": "agent-A",
        "profile_key": "店铺A",
        "reason": "RISK_VERIFICATION",
    }))

    event = asyncio.run(_handle_browser_handoff_session_event({
        "token": created["handoff_token"],
        "controller_id": "ctrl-1",
        "event_type": "resume_requested",
        "status": "resuming",
    }))

    assert event["success"] is True
    assert event["session"]["status"] == "resuming"
    assert statuses[-1]["status"] == "resuming"


def test_public_token_cannot_mark_handoff_completed(monkeypatch):
    import uuid as _uuid
    import auth.db as _db
    from tools.data_sources import (
        _handle_browser_handoff_session_create,
        _handle_browser_handoff_session_event,
    )

    statuses = []
    monkeypatch.setattr(_db, "get_sync_job", lambda *, sync_job_id: None)
    monkeypatch.setattr(_db, "set_browser_sync_job_status", lambda **kwargs: statuses.append(kwargs) or 1)

    created = asyncio.run(_handle_browser_handoff_session_create({
        "worker_token": _system_token(),
        "company_id": "00000000-0000-0000-0000-000000000001",
        "sync_job_id": str(_uuid.uuid4()),
        "agent_id": "agent-A",
        "profile_key": "店铺A",
        "reason": "RISK_VERIFICATION",
    }))
    statuses.clear()

    event = asyncio.run(_handle_browser_handoff_session_event({
        "token": created["handoff_token"],
        "controller_id": "ctrl-1",
        "event_type": "handoff_completed",
        "status": "completed",
    }))

    assert event["success"] is False
    assert "不允许" in event["error"]
    assert statuses == []


def test_worker_token_can_mark_handoff_completed_with_canonical_event(monkeypatch):
    import uuid as _uuid
    import auth.db as _db
    from tools.data_sources import (
        _handle_browser_handoff_session_create,
        _handle_browser_handoff_session_event,
    )

    monkeypatch.setattr(_db, "get_sync_job", lambda *, sync_job_id: None)
    created = asyncio.run(_handle_browser_handoff_session_create({
        "worker_token": _system_token(),
        "company_id": "00000000-0000-0000-0000-000000000001",
        "sync_job_id": str(_uuid.uuid4()),
        "agent_id": "agent-A",
        "profile_key": "店铺A",
        "reason": "RISK_VERIFICATION",
    }))

    event = asyncio.run(_handle_browser_handoff_session_event({
        "worker_token": _system_token(),
        "handoff_session_id": created["handoff_session_id"],
        "event_type": "completed",
        "status": "completed",
    }))

    assert event["success"] is True
    assert event["session"]["status"] == "completed"
    row = _db.get_handoff_session(handoff_session_id=created["handoff_session_id"])
    assert row["audit_events"][-1]["event_type"] == "completed"
    assert row["audit_events"][-1]["handoff_session_id"] == created["handoff_session_id"]


def test_worker_token_can_mark_handoff_failed_with_canonical_event(monkeypatch):
    import uuid as _uuid
    import auth.db as _db
    from tools.data_sources import (
        _handle_browser_handoff_session_create,
        _handle_browser_handoff_session_event,
    )

    monkeypatch.setattr(_db, "get_sync_job", lambda *, sync_job_id: None)
    created = asyncio.run(_handle_browser_handoff_session_create({
        "worker_token": _system_token(),
        "company_id": "00000000-0000-0000-0000-000000000001",
        "sync_job_id": str(_uuid.uuid4()),
        "agent_id": "agent-A",
        "profile_key": "店铺A",
        "reason": "RISK_VERIFICATION",
    }))

    event = asyncio.run(_handle_browser_handoff_session_event({
        "worker_token": _system_token(),
        "handoff_session_id": created["handoff_session_id"],
        "event_type": "failed",
        "status": "failed",
        "reason": "unit failure",
    }))

    assert event["success"] is True
    assert event["session"]["status"] == "failed"
    row = _db.get_handoff_session(handoff_session_id=created["handoff_session_id"])
    assert row["audit_events"][-1]["event_type"] == "failed"
    assert row["audit_events"][-1]["reason"] == "unit failure"


def test_handoff_event_tool_accepts_stream_and_agent_offline_metadata(monkeypatch):
    import uuid as _uuid
    import auth.db as _db
    from tools.data_sources import (
        _handle_browser_handoff_session_create,
        _handle_browser_handoff_session_event,
    )

    monkeypatch.setattr(_db, "get_sync_job", lambda *, sync_job_id: None)
    created = asyncio.run(_handle_browser_handoff_session_create({
        "worker_token": _system_token(),
        "company_id": "00000000-0000-0000-0000-000000000001",
        "sync_job_id": str(_uuid.uuid4()),
        "agent_id": "agent-A",
        "profile_key": "店铺A",
        "reason": "RISK_VERIFICATION",
    }))

    stream = asyncio.run(_handle_browser_handoff_session_event({
        "worker_token": _system_token(),
        "handoff_session_id": created["handoff_session_id"],
        "event_type": "stream_started",
        "status": "active",
        "metadata": {"frame_width": 100, "data": "raw-base64"},
    }))
    offline = asyncio.run(_handle_browser_handoff_session_event({
        "token": created["handoff_token"],
        "controller_id": "ctrl-1",
        "event_type": "agent_offline",
        "status": "waiting_agent",
        "agent_id": "agent-A",
    }))

    assert stream["success"] is True
    assert offline["success"] is True
    row = _db.get_handoff_session(handoff_session_id=created["handoff_session_id"])
    assert row["audit_events"][-2]["event_type"] == "stream_started"
    assert row["audit_events"][-2]["frame_width"] == 100
    assert "raw-base64" not in str(row["audit_events"][-2])
    assert row["audit_events"][-1]["event_type"] == "agent_offline"


def test_open_final_handoff_session_returns_error(monkeypatch):
    import uuid as _uuid
    import auth.db as _db
    from tools.data_sources import (
        _handle_browser_handoff_session_control_open,
        _handle_browser_handoff_session_create,
    )

    monkeypatch.setattr(_db, "get_sync_job", lambda *, sync_job_id: None)
    created = asyncio.run(_handle_browser_handoff_session_create({
        "worker_token": _system_token(),
        "company_id": "00000000-0000-0000-0000-000000000001",
        "sync_job_id": str(_uuid.uuid4()),
        "agent_id": "agent-A",
        "profile_key": "店铺A",
        "reason": "RISK_VERIFICATION",
    }))
    _db.transition_handoff_session_status(
        handoff_session_id=created["handoff_session_id"],
        status="completed",
        event_type="handoff_completed",
    )

    opened = asyncio.run(_handle_browser_handoff_session_control_open({
        "token": created["handoff_token"],
        "controller_id": "ctrl-1",
        "agent_online": True,
    }))

    assert opened["success"] is False
    assert opened["session"]["status"] == "completed"
