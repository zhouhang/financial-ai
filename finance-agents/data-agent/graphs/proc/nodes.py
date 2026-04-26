"""proc 子图节点函数模块

包含数据整理工作流的核心节点：

  1. get_rule_node           —— 从 PG 读取规则（公共节点）
  2. check_file_node         —— 校验上传文件（公共节点）
  3. proc_task_execute_node  —— 按 JSON 规则确定性执行数据整理
  4. result_node             —— 展示处理结果或返回错误信息

节点间通过 AgentState 的 proc_ctx 子字典传递中间状态，
不污染主图其他字段。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from langchain_core.messages import AIMessage

from models import AgentState, ProcAgentPhase

logger = logging.getLogger(__name__)


# ── 公共节点导入 ────────────────────────────────────────────────────────────
from graphs.main_graph.public_nodes import (
    _build_upload_name_maps,
    _get_proc_ctx,
)

# ── 辅助函数 ─────────────────────────────────────────────────────────────────

# _to_abs_path, _read_header, SUPPORTED_EXTENSIONS 已移至 graphs.main_graph.public_nodes

# ══════════════════════════════════════════════════════════════════════════════
# 节点流程定义（用于开始提示和进度提示）
_PROC_NODE_FLOW = [
    {"name": "读取规则", "desc": "从数据库加载数据整理规则定义", "node": "get_rule_node"},
    {"name": "文件校验", "desc": "校验上传文件格式、列名是否符合规则要求", "node": "check_file_node"},
    {"name": "执行整理", "desc": "按照规则执行数据转换和整理", "node": "proc_task_execute_node"},
    {"name": "结果展示", "desc": "展示处理结果和生成的执行计划", "node": "result_node"},
]


def _build_flow_overview() -> str:
    """构建节点流程概览文本。"""
    lines = ["📋 **处理流程**（共4个步骤）：\n"]
    for idx, step in enumerate(_PROC_NODE_FLOW, 1):
        lines.append(f"{idx}. **{step['name']}** — {step['desc']}")
    return "\n".join(lines)


def build_proc_start_message(rule_display: str, uploaded_count: int = 0) -> str:
    """构建数据整理任务开始提示。"""
    flow_overview = _build_flow_overview()
    display = rule_display or "（未指定）"
    header = (
        f"📊 **开始数据整理任务**\n\n"
        f"已选择规则：**{display}**\n"
    )

    if uploaded_count > 0:
        return (
            f"{header}"
            f"已上传文件：{uploaded_count} 个\n\n"
            f"{flow_overview}\n\n"
            "正在校验文件并加载规则..."
        )

    return (
        f"{header}\n"
        f"{flow_overview}\n\n"
        "请先上传需要整理的数据文件（Excel 或 CSV 格式）。"
    )


def _build_execute_success_summary(
    rule_display: str,
    generated_count: int,
    merged_count: int,
) -> str:
    """构建执行节点完成摘要（用于替换执行中占位）。"""
    lines = [
        "执行整理已完成。",
        "",
        f"- 规则：{rule_display}",
        f"- 生成目标文件：{generated_count} 个",
        f"- 合并文件：{merged_count} 个",
        "",
        "正在整理最终结果，请稍候。",
    ]
    return "\n".join(lines)


def _build_execute_error_summary(rule_display: str, error_msg: str) -> str:
    """构建执行节点失败摘要（用于替换执行中占位）。"""
    detail = (error_msg or "未知错误").strip()
    if len(detail) > 240:
        detail = detail[:240] + "..."
    return (
        "执行整理失败，正在整理错误详情。\n\n"
        f"- 规则：{rule_display}\n"
        f"- 错误摘要：{detail}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# 节点 1：get_rule_node — 从 PG 读取规则（公共节点）
# ══════════════════════════════════════════════════════════════════════════════

# get_rule_node 已移至 graphs.main_graph.public_nodes

# ══════════════════════════════════════════════════════════════════════════════
# 节点 2：check_file_node — 文件类型/数量/表头校验（公共节点）
# ══════════════════════════════════════════════════════════════════════════════

# check_file_node 已移至 graphs.main_graph.public_nodes

# ══════════════════════════════════════════════════════════════════════════════
# 节点 3：proc_task_execute_node — 按 JSON 规则确定性执行数据整理
# ══════════════════════════════════════════════════════════════════════════════

async def proc_task_execute_node(state: AgentState) -> dict:
    """按 JSON 规则确定性执行数据整理。

    调用 MCP proc_execute 工具，根据文件校验结果和 rule_code
    执行字段映射和数据转换，生成目标 Excel 文件。
    """
    ctx = _get_proc_ctx(state)
    rule_code: str = ctx.get("rule_code", "")
    rule_name: str = ctx.get("rule_name") or state.get("selected_rule_name") or ""
    rule_display = rule_name or rule_code or "（未知规则）"
    file_match_results: list[dict] = ctx.get("file_match_results", [])

    logger.info(f"[proc] proc_task_execute_node rule_code={rule_code!r}")
    logger.info(f"[proc] file_match_results={[m.get('file_name') for m in file_match_results]}")

    # ── 检查文件校验结果 ─────────────────────────────────────────────────────
    if not file_match_results:
        error_msg = "未找到文件校验结果，请先完成文件校验步骤"
        logger.error(f"[proc] {error_msg}")
        ctx.update({
            "phase": ProcAgentPhase.SHOWING_RESULT.value,
            "exec_status": "error",
            "exec_error": error_msg,
        })
        return {
            "messages": [AIMessage(content=_build_execute_error_summary(rule_display, error_msg))],
            "proc_ctx": ctx,
        }

    # ── 准备 proc_execute 参数 ───────────────────────────────────────────────
    # file_match_results 格式: [{file_name, table_id, table_name}]
    # 需要补充 file_path（从 uploaded_files 或 state 中获取）
    uploaded_files_raw: list = list(ctx.get("logical_uploaded_files") or state.get("uploaded_files") or [])

    # 构建 file_name -> file_path 映射，兼容原始文件名与存储文件名
    file_path_map, _ = _build_upload_name_maps(uploaded_files_raw)
    logger.info(f"[proc] file_path_map keys={list(file_path_map.keys())}")

    # 构建 uploaded_files 参数（proc_execute 需要的格式）
    sync_uploaded_files: list[dict] = []
    for match in file_match_results:
        file_name = match.get("file_name", "")
        table_name = match.get("table_name", "")
        table_id = match.get("table_id", "")
        file_path = file_path_map.get(file_name, "")
        if file_path:
            sync_uploaded_files.append({
                "file_name": file_name,
                "file_path": file_path,
                "table_id": table_id,
                "table_name": table_name,
            })

    if not sync_uploaded_files:
        error_msg = "无法构建文件路径映射，请检查上传文件状态"
        logger.error(f"[proc] {error_msg}")
        ctx.update({
            "phase": ProcAgentPhase.SHOWING_RESULT.value,
            "exec_status": "error",
            "exec_error": error_msg,
        })
        return {
            "messages": [AIMessage(content=_build_execute_error_summary(rule_display, error_msg))],
            "proc_ctx": ctx,
        }

    # ── 调用 proc_execute 工具 ───────────────────────────────────────────────
    from tools.mcp_client import execute_proc_rule

    try:
        logger.info(
            f"[proc] 调用 proc_execute，"
            f"files={[m['file_name'] for m in sync_uploaded_files]}"
        )
        sync_result = await execute_proc_rule(
            uploaded_files=sync_uploaded_files,
            rule_code=rule_code,
            auth_token=state.get("auth_token", ""),
        )
    except Exception as e:
        error_msg = f"调用数据整理服务失败: {e}"
        logger.error(f"[proc] {error_msg}", exc_info=True)
        ctx.update({
            "phase": ProcAgentPhase.SHOWING_RESULT.value,
            "exec_status": "error",
            "exec_error": error_msg,
        })
        return {
            "messages": [AIMessage(content=_build_execute_error_summary(rule_display, error_msg))],
            "proc_ctx": ctx,
        }

    logger.info(
        f"[proc] proc_execute 结果: "
        f"success={sync_result.get('success')}, "
        f"generated={sync_result.get('generated_count', 0)}"
    )

    # ── 处理执行结果 ─────────────────────────────────────────────────────────
    if not sync_result.get("success"):
        error_msg = sync_result.get("error", "数据整理执行失败")
        errors = sync_result.get("errors", [])
        if errors:
            error_msg += f"\n\n详细错误:\n" + "\n".join(f"- {e}" for e in errors)

        ctx.update({
            "phase": ProcAgentPhase.SHOWING_RESULT.value,
            "exec_status": "error",
            "exec_error": error_msg,
            "sync_result": sync_result,
        })

        return {
            "messages": [AIMessage(content=_build_execute_error_summary(rule_display, error_msg))],
            "proc_ctx": ctx,
        }

    # ── 执行成功 ─────────────────────────────────────────────────────────────
    generated_files: list[dict] = sync_result.get("generated_files", [])
    merged_files: list[dict] = sync_result.get("merged_files", [])

    # 构建执行计划摘要（用于 result_node 展示）
    execution_plan: list[dict] = []
    for gf in generated_files:
        execution_plan.append({
            "rule_id": gf.get("rule_id", ""),
            "description": f"生成目标表: {gf.get('target_table', '')}",
            "source_table": "",
            "target_table": gf.get("target_table", ""),
            "mapping_count": gf.get("row_count", 0),
        })

    ctx.update({
        "phase": ProcAgentPhase.SHOWING_RESULT.value,
        "exec_status": "success",
        "execution_plan": execution_plan,
        "processed_files": [gf.get("output_file", "") for gf in generated_files],
        "generated_files": generated_files,
        "merged_files": merged_files,
        "sync_result": sync_result,
    })

    return {
        "messages": [
            AIMessage(
                content=_build_execute_success_summary(
                    rule_display=rule_display,
                    generated_count=len(generated_files),
                    merged_count=len([m for m in merged_files if m.get("merged")]),
                )
            )
        ],
        "proc_ctx": ctx,
    }

# ══════════════════════════════════════════════════════════════════════════════
# 节点 4：result_node — 展示处理结果或返回错误信息
# ══════════════════════════════════════════════════════════════════════════════

def result_node(state: AgentState) -> dict:
    """向用户展示数据整理结果（成功摘要或错误详情）。"""
    ctx = _get_proc_ctx(state)
    rule_code: str = ctx.get("rule_code", "（未知规则）")
    exec_status: str = ctx.get("exec_status", "error")

    if exec_status == "success":
        generated_files: list[dict] = ctx.get("generated_files", [])
        merged_files: list[dict] = ctx.get("merged_files", [])
        rule_name: str = ctx.get("rule_name") or state.get("selected_rule_name") or ""
        
        # 构建规则展示文本
        if rule_name:
            rule_display = rule_name
        else:
            rule_display = rule_code

        # 构建生成文件清单（使用 MCP 返回的 download_url）
        file_lines = []
        for gf in generated_files:
            target_table = gf.get("target_table", "")
            row_count = gf.get("row_count", 0)
            # 优先使用 MCP 返回的 download_url
            download_url = gf.get("download_url")
            if download_url:
                file_lines.append(
                    f"- **[{target_table}]({download_url})** — {row_count}行"
                )

        # 构建合并文件清单（使用 MCP 返回的 download_url）
        merged_file_lines = []
        for mf in merged_files:
            if mf.get("merged") and mf.get("merged_file_path"):
                # 使用 match_field + (合并) 作为展示名称
                match_field = mf.get("match_field", "")
                display_name = f"{match_field}(合并)" if match_field else "合并文件"
                # 优先使用 MCP 返回的 download_url
                download_url = mf.get("download_url") or mf.get("merged_download_url")
                # 获取源文件列表
                source_files = mf.get("source_files", [])
                source_files_text = ""
                if source_files:
                    source_names = [os.path.basename(sf) for sf in source_files]
                    source_files_text = f"（由 {', '.join(source_names)} 合并）"
                row_count = mf.get("row_count", 0)
                row_text = f" — {row_count}行" if row_count else ""
                if download_url:
                    merged_file_lines.append(
                        f"- **[{display_name}]({download_url})**{row_text}{source_files_text}"
                    )

        merged_file_text = "\n".join(merged_file_lines) if merged_file_lines else ""

        # 构建消息：有生成文件时显示，否则只显示合并文件
        msg = (
            f"数据整理任务已完成，结果文件如下。\n\n"
            f"规则：{rule_display}\n"
        )
        # 只有生成文件时才显示生成文件部分
        if file_lines:
            file_list_text = "\n".join(file_lines)
            msg += f"\n**结果文件：**\n{file_list_text}\n"
        # 显示合并文件
        if merged_file_text:
            msg += f"\n**合并文件：**\n{merged_file_text}\n"
        msg += f"\n如需重新处理或使用其他规则，请告知。"
    else:
        exec_error: str = ctx.get("exec_error", "未知错误")
        rule_name_else: str = ctx.get("rule_name") or state.get("selected_rule_name") or ""
        rule_display_else = rule_name_else or rule_code
        msg = (
            f"数据整理任务执行失败。\n\n"
            f"**规则：** {rule_display_else}\n"
            f"**错误信息：** {exec_error}\n\n"
            f"请检查上传文件是否符合规则要求，或联系管理员排查问题。"
        )

    ctx.update({"phase": ProcAgentPhase.COMPLETED.value})
    return {
        "messages": [AIMessage(content=msg)],
        "proc_ctx": ctx,
    }
