"""编辑节点模块

包含编辑模式节点。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def edit_field_mapping_node(state: "AgentState") -> dict:
    """编辑规则 - 第1步：显示当前字段映射，支持修改或确认。"""
    from models import AgentState, ReconciliationPhase
    from langchain_core.messages import AIMessage
    from langgraph.types import interrupt
    from graphs.reconciliation.helpers import (
        _format_edit_field_mappings,
        _build_dummy_analyses_from_mappings,
        _adjust_field_mappings_with_llm,
        _format_operations_summary,
    )
    mappings = state.get("confirmed_mappings") or state.get("suggested_mappings", {})
    adjustment_feedback = state.get("mapping_adjustment_feedback")
    rule_name = state.get("editing_rule_name", "规则")

    mapping_display = _format_edit_field_mappings(mappings)
    if adjustment_feedback:
        question_text = f"📋 **编辑「{rule_name}」- 字段映射**\n\n{adjustment_feedback}\n\n{mapping_display}\n\n请确认或继续修改。"
    else:
        question_text = f"📋 **编辑「{rule_name}」- 字段映射**\n\n{mapping_display}\n\n请确认是否正确？回复「确认」继续，或描述需要修改的地方。"

    user_response = interrupt({
        "step": "1/3",
        "step_title": "确认字段映射",
        "question": question_text,
        "suggested_mappings": mappings,
        "hint": "• 回复「确认」继续  • 修改示例：「订单号改为XX」「添加status对应YY」「删除status」",
    })

    response_str = str(user_response).strip()
    if not response_str or (response_str.startswith("已上传") and response_str.endswith("请处理。")):
        return {"messages": [], "mapping_adjustment_feedback": None, "phase": ReconciliationPhase.EDIT_FIELD_MAPPING.value}

    response_lower = response_str.lower()
    if response_lower in ("确认", "ok", "yes", "确定", "对", "没问题", "正确"):
        return {
            "messages": [AIMessage(content="✅ 字段映射已确认。")],
            "confirmed_mappings": mappings,
            "mapping_adjustment_feedback": None,
            "phase": ReconciliationPhase.EDIT_RULE_CONFIG.value,
        }

    # 用户需要调整
    dummy_analyses = _build_dummy_analyses_from_mappings(mappings)
    adjusted_mappings, operations = _adjust_field_mappings_with_llm(mappings, response_str, dummy_analyses)
    if adjusted_mappings != mappings and operations:
        ops_summary = _format_operations_summary(operations)
        feedback = f"✅ 已更新：\n{ops_summary}"
    else:
        feedback = f"⚠️ 未能解析修改，请更具体描述。\n\n> {response_str}"

    return {
        "messages": [AIMessage(content=feedback)],
        "suggested_mappings": adjusted_mappings,
        "confirmed_mappings": adjusted_mappings,
        "mapping_adjustment_feedback": feedback,
        "phase": ReconciliationPhase.EDIT_FIELD_MAPPING.value,
    }




def edit_rule_config_node(state: "AgentState") -> dict:
    """编辑规则 - 第2步：显示当前规则配置，支持修改或确认。"""
    from models import AgentState, ReconciliationPhase
    from langchain_core.messages import AIMessage
    from langgraph.types import interrupt
    from graphs.reconciliation.helpers import (
        _get_file_names_from_rule_template,
        _format_rule_config_items,
        _find_matching_items,
    )
    from graphs.reconciliation.parsers import _parse_rule_config_json_snippet
    config_items = state.get("rule_config_items") or []
    rule_name = state.get("editing_rule_name", "规则")
    mappings = state.get("confirmed_mappings") or {}
    rule_template = state.get("editing_rule_template") or {}
    file_names = _get_file_names_from_rule_template(rule_template)

    config_display = _format_rule_config_items(config_items, file_names)
    question_text = f"⚙️ **编辑「{rule_name}」- 规则配置**\n\n{config_display}\n\n请确认是否正确？回复「确认」继续，或描述需要添加/删除的配置。"

    user_response = interrupt({
        "step": "2/3",
        "step_title": "确认规则配置",
        "question": question_text,
        "current_config_items": config_items,
        "hint": "• 回复「确认」继续  • 添加：「金额容差0.1」  • 删除：「删除金额容差」",
    })

    response_str = str(user_response).strip()
    if not response_str or (response_str.startswith("已上传") and response_str.endswith("请处理。")):
        return {"messages": [], "phase": ReconciliationPhase.EDIT_RULE_CONFIG.value}

    response_lower = response_str.lower()
    if response_lower in ("确认", "ok", "yes", "确定", "对", "没问题", "正确", "完成"):
        return {
            "messages": [AIMessage(content="✅ 规则配置已确认。")],
            "rule_config_items": config_items,
            "phase": ReconciliationPhase.EDIT_VALIDATION_PREVIEW.value,
        }

    # 用户需要调整
    parsed = _parse_rule_config_json_snippet(response_str, config_items, mappings)
    action = parsed.get("action", "unknown")
    new_config_items = config_items.copy()
    feedback_msg = ""

    if action == "add":
        new_item = {
            "json_snippet": parsed.get("json_snippet", {}),
            "description": parsed.get("description", "未知配置"),
            "user_input": response_str,
        }
        new_config_items.append(new_item)
        feedback_msg = f"✅ 已添加：{parsed.get('description', '')}\n\n> {response_str}"
    elif action == "delete":
        target = parsed.get("target", "").strip()
        for prefix in ("删除", "去掉", "移除", "删掉"):
            if target.startswith(prefix):
                target = target[len(prefix):].strip()
                break
        if target:
            matching = _find_matching_items(target, new_config_items, threshold=0.5, max_matches=1, strict_substring_only=True)
            if matching:
                for idx in sorted(matching, reverse=True):
                    del new_config_items[idx]
                feedback_msg = f"🗑️ 已删除匹配的配置\n\n> {response_str}"
            else:
                feedback_msg = f"⚠️ 未找到匹配项\n\n> {response_str}"
        else:
            feedback_msg = f"⚠️ 未指定删除目标\n\n> {response_str}"
    else:
        feedback_msg = f"⚠️ 未能解析，请更具体描述\n\n> {response_str}"

    return {
        "messages": [AIMessage(content=feedback_msg)],
        "rule_config_items": new_config_items,
        "phase": ReconciliationPhase.EDIT_RULE_CONFIG.value,
    }




def edit_validation_preview_node(state: "AgentState") -> dict:
    """编辑规则 - 第3步：预览并确认保存。以 editing_rule_template 为基准，仅更新 field_roles。"""
    import copy
    from models import AgentState, ReconciliationPhase
    from langchain_core.messages import AIMessage
    from langgraph.types import interrupt
    from graphs.reconciliation.helpers import (
        _format_edit_field_mappings,
        _get_file_names_from_rule_template,
        _format_rule_config_items,
        _merge_json_snippets,
        _validate_and_deduplicate_rules,
    )

    rule_template = state.get("editing_rule_template") or {}
    mappings = state.get("confirmed_mappings") or {}
    config_items = state.get("rule_config_items") or []
    rule_name = state.get("editing_rule_name", "规则")

    # 以原始 rule_template 为基准（完整保留用户原有配置），仅更新 field_roles
    schema = copy.deepcopy(rule_template)
    schema["description"] = rule_name
    if "data_sources" not in schema:
        schema["data_sources"] = {}
    for src in ("business", "finance"):
        if src not in schema["data_sources"]:
            schema["data_sources"][src] = {}
        schema["data_sources"][src]["field_roles"] = mappings.get(src, {})

    # 若用户编辑过规则配置（增删），从 config_items 重建；否则保留原 schema
    if config_items:
        orig_dcr = rule_template.get("data_cleaning_rules", {})
        base = {
            "version": "1.0",
            "description": rule_name,
            "data_sources": schema["data_sources"],
            "key_field_role": schema.get("key_field_role", "order_id"),
            "tolerance": {"date_format": "%Y-%m-%d", "amount_diff_max": 0.1},
            "data_cleaning_rules": {"global": orig_dcr.get("global", {})},
            "custom_validations": schema.get("custom_validations", []),
        }
        merged = _merge_json_snippets(base, config_items)
        schema["tolerance"] = merged.get("tolerance", schema.get("tolerance"))
        dcr = merged.get("data_cleaning_rules", {})
        if "global" not in dcr and "global" in orig_dcr:
            dcr["global"] = orig_dcr["global"]
        schema["data_cleaning_rules"] = dcr

    schema = _validate_and_deduplicate_rules(schema)

    mapping_display = _format_edit_field_mappings(mappings)
    file_names = _get_file_names_from_rule_template(rule_template)
    config_display = _format_rule_config_items(config_items, file_names)

    preview_text = (
        f"✅ **编辑「{rule_name}」- 预览**\n\n"
        f"🔗 **字段映射**\n\n{mapping_display}\n\n"
        f"📋 **规则配置**\n\n{config_display}\n\n"
        "确认无误后回复「保存」，将删除旧规则并保存新规则。"
    )

    user_response = interrupt({
        "step": "3/3",
        "step_title": "确认并保存",
        "question": preview_text,
        "hint": "• 回复「保存」完成编辑  • 回复「调整」返回上一步修改",
    })

    response_str = str(user_response).strip()
    if response_str in ("调整", "重新配置", "返回", "上一步"):
        return {
            "messages": [AIMessage(content="好的，返回规则配置。")],
            "phase": ReconciliationPhase.EDIT_RULE_CONFIG.value,
        }

    if response_str.lower() not in ("保存", "确认", "ok", "yes"):
        return {
            "messages": [AIMessage(content="请回复「保存」以完成编辑，或「调整」返回修改。")],
            "phase": ReconciliationPhase.EDIT_VALIDATION_PREVIEW.value,
        }

    return {
        "messages": [AIMessage(content="正在保存...")],
        "generated_schema": schema,
        "phase": ReconciliationPhase.EDIT_SAVE.value,
    }




__all__ = ["edit_field_mapping_node", "edit_rule_config_node", "edit_validation_preview_node"]
