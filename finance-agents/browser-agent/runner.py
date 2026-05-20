from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from finance_browser_agent.playbook_interpreter import validate_step_actions
from finance_browser_agent.quality_gate import validate_rows


def run_message(message: dict[str, Any]) -> dict[str, Any]:
    """Entry point invoked by ``dispatcher_loop.BrowserDispatcherLoop`` for each claimed job.

    Two execution modes:
    - default / ``BROWSER_AGENT_RUNNER_MODE=playwright`` → real Chrome via Playwright
      persistent context (production path; see ``playwright_runner.run_playbook_with_playwright``).
    - ``BROWSER_AGENT_RUNNER_MODE=synthetic`` → consume rows from ``params.rows`` or
      ``params.input_rows_path``; used by unit tests and dry-runs without a browser. The
      playbook's quality_gate still runs.
    """
    mode = (os.getenv("BROWSER_AGENT_RUNNER_MODE", "").strip() or "playwright").lower()
    if mode == "playwright":
        from finance_browser_agent.playwright_runner import run_playbook_with_playwright

        return run_playbook_with_playwright(message)
    return _run_synthetic(message)


def _run_synthetic(message: dict[str, Any]) -> dict[str, Any]:
    playbook = dict(message.get("playbook_body") or {})
    validate_step_actions(list(playbook.get("steps") or []))
    output = dict(playbook.get("output") or {})
    quality_gate = dict(playbook.get("quality_gate") or {})
    params = dict(message.get("params") or {})
    input_rows_path = params.get("input_rows_path")
    if input_rows_path:
        rows = json.loads(Path(str(input_rows_path)).read_text(encoding="utf-8"))
    else:
        rows = list(params.get("rows") or [])
    quality = validate_rows(
        rows=rows,
        columns=list(output.get("columns") or []),
        item_key_fields=list(output.get("item_key_fields") or []),
        amount_field=str(quality_gate.get("amount_field") or "amount"),
        date_field=str(quality_gate.get("date_field") or "biz_date"),
        biz_date=str(params.get("biz_date") or ""),
        expected_row_count=params.get("expected_row_count"),
        expected_amount_total=params.get("expected_amount_total"),
    )
    if not quality.get("success"):
        return {
            "job_id": message["job_id"],
            "status": "failed",
            "fail_reason": quality.get("fail_reason") or "DATA_MISMATCH",
            "error_info": {"message": quality.get("error") or "quality gate failed"},
        }
    item_key_fields = list(output.get("item_key_fields") or [])
    records = []
    for row in rows:
        item_key_values = {field: row.get(field) for field in item_key_fields}
        records.append(
            {
                "item_key": "|".join(str(item_key_values[field] or "") for field in item_key_fields),
                "item_key_values": item_key_values,
                "payload": row,
            }
        )
    return {
        "job_id": message["job_id"],
        "status": "success",
        "records": records,
        "capture_files": [],
        "quality_summary": quality["summary"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    message = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = run_message(message)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
