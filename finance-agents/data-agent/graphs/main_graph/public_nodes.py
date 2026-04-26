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
from utils.file_intake import (
    build_upload_name_maps as shared_build_upload_name_maps,
    prepare_logical_upload_files,
)

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
    upload_root = Path(UPLOAD_DIR).resolve()
    p = Path(file_path)

    # /uploads/... 是 MCP 返回的上传引用路径，不是本机可直接访问的绝对路径。
    if str(file_path).startswith("/uploads/"):
        rel = file_path.lstrip("/")[len("uploads/"):]
        resolved = (upload_root / rel).resolve()
        resolved.relative_to(upload_root)
        return str(resolved)

    if p.is_absolute():
        resolved = p.resolve()
        resolved.relative_to(upload_root)
        return str(resolved)

    rel = file_path.lstrip("/")
    if not rel.startswith("uploads/"):
        raise ValueError(f"非法上传文件路径: {file_path}")

    rel = rel[len("uploads/"):]
    resolved = (upload_root / rel).resolve()
    resolved.relative_to(upload_root)
    return str(resolved)


def _to_upload_ref(file_path: str) -> str:
    """将上传文件路径标准化为 /uploads/... 引用。"""
    upload_root = Path(UPLOAD_DIR).resolve()
    p = Path(file_path)

    if str(file_path).startswith("/uploads/"):
        return file_path

    if p.is_absolute():
        resolved = p.resolve()
        rel = resolved.relative_to(upload_root)
        return f"/uploads/{rel.as_posix()}"

    rel = file_path.lstrip("/")
    if not rel.startswith("uploads/"):
        raise ValueError(f"非法上传文件路径: {file_path}")
    return f"/{rel}"


def _build_upload_name_maps(raw_files: list[Any]) -> tuple[dict[str, str], dict[str, str]]:
    """构建上传文件名映射。

    Returns:
        display_name_to_ref: 用户原始文件名/存储文件名 -> /uploads/... 引用
        ref_to_display_name: /uploads.../绝对路径/存储文件名 -> 用户原始文件名
    """
    return shared_build_upload_name_maps(raw_files)


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


def _build_file_rule_requirements_text(rule_name: str, file_rule: dict[str, Any] | None) -> str:
    """构建文件校验失败时的规则要求说明。"""
    file_validation_rules = (file_rule or {}).get("file_validation_rules") or {}
    table_schemas = file_validation_rules.get("table_schemas") or []
    if not table_schemas:
        return (
            f"上传的文件不符合「{rule_name}」规则。\n"
            "请重新上传符合要求的文件。"
        )

    lines = [
        f"上传的文件不符合「{rule_name}」规则。",
        "规则要求上传以下文件，并且文件表头需包含对应列名：",
        "",
    ]
    for schema in table_schemas:
        table_name = str(schema.get("table_name") or "未命名表")
        required_columns = schema.get("required_columns") or []
        cols_text = "、".join(str(col) for col in required_columns) if required_columns else "未配置"
        lines.append(f"- {table_name}：{cols_text}")
    return "\n".join(lines)


