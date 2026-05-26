from __future__ import annotations

import sys
from pathlib import Path

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from tools import data_sources


def test_build_browser_collection_columns_infers_temporal_keeps_ids_as_string():
    """Materialize schema columns from collected records.

    - 时间字段 (有时分秒) -> datetime；账期 (YYYYMMDD + 名称含账期) -> date
    - 订单号/金额 等保持 string：19 位订单号绝不能被判成 number（会丢精度/损坏）。
    值带尾部制表符也要能正确推断（导出产物）。
    """
    records = [
        {
            "payload": {
                "订单号": "3303691179052000067\t",
                "确认收货时间": "2026-05-25 15:52:39\t",
                "账期": "20260525\t",
                "订单实际金额（元）": "103\t",
            }
        },
        {
            "payload": {
                "订单号": "5117239838291024835\t",
                "确认收货时间": "2026-05-25 21:08:39\t",
                "账期": "20260525\t",
                "订单实际金额（元）": "50.25\t",
            }
        },
    ]

    columns = data_sources._build_browser_collection_columns(records)
    by_name = {c["name"]: c["data_type"] for c in columns}

    # field names preserved (clean) and ordered
    assert [c["name"] for c in columns] == ["订单号", "确认收货时间", "账期", "订单实际金额（元）"]
    assert by_name["确认收货时间"] == "datetime"
    assert by_name["账期"] == "date"
    # identifiers and amounts must NOT become number
    assert by_name["订单号"] == "string"
    assert by_name["订单实际金额（元）"] == "string"
