"""Router and builder for manual scheme run graph."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from models import AgentState, ReconAgentPhase
from graphs.recon.scheme_execution import build_scheme_execution_graph
from .nodes import (
    build_manual_run_context_node,
    check_manual_files_node,
    load_scheme_node,
    maybe_offer_notify_node,
    render_manual_result_node,
    resolve_manual_inputs_node,
)


def route_after_load_scheme(state: AgentState) -> str:
    ctx = state.get("recon_ctx") or {}
    if str(ctx.get("phase") or "") == ReconAgentPhase.RULE_NOT_FOUND.value:
        return END
    return "resolve_manual_inputs_node"


def route_after_check_manual_files(state: AgentState) -> str:
    ctx = state.get("recon_ctx") or {}
    if str(ctx.get("phase") or "") == ReconAgentPhase.FILE_CHECK_FAILED.value:
        return END
    return "build_manual_run_context_node"


def build_manual_scheme_run_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    scheme_execution = build_scheme_execution_graph().compile()

    graph.add_node("load_scheme_node", load_scheme_node)
    graph.add_node("resolve_manual_inputs_node", resolve_manual_inputs_node)
    graph.add_node("check_manual_files_node", check_manual_files_node)
    graph.add_node("build_manual_run_context_node", build_manual_run_context_node)
    graph.add_node("scheme_execution_graph", scheme_execution)
    graph.add_node("render_manual_result_node", render_manual_result_node)
    graph.add_node("maybe_offer_notify_node", maybe_offer_notify_node)

    graph.set_entry_point("load_scheme_node")
    graph.add_conditional_edges(
        "load_scheme_node",
        route_after_load_scheme,
        {
            "resolve_manual_inputs_node": "resolve_manual_inputs_node",
            END: END,
        },
    )
    graph.add_edge("resolve_manual_inputs_node", "check_manual_files_node")
    graph.add_conditional_edges(
        "check_manual_files_node",
        route_after_check_manual_files,
        {
            "build_manual_run_context_node": "build_manual_run_context_node",
            END: END,
        },
    )
    graph.add_edge("build_manual_run_context_node", "scheme_execution_graph")
    graph.add_edge("scheme_execution_graph", "render_manual_result_node")
    graph.add_edge("render_manual_result_node", "maybe_offer_notify_node")
    graph.add_edge("maybe_offer_notify_node", END)
    return graph

