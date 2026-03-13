"""对账执行子图模块 (recon)

包含对账执行工作流的节点、路由和子图构建函数。

流程：
  get_rule_node → 规则存在？
    ├─ 否 → 返回：规则不存在 → END
    └─ 是 → check_file_node → 校验通过？
                ├─ 否 → 返回：文件校验失败 → END
                └─ 是 → recon_task_execution_node → recon_result_node → END

文件结构：
  recon/
  ├── __init__.py          # 本文件，重新导出所有公共接口
  ├── nodes.py             # 节点函数
  └── routers.py           # 路由函数和子图构建
"""

from __future__ import annotations

# ── 节点函数 ──────────────────────────────────────────────────────────────────
from graphs.recon.nodes import (
    recon_task_execution_node,
    recon_result_node,
)

# ── 公共节点（从 main_graph 导入）──────────────────────────────────────────────
from graphs.main_graph.public_nodes import (
    get_rule_node,
    check_file_node,
)

# ── 路由函数 & 子图构建 ────────────────────────────────────────────────────────
from graphs.recon.routers import (
    route_after_get_rule,
    route_after_check_file,
    build_recon_subgraph,
)

__all__ = [
    # 节点函数
    "get_rule_node",
    "check_file_node",
    "recon_task_execution_node",
    "recon_result_node",
    # 路由函数
    "route_after_get_rule",
    "route_after_check_file",
    # 子图构建
    "build_recon_subgraph",
]
