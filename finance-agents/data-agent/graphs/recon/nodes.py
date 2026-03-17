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
    """调用 MCP 工具 recon_task_execution 执行对账任务。

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

    # 统一调用 audit_reconc_execute 工具（支持审计对账和普通对账）
    from tools.mcp_client import execute_audit_reconc

    # 构建 validated_files 参数
    validated_files = [
        {"file_path": f["file_path"], "table_name": f["table_name"]}
        for f in recon_files
    ]

    try:
        logger.info(
            f"[recon] 调用 audit_reconc_execute，"
            f"rule_code={rule_code}, "
            f"files={[f['table_name'] for f in validated_files]}"
        )
        recon_result = await execute_audit_reconc(
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
        f"[recon] audit_reconc_execute 结果: "
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

    # 判断规则类型并处理结果
    rule_type = recon_result.get("rule_type", "")
    is_audit_reconc = rule_type == "audit_reconc"

    # 提取文件信息（从对账结果中）
    file_info_list = []
    output_files = []
    
    if is_audit_reconc:
        # 审计对账结果处理
        results = recon_result.get("results", [])
        total_diff = sum(r.get("matched_with_diff", 0) for r in results)
        total_source_only = sum(r.get("source_only", 0) for r in results)
        total_target_only = sum(r.get("target_only", 0) for r in results)
        total_matched = sum(r.get("matched_exact", 0) for r in results)
        
        # 收集文件信息和输出报告路径
        for r in results:
            source_file = r.get("source_file", "")
            target_file = r.get("target_file", "")
            output_file = r.get("output_file", "")
            rule_name = r.get("rule_name", "")
            if source_file and target_file:
                file_info_list.append({
                    "rule_name": rule_name,
                    "source_file": source_file.split("/")[-1] if "/" in source_file else source_file,
                    "target_file": target_file.split("/")[-1] if "/" in target_file else target_file,
                })
            if output_file:
                output_files.append(output_file)

        ctx.update({
            "phase": ReconAgentPhase.SHOWING_RESULT.value,
            "exec_status": "success",
            "recon_result": recon_result,
            "is_audit_reconc": True,
            "file_info_list": file_info_list,
            "output_files": output_files,
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
    else:
        # 普通对账结果处理
        # 普通对账返回单个结果（包装在 results 中或作为顶层字段）
        result = recon_result.get("results", [{}])[0] if recon_result.get("results") else recon_result
        
        # 收集文件信息和输出报告路径
        source_file = result.get("source_file", "")
        target_file = result.get("target_file", "")
        output_file = result.get("output_file", "")
        if source_file and target_file:
            file_info_list.append({
                "rule_name": result.get("rule_name", ""),
                "source_file": source_file.split("/")[-1] if "/" in source_file else source_file,
                "target_file": target_file.split("/")[-1] if "/" in target_file else target_file,
            })
        if output_file:
            output_files.append(output_file)

        ctx.update({
            "phase": ReconAgentPhase.SHOWING_RESULT.value,
            "exec_status": "success",
            "recon_result": recon_result,
            "is_audit_reconc": False,
            "file_info_list": file_info_list,
            "output_files": output_files,
            "differences": [
                {
                    "type": "matched_with_diff",
                    "description": f"匹配但有差异: {result.get('matched_with_diff', 0)} 条",
                    "count": result.get("matched_with_diff", 0),
                },
                {
                    "type": "source_only",
                    "description": f"源文件独有: {result.get('source_only', 0)} 条",
                    "count": result.get("source_only", 0),
                },
                {
                    "type": "target_only",
                    "description": f"目标文件独有: {result.get('target_only', 0)} 条",
                    "count": result.get("target_only", 0),
                },
            ],
            "matched_count": result.get("matched_exact", 0),
            "unmatched_count": (
                result.get("matched_with_diff", 0) +
                result.get("source_only", 0) +
                result.get("target_only", 0)
            ),
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
        differences: list[dict] = ctx.get("differences", [])
        matched_count: int = ctx.get("matched_count", 0)
        unmatched_count: int = ctx.get("unmatched_count", 0)
        rule_name: str = ctx.get("rule_name") or state.get("selected_rule_name") or ""
        file_info_list: list[dict] = ctx.get("file_info_list", [])
        output_files: list[str] = ctx.get("output_files", [])

        # 构建规则展示文本
        if rule_name:
            rule_display = f"{rule_name}（{rule_code}）"
        else:
            rule_display = rule_code

        # 构建文件对账信息
        file_info_text = ""
        if file_info_list:
            file_info_lines = []
            for i, info in enumerate(file_info_list, 1):
                rule_name_display = info.get("rule_name", f"规则{i}")
                source_file = info.get("source_file", "未知")
                target_file = info.get("target_file", "未知")
                file_info_lines.append(f"{i}. **{rule_name_display}**：`{source_file}` ↔ `{target_file}`")
            file_info_text = "\n".join(file_info_lines)
        else:
            file_info_text = "（未获取文件信息）"

        # 构建差异摘要（只显示中文描述，不显示技术字段名）
        diff_lines = []
        for diff in differences[:10]:  # 最多展示10条差异
            desc = diff.get("description", "")
            if desc:
                diff_lines.append(f"- {desc}")

        if len(differences) > 10:
            diff_lines.append(f"- ... 还有 {len(differences) - 10} 条差异")

        diff_text = "\n".join(diff_lines) if diff_lines else "（无差异）"

        # 构建报告文件链接（HTTP 下载链接）
        report_text = ""
        if output_files:
            # 获取 MCP 服务基础 URL
            try:
                from config import FINANCE_MCP_BASE_URL
                mcp_base_url = FINANCE_MCP_BASE_URL.rstrip("/")
            except Exception:
                mcp_base_url = "http://localhost:3335"
            
            report_lines = []
            for i, output_file in enumerate(output_files, 1):
                # 提取文件名
                file_name = output_file.split("/")[-1] if "/" in output_file else output_file
                # 生成下载 URL: /recon/download/{filename}
                download_url = f"{mcp_base_url}/recon/download/{file_name}"
                report_lines.append(f"- [详细差异报告 {i}]({download_url})：{file_name}")
            report_text = "\n".join(report_lines) + "\n\n"

        msg = (
            f"对账任务已完成。\n\n"
            f"**规则：** {rule_display}\n\n"
            f"**对账文件：**\n{file_info_text}\n\n"
            f"**统计：**\n"
            f"- 匹配记录：{matched_count} 条\n"
            f"- 差异记录：{unmatched_count} 条\n\n"
            f"**数据差异：**\n{diff_text}\n\n"
            f"{report_text}"
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
