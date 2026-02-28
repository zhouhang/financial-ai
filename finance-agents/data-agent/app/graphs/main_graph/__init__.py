"""主图模块

重新导出所有公共接口，保持向后兼容。
"""

from __future__ import annotations

# ── forms.py ────────────────────────────────────────────────────────────────
from .forms import (
    generate_login_form,
    generate_register_form,
    generate_admin_login_form,
    generate_create_company_form,
    generate_create_department_form,
    generate_admin_view,
)

# ── nodes.py ────────────────────────────────────────────────────────────────
from .nodes import (
    # 系统提示词
    SYSTEM_PROMPT_NOT_LOGGED_IN,
    SYSTEM_PROMPT,
    RESULT_ANALYSIS_PROMPT,
    # 节点函数
    router_node,
    task_execution_node,
    result_analysis_node,
    ask_start_now_node,
    # 内部辅助函数（暴露以便测试）
    _do_start_task,
    _do_poll,
    _run_async_safe,
)

# ── routers.py ──────────────────────────────────────────────────────────────
from .routers import (
    # 路由函数
    route_after_router,
    route_after_reconciliation,
    route_after_ask_start,
    _route_after_edit_field_mapping,
    _route_after_edit_rule_config,
    _route_after_edit_preview,
    # 图构建
    build_main_graph,
    create_app,
)


__all__ = [
    # forms
    "generate_login_form",
    "generate_register_form",
    "generate_admin_login_form",
    "generate_create_company_form",
    "generate_create_department_form",
    "generate_admin_view",
    # nodes - 系统提示词
    "SYSTEM_PROMPT_NOT_LOGGED_IN",
    "SYSTEM_PROMPT",
    "RESULT_ANALYSIS_PROMPT",
    # nodes - 节点函数
    "router_node",
    "task_execution_node",
    "result_analysis_node",
    "ask_start_now_node",
    # nodes - 内部辅助
    "_do_start_task",
    "_do_poll",
    "_run_async_safe",
    # routers - 路由函数
    "route_after_router",
    "route_after_reconciliation",
    "route_after_ask_start",
    "_route_after_edit_field_mapping",
    "_route_after_edit_rule_config",
    "_route_after_edit_preview",
    # routers - 图构建
    "build_main_graph",
    "create_app",
]
