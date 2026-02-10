"""数据整理子图 (Sub-Graph) — 占位，暂不开发，保留架构入口。"""

from __future__ import annotations

from langchain_core.messages import AIMessage
from langgraph.graph import END, StateGraph

from app.models import AgentState


def placeholder_node(state: AgentState) -> dict:
    return {
        "messages": [AIMessage(content="数据整理功能正在开发中，敬请期待。")],
    }


def build_data_preparation_subgraph() -> StateGraph:
    sg = StateGraph(AgentState)
    sg.add_node("placeholder", placeholder_node)
    sg.set_entry_point("placeholder")
    sg.add_edge("placeholder", END)
    return sg
