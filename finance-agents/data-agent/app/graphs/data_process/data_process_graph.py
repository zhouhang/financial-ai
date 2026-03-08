"""审计数据处理子图构建器（Deep Agent 架构）

构建 LangGraph 状态图，用于处理审计数据整理业务。

新架构流程（Claude Code 风格）：
  1. skill_retrieve: SKILL.md → embedding → skill retriever，检索最相关的 skills
  2. deep_agent: Deep Agent (tools subset)，LLM 推理选择 skill 并执行
  3. get_result: 格式化并展示执行结果
"""

from __future__ import annotations

from langgraph.graph import StateGraph, END
from app.models import AgentState
from .nodes import (
    skill_retrieve_node,
    deep_agent_node,
    get_result_node,
)
from .routers import (
    route_after_skill_retrieve,
    route_after_deep_agent,
)


def build_data_process_subgraph() -> StateGraph:
    """构建数据处理子图（Deep Agent 架构）

    流程：
    1. skill_retrieve: SKILL.md → embedding → skill retriever → tools subset
    2. deep_agent: Deep Agent (tools subset) → LLM 推理 → execute tool
    3. get_result: 格式化并展示结果

    返回：
        未编译的 StateGraph 实例
    """
    builder = StateGraph(AgentState)

    # 添加节点
    builder.add_node("skill_retrieve", skill_retrieve_node)
    builder.add_node("deep_agent", deep_agent_node)
    builder.add_node("get_result", get_result_node)

    # 设置入口点
    builder.set_entry_point("skill_retrieve")

    # 添加边
    builder.add_conditional_edges(
        "skill_retrieve",
        route_after_skill_retrieve,
        {
            "dp_deep_agent": "deep_agent",
            END: END,
        }
    )

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
