"""主图路由函数模块

包含主图的条件路由函数和图构建函数：
- route_after_router: router 之后的条件路由
- route_after_reconciliation: 对账子图完成后的路由
- route_after_ask_start: 询问是否立即执行后的路由
- _route_after_edit_*: 编辑规则流程的路由
- build_main_graph: 构建主 Agent 图
- create_app: 创建带有 MemorySaver 的可运行图实例
"""

from __future__ import annotations

import logging
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

logger = logging.getLogger(__name__)

from app.models import (
    AgentState,
    ReconciliationPhase,
    UserIntent,
)
from app.graphs.reconciliation import (
    file_analysis_node,
    field_mapping_node,
    rule_config_node,
    validation_preview_node,
    save_rule_node,
    edit_field_mapping_node,
    edit_rule_config_node,
    edit_validation_preview_node,
    edit_save_node,
    route_after_file_analysis,
    route_after_field_mapping,
    route_after_rule_config,
    route_after_preview,
)
from app.graphs.data_preparation import build_data_preparation_subgraph
from app.graphs.rule_creation import build_rule_creation_subgraph
from app.graphs.data_process.nodes import (
    skill_retrieve_node,
    deep_agent_node,
    get_result_node,
)
from app.graphs.data_process.routers import (
    route_after_skill_retrieve,
    route_after_deep_agent,
)
from .nodes import (
    router_node,
    task_execution_node,
    result_analysis_node,
    ask_start_now_node,
)


# ══════════════════════════════════════════════════════════════════════════════
# 路由函数
# ══════════════════════════════════════════════════════════════════════════════

def route_after_router(state: AgentState) -> str:
    """router 之后的条件路由。"""
    intent = state.get("user_intent", "")
    phase = state.get("phase", "")
    rule_creation_active = state.get("rule_creation_active", False)

    logger.info(
        f"route_after_router: intent={repr(intent)}, phase={repr(phase)}, "
        f"rule_creation_active={rule_creation_active}, "
        f"AUDIT_DATA_PROCESS={repr(UserIntent.AUDIT_DATA_PROCESS.value)}"
    )

    # ⚠️ AUDIT_DATA_PROCESS 优先级最高，清空 rule_creation_active 不影响此路由
    if intent == UserIntent.AUDIT_DATA_PROCESS.value:
        logger.info("route_after_router → dp_skill_retrieve")
        return "dp_skill_retrieve"  # ⚠️ 直接返回节点名，避免 LangGraph 1.0.x 非对等路径映射 bug

    # 检查是否正在创建规则（对话式），此优先级低于 AUDIT_DATA_PROCESS
    if rule_creation_active:
        logger.info(f"route_after_router → rule_creation (rule_creation_active=True)")
        return "rule_creation"

    if intent == UserIntent.CREATE_NEW_RULE.value:
        result = "file_analysis"
    elif intent == UserIntent.USE_EXISTING_RULE.value:
        result = "task_execution"
    elif intent == UserIntent.EDIT_RULE.value:
        result = "edit_field_mapping"
    elif intent == UserIntent.RULE_CREATION.value:
        result = "rule_creation"
    else:
        result = END

    logger.info(f"route_after_router → {repr(result)}")
    return result


def route_after_reconciliation(state: AgentState) -> str:
    """对账子图完成后，判断用户是否要立即执行。"""
    # 如果已保存规则，检查用户是否要立即开始
    saved = state.get("saved_rule_name")
    if saved:
        return "ask_start_now"
    return END


def route_after_ask_start(state: AgentState) -> str:
    phase = state.get("phase", "")
    if phase == ReconciliationPhase.TASK_EXECUTION.value:
        return "task_execution"
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


# ══════════════════════════════════════════════════════════════════════════════
# 构建主图
# ══════════════════════════════════════════════════════════════════════════════

