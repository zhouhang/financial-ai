"""审计数据处理子图路由函数（Deep Agent 架构）

包含子图内部的条件路由函数。

简化架构两节点流程：
  deep_agent → get_result

⚠️ 所有路由函数直接返回主图中的实际节点名（dp_get_result 等），
   避免 LangGraph 1.0.x 非对等路径映射 bug。
"""

from __future__ import annotations

from langgraph.graph import END

from app.models import AgentState


def route_after_deep_agent(state: AgentState) -> str:
    """Deep Agent 执行完成后路由：无论成功还是失败，都展示结果"""
    execution_status = state.get("execution_status", "")

    if execution_status in ("success", "error"):
        return "dp_get_result"  # 直接返回主图节点名
    return END
