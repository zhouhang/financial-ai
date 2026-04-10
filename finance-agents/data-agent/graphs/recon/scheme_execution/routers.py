"""Router and builder for shared scheme execution graph."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from models import AgentState
from .nodes import (
    build_recon_inputs_node,
    build_recon_observation_node,
    decide_prepare_node,
    execute_proc_node,
    execute_recon_node,
)


def route_after_decide_prepare(state: AgentState) -> str:
    ctx = state.get("recon_ctx") or {}
    if bool(ctx.get("should_prepare")):
        return "execute_proc_node"
    return "build_recon_inputs_node"


def build_scheme_execution_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("decide_prepare_node", decide_prepare_node)
    graph.add_node("execute_proc_node", execute_proc_node)
    graph.add_node("build_recon_inputs_node", build_recon_inputs_node)
    graph.add_node("execute_recon_node", execute_recon_node)
    graph.add_node("build_recon_observation_node", build_recon_observation_node)

    graph.set_entry_point("decide_prepare_node")
    graph.add_conditional_edges(
        "decide_prepare_node",
        route_after_decide_prepare,
        {
            "execute_proc_node": "execute_proc_node",
            "build_recon_inputs_node": "build_recon_inputs_node",
        },
    )
    graph.add_edge("execute_proc_node", "build_recon_inputs_node")
    graph.add_edge("build_recon_inputs_node", "execute_recon_node")
    graph.add_edge("execute_recon_node", "build_recon_observation_node")
    graph.add_edge("build_recon_observation_node", END)
    return graph

