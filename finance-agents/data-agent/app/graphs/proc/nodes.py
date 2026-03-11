"""proc 子图节点函数模块

包含数据整理工作流的4个核心节点：

  1. get_proc_rule_node      —— 从 PG 读取数据整理规则
  2. check_file_node         —— 校验上传文件（类型/必传/表头）
  3. proc_task_execute_node  —— 按 JSON 规则确定性执行数据整理
  4. result_node             —— 展示处理结果或返回错误信息

节点间通过 AgentState 的 proc_graph_ctx 子字典传递中间状态，
不污染主图其他字段。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from langchain_core.messages import AIMessage

from app.models import AgentState, ProcAgentPhase

logger = logging.getLogger(__name__)


# ── 常量 ──────────────────────────────────────────────────────────────────────

# 支持的文件扩展名（小写）
SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".csv"}


# ── 辅助函数 ─────────────────────────────────────────────────────────────────

def _get_proc_ctx(state: AgentState) -> dict[str, Any]:
    """安全地获取 proc_graph_ctx，不存在则返回空字典。"""
    return dict(state.get("proc_graph_ctx") or {})


def _run_async(coro):
    """在同步上下文中运行异步协程。"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def _load_rule_from_pg(rule_code: str, auth_token: str) -> dict[str, Any] | None:
    """从 PG（通过 MCP 工具）加载数据整理规则。
    
    同时获取：
    - 文件校验规则（bus_file_rules）
    - 整理规则（bus_proc_rules）
    
    Args:
        rule_code: 规则编码，如 "recognition"
        auth_token: JWT token
        
    Returns:
        合并后的规则对象，包含 file_validation_rules 和 proc_rules
    """
    from app.tools.mcp_client import get_file_validation_rule, get_proc_rule

    try:
        # 1. 获取文件校验规则
        file_rule_result = _run_async(get_file_validation_rule(rule_code=rule_code, auth_token=auth_token))
        logger.info(f"[proc_graph] 获取文件校验规则结果: success={file_rule_result.get('success')}")
        
        # 2. 获取整理规则
        proc_rule_result = _run_async(get_proc_rule(rule_code=rule_code, auth_token=auth_token))
        logger.info(f"[proc_graph] 获取整理规则结果: success={proc_rule_result.get('success')}")
        
        # 检查是否获取成功
        if not file_rule_result.get("success") and not proc_rule_result.get("success"):
            logger.warning(f"[proc_graph] 未找到规则 rule_code={rule_code}")
            return None
        
        # 合并规则
        combined_rule = {
            "rule_code": rule_code,
        }
        
        # 文件校验规则
        if file_rule_result.get("success"):
            file_data = file_rule_result.get("data") or {}
            # data 包含: id, rule_code, rule, memo
            file_rule_content = file_data.get("rule") or {}
            combined_rule["file_validation_rules"] = file_rule_content.get("file_validation_rules", {})
            combined_rule["file_rule_memo"] = file_data.get("memo", "")
        
        # 整理规则
        if proc_rule_result.get("success"):
            proc_data = proc_rule_result.get("data") or {}
            # data 包含: id, rule_code, rule, memo
            proc_rule_content = proc_data.get("rule") or {}
            combined_rule["role_desc"] = proc_rule_content.get("role_desc", "")
            combined_rule["rules"] = proc_rule_content.get("rules", [])
            combined_rule["proc_rule_memo"] = proc_data.get("memo", "")
        
        logger.info(
            f"[proc_graph] 规则加载成功 rule_code={rule_code}, "
            f"文件校验规则={'file_validation_rules' in combined_rule}, "
            f"整理规则数={len(combined_rule.get('rules', []))}"
        )
        return combined_rule
        
    except Exception as e:
        logger.error(f"[proc_graph] 读取规则失败 rule_code={rule_code}: {e}")
        return None


