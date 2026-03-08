"""审计数据处理子图节点函数（Deep Agent 架构）

基于 deepagents 包的 create_deep_agent 实现，核心流程：

    create_deep_agent(skills=["/skills/"])
        ↓
    Agent 启动时读取 SKILL.md frontmatter (name, description)
        ↓
    用户请求 → Agent 自动匹配 skill → progressive disclosure 加载完整 skill
        ↓
    LLM 推理 → 执行工具 → 返回结果

节点说明（简化架构）：
  1. deep_agent_node: 提取请求 + 调用 create_deep_agent，自动处理 skill 匹配与执行
  2. get_result_node: 格式化执行结果并写入 messages
"""

from __future__ import annotations

import importlib.util
import logging
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

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# 节点 1: deep_agent_node（入口节点）
# 提取请求 + 调用 create_deep_agent，自动处理 skill 匹配与执行
# ══════════════════════════════════════════════════════════════════════════════

def deep_agent_node(state: AgentState) -> Dict[str, Any]:
    """Deep Agent 节点（入口节点）

    使用 create_deep_agent 驱动 LLM 推理，自动：
    - 读取 skills/ 目录下的 SKILL.md frontmatter
    - 根据用户请求匹配相关 skill（progressive disclosure）
    - 执行对应的处理工具

    输入：messages、uploaded_files
    输出：execution_status、execution_result、error_message、user_request
    """
    logger.info("deep_agent_node: 启动 Deep Agent")

    from proc_agent.deep_agent import run_deep_agent, PROC_AGENT_DIR

    # ── 提取用户请求（原 skill_retrieve_node 逻辑）──────────────────────────
    user_request = state.get("user_request", "")
    if not user_request:
        messages = list(state.get("messages", []))
        for msg in reversed(messages):
            if hasattr(msg, "type") and msg.type == "human" and hasattr(msg, "content"):
                user_request = msg.content
                break
    if not user_request:
        user_request = "处理数据"

    uploaded_files = state.get("uploaded_files", [])
    output_dir = state.get("output_dir")
    thread_id = state.get("thread_id") or "default"

    logger.info(
        f"deep_agent_node: 请求={repr(user_request[:50]) if user_request else '无'}, "
        f"文件数={len(uploaded_files)}")

    # ── 解析文件路径 ──────────────────────────────────────────────────────
    file_paths = []
    for f in uploaded_files:
        if isinstance(f, dict):
            path = f.get("file_path", "")
            if path:
                file_paths.append(path)
        elif isinstance(f, str) and f:
            file_paths.append(f)

    # 将 /uploads/... 虚拟路径转换为绝对文件系统路径
    from app.config import FINANCE_MCP_UPLOAD_DIR
    resolved_paths = []
    for path in file_paths:
        if path.startswith("/uploads/"):
            rel = path[len("/uploads/"):]
            abs_path = str(Path(FINANCE_MCP_UPLOAD_DIR) / rel)
        else:
            abs_path = path
        resolved_paths.append(abs_path)
    file_paths = resolved_paths

    # ── 设置输出目录 ──────────────────────────────────────────────────────
    if not output_dir:
        # 默认使用 proc-agent/result/{thread_id}
        output_dir = str(PROC_AGENT_DIR / "result" / thread_id)

    # ── 运行 Deep Agent ───────────────────────────────────────────────────
    # create_deep_agent 已自动处理：
    # - 从 /skills/ 加载所有 SKILL.md 的 frontmatter
    # - 根据 user_request 自动匹配相关 skill
    # - progressive disclosure 加载完整 skill 内容
    # - LLM 推理并执行工具
    result = run_deep_agent(
        user_request=user_request,
        input_files=file_paths,
        output_dir=output_dir,
        chat_id=thread_id,
    )

    # run_deep_agent 返回 DeepAgentResult，需要转为 dict
    if hasattr(result, 'to_dict'):
        result = result.to_dict()

    execution_status = "success" if result.get("success") else "error"

    return {
        "execution_status": execution_status,
        "execution_result": result,
        "error_message": result.get("error") if execution_status == "error" else None,
        "selected_skill_id": result.get("selected_skill_id", ""),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 节点 2: get_result_node
# 格式化结果并写入 messages
# ══════════════════════════════════════════════════════════════════════════════

def get_result_node(state: AgentState) -> Dict[str, Any]:
    """结果展示节点

    获取 Deep Agent 执行结果并格式化为用户友好的消息。

    输入：execution_status、execution_result
    输出：formatted_result、messages、result_files
    """
    execution_status = state.get("execution_status")
    execution_result = state.get("execution_result") or {}
    selected_skill_id = state.get("selected_skill_id", "")

    if execution_status == "error":
        error_msg = (
            state.get("error_message")
            or execution_result.get("error", "执行失败")
        )
        formatted = f"❌ 数据处理失败：{error_msg}"
        return {
            "formatted_result": formatted,
            "messages": [AIMessage(content=formatted)],
        }

    # ── 解析成功结果 ──────────────────────────────────────────────────────
    skill_name = execution_result.get("selected_skill_name", selected_skill_id)
    tool_result = execution_result.get("tool_result") or {}
    result_files: list = tool_result.get("result_files", [])
    result_data: dict = tool_result.get("result_data") or {}
    download_urls: list = result_data.get("download_urls", [])

    result_text = "✅ 数据处理成功！\n\n"
    if skill_name:
        result_text += f"执行技能：{skill_name}\n"
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

    # 附加 LLM 推理说明（如果有）
    llm_response = execution_result.get("llm_response", "")
    if llm_response and len(llm_response) > 10:
        result_text += f"\n**处理说明：**\n{llm_response[:300]}\n"

    return {
        "formatted_result": result_text,
        "messages": [AIMessage(content=result_text)],
        "result_files": result_files,
    }
