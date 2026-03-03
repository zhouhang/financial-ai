"""分析节点模块

包含文件分析节点 file_analysis_node。
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.types import interrupt

logger = logging.getLogger(__name__)


async def file_analysis_node(state: "AgentState") -> dict:
    """第1步：分析上传的文件，提取列名和样本数据。

    支持智能分析：
    - 简单场景（2个标准文件）→ 快速分析
    - 复杂场景（多sheet/非标准格式/多文件）→ 智能分析

    ⚠️ 展平到主图后，interrupt/resume 不会 replay 此节点，无需缓存检查。
    """
    from app.models import AgentState, ReconciliationPhase, UserIntent
    from app.tools.mcp_client import call_mcp_tool
    from app.utils.workflow_intent import (
        check_user_intent_after_interrupt,
        check_user_intent_after_interrupt_guest,
        handle_intent_switch,
        handle_intent_switch_guest,
    )
    from app.graphs.reconciliation.helpers import (
        quick_complexity_check,
        invoke_intelligent_analyzer,
        _guess_field_mappings,
        build_single_file_error_message,
        build_format_error_message,
        delete_uploaded_files,
    )

    uploaded = state.get("uploaded_files", [])
    logger.info(f"🔍 [file_analysis_node] uploaded_files: {len(uploaded)} files: {uploaded}")
    if not uploaded:
        user_response = interrupt({
            "step": "1/4",
            "step_title": "上传文件",
            "question": "📤 第1步：上传文件\n\n请上传需要对账的文件（文件1和文件2各一个 Excel/CSV 文件）。",
            "hint": "💡 上传文件后，点击发送按钮或直接发送消息",
        })

        auth_token = state.get("auth_token", "")

        if not auth_token:
            intent = await check_user_intent_after_interrupt_guest(
                user_response=user_response,
                current_phase=ReconciliationPhase.FILE_ANALYSIS.value,
                state=state
            )
            if intent != UserIntent.RESUME_WORKFLOW.value:
                return await handle_intent_switch_guest(
                    intent=intent,
                    current_phase=ReconciliationPhase.FILE_ANALYSIS.value,
                    state=state,
                    user_input=str(user_response).strip()
                )
        else:
            intent = await check_user_intent_after_interrupt(
                user_response=user_response,
                current_phase=ReconciliationPhase.FILE_ANALYSIS.value,
                state=state
            )
            if intent != UserIntent.RESUME_WORKFLOW.value:
                return await handle_intent_switch(intent, ReconciliationPhase.FILE_ANALYSIS.value, state)

        uploaded = state.get("uploaded_files", [])
        if not uploaded:
            user_response = interrupt({
                "step": "1/4",
                "step_title": "上传文件",
                "question": "⚠️ 未检测到文件上传\n\n📤 请上传需要对账的文件（文件1和文件2各一个 Excel/CSV 文件）。",
                "hint": "💡 上传文件后，点击发送按钮或直接发送消息",
            })

            auth_token = state.get("auth_token", "")
            if not auth_token:
                intent = await check_user_intent_after_interrupt_guest(
                    user_response=user_response,
                    current_phase=ReconciliationPhase.FILE_ANALYSIS.value,
                    state=state
                )
                if intent != UserIntent.RESUME_WORKFLOW.value:
                    return await handle_intent_switch_guest(
                        intent=intent,
                        current_phase=ReconciliationPhase.FILE_ANALYSIS.value,
                        state=state,
                        user_input=str(user_response).strip()
                    )
            else:
                intent = await check_user_intent_after_interrupt(
                    user_response=user_response,
                    current_phase=ReconciliationPhase.FILE_ANALYSIS.value,
                    state=state
                )
                if intent != UserIntent.RESUME_WORKFLOW.value:
                    return await handle_intent_switch(intent, ReconciliationPhase.FILE_ANALYSIS.value, state)

            uploaded = state.get("uploaded_files", [])
            if not uploaded:
                from langchain_core.messages import AIMessage
                return {
                    "messages": [AIMessage(content="⚠️ 未检测到文件上传。\n\n请上传文件后说「对账」重新开始。")],
                    "phase": "",
                    "user_intent": UserIntent.UNKNOWN.value,
                    "file_analyses": [],
                }

    from app.utils.file_validation import is_standard_format
    from langchain_core.messages import AIMessage

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
            file_paths.append(item)

    file_count = len(file_paths)
    logger.info(f"开始文件验证，文件数量: {file_count}")

    validation_error_message = None

    if file_count == 1:
        logger.warning("只有一个文件，无法完成对账")
        validation_error_message = build_single_file_error_message()
    elif file_count == 2:
        validation_result = is_standard_format(file_paths)
        if not validation_result.is_standard:
            logger.warning(f"文件格式验证失败: {validation_result.reason}")
            validation_error_message = build_format_error_message(
                validation_result=validation_result,
                file_paths=file_paths,
                original_filenames_map=original_filenames_map
            )
    elif file_count > 2:
        logger.warning(f"文件数量过多: {file_count}个")
        validation_error_message = f"⚠️ 上传了{file_count}个文件，对账只需要2个文件（业务文件和财务文件）。\n\n请重新上传正确数量的文件。"

    if validation_error_message:
        logger.warning("文件验证失败，返回提示并等待用户重新上传")
        auth_token = state.get("auth_token", "")
        if file_paths:
            await delete_uploaded_files(uploaded, auth_token)

        return {
            "messages": [AIMessage(content=validation_error_message)],
            "phase": ReconciliationPhase.FILE_ANALYSIS.value,
            "uploaded_files": [],
            "file_analyses": [],
        }

    logger.info(f"文件验证通过，文件数量: {file_count}")

    complexity_level = quick_complexity_check(uploaded)
    logger.info(f"文件复杂度检测: {complexity_level}, 文件数: {len(uploaded)}")

    if complexity_level == "simple":
        logger.info("使用快速分析路径")

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
            warnings = []

        except Exception as e:
            logger.error(f"调用 MCP 文件分析工具失败: {e}", exc_info=True)
            return {
                "messages": [AIMessage(content=f"❌ 文件分析失败: {str(e)}")],
                "phase": ReconciliationPhase.FILE_ANALYSIS.value,
                "file_analyses": [],
            }
    else:
        logger.info(f"使用智能分析路径 (复杂度: {complexity_level})")

        try:
            result = await invoke_intelligent_analyzer(uploaded, complexity_level)

            if not result.get("success"):
                error_msg = result.get("recommendations", {}).get("message", "智能分析失败")
                analyses = result.get("analyses", [])
                warnings = result.get("warnings", [])

                msg_parts = [f"🔍 文件分析\n{error_msg}"]
                if warnings:
                    msg_parts.append("⚠️ " + "；".join(warnings[:3]))

                return {
                    "messages": [AIMessage(content="\n".join(msg_parts))],
                    "phase": ReconciliationPhase.FILE_ANALYSIS.value,
                    "file_analyses": analyses,
                }

            analyses = result.get("analyses", [])
            warnings = result.get("warnings", [])
            recommendations = result.get("recommendations", {})

            _MAX_COLS = 15
            msg_parts = ["🔍 **文件分析完成**\n"]
            for a in analyses:
                src = "业务" if a.get("guessed_source") == "business" else "财务"
                conf = int((a.get("confidence") or 0) * 100)
                fname = a.get("original_filename") or a.get("filename", "")
                cols = a.get("columns", [])
                rows = a.get("row_count", 0)
                msg_parts.append(f"**{fname}** ({src} {conf}%) {rows}行")
                if cols:
                    display_cols = cols[:_MAX_COLS]
                    sample_data = a.get("sample_data", [])[:3]
                    header_line = "| " + " | ".join(display_cols) + " |"
                    sep_line = "| " + " | ".join(["---"] * len(display_cols)) + " |"
                    msg_parts.append(header_line)
                    msg_parts.append(sep_line)
                    for sample_row in sample_data:
                        sample_vals = [str(sample_row.get(c, ""))[:50] for c in display_cols]
                        msg_parts.append("| " + " | ".join(sample_vals) + " |")
                    if not sample_data:
                        msg_parts.append("| " + " | ".join([""] * len(display_cols)) + " |")
                if a.get("processing_notes"):
                    msg_parts.append(f"  {a.get('processing_notes')}")
                msg_parts.append("")
            if recommendations.get("message"):
                msg_parts.append(recommendations["message"])
                msg_parts.append("")
            if warnings:
                msg_parts.append("⚠️ " + "；".join(warnings[:3]))
                msg_parts.append("")

        except Exception as e:
            logger.error(f"智能文件分析失败: {e}", exc_info=True)
            return {
                "messages": [AIMessage(content=f"❌ 智能文件分析失败: {str(e)}")],
                "phase": ReconciliationPhase.FILE_ANALYSIS.value,
                "file_analyses": [],
            }

    _MAX_COLS = 15
    if complexity_level == "simple":
        summary_parts: list[str] = ["📊 **文件分析完成**\n"]
        for a in analyses:
            fname = a.get('original_filename') or a.get('filename', '')
            cols = a.get('columns', [])
            rows = a.get('row_count', 0)
            summary_parts.append(f"**{fname}** ({rows}行)")
            if cols:
                display_cols = cols[:_MAX_COLS]
                sample_data = a.get("sample_data", [])[:3]
                header_line = "| " + " | ".join(display_cols) + " |"
                sep_line = "| " + " | ".join(["---"] * len(display_cols)) + " |"
                summary_parts.append(header_line)
                summary_parts.append(sep_line)
                for sample_row in sample_data:
                    sample_vals = [str(sample_row.get(c, ""))[:50] for c in display_cols]
                    summary_parts.append("| " + " | ".join(sample_vals) + " |")
                if not sample_data:
                    summary_parts.append("| " + " | ".join([""] * len(display_cols)) + " |")
            summary_parts.append("")
        msg = "\n".join(summary_parts)
    else:
        msg = "\n".join(msg_parts)

    suggested = _guess_field_mappings(analyses)

    # 使用规则流程：校验通过后进入任务执行；创建规则流程进入字段映射
    intent = state.get("user_intent", "")
    if intent == UserIntent.USE_EXISTING_RULE.value:
        phase = ReconciliationPhase.TASK_EXECUTION.value
    else:
        phase = ReconciliationPhase.FIELD_MAPPING.value

    return {
        "messages": [AIMessage(content=msg)],
        "file_analyses": analyses,
        "suggested_mappings": suggested,
        "phase": phase,
    }


__all__ = ["file_analysis_node"]
