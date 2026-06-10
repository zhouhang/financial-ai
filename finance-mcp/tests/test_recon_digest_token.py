from __future__ import annotations

from datetime import datetime, timezone
import sys
from pathlib import Path

import jwt
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from auth.recon_digest_token import build_recon_digest_token, verify_recon_digest_token


def test_recon_digest_token_roundtrip_boss_view() -> None:
    token = build_recon_digest_token(
        digest_id="digest-001",
        company_id="company-001",
        view="boss",
        biz_date="2026-06-05",
        domain="ecom",
        ttl_seconds=60,
    )

    payload = verify_recon_digest_token(token)

    assert payload is not None
    assert payload["purpose"] == "recon_digest_detail"
    assert payload["digest_id"] == "digest-001"
    assert payload["company_id"] == "company-001"
    assert payload["view"] == "boss"
    assert payload["biz_date"] == "2026-06-05"
    assert payload["domain"] == "ecom"


def test_recon_digest_token_rejects_wrong_expected_view() -> None:
    token = build_recon_digest_token(
        digest_id="digest-001",
        company_id="company-001",
        view="boss",
        biz_date="2026-06-05",
        domain="ecom",
        ttl_seconds=60,
    )

    assert verify_recon_digest_token(token, expected_view="finance") is None


def test_recon_digest_token_rejects_garbage() -> None:
    assert verify_recon_digest_token("not-a-token") is None


def test_recon_digest_token_has_no_expiry_by_default() -> None:
    token = build_recon_digest_token(
        digest_id="digest-001",
        company_id="company-001",
        view="finance",
        biz_date="2026-06-05",
        domain="ecom",
    )

    decoded = jwt.decode(token, options={"verify_signature": False})

    assert "exp" not in decoded
    assert verify_recon_digest_token(token, expected_view="finance") is not None


def test_recon_digest_token_explicit_ttl_seconds_roundtrips() -> None:
    token = build_recon_digest_token(
        digest_id="digest-001",
        company_id="company-001",
        view="finance",
        biz_date="2026-06-05",
        ttl_seconds=60,
    )

    decoded = jwt.decode(token, options={"verify_signature": False})
    payload = verify_recon_digest_token(token, expected_view="finance")

    assert "exp" in decoded
    assert decoded["exp"] > int(datetime.now(timezone.utc).timestamp())
    assert payload is not None
    assert payload["view"] == "finance"


def test_recon_digest_token_build_rejects_unsupported_view() -> None:
    with pytest.raises(ValueError):
        build_recon_digest_token(
            digest_id="digest-001",
            company_id="company-001",
            view="operator",
            biz_date="2026-06-05",
        )


def test_recon_digest_token_verify_rejects_unsupported_view() -> None:
    token = jwt.encode(
        {
            "purpose": "recon_digest_detail",
            "digest_id": "digest-001",
            "company_id": "company-001",
            "view": "operator",
            "biz_date": "2026-06-05",
        },
        "tally-secret-change-in-production",
        algorithm="HS256",
    )

    assert verify_recon_digest_token(token) is None


def test_recon_digest_token_verify_rejects_wrong_purpose() -> None:
    token = jwt.encode(
        {
            "purpose": "other",
            "digest_id": "digest-001",
            "company_id": "company-001",
            "view": "boss",
            "biz_date": "2026-06-05",
        },
        "tally-secret-change-in-production",
        algorithm="HS256",
    )

    assert verify_recon_digest_token(token) is None


@pytest.mark.parametrize(
    "missing_claim",
    ["digest_id", "company_id", "biz_date"],
)
def test_recon_digest_token_verify_rejects_missing_required_claim(missing_claim: str) -> None:
    payload = {
        "purpose": "recon_digest_detail",
        "digest_id": "digest-001",
        "company_id": "company-001",
        "view": "boss",
        "biz_date": "2026-06-05",
    }
    payload.pop(missing_claim)
    token = jwt.encode(payload, "tally-secret-change-in-production", algorithm="HS256")

    assert verify_recon_digest_token(token) is None
