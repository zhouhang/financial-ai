from __future__ import annotations

from collections.abc import Iterable
from typing import Any

VALID_ACTIONS = {
    "login",
    "login_if_needed",
    "navigate",
    "click",
    "fill",
    "set_date",
    "wait_for",
    "extract_text",
    "extract_summary",
    "download",
    "parse_table",
    "assert",
}


def validate_step_actions(steps: Iterable[dict[str, Any]]) -> None:
    for step in steps:
        action = str(step.get("action") or "")
        if action not in VALID_ACTIONS:
            raise ValueError(f"unsupported action: {action}")
