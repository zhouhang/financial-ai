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
)

# ── public_nodes.py ──────────────────────────────────────────────────────────
from .public_nodes import (
    get_rule_node,
    check_file_node,
)


def route_after_router(*args, **kwargs):
    from .routers import route_after_router as _route_after_router

    return _route_after_router(*args, **kwargs)


def build_main_graph(*args, **kwargs):
    from .routers import build_main_graph as _build_main_graph

    return _build_main_graph(*args, **kwargs)


def create_app(*args, **kwargs):
    from .routers import create_app as _create_app

    return _create_app(*args, **kwargs)


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
    # routers - 路由函数
    "route_after_router",
    # routers - 图构建
    "build_main_graph",
    "create_app",
    # public_nodes - 公共节点
    "get_rule_node",
    "check_file_node",
]
