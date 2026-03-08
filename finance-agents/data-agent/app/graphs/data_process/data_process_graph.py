"""审计数据处理子图构建器（Deep Agent 架构）

构建 LangGraph 状态图，用于处理审计数据整理业务。

简化架构流程（由 create_deep_agent 自动处理 skill 检索）：
  1. deep_agent: 提取请求 + Deep Agent (skills auto-discovery) → LLM 推理 + 执行
  2. get_result: 格式化并展示执行结果
"""

from __future__ import annotations

from langgraph.graph import StateGraph, END
from app.models import AgentState
from .nodes import (
    deep_agent_node,
    get_result_node,
)
from .routers import (
    route_after_deep_agent,
)


def build_data_process_subgraph() -> StateGraph:
    """构建数据处理子图（Deep Agent 架构，简化版）

    流程（skill 检索由 create_deep_agent 自动处理）：
    1. deep_agent: 提取请求 + create_deep_agent(skills=["/skills/"]) → 自动匹配 skill → 执行
    2. get_result: 格式化并展示结果

    返回：
        未编译的 StateGraph 实例
    """
    builder = StateGraph(AgentState)

    # 添加节点（简化为 2 个节点）
    builder.add_node("deep_agent", deep_agent_node)
    builder.add_node("get_result", get_result_node)

    # 设置入口点：直接进入 deep_agent
    builder.set_entry_point("deep_agent")

    # 添加边
    builder.add_conditional_edges(
        "deep_agent",
        route_after_deep_agent,
        {
            "dp_get_result": "get_result",
            END: END,
        }
    )

    builder.add_edge("get_result", END)

    return builder
