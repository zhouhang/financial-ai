from __future__ import annotations

import sys
from pathlib import Path

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

import unified_mcp_server


def test_pending_authorization_tools_are_routed_to_platform_handler():
    assert "platform_list_pending_authorizations" in unified_mcp_server._PLATFORM_TOOL_NAMES
    assert "platform_claim_pending_authorization" in unified_mcp_server._PLATFORM_TOOL_NAMES
