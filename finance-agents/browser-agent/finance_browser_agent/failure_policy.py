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
        "AUTH_EXPIRED",
        "RISK_VERIFICATION",
        "DATA_MISMATCH",
        "UNHEALTHY_BINDING",
        "BROWSER_CLOSED",
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

# PAGE_CHANGED is overloaded: most occurrences are transient render/latency hiccups that merely
# look like a selector miss (slow date-picker, async export not yet painted, brief interstitial),
# not a real page revision. So give it 2 retries with an ESCALATING backoff before committing to
# the terminal 'stale' pause: the first retry (5 min) catches short flakes; the second (15 min)
# catches the slower ones that clear within ~20 min (observed in prod — a page that failed both
# the run and the 5-min retry recovered later the same day). A genuine page change still fails all
# attempts and pauses (only ~20 min later; binding transition fires only on terminal failure).
_PAGE_CHANGED_RETRY_ATTEMPTS = 3  # initial try + 2 retries
_PAGE_CHANGED_RETRY_DELAYS_SECONDS = (300, 900)  # backoff after attempt 1, after attempt 2


def page_changed_retry_delay_seconds(current_attempt: int) -> int:
    """Escalating PAGE_CHANGED backoff keyed on the attempt that just failed.

    ``current_attempt`` is the just-failed attempt number (1-based; the claim increments it before
    the run). Returns the delay before the next retry — attempt 1 → 5 min, attempt 2 → 15 min. Past
    the schedule it returns the last value (the job goes terminal at max_attempts anyway, so this is
    only a safety fallback). The dispatcher passes this per-attempt value to the cloud failure
    handler, which sets ``next_retry_at = now + delay``.
    """
    idx = max(1, int(current_attempt or 1)) - 1
    delays = _PAGE_CHANGED_RETRY_DELAYS_SECONDS
    return delays[idx] if idx < len(delays) else delays[-1]

_BROWSER_CLOSED_MESSAGE_MARKERS = (
    "target page, context or browser has been closed",
    "target closed",
    "browser has been closed",
)


@dataclass(frozen=True)
class FailurePolicy:
    normalized_reason: str
    retryable: bool
    max_attempts: int = 3
    retry_delay_seconds: int = 1800


def classify_failure(reason: str | None, *, error_message: str | None = None) -> FailurePolicy:
    """Classify a browser fail_reason into a retry policy.

    Unknown reasons are normalized to ``OTHER`` and treated as transient. This keeps the cloud
    side conservative: if browser-agent emits a reason we don't yet recognize, retry rather than
    silently dropping the sync_job into a permanent failed state.
    """
    normalized = str(reason or "OTHER").strip().upper() or "OTHER"
    message = str(error_message or "").strip().lower()
    if any(marker in message for marker in _BROWSER_CLOSED_MESSAGE_MARKERS):
        normalized = "BROWSER_CLOSED"
    if normalized == "PAGE_CHANGED":
        return FailurePolicy(
            normalized_reason="PAGE_CHANGED",
            retryable=True,
            max_attempts=_PAGE_CHANGED_RETRY_ATTEMPTS,
            retry_delay_seconds=_PAGE_CHANGED_RETRY_DELAYS_SECONDS[0],
        )
    if normalized in DETERMINISTIC_FAILURES:
        return FailurePolicy(normalized_reason=normalized, retryable=False)
    if normalized not in TRANSIENT_FAILURES:
        normalized = "OTHER"
    return FailurePolicy(normalized_reason=normalized, retryable=True)
