from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from finance_browser_agent.failure_policy import classify_failure


def test_deterministic_failures_are_not_retried() -> None:
    for reason in ["PAGE_CHANGED", "AUTH_EXPIRED", "RISK_VERIFICATION", "DATA_MISMATCH"]:
        policy = classify_failure(reason)
        assert policy.retryable is False
        assert policy.normalized_reason == reason


def test_transient_failures_are_retried() -> None:
    for reason in [
        "AGENT_OFFLINE",
        "TIMEOUT",
        "CHROME_CRASH",
        "NETWORK_ERROR",
        "EXPORT_REPORT_NOT_READY",
        "OTHER",
    ]:
        policy = classify_failure(reason)
        assert policy.retryable is True


def test_unhealthy_binding_is_terminal() -> None:
    policy = classify_failure("UNHEALTHY_BINDING")
    assert policy.retryable is False


def test_unknown_reason_normalizes_to_other_and_retryable() -> None:
    policy = classify_failure("something_weird")
    assert policy.retryable is True
    assert policy.normalized_reason == "OTHER"


def test_max_attempts_defaults_to_three() -> None:
    assert classify_failure("TIMEOUT").max_attempts == 3
    assert classify_failure("TIMEOUT").retry_delay_seconds == 1800
