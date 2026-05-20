from __future__ import annotations

from typing import Any


def validate_emergency_promote(playbook: dict[str, Any]) -> dict[str, Any]:
    if not bool(playbook.get("emergency_page_changed")):
        return {"success": True}

    reason = str(playbook.get("bypass_canary_reason") or "").strip()
    required_tokens = ["验证店", "验证日期", "审批人"]
    missing = [token for token in required_tokens if token not in reason]
    if not reason or missing:
        return {
            "success": False,
            "error": f"页面改版紧急旁路必须填写原因，并包含: {', '.join(required_tokens)}",
        }
    return {"success": True}
