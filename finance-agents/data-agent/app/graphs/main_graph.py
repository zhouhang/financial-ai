"""主 Agent 图 — 整合三层架构

第1层：对话理解（AI自主决策 — router 节点）
第2层：规则生成（对账子图）
第3层：任务执行（调用 finance-mcp 完成对账）
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt, Command

from app.utils.llm import get_llm
from app.models import (
    AgentState,
    ReconciliationPhase,
    TaskExecutionStep,
    UserIntent,
)
from app.graphs.reconciliation import (
    file_analysis_node,
    field_mapping_node,
    rule_config_node,
    validation_preview_node,
    save_rule_node,
    route_after_file_analysis,
    route_after_field_mapping,
    route_after_rule_config,
    route_after_preview,
)
from app.graphs.data_preparation import build_data_preparation_subgraph
from app.tools.mcp_client import (
    list_available_rules,
    get_rule_detail,
    auth_login,
    auth_register,
    start_reconciliation,
    get_reconciliation_status,
    get_reconciliation_result,
)

logger = logging.getLogger(__name__)


# ── 全局进度回调管理 ──────────────────────────────────────────────────────────

_progress_callbacks: dict[str, callable] = {}

def register_progress_callback(thread_id: str, callback: callable):
    """注册进度回调函数（由 WebSocket 处理器调用）"""
    _progress_callbacks[thread_id] = callback

def unregister_progress_callback(thread_id: str):
    """注销进度回调函数"""
    _progress_callbacks.pop(thread_id, None)

def _get_progress_callback(thread_id: str):
    """获取进度回调函数"""
    return _progress_callbacks.get(thread_id)


# ── HTML 表单生成 ────────────────────────────────────────────────────────────

def generate_login_form(error: str = "") -> str:
    """生成登录表单 HTML"""
    error_html = f'<div class="auth-error">❌ {error}</div>' if error else ""
    return f"""
<div class="auth-form-container">
  <h3>用户登录</h3>
  {error_html}
  <form id="login-form" class="auth-form">
    <div class="form-group">
      <label for="username">用户名</label>
      <input type="text" id="username" name="username" required placeholder="请输入用户名" />
    </div>
    <div class="form-group">
      <label for="password">密码</label>
      <input type="password" id="password" name="password" required placeholder="请输入密码" />
    </div>
    <button type="submit" class="btn-primary">登录</button>
  </form>
  <p class="auth-hint">没有账号？请输入"我要注册"</p>
</div>
"""

def generate_register_form(error: str = "") -> str:
    """生成注册表单 HTML"""
    error_html = f'<div class="auth-error">❌ {error}</div>' if error else ""
    return f"""
<div class="auth-form-container">
  <h3>用户注册</h3>
  {error_html}
  <form id="register-form" class="auth-form">
    <div class="form-group">
      <label for="username">用户名 *</label>
      <input type="text" id="username" name="username" required placeholder="请输入用户名" />
    </div>
    <div class="form-group">
      <label for="password">密码 *</label>
      <input type="password" id="password" name="password" required placeholder="至少6位字符" />
    </div>
    <div class="form-group">
      <label for="email">邮箱</label>
      <input type="email" id="email" name="email" placeholder="选填" />
    </div>
    <div class="form-group">
      <label for="phone">手机号</label>
      <input type="tel" id="phone" name="phone" placeholder="选填" />
    </div>
    <div class="form-group">
      <label for="company_code">公司编码</label>
      <input type="text" id="company_code" name="company_code" placeholder="加入已有公司（选填）" />
    </div>
    <div class="form-group">
      <label for="department_code">部门编码</label>
      <input type="text" id="department_code" name="department_code" placeholder="选填" />
    </div>
    <button type="submit" class="btn-primary">注册</button>
  </form>
  <p class="auth-hint">已有账号？请输入"我要登录"</p>
