"""规则配置节点模块

包含规则配置节点 rule_config_node。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def rule_config_node(state) -> dict:
    """第3步 (HITL)：增量式配置规则参数，支持自然语言添加/删除配置项。

    新的配置体验：
    1. 初始配置为空，等待用户输入
    2. 用户输入配置，LLM解析为JSON片段并添加到"当前配置"
    3. 用户可以删除已添加的配置
    4. 用户确认后完成配置
    """
    from app.models import AgentState, ReconciliationPhase, UserIntent
    from langchain_core.messages import AIMessage
    from langgraph.types import interrupt
    from app.graphs.reconciliation.helpers import _format_rule_config_items, _find_matching_items, _calculate_fuzzy_match_score
    from app.graphs.reconciliation.parsers import _parse_rule_config_json_snippet
    logger.info(f"rule_config_node 进入，当前 phase={state.get('phase', '')}")
    
    # 获取当前已添加的配置项列表（初始为空）
    config_items = state.get("rule_config_items") or []
    logger.info(f"rule_config_node: 当前配置项数量={len(config_items)}, 配置项={[item.get('description', '未知') for item in config_items]}")
    
    # 构建文件名映射（优先用 original_filename，用户更易识别）
    file_names = {}
    file_analyses = state.get("file_analyses", [])
    for analysis in file_analyses:
        source = analysis.get("guessed_source", "")
        name = analysis.get("original_filename") or analysis.get("filename", "")
        if source == "business" and name:
            file_names["business"] = name
        elif source == "finance" and name:
            file_names["finance"] = name
    
    # 区分初始状态和配置中状态
    if len(config_items) == 0:
        # 初始状态：包含操作提示、「你可以」
        question_text = """⚙️ **第3步：配置对账规则参数**

请输入你的配置要求：

你可以：
- 添加配置（描述你的规则要求，如"金额容差0.01"、"按订单号合并"）
- 回复"确认"跳过（如果不需要配置规则）

💡 **操作提示**：

- 系统智能识别字段所属的文件
- 支持针对单个文件的规则配置
- 支持为两个文件配置不同的转换规则
- 完成后回复「确认」继续"""
    else:
        # 有配置项时：显示当前配置列表
        config_display = _format_rule_config_items(config_items, file_names)
        question_text = f"""⚙️ **第3步：配置对账规则参数**

当前配置：
{config_display}

