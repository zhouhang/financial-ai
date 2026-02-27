"""审计数据处理子图节点函数

包含审计数据整理子图的各个节点函数：
- list_skills_node: 列出所有可用的技能
- generate_script_node: 生成或加载脚本
- execute_script_node: 执行脚本
- get_result_node: 获取执行结果
"""

from __future__ import annotations

from typing import Any, Dict

from app.models import AgentState
from langchain_core.messages import AIMessage


def list_skills_node(state: AgentState) -> Dict[str, Any]:
    """列出所有可用的审计数据整理技能

    输入：state 中的用户请求
    输出：available_skills, selected_skill_id
    """
    # 直接调用 audit-agent 模块
    from proc_agent.skill_handler import list_skills, get_skill_detail
    from proc_agent.intent_recognizer import identify_intent

    user_request = state.get("user_request", "")
    uploaded_files = state.get("uploaded_files", [])

    # 识别用户意图
    intent_type, score = identify_intent(user_request)

    # 获取所有可用技能
    skills = list_skills()

    # 根据意图选择技能
    selected_skill = next((s for s in skills if s["id"] == intent_type), None)

    return {
        "available_skills": skills,
        "selected_skill_id": intent_type,
        "intent_score": score,
        "user_request": user_request,
        "uploaded_files": uploaded_files
    }


def generate_script_node(state: AgentState) -> Dict[str, Any]:
    """生成或加载脚本

    输入：selected_skill_id
    输出：script_path, script_status
    """
    from proc_agent.skill_handler import get_skill_detail
    from proc_agent.intent_recognizer import get_script_file
    from pathlib import Path

    selected_skill_id = state.get("selected_skill_id")

    # 获取技能详情
    skill_detail = get_skill_detail(selected_skill_id)
    if not skill_detail:
        return {
            "script_status": "error",
            "error_message": f"未找到技能：{selected_skill_id}"
        }

    # 获取脚本路径
    script_file = get_script_file(selected_skill_id)
    if not script_file:
        return {
            "script_status": "error",
            "error_message": f"未找到脚本文件映射：{selected_skill_id}"
        }

    # 检查脚本是否存在
    from proc_agent import PROC_AGENT_DIR
    script_path = PROC_AGENT_DIR / script_file

    if not script_path.exists():
        return {
            "script_status": "error",
            "error_message": f"脚本文件不存在：{script_path}",
            "script_path": str(script_path)
        }

    return {
        "script_path": str(script_path),
        "script_status": "ready",
        "skill_detail": skill_detail
    }


def execute_script_node(state: AgentState) -> Dict[str, Any]:
    """执行脚本处理数据

    输入：script_path, uploaded_files, output_dir
    输出：execution_status, execution_result
    """
    from proc_agent.skill_handler import process_audit_data

    script_path = state.get("script_path")
    uploaded_files = state.get("uploaded_files", [])
    output_dir = state.get("output_dir")

    if not script_path:
        return {
            "execution_status": "error",
            "error_message": "脚本路径为空"
        }

    # 获取用户请求
    user_request = state.get("user_request", "处理审计数据")

    # 执行脚本
    result = process_audit_data(
        user_request=user_request,
        files=uploaded_files,
        output_dir=output_dir
    )

    return {
        "execution_status": result.get("status", "error"),
        "execution_result": result,
        "error_message": result.get("error", {}).get("message") if result.get("status") == "error" else None
    }


def get_result_node(state: AgentState) -> Dict[str, Any]:
    """获取并格式化执行结果

    输入：execution_result
    输出：formatted_result, messages
    """
    execution_status = state.get("execution_status")
    execution_result = state.get("execution_result")

    if execution_status == "error":
        error_message = state.get("error_message", "执行失败")
        return {
            "formatted_result": f"❌ 执行失败：{error_message}",
            "messages": [AIMessage(content=f"执行失败：{error_message}")]
        }

    # 格式化成功结果
    result_files = execution_result.get("data", {}).get("result_files", [])
    intent_type = execution_result.get("intent_type", "")

    result_text = f"✅ 数据处理成功！\n\n"
    result_text += f"业务类型：{intent_type}\n"
    result_text += f"生成文件：{len(result_files)} 个\n"

    for file_path in result_files:
        result_text += f"- {file_path}\n"

    return {
        "formatted_result": result_text,
        "messages": [AIMessage(content=result_text)],
        "result_files": result_files
    }
