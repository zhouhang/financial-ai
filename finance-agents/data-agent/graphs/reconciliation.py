"""对账子图 (Sub-Graph) — 第2层：规则生成工作流

⚠️ 兼容层：此文件已重构为模块化结构，代码移至 reconciliation/ 目录。
本文件保留以确保向后兼容，所有导入从新模块重新导出。

新结构：
  reconciliation/
  ├── __init__.py      # 重新导出所有接口
  ├── helpers.py       # 辅助函数
  ├── parsers.py       # LLM 解析函数
  ├── nodes.py         # 节点函数
  └── routers.py       # 路由函数和子图构建

原始代码备份在 reconciliation_old.py
"""

# Re-export everything from the new modular structure
from graphs.reconciliation import *  # noqa: F401, F403
