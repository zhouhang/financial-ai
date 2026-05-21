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
