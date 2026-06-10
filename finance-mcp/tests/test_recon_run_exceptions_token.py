from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from auth.recon_digest_token import (
    build_recon_digest_token,
    build_recon_run_exceptions_token,
    verify_recon_run_exceptions_token,
)


def test_run_exceptions_token_roundtrip() -> None:
    token = build_recon_run_exceptions_token(run_id="run-001", company_id="company-001")

    payload = verify_recon_run_exceptions_token(token)

    assert payload is not None
    assert payload["purpose"] == "recon_run_exceptions"
    assert payload["run_id"] == "run-001"
    assert payload["company_id"] == "company-001"


def test_run_exceptions_token_rejects_other_purpose() -> None:
    token = build_recon_digest_token(
        digest_id="digest-001",
        company_id="company-001",
        view="boss",
        biz_date="2026-06-05",
    )

    assert verify_recon_run_exceptions_token(token) is None


def test_run_exceptions_token_rejects_garbage() -> None:
    assert verify_recon_run_exceptions_token("not-a-token") is None