</div>
"""


# ── 系统提示词 ────────────────────────────────────────────────────────────────

SYSTEM_PROMPT_NOT_LOGGED_IN = """\
你是一个专业的财务对账助手。你的职责是帮助用户完成财务数据对账工作。

⚠️ 当前用户尚未登录。请引导用户先登录或注册。

请根据用户的意图判断：
- 如果用户想登录，回复 JSON: {{"intent": "show_login_form"}}
- 如果用户想注册，回复 JSON: {{"intent": "show_register_form"}}
- 如果用户只是打招呼或询问功能，用**一条完整的消息**回复，包含：
  1. 简短的问候和自我介绍（1-2句话，不要使用感叹号开头）
  2. 说明需要登录才能使用
  3. 引导用户"请输入'我要登录'或'我要注册'"

重要：
- 所有内容必须在同一条消息中完成，不要分多次回复
- 不要使用感叹号（！或!）开头
- 只在用户明确表达要登录或注册时才返回 JSON，否则正常对话
"""

SYSTEM_PROMPT = """\
你是一个专业的财务对账助手。你的职责是帮助用户完成财务数据对账工作。
当前登录用户：{username}

你可以做以下事情：
1. 使用已有的对账规则快速执行对账
2. 引导用户创建新的对账规则
3. 帮助用户理解对账结果

当前已有的对账规则包括：
{available_rules}

请根据用户的意图判断下一步操作：
- 如果用户想使用已有规则对账，回复 JSON: {{"intent": "use_existing_rule", "rule_name": "规则名称"}}
- 如果用户想创建新规则，回复 JSON: {{"intent": "create_new_rule"}}
- 如果用户在闲聊或询问信息，正常用中文回复即可

