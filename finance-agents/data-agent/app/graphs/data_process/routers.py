"""审计数据处理子图路由函数

包含子图内部的条件路由函数。
"""

from __future__ import annotations

from app.models import AgentState


def route_after_list_skills(state: AgentState) -> str:
    """列出技能后路由"""
    selected_skill_id = state.get("selected_skill_id")

    if selected_skill_id:
        return "generate_script"
    return "end"


def route_after_generate_script(state: AgentState) -> str:
    """生成脚本后路由"""
    script_status = state.get("script_status")

    if script_status == "ready":
        return "execute_script"
    return "end"


def route_after_execute_script(state: AgentState) -> str:
    """执行脚本后路由"""
    execution_status = state.get("execution_status")

    if execution_status in ["success", "error"]:
        return "get_result"
    return "end"
