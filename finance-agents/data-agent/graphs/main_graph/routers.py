"""主图路由函数模块

包含主图的条件路由函数和图构建函数：
- route_after_router: router 之后的条件路由
- build_main_graph: 构建主 Agent 图
- create_app: 创建带有外部 checkpointer 的可运行图实例
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from models import (
    AgentState,
    UserIntent,
)
from graphs.proc import build_proc_subgraph
from graphs.recon.manual_notify import build_manual_notify_followup_graph
from graphs.recon.manual_scheme_run import build_manual_scheme_run_graph
from .nodes import (
    router_node,
)


# ══════════════════════════════════════════════════════════════════════════════
# 路由函数
# ══════════════════════════════════════════════════════════════════════════════

def route_after_router(state: AgentState) -> str:
    """router 之后的条件路由。"""
    intent = state.get("user_intent", "")
    recon_ctx = state.get("recon_ctx") or {}
    pending_manual_notify = bool(recon_ctx.get("pending_manual_notify")) and bool(state.get("auth_token"))

    if intent == UserIntent.PROC.value:
        return "proc_subgraph"
    if intent == UserIntent.RECON.value:
        return "manual_scheme_run_graph"
    if pending_manual_notify:
        return "manual_notify_followup_graph"
    return END


# ══════════════════════════════════════════════════════════════════════════════
# 构建主图
# ══════════════════════════════════════════════════════════════════════════════

def build_main_graph() -> StateGraph:
    """构建主 Agent 图。"""
    proc_sg = build_proc_subgraph()
    manual_recon_sg = build_manual_scheme_run_graph()
    manual_notify_sg = build_manual_notify_followup_graph()

    graph = StateGraph(AgentState)

    # ── 节点 ──────────────────────────────────────────────────────────────
    graph.add_node("router", router_node)

    graph.add_node("proc_subgraph", proc_sg.compile())
    graph.add_node("manual_scheme_run_graph", manual_recon_sg.compile())
    graph.add_node("manual_notify_followup_graph", manual_notify_sg.compile())

    # ── 边 ────────────────────────────────────────────────────────────────
    graph.set_entry_point("router")

    # router 后路由
    graph.add_conditional_edges("router", route_after_router, {
        "proc_subgraph": "proc_subgraph",
        "manual_scheme_run_graph": "manual_scheme_run_graph",
        "manual_notify_followup_graph": "manual_notify_followup_graph",
        END: END,
    })

    graph.add_edge("proc_subgraph", END)
    graph.add_edge("manual_scheme_run_graph", END)
    graph.add_edge("manual_notify_followup_graph", END)

    return graph


def create_app(checkpointer):
    """创建带有外部 checkpointer 的可运行图实例。"""
    graph = build_main_graph()
    return graph.compile(checkpointer=checkpointer)
