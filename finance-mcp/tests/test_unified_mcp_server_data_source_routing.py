from __future__ import annotations

import unified_mcp_server


def test_browser_playbook_retry_tool_is_routed_to_data_source_module() -> None:
    assert (
        "data_source_retry_browser_playbook_verification"
        in unified_mcp_server._DATA_SOURCE_TOOL_NAMES
    )
