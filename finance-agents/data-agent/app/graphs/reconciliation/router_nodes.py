"""路由节点模块

包含入口路由节点。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def entry_router_node(state: AgentState) -> dict:
    """子图入口路由节点：根据 phase 决定进入哪个节点。
    
    这是为了解决 LangGraph 子图 interrupt resume 后重新从入口点开始的问题。
    """
    phase = state.get("phase", "")
    logger.info(f"子图入口路由: phase={phase}")
    logger.info(f"  完整state keys: {list(state.keys())}")
    
    # 直接返回，让条件边路由到正确的节点
    return {"messages": []}


__all__ = ["entry_router_node"]
