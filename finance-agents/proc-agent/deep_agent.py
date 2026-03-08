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
        skill_meta: Optional[Dict[str, Any]] = None,
        tool_result: Optional[ToolExecutionResult] = None,
        llm_response: str = "",
        error: str = "",
    ):
        self.success = success
        self.selected_skill_id = selected_skill_id
        self.selected_skill_name = selected_skill_name
        self.skill_meta = skill_meta or {}
        self.tool_result = tool_result
        self.llm_response = llm_response
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "success": self.success,
            "selected_skill_id": self.selected_skill_id,
            "selected_skill_name": self.selected_skill_name,
            "skill_meta": self.skill_meta,
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

## 核心指令

当用户提出请求时，你必须：
1. **立即分析**用户的请求和上传的文件，判断应该使用哪个 skill
2. **直接执行**匹配的 skill，调用对应的工具处理数据
3. **禁止**回复欢迎语、自我介绍、功能说明等无关内容
4. **禁止**询问用户"需要什么帮助"或"请告诉我具体需求"
5. 处理完成后，简洁报告结果和生成的文件

## 重要原则

- 用户提供的「上传文件绝对路径」是完全可信的，文件已存在于该路径
- 禁止自行搜索文件系统来查找文件，直接使用用户指定的绝对路径
- 如果用户请求与某个 skill 匹配，**必须立即执行**该 skill 的处理脚本
- 执行脚本时，将用户上传的文件绝对路径作为输入
- 处理完成后，简洁列出生成的结果文件
- **不要**说"我来帮您"、"请上传文件"之类的话，直接处理

## 行为示例

❌ 错误："您好！我是数据整理数字员工，专注于审计数据整理和核算报表填充..."
❌ 错误："请告诉我您的具体需求，比如..."
✅ 正确：[直接调用 skill 工具执行数据处理]
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


