from __future__ import annotations
import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from auth import alipay_auth_invite as inv


def test_sign_then_verify_roundtrip(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    tok = inv.build_alipay_auth_invite_token(
        company_id="c1", operator_user_id="u1",
        merchant_display_name="搜卡手游专营店武汉搜卡科技有限公司",
        expected_alipay_account="s4k4net@163.com", external_shop_id="SK001",
    )
    p = inv.verify_alipay_auth_invite_token(tok)
    assert p is not None
    assert p["purpose"] == "alipay_auth_invite"
    assert p["company_id"] == "c1"
    assert p["operator_user_id"] == "u1"
    assert p["merchant_display_name"].startswith("搜卡手游专营店")
    assert p["expected_alipay_account"] == "s4k4net@163.com"


def test_verify_rejects_tampered(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    tok = inv.build_alipay_auth_invite_token(company_id="c1", operator_user_id="u1", merchant_display_name="x")
    assert inv.verify_alipay_auth_invite_token(tok + "tamper") is None


def test_verify_rejects_wrong_purpose(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    import jwt
    from datetime import datetime, timezone, timedelta
    bad = jwt.encode({"purpose": "other", "exp": datetime.now(timezone.utc) + timedelta(days=1)}, "test-secret", algorithm="HS256")
    assert inv.verify_alipay_auth_invite_token(bad) is None


def test_verify_rejects_expired(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    tok = inv.build_alipay_auth_invite_token(company_id="c1", operator_user_id="u1", merchant_display_name="x", ttl_days=0)
    time.sleep(1)
    assert inv.verify_alipay_auth_invite_token(tok) is None


from auth import db as auth_db


class _Cur:
    def __init__(self, row): self._row=row; self.sql=""
    def __enter__(self): return self
    def __exit__(self,*a): return None
    def execute(self, sql, params=None): self.sql=sql
    def fetchone(self): return self._row

class _Conn:
    def __init__(self,row): self._c=_Cur(row)
    def __enter__(self): return self
    def __exit__(self,*a): return None
    def cursor(self,*a,**k): return self._c
    def commit(self): pass

class _CM:
    def __init__(self,row): self.row=row
    def __enter__(self): return _Conn(self.row)
    def __exit__(self,*a): return None


def test_get_active_alipay_connection_for_shop_filters(monkeypatch):
    cm = _CM({"id": "conn-1"})
    monkeypatch.setattr(auth_db, "get_conn", lambda: cm)
    out = auth_db.get_active_alipay_connection_for_shop(
        company_id="c1", merchant_display_name="搜卡手游专营店武汉搜卡科技有限公司", external_shop_id="SK001")
    assert out == {"id": "conn-1"}


def test_get_active_alipay_connection_for_shop_none(monkeypatch):
    cm = _CM(None)
    monkeypatch.setattr(auth_db, "get_conn", lambda: cm)
    out = auth_db.get_active_alipay_connection_for_shop(
        company_id="c1", merchant_display_name="不存在的店", external_shop_id="")
    assert out is None
