from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from finance_browser_agent.credentials import inject_credentials_into_params, open_credential_ref


def _fallback_ref(payload: dict[str, str]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return "enc:fallback:v1:" + base64.urlsafe_b64encode(raw).decode("ascii")


def test_open_credential_ref_reads_sealed_json_payload() -> None:
    credential_ref = _fallback_ref({"username": "finance_ops", "password": "secret"})

    assert open_credential_ref(credential_ref) == {"username": "finance_ops", "password": "secret"}


def test_inject_credentials_into_params_adds_login_keys_without_overwriting() -> None:
    credential_ref = _fallback_ref({"username": "finance_ops", "password": "secret"})
    params = {"biz_date": "2026-05-21", "login_username": "manual"}

    result = inject_credentials_into_params(params, credential_ref)

    assert result == {
        "biz_date": "2026-05-21",
        "login_username": "manual",
        "login_password": "secret",
    }
    assert params == {"biz_date": "2026-05-21", "login_username": "manual"}


def test_inject_credentials_ignores_empty_ref() -> None:
    assert inject_credentials_into_params({"biz_date": "2026-05-21"}, "") == {
        "biz_date": "2026-05-21"
    }
