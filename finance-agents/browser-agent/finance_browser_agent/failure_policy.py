"""Browser collection failure classification.

Deterministic failures (page changed, login expired, risk verification triggered, data quality
mismatch, or upstream-known unhealthy binding) must not be retried — the cause won't fix itself
within the retry window. Transient failures (agent offline / timeout / Chrome crash / network
hiccup / unknown OTHER) get up to 3 retries spaced ~30 min apart.

Used by the browser-agent dispatcher loop after a runner returns a failed TASK_RESULT, and by the
cloud-side ``mark_browser_sync_job_failed`` to decide whether to reschedule the sync_job back to
``pending`` with ``next_retry_at`` set.
"""

from __future__ import annotations

from dataclasses import dataclass


DETERMINISTIC_FAILURES = frozenset(
    {
        "PAGE_CHANGED",
        "AUTH_EXPIRED",
        "RISK_VERIFICATION",
        "DATA_MISMATCH",
        "UNHEALTHY_BINDING",
    }
)

TRANSIENT_FAILURES = frozenset(
    {
        "AGENT_OFFLINE",
        "TIMEOUT",
        "CHROME_CRASH",
        "NETWORK_ERROR",
        "EXPORT_REPORT_NOT_READY",
        "OTHER",
    }
)


@dataclass(frozen=True)
class FailurePolicy:
    normalized_reason: str
    retryable: bool
    max_attempts: int = 3
    retry_delay_seconds: int = 1800


def classify_failure(reason: str | None) -> FailurePolicy:
    """Classify a browser fail_reason into a retry policy.

    Unknown reasons are normalized to ``OTHER`` and treated as transient. This keeps the cloud
    side conservative: if browser-agent emits a reason we don't yet recognize, retry rather than
    silently dropping the sync_job into a permanent failed state.
    """
    normalized = str(reason or "OTHER").strip().upper() or "OTHER"
    if normalized in DETERMINISTIC_FAILURES:
        return FailurePolicy(normalized_reason=normalized, retryable=False)
    if normalized not in TRANSIENT_FAILURES:
        normalized = "OTHER"
    return FailurePolicy(normalized_reason=normalized, retryable=True)
