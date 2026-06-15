from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from auth.recon_digest_token import (
    build_recon_digest_token,
    build_recon_run_exceptions_token,
)
from tools import execution_runs


@pytest.mark.asyncio
async def test_public_digest_bundle_rejects_view_mismatch() -> None:
    token = build_recon_digest_token(
        digest_id="digest-001",
        company_id="company-001",
        view="boss",
        biz_date="2026-06-05",
        domain="ecom",
        ttl_seconds=60,
    )

    result = await execution_runs.handle_tool_call(
        "recon_digest_public_bundle",
        {"token": token, "view": "finance"},
    )

    assert result["success"] is False
    assert "无效" in result["error"]


@pytest.mark.asyncio
async def test_public_digest_bundle_returns_repository_payload(monkeypatch) -> None:
    token = build_recon_digest_token(
        digest_id="digest-001",
        company_id="company-001",
        view="boss",
        biz_date="2026-06-05",
        domain="ecom",
        ttl_seconds=60,
    )
    captured: dict[str, object] = {}

    def fake_bundle(**kwargs):
        captured.update(kwargs)
        return {"success": True, "digest": {"id": kwargs["digest_id"]}}

    monkeypatch.setattr(
        execution_runs.recon_digest_detail_db,
        "get_public_digest_detail_bundle",
        fake_bundle,
    )

    result = await execution_runs.handle_tool_call(
        "recon_digest_public_bundle",
        {"token": token, "view": "boss", "line_limit": 250},
    )

    assert result["success"] is True
    assert result["digest"]["id"] == "digest-001"
    assert captured["company_id"] == "company-001"
    assert captured["domain"] == "ecom"
    assert captured["line_limit"] == 250


@pytest.mark.asyncio
async def test_public_digest_export_requires_finance_view() -> None:
    token = build_recon_digest_token(
        digest_id="digest-001",
        company_id="company-001",
        view="boss",
        biz_date="2026-06-05",
        domain="ecom",
    )

    result = await execution_runs.handle_tool_call(
        "recon_digest_public_export",
        {"token": token, "view": "boss"},
    )

    assert result["success"] is False
    assert "财务" in result["error"]


@pytest.mark.asyncio
async def test_public_digest_export_returns_full_rows(monkeypatch) -> None:
    token = build_recon_digest_token(
        digest_id="digest-001",
        company_id="company-001",
        view="finance",
        biz_date="2026-06-05",
        domain="ecom",
    )

    monkeypatch.setattr(
        execution_runs.recon_digest_detail_db,
        "get_public_digest_detail_bundle",
        lambda **kwargs: {
            "success": True,
            "domain": "ecom",
            "digest": {
                "structured": {
                    "rollup_scope": {
                        "plan_codes": ["p1"],
                        "recon_types": ["fund"],
                    }
                }
            },
        },
    )
    seen: dict[str, object] = {}

    def fake_rows(**kwargs):
        seen.update(kwargs)
        return [{"order_no": "O1", "recon_type": kwargs["recon_type"]}]

    monkeypatch.setattr(
        execution_runs.recon_digest_detail_db,
        "list_public_digest_diff_rows",
        fake_rows,
    )

    result = await execution_runs.handle_tool_call(
        "recon_digest_public_export",
        {"token": token, "view": "finance", "recon_type": "fund"},
    )

    assert result == {
        "success": True,
        "rows": [{"order_no": "O1", "recon_type": "fund"}],
        "total": 1,
    }
    assert seen["plan_codes"] == ["p1"]
    assert seen["recon_types"] == ["fund"]


@pytest.mark.asyncio
async def test_public_digest_export_resolves_domain_from_bundle_when_token_omits_it(monkeypatch) -> None:
    token = build_recon_digest_token(
        digest_id="digest-001",
        company_id="company-001",
        view="finance",
        biz_date="2026-06-05",
    )
    seen: dict[str, object] = {}

    monkeypatch.setattr(
        execution_runs.recon_digest_detail_db,
        "get_public_digest_detail_bundle",
        lambda **kwargs: {"success": True, "domain": "ecom", "digest": {"structured": {}}},
    )

    def fake_rows(**kwargs):
        seen.update(kwargs)
        return [{"order_no": "O1"}]

    monkeypatch.setattr(
        execution_runs.recon_digest_detail_db,
        "list_public_digest_diff_rows",
        fake_rows,
    )

    result = await execution_runs.handle_tool_call(
        "recon_digest_public_export",
        {"token": token, "view": "finance"},
    )

    assert result["success"] is True
    assert seen["domain"] == "ecom"


@pytest.mark.asyncio
async def test_digest_detail_link_create_requires_auth_and_checks_digest(monkeypatch) -> None:
    result = await execution_runs.handle_tool_call(
        "recon_digest_detail_link_create",
        {
            "digest_id": "digest-001",
            "view": "boss",
            "biz_date": "2026-06-05",
            "domain": "ecom",
        },
    )

    assert result["success"] is False
    assert "认证" in result["error"]

    monkeypatch.setattr(
        execution_runs,
        "_resolve_write_company_id",
        lambda token, explicit_company_id="": explicit_company_id or "company-001",
    )
    seen: dict[str, object] = {}

    def fake_bundle(**kwargs):
        seen.update(kwargs)
        return {"success": True, "domain": "ecom"}

    monkeypatch.setattr(
        execution_runs.recon_digest_detail_db,
        "get_public_digest_detail_bundle",
        fake_bundle,
    )

    ok = await execution_runs.handle_tool_call(
        "recon_digest_detail_link_create",
        {
            "auth_token": "valid-token",
            "digest_id": "digest-001",
            "view": "boss",
            "biz_date": "2026-06-05",
            "domain": "ecom",
        },
    )

    assert ok["success"] is True
    assert ok["path"].startswith("/recon/digests/")
    assert seen["company_id"] == "company-001"
    assert seen["digest_id"] == "digest-001"


