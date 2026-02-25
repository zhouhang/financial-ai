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

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.models import (
    AgentState,
    ReconciliationPhase,
    UserIntent,
)
from app.graphs.reconciliation import (
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
    route_after_file_analysis,
    route_after_field_mapping,
    route_after_rule_recommendation,
    route_after_rule_config,
    route_after_preview,
    route_after_save_rule,
    build_reconciliation_subgraph,
)
from app.graphs.data_preparation import build_data_preparation_subgraph
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

    if intent == "guest_reconciliation":
        return "file_analysis"
    elif intent == UserIntent.CREATE_NEW_RULE.value:
        return "file_analysis"
    elif intent == UserIntent.USE_EXISTING_RULE.value:
        return "task_execution"
    elif intent == UserIntent.EDIT_RULE.value:
        return "edit_field_mapping"
    else:
        return END


def route_after_reconciliation(state: AgentState) -> str:
    """对账子图完成后，判断用户是否要立即执行。
    
    流程：
    1. 如果使用了推荐规则且未保存 → 直接开始对账（task_execution）
    2. 如果已保存规则 → 询问是否立即开始
    3. 否则结束
    """
    using_recommended = state.get("using_recommended_rule", False)
    selected_rule_id = state.get("selected_rule_id")
    saved = state.get("saved_rule_name")
    
    # 使用推荐规则但还没保存，直接开始对账
    if using_recommended and selected_rule_id and not saved:
        return "task_execution"
    
    # 如果已保存规则，检查用户是否要立即开始
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
    """

    # 数据准备子图（暂时保留为子图）
    data_preparation_sg = build_data_preparation_subgraph()

    graph = StateGraph(AgentState)

    # ── 节点 ──────────────────────────────────────────────────────────────
    graph.add_node("router", router_node)
    
    # 对账规则生成节点（直接在主图中，避免子图 replay）
    graph.add_node("file_analysis", file_analysis_node)
    graph.add_node("field_mapping", field_mapping_node)
    graph.add_node("rule_recommendation", rule_recommendation_node)
    graph.add_node("rule_config", rule_config_node)
    graph.add_node("validation_preview", validation_preview_node)
    graph.add_node("save_rule", save_rule_node)
    graph.add_node("result_evaluation", result_evaluation_node)
    
    # 其他节点
    graph.add_node("data_preparation_subgraph", data_preparation_sg.compile())
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

    # router 后路由
    graph.add_conditional_edges("router", route_after_router, {
        "file_analysis": "file_analysis",
        "task_execution": "task_execution",
        "edit_field_mapping": "edit_field_mapping",
        END: END,
    })

    # 对账规则生成流程（展平的）
    graph.add_conditional_edges("file_analysis", route_after_file_analysis, {
        "rule_recommendation": "rule_recommendation",  # 直接进入规则推荐
        END: END,
    })
    graph.add_conditional_edges("rule_recommendation", route_after_rule_recommendation, {
        "field_mapping": "field_mapping",  # 不采纳推荐，进入字段映射
        "task_execution": "task_execution",  # 确认采用推荐规则，执行对账
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
        "task_execution": "task_execution",  # 新建规则：先对账再保存（与推荐规则流程一致）
    })
    graph.add_conditional_edges("save_rule", route_after_save_rule, {
        "result_evaluation": "result_evaluation",  # 使用推荐规则，进入评估
        "ask_start_now": "ask_start_now",  # 正常流程
        END: END,
    })
    # result_evaluation 后的路由：
    # - 对账已完成，直接结束（不需要再问是否开始对账）
    # - 如果用户选择"不要"，返回字段映射
    def route_after_result_evaluation(state: AgentState) -> str:
        phase = state.get("phase", "")
        if phase == ReconciliationPhase.FIELD_MAPPING.value:
            return "field_mapping"
        if phase == ReconciliationPhase.RESULT_EVALUATION.value:
            return "result_evaluation"  # 继续等待输入（如规则名称）
        return END  # 完成或其他情况
    
    graph.add_conditional_edges("result_evaluation", route_after_result_evaluation, {
        "field_mapping": "field_mapping",
        "result_evaluation": "result_evaluation",
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

    # task_execution → result_analysis（显示对账结果）→ 根据是否推荐规则决定下一步
    graph.add_edge("task_execution", "result_analysis")
    
    # result_analysis 后：推荐规则或新建规则（先对账）→ result_evaluation（询问保存）
    def route_after_result_analysis(state: AgentState) -> str:
        using_recommended = state.get("using_recommended_rule", False)
        generated_schema = state.get("generated_schema")
        if using_recommended or generated_schema:
            return "result_evaluation"
        return END
    
    graph.add_conditional_edges("result_analysis", route_after_result_analysis, {
        "result_evaluation": "result_evaluation",
        END: END,
    })

    return graph


def create_app():
    """创建带有 MemorySaver 的可运行图实例。"""
    memory = MemorySaver()
    graph = build_main_graph()
    return graph.compile(checkpointer=memory)
