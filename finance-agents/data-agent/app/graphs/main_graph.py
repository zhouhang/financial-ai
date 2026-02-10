"""主 Agent 图 — 整合三层架构

第1层：对话理解（AI自主决策 — router 节点）
第2层：规则生成（对账子图）
第3层：任务执行（调用 finance-mcp 完成对账）
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt, Command

from app.utils.llm import get_llm
from app.models import (
    AgentState,
    ReconciliationPhase,
    TaskExecutionStep,
    UserIntent,
)
from app.graphs.reconciliation import build_reconciliation_subgraph
from app.graphs.data_preparation import build_data_preparation_subgraph
from app.tools.mcp_client import (
    list_available_rules,
    start_reconciliation,
    get_reconciliation_status,
    get_reconciliation_result,
)

logger = logging.getLogger(__name__)


# ── 系统提示词 ────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
你是一个专业的财务对账助手。你的职责是帮助用户完成财务数据对账工作。

你可以做以下事情：
1. 使用已有的对账规则快速执行对账
2. 引导用户创建新的对账规则
3. 帮助用户理解对账结果

当前已有的对账规则：
{available_rules}

请根据用户的意图判断下一步操作：
- 如果用户想使用已有规则对账，回复 JSON: {{"intent": "use_existing_rule", "rule_name": "规则名称"}}
- 如果用户想创建新规则，回复 JSON: {{"intent": "create_new_rule"}}
- 如果用户在闲聊或询问信息，正常用中文回复即可

注意：只在明确判断意图时才返回 JSON，否则正常对话。
"""


# ══════════════════════════════════════════════════════════════════════════════
# 第1层：对话理解 — router
# ══════════════════════════════════════════════════════════════════════════════

def router_node(state: AgentState) -> dict:
    """AI 自主决策节点：分析用户意图，决定走快速路径还是引导式生成。"""
    import json as _json

    rules = list_available_rules()
    rules_text = "\n".join(
        [f"• {r['name_cn']}（type_key: {r['type_key']}）" for r in rules]
    ) if rules else "暂无已有规则"

    system_msg = SYSTEM_PROMPT.format(available_rules=rules_text)

    llm = get_llm()
    messages = list(state.get("messages", []))
    resp = llm.invoke([SystemMessage(content=system_msg)] + messages)

    content = resp.content.strip()

    # 尝试解析 JSON 意图
    try:
        # 支持 ```json ... ``` 包裹
        json_match = content
        if "```" in content:
            import re
            m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if m:
                json_match = m.group(1)
        parsed = _json.loads(json_match)
        intent = parsed.get("intent", "")
        rule_name = parsed.get("rule_name", "")
    except (_json.JSONDecodeError, AttributeError):
        intent = ""
        rule_name = ""

    if intent == UserIntent.USE_EXISTING_RULE.value and rule_name:
        return {
            "messages": [AIMessage(content=f"好的，将使用规则「{rule_name}」进行对账。请确认已上传需要对账的文件。")],
            "user_intent": intent,
            "selected_rule_name": rule_name,
            "phase": ReconciliationPhase.TASK_EXECUTION.value,
            "execution_step": TaskExecutionStep.NOT_STARTED.value,
        }
    elif intent == UserIntent.CREATE_NEW_RULE.value:
        return {
            "messages": [AIMessage(content="好的，让我们一步步创建新的对账规则。首先请上传需要对账的文件（业务数据和财务数据）。")],
            "user_intent": intent,
            "phase": ReconciliationPhase.FILE_ANALYSIS.value,
        }
    else:
        # 普通对话
        return {
            "messages": [AIMessage(content=content)],
            "user_intent": UserIntent.UNKNOWN.value,
        }


# ══════════════════════════════════════════════════════════════════════════════
# 第3层：任务执行 — 调用 finance-mcp
# ══════════════════════════════════════════════════════════════════════════════

async def _do_start_task(rule_name: str, files: list[str]) -> dict[str, Any]:
    """启动对账任务。"""
    result = await start_reconciliation(rule_name, files)
    return result


async def _do_poll(task_id: str, max_polls: int = 30, interval: float = 2.0) -> dict[str, Any]:
    """轮询任务状态直到完成。"""
    for _ in range(max_polls):
        status = await get_reconciliation_status(task_id)
        st = status.get("status", "")
        if st in ("completed", "failed", "error"):
            return status
        await asyncio.sleep(interval)
    return {"status": "timeout", "task_id": task_id}