@pytest.mark.asyncio
async def test_digest_detail_link_create_allows_system_token_with_explicit_company(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        execution_runs,
        "_resolve_write_company_id",
        lambda token, explicit_company_id="": explicit_company_id or "system-company",
    )
    seen: dict[str, object] = {}

    def fake_bundle(**kwargs):
        seen.update(kwargs)
        return {"success": True, "domain": "ecom"}

    monkeypatch.setattr(
        execution_runs.recon_digest_detail_db,
        "get_public_digest_detail_bundle",
        fake_bundle,
    )

    result = await execution_runs.handle_tool_call(
        "recon_digest_detail_link_create",
        {
            "auth_token": "system-token",
            "company_id": "company-001",
            "digest_id": "digest-001",
            "view": "boss",
            "biz_date": "2026-06-05",
            "domain": "ecom",
        },
    )

    assert result["success"] is True
    assert seen["company_id"] == "company-001"


@pytest.mark.asyncio
async def test_digest_subscription_upsert_and_list_use_resolved_company(monkeypatch) -> None:
    monkeypatch.setattr(
        execution_runs,
        "_resolve_write_company_id",
        lambda token, explicit_company_id="": explicit_company_id or "company-001",
    )
    captured: dict[str, object] = {}

    def fake_upsert(**kwargs):
        captured.update(kwargs)
        return {"id": "sub-001", "company_id": kwargs["company_id"], "view": kwargs["view"]}

    monkeypatch.setattr(
        execution_runs.recon_digest_finalizer_db,
        "create_or_update_digest_subscription",
        fake_upsert,
    )

    upsert = await execution_runs.handle_tool_call(
        "recon_digest_subscription_upsert",
        {
            "auth_token": "valid-token",
            "company_id": "company-001",
            "view": "boss",
            "recipient_json": {"user_id": "u1"},
            "scope": {"mode": "company_all"},
        },
    )

    assert upsert["success"] is True
    assert upsert["subscription"]["id"] == "sub-001"
    assert captured["company_id"] == "company-001"
    assert captured["recipient_json"] == {"user_id": "u1"}

    monkeypatch.setattr(
        execution_runs.recon_digest_finalizer_db,
        "list_digest_subscriptions",
        lambda **kwargs: [{"id": "sub-001", "view": kwargs["view"]}],
    )
    listed = await execution_runs.handle_tool_call(
        "recon_digest_subscription_list",
        {"auth_token": "valid-token", "company_id": "company-001", "view": "boss"},
    )

    assert listed == {
        "success": True,
        "count": 1,
        "subscriptions": [{"id": "sub-001", "view": "boss"}],
    }


@pytest.mark.asyncio
async def test_digest_finalize_daily_and_delivery_record_delegate_to_repository(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        execution_runs,
        "_resolve_write_company_id",
        lambda token, explicit_company_id="": explicit_company_id or "company-001",
    )
    seen: dict[str, object] = {}

    def fake_finalize(**kwargs):
        seen["finalize"] = kwargs
        return {"success": True, "ready_count": 1, "results": [{"status": "ready"}]}

    def fake_delivery(**kwargs):
        seen["delivery"] = kwargs
        return {"id": "delivery-001", "status": kwargs["status"]}

    monkeypatch.setattr(
        execution_runs.recon_digest_finalizer_db,
        "finalize_company_daily_digests",
        fake_finalize,
    )
    monkeypatch.setattr(
        execution_runs.recon_digest_finalizer_db,
        "upsert_digest_delivery_attempt",
        fake_delivery,
    )

    finalized = await execution_runs.handle_tool_call(
        "recon_digest_finalize_daily",
        {
            "auth_token": "valid-token",
            "company_id": "company-001",
            "biz_date": "2026-06-05",
            "view": "finance",
            "dry_run": True,
        },
    )
    delivery = await execution_runs.handle_tool_call(
        "recon_digest_delivery_record",
        {
            "auth_token": "valid-token",
            "company_id": "company-001",
            "digest_id": "digest-001",
            "subscription_id": "sub-001",
            "view": "finance",
            "status": "sent",
            "message_id": "msg-001",
            "detail_url": "https://example.test/detail",
        },
    )

    assert finalized["ready_count"] == 1
    assert seen["finalize"] == {
        "company_id": "company-001",
        "biz_date": "2026-06-05",
        "view": "finance",
        "dry_run": True,
    }
    assert delivery == {"success": True, "delivery": {"id": "delivery-001", "status": "sent"}}
    assert seen["delivery"]["message_id"] == "msg-001"


@pytest.mark.asyncio
async def test_public_exception_bundle_accepts_jwt_and_raw_run_id(monkeypatch) -> None:
    seen: list[dict[str, object]] = []

    def fake_bundle(**kwargs):
        seen.append(dict(kwargs))
        return {"run": {"id": kwargs["run_id"]}, "scheme": {}, "exceptions": []}

    monkeypatch.setattr(
        execution_runs.auth_db,
        "get_public_execution_run_exception_bundle",
        fake_bundle,
    )

    token = build_recon_run_exceptions_token(run_id="run-001", company_id="company-001")
    token_result = await execution_runs.handle_tool_call(
        "execution_run_public_exception_bundle",
        {"run_id": token},
    )
    raw_result = await execution_runs.handle_tool_call(
        "execution_run_public_exception_bundle",
        {"run_id": "run-002", "include_closed": True},
    )

    assert token_result["success"] is True
    assert raw_result["success"] is True
    assert [item["run_id"] for item in seen] == ["run-001", "run-002"]
    assert seen[0]["include_closed"] is False
    assert seen[1]["include_closed"] is True
