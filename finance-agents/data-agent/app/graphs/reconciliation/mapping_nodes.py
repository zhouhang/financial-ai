"""字段映射节点模块

包含字段映射确认节点 field_mapping_node。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def field_mapping_node(state: "AgentState") -> dict:
    """第2步 (HITL)：等待用户确认或修改字段映射。
    
    ⚠️ 展平到主图后，interrupt/resume 直接恢复到此节点，无需首次进入检查。
    """
    from app.models import AgentState, ReconciliationPhase, UserIntent
    from langgraph.types import interrupt
    from langchain_core.messages import AIMessage
    from app.utils.workflow_intent import (
        check_user_intent_after_interrupt,
        check_user_intent_after_interrupt_guest,
        handle_intent_switch,
        handle_intent_switch_guest,
    )
    from app.graphs.reconciliation.helpers import (
        _format_field_mappings,
        _adjust_field_mappings_with_llm,
        _format_operations_summary,
    )

    logger.info(f"field_mapping_node 进入，当前 phase={state.get('phase', '')}")
    
    suggested = state.get("suggested_mappings", {})
    confirmed = suggested.copy() if suggested else {}
    analyses = state.get("file_analyses", [])
    
    adjustment_feedback = state.get("mapping_adjustment_feedback")
    
    mapping_display = _format_field_mappings(confirmed, analyses, bullet_style=True)
    
    if adjustment_feedback:
        question_text = f"📋 **第2步：确认字段映射**\n\n{adjustment_feedback}\n\n请确认以下字段映射是否正确：\n\n{mapping_display}"
    else:
        question_text = (
            f"📋 **第2步：确认字段映射**\n\n"
            f"请确认以下字段映射是否正确：\n\n{mapping_display}"
        )
    
    user_response = interrupt({
        "step": "2/4",
        "step_title": "确认字段映射",
        "question": question_text,
        "suggested_mappings": confirmed,
        "hint": """**映射确认 请回复：**
1. **确认** - 映射正确，进入下一步
2. **调整** - 描述需修改的字段，如「订单号改为X」「删除status」
3. **查看字段** - 查看完整列名列表""",
    })

    response_str = str(user_response).strip()

    auth_token = state.get("auth_token", "")

    if not auth_token:
        intent = await check_user_intent_after_interrupt_guest(
            user_response=user_response,
            current_phase=ReconciliationPhase.FIELD_MAPPING.value,
            state=state
        )
        if intent != UserIntent.RESUME_WORKFLOW.value:
            return await handle_intent_switch_guest(
                intent=intent,
                current_phase=ReconciliationPhase.FIELD_MAPPING.value,
                state=state,
                user_input=response_str
            )
    else:
        intent = await check_user_intent_after_interrupt(
            user_response=user_response,
            current_phase=ReconciliationPhase.FIELD_MAPPING.value,
            state=state
        )
        if intent != UserIntent.RESUME_WORKFLOW.value:
            return await handle_intent_switch(intent, ReconciliationPhase.FIELD_MAPPING.value, state, response_str)

    if not response_str or (response_str.startswith("已上传") and response_str.endswith("请处理。")):
        return {
            "messages": [],
            "mapping_adjustment_feedback": None,
            "phase": ReconciliationPhase.FIELD_MAPPING.value,
        }
    
    response_lower = response_str.lower()

    if response_lower in ("确认", "ok", "yes", "确定", "对", "没问题", "正确"):
        return {
            "messages": [AIMessage(content="✅ 字段映射已确认。接下来配置对账规则。")],
            "confirmed_mappings": confirmed,
            "mapping_adjustment_feedback": None,
            "rule_config_items": [],
            "phase": ReconciliationPhase.RULE_CONFIG.value,
        }

    logger.info(f"用户调整意见: {response_str}")
    
    adjusted_mappings, operations = _adjust_field_mappings_with_llm(confirmed, response_str, analyses)
    
    if adjusted_mappings != confirmed and operations:
        operations_summary = _format_operations_summary(operations)
        adjustment_msg = f"✅ 已根据你的调整意见更新字段映射：\n{operations_summary}"
        logger.info("字段映射已更新")
    else:
        adjustment_msg = f"⚠️ 已记录你的调整意见，但未能自动解析。请详细描述需要修改的地方：\n\n> {response_str}"
        logger.warning("字段映射未更新（LLM 解析失败或无变化）")

    return {
        "messages": [AIMessage(content=adjustment_msg)],
        "suggested_mappings": adjusted_mappings,
        "mapping_adjustment_feedback": adjustment_msg,
        "phase": ReconciliationPhase.FIELD_MAPPING.value,
    }


__all__ = ["field_mapping_node"]
