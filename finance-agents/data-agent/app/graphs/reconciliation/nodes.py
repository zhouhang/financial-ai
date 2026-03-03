"""对账节点函数模块

包含对账工作流中的所有节点函数：
- file_analysis_node: 分析上传的文件
- field_mapping_node: 字段映射 (HITL)
- rule_config_node: 规则配置 (HITL)
- validation_preview_node: 验证预览 (HITL)
- save_rule_node: 保存规则
- edit_*_node: 编辑规则相关节点
- entry_router_node: 子图入口路由
- _generate_friendly_response_for_other_intent: 辅助函数

注意：所有节点函数已迁移到独立的模块，此文件保留用于向后兼容。
导入方式：from app.graphs.reconciliation import file_analysis_node, field_mapping_node, etc.
"""

from __future__ import annotations

import logging

from langchain_core.messages import AIMessage  # noqa: F401 (re-export)
from app.models import AgentState  # noqa: F401 (re-export)

from app.graphs.reconciliation.analysis_nodes import file_analysis_node  # noqa: F401
from app.graphs.reconciliation.mapping_nodes import field_mapping_node  # noqa: F401
from app.graphs.reconciliation.recommendation_nodes import rule_recommendation_node  # noqa: F401
from app.graphs.reconciliation.config_nodes import rule_config_node  # noqa: F401
from app.graphs.reconciliation.preview_nodes import validation_preview_node  # noqa: F401

from app.graphs.reconciliation.save_nodes import (  # noqa: F401
    save_rule_node,
    edit_save_node,
    result_evaluation_node,
)

from app.graphs.reconciliation.edit_nodes import (  # noqa: F401
    edit_field_mapping_node,
    edit_rule_config_node,
    edit_validation_preview_node,
)

from app.graphs.reconciliation.router_nodes import entry_router_node  # noqa: F401

logger = logging.getLogger(__name__)


# ── 辅助函数 ─────────────────────────────────────────────────────────────────

async def _generate_friendly_response_for_other_intent(
    user_input: str,
    current_phase: str,
    phase_description: str,
    next_action_hint: str
) -> str:
    """用 LLM 生成友好的回复（针对 OTHER 意图）"""
    from app.utils.llm import get_llm
    from langchain_core.messages import SystemMessage

    prompt = f"""你是一个友好的对账助手。用户在对账流程中向你提问或想聊天。

**当前阶段**：{phase_description}

**用户说**：{user_input}

请生成一个简短（1-2句话）、友好、自然的回复：
1. 如果是提问，简单回答或解释
2. 如果是闲聊，友好回应
3. 然后温和地引导回到任务

**语气要求**：轻松、口语化、像朋友聊天一样

请直接输出回复内容，不要加引号或其他格式。"""

    try:
        llm = get_llm(temperature=0.7)
        response = await llm.ainvoke([SystemMessage(content=prompt)])
        friendly_reply = response.content.strip()
        full_response = f"{friendly_reply}\n\n{next_action_hint}"
        return full_response
    except Exception as e:
        logger.error(f"LLM 生成友好回复失败: {e}")
        return f"😊 好的～\n\n{next_action_hint}"


__all__ = [
    "file_analysis_node",
    "field_mapping_node",
    "rule_recommendation_node",
    "rule_config_node",
    "validation_preview_node",
    "save_rule_node",
    "edit_field_mapping_node",
    "edit_rule_config_node",
    "edit_validation_preview_node",
    "edit_save_node",
    "result_evaluation_node",
    "entry_router_node",
    "_generate_friendly_response_for_other_intent",
]
