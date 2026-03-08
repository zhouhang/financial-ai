"""审计数据处理子图路由函数（Deep Agent 架构）

包含子图内部的条件路由函数。

新架构三节点流程：
  skill_retrieve → deep_agent → get_result

⚠️ 所有路由函数直接返回主图中的实际节点名（dp_deep_agent 等），
   避免 LangGraph 1.0.x 非对等路径映射 bug。
"""

from __future__ import annotations

from langgraph.graph import END

from app.models import AgentState


def route_after_skill_retrieve(state: AgentState) -> str:
    """Skill 检索完成后路由：有候选 skill 则进入 Deep Agent，否则结束"""
    tools_subset = state.get("tools_subset") or []
    retrieve_done = state.get("dp_retrieve_done", False)

    if retrieve_done and tools_subset:
        return "dp_deep_agent"  # 直接返回主图节点名
    return END


def route_after_deep_agent(state: AgentState) -> str:
    """Deep Agent 执行完成后路由：无论成功还是失败，都展示结果"""
    execution_status = state.get("execution_status", "")

    if execution_status in ("success", "error"):
        return "dp_get_result"  # 直接返回主图节点名
    return END
