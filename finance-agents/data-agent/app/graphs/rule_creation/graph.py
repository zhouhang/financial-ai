"""规则创建子图构建器

实现基于对话的规则创建 LangGraph 子图。
"""

from __future__ import annotations

from langgraph.graph import StateGraph, END
from app.models import AgentState
from .nodes import (
    rule_creation_intent_node,
    conversational_rule_creation_node,
    rule_creation_router,
)


def build_rule_creation_subgraph() -> StateGraph:
    """构建规则创建子图

    流程:
    1. intent: 识别用户是否有创建规则的意图
    2. conversational: 对话式信息收集
    3. 循环直到规则创建完成

    返回:
        编译好的 StateGraph 实例
    """
    builder = StateGraph(AgentState)

    # 添加节点
    builder.add_node("intent", rule_creation_intent_node)
    builder.add_node("conversational", conversational_rule_creation_node)

    # 设置入口点
    builder.set_entry_point("intent")

    # 添加边
    builder.add_edge("intent", "conversational")
    
    # 对话式创建后回到意图识别（多轮对话）
    builder.add_conditional_edges(
        "conversational",
        rule_creation_router,
        {
            "conversational_rule_creation": "conversational",
            "end": END
        }
    )

    return builder
