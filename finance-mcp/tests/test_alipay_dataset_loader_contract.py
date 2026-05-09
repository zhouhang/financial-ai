from __future__ import annotations

import sys
from pathlib import Path

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from recon.mcp_server import dataset_loader


def test_alipay_bill_lines_loader_contract() -> None:
    assert "platform_alipay_bill_lines" in dataset_loader._DATASET_LOADERS
    assert "alipay_bill_lines" in dataset_loader._DATASET_LOADERS
