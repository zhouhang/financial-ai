"""对账节点函数模块

包含对账工作流中的所有节点函数：
- file_analysis_node: 分析上传的文件
- field_mapping_node: 字段映射 (HITL)
- rule_config_node: 规则配置 (HITL)
- validation_preview_node: 验证预览 (HITL)
- save_rule_node: 保存规则
- edit_*_node: 编辑规则相关节点
- entry_router_node: 子图入口路由
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage
from langgraph.types import interrupt

from app.models import AgentState, ReconciliationPhase
from app.utils.schema_builder import build_schema
from app.tools.mcp_client import call_mcp_tool

from .helpers import (
    FILE_PATTERN_EXTENSIONS,
    _expand_file_patterns,
    _rewrite_schema_transforms_to_mapped_fields,
    _calculate_fuzzy_match_score,
    _find_matching_items,
    _format_operations_summary,
    _adjust_field_mappings_with_llm,
    _format_field_mappings,
    _rule_template_to_mappings,
    _rule_template_to_config_items,
    _format_edit_field_mappings,
    _build_field_mapping_text,
    _build_rule_config_text,
    _guess_field_mappings,
    _preview_schema,
    _build_dummy_analyses_from_mappings,
    _format_rule_config_items,
    _validate_and_deduplicate_rules,
    _merge_json_snippets,
    _translate_rule_name_to_english,
)
from .parsers import _parse_rule_config_json_snippet

logger = logging.getLogger(__name__)


# ── 节点函数 ─────────────────────────────────────────────────────────────────

async def file_analysis_node(state: AgentState) -> dict:
    """第1步：分析上传的文件，提取列名和样本数据。
    
    ⚠️ 展平到主图后，interrupt/resume 不会 replay 此节点，无需缓存检查。
    """
    uploaded = state.get("uploaded_files", [])
    if not uploaded:
        # 使用 interrupt 等待用户上传文件
        user_response = interrupt({
            "step": "1/4",
            "step_title": "上传文件",
            "question": "📤 **第1步：上传文件**\n\n请上传需要对账的文件（业务数据和财务数据各一个 Excel/CSV 文件）。",
            "hint": "💡 上传文件后，点击发送按钮或直接发送消息",
        })
        # interrupt 返回后，重新检查文件
        uploaded = state.get("uploaded_files", [])
        if not uploaded:
            # 仍然没有文件，返回提示消息
            return {
                "messages": [AIMessage(content="⚠️ 未检测到文件上传，请上传文件后再试。")],
            "phase": ReconciliationPhase.FILE_ANALYSIS.value,
                "file_analyses": [],  # 空列表，路由函数会返回END
            }

    # 调用 MCP 工具分析文件（包括 LLM 文件类型判断）
    # 提取文件路径和原始文件名映射
    file_paths = []
    original_filenames_map = {}
    
    for item in uploaded:
        if isinstance(item, dict):
            file_path = item.get("file_path", "")
            original_filename = item.get("original_filename", "")
            if file_path:
                file_paths.append(file_path)
                if original_filename:
                    original_filenames_map[file_path] = original_filename
        else:
            # 兼容旧格式（直接是文件路径字符串）
            file_paths.append(item)
    
    try:
        analyze_args = {"file_paths": file_paths}
        if original_filenames_map:
            analyze_args["original_filenames"] = original_filenames_map
        result = await call_mcp_tool("analyze_files", analyze_args)
        if not result.get("success"):
            error_msg = result.get("error", "文件分析失败")
            return {
                "messages": [AIMessage(content=f"❌ {error_msg}")],
                "phase": ReconciliationPhase.FILE_ANALYSIS.value,
                "file_analyses": [],
            }
        
        analyses = result.get("analyses", [])
    except Exception as e:
        logger.error(f"调用 MCP 文件分析工具失败: {e}", exc_info=True)
        return {
            "messages": [AIMessage(content=f"❌ 文件分析失败: {str(e)}")],
            "phase": ReconciliationPhase.FILE_ANALYSIS.value,
            "file_analyses": [],
        }

    # 构建文件分析摘要（只显示文件名和基本信息，不显示业务/财务标签）
    summary_parts: list[str] = ["📊 **第1步：文件分析完成**\n"]
    for a in analyses:
        summary_parts.append(f"📄 **{a['filename']}**")
        summary_parts.append(f"   • 列数: {len(a.get('columns', []))}  行数: {a.get('row_count', 0)}")
        summary_parts.append(f"   • 列名: {', '.join(a.get('columns', [])[:10])}{'...' if len(a.get('columns', [])) > 10 else ''}")
        summary_parts.append("")

    summary_parts.append("正在为你生成字段映射建议...")
    msg = "\n".join(summary_parts)

    # 使用 LLM 猜测字段映射（在后台完成，不显示给用户）
    suggested = _guess_field_mappings(analyses)

    return {
        "messages": [AIMessage(content=msg)],
        "file_analyses": analyses,
        "suggested_mappings": suggested,
        "phase": ReconciliationPhase.FIELD_MAPPING.value,
    }


def field_mapping_node(state: AgentState) -> dict:
    """第2步 (HITL)：等待用户确认或修改字段映射。
    
    ⚠️ 展平到主图后，interrupt/resume 直接恢复到此节点，无需首次进入检查。
    """
    logger.info(f"field_mapping_node 进入，当前 phase={state.get('phase', '')}")
    
    # 优先使用 suggested_mappings（可能已被调整）
    suggested = state.get("suggested_mappings", {})
    confirmed = suggested.copy() if suggested else {}
    analyses = state.get("file_analyses", [])
    
    # 检查是否有待处理的调整意见
    adjustment_feedback = state.get("mapping_adjustment_feedback")
    
    # 构建详细的字段映射展示
    mapping_display = _format_field_mappings(confirmed, analyses)
    
    # 构建问题文本
    if adjustment_feedback:
        # 如果有调整反馈，先显示反馈
        question_text = f"📋 **第2步：确认字段映射**\n\n{adjustment_feedback}\n\n当前字段对应关系：\n{mapping_display}\n\n**请确认是否正确？**"
    else:
        question_text = f"📋 **第2步：确认字段映射**\n\n我已经分析了这两个文件，为你建议了以下字段对应关系：\n{mapping_display}\n\n**这些对应关系是否正确？**"
    
    # interrupt 暂停，等待用户输入
    user_response = interrupt({
        "step": "2/4",
        "step_title": "确认字段映射",
        "question": question_text,
        "suggested_mappings": confirmed,
        "hint": '''💡 **操作提示**：
  • 如果正确，回复"确认"继续
  • **调整现有字段**（修改/删除）：例如"文件1的订单号改为X", "文件2删除status"
  • **添加新字段**：例如"文件1添加status对应Y", "两个文件都添加status"
  • **混合操作**：例如"文件1: 订单号改为X，添加status为Y; 文件2: 删除status"
  • 详细描述你需要的所有更改，系统会一次性生成所有操作''',
    })

    response_str = str(user_response).strip()

    # 忽略文件上传的默认消息或空消息
    if not response_str or (response_str.startswith("已上传") and response_str.endswith("请处理。")):
        # 清除调整反馈，重新 interrupt
        return {
            "messages": [],
            "mapping_adjustment_feedback": None,
            "phase": ReconciliationPhase.FIELD_MAPPING.value,
        }
    
    response_lower = response_str.lower()

    # 用户确认，进入下一步
    if response_lower in ("确认", "ok", "yes", "确定", "对", "没问题", "正确"):
        return {
            "messages": [AIMessage(content="✅ 字段映射已确认。接下来配置对账规则。")],
        "confirmed_mappings": confirmed,
            "mapping_adjustment_feedback": None,  # 清除反馈
        "phase": ReconciliationPhase.RULE_CONFIG.value,
    }

    # 用户需要调整，使用 LLM 解析调整意见并更新映射
    logger.info(f"用户调整意见: {response_str}")
    
    # 使用 LLM 调整映射（返回调整后的映射和操作列表）
    adjusted_mappings, operations = _adjust_field_mappings_with_llm(confirmed, response_str, analyses)
    
    # 检查映射是否有变化（且 operations 非空，避免显示无效更新）
    if adjusted_mappings != confirmed and operations:
        operations_summary = _format_operations_summary(operations)
        adjustment_msg = f"✅ 已根据你的调整意见更新字段映射：\n{operations_summary}"
        logger.info("字段映射已更新")
    else:
        adjustment_msg = f"⚠️ 已记录你的调整意见，但未能自动解析。请详细描述需要修改的地方：\n\n> {response_str}"
        logger.warning("字段映射未更新（LLM 解析失败或无变化）")

    return {
        "messages": [AIMessage(content=adjustment_msg)],
        "suggested_mappings": adjusted_mappings,  # 更新映射
        "mapping_adjustment_feedback": adjustment_msg,
        "phase": ReconciliationPhase.FIELD_MAPPING.value,  # 保持在当前阶段
    }


def rule_config_node(state: AgentState) -> dict:
    """第3步 (HITL)：增量式配置规则参数，支持自然语言添加/删除配置项。
    
    新的配置体验：
    1. 初始配置为空，等待用户输入
    2. 用户输入配置，LLM解析为JSON片段并添加到"当前配置"
    3. 用户可以删除已添加的配置
    4. 用户确认后完成配置
    """
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
        # 初始状态：只显示提示，不显示"当前配置"标题
        question_text = """⚙️ **第3步：配置对账规则参数**

