"""规则创建子图节点函数

实现基于对话的规则创建节点。
"""

from __future__ import annotations

from typing import Any, Dict, List
from app.models import AgentState
from langchain_core.messages import AIMessage


def rule_creation_intent_node(state: AgentState) -> Dict[str, Any]:
    """规则创建意图识别节点

    识别用户是否想要创建规则
    """
    messages = state.get("messages", [])
    if not messages:
        return {}
    
    last_message = messages[-1]
    user_message = last_message.content if hasattr(last_message, 'content') else str(last_message)
    
    # 检查是否包含规则创建相关关键词
    rule_creation_keywords = [
        '创建.*规则', '新建.*规则', '我想创建', '帮我创建',
        '添加.*规则', '规则创建', '新规则'
    ]
    
    import re
    for pattern in rule_creation_keywords:
        if re.search(pattern, user_message, re.IGNORECASE):
            return {
                "user_intent": "create_rule",
                "rule_creation_active": True
            }
    
    return {}


def conversational_rule_creation_node(state: AgentState) -> Dict[str, Any]:
    """对话式规则创建节点

    使用 proc-agent 的对话规则创建器处理用户消息
    """
    from proc_agent import get_rule_creator
    
    messages = state.get("messages", [])
    if not messages:
        return {"messages": [AIMessage(content="您好！我是规则创建助手，请问有什么可以帮您？")]}
    
    # 获取最后一条用户消息
    last_message = messages[-1]
    user_message = last_message.content if hasattr(last_message, 'content') else str(last_message)
    
    # 获取用户 ID（从当前用户或会话 ID）
    current_user = state.get("current_user", {})
    user_id = current_user.get("username") if current_user else None
    
    # 获取或创建规则创建器
    creator = get_rule_creator(user_id=user_id)
    
    # 处理消息
    result = creator.process_message(user_message)
    
    ai_response = result.get('message', '')
    
    # 检查是否完成规则创建
    if result.get('step') == 'completed':
        return {
            "messages": [AIMessage(content=ai_response)],
            "rule_creation_active": False,
            "created_rule_name": result.get('rule_name')
        }
    
    # 继续对话收集信息
    return {
        "messages": [AIMessage(content=ai_response)],
        "rule_creation_active": True,
        "current_rule_name": result.get('rule_name')
    }


def rule_creation_router(state: AgentState) -> str:
    """规则创建路由

    根据对话状态决定下一步
    """
    rule_creation_active = state.get("rule_creation_active", False)
    current_step = state.get("rule_creation_step", "collecting_info")
    
    if not rule_creation_active:
        return "end"
    
    if current_step == "completed":
        return "end"
    
    return "conversational_rule_creation"
