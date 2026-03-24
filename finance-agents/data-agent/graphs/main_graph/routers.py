"""主图路由函数模块

包含主图的条件路由函数和图构建函数：
- route_after_router: router 之后的条件路由
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
from graphs.proc import build_proc_subgraph
from graphs.recon import build_recon_subgraph
from .nodes import (
    router_node,
)


# ══════════════════════════════════════════════════════════════════════════════
# 路由函数
# ══════════════════════════════════════════════════════════════════════════════

def route_after_router(state: AgentState) -> str:
    """router 之后的条件路由。"""
    intent = state.get("user_intent", "")

    if intent == UserIntent.PROC.value:
        return "proc_subgraph"
    if intent == UserIntent.RECON.value:
        return "recon_subgraph"
    return END


# ══════════════════════════════════════════════════════════════════════════════
# 构建主图
# ══════════════════════════════════════════════════════════════════════════════

def build_main_graph() -> StateGraph:
    """构建主 Agent 图。"""
    proc_sg = build_proc_subgraph()
    recon_sg = build_recon_subgraph()

    graph = StateGraph(AgentState)

    # ── 节点 ──────────────────────────────────────────────────────────────
    graph.add_node("router", router_node)

    graph.add_node("proc_subgraph", proc_sg.compile())
    graph.add_node("recon_subgraph", recon_sg.compile())

    # ── 边 ────────────────────────────────────────────────────────────────
    graph.set_entry_point("router")

    # router 后路由
    graph.add_conditional_edges("router", route_after_router, {
        "proc_subgraph": "proc_subgraph",
        "recon_subgraph": "recon_subgraph",
        END: END,
    })

    graph.add_edge("proc_subgraph", END)
    graph.add_edge("recon_subgraph", END)

    return graph


def create_app():
    """创建带有 MemorySaver 的可运行图实例。"""
    memory = MemorySaver()
    graph = build_main_graph()
    return graph.compile(checkpointer=memory)
