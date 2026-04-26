"""SSE event helpers for rule generation workflows."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


NODE_LABELS: dict[str, str] = {
    "prepare_context": "准备上下文",
    "understand_rule": "理解业务规则",
    "field_binding": "绑定规则字段",
    "semantic_resolution": "自动消除歧义",
    "ambiguity_gate": "判断是否需要补充",
    "generate_or_repair_json": "生成规则",
    "lint_json": "校验规则",
    "build_sample_inputs": "读取真实样例数据",
    "run_sample": "样例执行",
    "assert_output": "校验输出结果",
    "result": "生成结果",
}


def now_iso() -> str:
    """Return an ISO timestamp suitable for frontend traces."""
    return datetime.now(timezone.utc).isoformat()


def build_event(
    event: str,
    *,
    run_id: str,
    side: str,
    target_table: str,
    node_code: str | None = None,
    node_status: str | None = None,
    node_name: str | None = None,
    attempt: int = 1,
    message: str = "",
    summary: dict[str, Any] | None = None,
    **payload: Any,
) -> dict[str, Any]:
    """Build a normalized event payload."""
    data: dict[str, Any] = {
        "event": event,
        "run_id": run_id,
        "side": side,
        "target_table": target_table,
        "message": message,
    }
    if node_code:
        data["node"] = {
            "code": node_code,
            "name": node_name or NODE_LABELS.get(node_code, node_code),
            "status": node_status or "running",
            "attempt": attempt,
        }
    if summary is not None:
        data["summary"] = summary
    data.update(payload)
    return data


def encode_sse(event: str, payload: dict[str, Any]) -> str:
    """Encode a payload as a Server-Sent Event frame."""
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
