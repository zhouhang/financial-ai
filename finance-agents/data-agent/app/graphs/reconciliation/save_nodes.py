"""保存节点模块

包含保存规则和结果评估节点。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def save_rule_node(state: "AgentState") -> dict:
    """第5步 (HITL)：保存规则，询问用户是否立即开始对账。"""
    from app.models import AgentState, ReconciliationPhase, UserIntent
    from langchain_core.messages import AIMessage
    from langgraph.types import interrupt
    from app.tools.mcp_client import call_mcp_tool
    from app.graphs.reconciliation.helpers import (
        _translate_rule_name_to_english,
        _expand_file_patterns,
        _rewrite_schema_transforms_to_mapped_fields,
        _build_field_mapping_text,
        _build_rule_config_text,
        _merge_json_snippets,
        _validate_and_deduplicate_rules,
    )
    schema = state.get("generated_schema")
    if not schema:
        return {
            "messages": [AIMessage(content="没有找到已生成的规则，请重新配置。")],
            "phase": ReconciliationPhase.RULE_CONFIG.value,
        }

    user_response = interrupt({
        "question": "请为这个规则命名",
        "hint": "输入规则名称，例如：直销对账",
    })

    rule_name_cn = str(user_response).strip()
    if not rule_name_cn:
        rule_name_cn = "自定义对账规则"

    # 使用 LLM 将中文名称翻译成英文（用作 type_key 和文件名）
    type_key = _translate_rule_name_to_english(rule_name_cn)
    
    # 更新 schema 的 description 为用户输入的中文名
    schema_with_desc = schema.copy()
    schema_with_desc["description"] = rule_name_cn

    # ⚠️ 保存前再次合并 rule_config_items，确保游客模式或异步场景下配置项正确写入 data_cleaning_rules
    config_items = state.get("rule_config_items", [])
    if config_items:
        schema_with_desc = _merge_json_snippets(schema_with_desc, config_items)
        schema_with_desc = _validate_and_deduplicate_rules(schema_with_desc)
        logger.info(f"save_rule_node - 保存前合并 {len(config_items)} 个配置项到 schema")

    # ✅ 在保存前扩展 file_pattern 为所有支持的格式
    biz_patterns_orig = schema_with_desc.get("data_sources", {}).get("business", {}).get("file_pattern", [])
    fin_patterns_orig = schema_with_desc.get("data_sources", {}).get("finance", {}).get("file_pattern", [])
    
    logger.info(f"save_rule_node - 保存前规则 file_pattern (原始): business={biz_patterns_orig}, finance={fin_patterns_orig}")
    
    # 扩展 file_pattern 为所有支持的格式（.xlsx/.xls/.xlsm/.xlsb/.csv）
    biz_patterns_expanded = []
    for pattern in biz_patterns_orig:
        biz_patterns_expanded.extend(_expand_file_patterns(pattern))
    
    fin_patterns_expanded = []
    for pattern in fin_patterns_orig:
        fin_patterns_expanded.extend(_expand_file_patterns(pattern))
    
    # 去重
    biz_patterns = list(set(biz_patterns_expanded))
    fin_patterns = list(set(fin_patterns_expanded))
    
    # 更新 schema 中的 file_pattern
    if "data_sources" not in schema_with_desc:
        schema_with_desc["data_sources"] = {}
    if "business" not in schema_with_desc["data_sources"]:
        schema_with_desc["data_sources"]["business"] = {}
    if "finance" not in schema_with_desc["data_sources"]:
        schema_with_desc["data_sources"]["finance"] = {}
    
    schema_with_desc["data_sources"]["business"]["file_pattern"] = biz_patterns
    schema_with_desc["data_sources"]["finance"]["file_pattern"] = fin_patterns
    
    logger.info(f"save_rule_node - 保存前规则 file_pattern (扩展后): business={biz_patterns}, finance={fin_patterns}")
    logger.info(f"save_rule_node - 完整的 schema data_sources: {schema_with_desc.get('data_sources', {})}")
    
    # 检查 file_pattern 是否有效
    def check_pattern_validity(patterns: list[str], source_name: str) -> bool:
        """检查 file_pattern 是否包含通配符，如果不包含则发出警告"""
        if not patterns:
            logger.warning(f"save_rule_node - ⚠️ {source_name} 的 file_pattern 为空")
            return False

        has_wildcard = any('*' in p for p in patterns)
        if not has_wildcard:
            logger.error(f"save_rule_node - ❌ 严重问题：{source_name} 的 file_pattern 不包含通配符，这会导致无法匹配带时间戳的文件！patterns={patterns}")
            return False

        logger.info(f"save_rule_node - ✅ {source_name} 的 file_pattern 有效：{patterns}")
        return True

    biz_valid = check_pattern_validity(biz_patterns, "business")
    fin_valid = check_pattern_validity(fin_patterns, "finance")

    if not biz_valid or not fin_valid:
        logger.error(f"save_rule_node - ⚠️ 警告：规则的 file_pattern 可能不完整，请检查规则配置是否正确")
        # 返回警告信息但继续保存
        warning_msg = "⚠️ 警告：规则的 file_pattern 可能有问题，请确保上传的文件包含时间戳后缀（如：filename_134019.csv）"
    else:
        warning_msg = None

    # ⚠️ 保存前将 transform/expression 中的原始列名重写为映射字段名（order_id、amount 等）
    _rewrite_schema_transforms_to_mapped_fields(schema_with_desc)

    # 保存用户自然语言描述，供后续编辑规则功能使用
    mappings = state.get("confirmed_mappings") or state.get("suggested_mappings", {})
    schema_with_desc["field_mapping_text"] = _build_field_mapping_text(mappings)
    schema_with_desc["rule_config_text"] = _build_rule_config_text(config_items)

    # ⚠️ 通过 finance-mcp 工具保存规则（带认证 token）
    auth_token = state.get("auth_token", "")
    try:
        result = await call_mcp_tool("save_reconciliation_rule", {
            "auth_token": auth_token,
            "name": rule_name_cn,
            "description": rule_name_cn,
            "rule_template": schema_with_desc,
            "visibility": "private",  # 默认仅创建者可见
        })

        if not result.get("success"):
            logger.error(f"保存规则失败: {result.get('error')}")
            return {
                "messages": [AIMessage(content=f"❌ 规则保存失败: {result.get('error')}")],
                "phase": ReconciliationPhase.SAVE_RULE.value,
            }
    except Exception as e:
        logger.error(f"调用 save_reconciliation_rule 失败: {e}")
        logger.exception(e)
        return {
            "messages": [AIMessage(content=f"❌ 规则保存失败: {str(e)}")],
            "phase": ReconciliationPhase.SAVE_RULE.value,
        }

    # 检查是否使用推荐规则
    using_recommended = state.get("using_recommended_rule", False)

    msg = (
        f"规则 **{rule_name_cn}** 已保存！\n\n"
    )

    if using_recommended:
        # 使用推荐规则，询问是否立即开始对账
        msg += f"是否立即开始对账？\n（回复\"开始\"立即执行对账，或回复\"不要\"返回字段映射）"
        next_phase = ReconciliationPhase.RESULT_EVALUATION.value
    else:
        msg += f"现在可以用它开始对账了。要立即开始吗？\n（回复\"开始\"立即执行对账，或稍后再说）"
        next_phase = ReconciliationPhase.COMPLETED.value

    if warning_msg:
        msg = warning_msg + "\n\n" + msg

    return {
        "messages": [AIMessage(content=msg)],
        "saved_rule_name": rule_name_cn,
        "phase": next_phase,
    }


# ── 编辑规则节点 ─────────────────────────────────────────────────────────────


async def edit_save_node(state: "AgentState") -> dict:
    """编辑规则 - 保存：仅在此步骤删除旧规则（PostgreSQL+JSON），并新建规则。"""
    from app.models import AgentState, ReconciliationPhase
    from langchain_core.messages import AIMessage
    from app.tools.mcp_client import call_mcp_tool
    from app.graphs.reconciliation.helpers import (
        _rewrite_schema_transforms_to_mapped_fields,
        _build_field_mapping_text,
        _build_rule_config_text,
    )
    schema = state.get("generated_schema")
    rule_id = state.get("editing_rule_id")
    rule_name = state.get("editing_rule_name")
    auth_token = state.get("auth_token", "")

    if not schema or not rule_id or not rule_name:
        return {
            "messages": [AIMessage(content="❌ 缺少规则信息，无法保存。")],
            "phase": ReconciliationPhase.COMPLETED.value,
        }

    _rewrite_schema_transforms_to_mapped_fields(schema)
    mappings = state.get("confirmed_mappings") or {}
    config_items = state.get("rule_config_items", [])
    schema["field_mapping_text"] = _build_field_mapping_text(mappings)
    schema["rule_config_text"] = _build_rule_config_text(config_items)

    # 1. 删除旧规则（PostgreSQL + JSON）
    try:
        del_result = await call_mcp_tool("delete_reconciliation_rule", {
            "auth_token": auth_token,
            "rule_id": rule_id,
            "rule_name": rule_name,  # 校验防止误删
        })
        if not del_result.get("success"):
            return {
                "messages": [AIMessage(content=f"❌ 删除旧规则失败: {del_result.get('error', '未知错误')}")],
                "phase": ReconciliationPhase.EDIT_SAVE.value,
            }
    except Exception as e:
        logger.error(f"删除旧规则失败: {e}")
        return {
            "messages": [AIMessage(content=f"❌ 删除旧规则失败: {str(e)}")],
            "phase": ReconciliationPhase.EDIT_SAVE.value,
        }

    # 2. 新建规则（PostgreSQL + JSON）
    try:
        save_result = await call_mcp_tool("save_reconciliation_rule", {
            "auth_token": auth_token,
            "name": rule_name,
            "description": rule_name,
            "rule_template": schema,
            "visibility": "private",
        })
        if not save_result.get("success"):
            return {
                "messages": [AIMessage(content=f"❌ 保存新规则失败: {save_result.get('error', '未知错误')}")],
                "phase": ReconciliationPhase.EDIT_SAVE.value,
            }
    except Exception as e:
        logger.error(f"保存新规则失败: {e}")
        return {
            "messages": [AIMessage(content=f"❌ 保存新规则失败: {str(e)}")],
            "phase": ReconciliationPhase.EDIT_SAVE.value,
        }

    return {
        "messages": [AIMessage(content=f"✅ 规则「{rule_name}」已更新！")],
        "saved_rule_name": rule_name,
        "editing_rule_id": None,
        "editing_rule_name": None,
        "editing_rule_template": None,
        "generated_schema": None,  # 清空 generated_schema，避免后续对账时被误判为新建规则流程
        "phase": ReconciliationPhase.COMPLETED.value,
    }


# ── 对账结果评估节点 ─────────────────────────────────────────────────────────



async def result_evaluation_node(state: "AgentState") -> dict:
    """第6步 (HITL)：对账完成后评估规则适用性，提示用户保存。

    流程：
    1. 分析对账结果（匹配率、差异分析）
    2. 生成规则适用性评估结论
    3. 展示评估结果和保存提示
    4. 用户选择保存或不保存
    5. 如果保存，调用 copy_rule 复制规则
    """
    from app.models import AgentState, ReconciliationPhase, UserIntent
    from langchain_core.messages import AIMessage
    from langgraph.types import interrupt
    from app.tools.mcp_client import call_mcp_tool
    from app.graphs.reconciliation.analysis_cache_helpers import (
        build_reconciliation_ctx_update,
        check_pending_interrupt,
        clear_pending_interrupt,
        compute_analysis_key,
    )
    logger.info(f"result_evaluation_node 进入，当前 phase={state.get('phase', '')}")
    reconciliation_ctx = state.get("reconciliation_ctx") or {}
    run_id = state.get("workflow_run_id") or reconciliation_ctx.get("run_id") or "default"
    uploaded = reconciliation_ctx.get("uploaded_files") or state.get("uploaded_files", [])
    analysis_key = compute_analysis_key(uploaded, {
        "intent": state.get("user_intent", ""),
        "selected_rule_id": state.get("selected_rule_id", ""),
        "selected_rule_name": state.get("selected_rule_name", ""),
    })
    if check_pending_interrupt(state, "result_evaluation", analysis_key, str(run_id)):
        logger.info("result_evaluation_node 命中 pending_interrupt 闸门，按重放模式执行")
    
    preview_result = state.get("preview_result", {})
    using_recommended = state.get("using_recommended_rule", False)
    selected_rule_id = state.get("selected_rule_id")
    waiting_for_name = state.get("waiting_for_rule_name", False)
    auth_token = state.get("auth_token", "")
    
    # 处理用户输入规则名称（推荐规则用 copy，新建规则用 save）
    generated_schema = state.get("generated_schema")
    if waiting_for_name and (selected_rule_id or generated_schema):
        user_response = interrupt({
            "question": "请输入规则名称",
            "hint": "输入规则名称，例如：我的对账规则",
        })
        
        rule_name = str(user_response).strip()
        if not rule_name:
            return {
                "messages": [AIMessage(content="⚠️ 请输入有效的规则名称。")],
                "phase": ReconciliationPhase.RESULT_EVALUATION.value,
                "waiting_for_rule_name": True,
            }
        
        if auth_token:
            try:
                if generated_schema:
                    # 新建规则：直接保存 schema
                    from .helpers import _rewrite_schema_transforms_to_mapped_fields, _build_field_mapping_text, _build_rule_config_text, _expand_file_patterns
                    schema_to_save = generated_schema.copy()
                    schema_to_save["description"] = rule_name
                    _rewrite_schema_transforms_to_mapped_fields(schema_to_save)
                    mappings = state.get("confirmed_mappings") or state.get("suggested_mappings", {})
                    config_items = state.get("rule_config_items", [])
                    schema_to_save["field_mapping_text"] = _build_field_mapping_text(mappings)
                    schema_to_save["rule_config_text"] = _build_rule_config_text(config_items)
                    for src in ("business", "finance"):
                        patterns = schema_to_save.get("data_sources", {}).get(src, {}).get("file_pattern", [])
                        expanded = []
                        for p in patterns:
                            expanded.extend(_expand_file_patterns(p))
                        if "data_sources" not in schema_to_save:
                            schema_to_save["data_sources"] = {}
                        if src not in schema_to_save["data_sources"]:
                            schema_to_save["data_sources"][src] = {}
                        schema_to_save["data_sources"][src]["file_pattern"] = list(set(expanded))
                    result = await call_mcp_tool("save_reconciliation_rule", {
                        "auth_token": auth_token,
                        "name": rule_name,
                        "description": rule_name,
                        "rule_template": schema_to_save,
                        "visibility": "private",
                    })
                else:
                    # 推荐规则：复制
                    result = await call_mcp_tool("copy_reconciliation_rule", {
                        "auth_token": auth_token,
                        "source_rule_id": selected_rule_id,
                        "new_rule_name": rule_name,
                    })
                if result.get("success"):
                    logger.info(f"规则保存成功: {rule_name}")
                    return {
                        "messages": [AIMessage(content=f"✅ 规则已保存为「{rule_name}」！您可以在后续对账中直接使用此规则。")],
                        "saved_rule_name": rule_name,
                        "phase": ReconciliationPhase.COMPLETED.value,
                        "waiting_for_rule_name": False,
                        **build_reconciliation_ctx_update(state, run_id=run_id),
                        **clear_pending_interrupt(state, "result_evaluation"),
                    }
                else:
                    update = {
                        "messages": [AIMessage(content=f"❌ 保存失败: {result.get('error', '未知错误')}")],
                        "phase": ReconciliationPhase.RESULT_EVALUATION.value,
                        "waiting_for_rule_name": True,
                    }
                    update.update(clear_pending_interrupt(state, "result_evaluation"))
                    return update
            except Exception as e:
                logger.error(f"保存规则失败: {e}")
                update = {
                    "messages": [AIMessage(content=f"❌ 保存失败: {str(e)}")],
                    "phase": ReconciliationPhase.RESULT_EVALUATION.value,
                    "waiting_for_rule_name": True,
                }
                update.update(clear_pending_interrupt(state, "result_evaluation"))
                return update
        
        # 游客：提示登录后保存
        # 推荐规则（有 selected_rule_id）：使用 SAVE_RULE 标记，登录后由 /api/copy-rule 复制
        # 新建规则（无 selected_rule_id 但有 generated_schema）：使用 SAVE_NEW_RULE 标记，登录后由 /api/save-pending-rule 从 thread 状态恢复并保存
        if selected_rule_id:
            update = {
                "messages": [AIMessage(content=f"[SAVE_RULE:{rule_name}:{selected_rule_id}]💡 请点击右上角「登录」按钮进行登录，登录后自动保存规则。")],
                "phase": ReconciliationPhase.COMPLETED.value,
            }
            update.update(clear_pending_interrupt(state, "result_evaluation"))
            return update
        update = {
            "messages": [AIMessage(content=f"[SAVE_NEW_RULE:{rule_name}]💡 请点击右上角「登录」按钮进行登录，登录后自动保存规则「{rule_name}」。")],
            "phase": ReconciliationPhase.COMPLETED.value,
        }
        update.update(clear_pending_interrupt(state, "result_evaluation"))
        return update
    
    # 首次进入：需为推荐规则或新建规则（有 generated_schema）才显示评估
    generated_schema = state.get("generated_schema")
    if not using_recommended and not selected_rule_id and not generated_schema:
        return {
            "messages": [],
            "phase": ReconciliationPhase.COMPLETED.value,
        }
    
    # 从 task_result 获取统计信息（推荐规则跳过preview直接执行）
    task_result = state.get("task_result") or {}
    preview_result = state.get("preview_result") or {}
    
    # 优先使用 task_result，否则使用 preview_result
    if task_result:
        summary = task_result.get("summary") or {}
        biz_count = summary.get("total_business_records", 0)
        fin_count = summary.get("total_finance_records", 0)
        estimated_match = summary.get("matched_records", 0)
    else:
        biz_count = preview_result.get("biz_count", 0)
        fin_count = preview_result.get("fin_count", 0)
        estimated_match = preview_result.get("estimated_match", 0)
    
    # 如果两者都为空，使用默认值
    if not biz_count and not fin_count and not estimated_match:
        logger.warning("task_result 和 preview_result 都为空，使用默认值")
        biz_count = fin_count = estimated_match = 0
    
    # 计算匹配率
    match_rate = 0
    if biz_count > 0:
        match_rate = (estimated_match / biz_count) * 100
    
    # 生成评估结论（不再重复显示对账结果，task_execution_node 已经显示过了）
    if match_rate >= 90:
        evaluation = "⭐⭐⭐⭐⭐ (强烈推荐)"
        conclusion = "该规则匹配度非常高，配置合理，建议保存为个人规则以便复用。"
    elif match_rate >= 70:
        evaluation = "⭐⭐⭐⭐☆ (推荐使用)"
        conclusion = "该规则匹配度较高，可以保存为个人规则。"
    elif match_rate >= 50:
        evaluation = "⭐⭐⭐☆☆ (可以使用)"
        conclusion = "该规则匹配度一般，建议根据实际情况决定是否保存。"
    else:
        evaluation = "⭐⭐☆☆☆ (不推荐)"
        conclusion = "该规则匹配度较低，建议重新配置规则。"
    
    # 只显示评估和保存提示（对账结果已在 task_execution_node 显示）
    question_text = (
        f"💡 规则适用性评估: {evaluation}\n"
        f"{conclusion}\n\n"
        f"请选择：\n"
        f"• 输入「保存」将规则保存为个人规则\n"
        f"• 输入「不要」返回字段映射界面重新配置"
    )
    
    user_response = interrupt({
        "step": "6/6",
        "step_title": "规则评估",
        "question": question_text,
        "hint": "输入「保存」或「不要」",
    })

    response_str = str(user_response).strip().lower()

    # ====== interrupt 返回后检查意图（游客模式）======
    if not auth_token:  # 游客模式
        from app.utils.workflow_intent import check_user_intent_after_interrupt_guest, handle_intent_switch_guest

        intent = await check_user_intent_after_interrupt_guest(
            user_response=user_response,
            current_phase=ReconciliationPhase.RESULT_EVALUATION.value,
            state=state
        )

        if intent != UserIntent.RESUME_WORKFLOW.value:
            logger.info(f"[游客] result_evaluation_node: 用户切换意图 {intent}")
            return await handle_intent_switch_guest(
                intent=intent,
                current_phase=ReconciliationPhase.RESULT_EVALUATION.value,
                state=state,
                user_input=response_str
            )

    if response_str in ("保存", "save", "是", "确认"):
        update = {
            "messages": [AIMessage(content="请输入规则名称，将为您保存为个人规则。")],
            "phase": ReconciliationPhase.RESULT_EVALUATION.value,
            "waiting_for_rule_name": True,
        }
        update.update(clear_pending_interrupt(state, "result_evaluation"))
        return update

    update = {
        "messages": [AIMessage(content="好的，将返回字段映射界面，您可以重新配置规则。")],
        "phase": ReconciliationPhase.FIELD_MAPPING.value,
    }
    update.update(build_reconciliation_ctx_update(state, run_id=run_id))
    update.update(clear_pending_interrupt(state, "result_evaluation"))
    return update


# ── 入口路由节点 ─────────────────────────────────────────────────────────────



__all__ = ["save_rule_node", "edit_save_node", "result_evaluation_node"]
