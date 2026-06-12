from __future__ import annotations

import sys
from pathlib import Path


def prefer_data_agent_imports(test_file: str) -> None:
    data_agent_root = Path(test_file).resolve().parents[2]
    root_text = str(data_agent_root)
    try:
        sys.path.remove(root_text)
    except ValueError:
        pass
    sys.path.insert(0, root_text)

    data_agent_tools = str(data_agent_root / "tools")
    tools_module = sys.modules.get("tools")
    module_paths = [str(path) for path in getattr(tools_module, "__path__", [])]
    if tools_module is not None and data_agent_tools not in module_paths:
        for name in list(sys.modules):
            if name == "tools" or name.startswith("tools."):
                sys.modules.pop(name, None)
