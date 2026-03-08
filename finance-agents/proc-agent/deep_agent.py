"""Deep Agent 模块（基于 deepagents 包的 create_deep_agent）

使用 deepagents.create_deep_agent + skills 参数实现 Deep Agent：
  SKILL.md
      ↓
  create_deep_agent(skills=["skills/"])
      ↓
  Agent 自动读取 SKILL.md frontmatter 做 progressive disclosure
      ↓
  LLM 推理 → 选择 skill → 执行工具

架构：
  - skills 参数传入 skills 目录
  - FilesystemBackend 指定根目录为 proc-agent
  - Agent 启动时读取 SKILL.md 的 frontmatter（name, description）
  - 用户请求时，Agent 判断是否需要使用某个 skill，按需加载完整 SKILL.md
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── proc-agent 根目录 ──────────────────────────────────────────────────────────
PROC_AGENT_DIR = Path(__file__).parent


# ══════════════════════════════════════════════════════════════════════════════
# 执行结果类型（保持接口兼容）
# ══════════════════════════════════════════════════════════════════════════════

class ToolExecutionResult:
    """脚本执行结果。"""

    def __init__(
        self,
        success: bool,
        skill_id: str,
        output: str = "",
        result_data: Optional[Dict[str, Any]] = None,
        result_files: Optional[List[str]] = None,
        error: str = "",
    ):
        self.success = success
        self.skill_id = skill_id
        self.output = output
        self.result_data = result_data or {}
        self.result_files = result_files or []
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "skill_id": self.skill_id,
            "output": self.output[:2000],
            "result_data": self.result_data,
            "result_files": self.result_files,
            "error": self.error,
        }


class DeepAgentResult:
    """Deep Agent 执行结果。"""

    def __init__(
        self,
        success: bool,
        selected_skill_id: str = "",
        selected_skill_name: str = "",
        tool_result: Optional[ToolExecutionResult] = None,
        llm_response: str = "",
        error: str = "",
    ):
        self.success = success
        self.selected_skill_id = selected_skill_id
        self.selected_skill_name = selected_skill_name
        self.tool_result = tool_result
        self.llm_response = llm_response
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "success": self.success,
            "selected_skill_id": self.selected_skill_id,
            "selected_skill_name": self.selected_skill_name,
            "llm_response": self.llm_response,
            "error": self.error,
        }
        if self.tool_result:
            d["tool_result"] = self.tool_result.to_dict()
            d["result_files"] = self.tool_result.result_files
            d["result_data"] = self.tool_result.result_data
        return d


# ══════════════════════════════════════════════════════════════════════════════
# Deep Agent 系统提示词
# ══════════════════════════════════════════════════════════════════════════════

_SYSTEM_PROMPT = """\
你是一个专业的财务数据整理数字员工。

你已被配置了若干 skills（技能），每个 skill 对应一种财务数据处理业务。
当用户提出请求时，你需要：
1. 分析用户的请求和上传的文件，理解需要处理什么业务
2. 如果某个 skill 与请求匹配，阅读该 skill 的详细指南
3. 按照 skill 指南中的步骤执行数据处理
4. 完成后，向用户报告处理结果，列出生成的文件和下载链接

