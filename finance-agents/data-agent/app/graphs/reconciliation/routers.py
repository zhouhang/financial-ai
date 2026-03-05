"""对账路由函数和子图构建模块。"""

from __future__ import annotations

import logging

from langgraph.graph import END, StateGraph

from app.models import AgentState, ReconciliationPhase, UserIntent
from .nodes import (
    entry_router_node,
    file_analysis_node,
    field_mapping_node,
    rule_recommendation_node,
    rule_config_node,
    validation_preview_node,
    save_rule_node,
    result_evaluation_node,
    edit_field_mapping_node,
    edit_rule_config_node,
    edit_validation_preview_node,
    edit_save_node,
)

logger = logging.getLogger(__name__)


# ── 路由函数 ─────────────────────────────────────────────────────────────────

def route_after_file_analysis(state: AgentState) -> str:
    """文件分析后路由。"""
    phase = state.get("phase", "")
    if not phase:
        return END

    analyses = state.get("file_analyses", [])
    if analyses:
        if state.get("user_intent") == UserIntent.USE_EXISTING_RULE.value:
            logger.info("文件验证通过，使用规则流程 -> task_execution")
            return "task_execution"
        return "rule_recommendation"

    uploaded_files = state.get("uploaded_files", [])
    if uploaded_files:
        logger.info("文件验证失败，循环回 file_analysis 重新验证")
        return "file_analysis"

    return END


def route_after_field_mapping(state: AgentState) -> str:
    phase = state.get("phase", "")
    if not phase:
        return END
    if phase == ReconciliationPhase.FIELD_MAPPING.value:
        return "field_mapping"
    return "rule_config"


def route_after_rule_recommendation(state: AgentState) -> str:
    using_recommended = state.get("using_recommended_rule", False)
    selected_rule_id = state.get("selected_rule_id")
    phase = state.get("phase", "")

    logger.info(
        "route_after_rule_recommendation: phase=%s, using_recommended=%s, selected_rule_id=%s",
        phase,
        using_recommended,
        selected_rule_id,
    )

    if not phase:
        return END

    if phase == ReconciliationPhase.RULE_RECOMMENDATION.value:
        return "rule_recommendation"

    if using_recommended and selected_rule_id:
        return "task_execution"

    if phase == ReconciliationPhase.FIELD_MAPPING.value:
        return "field_mapping"

    if phase == ReconciliationPhase.TASK_EXECUTION.value:
        return "task_execution"

    return "field_mapping"


def route_after_rule_config(state: AgentState) -> str:
    phase = state.get("phase", "")
    if not phase:
        return END
    if phase == ReconciliationPhase.RULE_CONFIG.value:
        return "rule_config"
    return "validation_preview"


def route_after_preview(state: AgentState) -> str:
    phase = state.get("phase", "")
    if not phase:
        return END
    if phase == ReconciliationPhase.RULE_CONFIG.value:
        return "rule_config"
    return "task_execution"


def route_after_save_rule(state: AgentState) -> str:
    using_recommended = state.get("using_recommended_rule", False)
    if using_recommended:
        return "result_evaluation"
    return END


def route_after_ask_start(state: AgentState) -> str:
    if state.get("phase", "") == ReconciliationPhase.TASK_EXECUTION.value:
        return "task_execution"
    return END


def route_after_result_analysis(state: AgentState) -> str:
    generated_schema = state.get("generated_schema")
    if generated_schema:
        return "result_evaluation"
    return END


def route_after_result_evaluation(state: AgentState) -> str:
    phase = state.get("phase", "")
    if phase == ReconciliationPhase.FIELD_MAPPING.value:
        return "field_mapping"
    if phase == ReconciliationPhase.RESULT_EVALUATION.value:
        return "result_evaluation"
    return END


def _route_after_edit_field_mapping(state: AgentState) -> str:
    phase = state.get("phase", "")
    if phase == ReconciliationPhase.EDIT_FIELD_MAPPING.value:
        return "edit_field_mapping"
    return "edit_rule_config"


def _route_after_edit_rule_config(state: AgentState) -> str:
    phase = state.get("phase", "")
    if phase == ReconciliationPhase.EDIT_RULE_CONFIG.value:
        return "edit_rule_config"
    return "edit_validation_preview"


def _route_after_edit_preview(state: AgentState) -> str:
    phase = state.get("phase", "")
    if phase == ReconciliationPhase.EDIT_RULE_CONFIG.value:
        return "edit_rule_config"
    return "edit_save"


