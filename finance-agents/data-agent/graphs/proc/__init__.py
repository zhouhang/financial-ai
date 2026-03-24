"""数据整理子图模块 (proc)

包含数据整理工作流的节点、路由和子图构建函数。

流程：
  get_rule_node → 规则存在？
    ├─ 否 → 返回：规则不存在 → END
    └─ 是 → check_file_node → 校验通过？
              ├─ 否 → 返回：文件校验失败 → END
              └─ 是 → proc_task_execute_node → result_node → END

文件结构：
  proc/
  ├── __init__.py          # 本文件，重新导出所有公共接口
  ├── prompts.py           # 各节点系统提示词
  ├── nodes.py             # 节点函数
  └── routers.py           # 路由函数和子图构建
"""

from __future__ import annotations

# ── 节点函数 ──────────────────────────────────────────────────────────────────
from graphs.proc.nodes import (
    build_proc_start_message,
    proc_task_execute_node,
    result_node,
)

# ── 公共节点（从 main_graph 导入）──────────────────────────────────────────────
from graphs.main_graph.public_nodes import (
    get_rule_node,
    check_file_node,
)

# ── 路由函数 & 子图构建 ────────────────────────────────────────────────────────
from graphs.proc.routers import (
    route_after_get_rule,
    route_after_check_file,
    build_proc_subgraph,
)

__all__ = [
    # 节点函数
    "build_proc_start_message",
    "get_rule_node",
    "check_file_node",
    "proc_task_execute_node",
    "result_node",
    # 路由函数
    "route_after_get_rule",
    "route_after_check_file",
    # 子图构建
    "build_proc_subgraph",
]
