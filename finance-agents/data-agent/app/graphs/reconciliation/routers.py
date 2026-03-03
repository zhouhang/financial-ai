"""对账路由函数和子图构建模块

包含对账工作流中的路由决策函数和子图构建逻辑。
"""

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
)

logger = logging.getLogger(__name__)


# ── 路由函数 ─────────────────────────────────────────────────────────────────

def route_after_file_analysis(state: AgentState) -> str:
    """文件分析后路由：如果有分析结果则进入规则推荐或任务执行，如果验证失败但有文件则循环回 file_analysis。"""
    phase = state.get("phase", "")

    # 如果 phase 为空，说明用户取消或退出了 workflow
    if not phase:
        return END

    analyses = state.get("file_analyses", [])
    if analyses:
        # 使用规则流程：校验通过后直接进入任务执行
        if state.get("user_intent") == UserIntent.USE_EXISTING_RULE.value:
            logger.info("文件验证通过，使用规则流程 -> task_execution")
            return "task_execution"
        return "rule_recommendation"  # 创建规则流程，进入规则推荐

    # 如果没有分析结果，但 uploaded_files 不为空，说明验证失败需要重新验证
    uploaded_files = state.get("uploaded_files", [])
    if uploaded_files:
        logger.info("文件验证失败，循环回 file_analysis 重新验证")
        return "file_analysis"  # 循环回 file_analysis

    return END


def route_after_field_mapping(state: AgentState) -> str:
    """字段映射后路由：进入规则配置。"""
    phase = state.get("phase", "")

    # 如果 phase 为空，说明用户取消或退出了 workflow
    if not phase:
        return END

    if phase == ReconciliationPhase.FIELD_MAPPING.value:
        return "field_mapping"  # 用户输入了调整意见，重新进入
    return "rule_config"  # 确认后进入规则配置


def route_after_rule_recommendation(state: AgentState) -> str:
    """规则推荐后路由：
    - 如果用户已选择推荐规则（selected_rule_id存在）→ 进入任务执行
    - 如果不采纳推荐 → 进入字段映射
    """
    using_recommended = state.get("using_recommended_rule", False)
    selected_rule_id = state.get("selected_rule_id")
    phase = state.get("phase", "")

    logger.info(f"route_after_rule_recommendation: phase={phase}, using_recommended={using_recommended}, selected_rule_id={selected_rule_id}")

    # 如果 phase 为空，说明用户取消或退出了 workflow
    if not phase:
        logger.info("路由: phase 为空，用户取消 -> END")
        return END

    # 用户已选择规则（通过数字选择），直接进入任务执行
    if using_recommended and selected_rule_id:
        logger.info("路由: 用户已选择规则 -> task_execution")
        return "task_execution"

    logger.info("路由: 不采纳推荐 -> field_mapping")
    return "field_mapping"


def route_after_rule_config(state: AgentState) -> str:
    """规则配置后路由：如果用户要调整则重新进入 rule_config，否则进入 validation_preview。"""
    phase = state.get("phase", "")

    # 如果 phase 为空，说明用户取消或退出了 workflow
    if not phase:
        return END

    if phase == ReconciliationPhase.RULE_CONFIG.value:
        return "rule_config"  # 用户输入了调整意见，重新进入
    return "validation_preview"  # 用户确认了，进入下一步


def route_after_preview(state: AgentState) -> str:
    """预览后路由：如果用户选择调整则回到 rule_config，否则进入对账执行。

    ⚠️ 创建规则流程：配置好规则后必须先对账，再在 result_evaluation 中提示保存。
    绝不在此处路由到 save_rule。
    """
    phase = state.get("phase", "")

    # 如果 phase 为空，说明用户取消或退出了 workflow
    if not phase:
        logger.info("route_after_preview: phase 为空，用户取消 -> END")
        return END

    if phase == ReconciliationPhase.RULE_CONFIG.value:
        logger.info("route_after_preview: 用户选择调整 -> rule_config")
        return "rule_config"
    # 预览确认后，直接执行对账（跳过保存规则步骤，先对账再提示保存）
    logger.info("route_after_preview: 用户确认 -> task_execution（先对账，后保存）")
    return "task_execution"