def _validate_files(
    uploaded_files: list[str],
    rule: dict[str, Any],
) -> tuple[bool, str]:
    """校验上传文件是否符合规则要求。

    Args:
        uploaded_files: 上传文件的路径列表
        rule: 从 PG 读取的规则 JSON

    Returns:
        (ok, reason) —— ok=True 表示通过，否则 reason 描述失败原因
    """
    file_validation = rule.get("file_validation_rules", {})
    table_schemas: list[dict] = file_validation.get("table_schemas", [])

    # ── 1. 文件数量校验 ──────────────────────────────────────────────────────
    if not uploaded_files:
        return False, "未检测到已上传的文件，请先上传所需文件后再试。"

    required_count = len([s for s in table_schemas if s.get("table_type") == "source"])
    if required_count > 0 and len(uploaded_files) < required_count:
        return False, (
            f"规则要求至少上传 {required_count} 个源文件，"
            f"当前仅上传了 {len(uploaded_files)} 个。"
        )

    # ── 2. 文件类型校验 ──────────────────────────────────────────────────────
    for fp in uploaded_files:
        ext = os.path.splitext(fp)[-1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return False, (
                f"文件「{os.path.basename(fp)}」格式不支持（{ext}），"
                f"请上传 {', '.join(sorted(SUPPORTED_EXTENSIONS))} 格式的文件。"
            )

    # ── 3. 表头校验（仅对 source 类型的 schema 做必填列校验） ─────────────────
    validation_config = file_validation.get("validation_config", {})
    case_sensitive: bool = validation_config.get("case_sensitive", False)
    ignore_whitespace: bool = validation_config.get("ignore_whitespace", True)

    source_schemas = [s for s in table_schemas if s.get("table_type") == "source"]
    if not source_schemas:
        # 规则未定义 schema，跳过表头校验
        return True, ""

    # 读取实际表头（仅做结构检查，不加载全量数据）
    for schema in source_schemas:
        required_cols: list[str] = schema.get("required_columns", [])
        if not required_cols:
            continue

        # 找到对应文件（简单策略：按序匹配）
        schema_idx = source_schemas.index(schema)
        if schema_idx >= len(uploaded_files):
            break
        file_path = uploaded_files[schema_idx]

        try:
            actual_cols = _read_header(file_path, ignore_whitespace=ignore_whitespace)
        except Exception as e:
            return False, f"读取文件「{os.path.basename(file_path)}」表头失败：{e}"

        if not case_sensitive:
            actual_cols_set = {c.lower() for c in actual_cols}
            missing = [
                c for c in required_cols
                if c.lower() not in actual_cols_set
            ]
        else:
            actual_cols_set = set(actual_cols)
            missing = [c for c in required_cols if c not in actual_cols_set]

        if missing:
            return False, (
                f"文件「{os.path.basename(file_path)}」缺少必需列：{missing}。\n"
                f"规则要求的必需列为：{required_cols}"
            )

    return True, ""


def _read_header(file_path: str, ignore_whitespace: bool = True) -> list[str]:
    """读取文件的第一行列名，支持 Excel / CSV。"""
    ext = os.path.splitext(file_path)[-1].lower()
    if ext in (".xlsx", ".xls"):
        import openpyxl
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        ws = wb.active
        header = [str(cell.value or "").strip() if ignore_whitespace else str(cell.value or "")
                  for cell in next(ws.iter_rows(max_row=1))]
        wb.close()
        return header
    elif ext == ".csv":
        import csv
        with open(file_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            row = next(reader, [])
        if ignore_whitespace:
            row = [c.strip() for c in row]
        return row
    else:
        raise ValueError(f"不支持的文件类型：{ext}")


# ══════════════════════════════════════════════════════════════════════════════
# 节点 0：welcome_node — 展示欢迎信息，引导用户上传文件
# ══════════════════════════════════════════════════════════════════════════════

def welcome_node(state: AgentState) -> dict:
    """展示数据整理任务开始的欢迎信息。

    显示已选择的规则名称，并引导用户上传待整理的数据文件。
    完成后 phase 不改变，直接流转到 get_proc_rule_node。
    """
    ctx = _get_proc_ctx(state)
    rule_code: str = ctx.get("rule_code") or state.get("selected_rule_code") or ""

    rule_display = f"**{rule_code}**" if rule_code else "（未指定）"

    msg = (
        f"📊 **开始数据整理任务**\n\n"
        f"已选择规则：{rule_display}\n\n"
    )

    logger.info(f"[proc_graph] welcome_node rule_code={rule_code!r}")
    return {
        "messages": [AIMessage(content=msg)],
    }


# ══════════════════════════════════════════════════════════════════════════════
# 节点 1：get_proc_rule_node — 从 PG 读取规则
# ══════════════════════════════════════════════════════════════════════════════

def get_proc_rule_node(state: AgentState) -> dict:
    """从 PostgreSQL 读取数据整理规则。

    - 若规则存在：将规则写入 proc_graph_ctx，phase → CHECKING_FILES
    - 若规则不存在：直接回复用户，phase → RULE_NOT_FOUND
    """
    ctx = _get_proc_ctx(state)
    
    # 优先从 ctx 中获取 rule_code，其次从 state 中获取
    rule_code: str = ctx.get("rule_code") or state.get("selected_rule_code") or ""
    auth_token: str = state.get("auth_token") or ""

    logger.info(f"[proc_graph] get_proc_rule_node rule_code={rule_code!r}")

    if not rule_code:
        msg = "未指定数据整理规则编码，请告知您要使用的规则。"
        ctx.update({"phase": ProcAgentPhase.RULE_NOT_FOUND.value, "error": msg})
        return {
            "messages": [AIMessage(content=msg)],
            "proc_graph_ctx": ctx,
        }
    
    rule = _load_rule_from_pg(rule_code=rule_code, auth_token=auth_token)
    
    if rule is None:
        msg = f"未找到规则编码为「{rule_code}」的数据整理规则。\n请确认规则编码是否正确，或联系管理员获取可用的规则列表。"
        ctx.update({"phase": ProcAgentPhase.RULE_NOT_FOUND.value, "error": msg})
        return {
            "messages": [AIMessage(content=msg)],
            "proc_graph_ctx": ctx,
        }
    
    ctx.update({
        "phase": ProcAgentPhase.CHECKING_FILES.value,
        "rule": rule,
        "rule_code": rule_code,
    })
    return {"proc_graph_ctx": ctx}


# ══════════════════════════════════════════════════════════════════════════════
# 节点 2：check_file_node — 文件类型/数量/表头校验
# ══════════════════════════════════════════════════════════════════════════════

def check_file_node(state: AgentState) -> dict:
    """校验已上传文件是否满足规则要求。

    - 通过：phase → EXECUTING
    - 不通过：回复错误原因，phase → FILE_CHECK_FAILED
    """
    ctx = _get_proc_ctx(state)
    rule: dict = ctx.get("rule") or {}
    rule_code: str = ctx.get("rule_code", "")
    uploaded_files: list[str] = list(state.get("uploaded_files") or [])

    logger.info(
        f"[proc_graph] check_file_node rule_code={rule_code!r} "
        f"files={[os.path.basename(f) for f in uploaded_files]}"
    )

    ok, reason = _validate_files(uploaded_files, rule)

    if not ok:
        file_validation = rule.get("file_validation_rules", {})
        table_schemas = file_validation.get("table_schemas", [])
        required_cols_all = [
            col
            for s in table_schemas
            if s.get("table_type") == "source"
            for col in s.get("required_columns", [])
        ]
        required_count = len([s for s in table_schemas if s.get("table_type") == "source"])

        msg = (
            f"文件校验失败：\n\n{reason}\n\n"
            f"**规则要求：**\n"
            f"- 支持文件类型：{', '.join(sorted(SUPPORTED_EXTENSIONS))}\n"
            f"- 需要上传文件数：{max(required_count, 1)} 个\n"
            f"- 必需列：{required_cols_all if required_cols_all else '（规则未指定）'}"
        )
        ctx.update({"phase": ProcAgentPhase.FILE_CHECK_FAILED.value, "error": reason})
        return {
            "messages": [AIMessage(content=msg)],
            "proc_graph_ctx": ctx,
        }

    ctx.update({"phase": ProcAgentPhase.EXECUTING.value})
    return {"proc_graph_ctx": ctx}



# ══════════════════════════════════════════════════════════════════════════════
# 节点 3：proc_task_execute_node — 按 JSON 规则确定性执行数据整理
# ══════════════════════════════════════════════════════════════════════════════

def proc_task_execute_node(state: AgentState) -> dict:
    """按规则中的 field_mappings 执行数据整理。

    当前实现将规则结构解析为执行计划并记录日志；
    实际数据转换逻辑由后续迭代接入 MCP 数据整理工具完成。
    """
    ctx = _get_proc_ctx(state)
    rule: dict = ctx.get("rule") or {}
    rule_code: str = ctx.get("rule_code", "")
    uploaded_files: list[str] = list(state.get("uploaded_files") or [])

    logger.info(f"[proc_graph] proc_task_execute_node rule_code={rule_code!r}")

    try:
        rules_list: list[dict] = rule.get("rules", [])
        execution_plan: list[dict] = []

        for r in rules_list:
            plan_item = {
                "rule_id": r.get("rule_id", ""),
                "description": r.get("description", ""),
                "source_table": r.get("source_table") or r.get("source_tables", []),
                "target_table": r.get("target_table", ""),
                "mapping_count": len(r.get("field_mappings", [])),
            }
            execution_plan.append(plan_item)

        logger.info(
            f"[proc_graph] 执行计划生成完成，共 {len(execution_plan)} 条规则，"
            f"文件：{[os.path.basename(f) for f in uploaded_files]}"
        )

        ctx.update({
            "phase": ProcAgentPhase.SHOWING_RESULT.value,
            "execution_plan": execution_plan,
            "exec_status": "success",
            "processed_files": [os.path.basename(f) for f in uploaded_files],
        })

    except Exception as e:
        logger.error(f"[proc_graph] 执行阶段异常：{e}")
        ctx.update({
            "phase": ProcAgentPhase.SHOWING_RESULT.value,
            "exec_status": "error",
            "exec_error": str(e),
        })

    return {"proc_graph_ctx": ctx}


# ══════════════════════════════════════════════════════════════════════════════
# 节点 4：result_node — 展示处理结果或返回错误信息
# ══════════════════════════════════════════════════════════════════════════════

def result_node(state: AgentState) -> dict:
    """向用户展示数据整理结果（成功摘要或错误详情）。"""
    ctx = _get_proc_ctx(state)
    rule_code: str = ctx.get("rule_code", "（未知规则）")
    exec_status: str = ctx.get("exec_status", "error")

    if exec_status == "success":
        execution_plan: list[dict] = ctx.get("execution_plan", [])
        processed_files: list[str] = ctx.get("processed_files", [])

        plan_lines = []
        for item in execution_plan:
            plan_lines.append(
                f"- **{item['rule_id']}**：{item['description']}"
                f"（字段映射数：{item['mapping_count']}）"
            )
        plan_text = "\n".join(plan_lines) if plan_lines else "（无规则详情）"

        msg = (
            f"数据整理任务已完成。\n\n"
            f"**规则编码：** {rule_code}\n"
            f"**处理文件：** {', '.join(processed_files) if processed_files else '（无）'}\n\n"
            f"**执行计划摘要：**\n{plan_text}\n\n"
            f"如需重新处理或使用其他规则，请告知。"
        )
    else:
        exec_error: str = ctx.get("exec_error", "未知错误")
        msg = (
            f"数据整理任务执行失败。\n\n"
            f"**规则编码：** {rule_code}\n"
            f"**错误信息：** {exec_error}\n\n"
            f"请检查上传文件是否符合规则要求，或联系管理员排查问题。"
        )

    ctx.update({"phase": ProcAgentPhase.COMPLETED.value})
    return {
        "messages": [AIMessage(content=msg)],
        "proc_graph_ctx": ctx,
    }
