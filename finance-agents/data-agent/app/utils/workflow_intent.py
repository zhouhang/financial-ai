"""
Workflow 意图分类和上下文管理工具

用于在 workflow 执行过程中判断用户输入的意图：
- 是否想继续当前 workflow（RESUME_WORKFLOW）
- 还是想切换到其他意图（LIST_RULES, USE_EXISTING_RULE 等）
"""

import logging
from datetime import datetime
from typing import Any

from app.models import UserIntent, ReconciliationPhase

logger = logging.getLogger(__name__)


async def classify_intent_in_workflow(
    user_msg: str,
    current_phase: str,
    state: dict[str, Any]
) -> str:
    """
    在任何 workflow 上下文中分类用户意图（通用版）

    Args:
        user_msg: 用户输入的消息
        current_phase: 当前 workflow 阶段（ReconciliationPhase 值）
        state: 当前状态字典

    Returns:
        str: UserIntent 枚举值（如 "resume_workflow", "list_rules" 等）
    """
    from app.utils.llm import get_llm
    from langchain_core.messages import SystemMessage

    # ====== 第一步：关键词快速检查（优先级最高，避免 LLM 误判）======
    user_msg_lower = user_msg.lower().strip()

    logger.info(f"🔍 [DEBUG] classify_intent_in_workflow 开始: user_msg='{user_msg}', user_msg_lower='{user_msg_lower}'")

    # 高优先级关键词检查：查看规则列表
    list_rules_keywords = [
        "规则列表", "我的规则", "查看规则", "有哪些规则",
        "规则有哪些", "看看规则", "所有规则"
    ]
    logger.info(f"🔍 [DEBUG] 检查规则列表关键词: {list_rules_keywords}")
    for kw in list_rules_keywords:
        if kw in user_msg_lower:
            logger.info(f"🔍 [DEBUG] ✅ 关键词匹配成功: '{kw}' in '{user_msg_lower}'")
            logger.info(f"关键词匹配: user_msg='{user_msg[:50]}...' → LIST_RULES (关键词: {kw})")
            return UserIntent.LIST_RULES.value

    # 使用已有规则对账
    use_rule_patterns = ["用.*规则.*对账", "使用.*规则", ".*规则对账"]
    import re
    for pattern in use_rule_patterns:
        if re.search(pattern, user_msg_lower):
            logger.info(f"关键词匹配: user_msg='{user_msg[:50]}...' → USE_EXISTING_RULE (匹配: {pattern})")
            return UserIntent.USE_EXISTING_RULE.value

    # 创建新规则（特殊处理：在推荐规则阶段，"创建新规则"是继续流程的意思，不是重新开始）
    create_rule_keywords = ["创建规则", "新建规则", "重新创建", "开始创建", "创建新规则"]
    if any(kw in user_msg_lower for kw in create_rule_keywords):
        # 如果有推荐规则但未选择，说明在推荐规则阶段，"创建新规则"表示不采纳推荐
        has_recommendations = bool(state.get("recommended_rules"))
        no_selection = not state.get("selected_rule_id")
        if has_recommendations and no_selection:
            logger.info(f"关键词匹配: 推荐规则阶段（有推荐但未选择），'{user_msg[:50]}...' → RESUME_WORKFLOW（不采纳推荐）")
            return UserIntent.RESUME_WORKFLOW.value
        logger.info(f"关键词匹配: user_msg='{user_msg[:50]}...' → CREATE_NEW_RULE")
        return UserIntent.CREATE_NEW_RULE.value

    # 编辑规则
    edit_rule_keywords = ["编辑规则", "修改规则", "调整规则"]
    if any(kw in user_msg_lower for kw in edit_rule_keywords):
        logger.info(f"关键词匹配: user_msg='{user_msg[:50]}...' → EDIT_RULE")
        return UserIntent.EDIT_RULE.value

    # ====== 第二步：LLM 分类（处理模糊或复杂的输入）======
    # 定义所有 workflow 阶段的人类可读名称
    phase_name_map = {
        # 规则创建流程
        "file_analysis": "文件分析（等待上传文件或确认）",
        "field_mapping": "字段映射（等待确认映射或调整）",
        "rule_recommendation": "规则推荐（等待选择推荐规则或手动配置）",
        "rule_config": "规则配置（等待配置参数或确认）",
        "validation_preview": "预览验证（等待确认或调整）",
        "save_rule": "保存规则（等待输入规则名称）",
        "result_evaluation": "结果评估（查看对账结果）",
        # 规则编辑流程
        "edit_field_mapping": "编辑字段映射（等待调整映射）",
        "edit_rule_config": "编辑规则配置（等待调整参数）",
        "edit_validation_preview": "编辑预览验证（等待确认）",
        "edit_save": "保存编辑（等待确认保存）",
    }

    current_phase_desc = phase_name_map.get(current_phase, f"工作流阶段：{current_phase}")

    prompt = f"""你是意图分类助手。当前用户正在进行对账相关的工作流程。

**当前阶段**：{current_phase_desc}
**用户输入**：{user_msg}

请判断用户的意图（选择最匹配的一项）：

A. RESUME_WORKFLOW - 继续当前流程
   - 用户的输入是对当前阶段问题的回答
   - 例如："确认"、"没问题"、"调整字段A→B"、"上传完成"、"继续"、"保存"、"好的"

B. LIST_RULES - 查看规则列表
   - 例如："规则列表"、"我的规则"、"有哪些规则"、"查看规则"

C. USE_EXISTING_RULE - 使用已有规则对账
   - 例如："用XX规则对账"、"使用南京飞翰规则"、"开始对账"

D. CREATE_NEW_RULE - 创建新规则（或重新创建）
   - 例如："重新创建"、"新建规则"、"创建规则"、"重新开始"

E. EDIT_RULE - 编辑规则
   - 例如："编辑规则"、"修改规则"、"调整规则"

F. OTHER - 其他意图
   - 例如："帮助"、"取消"、"查看历史"等

**重要**：如果用户输入明确是对当前阶段的回应（比如确认、输入数据、调整内容），选择 A；否则选择对应的其他意图。

请仅回答：A / B / C / D / E / F（不要解释）"""

    # 调用 LLM（使用当前系统配置的模型）
    try:
        llm = get_llm()
        response = llm.invoke([SystemMessage(content=prompt)])
        choice = response.content.strip().upper()

        # 映射回意图枚举
        mapping = {
            "A": UserIntent.RESUME_WORKFLOW.value,
            "B": UserIntent.LIST_RULES.value,
            "C": UserIntent.USE_EXISTING_RULE.value,
            "D": UserIntent.CREATE_NEW_RULE.value,
            "E": UserIntent.EDIT_RULE.value,
            "F": UserIntent.UNKNOWN.value  # 使用 UNKNOWN 代替 OTHER
        }

        result = mapping.get(choice, UserIntent.RESUME_WORKFLOW.value)
        logger.info(f"意图分类: user_msg='{user_msg[:50]}...' → {result} (phase={current_phase})")
        return result

    except Exception as e:
        logger.error(f"LLM 意图分类失败: {e}")
        # 降级：默认为 RESUME_WORKFLOW，保证 workflow 不中断
        return UserIntent.RESUME_WORKFLOW.value


