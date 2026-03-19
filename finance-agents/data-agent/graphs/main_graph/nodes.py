"""主图节点函数模块。"""

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
    UserIntent,
)
from tools.mcp_client import (
    list_available_rules,
    get_rule_detail,
    auth_login,
    auth_register,
    delete_rule,
    admin_login,
    create_company,
    create_department,
    list_companies,
    get_admin_view,
    list_companies_public,
    list_departments_public,
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
你是 Tally，专业的智能财务助手。

你可以帮助用户：
1. 引导用户登录后使用数据整理或对账执行能力
2. 回答用户关于系统功能和使用方式的问题

请根据用户的意图判断下一步操作：
- 如果用户明确想登录，回复 JSON: {{"intent": "show_login_form"}}
- 如果用户明确想注册，回复 JSON: {{"intent": "show_register_form"}}
- 如果用户在**闲聊或一般对话**（如打招呼、说心情、随便聊），**正常简短回复即可**，不要主动介绍自己或列举功能
- 仅当用户**明确要求**自我介绍、介绍功能（如「你是谁」「介绍一下」「你能做什么」「帮助」）时，才用完整格式介绍你是 Tally 及你的功能

⚠️ 严格禁止（违反此规则是严重错误）：
- **禁止**模拟或伪造任何文件处理结果
- 系统能力依赖真实后台执行，你只负责判断意图并返回 JSON 或正常回复

重要：
- 所有内容必须在同一条消息中完成，不要分多次回复
- 不要使用感叹号（！或!）开头
- 回复言简意赅，善用 Markdown 排版（如 **加粗**、- 列表、标题等）增强可读性
"""

SYSTEM_PROMPT = """\
你是 Tally，专业的智能财务助手。你的职责是帮助用户完成数据整理和对账执行工作。
当前登录用户：{username}

你可以做以下事情：
1. 查看可用规则列表
2. 删除规则
3. 执行数据整理任务
4. 执行对账任务
5. 回答一般使用问题

当前已有规则包括：
{available_rules}

请根据用户的意图判断下一步操作：
- 如果用户想**查看规则列表**（如“我的规则列表”、“看看有哪些规则”、“规则列表”），回复 JSON: {{"intent": "list_rules"}}
- 如果用户想删除规则，回复 JSON: {{"intent": "delete_rule", "rule_name": "规则名称"}}
- 如果用户想**执行数据整理**（如"数据整理"、"核算整理"、"使用核算规则"），回复 JSON: {{"intent": "proc", "rule_code": "recognition"}}
- 如果用户想**执行对账**（如“开始对账”、“执行对账”、“用XX规则对账”），回复 JSON: {{"intent": "recon", "rule_code": "规则编码"}}
- 如果用户在闲聊或一般对话（如打招呼、夸赞、闲聊），**正常简短回复即可**，不要主动介绍自己或列举规则。
- 仅当用户**明确要求**自我介绍、介绍功能、展示规则列表（如「介绍一下你自己」「你能做什么」「有哪些规则」「看看规则」）时，才用完整格式回复：
  1. 用「你好，{username}！我是 Tally」开头
  2. 简要介绍你能做的事
  3. 说明当前已有规则
  4. 询问用户需要什么帮助
  5. 回复言简意赅，善用 Markdown 排版（**加粗**、- 列表等）

注意：
- 只在明确判断意图时才返回 JSON，否则正常对话
- 删除规则时，必须从用户输入中提取准确的规则名称
- 对账和数据整理都依赖具体规则；如果无法确认规则编码，不要编造
- 只返回一条消息，不要分多次回复

⚠️ 严格禁止（违反此规则是严重错误）：
- **禁止**模拟或伪造任何文件分析结果、整理结果或对账结果
- **禁止**模拟或伪造规则数据
- 文件处理由真实后台系统完成，你只负责判断意图并返回 JSON
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

    if intent == "show_login_form":
        # 用户要登录，统一提示点击右上角登录按钮
        return {"messages": [AIMessage(content="💡 请点击右上角登录按钮进行登录。")]}
    if intent == "show_register_form":
        # 用户要注册，统一提示点击右上角登录按钮切换至注册
        return {"messages": [AIMessage(content="💡 请点击右上角登录按钮，切换至注册进行注册。")]}

    # LLM 正常回复（引导用户）
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
    # ====== 新增：前端显式选择任务类型时，直接路由（跳过 LLM 意图识别）======
    selected_task_code = state.get("selected_task_code", "")
    if selected_task_code == UserIntent.PROC.value:
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
            logger.warning(f"[intent_router] 前端选择 {UserIntent.PROC.value} 但未选择 rule_code")
            return {
                "messages": [AIMessage(content="❌ 请先选择要使用的整理规则。\n\n请在左侧规则列表中选择一个规则后再开始。")],
                "user_intent": UserIntent.UNKNOWN.value,
            }

        logger.info(f"[intent_router] 前端显式选择 {UserIntent.PROC.value}，直接路由: rule_code={rule_code}, rule_name={rule_name}, files={len(uploaded)}, user_msg='{last_user_input[:50]}'")

        # 从 state 获取 file_rule_code（必须在 AgentState schema 中声明）
        file_rule_code = state.get("file_rule_code") or ""

        return {
            "messages": [HumanMessage(content=last_user_input)] if last_user_input else [],
            "uploaded": uploaded,
            "user_intent": UserIntent.PROC.value,
            "selected_rule_code": rule_code,
            "selected_rule_name": rule_name,
            # 构建完整的 proc_ctx，包含 file_rule_code
            "proc_ctx": {
                **(state.get("proc_ctx") or {}),
                "rule_code": rule_code,
                "rule_name": rule_name,
                "file_rule_code": file_rule_code,
            },
        }

    if selected_task_code == UserIntent.RECON.value:
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
            logger.warning(f"[intent_router] 前端选择 {UserIntent.RECON.value} 但未选择 rule_code")
            return {
                "messages": [AIMessage(content="❌ 请先选择要使用的对账规则。\n\n请在左侧规则列表中选择一个规则后再开始。")],
                "user_intent": UserIntent.UNKNOWN.value,
            }

        logger.info(f"[intent_router] 前端显式选择 {UserIntent.RECON.value}，直接路由: rule_code={rule_code}, rule_name={rule_name}, files={len(uploaded)}, user_msg='{last_user_input[:50]}'")

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

        # 从 state 获取 file_rule_code（必须在 AgentState schema 中声明）
        file_rule_code = state.get("file_rule_code") or ""

        return {
            "messages": [AIMessage(content=welcome_msg)],
            "user_intent": UserIntent.RECON.value,
            "selected_rule_code": rule_code,
            "selected_rule_name": rule_name,
            # 构建完整的 recon_ctx，包含 file_rule_code
            "recon_ctx": {
                **(state.get("recon_ctx") or {}),
                "rule_code": rule_code,
                "rule_name": rule_name,
                "file_rule_code": file_rule_code,
            },
        }

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

    rule_code = parsed.get("rule_code", "") if "parsed" in locals() else ""

    last_user_msg = (messages[-1].content if messages and hasattr(messages[-1], "content") else "") or ""
    last_user_msg_lower = last_user_msg.lower().strip()
    list_rules_keywords = ("规则列表", "看看规则", "有哪些规则", "规则有哪些", "我的规则", "查看规则", "可用规则")
    if any(kw in last_user_msg_lower for kw in list_rules_keywords):
        intent = UserIntent.LIST_RULES.value
        rule_name = ""
        logger.info(f"router: 用户说「{last_user_msg[:30]}...」识别为 list_rules")

    delete_match = re.search(r"^\s*(?:删除|删掉)\s*([^\s,，。]+?)(?:\s*规则)?\s*$", last_user_msg)
    if delete_match:
        extracted_name = (delete_match.group(1) or "").strip()
        if extracted_name:
            intent = UserIntent.DELETE_RULE.value
            rule_name = extracted_name
            logger.info(f"router: 删除关键词兜底生效，规则名='{rule_name}'")

    uploaded_files = state.get("uploaded_files", [])

    if intent == UserIntent.LIST_RULES.value:
        if rules:
            lines = ["📋 **我的对账规则列表**\n"]
            for r in rules:
                lines.append(f"• **{r['name']}**")
            msg = "\n".join(lines)
        else:
            msg = "📋 暂无可用规则。"

        return {
            "messages": [AIMessage(content=msg)],
            "user_intent": UserIntent.UNKNOWN.value,
        }
    if intent == UserIntent.DELETE_RULE.value and rule_name:
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
    if intent == UserIntent.PROC.value:
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
            logger.warning(f"[intent_router] LLM 识别为 PROC 但未提供 rule_code")
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
        
        logger.info(f"[intent_router] PROC: rule_code={rule_code}, rule_name={rule_name}, files={len(uploaded)}")
        
        # 保留 state 中已有的 proc_ctx（例如 file_rule_code），只更新 rule_code/rule_name
        existing_proc_ctx = state.get("proc_ctx") or {}
        existing_proc_ctx.update({"rule_code": rule_code, "rule_name": rule_name})
        
        return {
            "messages": [AIMessage(content=welcome_msg)],
            "user_intent": UserIntent.PROC.value,
            "selected_rule_code": rule_code,
            "selected_rule_name": rule_name,
            "proc_ctx": existing_proc_ctx,
        }
    if intent == UserIntent.RECON.value:
        rule_code = state.get("selected_rule_code") or rule_code
        rule_name = state.get("selected_rule_name") or rule_name

        if not rule_code:
            logger.warning("[intent_router] LLM 识别为 RECON 但未提供 rule_code")
            return {
                "messages": [AIMessage(content="❌ 请先选择要使用的对账规则。")],
                "user_intent": UserIntent.UNKNOWN.value,
            }

        rule_display = f"{rule_name}（{rule_code}）" if rule_name else rule_code
        if not uploaded_files:
            welcome_msg = (
                "📊 **开始对账执行任务**\n\n"
                f"已选择规则：**{rule_display}**\n\n"
                "请先上传需要对账的数据文件（Excel 或 CSV 格式）。"
            )
        else:
            welcome_msg = (
                "📊 **开始对账执行任务**\n\n"
                f"已选择规则：**{rule_display}**\n"
                f"已上传文件：{len(uploaded_files)} 个\n\n"
                "正在校验文件并加载规则..."
            )

        return {
            "messages": [AIMessage(content=welcome_msg)],
            "user_intent": UserIntent.RECON.value,
            "selected_rule_code": rule_code,
            "selected_rule_name": rule_name,
            "recon_ctx": {
                **(state.get("recon_ctx") or {}),
                "rule_code": rule_code,
                "rule_name": rule_name,
                "file_rule_code": state.get("file_rule_code") or "",
            },
        }

    # 普通对话
    return {
        "messages": [AIMessage(content=content)],
        "user_intent": UserIntent.UNKNOWN.value,
        "uploaded_files": uploaded_files,
    }


async def router_node(state: AgentState) -> dict:
    """轻量级编排器：委托给专门的处理器。

    优先级顺序：
    1. 跳过子图执行阶段
    2. 管理员操作（最高优先级）
    3. 认证处理（未登录用户）
    4. 意图路由（已登录用户）
    """
    # 1. 尝试管理员处理器（最高优先级）
    admin_result = await admin_handler(state)
    if admin_result is not None:
        return admin_result

    # 2. 尝试认证处理器（第二优先级）
    auth_result = await auth_handler(state)
    if auth_result is not None:
        return auth_result

    # 3. 回退到意图路由器（已认证用户）
    return await intent_router(state)
