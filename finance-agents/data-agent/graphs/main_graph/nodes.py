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

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from utils.llm import get_llm
from models import (
    AgentState,
    ReconciliationPhase,
    TaskExecutionStep,
    UserIntent,
)
from graphs.reconciliation import (
    _rule_template_to_mappings,
    _rule_template_to_config_items,
)
from tools.mcp_client import (
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
你是 Tally，专业的智能对账助手。你的职责是帮助用户完成数据对比对账和数据整理工作。
当前登录用户：{username}

你可以做以下事情：
1. 使用已有的对账规则快速执行对账
2. 引导用户创建新的对账规则
3. 调整/编辑已有规则（如修改字段映射、规则配置等）
4. 删除对账规则
5. 查看规则列表
6. 帮助用户理解对账结果
7. 执行数据整理任务（如核算整理规则）

当前已有的对账规则包括：
{available_rules}

请根据用户的意图判断下一步操作：
- 如果用户想**查看规则列表**（如“我的规则列表”、“看看有哪些规则”、“规则列表”），回复 JSON: {{"intent": "list_rules"}}
- 如果用户想**使用已有规则对账**（如“用XX规则对账”、“执行XX对账”），回复 JSON: {{"intent": "use_existing_rule", "rule_name": "规则名称"}}
- 如果用户想**调整/编辑已有规则**（如“调整XX规则”、“编辑XX”、“修改XX规则”），回复 JSON: {{"intent": "edit_rule", "rule_name": "规则名称"}}
- 如果用户想创建新规则，回复 JSON: {{"intent": "create_new_rule"}}
- 如果用户想删除规则，回复 JSON: {{"intent": "delete_rule", "rule_name": "规则名称"}}
- 如果用户想**执行数据整理**（如"数据整理"、"核算整理"、"使用核算规则"），回复 JSON: {{"intent": "agent-recog", "rule_code": "recognition"}}
- 如果用户在闲聊或一般对话（如打招呼、夸赞、闲聊），**正常简短回复即可**，不要主动介绍自己或列举规则。
- 仅当用户**明确要求**自我介绍、介绍功能、展示规则列表（如「介绍一下你自己」「你能做什么」「有哪些规则」「看看规则」）时，才用完整格式回复：
  1. 用「你好，{username}！我是 Tally」开头
  2. 简要介绍你能做的事
  3. 说明当前已有规则
  4. 询问用户需要什么帮助
  5. 回复言简意赅，善用 Markdown 排版（**加粗**、- 列表等）

注意：
- **查看规则列表**与**使用规则对账**要严格区分：说“规则列表”、“看看规则”、“有哪些规则”→ list_rules；说“用XX对账”、“执行对账”→ use_existing_rule
- **调整/编辑规则**与**使用规则对账**要严格区分：说“调整XX”、“编辑XX”、“修改XX规则”→ edit_rule；说“用XX对账”、“执行对账”→ use_existing_rule
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
5. 对账概览和异常明细中，必须使用 summary.business_file 和 summary.finance_file 的真实文件名，不要使用「文件1」「文件2」「业务文件」「财务文件」等占位符
6. 【关键】差异/异常的总条数必须使用 summary.unmatched_records（或 issues_count），切勿使用 total_business_records 或 total_finance_records。例如差异列表标题应写「差异 (10条)」而非「差异 (985条)」

示例格式（假设 summary.business_file=销售数据.xlsx, summary.finance_file=财务报表.xlsx）：

✅ 对账完成

**对账概览**
- **销售数据.xlsx:** (100条)
- **财务报表.xlsx:** (98条)
- **匹配成功:** 95条
- **异常记录:** 5条
- **匹配率:** 95%

异常明细（必须用表格展示，表头为「异常订单号」「异常原因」，每行一条数据，异常原因中用真实文件名）：

| 异常订单号 | 异常原因 |
|-----------|----------|
| 订单A001 | 销售数据.xlsx存在，财务报表.xlsx无此订单记录 |
| 订单A002 | 销售数据.xlsx存在，财务报表.xlsx无此订单记录 |
| 订单B001 | 销售数据.xlsx与财务报表.xlsx金额差异（差异0.5元） |
| 订单B002 | 销售数据.xlsx与财务报表.xlsx金额差异（差异1.2元） |

注意：
- 异常明细必须使用 Markdown 表格，表头固定为「异常订单号」「异常原因」
- 每行一条异常记录，从 issues 中按 order_id 和 detail 提取
- 若 issues 的 detail 中有「文件1」「文件2」，必须替换为 summary.business_file 和 summary.finance_file 的真实文件名
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
        from utils.workflow_intent import classify_intent_in_workflow_guest

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
                from utils.workflow_intent import save_workflow_context
                save_workflow_context(state, current_phase)
                return {
                    "messages": [AIMessage(content="💡 请点击右上角登录按钮进行登录。")],
                    "phase": "",  # 清空 phase，退出 workflow
                }
            elif intent == "CANCEL":
                # 游客想取消/退出 workflow
                logger.info(f"auth_handler [游客]: 用户想取消 workflow")
                # 删除已上传的文件
                from graphs.reconciliation.helpers import delete_uploaded_files
                await delete_uploaded_files(state.get("uploaded_files", []), state.get("auth_token", ""))

                # 清除所有 workflow 相关状态，确保不会继续执行
                return {
                    "messages": [AIMessage(content="已取消当前操作。\n\n你可以说「对账」开始新的对账，或者点击右上角按钮登录。")],
                    "phase": "",  # 清空 phase，退出 workflow
                    "user_intent": UserIntent.UNKNOWN.value,
                    "uploaded_files": [],  # 清除上传的文件
                    "file_analyses": [],  # 清除文件分析
                    "workflow_context": {},  # 清除 workflow 上下文
                }
            elif intent == "OTHER":
                # 用户的闲聊/无关内容 - 退出 workflow，让用户重新开始
                logger.info(f"auth_handler [游客]: 用户闲聊/无关内容，退出 workflow")

                # 删除已上传的文件
                from graphs.reconciliation.helpers import delete_uploaded_files
                await delete_uploaded_files(state.get("uploaded_files", []), state.get("auth_token", ""))

                return {
                    "messages": [AIMessage(content="好的，流程已暂停。\n\n你可以说「对账」开始新的对账，或者点击右上角按钮登录。")],
                    "phase": "",  # 清空 phase，退出 workflow
                    "user_intent": UserIntent.UNKNOWN.value,
                    "uploaded_files": [],
                    "file_analyses": [],
                    "workflow_context": {},
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

    # ====== 检查是否已经在对账流程中（避免重复返回 JSON）======
    current_user_intent = state.get("user_intent", "")

    # 如果已经在 guest_reconciliation 流程中，不要再调用 LLM 识别意图
    # 而是直接提示用户上传文件或提供帮助
    if current_user_intent == "guest_reconciliation":
        uploaded = state.get("uploaded_files", [])
        if not uploaded:
            # 已经在对账流程中，但还没有文件，友好提示
            logger.info(f"[auth_handler] 用户已在 guest_reconciliation 流程中，提示上传文件")
            return {
                "messages": [AIMessage(content="请上传需要对账的两个文件（Excel 或 CSV 格式）。\n\n上传后我会为您分析并推荐合适的对账规则。")],
                "user_intent": "guest_reconciliation",  # 保持不变
            }

    # 使用 LLM 生成回复
    llm = get_llm()
    resp = llm.invoke([SystemMessage(content=SYSTEM_PROMPT_NOT_LOGGED_IN)] + messages)
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
    # ====== 新增：前端显式选择数字员工时，直接路由（跳过 LLM 意图识别）======
    selected_employee_code = state.get("selected_employee_code", "")
    if selected_employee_code == UserIntent.AGENT_RECOG.value:
        # 用户选择了"数据整理员工"，直接进入 proc 子图
        rule_code = state.get("selected_rule_code") or ""
        rule_name = state.get("selected_rule_name") or ""
        uploaded = state.get("uploaded_files", [])
        # 取用户实际输入的消息内容，而非固定 welcome_msg
        _msgs = list(state.get("messages", []))
        last_user_input = (
            _msgs[-1].content
            if _msgs and hasattr(_msgs[-1], "content")
            else ""
        ) or ""

        # ⚠️ 必须选择 rule_code，不能默认
        if not rule_code:
            logger.warning(f"[intent_router] 前端选择 {UserIntent.AGENT_RECOG.value} 但未选择 rule_code")
            return {
                "messages": [AIMessage(content="❌ 请先选择要使用的整理规则。\n\n请在左侧规则列表中选择一个规则后再开始。")],
                "user_intent": UserIntent.UNKNOWN.value,
            }

        logger.info(f"[intent_router] 前端显式选择 {UserIntent.AGENT_RECOG.value}，直接路由: rule_code={rule_code}, rule_name={rule_name}, files={len(uploaded)}, user_msg='{last_user_input[:50]}'")
        
        # 保留 state 中已有的 proc_ctx（例如 file_rule_code），只更新 rule_code/rule_name
        existing_proc_ctx = state.get("proc_ctx") or {}
        existing_proc_ctx.update({"rule_code": rule_code, "rule_name": rule_name})
        
        return {
            "messages": [HumanMessage(content=last_user_input)] if last_user_input else [],
            "uploaded": uploaded,
            "user_intent": UserIntent.AGENT_RECOG.value,
            "selected_rule_code": rule_code,
            "selected_rule_name": rule_name,
            "proc_ctx": existing_proc_ctx,
        }

    if selected_employee_code == UserIntent.AGENT_RECON.value:
        # 用户选择了"对账执行员工"，直接进入 recon 子图
        rule_code = state.get("selected_rule_code") or ""
        rule_name = state.get("selected_rule_name") or ""
        uploaded = state.get("uploaded_files", [])
        # 取用户实际输入的消息内容
        _msgs = list(state.get("messages", []))
        last_user_input = (
            _msgs[-1].content
            if _msgs and hasattr(_msgs[-1], "content")
            else ""
        ) or ""

        # ⚠️ 必须选择 rule_code
        if not rule_code:
            logger.warning(f"[intent_router] 前端选择 {UserIntent.AGENT_RECON.value} 但未选择 rule_code")
            return {
                "messages": [AIMessage(content="❌ 请先选择要使用的对账规则。\n\n请在左侧规则列表中选择一个规则后再开始。")],
                "user_intent": UserIntent.UNKNOWN.value,
            }

        logger.info(f"[intent_router] 前端显式选择 {UserIntent.AGENT_RECON.value}，直接路由: rule_code={rule_code}, rule_name={rule_name}, files={len(uploaded)}, user_msg='{last_user_input[:50]}'")

        # 构建规则展示文本
        rule_display = f"{rule_name}（{rule_code}）" if rule_name else rule_code

        # 检查是否有上传的文件
        if not uploaded:
            welcome_msg = (
                "📊 **开始对账执行任务**\n\n"
                f"已选择规则：**{rule_display}**\n\n"
                "请先上传需要对账的数据文件（Excel 或 CSV 格式）。"
            )
        else:
            welcome_msg = (
                "📊 **开始对账执行任务**\n\n"
                f"已选择规则：**{rule_display}**\n"
                f"已上传文件：{len(uploaded)} 个\n\n"
                "正在校验文件并加载规则..."
            )

        return {
            "messages": [AIMessage(content=welcome_msg)],
            "user_intent": UserIntent.AGENT_RECON.value,
            "selected_rule_code": rule_code,
            "selected_rule_name": rule_name,
            # 保留 state 中已有的 recon_ctx（例如 file_rule_code），只更新 rule_code/rule_name
            "recon_ctx": {**(state.get("recon_ctx") or {}), "rule_code": rule_code, "rule_name": rule_name},
        }

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
        from utils.workflow_intent import classify_intent_in_workflow, save_workflow_context

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
                # ⚠️ 同时清空工作流上传的文件和分析结果，防止退出规则创建后使用已有规则对账时误用这些文件
                return {
                    "phase": "",
                    "user_intent": intent,
                    "messages": [],
                    "uploaded_files": [],
                    "file_analyses": [],
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
    logger.info(f"[DEBUG] list_available_rules 返回 {len(rules)} 条规则: {[r.get('name') for r in rules]}")
    rules_text = "\n".join([f"• {r['name']}" for r in rules]) if rules else "暂无已有规则"

    username = current_user.get("username", "用户")
    # 使用 replace 替代 format，避免规则名称/描述中的 {} 被误解析
    system_msg = SYSTEM_PROMPT.replace("{username}", username).replace("{available_rules}", rules_text)

    llm = get_llm()
    messages = list(state.get("messages", []))
    resp = llm.invoke([SystemMessage(content=system_msg)] + messages)

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

    # ⚠️ 删除规则兜底：不依赖 LLM JSON，用户明确以“删除/删掉”开头时强制识别为 delete_rule
    delete_match = re.search(r"^\s*(?:删除|删掉)\s*([^\s,，。]+?)(?:\s*规则)?\s*$", last_user_msg)
    if delete_match:
        extracted_name = (delete_match.group(1) or "").strip()
        if extracted_name:
            intent = UserIntent.DELETE_RULE.value
            rule_name = extracted_name
            logger.info(f"router: 删除关键词兜底生效，规则名='{rule_name}'")

    # ⚠️ 编辑规则兜底：用户明确以“编辑/修改/调整”开头时，直接识别为 edit_rule（不依赖 LLM JSON）
    edit_match = re.search(r"^\s*(?:编辑|修改|调整)\s*([^\s,，。]+?)(?:\s*规则)?\s*$", last_user_msg)
    if edit_match:
        extracted_name = (edit_match.group(1) or "").strip()
        if extracted_name:
            # 规则名优先使用精确提取；若提取值不在规则列表，尝试用包含关系做一次归一化
            normalized_name = extracted_name
            if rules and not any(r.get("name") == extracted_name for r in rules):
                for r in rules:
                    name = r.get("name", "")
                    if extracted_name in name or name in extracted_name:
                        normalized_name = name
                        break
            intent = UserIntent.EDIT_RULE.value
            rule_name = normalized_name
            logger.info(f"router: 编辑关键词兜底生效，规则名='{rule_name}'")

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
                lines.append(f"• **{r['name']}**")
            msg = "\n".join(lines)
        else:
            msg = "📋 暂无对账规则。\n\n你可以说「创建新规则」来创建第一个对账规则。"

        # ====== 新增：附加 workflow 恢复提示 ======
        if state.get("workflow_context"):
            from utils.workflow_intent import generate_resume_prompt
            resume_prompt = generate_resume_prompt(state["workflow_context"])
            msg += resume_prompt

        return {
            "messages": [AIMessage(content=msg)],
            "user_intent": UserIntent.UNKNOWN.value,
        }
    elif intent == UserIntent.USE_EXISTING_RULE.value and rule_name:
        # ⚠️ 修复：切换意图时不要清空 uploaded_files，否则会丢失用户刚上传的新文件
        # （用户换文件后说「使用南京飞翰对账」时，state 已通过 input 合并了新文件，清空会导致仍用旧结果）
        # 先进入 file_analysis 校验文件格式，通过后再执行对账
        msg = f"好的，将使用规则「{rule_name}」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）"
        return {
            "messages": [AIMessage(content=msg)],
            "user_intent": intent,
            "selected_rule_name": rule_name,
            "phase": ReconciliationPhase.FILE_ANALYSIS.value,
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

            logger.info(f"[DEBUG] 删除规则: target_name='{target_name}', rules列表={[r.get('name') for r in rules]}")

            # 先在规则列表中查找
            rule_id = None
            matched_rule_name = None
            for rule in rules:
                if rule.get("name") == target_name:
                    rule_id = rule.get("id")
                    matched_rule_name = rule.get("name")
                    break

            if not rule_id:
                # ⚠️ 改进：即使列表中没找到，也尝试通过规则名查询并删除（防止缓存问题导致删除失败）
                logger.warning(f"[DEBUG] 规则列表中未找到「{target_name}」，尝试通过API查询")
                rule_detail = await get_rule_detail(auth_token, rule_name=target_name)
                if rule_detail and rule_detail.get("id"):
                    rule_id = rule_detail.get("id")
                    matched_rule_name = rule_detail.get("name")
                    logger.info(f"[DEBUG] API查询成功找到规则: id={rule_id}, name={matched_rule_name}")
                else:
                    logger.error(f"[DEBUG] API查询也未找到规则「{target_name}」")
                    return {
                        "messages": [AIMessage(content=f"❌ 未找到规则「{target_name}」，请检查规则名称是否正确。")],
                        "user_intent": UserIntent.UNKNOWN.value,
                    }

            # 调用删除规则 API（传入 rule_name 用于后端校验，防止误删）
            result = await delete_rule(auth_token, rule_id, rule_name=matched_rule_name)

            if result.get("success"):
                # 删除后二次校验，避免“看起来删了但列表仍显示”的假象
                refreshed_rules = await list_available_rules(auth_token)
                still_exists = any(str(r.get("id")) == str(rule_id) for r in refreshed_rules)
                if still_exists:
                    logger.warning(f"[DEBUG] 删除后校验仍存在: id={rule_id}, name={matched_rule_name}")
                    return {
                        "messages": [AIMessage(content=f"⚠️ 规则「{matched_rule_name}」删除请求已提交，但列表仍显示，请稍后刷新重试。")],
                        "user_intent": UserIntent.UNKNOWN.value,
                    }
                return {
                    "messages": [AIMessage(content=f"✅ 规则「{matched_rule_name}」已删除")],
                    "user_intent": UserIntent.UNKNOWN.value,
                    # 清空编辑流程相关状态，防止重新登录后恢复编辑该规则导致其被重新创建
                    "phase": ReconciliationPhase.COMPLETED.value,
                    "editing_rule_id": None,
                    "editing_rule_name": None,
                    "editing_rule_template": None,
                    "generated_schema": None,
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
    elif intent == UserIntent.AGENT_RECOG.value:
        # 数据整理意图：进入 proc 子图
        # 优先从 state 中读取前端传递的 rule_code，其次从 LLM 解析
        rule_code = state.get("selected_rule_code") or ""
        rule_name = state.get("selected_rule_name") or ""

        # 尝试从 LLM 解析的 JSON 中提取 rule_code
        if not rule_code:
            try:
                rule_code = parsed.get("rule_code", "")
            except:
                pass

        # ⚠️ 必须选择 rule_code，不能默认
        if not rule_code:
            logger.warning(f"[intent_router] LLM 识别为 AGENT_RECOG 但未提供 rule_code")
            return {
                "messages": [AIMessage(content="❌ 请指定要使用的整理规则。\n\n例如：「使用 recognition 规则整理数据」或在左侧规则列表中选择一个规则。")],
                "user_intent": UserIntent.UNKNOWN.value,
            }

        # 构建规则展示文本
        rule_display = f"{rule_name}（{rule_code}）" if rule_name else rule_code

        # 检查是否有上传的文件
        uploaded = state.get("uploaded_files", [])
        if not uploaded:
            welcome_msg = (
                "📊 **开始数据整理任务**\n\n"
                f"已选择规则：**{rule_display}**\n\n"
                "请先上传需要整理的数据文件（Excel 或 CSV 格式）。"
            )
        else:
            welcome_msg = (
                "📊 **开始数据整理任务**\n\n"
                f"已选择规则：**{rule_display}**\n"
                f"已上传文件：{len(uploaded)} 个\n\n"
                "正在校验文件并加载规则..."
            )
        
        logger.info(f"[intent_router] AGENT_RECOG: rule_code={rule_code}, rule_name={rule_name}, files={len(uploaded)}")
        
        # 保留 state 中已有的 proc_ctx（例如 file_rule_code），只更新 rule_code/rule_name
        existing_proc_ctx = state.get("proc_ctx") or {}
        existing_proc_ctx.update({"rule_code": rule_code, "rule_name": rule_name})
        
        return {
            "messages": [AIMessage(content=welcome_msg)],
            "user_intent": UserIntent.AGENT_RECOG.value,
            "selected_rule_code": rule_code,
            "selected_rule_name": rule_name,
            "proc_ctx": existing_proc_ctx,
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
# 第3层：任务执行（兼容导出）
# ══════════════════════════════════════════════════════════════════════════════

# 执行/结果相关节点已物理迁移到 reconciliation/execution_nodes.py
# 这里保留同名导出以兼容旧引用路径。
from graphs.reconciliation.execution_nodes import (
    _do_start_task,
    _do_poll,
    _run_async_safe,
    task_execution_node,
    result_analysis_node,
    ask_start_now_node,
)
