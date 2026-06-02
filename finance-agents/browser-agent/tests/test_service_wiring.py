from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import service


def test_waiting_reconciler_removed_from_browser_agent() -> None:
    # Reapers now live in finance-cron; the agent must not run them.
    assert not hasattr(service, "_waiting_reconciler")
    src = inspect.getsource(service.main)
    assert "_waiting_reconciler" not in src