请描述对账规则的配置要求。支持以下类型的配置：

**全局配置**（如金额容差）：
• "金额容差0.1元"

**聚合类配置**（按字段合并、金额累加等，放入 business/finance 的 aggregations，不放全局）：
• 未指定文件："按订单号合并金额" → 两个文件都配置
• 指定文件："文件1按订单号合并" → 只配置业务文件

**针对业务数据(文件1)的配置**：
• "业务文件的product_price除以100"
• "文件1的订单号去掉开头单引号，并截取前21位"

**针对财务数据(文件2)的配置**：
• "财务文件的发生-除以100"
• "文件2的订单号去除空格"

**为两个文件配置不同规则**：
• "文件1的金额除以100，文件2的金额不变"

⚠️ 系统会根据字段名自动识别字段所属的文件（以字段映射为准）。
例如：product_price 在财务数据(文件2)中 → 只在财务文件配置；在业务数据(文件1)中 → 只在业务文件配置

**请输入你的配置要求：**"""
    else:
        # 有配置项时：显示当前配置列表
        config_display = _format_rule_config_items(config_items, file_names)
        question_text = f"""⚙️ **第3步：配置对账规则参数**

当前配置：
{config_display}

你可以：
• 继续添加配置（为业务文件、财务文件或全局配置新规则）
• 删除配置（如"删除金额容差"、"去掉订单号过滤"）
• 回复"确认"完成配置

