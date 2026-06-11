import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # finance-agents/data-agent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

mcp_client = importlib.import_module("tools.mcp_client")


def test_recon_diff_digestion_uses_long_running_timeout():
    assert mcp_client._get_result_wait_timeout("recon_diff_digestion") == 600.0
