from __future__ import annotations
import asyncio, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools import platform_connections as pc


def test_alipay_create_auth_session_returns_longlived_landing_url(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("TALLY_PUBLIC_BASE_URL", "https://tally.example.com")
    monkeypatch.setattr(pc, "_require_user", lambda t: {"user_id": "u1", "company_id": "c1"})

    result = asyncio.run(pc._handle_create_auth_session({
        "auth_token": "tok", "platform_code": "alipay",
        "merchant_display_name": "搜卡手游专营店武汉搜卡科技有限公司",
        "return_path": "/data-connections", "mode": "real",
    }))

    assert result["success"] is True
    url = result["auth_url"]
    assert url.startswith("https://tally.example.com/p/alipay-auth?t=")
    from auth.alipay_auth_invite import verify_alipay_auth_invite_token
    tok = url.split("t=", 1)[1]
    p = verify_alipay_auth_invite_token(tok)
    assert p["company_id"] == "c1" and p["merchant_display_name"].startswith("搜卡手游专营店")


def test_alipay_create_auth_session_requires_base_url(monkeypatch):
    monkeypatch.delenv("TALLY_PUBLIC_BASE_URL", raising=False)
    monkeypatch.setattr(pc, "_require_user", lambda t: {"user_id": "u1", "company_id": "c1"})
    result = asyncio.run(pc._handle_create_auth_session({
        "auth_token": "tok", "platform_code": "alipay",
        "merchant_display_name": "x", "mode": "real",
    }))
    assert result["success"] is False
    assert "TALLY_PUBLIC_BASE_URL" in result["error"]


def test_invite_describe_valid_and_idempotent(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    from auth.alipay_auth_invite import build_alipay_auth_invite_token
    tok = build_alipay_auth_invite_token(company_id="c1", operator_user_id="u1",
        merchant_display_name="搜卡手游专营店武汉搜卡科技有限公司", expected_alipay_account="s4k4net@163.com")
    monkeypatch.setattr(pc.auth_db, "get_active_alipay_connection_for_shop", lambda **k: None)
    r = asyncio.run(pc.handle_tool_call("alipay_auth_invite_describe", {"token": tok}))
    assert r["success"] and r["valid"] and r["already_authorized"] is False
    assert r["merchant_display_name"].startswith("搜卡手游专营店")
    assert r["expected_alipay_account"] == "s4k4net@163.com"
    monkeypatch.setattr(pc.auth_db, "get_active_alipay_connection_for_shop", lambda **k: {"id": "conn-1"})
    r2 = asyncio.run(pc.handle_tool_call("alipay_auth_invite_describe", {"token": tok}))
    assert r2["already_authorized"] is True


def test_invite_describe_invalid_token(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    r = asyncio.run(pc.handle_tool_call("alipay_auth_invite_describe", {"token": "garbage"}))
    assert r["success"] is True and r["valid"] is False


def test_invite_continue_creates_session_without_login(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    from auth.alipay_auth_invite import build_alipay_auth_invite_token
    tok = build_alipay_auth_invite_token(company_id="c1", operator_user_id="u1",
        merchant_display_name="搜卡手游专营店武汉搜卡科技有限公司")
    captured = {}
    monkeypatch.setattr(pc, "_create_alipay_session_for_invite",
        lambda **k: captured.update(k) or {"success": True, "auth_url": "https://openauth.alipay.com/x?state=s1", "state": "s1"})
    r = asyncio.run(pc.handle_tool_call("alipay_auth_invite_continue", {"token": tok}))
    assert r["success"] is True
    assert r["auth_url"].startswith("https://openauth.alipay.com/")
    assert captured["company_id"] == "c1" and captured["operator_user_id"] == "u1"


def test_invite_continue_invalid_token(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    r = asyncio.run(pc.handle_tool_call("alipay_auth_invite_continue", {"token": "garbage"}))
    assert r["success"] is False
