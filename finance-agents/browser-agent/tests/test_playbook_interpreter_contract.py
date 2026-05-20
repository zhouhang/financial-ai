from __future__ import annotations

import json
import sys
from pathlib import Path

FINANCE_BROWSER_AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_BROWSER_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_BROWSER_AGENT_ROOT))

from runner import run_message


def test_runner_reads_rows_from_input_file_and_emits_task_result(tmp_path: Path) -> None:
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "output.json"
    rows_path = tmp_path / "rows.json"

    rows_path.write_text(
        json.dumps(
            [
                {"bill_no": "BILL-001", "amount": "1.00", "biz_date": "2026-05-18"},
                {"bill_no": "BILL-002", "amount": "2.00", "biz_date": "2026-05-18"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    input_path.write_text(
        json.dumps(
            {
                "job_id": "job-001",
                "playbook_body": {
                    "output": {
                        "item_key_fields": ["bill_no"],
                        "columns": [
                            {"name": "bill_no", "type": "string", "required": True},
                            {"name": "amount", "type": "decimal", "required": True},
                            {"name": "biz_date", "type": "date", "required": True},
                        ],
                    },
                    "quality_gate": {
                        "date_field": "biz_date",
                        "amount_field": "amount",
                    },
                },
                "params": {
                    "biz_date": "2026-05-18",
                    "input_rows_path": str(rows_path),
                    "expected_row_count": 2,
                    "expected_amount_total": "3.00",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = run_message(json.loads(input_path.read_text(encoding="utf-8")))

    assert result["status"] == "success"
    assert result["quality_summary"]["row_count"] == 2
    output_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    assert output_path.exists()
