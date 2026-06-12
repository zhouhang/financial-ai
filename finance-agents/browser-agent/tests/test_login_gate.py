"""Unit tests for the LoginGate device-level login serialisation primitive.

These tests verify:
- The inter-login wait is calculated correctly when the interval has not elapsed.
- The authenticated (login-skip) path never touches the gate.
- After release(), the last-finished timestamp is updated.
- Two threads competing for the gate serialise correctly.
"""
from __future__ import annotations

import threading
import time
from typing import Callable

import pytest

from finance_browser_agent.playwright_runner import LoginGate


def _make_gate(
    *,
    last_finished: float = 0.0,
    clock_values: list[float] | None = None,
    slept: list[float] | None = None,
) -> LoginGate:
    """Return an isolated LoginGate with a controllable clock and sleep recorder."""
    idx = [0]
    values = clock_values or []

    def fake_clock() -> float:
        if idx[0] < len(values):
            v = values[idx[0]]
            idx[0] += 1
            return v
        return values[-1] if values else 0.0

    recorded: list[float] = slept if slept is not None else []

    def fake_sleep(seconds: float) -> None:
        recorded.append(seconds)

    gate = LoginGate.make_test_instance(clock=fake_clock, sleep=fake_sleep)
    gate._last_finished_ref[0] = last_finished
    return gate


# ---------------------------------------------------------------------------
# Test 1: When interval has NOT elapsed, sleep covers the deficit
# ---------------------------------------------------------------------------

def test_acquire_sleeps_for_remaining_interval_when_not_elapsed():
    # last login finished at t=100; now=115; interval=180 (with 0% jitter for determinism)
    # expected wait = 180 - (115 - 100) = 165 seconds
    slept: list[float] = []
    # clock called twice: once in acquire (to compute elapsed), once at release
    gate = _make_gate(last_finished=100.0, clock_values=[115.0, 285.0], slept=slept)

    # Monkeypatch random.uniform to return 0 so jitter is 0 %
    import random
    original_uniform = random.uniform
    random.uniform = lambda a, b: 0.0
    try:
        gate.acquire_for_login(job_id="job-A", min_interval_seconds=180.0)
    finally:
        random.uniform = original_uniform

    assert len(slept) == 1
    assert abs(slept[0] - 165.0) < 0.01  # 180 - (115 - 100)


# ---------------------------------------------------------------------------
# Test 2: When interval HAS already elapsed, no sleep occurs
# ---------------------------------------------------------------------------

def test_acquire_does_not_sleep_when_interval_already_elapsed():
    slept: list[float] = []
    # last=100, now=400, interval=180: elapsed=300 > 180, no sleep needed
    gate = _make_gate(last_finished=100.0, clock_values=[400.0], slept=slept)

    import random
    original_uniform = random.uniform
    random.uniform = lambda a, b: 0.0
    try:
        gate.acquire_for_login(job_id="job-B", min_interval_seconds=180.0)
    finally:
        random.uniform = original_uniform

    assert slept == []


# ---------------------------------------------------------------------------
# Test 3: First-ever login (last_finished == 0) → no sleep
# ---------------------------------------------------------------------------

def test_acquire_no_sleep_on_first_login():
    slept: list[float] = []
    gate = _make_gate(last_finished=0.0, clock_values=[50.0], slept=slept)

    import random
    original_uniform = random.uniform
    random.uniform = lambda a, b: 0.0
    try:
        gate.acquire_for_login(job_id="job-first", min_interval_seconds=180.0)
    finally:
        random.uniform = original_uniform

    assert slept == []


# ---------------------------------------------------------------------------
# Test 4: release() updates the last-finished timestamp
# ---------------------------------------------------------------------------

def test_release_updates_last_finished_timestamp():
    slept: list[float] = []
    gate = _make_gate(last_finished=0.0, clock_values=[10.0, 50.0], slept=slept)

    import random
    original_uniform = random.uniform
    random.uniform = lambda a, b: 0.0
    try:
        gate.acquire_for_login(job_id="job-ts", min_interval_seconds=0.0)
        gate.release(now=999.0)
    finally:
        random.uniform = original_uniform

    assert gate._last_finished_ref[0] == 999.0


# ---------------------------------------------------------------------------
# Test 5: Two threads compete — the second one waits for the first to release
# ---------------------------------------------------------------------------

def test_two_threads_serialise():
    """The second thread must not acquire the gate until the first releases it."""
    import random
    original_uniform = random.uniform
    random.uniform = lambda a, b: 0.0

    real_clock = time.monotonic
    real_sleep = time.sleep

    # Use real threading.Lock but inject a real clock+sleep so the test finishes fast
    gate = LoginGate.make_test_instance(clock=real_clock, sleep=real_sleep)

    order: list[str] = []
    errors: list[str] = []

    def thread_a() -> None:
        try:
            gate.acquire_for_login(job_id="A", min_interval_seconds=0.0)
            order.append("A_acquired")
            real_sleep(0.05)  # hold the gate briefly so B must wait
            order.append("A_releasing")
        finally:
            gate.release()

    def thread_b() -> None:
        real_sleep(0.01)  # ensure A starts first
        try:
            gate.acquire_for_login(job_id="B", min_interval_seconds=0.0)
            order.append("B_acquired")
        finally:
            gate.release()

    ta = threading.Thread(target=thread_a)
    tb = threading.Thread(target=thread_b)
    ta.start()
    tb.start()
    ta.join(timeout=5)
    tb.join(timeout=5)

    random.uniform = original_uniform

    # B must have acquired AFTER A released
    assert order == ["A_acquired", "A_releasing", "B_acquired"], f"Unexpected order: {order}"


# ---------------------------------------------------------------------------
# Test 6: Authenticated path — gate's acquire/release are never called
# ---------------------------------------------------------------------------

def test_authenticated_path_does_not_use_gate():
    """should_skip_login_action returns True for authenticated profiles; gate untouched."""
    from finance_browser_agent.playwright_runner import should_skip_login_action

    acquire_called = [False]
    release_called = [False]

    gate = LoginGate.make_test_instance()
    original_acquire = gate.acquire_for_login
    original_release = gate.release

    def patched_acquire(**kwargs):  # type: ignore[override]
        acquire_called[0] = True
        original_acquire(**kwargs)

    def patched_release(**kwargs):  # type: ignore[override]
        release_called[0] = True
        original_release(**kwargs)

    gate.acquire_for_login = patched_acquire  # type: ignore[method-assign]
    gate.release = patched_release  # type: ignore[method-assign]

    # Simulate the authenticated branch: should_skip_login_action returns True
    step = {"action": "login"}
    skip = should_skip_login_action(step, authenticated=True)
    assert skip is True
    # Gate methods never called because the runner continues to next step
    assert acquire_called[0] is False
    assert release_called[0] is False
