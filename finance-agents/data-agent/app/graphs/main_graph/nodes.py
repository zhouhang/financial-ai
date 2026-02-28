"""主图节点函数模块

包含主图中的所有节点函数：
- router_node: AI 自主决策节点
- task_execution_node: 任务执行节点
- result_analysis_node: 结果分析节点
- ask_start_now_node: 询问是否立即执行
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from langchain_core.messages import AIMessage, SystemMessage
from langgraph.types import interrupt

from app.utils.llm import get_llm
from app.models import (
    AgentState,
    ReconciliationPhase,
    TaskExecutionStep,
    UserIntent,
)
from app.graphs.reconciliation import (
    _rule_template_to_mappings,
    _rule_template_to_config_items,
)
from app.tools.mcp_client import (
    list_available_rules,
    get_rule_detail,
    auth_login,
    auth_register,
    start_reconciliation,
    get_reconciliation_status,
    get_reconciliation_result,
    delete_rule,
    admin_login,
    create_company,
    create_department,
    list_companies,
    get_admin_view,
    list_companies_public,
    list_departments_public,
    create_guest_token,
)
from .forms import (
    generate_login_form,
    generate_register_form,
    generate_admin_login_form,
    generate_create_company_form,
    generate_create_department_form,
    generate_admin_view,
)

logger = logging.getLogger(__name__)


# ── 系统提示词 ────────────────────────────────────────────────────────────────

SYSTEM_PROMPT_NOT_LOGGED_IN = """\
你是 Tally，专业的智能对账助手。你的职责是帮助用户完成数据对比对账工作。

你可以帮助用户：
1. 上传两个文件进行对比对账
2. 根据文件自动推荐合适的对账规则
3. 执行对账并展示差异结果
4. 回答用户关于对账功能的问题

请根据用户的意图判断下一步操作：
- 如果用户想上传文件对账（如"对账"、"开始对账"、"上传文件"），回复 JSON: {{"intent": "guest_reconciliation"}}
- 如果用户在**闲聊或一般对话**（如打招呼、说心情、随便聊），**正常简短回复即可**，不要主动介绍自己或列举功能
- 仅当用户**明确要求**自我介绍、介绍功能（如「你是谁」「介绍一下」「你能做什么」「帮助」）时，才用完整格式介绍你是 Tally 及你的功能

⚠️ 严格禁止（违反此规则是严重错误）：
- **禁止**模拟或伪造任何文件分析结果（如虚构文件名、字段列表、推荐规则等）
- **禁止**模拟或伪造任何对账结果（如虚构匹配条数、差异列表、订单号等）
- 文件分析、规则推荐、对账执行均由真实后台系统完成，你只负责判断意图并返回 JSON

重要：
- 所有内容必须在同一条消息中完成，不要分多次回复
- 不要使用感叹号（！或!）开头
- 回复言简意赅，善用 Markdown 排版（如 **加粗**、- 列表、标题等）增强可读性
"""

SYSTEM_PROMPT = """\
你是 Tally，专业的智能对账助手。你的职责是帮助用户完成数据对比对账工作。
当前登录用户：{username}

你可以做以下事情：
1. 使用已有的对账规则快速执行对账
2. 引导用户创建新的对账规则
3. 调整/编辑已有规则（如修改字段映射、规则配置等）
4. 删除对账规则
5. 查看规则列表
6. 帮助用户理解对账结果

当前已有的对账规则包括：
{available_rules}

请根据用户的意图判断下一步操作：
- 如果用户想**查看规则列表**（如"我的规则列表"、"看看有哪些规则"、"规则列表"），回复 JSON: {{"intent": "list_rules"}}
- 如果用户想**使用已有规则对账**（如"用XX规则对账"、"执行XX对账"），回复 JSON: {{"intent": "use_existing_rule", "rule_name": "规则名称"}}
- 如果用户想**调整/编辑已有规则**（如"调整XX规则"、"编辑XX"、"修改XX规则"），回复 JSON: {{"intent": "edit_rule", "rule_name": "规则名称"}}
- 如果用户想创建新规则，回复 JSON: {{"intent": "create_new_rule"}}
- 如果用户想删除规则，回复 JSON: {{"intent": "delete_rule", "rule_name": "规则名称"}}
- 如果用户在闲聊或一般对话（如打招呼、夸赞、闲聊），**正常简短回复即可**，不要主动介绍自己或列举规则。
- 仅当用户**明确要求**自我介绍、介绍功能、展示规则列表（如「介绍一下你自己」「你能做什么」「有哪些规则」「看看规则」）时，才用完整格式回复：
  1. 用「你好，{username}！我是 Tally」开头
  2. 简要介绍你能做的事
  3. 说明当前已有规则
  4. 询问用户需要什么帮助
  5. 回复言简意赅，善用 Markdown 排版（**加粗**、- 列表等）

注意：
- **查看规则列表**与**使用规则对账**要严格区分：说"规则列表"、"看看规则"、"有哪些规则"→ list_rules；说"用XX对账"、"执行对账"→ use_existing_rule
- **调整/编辑规则**与**使用规则对账**要严格区分：说"调整XX"、"编辑XX"、"修改XX规则"→ edit_rule；说"用XX对账"、"执行对账"→ use_existing_rule
- 只在明确判断意图时才返回 JSON，否则正常对话
- 删除规则时，必须从用户输入中提取准确的规则名称
- 只返回一条消息，不要分多次回复

⚠️ 严格禁止（违反此规则是严重错误）：
- **禁止**模拟或伪造任何文件分析结果（如虚构文件名、字段列表等）
- **禁止**模拟或伪造任何对账结果（如虚构匹配条数、差异列表、订单号等）
- **禁止**模拟或伪造规则推荐数据
- 文件分析、规则推荐、对账执行均由真实后台系统完成，你只负责判断意图并返回 JSON
"""


RESULT_ANALYSIS_PROMPT = """\
你是对账结果分析助手。请用简洁友好的语言描述对账结果。

