"""审计数据处理子图构建器

构建 LangGraph 状态图，用于处理审计数据整理业务。
"""

from __future__ import annotations

from langgraph.graph import StateGraph, END
from app.models import AgentState
from .nodes import (
    list_skills_node,
    generate_script_node,
    execute_script_node,
    get_result_node,
)
from .routers import (
    route_after_list_skills,
    route_after_generate_script,
    route_after_execute_script,
)


def build_data_process_subgraph() -> StateGraph:
    """构建数据处理子图

    流程:
    1. list_skills: 列出可用技能，识别用户意图
    2. generate_script: 生成或加载脚本
    3. execute_script: 执行脚本处理数据
    4. get_result: 获取并展示结果

    返回:
        编译好的 StateGraph 实例
    """
    builder = StateGraph(AgentState)

    # 添加节点
    builder.add_node("list_skills", list_skills_node)
    builder.add_node("generate_script", generate_script_node)
    builder.add_node("execute_script", execute_script_node)
    builder.add_node("get_result", get_result_node)

    # 设置入口点
    builder.set_entry_point("list_skills")

    # 添加边
    builder.add_conditional_edges(
        "list_skills",
        route_after_list_skills,
        {
            "generate_script": "generate_script",
            "end": END,
        }
    )

    builder.add_conditional_edges(
        "generate_script",
        route_after_generate_script,
        {
            "execute_script": "execute_script",
            "end": END,
        }
    )

    builder.add_conditional_edges(
        "execute_script",
        route_after_execute_script,
        {
            "get_result": "get_result",
            "end": END,
        }
    )

    builder.add_edge("get_result", END)

    return builder