def route_from_entry(state: AgentState) -> str:
    """从入口路由节点决定下一步。"""
    phase = state.get("phase", "")
    logger.info("入口路由决策: phase=%s", phase)

    if phase == ReconciliationPhase.FIELD_MAPPING.value:
        return "field_mapping"
    if phase == ReconciliationPhase.RULE_RECOMMENDATION.value:
        return "rule_recommendation"
    if phase == ReconciliationPhase.RULE_CONFIG.value:
        return "rule_config"
    if phase == ReconciliationPhase.VALIDATION_PREVIEW.value:
        return "validation_preview"
    if phase == ReconciliationPhase.SAVE_RULE.value:
        return "save_rule"
    if phase == ReconciliationPhase.RESULT_EVALUATION.value:
        return "result_evaluation"
    if phase == ReconciliationPhase.EDIT_FIELD_MAPPING.value:
        return "edit_field_mapping"
    if phase == ReconciliationPhase.EDIT_RULE_CONFIG.value:
        return "edit_rule_config"
    if phase == ReconciliationPhase.EDIT_VALIDATION_PREVIEW.value:
        return "edit_validation_preview"
    if phase == ReconciliationPhase.EDIT_SAVE.value:
        return "edit_save"
    if phase == ReconciliationPhase.TASK_EXECUTION.value:
        return "task_execution"
    if phase == ReconciliationPhase.COMPLETED.value:
        return END
    return "file_analysis"


# ── 构建子图 ─────────────────────────────────────────────────────────────────

def build_reconciliation_subgraph() -> StateGraph:
    """构建对账子图（规则生成 + 编辑 + 执行 + 结果评估闭环）。"""
    from app.graphs.reconciliation.execution_nodes import (
        ask_start_now_node,
        result_analysis_node,
        task_execution_node,
    )

    sg = StateGraph(AgentState)

    sg.add_node("entry_router", entry_router_node)
    sg.add_node("file_analysis", file_analysis_node)
    sg.add_node("field_mapping", field_mapping_node)
    sg.add_node("rule_recommendation", rule_recommendation_node)
    sg.add_node("rule_config", rule_config_node)
    sg.add_node("validation_preview", validation_preview_node)
    sg.add_node("save_rule", save_rule_node)
    sg.add_node("result_evaluation", result_evaluation_node)

    sg.add_node("edit_field_mapping", edit_field_mapping_node)
    sg.add_node("edit_rule_config", edit_rule_config_node)
    sg.add_node("edit_validation_preview", edit_validation_preview_node)
    sg.add_node("edit_save", edit_save_node)

    sg.add_node("ask_start_now", ask_start_now_node)
    sg.add_node("task_execution", task_execution_node)
    sg.add_node("result_analysis", result_analysis_node)

    sg.set_entry_point("entry_router")

    sg.add_conditional_edges("entry_router", route_from_entry, {
        "file_analysis": "file_analysis",
        "field_mapping": "field_mapping",
        "rule_recommendation": "rule_recommendation",
        "rule_config": "rule_config",
        "validation_preview": "validation_preview",
        "save_rule": "save_rule",
        "result_evaluation": "result_evaluation",
        "edit_field_mapping": "edit_field_mapping",
        "edit_rule_config": "edit_rule_config",
        "edit_validation_preview": "edit_validation_preview",
        "edit_save": "edit_save",
        "task_execution": "task_execution",
        END: END,
    })

    sg.add_conditional_edges("file_analysis", route_after_file_analysis, {
        "file_analysis": "file_analysis",
        "rule_recommendation": "rule_recommendation",
        "task_execution": "task_execution",
        END: END,
    })
    sg.add_conditional_edges("field_mapping", route_after_field_mapping, {
        "field_mapping": "field_mapping",
        "rule_config": "rule_config",
        END: END,
    })
    sg.add_conditional_edges("rule_recommendation", route_after_rule_recommendation, {
        "rule_recommendation": "rule_recommendation",
        "field_mapping": "field_mapping",
        "task_execution": "task_execution",
        END: END,
    })
    sg.add_conditional_edges("rule_config", route_after_rule_config, {
        "rule_config": "rule_config",
        "validation_preview": "validation_preview",
        END: END,
    })
    sg.add_conditional_edges("validation_preview", route_after_preview, {
        "rule_config": "rule_config",
        "task_execution": "task_execution",
        END: END,
    })
    sg.add_conditional_edges("save_rule", route_after_save_rule, {
        "result_evaluation": "result_evaluation",
        END: END,
    })
    sg.add_conditional_edges("ask_start_now", route_after_ask_start, {
        "task_execution": "task_execution",
        END: END,
    })

    sg.add_edge("task_execution", "result_analysis")
    sg.add_conditional_edges("result_analysis", route_after_result_analysis, {
        "result_evaluation": "result_evaluation",
        END: END,
    })
    sg.add_conditional_edges("result_evaluation", route_after_result_evaluation, {
        "field_mapping": "field_mapping",
        "result_evaluation": "result_evaluation",
        END: END,
    })

    sg.add_conditional_edges("edit_field_mapping", _route_after_edit_field_mapping, {
        "edit_field_mapping": "edit_field_mapping",
        "edit_rule_config": "edit_rule_config",
    })
    sg.add_conditional_edges("edit_rule_config", _route_after_edit_rule_config, {
        "edit_rule_config": "edit_rule_config",
        "edit_validation_preview": "edit_validation_preview",
    })
    sg.add_conditional_edges("edit_validation_preview", _route_after_edit_preview, {
        "edit_rule_config": "edit_rule_config",
        "edit_save": "edit_save",
    })
    sg.add_edge("edit_save", END)

    return sg
