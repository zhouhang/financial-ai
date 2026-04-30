"""Router and builder for auto scheme run graph."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from models import AgentState
from graphs.recon.scheme_execution import build_scheme_execution_graph
from .nodes import (
    bind_ready_collection_node,
    build_auto_run_context_node,
    check_dataset_ready_node,
    create_exception_tasks_node,
    load_run_plan_node,
    load_scheme_node,
    maybe_auto_notify_node,
    persist_auto_run_node,
    persist_failed_run_node,
    resolve_biz_date_node,
    resolve_plan_inputs_node,
    update_rerun_exception_verification_node,
    validate_dataset_completeness_node,
    validate_run_plan_node,
    validate_scheme_rules_node,
)


def _get_ctx(state: AgentState) -> dict[str, Any]:
    return dict(state.get("recon_ctx") or {})


def _has_failed_reason(state: AgentState) -> bool:
    ctx = _get_ctx(state)
    return bool(str(ctx.get("failed_reason") or "").strip())


def route_after_load_run_plan(state: AgentState) -> str:
    if _has_failed_reason(state):
        return "persist_failed_run_node"
    return "validate_run_plan_node"


def route_after_validate_run_plan(state: AgentState) -> str:
    if _has_failed_reason(state):
        return "persist_failed_run_node"
    return "load_scheme_node"


def route_after_load_scheme(state: AgentState) -> str:
    if _has_failed_reason(state):
        return "persist_failed_run_node"
    return "validate_scheme_rules_node"


def route_after_validate_scheme_rules(state: AgentState) -> str:
    if _has_failed_reason(state):
        return "persist_failed_run_node"
    return "resolve_plan_inputs_node"


def build_ensure_dataset_ready_subgraph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("check_dataset_ready_node", check_dataset_ready_node)
    graph.add_node("bind_ready_collection_node", bind_ready_collection_node)

    graph.set_entry_point("check_dataset_ready_node")
    graph.add_edge("check_dataset_ready_node", "bind_ready_collection_node")
    graph.add_edge("bind_ready_collection_node", END)
    return graph


def route_after_ensure_dataset_ready(state: AgentState) -> str:
    if _has_failed_reason(state):
        return "persist_failed_run_node"
    return "validate_dataset_completeness_node"


def route_after_validate_dataset_completeness(state: AgentState) -> str:
    if _has_failed_reason(state):
        return "persist_failed_run_node"
    return "build_auto_run_context_node"


def build_auto_scheme_run_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    ensure_dataset_ready = build_ensure_dataset_ready_subgraph().compile()
    scheme_execution = build_scheme_execution_graph().compile()

    graph.add_node("load_run_plan_node", load_run_plan_node)
    graph.add_node("validate_run_plan_node", validate_run_plan_node)
    graph.add_node("load_scheme_node", load_scheme_node)
    graph.add_node("validate_scheme_rules_node", validate_scheme_rules_node)
    graph.add_node("resolve_plan_inputs_node", resolve_plan_inputs_node)
    graph.add_node("resolve_biz_date_node", resolve_biz_date_node)
    graph.add_node("ensure_dataset_ready_subgraph", ensure_dataset_ready)
    graph.add_node("validate_dataset_completeness_node", validate_dataset_completeness_node)
    graph.add_node("build_auto_run_context_node", build_auto_run_context_node)
    graph.add_node("scheme_execution_graph", scheme_execution)
    graph.add_node("persist_failed_run_node", persist_failed_run_node)
    graph.add_node("persist_auto_run_node", persist_auto_run_node)
    graph.add_node("create_exception_tasks_node", create_exception_tasks_node)
    graph.add_node("maybe_auto_notify_node", maybe_auto_notify_node)
    graph.add_node("update_rerun_exception_verification_node", update_rerun_exception_verification_node)

    graph.set_entry_point("load_run_plan_node")

    graph.add_conditional_edges(
        "load_run_plan_node",
        route_after_load_run_plan,
        {
            "validate_run_plan_node": "validate_run_plan_node",
            "persist_failed_run_node": "persist_failed_run_node",
        },
    )
    graph.add_conditional_edges(
        "validate_run_plan_node",
        route_after_validate_run_plan,
        {
            "load_scheme_node": "load_scheme_node",
            "persist_failed_run_node": "persist_failed_run_node",
        },
    )
    graph.add_conditional_edges(
        "load_scheme_node",
        route_after_load_scheme,
        {
            "validate_scheme_rules_node": "validate_scheme_rules_node",
            "persist_failed_run_node": "persist_failed_run_node",
        },
    )
    graph.add_conditional_edges(
        "validate_scheme_rules_node",
        route_after_validate_scheme_rules,
        {
            "resolve_plan_inputs_node": "resolve_plan_inputs_node",
            "persist_failed_run_node": "persist_failed_run_node",
        },
    )
    graph.add_edge("resolve_plan_inputs_node", "resolve_biz_date_node")
    graph.add_edge("resolve_biz_date_node", "ensure_dataset_ready_subgraph")
    graph.add_conditional_edges(
        "ensure_dataset_ready_subgraph",
        route_after_ensure_dataset_ready,
        {
            "validate_dataset_completeness_node": "validate_dataset_completeness_node",
            "persist_failed_run_node": "persist_failed_run_node",
        },
    )
    graph.add_conditional_edges(
        "validate_dataset_completeness_node",
        route_after_validate_dataset_completeness,
        {
            "build_auto_run_context_node": "build_auto_run_context_node",
            "persist_failed_run_node": "persist_failed_run_node",
        },
    )
    graph.add_edge("build_auto_run_context_node", "scheme_execution_graph")
    graph.add_edge("scheme_execution_graph", "persist_auto_run_node")
    graph.add_edge("persist_auto_run_node", "create_exception_tasks_node")
    graph.add_edge("create_exception_tasks_node", "maybe_auto_notify_node")
    graph.add_edge("maybe_auto_notify_node", "update_rerun_exception_verification_node")
    graph.add_edge("update_rerun_exception_verification_node", END)
    graph.add_edge("persist_failed_run_node", END)
    return graph


async def run_auto_scheme_run_graph(
    *,
    auth_token: str,
    run_plan_code: str,
    biz_date: str = "",
    trigger_mode: str = "schedule",
    run_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    app = build_auto_scheme_run_graph().compile()
    initial_ctx: dict[str, Any] = {
        "run_plan_code": run_plan_code,
        "biz_date": biz_date,
        "run_context": {
            **(dict(run_context) if isinstance(run_context, dict) else {}),
            "trigger_type": trigger_mode,
            "entry_mode": "dataset",
        },
    }
    output = await app.ainvoke(
        {
            "messages": [],
            "auth_token": auth_token,
            "recon_ctx": initial_ctx,
        }
    )
    return dict(output) if isinstance(output, dict) else {}