def route_after_save_rule(state: AgentState) -> str:
    """保存规则后路由：如果使用了推荐规则，进入结果评估。"""
    using_recommended = state.get("using_recommended_rule", False)
    if using_recommended:
        return "result_evaluation"
    return END


def route_from_entry(state: AgentState) -> str:
    """从入口路由节点决定下一步。"""
    phase = state.get("phase", "")
    logger.info(f"入口路由决策: phase={phase}")
    
    if phase == ReconciliationPhase.FIELD_MAPPING.value:
        logger.info("路由到: field_mapping")
        return "field_mapping"
    elif phase == ReconciliationPhase.RULE_RECOMMENDATION.value:
        logger.info("路由到: rule_recommendation")
        return "rule_recommendation"
    elif phase == ReconciliationPhase.RULE_CONFIG.value:
        logger.info("路由到: rule_config")
        return "rule_config"
    elif phase == ReconciliationPhase.VALIDATION_PREVIEW.value:
        logger.info("路由到: validation_preview")
        return "validation_preview"
    elif phase == ReconciliationPhase.SAVE_RULE.value:
        logger.info("路由到: save_rule")
        return "save_rule"
    elif phase == ReconciliationPhase.RESULT_EVALUATION.value:
        logger.info("路由到: result_evaluation")
        return "result_evaluation"
    else:
        logger.info(f"路由到: file_analysis (默认，phase={phase})")
        return "file_analysis"


# ── 构建子图 ─────────────────────────────────────────────────────────────────

def build_reconciliation_subgraph() -> StateGraph:
    """构建对账规则生成子图（第2层）。"""
    sg = StateGraph(AgentState)

    sg.add_node("entry_router", entry_router_node)
    sg.add_node("file_analysis", file_analysis_node)
    sg.add_node("field_mapping", field_mapping_node)
    sg.add_node("rule_recommendation", rule_recommendation_node)
    sg.add_node("rule_config", rule_config_node)
    sg.add_node("validation_preview", validation_preview_node)
    sg.add_node("save_rule", save_rule_node)
    sg.add_node("result_evaluation", result_evaluation_node)

    sg.set_entry_point("entry_router")
    
    # 入口路由：根据 phase 跳转
    sg.add_conditional_edges("entry_router", route_from_entry, {
        "file_analysis": "file_analysis",
        "field_mapping": "field_mapping",
        "rule_recommendation": "rule_recommendation",
        "rule_config": "rule_config",
        "validation_preview": "validation_preview",
        "save_rule": "save_rule",
        "result_evaluation": "result_evaluation",
    })

    sg.add_conditional_edges("file_analysis", route_after_file_analysis, {
        "file_analysis": "file_analysis",  # 允许循环回自己（验证失败时）
        "rule_recommendation": "rule_recommendation",
        END: END,
    })
    sg.add_conditional_edges("field_mapping", route_after_field_mapping, {
        "field_mapping": "field_mapping",
        "rule_config": "rule_config",
    })
    sg.add_conditional_edges("rule_recommendation", route_after_rule_recommendation, {
        "field_mapping": "field_mapping",
        "task_execution": "task_execution",
    })
    sg.add_conditional_edges("rule_config", route_after_rule_config, {
        "rule_config": "rule_config",
        "validation_preview": "validation_preview",
    })
    # ⚠️ 创建规则流程：确认后必须进入 task_execution（先对账），绝不进入 save_rule
    # 主图使用展平节点，此子图未被主图使用。若子图被使用，task_execution 会导向 END，
    # 由父图接管；否则需在子图中添加 task_execution 节点。
    sg.add_conditional_edges("validation_preview", route_after_preview, {
        "rule_config": "rule_config",
        "task_execution": END,  # 先对账：子图结束，父图应路由到 task_execution
        "save_rule": "save_rule",  # 兼容旧逻辑（route_after_preview 现不再返回 save_rule）
    })
    sg.add_conditional_edges("save_rule", route_after_save_rule, {
        "result_evaluation": "result_evaluation",
        END: END,
    })

    return sg
