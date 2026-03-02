"""审计数据处理子图节点函数

包含审计数据整理子图的各个节点函数：
- list_skills_node: 列出所有可用的技能
- generate_script_node: 生成或加载脚本
- execute_script_node: 执行脚本
- get_result_node: 获取执行结果
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict

from app.models import AgentState
from langchain_core.messages import AIMessage

# ── 将 proc-agent 注册为 proc_agent 包 ───────────────────────────────────────
# proc-agent 目录名含连字符，无法直接 import，使用 importlib 手动注册
_PROC_AGENT_DIR = Path(__file__).resolve().parents[4] / "proc-agent"


def _ensure_proc_agent_importable() -> None:
    """将 finance-agents/proc-agent/ 注册为 proc_agent 包（仅首次执行）。"""
    if "proc_agent" in sys.modules:
        return
    init_path = _PROC_AGENT_DIR / "__init__.py"
    if not init_path.exists():
        raise ImportError(f"proc-agent __init__.py 不存在: {init_path}")
    spec = importlib.util.spec_from_file_location(
        "proc_agent",
        str(init_path),
        submodule_search_locations=[str(_PROC_AGENT_DIR)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"无法创建 proc_agent 模块规格: {init_path}")
    mod = importlib.util.module_from_spec(spec)
    mod.__path__ = [str(_PROC_AGENT_DIR)]   # type: ignore[attr-defined]
    mod.__package__ = "proc_agent"
    sys.modules["proc_agent"] = mod          # 先注册避免循环导入
    spec.loader.exec_module(mod)             # type: ignore[union-attr]


_ensure_proc_agent_importable()


import logging
logger_dp = logging.getLogger(__name__)


def list_skills_node(state: AgentState) -> Dict[str, Any]:
    """列出所有可用的审计数据整理技能

    输入：state 中的用户请求
    输出：available_skills, selected_skill_id
    """
    logger_dp.info("list_skills_node 被调用！state keys=" + str(list(state.keys())))
    print("[DEBUG dp_list_skills] list_skills_node called!", flush=True)
    # 直接调用 audit-agent 模块
    from proc_agent.skill_handler import list_skills, get_skill_detail
    from proc_agent.intent_recognizer import identify_intent

    # 优先从 user_request 字段获取，其次从最后一条用户消息中提取
    user_request = state.get("user_request", "")
    if not user_request:
        messages = list(state.get("messages", []))
        for msg in reversed(messages):
            if hasattr(msg, "type") and msg.type == "human" and hasattr(msg, "content"):
                user_request = msg.content
                break

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
    if not user_request:
        messages = list(state.get("messages", []))
        for msg in reversed(messages):
            if hasattr(msg, "type") and msg.type == "human" and hasattr(msg, "content"):
                user_request = msg.content
                break

    # 提取文件路径（uploaded_files 可能是 dict 列表或字符串列表）
    file_paths = []
    for f in uploaded_files:
        if isinstance(f, dict):
            path = f.get("file_path", "")
            if path:
                file_paths.append(path)
        elif isinstance(f, str) and f:
            file_paths.append(f)

    # 将 /uploads/... 虚拟路径转换为绝对文件系统路径
    # MCP 服务器返回的路径格式为 /uploads/年/月/日/文件名，需拼接 FINANCE_MCP_UPLOAD_DIR 前缀
    from app.config import FINANCE_MCP_UPLOAD_DIR
    resolved_paths = []
    for path in file_paths:
        if path.startswith("/uploads/"):
            # /uploads/2026/3/3/file.xlsx → {FINANCE_MCP_UPLOAD_DIR}/2026/3/3/file.xlsx
            rel = path[len("/uploads/"):]
            abs_path = str(Path(FINANCE_MCP_UPLOAD_DIR) / rel)
        else:
            abs_path = path
        resolved_paths.append(abs_path)
    file_paths = resolved_paths

    # 使用 thread_id 作为 chat_id 隔离输出目录
    chat_id = state.get("thread_id") or "default"

    # 执行脚本
    result = process_audit_data(
        user_request=user_request,
        files=file_paths,
        output_dir=output_dir,
        chat_id=chat_id,
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
        # 尝试从 execution_result 中获取更详细的错误信息
        if execution_result and isinstance(execution_result, dict):
            err = execution_result.get("error", {})
            if isinstance(err, dict):
                error_message = err.get("message", error_message)
        return {
            "formatted_result": f"❌ 执行失败：{error_message}",
            "messages": [AIMessage(content=f"执行失败：{error_message}")]
        }

    # 格式化成功结果
    result_data = execution_result.get("data", {}) if execution_result else {}
    result_files = result_data.get("result_files", [])
    download_urls = result_data.get("download_urls", [])
    intent_type = execution_result.get("intent_type", "") if execution_result else ""

    result_text = "✅ 数据处理成功！\n\n"
    result_text += f"业务类型：{intent_type}\n"
    result_text += f"生成文件：{len(result_files)} 个\n"

    if download_urls:
        result_text += "\n**可下载链接：**\n"
        for url in download_urls:
            filename = url.split("/")[-1]
            result_text += f"- [{filename}]({url})\n"
    elif result_files:
        result_text += "\n**生成文件路径：**\n"
        for file_path in result_files:
            result_text += f"- {file_path}\n"

    return {
        "formatted_result": result_text,
        "messages": [AIMessage(content=result_text)],
        "result_files": result_files
    }
