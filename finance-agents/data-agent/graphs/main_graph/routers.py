"""主图路由函数模块

包含主图的条件路由函数和图构建函数：
- route_after_router: router 之后的条件路由
- route_after_reconciliation: 对账子图完成后的路由
- route_after_ask_start: 询问是否立即执行后的路由
- _route_after_edit_*: 编辑规则流程的路由
- build_main_graph: 构建主 Agent 图
- create_app: 创建带有 MemorySaver 的可运行图实例
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from models import (
    AgentState,
    UserIntent,
)
from graphs.reconciliation import (
    build_reconciliation_subgraph,
)
from graphs.data_preparation import build_data_preparation_subgraph
from graphs.proc import build_proc_subgraph
from .nodes import (
    router_node,
)


# ══════════════════════════════════════════════════════════════════════════════
# 路由函数
# ══════════════════════════════════════════════════════════════════════════════

def route_after_router(state: AgentState) -> str:
    """router 之后的条件路由。"""
    intent = state.get("user_intent", "")
    phase = state.get("phase", "")

    if intent == "guest_reconciliation":
        return "reconciliation_subgraph"
    elif intent == UserIntent.CREATE_NEW_RULE.value:
        return "reconciliation_subgraph"
    elif intent == UserIntent.USE_EXISTING_RULE.value:
        return "reconciliation_subgraph"
    elif intent == UserIntent.EDIT_RULE.value:
        return "reconciliation_subgraph"
    elif intent == UserIntent.DATA_PROCESS.value:
        return "proc_subgraph"
    else:
        return END


# ══════════════════════════════════════════════════════════════════════════════
# 构建主图
# ══════════════════════════════════════════════════════════════════════════════

def build_main_graph() -> StateGraph:
    """构建主 Agent 图。"""

    # 数据准备子图（暂时保留为子图）
    data_preparation_sg = build_data_preparation_subgraph()
    reconciliation_sg = build_reconciliation_subgraph()
    proc_sg = build_proc_subgraph()

    graph = StateGraph(AgentState)

    # ── 节点 ──────────────────────────────────────────────────────────────
    graph.add_node("router", router_node)

    # 子图节点（reconciliation 收回子图，内部依赖 analysis_key + cache + pending_interrupt 防重放）
    graph.add_node("reconciliation_subgraph", reconciliation_sg.compile())
    graph.add_node("data_preparation_subgraph", data_preparation_sg.compile())
    graph.add_node("proc_subgraph", proc_sg.compile())

    # ── 边 ────────────────────────────────────────────────────────────────
    graph.set_entry_point("router")

    # router 后路由
    graph.add_conditional_edges("router", route_after_router, {
        "reconciliation_subgraph": "reconciliation_subgraph",
        "proc_subgraph": "proc_subgraph",
        END: END,
    })

    graph.add_edge("reconciliation_subgraph", END)
    graph.add_edge("proc_subgraph", END)

    return graph


def create_app():
    """创建带有 MemorySaver 的可运行图实例。"""
    memory = MemorySaver()
    graph = build_main_graph()
    return graph.compile(checkpointer=memory)
