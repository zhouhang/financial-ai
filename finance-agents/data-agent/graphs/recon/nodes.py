"""recon 子图节点函数模块

包含对账执行工作流的核心节点：

  1. get_rule_node           —— 从 PG 读取规则（公共节点）
  2. check_file_node         —— 校验上传文件（公共节点）
  3. recon_task_execution_node —— 调用 MCP 工具执行对账
  4. recon_result_node       —— 展示对账结果（数据差异）

节点间通过 AgentState 的 recon_ctx 子字典传递中间状态，
不污染主图其他字段。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage

from models import AgentState, ReconAgentPhase

logger = logging.getLogger(__name__)


# ── 公共节点导入 ────────────────────────────────────────────────────────────
from graphs.main_graph.public_nodes import (
    get_rule_node,
    check_file_node,
    _get_proc_ctx,
    _to_abs_path,
)


# ── 辅助函数 ─────────────────────────────────────────────────────────────────

def _get_recon_ctx(state: AgentState) -> dict[str, Any]:
    """安全地获取 recon_ctx，不存在则返回空字典。"""
    return dict(state.get("recon_ctx") or {})


# ══════════════════════════════════════════════════════════════════════════════
# 节点 1：get_rule_node — 从 PG 读取规则（公共节点）
# ══════════════════════════════════════════════════════════════════════════════

# 公共节点 get_rule_node 使用 proc_ctx，这里通过适配层调用

async def get_rule_node_for_recon(state: AgentState) -> dict:
    """从 PostgreSQL 读取规则（适配 recon_ctx）。

    通过调用公共节点 get_rule_node 实现，将 proc_ctx 结果映射到 recon_ctx。

    - 若规则存在：将规则写入 recon_ctx，phase → CHECKING_FILES
    - 若规则不存在：直接回复用户，phase → RULE_NOT_FOUND
    """
    ctx = _get_recon_ctx(state)
    rule_code: str = ctx.get("rule_code") or state.get("selected_rule_code") or ""

    logger.info(f"[recon] get_rule_node_for_recon rule_code={rule_code!r}")

    # 构建适配 state：将 recon_ctx 映射为 proc_ctx 供公共节点使用
    adapted_state = {
        **state,
        "proc_ctx": ctx,  # 公共节点操作 proc_ctx
    }

    # 调用公共节点
    result = await get_rule_node(adapted_state)

    # 将公共节点的 proc_ctx 结果映射回 recon_ctx
    result_proc_ctx = result.get("proc_ctx", {})
    ctx.update(result_proc_ctx)

    # 转换 phase（ProcAgentPhase -> ReconAgentPhase）
    phase = ctx.get("phase", "")
    phase_mapping = {
        "rule_not_found": ReconAgentPhase.RULE_NOT_FOUND.value,
        "checking_files": ReconAgentPhase.CHECKING_FILES.value,
    }
    if phase in phase_mapping:
        ctx["phase"] = phase_mapping[phase]

    return {
        "messages": result.get("messages", []),
        "recon_ctx": ctx,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 节点 2：check_file_node — 文件类型/数量/表头校验（公共节点）
# ══════════════════════════════════════════════════════════════════════════════

# check_file_node 使用 proc_ctx，需要创建适配版本

async def check_file_node_for_recon(state: AgentState) -> dict:
    """校验已上传文件是否满足对账规则要求（适配 recon_ctx）。

    通过调用公共节点 check_file_node 实现，将 proc_ctx 结果映射到 recon_ctx。
    """
    ctx = _get_recon_ctx(state)
    file_rule_code: str = ctx.get("file_rule_code") or ""

    logger.info(
        f"[recon] check_file_node_for_recon file_rule_code={file_rule_code!r}"
    )

    # 构建适配 state：将 recon_ctx 映射为 proc_ctx 供公共节点使用
    adapted_state = {
        **state,
        "proc_ctx": ctx,           # 公共节点操作 proc_ctx
        "file_rule_code": file_rule_code,
    }

    # 调用公共节点
    result = await check_file_node(adapted_state)

    # 将公共节点的 proc_ctx 结果映射回 recon_ctx
    result_proc_ctx = result.get("proc_ctx", {})
    ctx.update(result_proc_ctx)

    # 转换 phase（ProcAgentPhase -> ReconAgentPhase）
    phase = ctx.get("phase", "")
    phase_mapping = {
        "file_check_failed": ReconAgentPhase.FILE_CHECK_FAILED.value,
        "executing": ReconAgentPhase.EXECUTING.value,
    }
    if phase in phase_mapping:
        ctx["phase"] = phase_mapping[phase]

    return {
        "messages": result.get("messages", []),
        "recon_ctx": ctx,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 节点 3：recon_task_execution_node — 调用 MCP 工具执行对账
# ══════════════════════════════════════════════════════════════════════════════

async def recon_task_execution_node(state: AgentState) -> dict:
    """调用 MCP 工具 recon_execute 执行对账任务。

    根据规则和文件匹配结果执行对账，生成差异报告。
    """
    ctx = _get_recon_ctx(state)
    rule_code: str = ctx.get("rule_code", "")
    file_match_results: list[dict] = ctx.get("file_match_results", [])
    rule: dict = ctx.get("rule", {})

    messages: list = list(state.get("messages") or [])

    logger.info(f"[recon] recon_task_execution_node rule_code={rule_code!r}")
    logger.info(f"[recon] file_match_results={[m.get('file_name') for m in file_match_results]}")

    # 检查文件校验结果
    if not file_match_results:
        error_msg = "未找到文件校验结果，请先完成文件校验步骤"
        logger.error(f"[recon] {error_msg}")
        ctx.update({
            "phase": ReconAgentPhase.EXEC_FAILED.value,
            "exec_status": "error",
            "exec_error": error_msg,
        })
        return {
            "messages": messages,
            "recon_ctx": ctx,
        }

    # 准备对账参数
    uploaded_files_raw: list = list(state.get("uploaded_files") or [])
    file_path_map: dict[str, str] = {}
    for item in uploaded_files_raw:
        if isinstance(item, dict):
            fp = item.get("file_path") or item.get("path") or ""
        else:
            fp = str(item)
        if fp:
            abs_fp = _to_abs_path(fp)
            file_path_map[abs_fp.split("/")[-1]] = abs_fp

    # 构建文件参数
    recon_files: list[dict] = []
    for match in file_match_results:
        file_name = match.get("file_name", "")
        file_path = file_path_map.get(file_name, "")
        if file_path:
            recon_files.append({
                "file_name": file_name,
                "file_path": file_path,
                "table_id": match.get("table_id", ""),
                "table_name": match.get("table_name", ""),
            })

    if not recon_files:
        error_msg = "无法构建文件路径映射，请检查上传文件状态"
        logger.error(f"[recon] {error_msg}")
        ctx.update({
            "phase": ReconAgentPhase.EXEC_FAILED.value,
            "exec_status": "error",
            "exec_error": error_msg,
        })
        return {
            "messages": messages,
            "recon_ctx": ctx,
        }

    # 统一调用 recon_execute 工具（对账）
    from tools.mcp_client import execute_recon

    # 构建 validated_files 参数
    validated_files = [
        {"file_path": f["file_path"], "table_name": f["table_name"]}
        for f in recon_files
    ]

    try:
        logger.info(
            f"[recon] 调用 recon_execute，"
            f"rule_code={rule_code}, "
            f"files={[f['table_name'] for f in validated_files]}"
        )
        recon_result = await execute_recon(
            validated_files=validated_files,
            rule_code=rule_code,
            rule_id="",  # 不指定则执行所有匹配的规则
        )
    except Exception as e:
        error_msg = f"调用对账服务失败: {e}"
        logger.error(f"[recon] {error_msg}", exc_info=True)
        ctx.update({
            "phase": ReconAgentPhase.EXEC_FAILED.value,
            "exec_status": "error",
            "exec_error": error_msg,
        })
        return {
            "messages": messages,
            "recon_ctx": ctx,
        }

    logger.info(
        f"[recon] recon_execute 结果: "
        f"success={recon_result.get('success')}, "
        f"rule_type={recon_result.get('rule_type')}"
    )

    # 处理执行结果
    if not recon_result.get("success"):
        error_msg = recon_result.get("error", "对账执行失败")
        ctx.update({
            "phase": ReconAgentPhase.EXEC_FAILED.value,
            "exec_status": "error",
            "exec_error": error_msg,
            "recon_result": recon_result,
        })
        return {
            "messages": messages,
            "recon_ctx": ctx,
        }

    # 提取文件信息（从对账结果中）
    file_info_list = []
    output_files = []
    download_urls = []  # MCP 返回的下载链接

    # 统一处理对账结果（支持单条或多条规则）
    results = recon_result.get("results", [])
    if not results and recon_result.get("success"):
        # 兼容没有包装在 results 中的单个结果
        results = [recon_result]

    total_diff = sum(r.get("matched_with_diff", 0) for r in results)
    total_source_only = sum(r.get("source_only", 0) for r in results)
    total_target_only = sum(r.get("target_only", 0) for r in results)
    total_matched = sum(r.get("matched_exact", 0) for r in results)

    # 收集文件信息、输出报告路径和过滤统计信息
    filter_stats = {}
    for r in results:
        source_file = r.get("source_file", "")
        target_file = r.get("target_file", "")
        output_file = r.get("output_file", "")
        download_url = r.get("download_url")  # MCP 返回的下载链接
        rule_name = r.get("rule_name", "")
        if source_file and target_file:
            file_info_list.append({
                "rule_name": rule_name,
                "source_file": source_file.split("/")[-1] if "/" in source_file else source_file,
                "target_file": target_file.split("/")[-1] if "/" in target_file else target_file,
            })
        if output_file:
            output_files.append(output_file)
        if download_url:
            download_urls.append(download_url)
        # 提取过滤统计信息
        if r.get("source_filter_stats"):
            filter_stats["source"] = r.get("source_filter_stats")
        if r.get("target_filter_stats"):
            filter_stats["target"] = r.get("target_filter_stats")

    ctx.update({
        "phase": ReconAgentPhase.SHOWING_RESULT.value,
        "exec_status": "success",
        "recon_result": recon_result,
        "file_info_list": file_info_list,
        "output_files": output_files,
        "download_urls": download_urls,
        "filter_stats": filter_stats,
        "differences": [
            {
                "type": "matched_with_diff",
                "description": f"匹配但有差异: {total_diff} 条",
                "count": total_diff,
            },
            {
                "type": "source_only",
                "description": f"源文件独有: {total_source_only} 条",
                "count": total_source_only,
            },
            {
                "type": "target_only",
                "description": f"目标文件独有: {total_target_only} 条",
                "count": total_target_only,
            },
        ],
        "matched_count": total_matched,
        "unmatched_count": total_diff + total_source_only + total_target_only,
    })

    return {
        "messages": messages,
        "recon_ctx": ctx,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 节点 4：recon_result_node — 展示对账结果（数据差异）
# ══════════════════════════════════════════════════════════════════════════════

def recon_result_node(state: AgentState) -> dict:
    """向用户展示对账结果（数据差异摘要）。"""
    ctx = _get_recon_ctx(state)
    rule_code: str = ctx.get("rule_code", "（未知规则）")
    exec_status: str = ctx.get("exec_status", "error")

    messages: list = list(state.get("messages") or [])

    if exec_status == "success":
        rule_name: str = ctx.get("rule_name") or state.get("selected_rule_name") or ""
        file_info_list: list[dict] = ctx.get("file_info_list", [])
        download_urls: list[str] = ctx.get("download_urls", [])
        recon_result: dict = ctx.get("recon_result", {})

        # 构建规则展示文本
        if rule_name:
            rule_display = f"{rule_name}（{rule_code}）"
        else:
            rule_display = rule_code

        # 获取每个规则的详细结果
        results = recon_result.get("results", [])
        if not results and recon_result.get("success"):
            results = [recon_result]

        # 过滤掉没有匹配到文件的规则（source_file 或 target_file 为空）
        valid_results = []
        for result in results:
            source_file = result.get("source_file", "")
            target_file = result.get("target_file", "")
            # 只有当源文件和目标文件都存在时才显示
            if source_file and target_file:
                valid_results.append(result)

        # 构建每个规则的独立显示
        rule_sections = []
        for i, result in enumerate(valid_results, 1):
            rule_section = _build_single_rule_result(result, i)
            if rule_section:  # 只添加非空的结果
                rule_sections.append(rule_section)

        # 合并所有规则的结果显示
        all_rules_text = "\n\n".join(rule_sections)

        msg = (
            f"对账任务已完成。\n\n"
            f"**规则：** {rule_display}\n\n"
            f"---\n\n"
            f"{all_rules_text}\n\n"
            f"如需进一步分析或有疑问，请告知。"
        )
    else:
        exec_error: str = ctx.get("exec_error", "未知错误")
        msg = (
            f"对账任务执行失败。\n\n"
            f"**规则：** {rule_code}\n"
            f"**错误信息：** {exec_error}\n\n"
            f"请检查上传文件是否符合规则要求，或联系管理员排查问题。"
        )

    ctx.update({"phase": ReconAgentPhase.COMPLETED.value})
    return {
        "messages": messages + [AIMessage(content=msg)],
        "recon_ctx": ctx,
    }


def _build_single_rule_result(result: dict, index: int) -> str:
    """构建单个规则的详细结果显示（使用 Markdown 格式）"""
    rule_name = result.get("rule_name", f"规则{index}")

    # 获取文件信息
    source_file = result.get("source_file", "")
    target_file = result.get("target_file", "")

    # 如果缺少源文件或目标文件，则不显示此规则
    if not source_file or not target_file:
        return ""

    source_file_name = source_file.split("/")[-1] if "/" in source_file else source_file
    target_file_name = target_file.split("/")[-1] if "/" in target_file else target_file

    # 获取过滤统计
    source_filter_stats = result.get("source_filter_stats", {})
    target_filter_stats = result.get("target_filter_stats", {})

    # 获取统计数据
    matched_exact = result.get("matched_exact", 0)
    matched_with_diff = result.get("matched_with_diff", 0)
    source_only = result.get("source_only", 0)
    target_only = result.get("target_only", 0)
    total_matched = matched_exact + matched_with_diff
    total_diff = matched_with_diff + source_only + target_only

    # 获取下载链接
    download_url = result.get("download_url", "")

    # 构建过滤信息（分行显示，使用列表格式）
    filter_lines = []
    if source_filter_stats:
        orig = source_filter_stats.get('original_count', 0)
        filt = source_filter_stats.get('filtered_count', 0)
        removed = source_filter_stats.get('removed_count', 0)
        rate = source_filter_stats.get('filter_rate', 0)
        filter_lines.append(f"- 🔍 **源文件过滤**: {orig} → {filt} (过滤 {removed} 条, {rate}%)")
    if target_filter_stats:
        orig = target_filter_stats.get('original_count', 0)
        filt = target_filter_stats.get('filtered_count', 0)
        removed = target_filter_stats.get('removed_count', 0)
        rate = target_filter_stats.get('filter_rate', 0)
        filter_lines.append(f"- 🔍 **目标文件过滤**: {orig} → {filt} (过滤 {removed} 条, {rate}%)")
    filter_text = "\n".join(filter_lines)

    # 构建统计表格
    stats_table = (
        "| 类型 | 数量 | 说明 |\n"
        "|------|------|------|\n"
        f"| ✅ 完全匹配 | {matched_exact} | 数据完全一致 |\n"
        f"| ⚠️ 匹配有差异 | {matched_with_diff} | 关键列匹配但数值不同 |\n"
        f"| 📤 源文件独有 | {source_only} | 仅在源文件中存在 |\n"
        f"| 📥 目标文件独有 | {target_only} | 仅在目标文件中存在 |\n"
        f"| **合计** | **{total_matched + total_diff}** | 总记录数 |"
    )

    # 下载链接
    download_link = f"\n📄 **[查看详细差异报告]({download_url})**\n" if download_url else ""

    # 构建规则结果块（使用一级标题使规则名称更突出）
    section = (
        f"# **{rule_name}**\n\n"
        f"📁 **文件**: `{source_file_name}` ↔ `{target_file_name}`\n\n"
        f"{filter_text}\n\n"
        f"📊 **结果统计**:\n\n"
        f"{stats_table}\n"
        f"{download_link}\n"
        f"---\n"
    )

    return section
