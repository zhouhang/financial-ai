"""Sample execution helpers for generated proc rules."""

from __future__ import annotations

from typing import Any

from tools.mcp_client import execution_proc_draft_trial


async def run_proc_sample(
    *,
    auth_token: str,
    rule_json: dict[str, Any],
    sources: list[dict[str, Any]],
    expected_target: str = "",
    expected_targets: list[str] | None = None,
) -> dict[str, Any]:
    """Run a generated proc rule against source sample rows."""
    targets = [item for item in list(expected_targets or []) if str(item).strip()]
    if not targets and expected_target:
        targets = [expected_target]
    payload = {
        "proc_rule_json": rule_json,
        "sample_datasets": [_to_sample_dataset(source) for source in sources],
        "expected_targets": targets,
        "require_both_sides": False,
    }
    return await execution_proc_draft_trial(auth_token=auth_token, payload=payload)


def _to_sample_dataset(source: dict[str, Any]) -> dict[str, Any]:
    table_name = str(
        source.get("table_name")
        or source.get("resource_key")
        or source.get("dataset_code")
        or source.get("dataset_name")
        or source.get("source_id")
        or ""
    ).strip()
    return {
        **source,
        "table_name": table_name,
        "sample_rows": list(source.get("sample_rows") or [])[:20],
    }
