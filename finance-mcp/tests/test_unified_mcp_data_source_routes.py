from __future__ import annotations

import sys
from pathlib import Path

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

import unified_mcp_server
from tools.data_sources import create_tools as create_data_source_tools


def test_all_data_source_tools_are_routable() -> None:
    tool_names = {tool.name for tool in create_data_source_tools()}

    assert tool_names <= unified_mcp_server._DATA_SOURCE_TOOL_NAMES