def save_workflow_context(state: dict[str, Any], current_phase: str):
    """
    保存当前 workflow 状态（适用于所有 workflow 阶段）

    Args:
        state: 当前状态字典（会被修改，添加 workflow_context 字段）
        current_phase: 当前 workflow 阶段
    """
    # 提取所有可能的 workflow 相关状态字段
    saved_progress = {}

    # 规则创建流程相关字段
    if state.get("file_analyses"):
        saved_progress["file_analyses"] = state["file_analyses"]
    if state.get("suggested_mappings"):
        saved_progress["suggested_mappings"] = state["suggested_mappings"]
    if state.get("confirmed_mappings"):
        saved_progress["confirmed_mappings"] = state["confirmed_mappings"]
    if state.get("rule_config_items"):
        saved_progress["rule_config_items"] = state["rule_config_items"]
    if state.get("generated_schema"):
        saved_progress["generated_schema"] = state["generated_schema"]
    if state.get("preview_result"):
        saved_progress["preview_result"] = state["preview_result"]

    # 规则推荐相关字段
    if state.get("recommended_rules"):
        saved_progress["recommended_rules"] = state["recommended_rules"]
    if state.get("selected_rule_id"):
        saved_progress["selected_rule_id"] = state["selected_rule_id"]

    # 规则编辑相关字段
    if state.get("editing_rule_id"):
        saved_progress["editing_rule_id"] = state["editing_rule_id"]
    if state.get("editing_rule_name"):
        saved_progress["editing_rule_name"] = state["editing_rule_name"]
    if state.get("editing_rule_template"):
        saved_progress["editing_rule_template"] = state["editing_rule_template"]

    # 任务执行相关字段
    if state.get("task_id"):
        saved_progress["task_id"] = state["task_id"]
    if state.get("task_status"):
        saved_progress["task_status"] = state["task_status"]

    # 上传的文件（重要，恢复时需要）
    if state.get("uploaded_files"):
        saved_progress["uploaded_files"] = state["uploaded_files"]

    state["workflow_context"] = {
        "paused_phase": current_phase,
        "paused_at": datetime.now().isoformat(),
        "saved_progress": saved_progress
    }

    logger.info(f"已保存 workflow 上下文: phase={current_phase}, fields={list(saved_progress.keys())}")


