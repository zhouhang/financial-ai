"""验证预览节点模块

包含验证预览节点 validation_preview_node。
"""

from __future__ import annotations

import logging
import json

logger = logging.getLogger(__name__)


async def validation_preview_node(state: "AgentState") -> dict:
    """第4步 (HITL)：生成规则 schema，预览对账效果，等待用户确认。"""
    import re
    from pathlib import Path
    from app.models import AgentState, ReconciliationPhase, UserIntent
    from langchain_core.messages import AIMessage
    from langgraph.types import interrupt
    from app.utils.schema_builder import build_schema
    from app.graphs.reconciliation.helpers import (
        _expand_file_patterns,
        FILE_PATTERN_EXTENSIONS,
        _merge_json_snippets,
        _validate_and_deduplicate_rules,
        _preview_schema,
        _format_field_mappings,
        _format_rule_config_items,
    )
    from app.graphs.reconciliation.analysis_cache_helpers import (
        build_reconciliation_ctx_update,
        check_pending_interrupt,
        clear_pending_interrupt,
        compute_analysis_key,
    )

    logger.info("validation_preview_node - 开始执行")
    mappings = state.get("confirmed_mappings") or state.get("suggested_mappings", {})
    config_items = state.get("rule_config_items", [])  # 新的配置项列表
    reconciliation_ctx = state.get("reconciliation_ctx") or {}
    analyses = reconciliation_ctx.get("file_analyses") or state.get("file_analyses", [])
    run_id = state.get("workflow_run_id") or reconciliation_ctx.get("run_id") or "default"
    uploaded = reconciliation_ctx.get("uploaded_files") or state.get("uploaded_files", [])
    analysis_key = compute_analysis_key(uploaded, {
        "intent": state.get("user_intent", ""),
        "selected_rule_id": state.get("selected_rule_id", ""),
        "selected_rule_name": state.get("selected_rule_name", ""),
    })
    if check_pending_interrupt(state, "validation_preview", analysis_key, str(run_id)):
        logger.info("validation_preview_node 命中 pending_interrupt 闸门，按重放模式执行")
    logger.info(f"validation_preview_node - 初始状态: analyses数量={len(analyses)}, config_items数量={len(config_items)}")

    # ⚠️ 提取文件模式：使用带时间戳的文件名生成匹配模式，时间戳部分用*替换
    # 例如：sales_data_115959.csv → sales_data_*.csv
    biz_patterns: list[str] = []
    fin_patterns: list[str] = []

    # 调试日志：记录 analyses 的内容
    logger.info(f"validation_preview_node - 收到的 analyses 数量: {len(analyses)}")
    for idx, a in enumerate(analyses):
        logger.info(f"validation_preview_node - analyses[{idx}]: filename={a.get('filename', 'N/A')}, original_filename={a.get('original_filename', 'N/A')}, guessed_source={a.get('guessed_source', 'N/A')}")

    for a in analyses:
        src = a.get("guessed_source")
        # 使用带时间戳的文件名（filename），而不是original_filename
        filename_with_timestamp = a.get("filename", "")
        original_filename = a.get("original_filename", "")
        file_path = a.get("file_path", "")

        # ⚠️ 关键修复：检查 filename 是否真的包含时间戳
        # 如果 filename 看起来是原始文件名（与 original_filename 相同），则从 file_path 提取
        if filename_with_timestamp and original_filename and filename_with_timestamp == original_filename:
            logger.warning(f"validation_preview_node - ⚠️ 发现问题：filename({filename_with_timestamp}) == original_filename({original_filename})，这表示 filename 可能被错误设置")
            # 尝试从 file_path 中提取系统文件名（应该带时间戳）
            if file_path:
                path_obj = Path(file_path)
                extracted_filename = path_obj.name
                # 验证提取的文件名是否包含时间戳
                has_timestamp = re.search(r'_\d{6}(\.\w+)$', extracted_filename) or re.search(r'_\d+(\.\w+)$', extracted_filename)
                if has_timestamp:
                    filename_with_timestamp = extracted_filename
                    logger.info(f"validation_preview_node - ✅ 修正：从 file_path 提取带时间戳的文件名: {filename_with_timestamp}")
                else:
                    logger.error(f"validation_preview_node - ❌ 从 file_path 提取的文件名也没有时间戳: {extracted_filename}，这表示文件上传阶段可能有问题")

        # 如果 filename 不包含时间戳（不包含 _ 后跟数字），尝试从 file_path 中提取
        elif filename_with_timestamp and not re.search(r'_\d{6}(\.\w+)$', filename_with_timestamp) and not re.search(r'_\d+(\.\w+)$', filename_with_timestamp):
            # 从 file_path 中提取文件名
            if file_path:
                path_obj = Path(file_path)
                extracted_filename = path_obj.name
                # 如果提取的文件名包含时间戳，使用它
                if re.search(r'_\d{6}(\.\w+)$', extracted_filename) or re.search(r'_\d+(\.\w+)$', extracted_filename):
                    logger.warning(f"validation_preview_node - filename({filename_with_timestamp}) 没有时间戳，从 file_path 提取: {extracted_filename}")
                    filename_with_timestamp = extracted_filename

        if not filename_with_timestamp:
            logger.warning(f"validation_preview_node - 跳过文件（没有 filename）: original_filename={original_filename}, file_path={file_path}")
            continue

        # 详细的调试日志
        logger.info(f"validation_preview_node - 处理文件: filename={filename_with_timestamp}, original_filename={original_filename}, file_path={file_path}, source={src}")

        # 将时间戳部分替换为*通配符
        # 匹配格式：filename_HHMMSS.ext 或 filename_数字.ext
        # 例如：sales_data_115959.csv → sales_data_*.csv
        # 例如：1767597466118_134019.csv → 1767597466118_*.csv
        pattern = filename_with_timestamp

        # 首先尝试匹配 _HHMMSS 格式（6位数字，时间戳格式）
        # 例如：1767597466118_134019.csv → 1767597466118_*.csv
        pattern = re.sub(r'_(\d{6})(\.\w+)$', r'_*\2', pattern)

        # 如果上面没匹配到，尝试匹配其他数字后缀格式（任意长度的数字）
        # 例如：filename_12345.csv → filename_*.csv
        if pattern == filename_with_timestamp:
            pattern = re.sub(r'_(\d+)(\.\w+)$', r'_*\2', pattern)

        # 如果还是没匹配到，说明文件名本身可能不包含时间戳
        # 这是一个诊断点，表示上游可能出现问题
        if pattern == filename_with_timestamp:
            logger.error(f"validation_preview_node - ❌ 警告：无法从 filename={filename_with_timestamp} 生成时间戳通配符，这可能导致对账无法匹配带时间戳的文件")
            # 修复：同时生成原始文件名和带时间戳的文件名模式
            # 例如：1767597466118.csv → ['1767597466118.csv', '1767597466118_*.csv']
            name_parts = filename_with_timestamp.rsplit('.', 1)
            if len(name_parts) == 2:
                # 生成两个模式：原始文件名 + 带时间戳的通配符
                patterns_to_add = [
                    filename_with_timestamp,  # 原始文件名，例如 1767597466118.csv
                    f"{name_parts[0]}_*.{name_parts[1]}"  # 带时间戳的通配符，例如 1767597466118_*.csv
                ]
            else:
                patterns_to_add = [filename_with_timestamp]
        else:
            patterns_to_add = [pattern]

        # 调试日志：记录生成的 pattern（显示是否成功生成通配符）
        has_wildcard = any('*' in p for p in patterns_to_add)
        logger.info(f"validation_preview_node - 生成的 file_pattern: {patterns_to_add} (是否包含通配符: {has_wildcard}, 来源: {src}, 原始 filename: {filename_with_timestamp})")

        # Excel/CSV 格式扩展为所有支持类型（.xlsx/.xls/.xlsm/.xlsb/.csv）
        expanded_patterns = []
        for p in patterns_to_add:
            expanded_patterns.extend(_expand_file_patterns(p))

        if src == "business":
            for p in expanded_patterns:
                if p not in biz_patterns:
                    biz_patterns.append(p)
        elif src == "finance":
            for p in expanded_patterns:
                if p not in fin_patterns:
                    fin_patterns.append(p)

    # 默认模式（如果没有找到文件）- 包含所有 Excel + CSV 格式
    if not biz_patterns:
        biz_patterns = [f"*{e}" for e in FILE_PATTERN_EXTENSIONS]
    if not fin_patterns:
        fin_patterns = [f"*{e}" for e in FILE_PATTERN_EXTENSIONS]

    # 调试日志：记录最终生成的 file_pattern
    logger.info(f"validation_preview_node - 最终生成的 file_pattern: business={biz_patterns}, finance={fin_patterns}")

    biz_field_roles = mappings.get("business", {})
    fin_field_roles = mappings.get("finance", {})

    # 先构建基础 schema（使用默认值）
    base_schema = build_schema(
        description="用户自定义对账规则",
        business_file_patterns=biz_patterns,
        finance_file_patterns=fin_patterns,
        business_field_roles=biz_field_roles,
        finance_field_roles=fin_field_roles,
        order_id_pattern=None,  # 从配置项中获取
        amount_tolerance=0.1,  # 从配置项中获取
        check_order_status=True,  # 从配置项中获取
    )

    # 将用户添加的配置项合并到基础schema中
    # ⚠️ 保护 file_pattern，防止被覆盖
    protected_file_patterns = {
        "business": biz_patterns.copy(),
        "finance": fin_patterns.copy(),
    }

    if config_items:
        schema = _merge_json_snippets(base_schema, config_items)
        # 关键修复：合并后立即验证和去重规则，防止重复处理同一字段
        schema = _validate_and_deduplicate_rules(schema)
    else:
        schema = base_schema

    # 强制恢复被保护的 file_pattern，确保在任何合并后都保留正确的模式
    # 这是关键修复：无论合并过程如何，都要确保 file_pattern 是正确的
    if "data_sources" in schema:
        if "business" in schema["data_sources"]:
            schema["data_sources"]["business"]["file_pattern"] = protected_file_patterns["business"]
        else:
            # 如果 business 不存在，创建它
            schema["data_sources"]["business"] = {"file_pattern": protected_file_patterns["business"]}

        if "finance" in schema["data_sources"]:
            schema["data_sources"]["finance"]["file_pattern"] = protected_file_patterns["finance"]
        else:
            # 如果 finance 不存在，创建它
            schema["data_sources"]["finance"] = {"file_pattern": protected_file_patterns["finance"]}

    # 再次验证 file_pattern 是否正确设置
    biz_file_pattern = schema.get("data_sources", {}).get("business", {}).get("file_pattern", [])
    fin_file_pattern = schema.get("data_sources", {}).get("finance", {}).get("file_pattern", [])
    logger.info(f"validation_preview_node - 修复后的 schema file_pattern: business={biz_file_pattern}, finance={fin_file_pattern}")

    # 调试日志：记录合并后的 schema 中的 file_pattern
    biz_patterns_after_merge = schema.get("data_sources", {}).get("business", {}).get("file_pattern", [])
    fin_patterns_after_merge = schema.get("data_sources", {}).get("finance", {}).get("file_pattern", [])
    logger.info(f"validation_preview_node - 合并后的 schema file_pattern: business={biz_patterns_after_merge}, finance={fin_patterns_after_merge}")

    # 简单预览（统计匹配信息）
    preview = _preview_schema(schema, analyses)

    # 字段映射展示（bullet_style 与数据统计一致）
    mapping_display = _format_field_mappings(mappings, analyses, bullet_style=True)

    # 构建文件名映射（优先用 original_filename，用户更易识别）
    file_names = {}
    for a in analyses:
        src = a.get("guessed_source", "")
        name = a.get("original_filename") or a.get("filename", "")
        if src == "business" and name:
            file_names["business"] = name
        elif src == "finance" and name:
            file_names["finance"] = name
    if not file_names and analyses:
        file_names["business"] = analyses[0].get("original_filename") or analyses[0].get("filename", "文件1") if len(analyses) > 0 else "文件1"
        file_names["finance"] = analyses[1].get("original_filename") or analyses[1].get("filename", "文件2") if len(analyses) > 1 else "文件2"

    # 用户配置的具体规则（第3步添加的配置项，使用真实文件名）
    config_display = (
        _format_rule_config_items(config_items, file_names)
        if config_items
        else "（无额外配置，使用默认规则）"
    )

    preview_text = (
        f"✅ **第4步：确认规则并执行对账**\n\n"
        f"我已经根据你的配置生成了对账规则！预览结果：\n\n"
        f"📊 **数据统计**\n"
        f"• 业务记录数：{preview.get('biz_count', 'N/A')}\n"
        f"• 财务记录数：{preview.get('fin_count', 'N/A')}\n"
        f"• 预计可匹配：{preview.get('estimated_match', 'N/A')}条\n\n"
        f"🔗 **字段映射**\n\n{mapping_display}\n\n\n"
        f"📋 **你配置的规则**\n{config_display}\n\n"
        f"规则看起来合理吗？"
    )

    user_response = interrupt({
        "step": "4/4",
        "step_title": "确认并执行对账",
        "question": preview_text,
        "preview": preview,
        "schema_summary": {
            "validations": len(schema.get("custom_validations", [])),
            "biz_patterns": biz_patterns,
            "fin_patterns": fin_patterns,
        },
        "hint": "• 回复「确认」执行对账  • 回复「调整」重新配置",
    })

    response_str = str(user_response).strip()

    # ====== interrupt 返回后检查意图（游客模式）======
    auth_token = state.get("auth_token", "")
    if not auth_token:  # 游客模式
        from app.utils.workflow_intent import check_user_intent_after_interrupt_guest, handle_intent_switch_guest

        intent = await check_user_intent_after_interrupt_guest(
            user_response=user_response,
            current_phase=ReconciliationPhase.VALIDATION_PREVIEW.value,
            state=state
        )

        if intent != UserIntent.RESUME_WORKFLOW.value:
            logger.info(f"[游客] validation_preview_node: 用户切换意图 {intent}")
            return await handle_intent_switch_guest(
                intent=intent,
                current_phase=ReconciliationPhase.VALIDATION_PREVIEW.value,
                state=state,
                user_input=response_str
            )

    if response_str in ("调整", "重新配置", "重来", "adjust"):
        update = {
            "messages": [AIMessage(content="好的，让我们重新配置规则参数。")],
            "phase": ReconciliationPhase.RULE_CONFIG.value,
            "generated_schema": None,
        }
        update.update(clear_pending_interrupt(state, "validation_preview"))
        return update

    # ⚠️ 功能关键：与推荐规则流程一致，必须先执行对账，再在 result_evaluation 中提示保存
    # 绝不在此处进入 save_rule（先对账再保存）
    logger.info("validation_preview_node: 用户确认规则 -> phase=TASK_EXECUTION，将执行对账")
    update = {
        "messages": [AIMessage(content="✅ 规则确认完毕，正在执行对账...")],
        "generated_schema": schema,
        "preview_result": preview,
        "selected_rule_name": "新规则_待确认",  # 用于 task_execution 显示
        "phase": ReconciliationPhase.TASK_EXECUTION.value,
    }
    update.update(build_reconciliation_ctx_update(state, run_id=run_id))
    update.update(clear_pending_interrupt(state, "validation_preview"))
    return update




__all__ = ["validation_preview_node"]
