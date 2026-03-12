"""规则推荐节点模块

包含规则推荐节点 rule_recommendation_node。
"""

from __future__ import annotations

import logging
import hashlib
import json

logger = logging.getLogger(__name__)


async def rule_recommendation_node(state: AgentState) -> dict:
    """第2.5步 (HITL)：根据字段映射推荐已有规则，供用户选择。

    流程：
    1. 计算当前字段映射的哈希值
    2. 调用 MCP 工具搜索匹配规则
    3. 如果哈希匹配结果少，用字段名匹配补充
    4. 展示推荐结果，供用户选择
    5. 用户选择推荐规则或创建新规则
    """
    from models import AgentState, ReconciliationPhase, UserIntent
    from langchain_core.messages import AIMessage
    from langgraph.types import interrupt
    from tools.mcp_client import call_mcp_tool
    from graphs.reconciliation.helpers import _get_file_names_from_rule_template
    from graphs.reconciliation.analysis_cache_helpers import (
        build_reconciliation_ctx_update,
        check_pending_interrupt,
        clear_pending_interrupt,
        compute_analysis_key,
    )
    import hashlib
    import json
    
    logger.info(f"rule_recommendation_node 进入，当前 phase={state.get('phase', '')}")
    
    mappings = state.get("confirmed_mappings") or state.get("suggested_mappings", {})
    auth_token = state.get("auth_token", "")
    reconciliation_ctx = state.get("reconciliation_ctx") or {}
    file_analyses = reconciliation_ctx.get("file_analyses") or state.get("file_analyses", [])
    run_id = state.get("workflow_run_id") or reconciliation_ctx.get("run_id") or "default"
    uploaded = reconciliation_ctx.get("uploaded_files") or state.get("uploaded_files", [])
    analysis_key = compute_analysis_key(uploaded, {
        "intent": state.get("user_intent", ""),
        "selected_rule_id": state.get("selected_rule_id", ""),
        "selected_rule_name": state.get("selected_rule_name", ""),
    })
    if check_pending_interrupt(state, "rule_recommendation", analysis_key, str(run_id)):
        logger.info("rule_recommendation_node 命中 pending_interrupt 闸门，按重放模式执行")
    
    # 计算字段映射哈希
    def compute_hash(m: dict) -> str:
        fields = []
        for source in ["business", "finance"]:
            for role in ["order_id", "amount", "date"]:
                value = m.get(source, {}).get(role, "")
                if isinstance(value, list):
                    value = ",".join(sorted(value))
                elif value:
                    value = str(value)
                else:
                    value = ""
                fields.append(f"{source}.{role}={value}")
        fields.sort()
        hash_input = "|".join(fields)
        return hashlib.md5(hash_input.encode()).hexdigest()
    
    field_hash = compute_hash(mappings)
    logger.info(f"字段映射哈希: {field_hash}")
    
    # 调用 MCP 工具搜索匹配规则（基于哈希）
    recommended = []
    guest_token = state.get("guest_token", "")
    
    if auth_token:
        try:
            result = await call_mcp_tool("search_rules_by_mapping", {
                "auth_token": auth_token,
                "field_mapping_hash": field_hash,
                "limit": 5,
            })
            if result.get("success"):
                recommended = result.get("rules", [])
                logger.info(f"基于哈希找到 {len(recommended)} 个匹配规则")
        except Exception as e:
            logger.error(f"搜索推荐规则失败: {e}")
    elif guest_token:
        # 游客模式：使用 search_rules_by_mapping 搜索匹配规则
        try:
            result = await call_mcp_tool("search_rules_by_mapping", {
                "guest_token": guest_token,
                "field_mapping_hash": field_hash,
                "limit": 5,
            })
            if result.get("success"):
                recommended = result.get("rules", [])
                logger.info(f"游客模式基于哈希找到 {len(recommended)} 个匹配规则")
        except Exception as e:
            logger.error(f"游客搜索推荐规则失败: {e}")
    
    # 如果哈希匹配结果少于5条，用字段名匹配补充
    from .helpers import match_rules_by_field_names, calculate_match_percentage, get_match_reason, KEY_FIELD_ALIASES
    
    if len(recommended) < 5 and file_analyses:
        # 构建文件列名字典
        file_columns = {}
        for analysis in file_analyses:
            source = analysis.get("guessed_source", "")
            columns = analysis.get("columns", [])
            if source:
                file_columns[source] = columns
        
        if file_columns:
            try:
                # 获取所有规则列表（不含 rule_template）- 支持游客模式
                list_args = {"status": "active"}
                if auth_token:
                    list_args["auth_token"] = auth_token
                elif guest_token:
                    list_args["guest_token"] = guest_token
                list_result = await call_mcp_tool("list_reconciliation_rules", list_args)
                if list_result.get("success"):
                    all_rules = list_result.get("rules", [])
                    
                    # 获取当前用户ID，过滤掉用户自己的规则
                    current_user = state.get("current_user", {})
                    current_user_id = current_user.get("id") if isinstance(current_user, dict) else None
                    logger.info(f"[DEBUG] current_user: {current_user}, current_user_id: {current_user_id}")
                    
                    if current_user_id:
                        original_count = len(all_rules)
                        all_rules = [r for r in all_rules if str(r.get("created_by")) != str(current_user_id)]
                        logger.info(f"过滤用户自己的规则: {original_count} -> {len(all_rules)} 条规则")
                    
                    # 过滤掉已通过哈希匹配的规则
                    matched_ids = {r.get("id") for r in recommended}
                    remaining_rule_ids = [r.get("id") for r in all_rules if r.get("id") not in matched_ids]
                    
                    # 使用批量 API 获取规则详情（含 rule_template）- 支持游客模式
                    rules_with_template = []
                    if remaining_rule_ids:
                        batch_args = {"rule_ids": remaining_rule_ids[:100]}
                        if auth_token:
                            batch_args["auth_token"] = auth_token
                        elif guest_token:
                            batch_args["guest_token"] = guest_token
                        batch_result = await call_mcp_tool("batch_get_reconciliation_rules", batch_args)
                        if batch_result.get("success"):
                            rules_with_template = batch_result.get("rules", [])
                    
                    # 字段名匹配
                    field_matches = match_rules_by_field_names(file_columns, rules_with_template)
                    
                    # 添加字段名匹配的结果
                    for rule, score, matched_fields in field_matches:
                        match_pct = calculate_match_percentage(matched_fields)
                        # 只添加匹配度 >= 90% 的规则
                        if match_pct >= 90 and len(recommended) < 3:
                            rule["_match_score"] = score
                            rule["_matched_fields"] = matched_fields
                            rule["_match_reason"] = get_match_reason(matched_fields)
                            recommended.append(rule)
                    
                    logger.info(f"字段名匹配后共有 {len(recommended)} 个推荐规则（匹配度>=90%）")
            except Exception as e:
                logger.error(f"字段名匹配补充失败: {e}")
    
    # 过滤：只保留匹配度 >= 90% 的规则，最多3个
    # 注意：哈希匹配的规则没有 _matched_fields（key 不存在），视为 100% 匹配
    # 字段名匹配的规则有 _matched_fields（可能为空列表），需计算匹配度
    high_match_rules = []
    for rule in recommended:
        if "_matched_fields" not in rule:
            # 哈希匹配命中，直接视为高匹配度
            high_match_rules.append(rule)
        else:
            matched_fields = rule["_matched_fields"]
            match_pct = calculate_match_percentage(matched_fields)
            if match_pct >= 90:
                high_match_rules.append(rule)
        if len(high_match_rules) >= 3:
            break
    
    recommended = high_match_rules
    
    # 如果没有高匹配度的推荐规则，直接跳过推荐流程
    if not recommended:
        logger.info("没有匹配度>=90%的规则，跳过推荐流程")
        update = {
            "messages": [],
            "recommended_rules": [],
            "using_recommended_rule": False,
            "rule_config_items": [],  # 新建规则时第三步从空配置开始
            "phase": ReconciliationPhase.FIELD_MAPPING.value,
        }
        update.update(clear_pending_interrupt(state, "rule_recommendation"))
        return update
    
    # 构建推荐结果展示（优化格式）
    rule_list_text = []
    for idx, rule in enumerate(recommended[:3], 1):
        name = rule.get("name", "未知规则")
        template = rule.get("rule_template", {})
        if isinstance(template, str):
            template = json.loads(template)
        
        # 计算匹配度
        matched_fields = rule.get("_matched_fields", [])
        match_reason = rule.get("_match_reason", "")
        match_percentage = calculate_match_percentage(matched_fields)
        
        biz_fields = template.get("data_sources", {}).get("business", {}).get("field_roles", {})
        fin_fields = template.get("data_sources", {}).get("finance", {}).get("field_roles", {})

        def _fmt_col(v):
            if isinstance(v, list):
                return "、".join(str(x) for x in v)
            return str(v) if v else ""

        mapping_lines = []
        for role in biz_fields.keys() & fin_fields.keys():
            biz_col = biz_fields.get(role)
            fin_col = fin_fields.get(role)
            if biz_col and fin_col:
                mapping_lines.append(f"{_fmt_col(biz_col)}↔{_fmt_col(fin_col)}")

        custom_validations = template.get("custom_validations", [])
        rule_config_text = template.get("rule_config_text", "")
        data_cleaning_rules = template.get("data_cleaning_rules", {})
        file_labels = _get_file_names_from_rule_template(template)
        
        # 构建配置规则显示，从 data_cleaning_rules 获取
        config_items = []
        
        # 从 data_cleaning_rules 提取每个有 description 的规则项
        for src in ("business", "finance"):
            src_label = file_labels.get(src, "文件1" if src == "business" else "文件2")
            src_rules = data_cleaning_rules.get(src, {})
            # field_transforms
            for t in src_rules.get("field_transforms", []):
                desc = t.get("description", "").strip()
                if desc:
                    config_items.append(f"{src_label}：{desc}")
            # aggregations
            for agg in src_rules.get("aggregations", []):
                desc = agg.get("description", "").strip()
                if desc:
                    config_items.append(f"{src_label}：{desc}")
            # row_filters
            for rf in src_rules.get("row_filters", []):
                desc = rf.get("description", "").strip()
                if desc:
                    config_items.append(f"{src_label}：{desc}")

        br = "  \n"
        rule_text = f"**{idx}. {name}** ({match_percentage}%){br}"
        if mapping_lines:
            rule_text += f"**字段映射：**{br}"
            rule_text += br.join(f"• {line}" for line in mapping_lines)
        if config_items:
            if mapping_lines:
                rule_text += "\n\n"
            rule_text += f"**配置规则：**{br}"
            for cfg in config_items:
                rule_text += f"• {cfg}{br}"

        rule_list_text.append(rule_text)

    recommendation_text = "\n\n".join(rule_list_text)

    question_text = (
        f"**推荐规则**\n\n{recommendation_text}\n\n"
        f"输入数字（1/2/3）选择，或「继续」"
    )

    user_response = interrupt({
        "step": "2.5/4",
        "step_title": "规则推荐",
        "question": question_text,
        "recommended_rules": recommended,
        "hint": "数字选择 或 「继续」",
    })
    
    response_str = str(user_response).strip()

    # 上传后自动占位消息可能被同轮 resume 透传到此 interrupt，需忽略并保持在推荐步骤。
    if not response_str or (response_str.startswith("已上传") and response_str.endswith("请处理。")):
        update = {
            "messages": [],
            "recommended_rules": recommended,
            "phase": ReconciliationPhase.RULE_RECOMMENDATION.value,
        }
        update.update(build_reconciliation_ctx_update(state, run_id=run_id))
        update.update(clear_pending_interrupt(state, "rule_recommendation"))
        return update

    logger.info(f"rule_recommendation_node 处理输入: response={response_str}, using_recommended_rule={state.get('using_recommended_rule')}, selected_rule_id={state.get('selected_rule_id')}, current_phase={state.get('phase')}")

    # ====== interrupt 返回后检查意图（支持游客和登录模式）======
    if not auth_token:  # 游客模式
        from utils.workflow_intent import check_user_intent_after_interrupt_guest, handle_intent_switch_guest

        intent = await check_user_intent_after_interrupt_guest(
            user_response=user_response,
            current_phase=ReconciliationPhase.RULE_RECOMMENDATION.value,
            state=state
        )

        if intent != UserIntent.RESUME_WORKFLOW.value:
            logger.info(f"[游客] rule_recommendation_node: 用户切换意图 {intent}")
            return await handle_intent_switch_guest(
                intent=intent,
                current_phase=ReconciliationPhase.RULE_RECOMMENDATION.value,
                state=state,
                user_input=response_str
            )
    else:  # 登录模式
        from utils.workflow_intent import check_user_intent_after_interrupt, handle_intent_switch

        intent = await check_user_intent_after_interrupt(
            user_response=user_response,
            current_phase=ReconciliationPhase.RULE_RECOMMENDATION.value,
            state=state
        )

        if intent != UserIntent.RESUME_WORKFLOW.value:
            logger.info(f"[登录] rule_recommendation_node: 用户切换意图 {intent}")
            return await handle_intent_switch(intent, ReconciliationPhase.RULE_RECOMMENDATION.value, state)

    # 解析用户选择数字 → 直接执行对账（不再询问确认）
    response_lower = response_str.lower()
    if response_lower.isdigit():
        idx = int(response_str) - 1
        if 0 <= idx < len(recommended):
            selected = recommended[idx]
            
            # 加载推荐规则的模板
            template = selected.get("rule_template", {})
            if isinstance(template, str):
                template = json.loads(template)
            
            # 提取字段映射到 confirmed_mappings
            biz_roles = template.get("data_sources", {}).get("business", {}).get("field_roles", {})
            fin_roles = template.get("data_sources", {}).get("finance", {}).get("field_roles", {})
            
            # 提取规则配置信息
            rule_config_text = template.get("rule_config_text", "")
            custom_validations = template.get("custom_validations", [])
            data_cleaning_rules = template.get("data_cleaning_rules", {})
            
            # 构建 rule_config_items（用于预览显示）- 兼容字段名
            rule_config_items = []
            if rule_config_text:
                rule_config_items.append({"type": "rule_config", "content": rule_config_text})
            if custom_validations:
                for v in custom_validations:
                    rule_config_items.append({"type": "validation", "name": v.get("name", ""), "content": v.get("detail_template", "")})
            
            # 提取文件清洗规则描述
            cleaning_descriptions = []
            for source in ["business", "finance"]:
                source_rules = data_cleaning_rules.get(source, {})
                for rule_type, rules in source_rules.items():
                    if isinstance(rules, list):
                        for r in rules:
                            desc = r.get("description", "")
                            if desc:
                                cleaning_descriptions.append(f"{source}: {desc}")
            
            logger.info(f"用户选择推荐规则 {selected['name']}，直接执行对账，phase=TASK_EXECUTION")
            
            # 用户选择数字后直接执行对账，不再询问确认
            update = {
                "messages": [AIMessage(content=f"✅ 已选择规则「{selected['name']}」，正在开始对账...")],
                "recommended_rules": recommended,
                "selected_rule_id": selected["id"],
                "selected_rule_name": selected.get("name", ""),
                "using_recommended_rule": True,
                "confirmed_mappings": {"business": biz_roles, "finance": fin_roles},
                "generated_schema": template,
                "rule_config_items": rule_config_items,
                "rule_config_text": rule_config_text,
                "cleaning_descriptions": cleaning_descriptions,
                "phase": ReconciliationPhase.TASK_EXECUTION.value,  # 直接进入任务执行
            }
            update.update(build_reconciliation_ctx_update(state, run_id=run_id))
            update.update(clear_pending_interrupt(state, "rule_recommendation"))
            return update
    
    # 用户选择创建新规则
    update = {
        "messages": [AIMessage(content="好的，将继续创建新规则。")],
        "recommended_rules": recommended,
        "selected_rule_id": None,
        "using_recommended_rule": False,
        "rule_config_items": [],  # 新建规则时清空，避免残留旧格式配置
        "phase": ReconciliationPhase.FIELD_MAPPING.value,  # 回到字段映射流程
    }
    update.update(build_reconciliation_ctx_update(state, run_id=run_id))
    update.update(clear_pending_interrupt(state, "rule_recommendation"))
    return update





__all__ = ["rule_recommendation_node"]