**请输入：**"""
    
    # interrupt 暂停，等待用户输入
    user_response = interrupt({
        "step": "3/4",
        "step_title": "配置规则参数",
        "question": question_text,
        "current_config_items": config_items,
        "hint": '''💡 **操作提示**：
  • 系统智能识别字段所属的文件（业务或财务）
  • 支持针对单个文件的规则配置
  • 支持为两个文件配置不同的转换规则
  • 完成后回复"确认"继续''',
    })

    response_str = str(user_response).strip()
    logger.info(f"rule_config interrupt 返回，用户输入: {response_str}")
    
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
        new_item = {
            "json_snippet": parsed_result.get("json_snippet", {}),
            "description": parsed_result.get("description", "未知配置"),
            "user_input": response_str,
        }
        new_config_items.append(new_item)
        # 显示更新后的配置列表
        updated_config_display = _format_rule_config_items(new_config_items, file_names)
        feedback_msg = f"✅ 已添加配置：{parsed_result.get('description', '未知配置')}\n\n> {response_str}\n\n当前配置：\n{updated_config_display}"
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


def validation_preview_node(state: AgentState) -> dict:
    """第4步 (HITL)：生成规则 schema，预览对账效果，等待用户确认。"""
    logger.info("validation_preview_node - 开始执行")
    mappings = state.get("confirmed_mappings") or state.get("suggested_mappings", {})
    config_items = state.get("rule_config_items", [])  # 新的配置项列表
    analyses = state.get("file_analyses", [])
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

    # 字段映射展示
    mapping_display = _format_field_mappings(mappings, analyses)

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
        f"✅ **第4步：确认规则并保存**\n\n"
        f"我已经根据你的配置生成了对账规则！预览结果：\n\n"
        f"📊 **数据统计**\n"
        f"• 业务记录数：{preview.get('biz_count', 'N/A')}\n"
        f"• 财务记录数：{preview.get('fin_count', 'N/A')}\n"
        f"• 预计可匹配：{preview.get('estimated_match', 'N/A')}条\n\n"
        f"🔗 **字段映射**{mapping_display}\n\n"
        f"📋 **你配置的规则**\n{config_display}\n\n"
        f"规则看起来合理吗？"
    )

    user_response = interrupt({
        "step": "4/4",
        "step_title": "确认并保存规则",
        "question": preview_text,
        "preview": preview,
        "schema_summary": {
            "validations": len(schema.get("custom_validations", [])),
            "biz_patterns": biz_patterns,
            "fin_patterns": fin_patterns,
        },
        "hint": "• 如果确认无误，回复\"保存\"\n• 如果需要调整，回复\"调整\"重新配置",
    })

    response_str = str(user_response).strip()

    if response_str in ("调整", "重新配置", "重来", "adjust"):
        return {
            "messages": [AIMessage(content="好的，让我们重新配置规则参数。")],
            "phase": ReconciliationPhase.RULE_CONFIG.value,
            "generated_schema": None,
        }

    return {
        "messages": [AIMessage(content="规则确认完毕，准备保存。请为这个规则起个名字（例如：\"直销对账\"）。")],
        "generated_schema": schema,
        "preview_result": preview,
        "phase": ReconciliationPhase.SAVE_RULE.value,
    }


async def save_rule_node(state: AgentState) -> dict:
    """第5步 (HITL)：保存规则，询问用户是否立即开始对账。"""
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
    config_items = state.get("rule_config_items", [])
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

    msg = (
        f"规则 **{rule_name_cn}** 已保存！\n\n"
        f"现在可以用它开始对账了。要立即开始吗？\n"
        f"（回复\"开始\"立即执行对账，或稍后再说）"
    )
    
    if warning_msg:
        msg = warning_msg + "\n\n" + msg

    return {
        "messages": [AIMessage(content=msg)],
        "saved_rule_name": rule_name_cn,
        "phase": ReconciliationPhase.COMPLETED.value,
    }


# ── 编辑规则节点 ─────────────────────────────────────────────────────────────

def edit_field_mapping_node(state: AgentState) -> dict:
    """编辑规则 - 第1步：显示当前字段映射，支持修改或确认。"""
    mappings = state.get("confirmed_mappings") or state.get("suggested_mappings", {})
    adjustment_feedback = state.get("mapping_adjustment_feedback")
    rule_name = state.get("editing_rule_name", "规则")

    mapping_display = _format_edit_field_mappings(mappings)
    if adjustment_feedback:
        question_text = f"📋 **编辑「{rule_name}」- 字段映射**\n\n{adjustment_feedback}\n\n当前映射：\n{mapping_display}\n\n请确认或继续修改。"
    else:
        question_text = f"📋 **编辑「{rule_name}」- 字段映射**\n\n当前字段对应关系：\n{mapping_display}\n\n请确认是否正确？回复「确认」继续，或描述需要修改的地方。"

    user_response = interrupt({
        "step": "1/3",
        "step_title": "确认字段映射",
        "question": question_text,
        "suggested_mappings": mappings,
        "hint": "• 回复「确认」继续  • 修改示例：「订单号改为XX」「添加status对应YY」「删除status」",
    })

    response_str = str(user_response).strip()
    if not response_str or (response_str.startswith("已上传") and response_str.endswith("请处理。")):
        return {"messages": [], "mapping_adjustment_feedback": None, "phase": ReconciliationPhase.EDIT_FIELD_MAPPING.value}

    response_lower = response_str.lower()
    if response_lower in ("确认", "ok", "yes", "确定", "对", "没问题", "正确"):
        return {
            "messages": [AIMessage(content="✅ 字段映射已确认。")],
            "confirmed_mappings": mappings,
            "mapping_adjustment_feedback": None,
            "phase": ReconciliationPhase.EDIT_RULE_CONFIG.value,
        }

    # 用户需要调整
    dummy_analyses = _build_dummy_analyses_from_mappings(mappings)
    adjusted_mappings, operations = _adjust_field_mappings_with_llm(mappings, response_str, dummy_analyses)
    if adjusted_mappings != mappings and operations:
        ops_summary = _format_operations_summary(operations)
        feedback = f"✅ 已更新：\n{ops_summary}"
    else:
        feedback = f"⚠️ 未能解析修改，请更具体描述。\n\n> {response_str}"

    return {
        "messages": [AIMessage(content=feedback)],
        "suggested_mappings": adjusted_mappings,
        "confirmed_mappings": adjusted_mappings,
        "mapping_adjustment_feedback": feedback,
        "phase": ReconciliationPhase.EDIT_FIELD_MAPPING.value,
    }


def edit_rule_config_node(state: AgentState) -> dict:
    """编辑规则 - 第2步：显示当前规则配置，支持修改或确认。"""
    config_items = state.get("rule_config_items") or []
    rule_name = state.get("editing_rule_name", "规则")
    mappings = state.get("confirmed_mappings") or {}

    config_display = _format_rule_config_items(config_items, {"business": "业务文件", "finance": "财务文件"})
    question_text = f"⚙️ **编辑「{rule_name}」- 规则配置**\n\n当前配置：\n{config_display}\n\n请确认是否正确？回复「确认」继续，或描述需要添加/删除的配置。"

    user_response = interrupt({
        "step": "2/3",
        "step_title": "确认规则配置",
        "question": question_text,
        "current_config_items": config_items,
        "hint": "• 回复「确认」继续  • 添加：「金额容差0.1」  • 删除：「删除金额容差」",
    })

    response_str = str(user_response).strip()
    if not response_str or (response_str.startswith("已上传") and response_str.endswith("请处理。")):
        return {"messages": [], "phase": ReconciliationPhase.EDIT_RULE_CONFIG.value}

    response_lower = response_str.lower()
    if response_lower in ("确认", "ok", "yes", "确定", "对", "没问题", "正确", "完成"):
        return {
            "messages": [AIMessage(content="✅ 规则配置已确认。")],
            "rule_config_items": config_items,
            "phase": ReconciliationPhase.EDIT_VALIDATION_PREVIEW.value,
        }

    # 用户需要调整
    parsed = _parse_rule_config_json_snippet(response_str, config_items, mappings)
    action = parsed.get("action", "unknown")
    new_config_items = config_items.copy()
    feedback_msg = ""

    if action == "add":
        new_item = {
            "json_snippet": parsed.get("json_snippet", {}),
            "description": parsed.get("description", "未知配置"),
            "user_input": response_str,
        }
        new_config_items.append(new_item)
        feedback_msg = f"✅ 已添加：{parsed.get('description', '')}\n\n> {response_str}"
    elif action == "delete":
        target = parsed.get("target", "").strip()
        for prefix in ("删除", "去掉", "移除", "删掉"):
            if target.startswith(prefix):
                target = target[len(prefix):].strip()
                break
        if target:
            matching = _find_matching_items(target, new_config_items, threshold=0.5, max_matches=1, strict_substring_only=True)
            if matching:
                for idx in sorted(matching, reverse=True):
                    del new_config_items[idx]
                feedback_msg = f"🗑️ 已删除匹配的配置\n\n> {response_str}"
            else:
                feedback_msg = f"⚠️ 未找到匹配项\n\n> {response_str}"
        else:
            feedback_msg = f"⚠️ 未指定删除目标\n\n> {response_str}"
    else:
        feedback_msg = f"⚠️ 未能解析，请更具体描述\n\n> {response_str}"

    return {
        "messages": [AIMessage(content=feedback_msg)],
        "rule_config_items": new_config_items,
        "phase": ReconciliationPhase.EDIT_RULE_CONFIG.value,
    }


def edit_validation_preview_node(state: AgentState) -> dict:
    """编辑规则 - 第3步：预览并确认保存。以 editing_rule_template 为基准，仅更新 field_roles。"""
    import copy

    rule_template = state.get("editing_rule_template") or {}
    mappings = state.get("confirmed_mappings") or {}
    config_items = state.get("rule_config_items") or []
    rule_name = state.get("editing_rule_name", "规则")

    # 以原始 rule_template 为基准（完整保留用户原有配置），仅更新 field_roles
    schema = copy.deepcopy(rule_template)
    schema["description"] = rule_name
    if "data_sources" not in schema:
        schema["data_sources"] = {}
    for src in ("business", "finance"):
        if src not in schema["data_sources"]:
            schema["data_sources"][src] = {}
        schema["data_sources"][src]["field_roles"] = mappings.get(src, {})

    # 若用户编辑过规则配置（增删），从 config_items 重建；否则保留原 schema
    if config_items:
        orig_dcr = rule_template.get("data_cleaning_rules", {})
        base = {
            "version": "1.0",
            "description": rule_name,
            "data_sources": schema["data_sources"],
            "key_field_role": schema.get("key_field_role", "order_id"),
            "tolerance": {"date_format": "%Y-%m-%d", "amount_diff_max": 0.1},
            "data_cleaning_rules": {"global": orig_dcr.get("global", {})},
            "custom_validations": schema.get("custom_validations", []),
        }
        merged = _merge_json_snippets(base, config_items)
        schema["tolerance"] = merged.get("tolerance", schema.get("tolerance"))
        dcr = merged.get("data_cleaning_rules", {})
        if "global" not in dcr and "global" in orig_dcr:
            dcr["global"] = orig_dcr["global"]
        schema["data_cleaning_rules"] = dcr

    schema = _validate_and_deduplicate_rules(schema)

    mapping_display = _format_edit_field_mappings(mappings)
    config_display = _format_rule_config_items(config_items, {"business": "业务文件", "finance": "财务文件"})

    preview_text = (
        f"✅ **编辑「{rule_name}」- 预览**\n\n"
        f"🔗 **字段映射**\n{mapping_display}\n\n"
        f"📋 **规则配置**\n{config_display}\n\n"
        "确认无误后回复「保存」，将删除旧规则并保存新规则。"
    )

    user_response = interrupt({
        "step": "3/3",
        "step_title": "确认并保存",
        "question": preview_text,
        "hint": "• 回复「保存」完成编辑  • 回复「调整」返回上一步修改",
    })

    response_str = str(user_response).strip()
    if response_str in ("调整", "重新配置", "返回", "上一步"):
        return {
            "messages": [AIMessage(content="好的，返回规则配置。")],
            "phase": ReconciliationPhase.EDIT_RULE_CONFIG.value,
        }

    if response_str.lower() not in ("保存", "确认", "ok", "yes"):
        return {
            "messages": [AIMessage(content="请回复「保存」以完成编辑，或「调整」返回修改。")],
            "phase": ReconciliationPhase.EDIT_VALIDATION_PREVIEW.value,
        }

    return {
        "messages": [AIMessage(content="正在保存...")],
        "generated_schema": schema,
        "phase": ReconciliationPhase.EDIT_SAVE.value,
    }


async def edit_save_node(state: AgentState) -> dict:
    """编辑规则 - 保存：仅在此步骤删除旧规则（PostgreSQL+JSON），并新建规则。"""
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
        "messages": [AIMessage(content=f"✅ 规则「{rule_name}」已更新！（已删除旧规则并保存新规则）")],
        "saved_rule_name": rule_name,
        "editing_rule_id": None,
        "editing_rule_name": None,
        "editing_rule_template": None,
        "phase": ReconciliationPhase.COMPLETED.value,
    }


# ── 入口路由节点 ─────────────────────────────────────────────────────────────

def entry_router_node(state: AgentState) -> dict:
    """子图入口路由节点：根据 phase 决定进入哪个节点。
    
    这是为了解决 LangGraph 子图 interrupt resume 后重新从入口点开始的问题。
    """
    phase = state.get("phase", "")
    logger.info(f"子图入口路由: phase={phase}")
    
    # 直接返回，让条件边路由到正确的节点
    return {"messages": []}