重要原则：
- 如果用户请求与某个 skill 匹配，必须使用该 skill 的处理脚本
- 执行脚本时，将用户上传的文件作为输入
- 处理完成后，简洁列出生成的结果文件
"""


# ══════════════════════════════════════════════════════════════════════════════
# 缓存的 Agent 实例（避免每次请求都重建）
# ══════════════════════════════════════════════════════════════════════════════

_cached_agent = None
_cached_model_name = None


def _get_model_name() -> str:
    """获取配置的 LLM model 名称。"""
    try:
        from app.config import (
            LLM_PROVIDER,
            OPENAI_MODEL, DEEPSEEK_MODEL, QWEN_MODEL,
        )
        if LLM_PROVIDER == "deepseek":
            return f"deepseek:{DEEPSEEK_MODEL}"
        elif LLM_PROVIDER == "qwen":
            return f"openai:{QWEN_MODEL}"  # Qwen 使用 OpenAI 兼容格式
        else:
            return f"openai:{OPENAI_MODEL}"
    except Exception:
        return "openai:gpt-4o"


def _create_deep_agent_instance():
    """创建 Deep Agent 实例（使用 deepagents 包）。
    
    使用 FilesystemBackend + skills 目录参数实现 skill 加载：
    - backend: FilesystemBackend(root_dir=proc-agent目录)
    - skills: ["/skills/"] 相对于 backend root 的路径
    
    Agent 启动时读取每个 SKILL.md 的 frontmatter (name, description)，
    按需进行 progressive disclosure 加载完整 skill 内容。
    """
    global _cached_agent, _cached_model_name

    model_name = _get_model_name()
    if _cached_agent is not None and _cached_model_name == model_name:
        return _cached_agent

    try:
        from deepagents import create_deep_agent
        from deepagents.backends.filesystem import FilesystemBackend
        from langgraph.checkpoint.memory import MemorySaver

        # 配置环境变量（deepagents 需要）
        _setup_env_for_deepagents()

        # FilesystemBackend 指定 proc-agent 为根目录
        backend = FilesystemBackend(root_dir=str(PROC_AGENT_DIR))

        # skills 目录路径（相对于 backend 的 root_dir，以 / 开头）
        # 参考: https://docs.langchain.com/oss/python/deepagents/skills
        skills_paths = ["/skills/"]

        # 创建 Deep Agent
        # create_deep_agent 会自动扫描 skills 目录，读取每个子目录的 SKILL.md
        agent = create_deep_agent(
            model=model_name,
            backend=backend,
            skills=skills_paths,
            system_prompt=_SYSTEM_PROMPT,
            checkpointer=MemorySaver(),
        )

        _cached_agent = agent
        _cached_model_name = model_name
        logger.info(f"Deep Agent 创建成功，model={model_name}, skills={skills_paths}, root={PROC_AGENT_DIR}")
        return agent

    except Exception as e:
        logger.error(f"创建 Deep Agent 失败: {e}")
        raise


def _setup_env_for_deepagents():
    """为 deepagents 设置必要的环境变量。"""
    try:
        from app.config import (
            LLM_PROVIDER,
            OPENAI_API_KEY, OPENAI_BASE_URL,
            DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL,
            QWEN_API_KEY, QWEN_BASE_URL,
        )

        if LLM_PROVIDER == "deepseek" and DEEPSEEK_API_KEY:
            os.environ.setdefault("OPENAI_API_KEY", DEEPSEEK_API_KEY)
            os.environ.setdefault("OPENAI_BASE_URL", DEEPSEEK_BASE_URL)
        elif LLM_PROVIDER == "qwen" and QWEN_API_KEY:
            os.environ.setdefault("OPENAI_API_KEY", QWEN_API_KEY)
            os.environ.setdefault("OPENAI_BASE_URL", QWEN_BASE_URL)
        elif OPENAI_API_KEY:
            os.environ.setdefault("OPENAI_API_KEY", OPENAI_API_KEY)
            if OPENAI_BASE_URL:
                os.environ.setdefault("OPENAI_BASE_URL", OPENAI_BASE_URL)

    except Exception as e:
        logger.warning(f"设置 deepagents 环境变量失败: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# run_deep_agent: 核心执行函数
# ══════════════════════════════════════════════════════════════════════════════

def run_deep_agent(
    user_request: str,
    input_files: List[str],
    output_dir: str,
    skill_schemas: List[Dict[str, Any]] = None,  # 保留参数兼容性，但不再使用
    chat_id: str = "default",
    llm_client: Any = None,  # 保留参数兼容性，但不再使用
) -> DeepAgentResult:
    """使用 create_deep_agent 运行 Deep Agent。

    参数:
        user_request: 用户自然语言请求
        input_files: 输入文件绝对路径列表
        output_dir: 输出目录
        skill_schemas: 已弃用（由 create_deep_agent 自动从 skills/ 加载）
        chat_id: 会话 ID
        llm_client: 已弃用

    返回:
        DeepAgentResult
    """
    os.makedirs(output_dir, exist_ok=True)

    try:
        agent = _create_deep_agent_instance()
    except Exception as e:
        logger.warning(f"run_deep_agent: 创建 Agent 失败 ({e})，降级为启发式执行")
        return _heuristic_fallback(user_request, input_files, output_dir, chat_id)

    # ── 构造用户消息 ──────────────────────────────────────────────────────
    file_names = ", ".join(Path(f).name for f in input_files) if input_files else "无"
    user_msg = (
        f"请处理以下请求：{user_request}\n\n"
        f"上传文件：{file_names}\n\n"
        f"输出目录：{output_dir}"
    )

    # ── 运行 Agent ────────────────────────────────────────────────────────
    try:
        from langchain_core.messages import HumanMessage

        result_state = agent.invoke(
            {"messages": [HumanMessage(content=user_msg)]},
            config={"configurable": {"thread_id": chat_id}},
        )
    except Exception as e:
        logger.error(f"run_deep_agent: Agent 执行失败: {e}")
        return DeepAgentResult(success=False, error=str(e))

    # ── 解析结果 ──────────────────────────────────────────────────────────
    messages = result_state.get("messages", [])
    llm_response = ""
    result_files: List[str] = []

    # 提取最后一条 AI 消息
    for msg in reversed(messages):
        msg_type = getattr(msg, "type", "")
        if msg_type == "ai" and not llm_response:
            llm_response = getattr(msg, "content", "") or ""
            break

    # 扫描输出目录获取结果文件
    out_path = Path(output_dir)
    if out_path.exists():
        for ext in ["*.xlsx", "*.csv", "*.md", "*.json"]:
            result_files.extend(str(p) for p in out_path.glob(ext))

    # 判断是否成功（有结果文件或 LLM 回复正常）
    success = bool(result_files) or ("成功" in llm_response or "完成" in llm_response)

    tool_result = ToolExecutionResult(
        success=success,
        skill_id="deep_agent",
        output=llm_response[:500],
        result_files=result_files,
    )

    return DeepAgentResult(
        success=success,
        selected_skill_id="deep_agent",
        selected_skill_name="Deep Agent",
        tool_result=tool_result,
        llm_response=llm_response,
        error="" if success else "处理未产生结果文件",
    )


# ══════════════════════════════════════════════════════════════════════════════
# 降级：无法创建 Agent 时的启发式执行
# ══════════════════════════════════════════════════════════════════════════════

def _heuristic_fallback(
    user_request: str,
    input_files: List[str],
    output_dir: str,
    chat_id: str,
) -> DeepAgentResult:
    """降级：使用旧的 skill_handler 直接执行。"""
    try:
        from .skill_handler import process_audit_data

        result = process_audit_data(
            user_request=user_request,
            files=input_files,
            output_dir=output_dir,
            chat_id=chat_id,
        )

        success = result.get("status") == "success"
        result_files = result.get("data", {}).get("result_files", [])
        error = result.get("error", {}).get("message", "") if not success else ""

        tool_result = ToolExecutionResult(
            success=success,
            skill_id=result.get("skill_id", ""),
            output="",
            result_data=result.get("data", {}),
            result_files=result_files,
            error=error,
        )

        return DeepAgentResult(
            success=success,
            selected_skill_id=result.get("skill_id", ""),
            selected_skill_name=result.get("intent_type", ""),
            tool_result=tool_result,
            llm_response="[降级模式：使用传统 skill_handler 执行]",
            error=error,
        )

    except Exception as e:
        logger.error(f"_heuristic_fallback: 执行失败: {e}")
        return DeepAgentResult(
            success=False,
            error=f"降级执行失败: {e}",
        )


# ══════════════════════════════════════════════════════════════════════════════
# 便捷入口函数（保持接口兼容）
# ══════════════════════════════════════════════════════════════════════════════

def process_with_deep_agent(
    user_request: str,
    input_files: List[str],
    output_dir: str,
    chat_id: str = "default",
    top_k_skills: int = 3,  # 已弃用
    llm_client: Any = None,  # 已弃用
) -> Dict[str, Any]:
    """完整的 Deep Agent 流程。

    参数:
        user_request: 用户自然语言请求
        input_files: 输入文件绝对路径列表
        output_dir: 输出目录
        chat_id: 会话 ID
        top_k_skills: 已弃用（由 create_deep_agent 自动处理）
        llm_client: 已弃用

    返回:
        处理结果字典
    """
    result = run_deep_agent(
        user_request=user_request,
        input_files=input_files,
        output_dir=output_dir,
        chat_id=chat_id,
    )

    return result.to_dict()