def _build_chat_model():
    """构建 BaseChatModel 实例，避免 deepagents 对 openai: 前缀自动启用 Responses API。

    千问百炼/DeepSeek 兼容 OpenAI chat completions 接口（/v1/chat/completions），
    但不支持 OpenAI Responses API（/v1/responses），必须用 ChatOpenAI 直接配置。
    """
    try:
        from langchain_openai import ChatOpenAI
        from app.config import (
            LLM_PROVIDER,
            OPENAI_MODEL, OPENAI_API_KEY, OPENAI_BASE_URL,
            DEEPSEEK_MODEL, DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL,
            QWEN_MODEL, QWEN_API_KEY, QWEN_BASE_URL,
        )

        if LLM_PROVIDER == "deepseek":
            return ChatOpenAI(
                model=DEEPSEEK_MODEL,
                api_key=DEEPSEEK_API_KEY,
                base_url=DEEPSEEK_BASE_URL,
                temperature=0.1,
            )
        elif LLM_PROVIDER == "qwen":
            return ChatOpenAI(
                model=QWEN_MODEL,
                api_key=QWEN_API_KEY,
                base_url=QWEN_BASE_URL,
                temperature=0.1,
            )
        else:
            return ChatOpenAI(
                model=OPENAI_MODEL,
                api_key=OPENAI_API_KEY,
                base_url=OPENAI_BASE_URL or "https://api.openai.com/v1",
                temperature=0.1,
            )
    except Exception as e:
        logger.warning(f"_build_chat_model 失败，回退到字符串模型名: {e}")
        return _get_model_name()


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
        from deepagents.backends.local_shell import LocalShellBackend

        # 配置环境变量（deepagents 需要）
        _setup_env_for_deepagents()

        # 构建 BaseChatModel（显式禁用 Responses API，兼容千问百炼/DeepSeek）
        model = _build_chat_model()

        # LocalShellBackend 支持文件操作 + shell 命令执行（用于执行 skill 脚本）
        # virtual_mode=True: 使用虚拟路径语义，确保 /skills/ 相对于 root_dir 正确解析
        # inherit_env=True: 继承当前进程的环境变量（包括 PATH）
        backend = LocalShellBackend(
            root_dir=str(PROC_AGENT_DIR),
            virtual_mode=True,
            inherit_env=True,
        )

        # skills 目录路径（相对于 backend 的 root_dir，以 / 开头）
        skills_paths = ["/skills/"]

        # 创建 Deep Agent
        # 注意：不使用 checkpointer，避免 skills_metadata 被缓存为空（导致后续会话无法重新加载 skills）
        agent = create_deep_agent(
            model=model,
            backend=backend,
            skills=skills_paths,
            system_prompt=_SYSTEM_PROMPT,
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

        # 确保 PATH 包含常用 Python 路径（供 LocalShellBackend 执行命令时使用）
        python_paths = [
            "/opt/anaconda3/bin",
            "/usr/local/bin",
            "/usr/bin",
        ]
        current_path = os.environ.get("PATH", "")
        new_paths = [p for p in python_paths if p not in current_path]
        if new_paths:
            os.environ["PATH"] = ":".join(new_paths) + ":" + current_path
            logger.info(f"_setup_env_for_deepagents: 更新 PATH={os.environ['PATH'][:100]}...")

    except Exception as e:
        logger.warning(f"设置 deepagents 环境变量失败: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 工具函数：从消息列表中解析 skill 命中信息
# ══════════════════════════════════════════════════════════════════════════════

# Skill 完整元数据注册表（id → metadata dict）
_SKILL_META: Dict[str, Dict[str, Any]] = {
    "recognition-report-filler": {
        "id": "recognition-report-filler",
        "name": "核算报表填充",
        "description": "将手工凭证 Excel 中的数据提取并自动填充到 BI 费用明细表和 BI 损益毛利明细表中，支持自动生成或追加同步两种模式。",
        "tags": ["手工凭证", "BI报表", "费用明细", "损益毛利"],
        "icon": "📊",
        "input_files": [
            {"name": "手工凭证", "required": True,  "hint": "文件名含'凭证'"},
            {"name": "BI费用明细表", "required": False, "hint": "可选，不传则自动生成"},
            {"name": "BI损益毛利明细表", "required": False, "hint": "可选，不传则自动生成"},
        ],
    },
    "audit-data-processor": {
        "id": "audit-data-processor",
        "name": "审计数据整理",
        "description": "对审计相关 Excel 数据进行清洗、分类与整理，支持货币资金、流水分析、应收账款、库存商品等多种审计业务场景。",
        "tags": ["审计", "货币资金", "流水分析", "应收账款"],
        "icon": "🔍",
        "input_files": [
            {"name": "业务数据文件", "required": True, "hint": "审计相关 Excel 文件"},
        ],
    },
}

# 向后兼容：保留旧的 display names 映射
_SKILL_DISPLAY_NAMES: Dict[str, str] = {
    k: v["name"] for k, v in _SKILL_META.items()
}


def _extract_skill_hit(messages: list) -> Dict[str, Any]:
    """从 Agent 消息列表中提取命中的 skill 完整元数据。

    返回: skill metadata dict（未命中则返回空 dict）
    """
    # 遍历消息，查找 tool_use / tool_call 类型消息，提取 skill 名称
    for msg in messages:
        # LangChain ToolMessage / tool_calls 内有 skill id
        tool_calls = getattr(msg, "tool_calls", None) or []
        for tc in tool_calls:
            name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
            if name and name in _SKILL_META:
                logger.info(f"_extract_skill_hit: skill 命中={name}")
                return _SKILL_META[name]

        # 备用：从 AI 消息内容中匹配 skill 名称关键词
        content = getattr(msg, "content", "") or ""
        for skill_id, meta in _SKILL_META.items():
            if skill_id in content or meta["name"] in content:
                return meta

    return {}



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
    if input_files:
        # 构建文件列表，包含文件名和绝对路径，让 Agent 知道文件确切在哪里
        file_lines = []
        for f in input_files:
            fname = Path(f).name
            file_lines.append(f"  - 文件名: {fname}")
            file_lines.append(f"    绝对路径: {f}")
        files_desc = "\n".join(file_lines)
    else:
        files_desc = "  （无文件）"

    user_msg = (
        f"请处理以下请求：{user_request}\n\n"
        f"上传文件（绝对路径已提供，请直接使用，无需搜索）：\n{files_desc}\n\n"
        f"输出目录：{output_dir}"
    )
    logger.info(f"run_deep_agent: 发送给 Agent 的消息=\n{user_msg}")

    # ── 运行 Agent ────────────────────────────────────────────────────────
    try:
        from langchain_core.messages import HumanMessage
        import asyncio
        from concurrent.futures import TimeoutError as FutureTimeoutError

        logger.info(f"run_deep_agent: 开始调用 agent.invoke(), thread_id={chat_id}")

        # 使用 asyncio.wait_for 添加超时控制（防止 deepagents 内部卡住）
        async def _invoke_agent():
            return await asyncio.to_thread(
                agent.invoke,
                {"messages": [HumanMessage(content=user_msg)]},
                config={"configurable": {"thread_id": chat_id}},
            )

        try:
            # 获取或创建事件循环
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            # 运行带超时的调用
            result_state = loop.run_until_complete(
                asyncio.wait_for(_invoke_agent(), timeout=120.0)
            )
            logger.info(f"run_deep_agent: agent.invoke() 完成")
        except asyncio.TimeoutError:
            logger.error("run_deep_agent: Agent 执行超时（120秒）")
            return DeepAgentResult(
                success=False,
                error="Agent 执行超时，请稍后重试或联系管理员",
            )
        except Exception as invoke_e:
            logger.error(f"run_deep_agent: agent.invoke() 异常: {invoke_e}")
            raise invoke_e

    except Exception as e:
        logger.error(f"run_deep_agent: Agent 执行失败: {e}", exc_info=True)
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

    # ✔ 解析 skill 命中信息
    skill_meta = _extract_skill_hit(messages)
    skill_id = skill_meta.get("id", "")
    skill_display = skill_meta.get("name", "")
    if skill_id:
        logger.info(f"run_deep_agent: skill 命中={skill_id} ({skill_display})")
    else:
        logger.info("run_deep_agent: 未提取到具体 skill 命中信息")
    # 扫描输出目录获取结果文件
    out_path = Path(output_dir)
    if out_path.exists():
        for ext in ["*.xlsx", "*.csv", "*.md", "*.json"]:
            result_files.extend(str(p) for p in out_path.glob(ext))

    # 判断是否成功（有结果文件或 LLM 回复正常）
    success = bool(result_files) or ("成功" in llm_response or "完成" in llm_response)

    tool_result = ToolExecutionResult(
        success=success,
        skill_id=skill_id or "deep_agent",
        output=llm_response[:500],
        result_files=result_files,
    )

    return DeepAgentResult(
        success=success,
        selected_skill_id=skill_id or "deep_agent",
        selected_skill_name=skill_display or "Deep Agent",
        skill_meta=skill_meta,
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