def build_main_graph() -> StateGraph:
    """构建主 Agent 图。

    ⚠️ 对账规则生成的节点直接展平到主图中（不再使用子图），
    这样 interrupt/resume 时不会 replay 之前的节点，避免重复文件分析。
    ⚠️ data_process 节点同样展平（LangGraph 1.0.x 中编译子图作为节点存在路由问题）。
    """

    # 数据准备子图（暂时保留为子图）
    data_preparation_sg = build_data_preparation_subgraph()

    # 规则创建子图（对话式）
    rule_creation_sg = build_rule_creation_subgraph()

    graph = StateGraph(AgentState)

    # ── 节点 ──────────────────────────────────────────────────────────────
    graph.add_node("router", router_node)

    # 对账规则生成节点（直接在主图中，避免子图 replay）
    graph.add_node("file_analysis", file_analysis_node)
    graph.add_node("field_mapping", field_mapping_node)
    graph.add_node("rule_config", rule_config_node)
    graph.add_node("validation_preview", validation_preview_node)
    graph.add_node("save_rule", save_rule_node)

    # 审计数据处理节点（展平，Deep Agent 架构，避免 LangGraph 1.0.x 子图路由问题）
    graph.add_node("dp_skill_retrieve", skill_retrieve_node)
    graph.add_node("dp_deep_agent", deep_agent_node)
    graph.add_node("dp_get_result", get_result_node)

    # 其他节点
    graph.add_node("data_preparation_subgraph", data_preparation_sg.compile())
    graph.add_node("rule_creation", rule_creation_sg.compile())  # 规则创建子图
    graph.add_node("task_execution", task_execution_node)
    graph.add_node("result_analysis", result_analysis_node)
    graph.add_node("ask_start_now", ask_start_now_node)

    # ── 边 ────────────────────────────────────────────────────────────────
    graph.set_entry_point("router")

    # 编辑规则节点
    graph.add_node("edit_field_mapping", edit_field_mapping_node)
    graph.add_node("edit_rule_config", edit_rule_config_node)
    graph.add_node("edit_validation_preview", edit_validation_preview_node)
    graph.add_node("edit_save", edit_save_node)

    # router 后路由（⚠️ 所有 key 与 value 对等，避免 LangGraph 1.0.x 非对等路径映射 bug）
    graph.add_conditional_edges("router", route_after_router, {
        "file_analysis": "file_analysis",
        "task_execution": "task_execution",
        "edit_field_mapping": "edit_field_mapping",
        "dp_skill_retrieve": "dp_skill_retrieve",  # 审计数据处理入口（Deep Agent 架构）
        "rule_creation": "rule_creation",
        END: END,
    })

    # 审计数据处理流程（Deep Agent，展平节点，⚠️ 所有路径映射均对等）
    graph.add_conditional_edges("dp_skill_retrieve", route_after_skill_retrieve, {
        "dp_deep_agent": "dp_deep_agent",
        END: END,
    })
    graph.add_conditional_edges("dp_deep_agent", route_after_deep_agent, {
        "dp_get_result": "dp_get_result",
        END: END,
    })
    graph.add_edge("dp_get_result", END)

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

    # 编辑规则流程
    graph.add_conditional_edges("edit_field_mapping", _route_after_edit_field_mapping, {
        "edit_field_mapping": "edit_field_mapping",
        "edit_rule_config": "edit_rule_config",
    })
    graph.add_conditional_edges("edit_rule_config", _route_after_edit_rule_config, {
        "edit_rule_config": "edit_rule_config",
        "edit_validation_preview": "edit_validation_preview",
    })
    graph.add_conditional_edges("edit_validation_preview", _route_after_edit_preview, {
        "edit_rule_config": "edit_rule_config",
        "edit_save": "edit_save",
    })
    graph.add_edge("edit_save", END)

    # task_execution → result_analysis → END
    graph.add_edge("task_execution", "result_analysis")
    graph.add_edge("result_analysis", END)

    return graph


def create_app():
    """创建带有 MemorySaver 的可运行图实例。"""
    memory = MemorySaver()
    graph = build_main_graph()
    return graph.compile(checkpointer=memory)
