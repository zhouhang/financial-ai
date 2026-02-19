"""对账路由函数和子图构建模块

包含对账工作流中的路由决策函数和子图构建逻辑。
"""

from __future__ import annotations

import logging

from langgraph.graph import END, StateGraph

from app.models import AgentState, ReconciliationPhase
from .nodes import (
    entry_router_node,
    file_analysis_node,
    field_mapping_node,
    rule_config_node,
    validation_preview_node,
    save_rule_node,
)

logger = logging.getLogger(__name__)


# ── 路由函数 ─────────────────────────────────────────────────────────────────

def route_after_file_analysis(state: AgentState) -> str:
    """文件分析后路由：如果有分析结果则继续，否则结束等待文件上传。"""
    analyses = state.get("file_analyses", [])
    if analyses:
        return "field_mapping"
    return END


def route_after_field_mapping(state: AgentState) -> str:
    """字段映射后路由：如果用户要调整则重新进入 field_mapping，否则进入 rule_config。"""
    phase = state.get("phase", "")
    if phase == ReconciliationPhase.FIELD_MAPPING.value:
        return "field_mapping"  # 用户输入了调整意见，重新进入
    return "rule_config"  # 用户确认了，进入下一步


def route_after_rule_config(state: AgentState) -> str:
    """规则配置后路由：如果用户要调整则重新进入 rule_config，否则进入 validation_preview。"""
    phase = state.get("phase", "")
    if phase == ReconciliationPhase.RULE_CONFIG.value:
        return "rule_config"  # 用户输入了调整意见，重新进入
    return "validation_preview"  # 用户确认了，进入下一步


def route_after_preview(state: AgentState) -> str:
    """预览后路由：如果用户选择调整则回到 rule_config，否则进入 save_rule。"""
    phase = state.get("phase", "")
    if phase == ReconciliationPhase.RULE_CONFIG.value:
        return "rule_config"
    return "save_rule"


def route_from_entry(state: AgentState) -> str:
    """从入口路由节点决定下一步。"""
    phase = state.get("phase", "")
    logger.info(f"入口路由决策: phase={phase}")
    
    if phase == ReconciliationPhase.FIELD_MAPPING.value:
        logger.info("路由到: field_mapping")
        return "field_mapping"
    elif phase == ReconciliationPhase.RULE_CONFIG.value:
        logger.info("路由到: rule_config")
        return "rule_config"
    elif phase == ReconciliationPhase.SAVE_RULE.value:
        logger.info("路由到: save_rule")
        return "save_rule"
    else:
        # 默认从 file_analysis 开始
        logger.info(f"路由到: file_analysis (默认，phase={phase})")
        return "file_analysis"


# ── 构建子图 ─────────────────────────────────────────────────────────────────

def build_reconciliation_subgraph() -> StateGraph:
    """构建对账规则生成子图（第2层）。"""
    sg = StateGraph(AgentState)

    sg.add_node("entry_router", entry_router_node)
    sg.add_node("file_analysis", file_analysis_node)
    sg.add_node("field_mapping", field_mapping_node)
    sg.add_node("rule_config", rule_config_node)
    sg.add_node("validation_preview", validation_preview_node)
    sg.add_node("save_rule", save_rule_node)

    sg.set_entry_point("entry_router")
    
    # 入口路由：根据 phase 跳转
    sg.add_conditional_edges("entry_router", route_from_entry, {
        "file_analysis": "file_analysis",
        "field_mapping": "field_mapping",
        "rule_config": "rule_config",
        "save_rule": "save_rule",
    })
    
    sg.add_conditional_edges("file_analysis", route_after_file_analysis, {
        "field_mapping": "field_mapping",
        END: END,
    })
    sg.add_conditional_edges("field_mapping", route_after_field_mapping, {
        "field_mapping": "field_mapping",  # 调整意见，重新进入
        "rule_config": "rule_config",      # 确认，进入下一步
    })
    sg.add_conditional_edges("rule_config", route_after_rule_config, {
        "rule_config": "rule_config",           # 调整意见，重新进入
        "validation_preview": "validation_preview",  # 确认，进入下一步
    })
    sg.add_conditional_edges("validation_preview", route_after_preview, {
        "rule_config": "rule_config",
        "save_rule": "save_rule",
    })
    sg.add_edge("save_rule", END)

    return sg
