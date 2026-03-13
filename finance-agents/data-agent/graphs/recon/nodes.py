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

    通过调用公共节点 get_rule_node 实现，将 recon_ctx 映射到 proc_ctx。

    - 若规则存在：将规则写入 recon_ctx，phase → CHECKING_FILES
    - 若规则不存在：直接回复用户，phase → RULE_NOT_FOUND
    """
    ctx = _get_recon_ctx(state)
    rule_code: str = ctx.get("rule_code") or state.get("selected_rule_code") or ""

    logger.info(f"[recon] get_rule_node_for_recon rule_code={rule_code!r}")

    # 临时将 recon_ctx 复制到 proc_ctx 以复用公共节点
    temp_state = dict(state)
    temp_state["proc_ctx"] = ctx

    # 调用公共节点
    result = await get_rule_node(temp_state)

    # 将结果从 proc_ctx 复制回 recon_ctx
    result_ctx = result.get("proc_ctx", {})
    ctx.update(result_ctx)

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
    """
    ctx = _get_recon_ctx(state)
    file_rule_code: str = ctx.get("file_rule_code") or ctx.get("rule_code") or ""
    raw_files: list = list(state.get("uploaded_files") or [])

    messages: list = list(state.get("messages") or [])

    # 提取文件路径
    uploaded_files: list[str] = []
    for item in raw_files:
        if isinstance(item, dict):
            fp = item.get("file_path") or item.get("path") or ""
        else:
            fp = str(item)
        if fp:
            uploaded_files.append(_to_abs_path(fp))

    logger.info(
        f"[recon] check_file_node_for_recon file_rule_code={file_rule_code!r} "
        f"files={[fp.split('/')[-1] for fp in uploaded_files]}"
    )

    # 文件列表不能为空
    if not uploaded_files:
        reason = "未检测到已上传的文件，请先上传所需文件后再试。"
        msg = f"文件校验失败：\n\n{reason}"
        ctx.update({"phase": ReconAgentPhase.FILE_CHECK_FAILED.value, "error": reason})
        return {
            "messages": messages + [AIMessage(content=msg)],
            "recon_ctx": ctx,
        }

    # 临时将 recon_ctx 复制到 proc_ctx 以复用公共节点
    temp_state = dict(state)
    temp_state["proc_ctx"] = ctx
    temp_state["file_rule_code"] = file_rule_code

    # 调用公共节点（已在顶部导入）
    result = await check_file_node(temp_state)
    
    # 将结果从 proc_ctx 复制回 recon_ctx
    result_ctx = result.get("proc_ctx", {})
    ctx.update(result_ctx)
    
    # 转换 phase
    phase = ctx.get("phase", "")
    if phase == "executing":  # ProcAgentPhase.EXECUTING
        ctx["phase"] = ReconAgentPhase.EXECUTING.value
    
    return {
        "messages": result.get("messages", messages),
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

    # 调用 MCP 工具 recon_task_execution
    from tools.mcp_client import execute_recon_task

    try:
        logger.info(
            f"[recon] 调用 recon_task_execution，"
            f"files={[f['file_name'] for f in recon_files]}"
        )
        recon_result = await execute_recon_task(
            files=recon_files,
            rule_code=rule_code,
            auth_token=state.get("auth_token") or "",
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
        f"[recon] recon_task_execution 结果: "
        f"success={recon_result.get('success')}"
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

    # 执行成功
    ctx.update({
        "phase": ReconAgentPhase.SHOWING_RESULT.value,
        "exec_status": "success",
        "recon_result": recon_result,
        "differences": recon_result.get("differences", []),
        "matched_count": recon_result.get("matched_count", 0),
        "unmatched_count": recon_result.get("unmatched_count", 0),
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

        # 构建规则展示文本
        if rule_name:
            rule_display = f"{rule_name}（{rule_code}）"
        else:
            rule_display = rule_code

        # 构建差异摘要
        diff_lines = []
        for diff in differences[:10]:  # 最多展示10条差异
            diff_type = diff.get("type", "unknown")
            desc = diff.get("description", "")
            diff_lines.append(f"- **{diff_type}**: {desc}")

        if len(differences) > 10:
            diff_lines.append(f"- ... 还有 {len(differences) - 10} 条差异")

        diff_text = "\n".join(diff_lines) if diff_lines else "（无差异）"

        msg = (
            f"对账任务已完成。\n\n"
            f"**规则：** {rule_display}\n\n"
            f"**统计：**\n"
            f"- 匹配记录：{matched_count} 条\n"
            f"- 差异记录：{unmatched_count} 条\n\n"
            f"**数据差异：**\n{diff_text}\n\n"
            f"如需查看详细差异或导出报告，请告知。"
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