注意：只在明确判断意图时才返回 JSON，否则正常对话。
"""


# ══════════════════════════════════════════════════════════════════════════════
# 第1层：对话理解 — router
# ══════════════════════════════════════════════════════════════════════════════

async def router_node(state: AgentState) -> dict:
    """AI 自主决策节点：分析用户意图，决定走快速路径还是引导式生成。"""
    import json as _json

    # ⚠️ 关键：如果当前在子图执行中，不要重新识别意图，直接透传
    current_phase = state.get("phase", "")
    subgraph_phases = [
        ReconciliationPhase.FILE_ANALYSIS.value,
        ReconciliationPhase.FIELD_MAPPING.value,
        ReconciliationPhase.RULE_CONFIG.value,
        ReconciliationPhase.VALIDATION_PREVIEW.value,
        ReconciliationPhase.SAVE_RULE.value,
    ]
    
    if current_phase in subgraph_phases:
        logger.info(f"router_node: 当前在子图执行中 (phase={current_phase})，跳过意图识别")
        return {"messages": []}

    auth_token = state.get("auth_token", "")
    current_user = state.get("current_user")

    # ── 未登录状态：引导登录 / 处理登录注册 ──────────────────────
    if not auth_token or not current_user:
        messages = list(state.get("messages", []))
        last_user_msg = messages[-1].content if messages and hasattr(messages[-1], "content") else ""
        
        # 检查是否是表单提交（JSON 格式的表单数据）
        form_data = None
        try:
            if last_user_msg.strip().startswith("{") and "form_type" in last_user_msg:
                form_data = _json.loads(last_user_msg)
        except:
            pass
        
        if form_data:
            # 处理表单提交
            form_type = form_data.get("form_type")
            if form_type == "login":
                username = form_data.get("username", "").strip()
                password = form_data.get("password", "").strip()
                if username and password:
                    result = await auth_login(username, password)
                    if result.get("success"):
                        return {
                            "messages": [AIMessage(content=f"✅ {result['message']}")],
                            "auth_token": result["token"],
                            "current_user": result["user"],
                            "user_intent": UserIntent.UNKNOWN.value,
                        }
                    else:
                        # 登录失败，重新显示登录表单（错误信息嵌入表单）
                        error = result.get('error', '用户名或密码错误')
                        return {"messages": [AIMessage(content=generate_login_form(error))]}
            elif form_type == "register":
                username = form_data.get("username", "").strip()
                password = form_data.get("password", "").strip()
                if username and password:
                    result = await auth_register(
                        username, password,
                        email=form_data.get("email", "").strip() or None,
                        phone=form_data.get("phone", "").strip() or None,
                        company_code=form_data.get("company_code", "").strip() or None,
                        department_code=form_data.get("department_code", "").strip() or None,
                    )
                    if result.get("success"):
                        return {
                            "messages": [AIMessage(content=f"✅ {result['message']}")],
                            "auth_token": result["token"],
                            "current_user": result["user"],
                            "user_intent": UserIntent.UNKNOWN.value,
                        }
                    else:
                        # 注册失败，重新显示注册表单（错误信息嵌入表单）
                        error = result.get('error', '注册失败，请检查输入信息')
                        return {"messages": [AIMessage(content=generate_register_form(error))]}
        
        # 使用 LLM 流式生成回复（支持流式输出）
        llm = get_llm()
        # 使用 astream 进行流式调用，LangGraph 会自动处理流式输出
        resp = llm.invoke([SystemMessage(content=SYSTEM_PROMPT_NOT_LOGGED_IN)] + messages)
        content = resp.content.strip()

        # 尝试解析意图 JSON
        try:
            json_match = content
            if "```" in content:
                import re
                m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
                if m:
                    json_match = m.group(1)
            parsed = _json.loads(json_match)
            intent = parsed.get("intent", "")
        except (_json.JSONDecodeError, AttributeError):
            intent = ""

        if intent == "show_login_form":
            login_html = generate_login_form()
            # 验证：确保登录表单只包含用户名和密码字段
            if login_html.count('<input') != 2:
                logger.error(f"登录表单字段数量错误！期望2个，实际: {login_html.count('<input')}")
            if 'company_code' in login_html or 'department_code' in login_html:
                logger.error("登录表单错误地包含了公司编码或部门编码字段！")
            logger.info(f"返回登录表单，长度: {len(login_html)}, 输入框数量: {login_html.count('<input')}")
            return {"messages": [AIMessage(content=login_html)]}
        elif intent == "show_register_form":
            register_html = generate_register_form()
            logger.info(f"返回注册表单，长度: {len(register_html)}, 输入框数量: {register_html.count('<input')}")
            return {"messages": [AIMessage(content=register_html)]}
        else:
            # LLM 正常回复（引导用户）
            # 去掉开头的"！"或"!"，并确保只有一条消息
            cleaned_content = content.lstrip("！!").strip()
            return {"messages": [AIMessage(content=cleaned_content)]}

    # ── 已登录状态：正常意图识别 ──────────────────────────────────
    rules = await list_available_rules(auth_token)
    rules_text = "\n".join(
        [f"• {r['name']}（{r.get('description', '')}）" for r in rules]
    ) if rules else "暂无已有规则"

    username = current_user.get("username", "用户")
    system_msg = SYSTEM_PROMPT.format(username=username, available_rules=rules_text)

    llm = get_llm()
    messages = list(state.get("messages", []))
    resp = llm.invoke([SystemMessage(content=system_msg)] + messages)

    content = resp.content.strip()

    # 尝试解析 JSON 意图
    try:
        json_match = content
        if "```" in content:
            import re
            m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if m:
                json_match = m.group(1)
        parsed = _json.loads(json_match)
        intent = parsed.get("intent", "")
        rule_name = parsed.get("rule_name", "")
    except (_json.JSONDecodeError, AttributeError):
        intent = ""
        rule_name = ""

    # 检查是否切换意图
    old_intent = state.get("user_intent", "")
    uploaded_files = state.get("uploaded_files", [])
    
    if intent == UserIntent.USE_EXISTING_RULE.value and rule_name:
        if old_intent != intent:
            uploaded_files = []
        return {
            "messages": [AIMessage(content=f"好的，将使用规则「{rule_name}」进行对账。")],
            "user_intent": intent,
            "selected_rule_name": rule_name,
            "phase": ReconciliationPhase.TASK_EXECUTION.value,
            "execution_step": TaskExecutionStep.NOT_STARTED.value,
            "uploaded_files": uploaded_files,
        }
    elif intent == UserIntent.CREATE_NEW_RULE.value:
        if old_intent != intent:
            uploaded_files = []
        welcome_msg = (
            "🎯 **开始创建新的对账规则**\n\n"
            "我会引导你完成以下4个步骤：\n\n"
            "**1️⃣ 上传并分析文件** - 分析文件结构和列名\n"
            "**2️⃣ 确认字段映射** - 将列名映射到标准字段（订单号、金额等）\n"
            "**3️⃣ 配置规则参数** - 设置容差、订单号特征等\n"
            "**4️⃣ 预览并保存** - 查看规则效果并保存\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "请先上传需要对账的文件（业务数据和财务数据各一个 Excel/CSV 文件）。"
        )
        return {
            "messages": [AIMessage(content=welcome_msg)],
            "user_intent": intent,
            "phase": ReconciliationPhase.FILE_ANALYSIS.value,
            "uploaded_files": uploaded_files,
            "file_analyses": [],
            "suggested_mappings": {},  # 清空之前的字段映射
            "confirmed_mappings": {},  # 清空之前的确认映射
        }
    else:
        # 普通对话
        return {
            "messages": [AIMessage(content=content)],
            "user_intent": UserIntent.UNKNOWN.value,
            "uploaded_files": uploaded_files,  # 保留文件信息
        }


# ══════════════════════════════════════════════════════════════════════════════
# 第3层：任务执行 — 调用 finance-mcp
# ══════════════════════════════════════════════════════════════════════════════

async def _do_start_task(rule_name: str, files: list[str]) -> dict[str, Any]:
    """启动对账任务。"""
    result = await start_reconciliation(rule_name, files)
    return result


async def _do_poll(
    task_id: str, 
    progress_callback=None,
    max_polls: int = 60,  # 增加到 60 次 (60 秒)
    interval: float = 1.0  # 缩短到 1 秒
) -> dict[str, Any]:
    """轮询任务状态直到完成，并收集进度消息。
    
    Args:
        task_id: 任务 ID
        progress_callback: 未使用（保留接口兼容性）
        max_polls: 最大轮询次数
        interval: 轮询间隔（秒）
    
    Returns:
        包含 status 和可选的 progress_messages 的字典
    """
    # 进度消息列表（带时间戳，用于显示）
    progress_messages_with_timing = [
        (0, "📊 正在加载数据文件..."),
        (5, "🔍 正在分析数据结构..."),
        (15, "⚙️  正在执行对账规则..."),
        (30, "📈 正在生成对账结果..."),
        (45, "✨ 即将完成..."),
    ]
    
    collected_progress = []
    last_message_idx = -1
    
    for poll_count in range(max_polls):
        status = await get_reconciliation_status(task_id)
        st = status.get("status", "")
        
        # 根据时间显示进度（不使用回调，而是收集消息）
        for idx, (timing, message) in enumerate(progress_messages_with_timing):
            if poll_count >= timing and idx > last_message_idx:
                collected_progress.append(message)
                last_message_idx = idx
                logger.info(f"对账进度 [{poll_count}s]: {message}")
        
        if st in ("completed", "failed", "error"):
            result = status.copy()
            result["progress_messages"] = collected_progress
            return result
        
        await asyncio.sleep(interval)
    
    return {
        "status": "timeout",
        "task_id": task_id,
        "progress_messages": collected_progress
    }


def _run_async_safe(coro):
    """安全地运行协程，兼容已存在的事件循环环境。"""
    try:
        # 尝试获取当前运行中的事件循环
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # 没有运行中的事件循环，创建新的并运行
        return asyncio.run(coro)
    else:
        # 已有运行中的事件循环，在线程池中运行
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()


def task_execution_node(state: AgentState) -> dict:
    """第3层：启动对账任务、轮询状态、展示结果。

    由于 langgraph 节点是同步的，内部使用 asyncio 调用异步函数。
    """
    rule_name = state.get("selected_rule_name") or state.get("saved_rule_name")
    files = state.get("uploaded_files", [])
    step = state.get("execution_step", TaskExecutionStep.NOT_STARTED.value)

    if not rule_name:
        return {
            "messages": [AIMessage(content="缺少对账规则名称，请先选择或创建一个规则。")],
            "phase": ReconciliationPhase.IDLE.value,
        }
    if not files:
        # 等待文件上传
        interrupt({
            "question": "请上传需要对账的文件",
            "hint": "💡 上传文件后，点击发送按钮或直接发送消息",
        })
        # interrupt后结束节点，等待用户上传文件后重新进入
        return {
            "messages": [],
            "phase": ReconciliationPhase.TASK_EXECUTION.value,
                "execution_step": TaskExecutionStep.NOT_STARTED.value,
            }

    # ── 启动任务 ──
    logger.info(f"开始执行对账任务: rule={rule_name}, files={len(files)}个")
    start_result = _run_async_safe(_do_start_task(rule_name, files))

    if "error" in start_result:
        return {
            "messages": [AIMessage(content=f"❌ 启动对账任务失败：{start_result['error']}")],
            "phase": ReconciliationPhase.TASK_EXECUTION.value,
            "execution_step": TaskExecutionStep.NOT_STARTED.value,
        }

    task_id = start_result.get("task_id", "")
    
    # ── 启动成功，立即返回消息并开始轮询 ──
    messages_to_send = [
        AIMessage(content=f"🚀 对账任务已启动\n\n📋 规则：{rule_name}\n📁 文件：{len(files)} 个\n💾 任务ID：{task_id}\n\n⏳ 正在执行对账，预计需要 10-60 秒...\n\n📊 进度：开始加载数据..."),
    ]

    # ── 轮询 ──
    logger.info(f"开始轮询任务状态: task_id={task_id}")
    poll_result = _run_async_safe(_do_poll(task_id))

    status = poll_result.get("status", "")
    logger.info(f"轮询结束: task_id={task_id}, status={status}")

    if status == "completed":
        # ── 获取结果，存入 state，交给 result_analysis 节点由 LLM 分析 ──
        try:
            logger.info(f"开始获取对账结果: task_id={task_id}")
            result = _run_async_safe(get_reconciliation_result(task_id))
            logger.info(f"对账结果获取成功: task_id={task_id}, result keys={list(result.keys())}")

            return {
                "messages": messages_to_send,
                "task_id": task_id,
                "task_status": "completed",
                "task_result": result,
                "phase": ReconciliationPhase.TASK_EXECUTION.value,
                "execution_step": TaskExecutionStep.SHOWING_RESULT.value,
            }
        except Exception as e:
            logger.error(f"获取对账结果出错: task_id={task_id}, error={e}", exc_info=True)
            messages_to_send.append(AIMessage(content=f"❌ 获取对账结果失败：{str(e)}"))
            return {
                "messages": messages_to_send,
                "task_id": task_id,
                "task_status": "error",
                "phase": ReconciliationPhase.COMPLETED.value,
                "execution_step": TaskExecutionStep.DONE.value,
            }
    elif status == "timeout":
        messages_to_send.append(AIMessage(content="⏱️ 对账任务超时，任务可能仍在后台执行，请稍后查询。"))
        return {
            "messages": messages_to_send,
            "task_id": task_id,
            "task_status": status,
            "phase": ReconciliationPhase.COMPLETED.value,
            "execution_step": TaskExecutionStep.DONE.value,
        }
    else:
        messages_to_send.append(AIMessage(content=f"❌ 对账任务失败（状态: {status}），请检查日志或重试。"))
        return {
            "messages": messages_to_send,
            "task_id": task_id,
            "task_status": status,
            "phase": ReconciliationPhase.COMPLETED.value,
            "execution_step": TaskExecutionStep.DONE.value,
        }


# ══════════════════════════════════════════════════════════════════════════════
# 结果分析 — 由 LLM 分析对账结果并流式输出
# ══════════════════════════════════════════════════════════════════════════════

RESULT_ANALYSIS_PROMPT = """\
你是一个专业的财务对账分析师。请根据以下对账结果，给出清晰、专业的分析报告。