async def check_user_intent_after_interrupt(
    user_response: Any,
    current_phase: str,
    state: dict[str, Any]
) -> str:
    """
    在 interrupt 返回后检查用户意图的通用函数

    Args:
        user_response: interrupt() 的返回值
        current_phase: 当前 workflow 阶段
        state: 当前状态字典

    Returns:
        str: UserIntent 枚举值
    """
    # 获取用户输入
    user_input = str(user_response).strip() if user_response else ""

    logger.info(f"🔍 [DEBUG] interrupt 返回，检查意图: phase={current_phase}, user_input='{user_input[:100]}'")

    # 调用意图分类
    intent = await classify_intent_in_workflow(
        user_msg=user_input,
        current_phase=current_phase,
        state=state
    )

    logger.info(f"🔍 [DEBUG] 意图检测结果: {intent}")

    return intent


async def handle_intent_switch(
    intent: str,
    current_phase: str,
    state: dict[str, Any]
) -> dict:
    """
    统一处理 workflow 中的意图切换

    当用户在 workflow 中输入无关指令时，此函数会：
    1. 保存当前进度
    2. 处理常见意图（如查看规则列表）
    3. 返回适当的响应或跳转回 router

    Args:
        intent: 用户意图
        current_phase: 当前 workflow 阶段
        state: 当前状态字典

    Returns:
        dict: 状态更新字典或 Command
    """
    from langchain_core.messages import AIMessage
    from langgraph.types import Command
    from app.models import UserIntent
    from app.tools.mcp_client import call_mcp_tool

    logger.info(f"handle_intent_switch: 用户切换意图 {current_phase} → {intent}")

    # 保存当前进度
    save_workflow_context(state, current_phase)

    # 处理常见意图（避免 resume 模式下 router 消息被跳过）
    if intent == UserIntent.LIST_RULES.value:
        # 查看规则列表
        auth_token = state.get("auth_token", "")

        try:
            result = await call_mcp_tool("list_reconciliation_rules", {"token": auth_token})
            rules = result.get("rules", []) if result.get("success") else []

            if rules:
                lines = ["📋 **我的对账规则列表**\n"]
                for r in rules:
                    desc = r.get("description", "")
                    lines.append(f"• **{r['name']}**" + (f"（{desc}）" if desc else ""))
                msg = "\n".join(lines)
            else:
                msg = "📋 暂无对账规则。\n\n你可以说「创建新规则」来创建第一个对账规则。"

            # 附加 workflow 恢复提示
            if state.get("workflow_context"):
                resume_prompt = generate_resume_prompt(state["workflow_context"])
                msg += resume_prompt

            return {
                "messages": [AIMessage(content=msg)],
                "phase": "",  # 清空 phase，退出 workflow
            }
        except Exception as e:
            logger.error(f"获取规则列表失败: {e}")
            return {
                "messages": [AIMessage(content=f"❌ 获取规则列表失败: {str(e)}")],
                "phase": "",
            }

    elif intent == UserIntent.CREATE_NEW_RULE.value:
        # 创建新规则
        msg = (
            "🎯 **开始创建新的对账规则**\n\n"
            "我会引导你完成以下4个步骤：\n\n"
            "1️⃣ 上传并分析文件\n"
            "2️⃣ 确认字段映射\n"
            "3️⃣ 配置规则参数\n"
            "4️⃣ 预览并保存\n\n"
            "请先上传需要对账的文件。"
        )

        # 附加当前进度提示
        if state.get("workflow_context"):
            msg = f"💡 已保存当前进度。\n\n{msg}"

        return Command(
            update={
                "messages": [AIMessage(content=msg)],
                "phase": "",
                "user_intent": intent,
            },
            goto="router"
        )

    else:
        # 其他意图：跳转回 router 处理
        return Command(
            update={
                "phase": "",
                "user_intent": intent,
            },
            goto="router"
        )


def generate_resume_prompt(workflow_context: dict[str, Any]) -> str:
    """
    生成恢复 workflow 的提示文案

    Args:
        workflow_context: workflow_context 字典

    Returns:
        str: 格式化的恢复提示文案
    """
    phase = workflow_context.get("paused_phase", "")
    progress = workflow_context.get("saved_progress", {})

    phase_names = {
        "file_analysis": "文件分析",
        "field_mapping": "字段映射",
        "rule_recommendation": "规则推荐",
        "rule_config": "规则配置",
        "validation_preview": "预览验证",
        "save_rule": "保存规则",
        "result_evaluation": "结果评估",
        "edit_field_mapping": "编辑字段映射",
        "edit_rule_config": "编辑规则配置",
        "edit_validation_preview": "编辑预览",
        "edit_save": "保存编辑",
    }

    completed_steps = []
    if progress.get("file_analyses"):
        completed_steps.append("文件分析✅")
    if progress.get("confirmed_mappings"):
        completed_steps.append("字段映射✅")
    if progress.get("rule_config_items"):
        completed_steps.append("规则配置✅")

    steps_text = " ".join(completed_steps) if completed_steps else "初始阶段"

    phase_name = phase_names.get(phase, "配置")

    return f"""
💡 你刚才正在创建新规则（已完成：{steps_text}）
是否继续{phase_name}？
• 回复「继续」或「继续{phase_name}」返回规则创建流程
• 或直接发送新指令
"""
