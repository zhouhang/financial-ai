"""Tests for the per-login-identity browser profile ref derivation.

A shop's order + bill datasets (and any future datasets that authenticate as the same account
on the same platform) must resolve to ONE persistent Chrome profile, so they reuse a single
login session instead of each logging in (and risking same-account session kick-out).
"""
from __future__ import annotations

from tools.data_sources import _browser_login_profile_ref, _registrable_domain


def test_registrable_domain_strips_subdomains():
    assert _registrable_domain("mms.pinduoduo.com") == "pinduoduo.com"
    assert _registrable_domain("cashier.pinduoduo.com") == "pinduoduo.com"
    assert _registrable_domain("myseller.taobao.com") == "taobao.com"
    assert _registrable_domain("loginmyseller.taobao.com") == "taobao.com"
    assert _registrable_domain("taobao.com") == "taobao.com"


def test_registrable_domain_handles_compound_cn_suffix():
    assert _registrable_domain("shop.example.com.cn") == "example.com.cn"
    assert _registrable_domain("example.com.cn") == "example.com.cn"


def _pb(url: str) -> dict:
    return {"steps": [{"action": "navigate", "url": url}]}


def test_pdd_orders_and_bills_share_profile_via_sso_domain():
    # PDD orders live on mms.pinduoduo.com, bills on cashier.pinduoduo.com — one SSO login.
    orders = _browser_login_profile_ref(playbook_body=_pb("https://mms.pinduoduo.com/orders/list"), username="bk财务")
    bills = _browser_login_profile_ref(playbook_body=_pb("https://cashier.pinduoduo.com/main/bills"), username="bk财务")
    assert orders == bills
    assert orders.startswith("login::pinduoduo.com::")


def test_different_accounts_get_different_profiles():
    a = _browser_login_profile_ref(playbook_body=_pb("https://mms.pinduoduo.com/orders/list"), username="shopA")
    b = _browser_login_profile_ref(playbook_body=_pb("https://mms.pinduoduo.com/orders/list"), username="shopB")
    assert a != b


def test_same_username_different_platform_get_different_profiles():
    pdd = _browser_login_profile_ref(playbook_body=_pb("https://mms.pinduoduo.com/orders/list"), username="dup")
    tb = _browser_login_profile_ref(playbook_body=_pb("https://myseller.taobao.com/home.htm"), username="dup")
    assert pdd != tb


def test_blank_username_returns_empty_so_caller_falls_back():
    assert _browser_login_profile_ref(playbook_body=_pb("https://mms.pinduoduo.com/x"), username="") == ""


def test_no_navigate_url_returns_empty():
    assert _browser_login_profile_ref(playbook_body={"steps": [{"action": "wait_ms"}]}, username="u") == ""
