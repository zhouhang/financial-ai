from __future__ import annotations

import sys
from pathlib import Path


DATA_AGENT_ROOT = Path(__file__).resolve().parents[1]
DATA_AGENT_TOOLS_DIR = DATA_AGENT_ROOT / "tools"


def _ensure_data_agent_import_root() -> None:
    root_text = str(DATA_AGENT_ROOT)
    if sys.path[:1] != [root_text]:
        try:
            sys.path.remove(root_text)
        except ValueError:
            pass
        sys.path.insert(0, root_text)


def _reset_foreign_tools_package() -> None:
    tools_module = sys.modules.get("tools")
    module_paths = [str(path) for path in getattr(tools_module, "__path__", [])]
    if tools_module is None or str(DATA_AGENT_TOOLS_DIR) in module_paths:
        return
    for name in list(sys.modules):
        if name == "tools" or name.startswith("tools."):
            sys.modules.pop(name, None)


_ensure_data_agent_import_root()
_reset_foreign_tools_package()


def pytest_collect_file(file_path, parent):  # type: ignore[no-untyped-def]
    if DATA_AGENT_ROOT in file_path.parents:
        _ensure_data_agent_import_root()
        _reset_foreign_tools_package()
    return None