对账结果数据：
{result_json}

重要要求：
1. 善用 Markdown 排版（**加粗**、- 列表、标题等）增强可读性
2. 使用 Emoji 图标增强可读性
3. 语言言简意赅，简洁直白，易于理解
4. 文件名不要包含时间戳，使用原始上传的文件名
5. 异常类型直接用文件名表示，不要用"文件1"、"文件2"等描述
6. 【关键】差异/异常的总条数必须使用 summary.unmatched_records（或 issues_count），切勿使用 total_business_records 或 total_finance_records。例如差异列表标题应写「差异 (10条)」而非「差异 (985条)」

示例格式：

✅ 对账完成

总记录：100条
匹配成功：95条
异常记录：5条
匹配率：95%

异常明细（必须用表格展示，表头为「异常订单号」「异常原因」，每行一条数据）：

| 异常订单号 | 异常原因 |
|-----------|----------|
| 订单A001 | 销售数据.xlsx缺失 |
| 订单A002 | 销售数据.xlsx缺失 |
| 订单B001 | 财务报表.xlsx金额差异（差异0.5元） |
| 订单B002 | 财务报表.xlsx金额差异（差异1.2元） |

注意：
- 异常明细必须使用 Markdown 表格，表头固定为「异常订单号」「异常原因」
- 每行一条异常记录，从 issues 中按 order_id 和 detail 提取
- 如果某类型订单数超过20条，只列前20个并在表格后注明「（共N条，仅列前20条）」
"""


# ══════════════════════════════════════════════════════════════════════════════
# 第1层：对话理解 — router
# ══════════════════════════════════════════════════════════════════════════════

def _parse_form_data(last_user_msg: str) -> dict | None:
    """解析用户消息中的表单数据。

    Args:
        last_user_msg: 用户最后一条消息内容

    Returns:
        解析出的表单数据字典，如果不是表单数据则返回 None
    """
    try:
        if last_user_msg.strip().startswith("{") and "form_type" in last_user_msg:
            return json.loads(last_user_msg)
    except:
        pass
    return None


async def admin_handler(state: AgentState) -> dict | None:
    """处理管理员登录和管理员操作。

    Args:
        state: 当前状态

    Returns:
        如果是管理员相关操作，返回状态更新字典；否则返回 None
    """
    # 提取通用状态
    messages = list(state.get("messages", []))
    last_user_msg = messages[-1].content if messages and hasattr(messages[-1], "content") else ""
    last_user_msg_lower = last_user_msg.lower().strip()
    admin_token = state.get("admin_token", "")
    admin_data = state.get("admin_data", {})

    # 解析表单数据
    form_data = _parse_form_data(last_user_msg)

    # ── 管理员隐藏指令检测（优先级最高，在用户登录状态判断之前）─────
    # 管理员登录指令（任何状态下都可触发）
    if "管理员登录" in last_user_msg or ("admin" in last_user_msg_lower and "login" not in last_user_msg_lower):
        return {
            "messages": [AIMessage(content=generate_admin_login_form())],
            "user_intent": UserIntent.ADMIN_LOGIN.value,
        }

    # 管理员表单提交
    if form_data and form_data.get("form_type") == "admin_login":
        username = form_data.get("username", "").strip()
        password = form_data.get("password", "").strip()
        if username and password:
            result = await admin_login(username, password)
            if result.get("success"):
                # 登录成功，显示简单提示
                return {
                    "messages": [AIMessage(content=f"✅ 管理员 {username} 登录成功！\n\n可用指令：\n• 输入「创建公司」添加公司\n• 输入「创建部门」添加部门\n• 输入「退出管理」退出管理员模式")],
                    "admin_token": result["admin_token"],
                    "user_intent": UserIntent.ADMIN_VIEW.value,
                }
            else:
                error = result.get('error', '管理员用户名或密码错误')
                return {"messages": [AIMessage(content=generate_admin_login_form(error))]}

    # 管理员视图状态下的操作
    if admin_token:
        # 创建公司指令
        if "创建公司" in last_user_msg:
            return {
                "messages": [AIMessage(content=generate_create_company_form())],
                "user_intent": UserIntent.CREATE_COMPANY.value,
            }

        # 创建公司表单提交
        if form_data and form_data.get("form_type") == "create_company":
            name = form_data.get("name", "").strip()
            if name:
                result = await create_company(admin_token, name)
                if result.get("success"):
                    return {
                        "messages": [AIMessage(content=f"✅ 公司 '{name}' 创建成功！\n\n输入「创建公司」继续添加 | 输入「创建部门」添加部门")],
                    }
                else:
                    error = result.get('error', '创建公司失败')
                    return {"messages": [AIMessage(content=generate_create_company_form(error))]}

        # 创建部门指令
        if "创建部门" in last_user_msg:
            companies_result = await list_companies(admin_token)
            return {
                "messages": [AIMessage(content=generate_create_department_form(companies_result.get("companies")))],
                "user_intent": UserIntent.CREATE_DEPARTMENT.value,
            }

        # 创建部门表单提交
        if form_data and form_data.get("form_type") == "create_department":
            company_id = form_data.get("company_id", "").strip()
            name = form_data.get("name", "").strip()
            if company_id and name:
                result = await create_department(admin_token, company_id, name)
                if result.get("success"):
                    return {
                        "messages": [AIMessage(content=f"✅ 部门 '{name}' 创建成功！\n\n输入「创建部门」继续添加 | 输入「创建公司」添加公司")],
                    }
                else:
                    error = result.get('error', '创建部门失败')
                    companies_result = await list_companies(admin_token)
                    return {"messages": [AIMessage(content=generate_create_department_form(companies_result.get("companies"), error))]}

        # 退出管理员
        if "退出" in last_user_msg and "管理" in last_user_msg:
            return {
                "messages": [AIMessage(content="已退出管理员模式")],
                "admin_token": None,
                "admin_data": None,
                "user_intent": UserIntent.UNKNOWN.value,
            }

        # 返回/查看管理员视图
        if ("返回" in last_user_msg or "查看" in last_user_msg) and admin_token:
            view_result = await get_admin_view(admin_token)
            return {
                "messages": [AIMessage(content=generate_admin_view(view_result.get("data"), admin_token))],
                "admin_data": view_result.get("data", {}),
            }

    # 不是管理员相关操作，返回 None
    return None


async def auth_handler(state: AgentState) -> dict | None:
    """处理未登录用户的认证流程（登录/注册）。

    增强版：支持游客模式下的 workflow 上下文感知
    - 在 workflow 中时，判断游客是想继续当前流程还是切换意图
    - 如果是 RESUME_WORKFLOW，返回空消息，让 graph 继续路由到当前 phase 节点
    - 如果是其他意图（如想登录），保存 workflow 状态并处理

    Args:
        state: 当前状态

    Returns:
        如果用户未认证，返回状态更新字典；如果已认证，返回 None
    """
    # 提取通用状态
    auth_token = state.get("auth_token", "")
    current_user = state.get("current_user")
    messages = list(state.get("messages", []))
    last_user_msg = messages[-1].content if messages and hasattr(messages[-1], "content") else ""

    # 如果已登录，返回 None（由 intent_router 处理）
    if auth_token and current_user:
        return None

    # ====== 新增：游客模式下的 workflow 上下文感知 ======
    current_phase = state.get("phase", "")

    # 定义游客可能进入的 workflow 阶段（游客对账流程）
    guest_workflow_phases = [
        ReconciliationPhase.FILE_ANALYSIS.value,
        ReconciliationPhase.FIELD_MAPPING.value,
        ReconciliationPhase.RULE_RECOMMENDATION.value,
        ReconciliationPhase.RULE_CONFIG.value,
        ReconciliationPhase.VALIDATION_PREVIEW.value,
        ReconciliationPhase.SAVE_RULE.value,
        ReconciliationPhase.RESULT_EVALUATION.value,
    ]

    if current_phase in guest_workflow_phases:
        # 游客在 workflow 中，判断是想继续还是切换意图
        from app.utils.workflow_intent import classify_intent_in_workflow_guest

        logger.info(f"🔍 [游客模式] auth_handler 进入 workflow 上下文检查: phase={current_phase}, user_msg='{last_user_msg[:100]}'")

        try:
            intent = await classify_intent_in_workflow_guest(
                user_msg=last_user_msg,
                current_phase=current_phase,
                state=state
            )

            logger.info(f"🔍 [游客模式] classify_intent_in_workflow_guest 返回: intent={intent}")

            if intent == UserIntent.RESUME_WORKFLOW.value:
                # 继续 workflow，返回空，让 graph 路由到当前 phase 的节点
                logger.info(f"auth_handler [游客]: 用户想继续 workflow (phase={current_phase})")
                return {"messages": []}
            elif intent == "LOGIN":
                # 游客想登录，保存 workflow 状态，统一提示点击右上角登录
                logger.info(f"auth_handler [游客]: 用户在 workflow 中想登录")
                from app.utils.workflow_intent import save_workflow_context
                save_workflow_context(state, current_phase)
                return {
                    "messages": [AIMessage(content="💡 请点击右上角登录按钮进行登录。")],
                    "phase": "",  # 清空 phase，退出 workflow
                }
            elif intent == "CANCEL":
                # 游客想取消/退出 workflow
                logger.info(f"auth_handler [游客]: 用户想取消 workflow")
                return {
                    "messages": [AIMessage(content="已取消当前操作。\n\n你可以说「创建规则」开始新的对账，或者「登录」查看已有规则。")],
                    "phase": "",  # 清空 phase，退出 workflow
                    "user_intent": UserIntent.UNKNOWN.value,
                }
            else:
                # 其他意图，继续 workflow（降级策略）
                logger.info(f"auth_handler [游客]: 未识别的意图 {intent}，默认继续 workflow")
                return {"messages": []}
        except Exception as e:
            logger.error(f"[游客模式] workflow 意图分类失败: {e}，降级为继续 workflow")
            # 降级：出错时默认继续 workflow，避免中断用户流程
            return {"messages": []}

    # 解析表单数据
    form_data = _parse_form_data(last_user_msg)

    # ── 未登录状态：引导登录 / 处理登录注册 ──────────────────────
    if form_data:
        # 处理表单提交
        form_type = form_data.get("form_type")
        if form_type == "login":
            username = form_data.get("username", "").strip()
            password = form_data.get("password", "").strip()
            if username and password:
                result = await auth_login(username, password)
                if result.get("success"):
                    # token/user 通过 output 由 server 发送 type "auth"，前端保存；消息内容仅展示友好文案
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
        elif form_type == "select_company":
            # 用户选择了公司，显示带部门的注册表单
            company_id = form_data.get("company_id", "").strip()
            if company_id:
                # 获取公司列表和该公司的部门列表
                companies_result = await list_companies_public()
                departments_result = await list_departments_public(company_id)
                return {
                    "messages": [AIMessage(content=generate_register_form(
                        companies=companies_result.get("companies", []),
                        departments=departments_result.get("departments", []),
                        selected_company_id=company_id
                    ))],
                }
        elif form_type == "register":
            username = form_data.get("username", "").strip()
            password = form_data.get("password", "").strip()
            company_id = form_data.get("company_id", "").strip()
            department_id = form_data.get("department_id", "").strip()
            if username and password:
                result = await auth_register(
                    username, password,
                    email=form_data.get("email", "").strip() or None,
                    phone=form_data.get("phone", "").strip() or None,
                    company_id=company_id or None,
                    department_id=department_id or None,
                )
                if result.get("success"):
                    # token/user 通过 output 由 server 发送 type "auth"，前端保存；消息内容仅展示友好文案
                    return {
                        "messages": [AIMessage(content=f"✅ {result['message']}")],
                        "auth_token": result["token"],
                        "current_user": result["user"],
                        "user_intent": UserIntent.UNKNOWN.value,
                    }
                else:
                    # 注册失败，重新显示注册表单（错误信息嵌入表单）
                    error = result.get('error', '注册失败，请检查输入信息')
                    companies_result = await list_companies_public()
                    departments_result = await list_departments_public(company_id) if company_id else {"departments": []}
                    return {"messages": [AIMessage(content=generate_register_form(
                        error=error,
                        companies=companies_result.get("companies", []),
                        departments=departments_result.get("departments", []),
                        selected_company_id=company_id
                    ))]}

    # 使用 LLM 生成回复
    llm = get_llm()
    resp = await llm.ainvoke([SystemMessage(content=SYSTEM_PROMPT_NOT_LOGGED_IN)] + messages)
    content = resp.content.strip()

    # 尝试解析意图 JSON
    try:
        json_match = content
        if "```" in content:
            m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if m:
                json_match = m.group(1)
        parsed = json.loads(json_match)
        intent = parsed.get("intent", "")
    except (json.JSONDecodeError, AttributeError):
        intent = ""

    if intent == "guest_reconciliation":
        # 游客对账流程：使用推荐规则
        # 创建或获取游客token
        session_id = state.get("thread_id") or f"guest_{state.get('thread_id', 'unknown')}"
        
        # 获取游客token
        guest_result = await create_guest_token(session_id=session_id)
        
        if guest_result.get("success"):
            guest_token = guest_result.get("token")
            # 检查是否已有上传的文件
            uploaded = state.get("uploaded_files", [])
            if uploaded:
                # 已有文件，直接进入文件分析
                return {
                    "messages": [AIMessage(content="好的，我现在为您分析文件并推荐合适的规则。")],
                    "guest_token": guest_token,
                    "user_intent": "guest_reconciliation",
                }
            else:
                # 没有文件，提示上传
                return {
                    "messages": [AIMessage(content="好的，请您上传两个文件，我会为您推荐合适的规则。")],
                    "guest_token": guest_token,
                    "user_intent": "guest_reconciliation",
                }
        else:
            return {"messages": [AIMessage(content="抱歉，无法创建游客会话，请稍后重试。")]}
    elif intent == "show_login_form":
        # 用户要登录，统一提示点击右上角登录按钮
        return {"messages": [AIMessage(content="💡 请点击右上角登录按钮进行登录。")]}
    elif intent == "show_register_form":
        # 用户要注册，统一提示点击右上角登录按钮切换至注册
        return {"messages": [AIMessage(content="💡 请点击右上角登录按钮，切换至注册进行注册。")]}
    else:
        # LLM 正常回复（引导用户）
        # 去掉开头的"！"或"!"，并确保只有一条消息
        cleaned_content = content.strip()
        return {"messages": [AIMessage(content=cleaned_content)]}


async def intent_router(state: AgentState) -> dict:
    """核心意图识别：为已登录用户识别意图并路由到相应流程。

    增强版：支持所有 workflow 上下文感知
    - 在 workflow 中时，判断用户是想继续当前流程还是切换意图
    - 如果是 RESUME_WORKFLOW，返回空消息，让 graph 继续路由到当前 phase 节点
    - 如果是其他意图，保存 workflow 状态，清空 phase，切换意图

    Args:
        state: 当前状态（假设用户已认证）

    Returns:
        状态更新字典，包含识别的意图和相应的状态转换
    """
    # ====== 新增：workflow 上下文感知（覆盖所有 workflow 阶段）======
    current_phase = state.get("phase", "")

    # 定义所有 workflow 阶段
    all_workflow_phases = [
        # 规则创建流程
        ReconciliationPhase.FILE_ANALYSIS.value,
        ReconciliationPhase.FIELD_MAPPING.value,
        ReconciliationPhase.RULE_RECOMMENDATION.value,
        ReconciliationPhase.RULE_CONFIG.value,
        ReconciliationPhase.VALIDATION_PREVIEW.value,
        ReconciliationPhase.SAVE_RULE.value,
        ReconciliationPhase.RESULT_EVALUATION.value,
        # 规则编辑流程
        ReconciliationPhase.EDIT_FIELD_MAPPING.value,
        ReconciliationPhase.EDIT_RULE_CONFIG.value,
        ReconciliationPhase.EDIT_VALIDATION_PREVIEW.value,
        ReconciliationPhase.EDIT_SAVE.value,
    ]

    if current_phase in all_workflow_phases:
        # 在任何 workflow 中，判断用户是想继续还是切换意图
        from app.utils.workflow_intent import classify_intent_in_workflow, save_workflow_context

        messages = list(state.get("messages", []))
        last_user_msg = (messages[-1].content if messages and hasattr(messages[-1], "content") else "") or ""

        logger.info(f"🔍 [DEBUG] intent_router 进入 workflow 上下文检查: phase={current_phase}, user_msg='{last_user_msg[:100]}'")

        try:
            intent = await classify_intent_in_workflow(
                user_msg=last_user_msg,
                current_phase=current_phase,
                state=state
            )

            logger.info(f"🔍 [DEBUG] classify_intent_in_workflow 返回: intent={intent}")

            if intent == UserIntent.RESUME_WORKFLOW.value:
                # 继续 workflow，返回空，让 graph 路由到当前 phase 的节点
                logger.info(f"intent_router: 用户想继续 workflow (phase={current_phase})")
                return {"messages": []}
            else:
                # 用户想切换意图，保存 workflow 状态并切换
                logger.info(f"intent_router: 用户在 workflow 中切换意图 {current_phase} → {intent}")
                save_workflow_context(state, current_phase)
                # 清空 phase，设置新意图，LangGraph 会重新路由
                return {
                    "phase": "",
                    "user_intent": intent,
                    "messages": []
                }
        except Exception as e:
            logger.error(f"workflow 意图分类失败: {e}，降级为继续 workflow")
            # 降级：出错时默认继续 workflow，避免中断用户流程
            return {"messages": []}

    # ====== 原有逻辑：正常意图识别 ======
    # 提取通用状态
    auth_token = state.get("auth_token", "")
    current_user = state.get("current_user")
    messages = list(state.get("messages", []))

    # ── 已登录状态：正常意图识别 ──────────────────────────────────
    rules = await list_available_rules(auth_token)
    rules_text = "\n".join(
        [f"• {r['name']}（{r.get('description', '')}）" for r in rules]
    ) if rules else "暂无已有规则"

    username = current_user.get("username", "用户")
    # 使用 replace 替代 format，避免规则名称/描述中的 {} 被误解析
    system_msg = SYSTEM_PROMPT.replace("{username}", username).replace("{available_rules}", rules_text)

    llm = get_llm()
    messages = list(state.get("messages", []))
    resp = await llm.ainvoke([SystemMessage(content=system_msg)] + messages)

    content = resp.content.strip()

    # 尝试解析 JSON 意图
    try:
        json_match = content
        if "```" in content:
            m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if m:
                json_match = m.group(1)
        parsed = json.loads(json_match)
        intent = parsed.get("intent", "")
        rule_name = parsed.get("rule_name", "")
    except (json.JSONDecodeError, AttributeError):
        intent = ""
        rule_name = ""

    # ⚠️ 兜底：用户明确说"规则列表"/"看看规则"时，强制识别为 list_rules，避免误触发对账
    last_user_msg = (messages[-1].content if messages and hasattr(messages[-1], "content") else "") or ""
    last_user_msg_lower = last_user_msg.lower().strip()
    list_rules_keywords = ("规则列表", "看看规则", "有哪些规则", "规则有哪些", "我的规则", "查看规则")
    if any(kw in last_user_msg_lower for kw in list_rules_keywords) and intent == UserIntent.USE_EXISTING_RULE.value:
        intent = UserIntent.LIST_RULES.value
        rule_name = ""
        logger.info(f"router: 用户说「{last_user_msg[:30]}...」强制识别为 list_rules，避免误触发对账")

    # ⚠️ 兜底：对账完成后用户说"调整/编辑/修改XX规则"时，强制识别为 edit_rule，避免误触发再次对账
    edit_rule_keywords = ("调整", "编辑", "修改")
    if (state.get("phase", "") == ReconciliationPhase.COMPLETED.value
            and any(kw in last_user_msg_lower for kw in edit_rule_keywords)
            and intent != UserIntent.EDIT_RULE.value):
        intent = UserIntent.EDIT_RULE.value
        # 从规则名中提取：用户可能说"调整喜马"、"调整喜马规则"
        if not rule_name and rules:
            for r in rules:
                if r.get("name", "") in last_user_msg or last_user_msg in r.get("name", ""):
                    rule_name = r.get("name", "")
                    break
        logger.info(f"router: 对账完成后用户说「{last_user_msg[:30]}...」强制识别为 edit_rule，避免误触发对账")

    # 检查是否切换意图
    old_intent = state.get("user_intent", "")
    old_phase = state.get("phase", "")
    uploaded_files = state.get("uploaded_files", [])

    # ⚠️ 关键修复：如果前一个对账已完成，开始新对账时需要清空旧数据
    # 只有在 phase 不是 COMPLETED 时，才保留 uploaded_files（用户换文件的场景）
    if old_phase == ReconciliationPhase.COMPLETED.value:
        # 对账已完成，开始新对账需要清空旧数据
        uploaded_files = []

    if intent == UserIntent.LIST_RULES.value:
        # 查看规则列表：直接展示，不触发对账
        if rules:
            lines = ["📋 **我的对账规则列表**\n"]
            for r in rules:
                desc = r.get("description", "")
                lines.append(f"• **{r['name']}**" + (f"（{desc}）" if desc else ""))
            msg = "\n".join(lines)
        else:
            msg = "📋 暂无对账规则。\n\n你可以说「创建新规则」来创建第一个对账规则。"

        # ====== 新增：附加 workflow 恢复提示 ======
        if state.get("workflow_context"):
            from app.utils.workflow_intent import generate_resume_prompt
            resume_prompt = generate_resume_prompt(state["workflow_context"])
            msg += resume_prompt

        return {
            "messages": [AIMessage(content=msg)],
            "user_intent": UserIntent.UNKNOWN.value,
        }
    elif intent == UserIntent.USE_EXISTING_RULE.value and rule_name:
        # ⚠️ 修复：切换意图时不要清空 uploaded_files，否则会丢失用户刚上传的新文件
        # （用户换文件后说「使用南京飞翰对账」时，state 已通过 input 合并了新文件，清空会导致仍用旧结果）
        msg = f"好的，将使用规则「{rule_name}」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）"
        return {
            "messages": [AIMessage(content=msg)],
            "user_intent": intent,
            "selected_rule_name": rule_name,
            "phase": ReconciliationPhase.TASK_EXECUTION.value,
            "execution_step": TaskExecutionStep.NOT_STARTED.value,
            "uploaded_files": uploaded_files,
        }
    elif intent == UserIntent.CREATE_NEW_RULE.value:
        if old_intent != intent or old_phase == ReconciliationPhase.COMPLETED.value:
            # 开始创建新规则，清空旧数据
            uploaded_files = []
        welcome_msg = (
            "🎯 **开始创建新的对账规则**\n\n"
            "我会引导你完成以下4个步骤：\n\n"
            "1️⃣ 上传并分析文件 - 分析文件结构和列名\n\n"
            "2️⃣ 确认字段映射 - 将列名映射到标准字段（订单号、金额等）\n\n"
            "3️⃣ 配置规则参数 - 设置容差、订单号特征等\n\n"
            "4️⃣ 预览并保存 - 查看规则效果并保存\n\n"
            "请先上传需要对账的文件（文件1和文件2各一个 Excel/CSV 文件）。"
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
    elif intent == UserIntent.DELETE_RULE.value and rule_name:
        # 删除规则：必须从用户消息中提取精确的规则名，避免误删（如用户说「删除西福3」时不应删除「西福」）
        try:
            target_name = rule_name
            m = re.search(r"(?:删除|删掉)\s*([^\s,，。]+?)(?:\s*规则)?\s*$", last_user_msg)
            if m:
                extracted = m.group(1).strip()
                if extracted.endswith("规则"):
                    extracted = extracted[:-2].strip()
                target_name = extracted
            # 仅当规则列表中存在与 target_name 完全匹配的规则时才删除
            rule_id = None
            matched_rule_name = None
            for rule in rules:
                if rule.get("name") == target_name:
                    rule_id = rule.get("id")
                    matched_rule_name = rule.get("name")
                    break

            if not rule_id:
                return {
                    "messages": [AIMessage(content=f"❌ 未找到规则「{target_name}」，请检查规则名称是否正确。")],
                    "user_intent": UserIntent.UNKNOWN.value,
                }

            # 调用删除规则 API（传入 rule_name 用于后端校验，防止误删）
            result = await delete_rule(auth_token, rule_id, rule_name=matched_rule_name)

            if result.get("success"):
                return {
                    "messages": [AIMessage(content=f"✅ 规则「{matched_rule_name}」已删除")],
                    "user_intent": UserIntent.UNKNOWN.value,
                }
            else:
                error_msg = result.get("error", "删除失败")
                return {
                    "messages": [AIMessage(content=f"❌ 删除规则失败：{error_msg}")],
                    "user_intent": UserIntent.UNKNOWN.value,
                }
        except Exception as e:
            logger.error(f"删除规则时出错: {e}")
            return {
                "messages": [AIMessage(content=f"❌ 删除规则时发生错误：{str(e)}")],
                "user_intent": UserIntent.UNKNOWN.value,
            }
    elif intent == UserIntent.EDIT_RULE.value:
        if not rule_name:
            return {
                "messages": [AIMessage(content="❌ 请指定要编辑的规则名称，例如「调整喜马规则」。")],
                "user_intent": UserIntent.UNKNOWN.value,
            }
        # 调整/编辑规则：加载规则详情，进入编辑流程
        rule_detail = await get_rule_detail(auth_token, rule_name=rule_name)
        if not rule_detail:
            return {
                "messages": [AIMessage(content=f"❌ 未找到规则「{rule_name}」，请检查规则名称是否正确。")],
                "user_intent": UserIntent.UNKNOWN.value,
            }
        rule_template = rule_detail.get("rule_template") or {}
        rule_id = rule_detail.get("id", "")
        mappings = _rule_template_to_mappings(rule_template)
        config_items = _rule_template_to_config_items(rule_template)
        welcome_msg = f"📝 正在加载规则「{rule_name}」的编辑..."
        return {
            "messages": [AIMessage(content=welcome_msg)],
            "user_intent": UserIntent.EDIT_RULE.value,
            "editing_rule_id": rule_id,
            "editing_rule_name": rule_name,
            "editing_rule_template": rule_template,
            "confirmed_mappings": mappings,
            "suggested_mappings": mappings,
            "rule_config_items": config_items,
            "phase": ReconciliationPhase.EDIT_FIELD_MAPPING.value,
        }
    else:
        # 普通对话
        return {
            "messages": [AIMessage(content=content)],
            "user_intent": UserIntent.UNKNOWN.value,
            "uploaded_files": uploaded_files,  # 保留文件信息
        }


async def router_node(state: AgentState) -> dict:
    """轻量级编排器：委托给专门的处理器。

    优先级顺序：
    1. 跳过子图执行阶段
    2. 管理员操作（最高优先级）
    3. 认证处理（未登录用户）
    4. 意图路由（已登录用户）
    """
    # 1. 如果当前在子图执行中，不要重新识别意图，直接透传
    current_phase = state.get("phase", "")
    subgraph_phases = [
        ReconciliationPhase.FILE_ANALYSIS.value,
        ReconciliationPhase.FIELD_MAPPING.value,
        ReconciliationPhase.RULE_CONFIG.value,
        ReconciliationPhase.VALIDATION_PREVIEW.value,
        ReconciliationPhase.SAVE_RULE.value,
        ReconciliationPhase.EDIT_FIELD_MAPPING.value,
        ReconciliationPhase.EDIT_RULE_CONFIG.value,
        ReconciliationPhase.EDIT_VALIDATION_PREVIEW.value,
        ReconciliationPhase.EDIT_SAVE.value,
    ]

    # NOTE: 不再跳过意图识别，所有输入（包括 workflow 中的）都走 intent_router
    # 由 intent_router 判断用户是想继续当前 workflow 还是切换意图

    # 2. 尝试管理员处理器（最高优先级）
    admin_result = await admin_handler(state)
    if admin_result is not None:
        return admin_result

    # 3. 尝试认证处理器（第二优先级）
    auth_result = await auth_handler(state)
    if auth_result is not None:
        return auth_result

    # 4. 回退到意图路由器（已认证用户）
    return await intent_router(state)


# ══════════════════════════════════════════════════════════════════════════════
# 第3层：任务执行 — 调用 finance-mcp
# ══════════════════════════════════════════════════════════════════════════════

async def _do_start_task(
    auth_token: str,
    rule_name: str,
    files: list[str],
    guest_token: str = None,
    rule_template: dict = None,
) -> dict[str, Any]:
    """启动对账任务。
    
    Args:
        auth_token: JWT token (优先使用)
        rule_name: 规则名称（与 rule_template 二选一）
        files: 文件列表
        guest_token: 游客token (当 auth_token 为空时使用)
        rule_template: 规则模板（新建规则流程直接传入，先对账再保存）
    """
    if rule_template:
        result = await start_reconciliation(
            files=files,
            rule_template=rule_template,
            auth_token=auth_token,
            guest_token=guest_token,
        )
    else:
        result = await start_reconciliation(
            files=files,
            rule_name=rule_name,
            auth_token=auth_token,
            guest_token=guest_token,
        )
    return result


async def _do_poll(
    auth_token: str,
    task_id: str, 
    guest_token: str = None,
    progress_callback=None,
    max_polls: int = 60,  # 增加到 60 次 (60 秒)
    interval: float = 1.0  # 缩短到 1 秒
) -> dict[str, Any]:
    """轮询任务状态直到完成，并收集进度消息。
    
    Args:
        auth_token: JWT token，用于身份验证
        task_id: 任务 ID
        guest_token: 游客token（当 auth_token 为空时使用）
        progress_callback: 未使用（保留接口兼容性）
        max_polls: 最大轮询次数
        interval: 轮询间隔（秒）
    
    Returns:
        包含 status 和可选的 progress_messages 的字典
    """
    # 进度消息列表（带时间戳，用于显示）
    progress_messages_with_timing = [
        (0, "📊 正在加载数据文件 {{SPINNER}}"),
        (5, "🔍 正在分析数据结构 {{SPINNER}}"),
        (15, "⚙️  正在执行对账规则 {{SPINNER}}"),
        (30, "📈 正在生成对账结果 {{SPINNER}}"),
        (45, "✨ 即将完成 {{SPINNER}}"),
    ]
    
    collected_progress = []
    last_message_idx = -1
    
    for poll_count in range(max_polls):
        status = await get_reconciliation_status(task_id, auth_token=auth_token, guest_token=guest_token)
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
    """第3层：启动对账任务、轮询状态，展示结果。

    由于 langgraph 节点是同步的，内部使用 asyncio 调用异步函数。
    支持两种模式：1) 已保存规则（rule_name） 2) 新建规则（generated_schema，先对账再保存）
    """
    generated_schema = state.get("generated_schema")
    rule_name = state.get("selected_rule_name") or state.get("saved_rule_name")
    auth_token = state.get("auth_token", "")
    guest_token = state.get("guest_token", "")
    uploaded_files = state.get("uploaded_files", [])
    step = state.get("execution_step", TaskExecutionStep.NOT_STARTED.value)

    # ⚠️ 清除旧的对账结果，防止显示上一次的结果
    state.pop("task_id", None)
    state.pop("task_result", None)
    state.pop("task_status", None)
    
    # 新建规则流程：有 generated_schema 则直接使用，无需 rule_name
    use_rule_template = bool(generated_schema)
    display_name = rule_name or ("新规则_待确认" if use_rule_template else "")
    
    if not rule_name and not use_rule_template:
        return {
            "messages": [AIMessage(content="缺少对账规则名称，请先选择或创建一个规则。")],
            "phase": ReconciliationPhase.IDLE.value,
        }
    
    # 从 uploaded_files 中提取 file_path（带时间戳的文件路径）
    # uploaded_files 可能是对象列表（包含 file_path 和 original_filename）或字符串列表（直接是文件路径）
    files = []
    for item in uploaded_files:
        if isinstance(item, dict):
            file_path = item.get("file_path", "")
            if file_path:
                files.append(file_path)
        else:
            # 兼容旧格式（直接是文件路径字符串）
            files.append(item)
    
    # ⚠️ 新建规则流程：用户从 result_evaluation 选「不要」返回字段映射后，uploaded_files 已被清空
    # 此时 file_analyses 仍保留原始文件路径，可从其恢复
    if not files and use_rule_template:
        analyses = state.get("file_analyses", [])
        for a in analyses:
            fp = a.get("file_path", "")
            if fp:
                files.append(fp)
        if files:
            logger.info(f"从 file_analyses 恢复文件路径: {len(files)} 个")
    
    if not files:
        # 等待文件上传
        user_response = interrupt({
            "question": "请上传需要对账的文件",
            "hint": "💡 上传文件后，点击发送按钮或直接发送消息",
        })
        # ⚠️ 若用户回复的是「规则列表」等，说明想切换意图，不继续对账流程
        response_str = (user_response or "").strip().lower()
        list_rules_keywords = ("规则列表", "看看规则", "有哪些规则", "规则有哪些", "我的规则", "查看规则")
        if any(kw in response_str for kw in list_rules_keywords):
            rules = _run_async_safe(list_available_rules(auth_token or guest_token))
            if rules:
                lines = ["📋 **我的对账规则列表**\n"]
                for r in rules:
                    desc = r.get("description", "")
                    lines.append(f"• **{r['name']}**" + (f"（{desc}）" if desc else ""))
                msg = "\n".join(lines)
            else:
                msg = "📋 暂无对账规则。\n\n你可以说「创建新规则」来创建第一个对账规则。"
            return {
                "messages": [AIMessage(content=msg)],
                "phase": ReconciliationPhase.COMPLETED.value,
                "selected_rule_name": None,
            }
        # interrupt后结束节点，等待用户上传文件后重新进入
        return {
            "messages": [],
            "phase": ReconciliationPhase.TASK_EXECUTION.value,
            "execution_step": TaskExecutionStep.NOT_STARTED.value,
        }

    # ── 启动任务 ──
    if not auth_token and not guest_token:
        return {
            "messages": [AIMessage(content="❌ 缺少认证信息，请先登录或使用游客模式")],
            "phase": ReconciliationPhase.TASK_EXECUTION.value,
            "execution_step": TaskExecutionStep.NOT_STARTED.value,
        }
    
    # 使用 auth_token 或 guest_token
    logger.info(f"开始执行对账任务: rule={display_name}, use_template={use_rule_template}, files={len(files)}个")
    start_result = _run_async_safe(_do_start_task(
        auth_token if auth_token else "",
        rule_name or display_name,
        files,
        guest_token=guest_token if guest_token else None,
        rule_template=generated_schema if use_rule_template else None,
    ))

    if "error" in start_result:
        return {
            "messages": [AIMessage(content=f"❌ 启动对账任务失败：{start_result['error']}")],
            "phase": ReconciliationPhase.TASK_EXECUTION.value,
            "execution_step": TaskExecutionStep.NOT_STARTED.value,
        }

    task_id = start_result.get("task_id", "")
    
    # ── 启动成功，立即返回消息并开始轮询 ──
    messages_to_send = [
        AIMessage(content=f"🚀 对账任务已启动\n\n规则：{display_name}\n文件：{len(files)} 个\n任务ID：{task_id}\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据"),
    ]

    # ── 轮询 ──
    logger.info(f"开始轮询任务状态: task_id={task_id}")
    poll_result = _run_async_safe(_do_poll(auth_token or "", task_id, guest_token=guest_token))

    status = poll_result.get("status", "")
    logger.info(f"轮询结束: task_id={task_id}, status={status}")

    if status == "completed":
        # ── 获取结果，存入 state，交给 result_analysis 节点由 LLM 分析 ──
        try:
            logger.info(f"开始获取对账结果: task_id={task_id}")
            result = _run_async_safe(get_reconciliation_result(task_id, auth_token=auth_token or "", guest_token=guest_token))
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
        error_detail = poll_result.get("error", "")
        err_msg = f"❌ 对账任务失败（状态: {status}）"
        if error_detail:
            err_msg += f"\n\n{error_detail}"
        else:
            err_msg += "，请检查日志或重试。"
        messages_to_send.append(AIMessage(content=err_msg))
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

def result_analysis_node(state: AgentState) -> dict:
    """由 LLM 分析对账结果并生成报告（流式输出）。
    
    ⚠️ 对账完成后清除旧数据，防止下次新对账时误用旧文件
    """

    task_result = state.get("task_result")
    task_status = state.get("task_status", "")

    # 如果任务未完成，跳过分析
    if task_status != "completed" or not task_result:
        logger.info(f"跳过结果分析: task_status={task_status}")
        return {
            "phase": ReconciliationPhase.COMPLETED.value,
            "execution_step": TaskExecutionStep.DONE.value,
            "selected_rule_name": None,
        }

    # 构建结果 JSON（精简版，避免 token 过多）
    summary = task_result.get("summary", {})
    issues = task_result.get("issues", [])
    unmatched_count = summary.get("unmatched_records", len(issues))
    
    result_for_llm = {
        "summary": summary,
        "issues_count": len(issues),
        "unmatched_records": unmatched_count,  # 差异/异常总数，用于差异列表标题
        "issues": issues[:50],  # 传前50条给 LLM（按类型分组需要更多数据）
    }

    result_json = json.dumps(result_for_llm, ensure_ascii=False, indent=2, default=str)
    logger.info(f"开始 LLM 分析对账结果: summary={summary}, issues_count={len(issues)}")

    llm = get_llm()
    # 使用 replace 替代 format，避免 JSON 中的 {} 被误解析为格式化占位符
    # 仅替换占位符一次，防止 result_json 内含 {result_json} 导致递归
    prompt = RESULT_ANALYSIS_PROMPT.replace("{result_json}", result_json, 1)

    messages = [SystemMessage(content=prompt)]
    resp = llm.invoke(messages)

    return {
        "messages": [AIMessage(content=resp.content)],
        "phase": ReconciliationPhase.COMPLETED.value,
        "execution_step": TaskExecutionStep.DONE.value,
        # ⚠️ 保留 uploaded_files：用户回复「不要」仅表示不采纳/不保存规则，返回重新配置时仍需使用原文件
        "selected_rule_name": None,
    }


def ask_start_now_node(state: AgentState) -> dict:
    """询问用户是否立即开始对账。"""
    user_response = interrupt({
        "question": "是否立即开始对账？",
        "hint": "回复\"开始\"立即执行，或\"稍后\"退出",
    })

    response_str = str(user_response).strip()
    if response_str in ("开始", "是", "yes", "ok", "好", "执行", "立即开始"):
        # 保留 uploaded_files，因为在创建规则流程中已经上传过文件
        return {
            "messages": [AIMessage(content="好的，开始执行对账 {{SPINNER}}")],
            "selected_rule_name": state.get("saved_rule_name"),
            "phase": ReconciliationPhase.TASK_EXECUTION.value,
            "execution_step": TaskExecutionStep.NOT_STARTED.value,
            "uploaded_files": state.get("uploaded_files", []),
        }
    else:
        return {
            "messages": [AIMessage(content="好的，你可以随时回来执行对账。")],
            "phase": ReconciliationPhase.COMPLETED.value,
        }
