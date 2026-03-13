"""recon 子图路由函数与子图构建模块

包含：
- route_after_get_rule    : get_rule_node 之后的条件路由
- route_after_check_file  : check_file_node 之后的条件路由
- build_recon_subgraph    : 构建并返回 StateGraph（未编译）
"""

from __future__ import annotations

import asyncio
import time
from typing import Callable

from langgraph.graph import END, StateGraph

from models import AgentState, ReconAgentPhase
from graphs.recon.nodes import (
    get_rule_node_for_recon,
    check_file_node_for_recon,
    recon_task_execution_node,
    recon_result_node,
)

# ── 停顿配置 ─────────────────────────────────────────────────────────────────────────────
# 每个节点成功完成后的停顿时长（秒），0 表示不停顿。
# 修改此处即可全局调整，无需修改各节点函数。
_NODE_PAUSE_SECONDS: float = 0


def _with_pause(node_fn: Callable) -> Callable:
    """节点包装器：在节点执行完成后追加停顿。支持同步和异步节点函数。"""
    if asyncio.iscoroutinefunction(node_fn):
        async def async_wrapper(state: AgentState) -> dict:
            result = await node_fn(state)
            if _NODE_PAUSE_SECONDS > 0:
                await asyncio.sleep(_NODE_PAUSE_SECONDS)
            return result
        async_wrapper.__name__ = node_fn.__name__
        async_wrapper.__doc__ = node_fn.__doc__
        return async_wrapper
    else:
        def sync_wrapper(state: AgentState) -> dict:
            result = node_fn(state)
            if _NODE_PAUSE_SECONDS > 0:
                time.sleep(_NODE_PAUSE_SECONDS)
            return result
        sync_wrapper.__name__ = node_fn.__name__
        sync_wrapper.__doc__ = node_fn.__doc__
        return sync_wrapper


# ══════════════════════════════════════════════════════════════════════════════
# 路由函数
# ══════════════════════════════════════════════════════════════════════════════

def route_after_get_rule(state: AgentState) -> str:
    """get_rule_node 之后：规则存在则继续，否则结束。"""
    ctx = state.get("recon_ctx") or {}
    phase = ctx.get("phase", "")
    if phase == ReconAgentPhase.RULE_NOT_FOUND.value:
        return END
    return "check_file_node"


def route_after_check_file(state: AgentState) -> str:
    """check_file_node 之后：校验通过则执行，否则结束。"""
    ctx = state.get("recon_ctx") or {}
    phase = ctx.get("phase", "")
    if phase == ReconAgentPhase.FILE_CHECK_FAILED.value:
        return END
    return "recon_task_execution_node"


# ══════════════════════════════════════════════════════════════════════════════
# 子图构建
# ══════════════════════════════════════════════════════════════════════════════

def build_recon_subgraph() -> StateGraph:
    """构建对账执行子图。

    流程图：
        get_rule_node
                ├─ 规则不存在 → END
                └─ 规则存在 → check_file_node
                                    ├─ 校验失败 → END
                                    └─ 校验通过 → recon_task_execution_node → recon_result_node → END

    Returns:
        未编译的 StateGraph，由主图调用 .compile() 后注册为子图节点。
    """
    sg = StateGraph(AgentState)

    # ── 节点 ─────────────────────────────────────────────────────────────────
    sg.add_node("get_rule_node", _with_pause(get_rule_node_for_recon))
    sg.add_node("check_file_node", _with_pause(check_file_node_for_recon))
    sg.add_node("recon_task_execution_node", _with_pause(recon_task_execution_node))
    sg.add_node("recon_result_node", recon_result_node)

    # ── 入口 ─────────────────────────────────────────────────────────────────
    sg.set_entry_point("get_rule_node")

    # ── 边 ───────────────────────────────────────────────────────────────────
    sg.add_conditional_edges(
        "get_rule_node",
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
            "recon_task_execution_node": "recon_task_execution_node",
            END: END,
        },
    )

    sg.add_edge("recon_task_execution_node", "recon_result_node")
    sg.add_edge("recon_result_node", END)

    return sg