对账结果数据：
{result_json}

请严格按照以下格式输出分析报告：

## 📊 对账概况
简要列出：业务记录数、财务记录数、匹配数、差异数、匹配率。

## ⚠️ 差异分析
**按问题类型（issue_type）分组**列出差异，每个类型下列出对应的订单号。格式如下：

### 类型名称（X 条）
说明该类型的含义。
- 订单号列表（每行一个）

如果某类型的订单数超过20条，只列前20个并注明总数。

要求：
- 使用中文
- 数据准确，直接引用结果中的数字
- 语言简洁专业，不要重复信息
- 不需要给出建议，只做数据分析
"""


def result_analysis_node(state: AgentState) -> dict:
    """由 LLM 分析对账结果并生成报告（流式输出）。"""
    import json as _json

    task_result = state.get("task_result")
    task_status = state.get("task_status", "")

    # 如果任务未完成，跳过分析
    if task_status != "completed" or not task_result:
        logger.info(f"跳过结果分析: task_status={task_status}")
        return {
            "phase": ReconciliationPhase.COMPLETED.value,
            "execution_step": TaskExecutionStep.DONE.value,
        }

    # 构建结果 JSON（精简版，避免 token 过多）
    summary = task_result.get("summary", {})
    issues = task_result.get("issues", [])
    
    result_for_llm = {
        "summary": summary,
        "issues_count": len(issues),
        "issues": issues[:50],  # 传前50条给 LLM（按类型分组需要更多数据）
    }

    result_json = _json.dumps(result_for_llm, ensure_ascii=False, indent=2, default=str)
    logger.info(f"开始 LLM 分析对账结果: summary={summary}, issues_count={len(issues)}")

    llm = get_llm()
    prompt = RESULT_ANALYSIS_PROMPT.format(result_json=result_json)

    messages = [SystemMessage(content=prompt)]
    resp = llm.invoke(messages)

    return {
        "messages": [AIMessage(content=resp.content)],
        "phase": ReconciliationPhase.COMPLETED.value,
        "execution_step": TaskExecutionStep.DONE.value,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 路由
# ══════════════════════════════════════════════════════════════════════════════

def route_after_router(state: AgentState) -> str:
    """router 之后的条件路由。"""
    intent = state.get("user_intent", "")
    phase = state.get("phase", "")

    if intent == UserIntent.CREATE_NEW_RULE.value:
        # 直接路由到文件分析节点（不再使用子图）
        return "file_analysis"
    elif intent == UserIntent.USE_EXISTING_RULE.value:
        return "task_execution"
    else:
        return END


def route_after_reconciliation(state: AgentState) -> str:
    """对账子图完成后，判断用户是否要立即执行。"""
    # 如果已保存规则，检查用户是否要立即开始
    saved = state.get("saved_rule_name")
    if saved:
        return "ask_start_now"
    return END


def ask_start_now_node(state: AgentState) -> dict:
    """询问用户是否立即开始对账。"""
    user_response = interrupt({
        "question": "是否立即开始对账？",
        "hint": "回复\"开始\"立即执行，或\"稍后\"退出",
    })

    response_str = str(user_response).strip()
    if response_str in ("开始", "是", "yes", "ok", "好", "执行", "立即开始"):
        return {
            "messages": [AIMessage(content="好的，开始执行对账...")],
            "selected_rule_name": state.get("saved_rule_name"),
            "phase": ReconciliationPhase.TASK_EXECUTION.value,
            "execution_step": TaskExecutionStep.NOT_STARTED.value,
        }
    else:
        return {
            "messages": [AIMessage(content="好的，你可以随时回来执行对账。")],
            "phase": ReconciliationPhase.COMPLETED.value,
        }


def route_after_ask_start(state: AgentState) -> str:
    phase = state.get("phase", "")
    if phase == ReconciliationPhase.TASK_EXECUTION.value:
        return "task_execution"
    return END


# ══════════════════════════════════════════════════════════════════════════════
# 构建主图
# ══════════════════════════════════════════════════════════════════════════════

def build_main_graph() -> StateGraph:
    """构建主 Agent 图。
    
    ⚠️ 对账规则生成的节点直接展平到主图中（不再使用子图），
    这样 interrupt/resume 时不会 replay 之前的节点，避免重复文件分析。
    """

    # 数据准备子图（暂时保留为子图）
    data_preparation_sg = build_data_preparation_subgraph()

    graph = StateGraph(AgentState)

    # ── 节点 ──────────────────────────────────────────────────────────────
    graph.add_node("router", router_node)
    
    # 对账规则生成节点（直接在主图中，避免子图 replay）
    graph.add_node("file_analysis", file_analysis_node)
    graph.add_node("field_mapping", field_mapping_node)
    graph.add_node("rule_config", rule_config_node)
    graph.add_node("validation_preview", validation_preview_node)
    graph.add_node("save_rule", save_rule_node)
    
    # 其他节点
    graph.add_node("data_preparation_subgraph", data_preparation_sg.compile())
    graph.add_node("task_execution", task_execution_node)
    graph.add_node("result_analysis", result_analysis_node)
    graph.add_node("ask_start_now", ask_start_now_node)

    # ── 边 ────────────────────────────────────────────────────────────────
    graph.set_entry_point("router")

    # router 后路由
    graph.add_conditional_edges("router", route_after_router, {
        "file_analysis": "file_analysis",
        "task_execution": "task_execution",
        END: END,
    })

    # 对账规则生成流程（展平的）
    graph.add_conditional_edges("file_analysis", route_after_file_analysis, {
        "field_mapping": "field_mapping",
        END: END,
    })
    graph.add_conditional_edges("field_mapping", route_after_field_mapping, {
        "field_mapping": "field_mapping",   # 调整意见，重新进入
        "rule_config": "rule_config",       # 确认，进入下一步
    })
    graph.add_conditional_edges("rule_config", route_after_rule_config, {
        "rule_config": "rule_config",                # 调整意见，重新进入
        "validation_preview": "validation_preview",  # 确认，进入下一步
    })
    graph.add_conditional_edges("validation_preview", route_after_preview, {
        "rule_config": "rule_config",
        "save_rule": "save_rule",
    })
    graph.add_conditional_edges("save_rule", route_after_reconciliation, {
        "ask_start_now": "ask_start_now",
        END: END,
    })

    # 询问是否立即执行
    graph.add_conditional_edges("ask_start_now", route_after_ask_start, {
        "task_execution": "task_execution",
        END: END,
    })

    # task_execution → result_analysis → END
    graph.add_edge("task_execution", "result_analysis")
    graph.add_edge("result_analysis", END)

    return graph


def create_app():
    """创建带有 MemorySaver 的可运行图实例。"""
    memory = MemorySaver()
    graph = build_main_graph()
    return graph.compile(checkpointer=memory)
