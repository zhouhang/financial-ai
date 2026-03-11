"""proc 子图路由函数与子图构建模块

包含：
- route_after_get_rule    : get_proc_rule_node 之后的条件路由
- route_after_check_file  : check_file_node 之后的条件路由
- build_proc_graph_subgraph : 构建并返回 StateGraph（未编译）
"""

from __future__ import annotations

import time
from typing import Callable

from langgraph.graph import END, StateGraph

from app.models import AgentState, ProcAgentPhase
from app.graphs.proc.nodes import (
    welcome_node,
    get_proc_rule_node,
    check_file_node,
    proc_task_execute_node,
    result_node,
)

# ── 停顿配置 ─────────────────────────────────────────────────────────────────────────────
# 每个节点成功完成后的停顿时长（秒），0 表示不停顿。
# 修改此处即可全局调整，无需修改各节点函数。
_NODE_PAUSE_SECONDS: float = 0


def _with_pause(node_fn: Callable[[AgentState], dict]) -> Callable[[AgentState], dict]:
    """节点包装器：在节点执行完成后追加停顿。

    在 build_proc_graph_subgraph 中统一注入，节点内部不需包含任何 time.sleep 调用。
    """
    def wrapper(state: AgentState) -> dict:
        result = node_fn(state)
        if _NODE_PAUSE_SECONDS > 0:
            time.sleep(_NODE_PAUSE_SECONDS)
        return result
    wrapper.__name__ = node_fn.__name__
    wrapper.__doc__ = node_fn.__doc__
    return wrapper


# ══════════════════════════════════════════════════════════════════════════════
# 路由函数
# ══════════════════════════════════════════════════════════════════════════════

def route_after_get_rule(state: AgentState) -> str:
    """get_proc_rule_node 之后：规则存在则继续，否则结束。"""
    ctx = state.get("proc_graph_ctx") or {}
    phase = ctx.get("phase", "")
    if phase == ProcAgentPhase.RULE_NOT_FOUND.value:
        return END
    return "check_file_node"


def route_after_check_file(state: AgentState) -> str:
    """check_file_node 之后：校验通过则执行，否则结束。"""
    ctx = state.get("proc_graph_ctx") or {}
    phase = ctx.get("phase", "")
    if phase == ProcAgentPhase.FILE_CHECK_FAILED.value:
        return END
    return "proc_task_execute_node"


# ══════════════════════════════════════════════════════════════════════════════
# 子图构建
# ══════════════════════════════════════════════════════════════════════════════

def build_proc_graph_subgraph() -> StateGraph:
    """构建数据整理子图。

    流程图：
        welcome_node
            └─ get_proc_rule_node
                    ├─ 规则不存在 → END
                    └─ 规则存在 → check_file_node
                                      ├─ 校验失败 → END
                                      └─ 校验通过 → proc_task_execute_node → result_node → END

    Returns:
        未编译的 StateGraph，由主图调用 .compile() 后注册为子图节点。
    """
    sg = StateGraph(AgentState)

    # ── 节点 ─────────────────────────────────────────────────────────────────
    sg.add_node("welcome_node", welcome_node)
    sg.add_node("get_proc_rule_node", _with_pause(get_proc_rule_node))
    sg.add_node("check_file_node", _with_pause(check_file_node))
    sg.add_node("proc_task_execute_node", _with_pause(proc_task_execute_node))
    sg.add_node("result_node", result_node)

    # ── 入口 ─────────────────────────────────────────────────────────────────
    sg.set_entry_point("welcome_node")

    # ── 边 ───────────────────────────────────────────────────────────────────
    sg.add_edge("welcome_node", "get_proc_rule_node")

    sg.add_conditional_edges(
        "get_proc_rule_node",
        route_after_get_rule,
        {
            "check_file_node": "check_file_node",
            END: END,
        },
    )

    sg.add_conditional_edges(
        "check_file_node",
        route_after_check_file,
        {
            "proc_task_execute_node": "proc_task_execute_node",
            END: END,
        },
    )

    sg.add_edge("proc_task_execute_node", "result_node")
    sg.add_edge("result_node", END)

    return sg
