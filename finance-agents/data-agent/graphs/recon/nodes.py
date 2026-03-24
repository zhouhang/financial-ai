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
    _build_upload_name_maps,
    get_rule_node,
    check_file_node,
    _get_proc_ctx,
    _to_abs_path,
    _to_upload_ref,
)
from .execution_service import (
    build_recon_observation,
    build_execution_request,
    build_recon_ctx_update_from_execution,
    resolve_recon_inputs,
    run_recon_execution,
)


# ── 辅助函数 ─────────────────────────────────────────────────────────────────

def _get_recon_ctx(state: AgentState) -> dict[str, Any]:
    """安全地获取 recon_ctx，不存在则返回空字典。"""
    return dict(state.get("recon_ctx") or {})


def _to_int(value: Any) -> int:
    """安全转换为 int，异常时返回 0。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _build_recon_execution_summary(
    *,
    execution_status: str,
    ctx_update: dict[str, Any],
) -> str:
    """构建 recon_task_execution_node 的完成摘要消息。"""
    matched_count = _to_int(ctx_update.get("matched_count"))
    unmatched_count = _to_int(ctx_update.get("unmatched_count"))
    total_count = matched_count + unmatched_count

    differences = list(ctx_update.get("differences") or [])
    diff_lines: list[str] = []
    for item in differences:
        if not isinstance(item, dict):
            continue
        count = _to_int(item.get("count"))
        description = str(item.get("description") or "").strip()
        if count > 0 and description:
            diff_lines.append(f"- {description}")

    recon_result = ctx_update.get("recon_result") if isinstance(ctx_update.get("recon_result"), dict) else {}
    results = list(recon_result.get("results") or [])
    if not results and recon_result.get("success"):
        results = [recon_result]
    succeeded_rules = sum(1 for r in results if isinstance(r, dict) and r.get("status", "succeeded") == "succeeded")
    skipped_rules = len(list(ctx_update.get("skipped_results") or []))
    failed_rules = len(list(ctx_update.get("failed_results") or []))

    if execution_status == "skipped":
        return (
            "对账执行已完成，本次未生成有效结果。\n\n"
            "正在整理规则跳过原因并生成详细说明。"
        )

    lines = [
        f"对账执行已完成：共处理 {total_count} 条，匹配 {matched_count} 条，异常 {unmatched_count} 条。"
    ]

    if execution_status == "partial_success":
        lines.append(
            f"规则执行情况：成功 {succeeded_rules} 条，跳过 {skipped_rules} 条，失败 {failed_rules} 条。"
        )

    if diff_lines:
        lines.append("")
        lines.append("异常分布：")
        lines.extend(diff_lines)

    lines.append("")
    lines.append("正在生成详细结果，请稍候。")
    return "\n".join(lines)


def _build_recon_execution_error_summary(rule_display: str, error_msg: str) -> str:
    """构建 recon 执行节点失败摘要（用于替换执行中占位）。"""
    detail = (error_msg or "未知错误").strip()
    if len(detail) > 240:
        detail = detail[:240] + "..."
    return (
        "对账执行失败，正在整理错误详情。\n\n"
        f"- 规则：{rule_display}\n"
        f"- 错误摘要：{detail}"
    )


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
    rule_id: str = ctx.get("rule_id", "")
    rule: dict = ctx.get("rule", {})
    rule_name: str = str(ctx.get("rule_name") or state.get("selected_rule_name") or rule_code)
    auth_token: str = state.get("auth_token") or ""

    messages: list = []

    logger.info(f"[recon] recon_task_execution_node rule_code={rule_code!r}")

    recon_inputs, ref_to_display_name, input_error = resolve_recon_inputs(state=state, ctx=ctx)
    if input_error:
        logger.error(f"[recon] {input_error}")
        ctx.update({
            "phase": ReconAgentPhase.EXEC_FAILED.value,
            "exec_status": "error",
            "exec_error": input_error,
        })
        return {
            "messages": [AIMessage(content=_build_recon_execution_error_summary(rule_name, input_error))],
            "recon_ctx": ctx,
        }

    execution_request, request_error = build_execution_request(
        rule_code=rule_code,
        rule_id=rule_id,
        auth_token=auth_token,
        recon_inputs=recon_inputs,
        run_context=ctx.get("run_context") if isinstance(ctx.get("run_context"), dict) else {},
    )
    if request_error:
        logger.error(f"[recon] {request_error}")
        ctx.update({
            "phase": ReconAgentPhase.EXEC_FAILED.value,
            "exec_status": "error",
            "exec_error": request_error,
        })
        return {
            "messages": [AIMessage(content=_build_recon_execution_error_summary(rule_name, request_error))],
            "recon_ctx": ctx,
        }

    logger.info(
        f"[recon] 调用 recon_execute, rule_code={rule_code}, "
        f"inputs={[item.get('table_name') for item in execution_request.get('validated_inputs', [])]}"
    )
    recon_result, exec_error = await run_recon_execution(execution_request)
    if exec_error:
        logger.error(f"[recon] {exec_error}")
        ctx.update({
            "phase": ReconAgentPhase.EXEC_FAILED.value,
            "exec_status": "error",
            "exec_error": exec_error,
            "execution_request": execution_request,
        })
        return {
            "messages": [AIMessage(content=_build_recon_execution_error_summary(rule_name, exec_error))],
            "recon_ctx": ctx,
        }

    logger.info(
        f"[recon] recon_execute 结果: "
        f"success={recon_result.get('success')}, "
        f"rule_type={recon_result.get('rule_type')}"
    )

    run_context = ctx.get("run_context") if isinstance(ctx.get("run_context"), dict) else {}
    run_context = {
        **run_context,
        "trigger_type": str(run_context.get("trigger_type") or "chat"),
        "entry_mode": str(run_context.get("entry_mode") or "file"),
    }
    recon_observation = build_recon_observation(
        rule_code=rule_code,
        rule_name=rule_name,
        rule=rule if isinstance(rule, dict) else {},
        trigger_type=str(run_context.get("trigger_type") or "chat"),
        entry_mode=str(run_context.get("entry_mode") or "file"),
        recon_inputs=recon_inputs,
        recon_result=recon_result if isinstance(recon_result, dict) else {},
        run_context=run_context,
        run_id=str(ctx.get("run_id") or ""),
        ref_to_display_name=ref_to_display_name,
    )

    execution_ctx = build_recon_ctx_update_from_execution(
        recon_result=recon_result if isinstance(recon_result, dict) else {},
        recon_inputs=recon_inputs,
        execution_request=execution_request,
        ref_to_display_name=ref_to_display_name,
        recon_observation=recon_observation,
    )
    ctx_update = execution_ctx.get("ctx_update") if isinstance(execution_ctx.get("ctx_update"), dict) else {}
    execution_status = str(execution_ctx.get("execution_status", "success"))

    if not execution_ctx.get("ok"):
        exec_error_msg = str(execution_ctx.get("exec_error", "对账执行失败"))
        ctx.update({
            "phase": ReconAgentPhase.EXEC_FAILED.value,
            "exec_status": execution_status,
            "exec_error": exec_error_msg,
            **ctx_update,
        })
        return {
            "messages": [AIMessage(content=_build_recon_execution_error_summary(rule_name, exec_error_msg))],
            "recon_ctx": ctx,
        }

    summary_msg = _build_recon_execution_summary(
        execution_status=execution_status,
        ctx_update=ctx_update,
    )
    if summary_msg:
        messages.append(AIMessage(content=summary_msg))

    ctx.update({
        "phase": ReconAgentPhase.SHOWING_RESULT.value,
        "exec_status": execution_status,
        "exec_error": "",
        "run_context": run_context,
        **ctx_update,
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

    messages: list = []

    if exec_status in {"success", "partial_success", "skipped"}:
        rule_name: str = ctx.get("rule_name") or state.get("selected_rule_name") or ""
        recon_result: dict = ctx.get("recon_result", {})
        skipped_results: list[dict] = ctx.get("skipped_results", [])
        failed_results: list[dict] = ctx.get("failed_results", [])
        summary: dict = recon_result.get("summary", {})

        # 构建规则展示文本
        if rule_name:
            rule_display = rule_name
        else:
            rule_display = rule_code

        # 获取每个规则的详细结果
        results = recon_result.get("results", [])
        if not results and recon_result.get("success"):
            results = [recon_result]
        valid_results = [result for result in results if result.get("status", "succeeded") == "succeeded"]

        # 构建每个规则的独立显示
        _, ref_to_display_name = _build_upload_name_maps(list(state.get("uploaded_files") or []))
        diff_label = _build_diff_description(ctx)
        show_rule_title = len(valid_results) > 1
        rule_sections = []
        for i, result in enumerate(valid_results, 1):
            rule_section = _build_single_rule_result(
                result,
                i,
                ref_to_display_name=ref_to_display_name,
                diff_label=diff_label,
                show_rule_title=show_rule_title,
            )
            if rule_section:  # 只添加非空的结果
                rule_sections.append(rule_section)

        # 合并所有规则的结果显示
        all_rules_text = "\n\n".join(rule_sections)
        extra_sections: list[str] = []
        if exec_status == "partial_success":
            extra_sections.append(
                f"本次执行为部分成功：成功 {summary.get('succeeded_rules', len(valid_results))} 条，"
                f"跳过 {summary.get('skipped_rules', len(skipped_results))} 条，"
                f"失败 {summary.get('failed_rules', len(failed_results))} 条。"
            )
        elif exec_status == "skipped":
            extra_sections.append("本次未生成对账结果，所有规则都被跳过。")
        if skipped_results:
            extra_sections.append(_build_rule_status_list("跳过规则", skipped_results, reason_key="skip_reason"))
        if failed_results:
            extra_sections.append(_build_rule_status_list("失败规则", failed_results, reason_key="error"))
        extra_text = "\n\n".join(section for section in extra_sections if section)

        msg = (
            f"以下是详细对账结果。\n\n"
            f"**规则：** {rule_display}\n\n"
            f"---\n\n"
            f"{all_rules_text}"
            f"{f'{chr(10) * 2}{extra_text}' if extra_text else ''}\n\n"
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
        "messages": [AIMessage(content=msg)],
        "recon_ctx": ctx,
        "uploaded_files": [],
    }


def _build_single_rule_result(
    result: dict,
    index: int,
    *,
    ref_to_display_name: dict[str, str],
    diff_label: str,
    show_rule_title: bool,
) -> str:
    """构建单个规则的详细结果显示（使用 Markdown 格式）"""
    rule_name = result.get("rule_name", f"规则{index}")

    # 获取文件信息
    source_file = result.get("source_file", "")
    target_file = result.get("target_file", "")

    # 如果缺少源文件或目标文件，则不显示此规则
    if not source_file or not target_file:
        return ""

    source_file_name = ref_to_display_name.get(source_file, source_file.split("/")[-1] if "/" in source_file else source_file)
    target_file_name = ref_to_display_name.get(target_file, target_file.split("/")[-1] if "/" in target_file else target_file)

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
        f"| ⚠️ 匹配有差异 | {matched_with_diff} | {diff_label} |\n"
        f"| 📤 {source_file_name}独有 | {source_only} | 仅在{source_file_name}中存在 |\n"
        f"| 📥 {target_file_name}独有 | {target_only} | 仅在{target_file_name}中存在 |\n"
        f"| **合计** | **{total_matched + total_diff}** | 总记录数 |"
    )

    # 下载链接
    download_link = f"\n📄 **[查看详细差异报告]({download_url})**\n" if download_url else ""

    # 构建规则结果块（使用一级标题使规则名称更突出）
    title = f"# **{rule_name}**\n\n" if show_rule_title else ""
    section = (
        f"{title}"
        f"📁 **文件**: `{source_file_name}` ↔ `{target_file_name}`\n\n"
        f"{filter_text}\n\n"
        f"📊 **结果统计**:\n\n"
        f"{stats_table}\n"
        f"{download_link}\n"
        f"---\n"
    )

    return section


def _build_diff_description(ctx: dict[str, Any]) -> str:
    """根据规则配置生成差异说明。"""
    rule = ctx.get("rule") or {}
    rules = rule.get("rules") or []
    first_rule = rules[0] if rules else {}
    recon_config = first_rule.get("recon") or first_rule.get("reconciliation_config") or {}

    key_config = recon_config.get("key_columns") or {}
    mappings = key_config.get("mappings") or []
    if not mappings:
        source_field = (key_config.get("source_field") or "").strip()
        target_field = (key_config.get("target_field") or "").strip()
        if source_field and target_field:
            mappings = [{"source_field": source_field, "target_field": target_field}]

    key_labels: list[str] = []
    for mapping in mappings:
        key_source = (mapping.get("source_field") or "").strip()
        key_target = (mapping.get("target_field") or "").strip()
        if key_source and key_target and key_source != key_target:
            key_labels.append(f"{key_source}/{key_target}")
        elif key_source or key_target:
            key_labels.append(key_source or key_target)
    key_label = " + ".join(key_labels) if key_labels else "关键列"

    compare_columns = (recon_config.get("compare_columns") or {}).get("columns") or []
    compare_item = compare_columns[0] if compare_columns else {}
    compare_label = (
        (compare_item.get("name") or "").strip()
        or (compare_item.get("alias") or "").strip()
        or (compare_item.get("source_column") or "").strip()
        or (compare_item.get("target_column") or "").strip()
        or (compare_item.get("column") or "").strip()
        or "数值"
    )
    return f"{key_label}匹配但{compare_label}不同"


def _build_rule_status_list(title: str, results: list[dict], reason_key: str) -> str:
    """构建跳过/失败规则列表。"""
    if not results:
        return ""

    lines = [f"## {title}"]
    for item in results:
        rule_name = item.get("rule_name") or item.get("rule_id") or "未命名规则"
        reason = item.get(reason_key) or item.get("message") or "未提供原因"
        lines.append(f"- **{rule_name}**: {reason}")
    return "\n".join(lines)