def _get_table_schema_map(file_rule: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """按 table_name 构建 schema 映射。"""
    file_validation_rules = (file_rule or {}).get("file_validation_rules") or {}
    table_schemas = file_validation_rules.get("table_schemas") or []
    return {
        str(schema.get("table_name") or ""): schema
        for schema in table_schemas
        if schema.get("table_name")
    }


def _format_required_columns(schema: dict[str, Any] | None) -> str:
    required_columns = (schema or {}).get("required_columns") or []
    return "、".join(str(col) for col in required_columns) if required_columns else "未配置"


def _format_file_list(items: list[str]) -> str:
    return "、".join(str(item) for item in items if str(item).strip())


def _format_prefilter_target(item: dict[str, Any]) -> str:
    workbook_name = (
        str(item.get("workbook_display_name") or item.get("workbook_original_filename") or "").strip()
    )
    sheet_name = str(item.get("sheet_name") or "").strip()
    if workbook_name and sheet_name:
        return f"{workbook_name} / {sheet_name}"
    return str(item.get("display_name") or workbook_name or "未命名文件").strip()


def _build_prefilter_summary_text(
    prefilter_summary: list[dict[str, Any]],
    *,
    include_kept: bool = False,
) -> str:
    if not prefilter_summary:
        return ""

    has_multi_sheet = any(item.get("is_logical_split") for item in prefilter_summary)
    dropped_items = [item for item in prefilter_summary if item.get("status") == "dropped"]
    kept_items = [item for item in prefilter_summary if item.get("status") == "kept"]
    if not dropped_items and (not include_kept or not has_multi_sheet):
        return ""

    sections: list[str] = []
    if include_kept and kept_items:
        kept_lines = []
        for item in kept_items:
            target = _format_prefilter_target(item)
            candidates = [str(name) for name in item.get("candidate_table_names") or [] if str(name).strip()]
            if candidates:
                kept_lines.append(f"- {target} -> 进入正式校验（候选：{', '.join(candidates)}）")
            else:
                kept_lines.append(f"- {target} -> 进入正式校验")
        sections.append("纳入正式校验的文件 / sheet：\n" + "\n".join(kept_lines))

    if dropped_items:
        dropped_lines = []
        for item in dropped_items:
            target = _format_prefilter_target(item)
            reason = str(item.get("reason") or item.get("reason_code") or "已过滤").strip()
            dropped_lines.append(f"- {target} -> 已过滤（{reason}）")
        sections.append("预筛选已过滤的文件 / sheet：\n" + "\n".join(dropped_lines))

    if not sections:
        return ""
    return "\n\n".join(sections)


def _build_candidate_mapping_text(candidate_mappings: dict[str, Any]) -> str:
    if not isinstance(candidate_mappings, dict) or not candidate_mappings:
        return ""

    lines: list[str] = []
    for file_name, candidates in sorted(candidate_mappings.items()):
        if not isinstance(candidates, list):
            continue
        table_names = [
            str(item.get("table_name") or "").strip()
            for item in candidates
            if isinstance(item, dict) and str(item.get("table_name") or "").strip()
        ]
        if table_names:
            lines.append(f"- {file_name} -> {', '.join(table_names)}")
    if not lines:
        return ""
    return "存在映射歧义的文件 / sheet：\n" + "\n".join(lines)


async def _load_rule_from_pg(rule_code: str, auth_token: str) -> dict[str, Any] | None:
    """从 PG（通过 MCP 工具）加载规则。
    
    从 rule_detail 表获取规则记录，包含：
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
        # 获取规则（get_rule 返回完整规则记录）
        rule_result = await get_file_validation_rule(rule_code=rule_code, auth_token=auth_token)
        logger.info(f"[public_nodes] rule_code={rule_code}; 获取规则结果: success={rule_result.get('success')}")
        
        if not rule_result.get("success", False):
            logger.warning(f"[public_nodes] 未找到规则 rule_code={rule_code}")
            return None
        
        # 解析规则内容
        rule_data = rule_result.get("data") or {}
        # data 包含: id, user_id, rule_code, rule, rule_type, remark
        rule_content = rule_data.get("rule") or {}
        
        combined_rule = {
            "rule_code": rule_code,
            # 文件校验规则
            "file_validation_rules": rule_content.get("file_validation_rules", {}),
            "file_rule_memo": rule_data.get("remark", ""),
            # 整理规则
            "role_desc": rule_content.get("role_desc", ""),
            "rules": rule_content.get("rules", []),
            "proc_rule_memo": rule_data.get("remark", ""),
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

    if not rule_code:
        msg = "未指定规则编码，请告知您要使用的规则。"
        ctx.update({"phase": ProcAgentPhase.RULE_NOT_FOUND.value, "error": msg})
        return {
            "messages": [AIMessage(content=msg)],
            "proc_ctx": ctx,
        }

    rule = await _load_rule_from_pg(rule_code=rule_code, auth_token=auth_token)

    if rule is None:
        msg = f"未找到规则编码为「{rule_code}」的规则。\n请确认规则编码是否正确，或联系管理员获取可用的规则列表。"
        ctx.update({"phase": ProcAgentPhase.RULE_NOT_FOUND.value, "error": msg})
        return {
            "messages": [AIMessage(content=msg)],
            "proc_ctx": ctx,
        }

    ctx.update({
        "phase": ProcAgentPhase.CHECKING_FILES.value,
        "rule": rule,
        "rule_code": rule_code,
    })

    rule_name = (
        ctx.get("rule_name")
        or state.get("selected_rule_name")
        or rule.get("name")
        or rule_code
    )
    completion_msg = f"已读取规则「{rule_name}」，开始准备文件校验。"
    return {
        "messages": [AIMessage(content=completion_msg)],
        "proc_ctx": ctx,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 公共节点：check_file_node — 文件类型/数量/表头校验
# ══════════════════════════════════════════════════════════════════════════════

async def check_file_node(state: AgentState) -> dict:
    """校验已上传文件是否满足规则要求。

    通过调用 MCP 工具 validate_files 执行校验：
    - 读取每个文件的列名
    - 调用 validate_files tool 进行全量列名精确匹配
    - 通过：phase → EXECUTING
    - 不通过：回复错误原因，phase → FILE_CHECK_FAILED
    
    这是一个公共节点，可被多个子图共享使用。
    """
    ctx = _get_proc_ctx(state)
    # 文件校验规则编码（优先从 file_rule_code 获取，用于文件校验）
    # ⚠️ file_rule_code 和 rule_code 是不同的概念，不能互相 fallback
    file_rule_code: str = ctx.get("file_rule_code") or state.get("file_rule_code") or ""
    rule_display_name: str = (
        ctx.get("rule_name")
        or state.get("selected_rule_name")
        or ctx.get("rule_code")
        or state.get("selected_rule_code")
        or "当前规则"
    )

    raw_files: list = list(state.get("uploaded_files") or [])
    auth_token: str = state.get("auth_token") or ""

    # uploaded_files 可能是 str 路径或 dict（{file_path, original_filename}）
    uploaded_file_entries: list[dict[str, str]] = []
    for item in raw_files:
        if isinstance(item, dict):
            fp = item.get("file_path") or item.get("path") or ""
            display_name = (item.get("original_filename") or item.get("name") or "").strip()
        else:
            fp = str(item)
            display_name = ""
        if fp:
            try:
                abs_path = _to_abs_path(fp)
                uploaded_file_entries.append({
                    "abs_path": abs_path,
                    "display_name": display_name or os.path.basename(abs_path),
                })
            except ValueError as e:
                reason = f"上传文件路径非法：{e}"
                msg = f"文件校验失败：\n\n{reason}"
                ctx.update({"phase": ProcAgentPhase.FILE_CHECK_FAILED.value, "error": reason})
                return {
                    "messages": [AIMessage(content=msg)],
                    "proc_ctx": ctx,
                }

    uploaded_files = [entry["abs_path"] for entry in uploaded_file_entries]

    logger.info(
        f"[public_nodes] check_file_node file_rule_code={file_rule_code!r} "
        f"files={[entry['display_name'] for entry in uploaded_file_entries]}"
    )

    file_rule = await _load_rule_from_pg(rule_code=file_rule_code, auth_token=auth_token) if file_rule_code else None

    # ── 0. 检查 file_rule_code 是否配置 ──────────────────────────────────────
    if not file_rule_code:
        reason = "未配置文件校验规则编码（file_rule_code），请联系管理员配置规则的文件校验规则。"
        msg = f"文件校验失败：\n\n{reason}"
        ctx.update({"phase": ProcAgentPhase.FILE_CHECK_FAILED.value, "error": reason})
        return {
            "messages": [AIMessage(content=msg)],
            "proc_ctx": ctx,
        }

    # ── 1. 基础判断：文件列表不能为空 ───────────────────────────────────────
    if not uploaded_files:
        reason = "未检测到已上传的文件，请先上传所需文件后再试。"
        msg = f"文件校验失败：\n\n{reason}"
        ctx.update({"phase": ProcAgentPhase.FILE_CHECK_FAILED.value, "error": reason})
        return {
            "messages": [AIMessage(content=msg)],
            "proc_ctx": ctx,
        }

    # ── 2. 文件类型校验 ──────────────────────────────────────────────────
    for entry in uploaded_file_entries:
        fp = entry["abs_path"]
        display_name = entry["display_name"]
        ext = os.path.splitext(fp)[-1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            reason = (
                f"文件「{display_name}」格式不支持（{ext}），"
                f"请上传 {', '.join(sorted(SUPPORTED_EXTENSIONS))} 格式的文件。"
            )
            msg = f"文件校验失败：\n\n{reason}"
            ctx.update({"phase": ProcAgentPhase.FILE_CHECK_FAILED.value, "error": reason})
            return {
                "messages": [AIMessage(content=msg)],
                "proc_ctx": ctx,
            }

    # ── 3. 预处理上传文件：多 sheet 拆分 + sheet 级预筛选 ─────────────────
    try:
        intake_result = prepare_logical_upload_files(raw_files, file_rule=file_rule)
    except Exception as e:
        reason = f"拆分或预处理上传文件失败：{e}"
        msg = f"文件校验失败：\n\n{reason}"
        ctx.update({"phase": ProcAgentPhase.FILE_CHECK_FAILED.value, "error": reason})
        return {
            "messages": [AIMessage(content=msg)],
            "proc_ctx": ctx,
        }

    logical_uploaded_files: list[dict[str, Any]] = list(intake_result.get("logical_uploaded_files") or [])
    files_with_columns: list[dict[str, Any]] = list(intake_result.get("files_with_columns") or [])
    prefilter_summary: list[dict[str, Any]] = list(intake_result.get("prefilter_summary") or [])

    logger.info(
        "[public_nodes] 预处理上传文件完成: kept=%s dropped=%s logical_files=%s",
        intake_result.get("kept_count", 0),
        intake_result.get("dropped_count", 0),
        [item.get("display_name") for item in logical_uploaded_files],
    )

    prefilter_summary_text = _build_prefilter_summary_text(prefilter_summary, include_kept=True)

    if not files_with_columns:
        reason = "上传文件拆分后没有可参与正式校验的文件 / sheet，请检查表头、数据行或规则要求。"
        sections = [
            "文件校验失败：",
            "",
            reason,
        ]
        if prefilter_summary_text:
            sections.extend(["", prefilter_summary_text])
        requirement_text = _build_file_rule_requirements_text(rule_display_name, file_rule)
        sections.extend(["", requirement_text])
        msg = "\n".join(sections)
        ctx.update({
            "phase": ProcAgentPhase.FILE_CHECK_FAILED.value,
            "error": reason,
            "logical_uploaded_files": logical_uploaded_files,
            "sheet_prefilter_summary": prefilter_summary,
        })
        return {
            "messages": [AIMessage(content=msg)],
            "proc_ctx": ctx,
        }

    # ── 4. 调用 MCP tool validate_files 执行全量列名精确匹配 ──────────────────
    from tools.mcp_client import validate_files as mcp_validate_files

    try:
        validate_result = await mcp_validate_files(
            uploaded_files=files_with_columns,
            rule_code=file_rule_code,
            auth_token=auth_token,
        )
    except Exception as e:
        reason = f"调用文件校验服务失败：{e}"
        logger.error(f"[public_nodes] check_file_node 校验工具调用异常: {e}")
        msg = f"文件校验失败：\n\n{reason}"
        ctx.update({"phase": ProcAgentPhase.FILE_CHECK_FAILED.value, "error": reason})
        return {
            "messages": [AIMessage(content=msg)],
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
        matched_results = validate_result.get("matched_results", [])
        missing_tables = validate_result.get("missing_tables", [])
        unmatched_files = validate_result.get("unmatched_files", [])
        candidate_mappings = validate_result.get("candidate_mappings", {})
        uploaded_count = len(files_with_columns)

        matched_lines: list[str] = []
        if matched_results:
            for item in matched_results:
                file_name = item.get("file_name", "")
                table_name = item.get("table_name", "")
                if file_name and table_name:
                    matched_lines.append(f"- {file_name} -> {table_name}")

        unmatched_lines = [f"- {file_name}" for file_name in unmatched_files]
        upload_summary = f"本次参与正式校验的文件 / sheet 共 {uploaded_count} 个。"
        candidate_mapping_text = _build_candidate_mapping_text(candidate_mappings)

        if candidate_mapping_text:
            sections = [
                "文件校验失败：",
                "",
                upload_summary,
                "",
                candidate_mapping_text,
            ]
            if prefilter_summary_text:
                sections.extend(["", prefilter_summary_text])
            sections.extend([
                "",
                "这些文件 / sheet 的表头可以匹配多个 schema，当前无法唯一确定对应关系。",
                "请收紧规则 required_columns，或去掉结构过于相似的冗余 sheet 后重试。",
            ])
            msg = "\n".join(sections)
        elif unmatched_files or missing_tables:
            requirement_text = _build_file_rule_requirements_text(rule_display_name, file_rule)
            detail_lines = []
            if missing_tables:
                missing_names = "、".join(t["table_name"] for t in missing_tables)
                detail_lines.append(f"- 缺少规则要求的文件：{missing_names}")
            if unmatched_files:
                detail_lines.append("- 存在未能识别的文件，请检查文件格式和表头是否符合规则要求。")
            sections = [
                "文件校验失败：",
                "",
                upload_summary,
                "",
                requirement_text,
            ]
            if matched_lines:
                sections.extend(["", "已识别的文件：", "\n".join(matched_lines)])
            if unmatched_lines:
                sections.extend(["", "未识别的文件：", "\n".join(unmatched_lines)])
            if prefilter_summary_text:
                sections.extend(["", prefilter_summary_text])
            sections.extend([
                "",
                "发现以下问题：",
                "\n".join(detail_lines),
                "",
                "请检查文件格式后重新上传文件。",
            ])
            msg = (
                "\n".join(sections)
            )
        else:
            sections = ["文件校验失败：", "", error_msg]
            if prefilter_summary_text:
                sections.extend(["", prefilter_summary_text])
            msg = "\n".join(sections)
        ctx.update({
            "phase": ProcAgentPhase.FILE_CHECK_FAILED.value,
            "error": error_msg,
            "logical_uploaded_files": logical_uploaded_files,
            "sheet_prefilter_summary": prefilter_summary,
        })
        return {
            "messages": [AIMessage(content=msg)],
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
    dropped_prefilter_text = _build_prefilter_summary_text(prefilter_summary, include_kept=False)
    if dropped_prefilter_text:
        summary_parts.append("🧹 **预筛选已过滤：**\n" + dropped_prefilter_text.replace("\n\n", "\n"))

    file_match_summary = (
        "\n\n**文件识别结果：**\n" + "\n\n".join(summary_parts)
        if summary_parts else ""
    )

    completion_msg = f"文件校验通过。{file_match_summary}"

    ctx.update({
        "phase": ProcAgentPhase.EXECUTING.value,
        "file_match_results": matched_results,   # [{file_name, table_id, table_name}]
        "logical_uploaded_files": logical_uploaded_files,
        "sheet_prefilter_summary": prefilter_summary,
    })
    return {
        "messages": [AIMessage(content=completion_msg)] if completion_msg else [],
        "proc_ctx": ctx,
    }