def task_execution_node(state: AgentState) -> dict:
    """第3层：启动对账任务、轮询状态、展示结果。

    由于 langgraph 节点是同步的，内部使用 asyncio 调用异步函数。
    """
    rule_name = state.get("selected_rule_name") or state.get("saved_rule_name")
    files = state.get("uploaded_files", [])
    step = state.get("execution_step", TaskExecutionStep.NOT_STARTED.value)

    if not rule_name:
        return {
            "messages": [AIMessage(content="缺少对账规则名称，请先选择或创建一个规则。")],
            "phase": ReconciliationPhase.IDLE.value,
        }
    if not files:
        # 等待文件上传
        user_resp = interrupt({
            "question": "请上传需要对账的文件",
            "hint": "请通过 /upload 接口上传业务数据和财务数据文件",
        })
        # 用户回复后，文件应该已在 state 中
        files = state.get("uploaded_files", [])
        if not files:
            return {
                "messages": [AIMessage(content="未检测到文件，请先上传文件后再开始对账。")],
                "phase": ReconciliationPhase.TASK_EXECUTION.value,
                "execution_step": TaskExecutionStep.NOT_STARTED.value,
            }

    # ── 启动任务 ──
    loop = asyncio.new_event_loop()
    try:
        start_result = loop.run_until_complete(_do_start_task(rule_name, files))
    finally:
        loop.close()

    if "error" in start_result:
        return {
            "messages": [AIMessage(content=f"启动对账任务失败：{start_result['error']}")],
            "phase": ReconciliationPhase.TASK_EXECUTION.value,
            "execution_step": TaskExecutionStep.NOT_STARTED.value,
        }

    task_id = start_result.get("task_id", "")

    # ── 轮询 ──
    loop2 = asyncio.new_event_loop()
    try:
        poll_result = loop2.run_until_complete(_do_poll(task_id))
    finally:
        loop2.close()

    status = poll_result.get("status", "")

    if status == "completed":
        # ── 获取结果 ──
        loop3 = asyncio.new_event_loop()
        try:
            result = loop3.run_until_complete(get_reconciliation_result(task_id))
        finally:
            loop3.close()

        summary = result.get("summary", {})
        issues = result.get("issues", [])
        msg_parts = [
            "对账完成！结果如下：\n",
            f"• 业务记录数：{summary.get('total_business_records', 'N/A')}",
            f"• 财务记录数：{summary.get('total_finance_records', 'N/A')}",
            f"• 匹配记录数：{summary.get('matched_records', 'N/A')}",
            f"• 差异记录数：{summary.get('unmatched_records', 'N/A')}",
        ]

        if issues:
            msg_parts.append(f"\n前 {min(10, len(issues))} 条差异详情：")
            for i, issue in enumerate(issues[:10]):
                msg_parts.append(
                    f"  {i+1}. [{issue.get('issue_type', '')}] "
                    f"订单号={issue.get('order_id', '')}  {issue.get('detail', '')}"
                )
            if len(issues) > 10:
                msg_parts.append(f"  ... 共 {len(issues)} 条差异")

        return {
            "messages": [AIMessage(content="\n".join(msg_parts))],
            "task_id": task_id,
            "task_status": "completed",
            "task_result": result,
            "phase": ReconciliationPhase.COMPLETED.value,
            "execution_step": TaskExecutionStep.DONE.value,
        }
    else:
        return {
            "messages": [AIMessage(content=f"对账任务状态：{status}。任务ID：{task_id}")],
            "task_id": task_id,
            "task_status": status,
            "phase": ReconciliationPhase.TASK_EXECUTION.value,
            "execution_step": TaskExecutionStep.POLLING.value,
        }


# ══════════════════════════════════════════════════════════════════════════════
# 路由
# ══════════════════════════════════════════════════════════════════════════════

def route_after_router(state: AgentState) -> str:
    """router 之后的条件路由。"""
    intent = state.get("user_intent", "")
    phase = state.get("phase", "")

    if intent == UserIntent.CREATE_NEW_RULE.value:
        return "reconciliation_subgraph"
    elif intent == UserIntent.USE_EXISTING_RULE.value:
        return "task_execution"
    else:
        return END


def route_after_reconciliation(state: AgentState) -> str:
    """对账子图完成后，判断用户是否要立即执行。"""
    # 如果已保存规则，检查用户是否要立即开始
    saved = state.get("saved_rule_name")
    if saved:
        return "ask_start_now"
    return END


def ask_start_now_node(state: AgentState) -> dict:
    """询问用户是否立即开始对账。"""
    user_response = interrupt({
        "question": "是否立即开始对账？",
        "hint": "回复\"开始\"立即执行，或\"稍后\"退出",
    })

    response_str = str(user_response).strip()
    if response_str in ("开始", "是", "yes", "ok", "好", "执行", "立即开始"):
        return {
            "messages": [AIMessage(content="好的，开始执行对账...")],
            "selected_rule_name": state.get("saved_rule_name"),
            "phase": ReconciliationPhase.TASK_EXECUTION.value,
            "execution_step": TaskExecutionStep.NOT_STARTED.value,
        }
    else:
        return {
            "messages": [AIMessage(content="好的，你可以随时回来执行对账。")],
            "phase": ReconciliationPhase.COMPLETED.value,
        }


def route_after_ask_start(state: AgentState) -> str:
    phase = state.get("phase", "")
    if phase == ReconciliationPhase.TASK_EXECUTION.value:
        return "task_execution"
    return END


# ══════════════════════════════════════════════════════════════════════════════
# 构建主图
# ══════════════════════════════════════════════════════════════════════════════

def build_main_graph() -> StateGraph:
    """构建主 Agent 图。"""

    # 子图
    reconciliation_sg = build_reconciliation_subgraph()
    data_preparation_sg = build_data_preparation_subgraph()

    graph = StateGraph(AgentState)

    # 节点
    graph.add_node("router", router_node)
    graph.add_node("reconciliation_subgraph", reconciliation_sg.compile())
    graph.add_node("data_preparation_subgraph", data_preparation_sg.compile())
    graph.add_node("task_execution", task_execution_node)
    graph.add_node("ask_start_now", ask_start_now_node)

    # 边
    graph.set_entry_point("router")

    graph.add_conditional_edges("router", route_after_router, {
        "reconciliation_subgraph": "reconciliation_subgraph",
        "task_execution": "task_execution",
        END: END,
    })

    graph.add_conditional_edges("reconciliation_subgraph", route_after_reconciliation, {
        "ask_start_now": "ask_start_now",
        END: END,
    })

    graph.add_conditional_edges("ask_start_now", route_after_ask_start, {
        "task_execution": "task_execution",
        END: END,
    })

    graph.add_edge("task_execution", END)

    return graph


def create_app():
    """创建带有 MemorySaver 的可运行图实例。"""
    memory = MemorySaver()
    graph = build_main_graph()
    return graph.compile(checkpointer=memory)