你可以：
- 继续添加配置（为文件1、文件2或全局配置新规则）
- 删除配置（如"删除金额容差"、"去掉订单号过滤"）
- 回复"确认"完成配置"""
    
    # interrupt 暂停，等待用户输入
    # 初始状态 question 已含操作提示，hint 留空避免重复；有配置项时 question 不含操作提示，用 hint 补充
    interrupt_hint = "" if len(config_items) == 0 else '''💡 **操作提示**：

- 系统智能识别字段所属的文件
- 支持针对单个文件的规则配置
- 支持为两个文件配置不同的转换规则
- 完成后回复"确认"继续'''
    user_response = interrupt({
        "step": "3/4",
        "step_title": "配置规则参数",
        "question": question_text,
        "current_config_items": config_items,
        "hint": interrupt_hint,
    })

    response_str = str(user_response).strip()
    logger.info(f"rule_config interrupt 返回，用户输入: {response_str}")

    # ====== interrupt 返回后检查意图（支持游客和登录模式）======
    auth_token = state.get("auth_token", "")

    if not auth_token:  # 游客模式
        from app.utils.workflow_intent import check_user_intent_after_interrupt_guest, handle_intent_switch_guest

        intent = await check_user_intent_after_interrupt_guest(
            user_response=user_response,
            current_phase=ReconciliationPhase.RULE_CONFIG.value,
            state=state
        )

        if intent != UserIntent.RESUME_WORKFLOW.value:
            logger.info(f"[游客] rule_config_node: 用户切换意图 {intent}")
            return await handle_intent_switch_guest(
                intent=intent,
                current_phase=ReconciliationPhase.RULE_CONFIG.value,
                state=state,
                user_input=response_str
            )
    else:  # 登录模式
        from app.utils.workflow_intent import check_user_intent_after_interrupt, handle_intent_switch

        intent = await check_user_intent_after_interrupt(
            user_response=user_response,
            current_phase=ReconciliationPhase.RULE_CONFIG.value,
            state=state
        )
        if intent != UserIntent.RESUME_WORKFLOW.value:
            logger.info(f"rule_config_node: 用户切换意图 {intent}")
            return await handle_intent_switch(intent, ReconciliationPhase.RULE_CONFIG.value, state, response_str)

    # 忽略文件上传的默认消息或空消息
    if not response_str or (response_str.startswith("已上传") and response_str.endswith("请处理。")):
        logger.info("忽略空消息或文件上传消息，保持 phase=RULE_CONFIG")
        return {
            "messages": [],
            "phase": ReconciliationPhase.RULE_CONFIG.value,
        }
    
    response_lower = response_str.lower()
    
    # 用户确认，进入下一步
    if response_lower in ("确认", "ok", "yes", "确定", "对", "没问题", "正确", "完成"):
        if len(config_items) == 0:
            return {
                "messages": [AIMessage(content="⚠️ 当前还没有添加任何配置，请至少添加一个配置项后再确认。")],
                "phase": ReconciliationPhase.RULE_CONFIG.value,
            }
        logger.info("用户确认配置，进入 VALIDATION_PREVIEW")
        return {
            "messages": [AIMessage(content="✅ 规则配置已确认。正在生成规则并预览效果...")],
            "rule_config_items": config_items,
            "phase": ReconciliationPhase.VALIDATION_PREVIEW.value,
        }
    
    # 用户输入配置或删除指令，使用 LLM 解析
    logger.info(f"用户配置指令: {response_str}")
    
    # 获取字段映射以提供更好的上下文
    mappings = state.get("confirmed_mappings") or state.get("suggested_mappings", {})
    
    # 使用新的LLM解析函数，传递字段映射信息
    parsed_result = _parse_rule_config_json_snippet(response_str, config_items, mappings)
    action = parsed_result.get("action", "unknown")
    
    new_config_items = config_items.copy()
    feedback_msg = ""
    
    if action == "add":
        # 添加配置项
        json_snippet = parsed_result.get("json_snippet", {})
        if not json_snippet:
            logger.warning(f"rule_config_node - ⚠️ LLM 返回的 json_snippet 为空，配置将不会写入 data_cleaning_rules。用户输入: {response_str[:80]}")
        new_item = {
            "json_snippet": json_snippet,
            "description": parsed_result.get("description", "未知配置"),
            "user_input": response_str,
        }
        new_config_items.append(new_item)
        # 显示更新后的配置列表（描述中去掉「两个文件」字样）
        updated_config_display = _format_rule_config_items(new_config_items, file_names)
        add_desc = parsed_result.get("description", "未知配置")
        for sfx in ("（两个文件）", "(两个文件)"):
            if add_desc.endswith(sfx):
                add_desc = add_desc[: -len(sfx)].rstrip().rstrip("，, ") or "未知配置"
                break
        feedback_msg = f"✅ 已添加配置：{add_desc}\n\n> {response_str}\n\n当前配置：\n{updated_config_display}"
        logger.info(f"添加配置项: {parsed_result.get('description')}, 当前配置项数量: {len(new_config_items)}")
    
    elif action == "delete":
        # 删除配置项 - 只删除匹配度最高的单个配置，避免误删多个
        target = parsed_result.get("target", "").strip()
        # 去掉常见前缀，确保能匹配到配置项描述（如 "删除product_price除以100" → "product_price除以100"）
        for prefix in ("删除", "去掉", "移除", "删掉"):
            if target.startswith(prefix):
                target = target[len(prefix):].strip()
                break
        
        if not target:
            feedback_msg = f"⚠️ 未指定删除目标，请检查输入\n\n> {response_str}"
        else:
            # 只匹配并删除最相关的那一项（max_matches=1，strict 仅子串匹配避免误删）
            matching_indices = _find_matching_items(
                target, new_config_items, threshold=0.5, max_matches=1, strict_substring_only=True
            )
            
            if matching_indices:
                # 删除匹配的项（从高索引到低索引，避免索引变化）
                deleted_items_desc = []
                for idx in sorted(matching_indices, reverse=True):
                    item = new_config_items[idx]
                    deleted_items_desc.append(item.get("description", "未知配置"))
                    del new_config_items[idx]
                
                # 显示更新后的配置列表
                updated_config_display = _format_rule_config_items(new_config_items, file_names)
                deleted_desc = "、".join(deleted_items_desc)
                feedback_msg = f"🗑️ 已删除配置：{deleted_desc}\n\n> {response_str}\n\n当前配置：\n{updated_config_display}"
                logger.info(f"删除了 {len(matching_indices)} 个配置项: {deleted_desc}")
            else:
                # 未找到匹配项 - 显示相似度最高的项作为建议
                if new_config_items:
                    # 计算与所有项的相似度并显示最高的几个
                    scores: list[tuple[int, float, str]] = []
                    for idx, item in enumerate(new_config_items):
                        description = item.get("description", "")
                        score = _calculate_fuzzy_match_score(target, description)
                        scores.append((idx, score, description))
                    
                    # 按相似度排序
                    scores.sort(key=lambda x: x[1], reverse=True)
                    
                    # 显示相似度最高的3个作为建议
                    suggestions = "\n\n**相似的配置项：**\n"
                    for idx, (_, score, desc) in enumerate(scores[:3]):
                        suggestions += f"  {idx+1}. {desc} (相似度: {score*100:.0f}%)\n"
                    
                    updated_config_display = _format_rule_config_items(new_config_items, file_names)
                    feedback_msg = f"⚠️ 未找到匹配的配置项\n\n> {response_str}{suggestions}\n\n**当前配置列表：**\n{updated_config_display}\n\n**💡 提示：** 尝试使用配置项中的关键词来删除，或者告诉我要删除的具体内容。"
                else:
                    updated_config_display = _format_rule_config_items(new_config_items, file_names)
                    feedback_msg = f"⚠️ 未找到匹配的配置项，且配置列表为空\n\n> {response_str}\n\n当前配置：\n{updated_config_display}"
                
                logger.warning(f"删除操作：未找到匹配项，target='{target}'")

    
    elif action == "update":
        # 更新配置项 - 使用智能匹配来找到目标项
        target = parsed_result.get("target", "").strip()
        
        if not target:
            feedback_msg = f"⚠️ 未指定更新目标，请检查输入\n\n> {response_str}"
        else:
            # 使用智能匹配查找最相关的配置项
            matching_indices = _find_matching_items(target, new_config_items, threshold=0.5)
            
            if matching_indices:
                # 更新第一个（最相关的）匹配项
                update_idx = matching_indices[0]
                old_desc = new_config_items[update_idx].get("description", "")
                
                new_config_items[update_idx] = {
                    "json_snippet": parsed_result.get("json_snippet", {}),
                    "description": parsed_result.get("description", "未知配置"),
                    "user_input": response_str,
                }
                
                updated_config_display = _format_rule_config_items(new_config_items, file_names)
                feedback_msg = f"✏️ 已更新配置：{old_desc} → {parsed_result.get('description', '未知配置')}\n\n> {response_str}\n\n当前配置：\n{updated_config_display}"
                logger.info(f"更新配置项: {old_desc} → {parsed_result.get('description')}")
            else:
                # 未找到匹配项 - 添加为新配置项
                new_item = {
                    "json_snippet": parsed_result.get("json_snippet", {}),
                    "description": parsed_result.get("description", "未知配置"),
                    "user_input": response_str,
                }
                new_config_items.append(new_item)
                
                updated_config_display = _format_rule_config_items(new_config_items, file_names)
                feedback_msg = f"⚠️ 未找到与 '{target}' 相匹配的配置项，已作为新配置添加\n\n> {response_str}\n\n当前配置：\n{updated_config_display}"
                logger.info(f"未找到匹配项，添加为新配置: {parsed_result.get('description')}")
        
        # 显示更新后的配置列表
        updated_config_display = _format_rule_config_items(new_config_items, file_names)
    
    else:
        # 解析失败或未知操作
        feedback_msg = f"⚠️ 未能理解你的配置要求，请重新描述\n\n> {response_str}\n\n提示：可以描述具体的配置项，如\"金额容差0.1元\"、\"订单号104开头\"等"
    
    logger.info(f"配置项数量: {len(config_items)} -> {len(new_config_items)}")
    logger.info(f"保存的配置项: {[item.get('description', '未知') for item in new_config_items]}")
    
    # 确保状态正确保存
    return {
        "messages": [AIMessage(content=feedback_msg)],
        "rule_config_items": new_config_items,  # 明确保存配置项列表
        "phase": ReconciliationPhase.RULE_CONFIG.value,  # 保持在当前阶段
    }





__all__ = ["rule_config_node"]
