from __future__ import annotations

import sys
from pathlib import Path

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from recon.mcp_server import dataset_loader


def test_load_platform_order_lines_from_dataset_ref(monkeypatch):
    def fake_columns(table_name: str) -> set[str]:
        assert table_name == "platform_order_lines"
        return {"company_id", "data_source_id", "dataset_id", "biz_date", "payload", "updated_at"}

    def fake_query(*, source_key: str, query: dict):
        assert source_key == "source-001"
        assert query["dataset_id"] == "dataset-001"
        assert query["biz_date"] == "2026-05-06"
        return [{"payload": {"tid": "T1", "oid": "O1", "order_payment": "80.00"}}]

    monkeypatch.setattr(dataset_loader, "_table_columns", fake_columns)
    monkeypatch.setattr(dataset_loader, "_load_platform_order_line_rows", fake_query)

    df = dataset_loader.load_dataset_as_df(
        {
            "source_type": "platform_order_lines",
            "source_key": "source-001",
            "query": {"dataset_id": "dataset-001", "biz_date": "2026-05-06"},
        },
        "淘宝订单",
    )

    assert list(df["tid"]) == ["T1"]
    assert list(df["order_payment"]) == ["80.00"]
