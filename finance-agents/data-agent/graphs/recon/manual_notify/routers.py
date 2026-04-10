"""Router and builder for manual notify follow-up graph."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from models import AgentState
from .nodes import (
    parse_notify_targets_node,
    render_notify_result_node,
    send_manual_notify_node,
)


def build_manual_notify_followup_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("parse_notify_targets_node", parse_notify_targets_node)
    graph.add_node("send_manual_notify_node", send_manual_notify_node)
    graph.add_node("render_notify_result_node", render_notify_result_node)

    graph.set_entry_point("parse_notify_targets_node")
    graph.add_edge("parse_notify_targets_node", "send_manual_notify_node")
    graph.add_edge("send_manual_notify_node", "render_notify_result_node")
    graph.add_edge("render_notify_result_node", END)
    return graph

