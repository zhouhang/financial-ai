"""审计数据处理子图路由函数

包含子图内部的条件路由函数。
⚠️ 所有路由函数直接返回主图中的实际节点名（dp_generate_script 等），
   避免 LangGraph 1.0.x 非对等路径映射 bug。
"""

from __future__ import annotations

from langgraph.graph import END

from app.models import AgentState


def route_after_list_skills(state: AgentState) -> str:
    """列出技能后路由：直接返回主图节点名"""
    selected_skill_id = state.get("selected_skill_id")

    if selected_skill_id:
        return "dp_generate_script"  # 直接返回主图节点名
    return END


def route_after_generate_script(state: AgentState) -> str:
    """生成脚本后路由：直接返回主图节点名"""
    script_status = state.get("script_status")

    if script_status == "ready":
        return "dp_execute_script"  # 直接返回主图节点名
    return END


def route_after_execute_script(state: AgentState) -> str:
    """执行脚本后路由：直接返回主图节点名"""
    execution_status = state.get("execution_status")

    if execution_status in ["success", "error"]:
        return "dp_get_result"  # 直接返回主图节点名
    return END
