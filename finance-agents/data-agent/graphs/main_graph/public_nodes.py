"""公共节点函数模块

包含可被多个子图共享的通用节点函数。
"""

from __future__ import annotations

import csv
import logging
import os
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage

from config import UPLOAD_DIR
from models import AgentState, ProcAgentPhase

logger = logging.getLogger(__name__)


# ── 常量 ──────────────────────────────────────────────────────────────────────

# 支持的文件扩展名（小写）
SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".csv"}


# ── 辅助函数 ─────────────────────────────────────────────────────────────────

def _get_proc_ctx(state: AgentState) -> dict[str, Any]:
    """安全地获取 proc_ctx，不存在则返回空字典。"""
    return dict(state.get("proc_ctx") or {})


def _to_abs_path(file_path: str) -> str:
    """将上传文件的相对路径转为绝对路径。

    file_path 可能是 /uploads/2026/3/11/xxx.xlsx（相对路径），
    需要拼接 UPLOAD_DIR 根目录才能在本机找到文件。
    如果已经是存在的绝对路径则直接返回。
    """
    p = Path(file_path)
    if p.is_absolute() and p.exists():
        return str(p)
    # 去掉开头的 /uploads 或 uploads 前缀，拼接 UPLOAD_DIR
    rel = file_path.lstrip("/")
    if rel.startswith("uploads/"):
        rel = rel[len("uploads/"):]
    return str(Path(UPLOAD_DIR) / rel)


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
        with open(file_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            row = next(reader, [])
        if ignore_whitespace:
            row = [c.strip() for c in row]
        return row
    else:
        raise ValueError(f"不支持的文件类型：{ext}")


async def _load_rule_from_pg(rule_code: str, auth_token: str) -> dict[str, Any] | None:
    """从 PG（通过 MCP 工具）加载规则。
    
    从 bus_rules 表获取规则记录，包含：
    - 文件校验规则（file_validation_rules）
    - 整理规则（role_desc, rules）
    
    Args:
        rule_code: 规则编码，如 "recognition"
        auth_token: JWT token
        
    Returns:
        规则对象，包含 file_validation_rules 和 proc_rules
    """
    from tools.mcp_client import get_file_validation_rule

    try:
        # 获取规则（get_rule_from_bus 返回完整规则记录）
        rule_result = await get_file_validation_rule(rule_code=rule_code, auth_token=auth_token)
        logger.info(f"[public_nodes] rule_code={rule_code}; 获取规则结果: success={rule_result.get('success')}")
        
        if not rule_result.get("success", False):
            logger.warning(f"[public_nodes] 未找到规则 rule_code={rule_code}")
            return None
        
        # 解析规则内容
        rule_data = rule_result.get("data") or {}
        # data 包含: id, rule_code, rule, memo
        rule_content = rule_data.get("rule") or {}
        
        combined_rule = {
            "rule_code": rule_code,
            # 文件校验规则
            "file_validation_rules": rule_content.get("file_validation_rules", {}),
            "file_rule_memo": rule_data.get("memo", ""),
            # 整理规则
            "role_desc": rule_content.get("role_desc", ""),
            "rules": rule_content.get("rules", []),
            "proc_rule_memo": rule_data.get("memo", ""),
        }
        
        logger.info(
            f"[public_nodes] 规则加载成功 rule_code={rule_code}, "
            f"文件校验规则={'file_validation_rules' in combined_rule}, "
            f"整理规则数={len(combined_rule.get('rules', []))}"
        )
        return combined_rule
        
    except Exception as e:
        logger.error(f"[public_nodes] 读取规则失败 rule_code={rule_code}: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# 公共节点：get_rule_node — 从 PG 读取规则
# ══════════════════════════════════════════════════════════════════════════════

async def get_rule_node(state: AgentState) -> dict:
    """从 PostgreSQL 读取规则。

    - 若规则存在：将规则写入 proc_ctx，phase → CHECKING_FILES
    - 若规则不存在：直接回复用户，phase → RULE_NOT_FOUND
    
    这是一个公共节点，可被多个子图共享使用。
    """
    ctx = _get_proc_ctx(state)

    # 优先从 ctx 中获取 rule_code，其次从 state 中获取
    rule_code: str = ctx.get("rule_code") or state.get("selected_rule_code") or ""
    auth_token: str = state.get("auth_token") or ""

    logger.info(f"[public_nodes] get_rule_node rule_code={rule_code!r}")

    messages: list = list(state.get("messages") or [])

    if not rule_code:
        msg = "未指定规则编码，请告知您要使用的规则。"
        ctx.update({"phase": ProcAgentPhase.RULE_NOT_FOUND.value, "error": msg})
        return {
            "messages": messages + [AIMessage(content=msg)],
            "proc_ctx": ctx,
        }

    rule = await _load_rule_from_pg(rule_code=rule_code, auth_token=auth_token)

    if rule is None:
        msg = f"未找到规则编码为「{rule_code}」的规则。\n请确认规则编码是否正确，或联系管理员获取可用的规则列表。"
        ctx.update({"phase": ProcAgentPhase.RULE_NOT_FOUND.value, "error": msg})
        return {
            "messages": messages + [AIMessage(content=msg)],
            "proc_ctx": ctx,
        }

    ctx.update({
        "phase": ProcAgentPhase.CHECKING_FILES.value,
        "rule": rule,
        "rule_code": rule_code,
    })
    return {
        "messages": messages,
        "proc_ctx": ctx,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 公共节点：check_file_node — 文件类型/数量/表头校验
# ══════════════════════════════════════════════════════════════════════════════

async def check_file_node(state: AgentState) -> dict:
    """校验已上传文件是否满足规则要求。

    通过调用 MCP 工具 validate_uploaded_files 执行校验：
    - 读取每个文件的列名
    - 调用 validate_uploaded_files tool 进行全量列名精确匹配
    - 通过：phase → EXECUTING
    - 不通过：回复错误原因，phase → FILE_CHECK_FAILED
    
    这是一个公共节点，可被多个子图共享使用。
    """
    ctx = _get_proc_ctx(state)
    # 文件校验规则编码（优先从 file_rule_code 获取，用于文件校验）
    # ⚠️ file_rule_code 和 rule_code 是不同的概念，不能互相 fallback
    file_rule_code: str = ctx.get("file_rule_code") or state.get("file_rule_code") or ""

    raw_files: list = list(state.get("uploaded_files") or [])

    messages: list = list(state.get("messages") or [])

    # uploaded_files 可能是 str 路径或 dict（{file_path, original_filename}），统一提取绝对路径
    uploaded_files: list[str] = []
    for item in raw_files:
        if isinstance(item, dict):
            fp = item.get("file_path") or item.get("path") or ""
        else:
            fp = str(item)
        if fp:
            uploaded_files.append(_to_abs_path(fp))

    logger.info(
        f"[public_nodes] check_file_node file_rule_code={file_rule_code!r} "
        f"files={[os.path.basename(f) for f in uploaded_files]}"
    )

    # ── 0. 检查 file_rule_code 是否配置 ──────────────────────────────────────
    if not file_rule_code:
        reason = "未配置文件校验规则编码（file_rule_code），请联系管理员配置规则的文件校验规则。"
        msg = f"文件校验失败：\n\n{reason}"
        ctx.update({"phase": ProcAgentPhase.FILE_CHECK_FAILED.value, "error": reason})
        return {
            "messages": messages + [AIMessage(content=msg)],
            "proc_ctx": ctx,
        }

    # ── 1. 基础判断：文件列表不能为空 ───────────────────────────────────────
    if not uploaded_files:
        reason = "未检测到已上传的文件，请先上传所需文件后再试。"
        msg = f"文件校验失败：\n\n{reason}"
        ctx.update({"phase": ProcAgentPhase.FILE_CHECK_FAILED.value, "error": reason})
        return {
            "messages": messages + [AIMessage(content=msg)],
            "proc_ctx": ctx,
        }

    # ── 2. 文件类型校验 ──────────────────────────────────────────────────
    for fp in uploaded_files:
        ext = os.path.splitext(fp)[-1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            reason = (
                f"文件「{os.path.basename(fp)}」格式不支持（{ext}），"
                f"请上传 {', '.join(sorted(SUPPORTED_EXTENSIONS))} 格式的文件。"
            )
            msg = f"文件校验失败：\n\n{reason}"
            ctx.update({"phase": ProcAgentPhase.FILE_CHECK_FAILED.value, "error": reason})
            return {
                "messages": messages + [AIMessage(content=msg)],
                "proc_ctx": ctx,
            }

    # ── 3. 读取各文件列名，构建 tool 参数 ────────────────────────────────
    files_with_columns: list[dict] = []
    for fp in uploaded_files:
        try:
            columns = _read_header(fp, ignore_whitespace=True)
            files_with_columns.append({
                "file_name": os.path.basename(fp),
                "columns": columns,
            })
            logger.info(
                f"[public_nodes] 读取列名成功: {os.path.basename(fp)}, 共 {len(columns)} 列"
            )
        except Exception as e:
            reason = f"读取文件「{os.path.basename(fp)}」表头失败：{e}"
            msg = f"文件校验失败：\n\n{reason}"
            ctx.update({"phase": ProcAgentPhase.FILE_CHECK_FAILED.value, "error": reason})
            return {
                "messages": messages + [AIMessage(content=msg)],
                "proc_ctx": ctx,
            }

    # ── 4. 调用 MCP tool validate_uploaded_files 执行全量列名精确匹配 ─────────
    from tools.mcp_client import validate_uploaded_files as mcp_validate_files

    try:
        validate_result = await mcp_validate_files(
            uploaded_files=files_with_columns,
            rule_code=file_rule_code,
        )
    except Exception as e:
        reason = f"调用文件校验服务失败：{e}"
        logger.error(f"[public_nodes] check_file_node 校验工具调用异常: {e}")
        msg = f"文件校验失败：\n\n{reason}"
        ctx.update({"phase": ProcAgentPhase.FILE_CHECK_FAILED.value, "error": reason})
        return {
            "messages": messages + [AIMessage(content=msg)],
            "proc_ctx": ctx,
        }

    logger.info(
        f"[public_nodes] check_file_node 校验结果: success={validate_result.get('success')}, "
        f"matched={len(validate_result.get('matched_results', []))}, "
        f"unmatched={validate_result.get('unmatched_count', 0)}"
    )

    # ── 5. 处理校验结果 ──────────────────────────────────────────────────────
    if not validate_result.get("success"):
        error_msg = validate_result.get("error", "文件校验未通过")

        # 展示未匹配信息和缺少的必传表
        missing_tables = validate_result.get("missing_necessary_tables", [])
        unmatched_files = validate_result.get("unmatched_files", [])

        detail_lines = []
        if missing_tables:
            missing_names = ", ".join(t["table_name"] for t in missing_tables)
            detail_lines.append(f"缺少必传文件类型：{missing_names}")
        if unmatched_files:
            detail_lines.append(f"未能识别的文件：{', '.join(unmatched_files)}")

        detail_text = "\n".join(f"- {line}" for line in detail_lines) if detail_lines else ""
        msg = (
            f"文件校验失败：\n\n{error_msg}"
            + (f"\n\n**详情：**\n{detail_text}" if detail_text else "")
        )
        ctx.update({"phase": ProcAgentPhase.FILE_CHECK_FAILED.value, "error": error_msg})
        return {
            "messages": messages + [AIMessage(content=msg)],
            "proc_ctx": ctx,
        }

    # ── 6. 校验通过：将匹配结果写入 ctx ─────────────────────────────────
    matched_results: list[dict] = validate_result.get("matched_results", [])

    # 构建文件匹配结果提示（每个文件对应的表规则）
    match_lines = []
    for m in matched_results:
        fname = m.get("file_name", "")
        tname = m.get("table_name", "")
        if fname and tname:
            match_lines.append(f"- **{fname}** → {tname}")

    unmatched_files: list = validate_result.get("unmatched_files", [])
    # 构建文件名 -> 列名 的映射，用于展示未匹配文件的原始列
    file_columns_map: dict[str, list[str]] = {
        f["file_name"]: f.get("columns", [])
        for f in files_with_columns
    }
    unmatch_lines = []
    for f in unmatched_files:
        cols = file_columns_map.get(f, [])
        cols_text = "、".join(cols) if cols else "（无法读取列名）"
        unmatch_lines.append(
            f"- **{f}** ⚠️ 未能识别\n"
            f"  - 原因：该文件不在规则预定义的表范围内，将被跳过\n"
            f"  - 文件列名：{cols_text}"
        )

    summary_parts = []
    if match_lines:
        summary_parts.append("✅ **已匹配：**\n" + "\n".join(match_lines))
    if unmatch_lines:
        summary_parts.append("⚠️ **未匹配：**\n" + "\n".join(unmatch_lines))

    file_match_summary = (
        "\n\n**文件识别结果：**\n" + "\n\n".join(summary_parts)
        if summary_parts else ""
    )

    completion_msg = f"文件校验通过。{file_match_summary}"

    ctx.update({
        "phase": ProcAgentPhase.EXECUTING.value,
        "file_match_results": matched_results,   # [{file_name, table_id, table_name}]
    })
    return {
        "messages": messages + [AIMessage(content=completion_msg)] if completion_msg else messages,
        "proc_ctx": ctx,
    }
