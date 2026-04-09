"""execution_* MCP 工具。

提供以下能力：
1. execution_schemes CRUD
2. execution_run_plans CRUD
3. execution_runs CRUD（更新仅支持状态与结果字段）
4. execution_run_exceptions CRUD
5. proc/recon 草稿试跑
"""

from __future__ import annotations

import re
import shutil
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from mcp import Tool

from auth import db as auth_db
from auth.jwt_utils import get_user_from_token
from security_utils import UPLOAD_ROOT, resolve_upload_file_path
from tools.rule_schema import validate_rule_record


_ALLOWED_SCHEME_TYPES = {"recon"}
_ALLOWED_SCHEDULE_TYPES = {"manual_trigger", "daily", "weekly", "monthly", "cron"}
_ALLOWED_TRIGGER_TYPES = {"chat", "schedule", "api"}
_ALLOWED_ENTRY_MODES = {"file", "dataset"}
_ALLOWED_EXECUTION_STATUS = {"running", "success", "failed"}


def create_tools() -> list[Tool]:
    return [
        Tool(
            name="execution_scheme_list",
            description="查询执行方案列表。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "include_disabled": {"type": "boolean"},
                    "limit": {"type": "integer"},
                    "offset": {"type": "integer"},
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="execution_scheme_get",
            description="查询单个执行方案（按 scheme_id 或 scheme_code）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "scheme_id": {"type": "string"},
                    "scheme_code": {"type": "string"},
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="execution_scheme_create",
            description="创建执行方案。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "scheme_name": {"type": "string"},
                    "scheme_code": {"type": "string"},
                    "scheme_type": {"type": "string"},
                    "description": {"type": "string"},
                    "file_rule_code": {"type": "string"},
                    "proc_rule_code": {"type": "string"},
                    "recon_rule_code": {"type": "string"},
                    "scheme_meta_json": {"type": "object"},
                    "is_enabled": {"type": "boolean"},
                },
                "required": ["auth_token", "scheme_name"],
            },
        ),
        Tool(
            name="execution_scheme_update",
            description="更新执行方案。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "scheme_id": {"type": "string"},
                    "scheme_name": {"type": "string"},
                    "scheme_type": {"type": "string"},
                    "description": {"type": "string"},
                    "file_rule_code": {"type": "string"},
                    "proc_rule_code": {"type": "string"},
                    "recon_rule_code": {"type": "string"},
                    "scheme_meta_json": {"type": "object"},
                    "is_enabled": {"type": "boolean"},
                },
                "required": ["auth_token", "scheme_id"],
            },
        ),
        Tool(
            name="execution_scheme_delete",
            description="停用执行方案。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "scheme_id": {"type": "string"},
                },
                "required": ["auth_token", "scheme_id"],
            },
        ),
        Tool(
            name="execution_run_plan_list",
            description="查询执行运行计划列表。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "scheme_code": {"type": "string"},
                    "scheme_id": {"type": "string"},
                    "include_disabled": {"type": "boolean"},
                    "limit": {"type": "integer"},
                    "offset": {"type": "integer"},
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="execution_run_plan_get",
            description="查询单个执行运行计划（按 plan_id 或 plan_code）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "plan_id": {"type": "string"},
                    "run_plan_id": {"type": "string"},
                    "plan_code": {"type": "string"},
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="execution_run_plan_create",
            description="创建执行运行计划。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "plan_name": {"type": "string"},
                    "plan_code": {"type": "string"},
                    "scheme_code": {"type": "string"},
                    "schedule_type": {"type": "string"},
                    "schedule_expr": {"type": "string"},
                    "biz_date_offset": {"type": "string"},
                    "input_bindings_json": {"type": "array"},
                    "channel_config_id": {"type": "string"},
                    "owner_mapping_json": {"type": "object"},
                    "plan_meta_json": {"type": "object"},
                    "is_enabled": {"type": "boolean"},
                },
                "required": ["auth_token", "plan_name", "scheme_code"],
            },
        ),
        Tool(
            name="execution_run_plan_update",
            description="更新执行运行计划。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "plan_id": {"type": "string"},
                    "run_plan_id": {"type": "string"},
                    "plan_name": {"type": "string"},
                    "scheme_code": {"type": "string"},
                    "schedule_type": {"type": "string"},
                    "schedule_expr": {"type": "string"},
                    "biz_date_offset": {"type": "string"},
                    "input_bindings_json": {"type": "array"},
                    "channel_config_id": {"type": "string"},
                    "owner_mapping_json": {"type": "object"},
                    "plan_meta_json": {"type": "object"},
                    "is_enabled": {"type": "boolean"},
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="execution_run_plan_delete",
            description="停用执行运行计划。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "plan_id": {"type": "string"},
                    "run_plan_id": {"type": "string"},
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="execution_run_list",
            description="查询执行记录列表。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "scheme_code": {"type": "string"},
                    "scheme_id": {"type": "string"},
                    "plan_code": {"type": "string"},
                    "run_plan_id": {"type": "string"},
                    "limit": {"type": "integer"},
                    "offset": {"type": "integer"},
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="execution_run_get",
            description="查询单个执行记录（按 run_id 或 run_code）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "run_id": {"type": "string"},
                    "run_code": {"type": "string"},
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="execution_run_create",
            description="创建执行记录。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "run_code": {"type": "string"},
                    "scheme_code": {"type": "string"},
                    "plan_code": {"type": "string"},
                    "scheme_type": {"type": "string"},
                    "trigger_type": {"type": "string"},
                    "entry_mode": {"type": "string"},
                    "execution_status": {"type": "string"},
                    "failed_stage": {"type": "string"},
                    "failed_reason": {"type": "string"},
                    "run_context_json": {"type": "object"},
                    "source_snapshot_json": {"type": "object"},
                    "subtasks_json": {"type": "array"},
                    "proc_result_json": {"type": "object"},
                    "recon_result_summary_json": {"type": "object"},
                    "artifacts_json": {"type": "object"},
                    "anomaly_count": {"type": "integer"},
                    "started_at_now": {"type": "boolean"},
                    "finished_at_now": {"type": "boolean"},
                },
                "required": ["auth_token", "scheme_code"],
            },
        ),
        Tool(
            name="execution_run_update",
            description="更新执行记录。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "run_id": {"type": "string"},
                    "execution_status": {"type": "string"},
                    "failed_stage": {"type": "string"},
                    "failed_reason": {"type": "string"},
                    "run_context_json": {"type": "object"},
                    "source_snapshot_json": {"type": "object"},
                    "subtasks_json": {"type": "array"},
                    "proc_result_json": {"type": "object"},
                    "recon_result_summary_json": {"type": "object"},
                    "artifacts_json": {"type": "object"},
                    "anomaly_count": {"type": "integer"},
                    "started_at_now": {"type": "boolean"},
                    "finished_at_now": {"type": "boolean"},
                },
                "required": ["auth_token", "run_id"],
            },
        ),
        Tool(
            name="execution_run_exceptions",
            description="按 run_id 查询执行异常列表。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "run_id": {"type": "string"},
                    "run_code": {"type": "string"},
                    "limit": {"type": "integer"},
                    "offset": {"type": "integer"},
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="execution_run_exception_get",
            description="查询单个执行异常。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "exception_id": {"type": "string"},
                },
                "required": ["auth_token", "exception_id"],
            },
        ),
        Tool(
            name="execution_run_exception_create",
            description="创建或幂等更新执行异常。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "run_id": {"type": "string"},
                    "scheme_code": {"type": "string"},
                    "anomaly_key": {"type": "string"},
                    "anomaly_type": {"type": "string"},
                    "summary": {"type": "string"},
                    "detail_json": {"type": "object"},
                    "owner_name": {"type": "string"},
                    "owner_identifier": {"type": "string"},
                    "owner_contact_json": {"type": "object"},
                    "reminder_status": {"type": "string"},
                    "processing_status": {"type": "string"},
                    "fix_status": {"type": "string"},
                    "latest_feedback": {"type": "string"},
                    "feedback_json": {"type": "object"},
                    "is_closed": {"type": "boolean"},
                },
                "required": ["auth_token", "run_id", "anomaly_key", "anomaly_type", "summary"],
            },
        ),
        Tool(
            name="execution_run_exception_update",
            description="更新执行异常。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "exception_id": {"type": "string"},
                    "owner_name": {"type": "string"},
                    "owner_identifier": {"type": "string"},
                    "owner_contact_json": {"type": "object"},
                    "reminder_status": {"type": "string"},
                    "processing_status": {"type": "string"},
                    "fix_status": {"type": "string"},
                    "latest_feedback": {"type": "string"},
                    "feedback_json": {"type": "object"},
                    "is_closed": {"type": "boolean"},
                },
                "required": ["auth_token", "exception_id"],
            },
        ),
        Tool(
            name="execution_proc_draft_trial",
            description="proc 草稿试跑（规则结构校验 + steps 运行验证，不落库）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "proc_rule_json": {"type": "object"},
                    "uploaded_files": {"type": "array"},
                    "sample_datasets": {"type": "array"},
                },
                "required": ["auth_token", "proc_rule_json"],
            },
        ),
        Tool(
            name="execution_recon_draft_trial",
            description="recon 草稿试跑（最小可用：规则结构校验，不落库）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "recon_rule_json": {"type": "object"},
                    "validated_inputs": {"type": "array"},
                },
                "required": ["auth_token", "recon_rule_json"],
            },
        ),
    ]


async def handle_tool_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        if name == "execution_scheme_list":
            return _scheme_list(arguments)
        if name == "execution_scheme_get":
            return _scheme_get(arguments)
        if name == "execution_scheme_create":
            return _scheme_create(arguments)
        if name == "execution_scheme_update":
            return _scheme_update(arguments)
        if name == "execution_scheme_delete":
            return _scheme_delete(arguments)
        if name == "execution_run_plan_list":
            return _plan_list(arguments)
        if name == "execution_run_plan_get":
            return _plan_get(arguments)
        if name == "execution_run_plan_create":
            return _plan_create(arguments)
        if name == "execution_run_plan_update":
            return _plan_update(arguments)
        if name == "execution_run_plan_delete":
            return _plan_delete(arguments)
        if name == "execution_run_list":
            return _run_list(arguments)
        if name == "execution_run_get":
            return _run_get(arguments)
        if name == "execution_run_create":
            return _run_create(arguments)
        if name == "execution_run_update":
            return _run_update(arguments)
        if name == "execution_run_exceptions":
            return _run_exceptions(arguments)
        if name == "execution_run_exception_get":
            return _exception_get(arguments)
        if name == "execution_run_exception_create":
            return _exception_create(arguments)
        if name == "execution_run_exception_update":
            return _exception_update(arguments)
        if name == "execution_proc_draft_trial":
            return _proc_draft_trial(arguments)
        if name == "execution_recon_draft_trial":
            return _recon_draft_trial(arguments)
        return {"success": False, "error": f"未知工具: {name}"}
    except ValueError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"execution 工具调用失败: {exc}"}


def _require_user(auth_token: str) -> dict[str, Any]:
    token = str(auth_token or "").strip()
    if not token:
        raise ValueError("未提供认证 token，请先登录")
    user = get_user_from_token(token)
    if not user:
        raise ValueError("token 无效或已过期，请重新登录")
    if not user.get("company_id"):
        raise ValueError("当前用户未绑定公司")
    return user


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = _as_text(value).lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _as_int(value: Any, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def _normalize_optional_uuid(value: Any) -> str | None:
    text = _as_text(value)
    return text or None


def _is_nullish_scalar(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except Exception:
        return False


def _preview_value(value: Any) -> str | int | float | None:
    if hasattr(value, "item") and not isinstance(value, (str, bytes, bytearray)):
        try:
            value = value.item()
        except Exception:
            pass
    if _is_nullish_scalar(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime().isoformat(sep=" ")
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return float(round(value, 6))
    return str(value)


def _rows_to_preview_rows(rows: list[dict[str, Any]], *, limit: int = 3) -> list[dict[str, Any]]:
    preview_rows: list[dict[str, Any]] = []
    for raw_row in rows[:limit]:
        row = _safe_dict(raw_row)
        preview_rows.append({str(key): _preview_value(value) for key, value in row.items()})
    return preview_rows


def _dataframe_to_preview_rows(df: pd.DataFrame, *, limit: int = 3) -> list[dict[str, Any]]:
    records = df.head(limit).to_dict(orient="records")
    return _rows_to_preview_rows([_safe_dict(item) for item in records])


def _safe_trial_filename(name: str, index: int) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "_", _as_text(name)) or f"sample_{index}"
    return f"{index:02d}_{normalized}.xlsx"


def _write_trial_dataset_file(base_dir: Path, table_name: str, rows: list[dict[str, Any]], index: int) -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    output_path = base_dir / _safe_trial_filename(table_name, index)
    pd.DataFrame(rows).to_excel(output_path, index=False)
    return output_path


def _read_preview_dataframe(file_path: str) -> pd.DataFrame:
    path = resolve_upload_file_path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        try:
            return pd.read_csv(path, encoding="utf-8-sig")
        except UnicodeDecodeError:
            import chardet

            with open(path, "rb") as file:
                encoding = chardet.detect(file.read()).get("encoding", "gbk")
            return pd.read_csv(path, encoding=encoding)
    if suffix in {".xlsx", ".xls", ".xlsm", ".xlsb"}:
        return pd.read_excel(path)
    raise ValueError(f"不支持的试跑输入文件格式: {suffix}")


def _read_output_dataframe(file_path: str) -> pd.DataFrame:
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path, encoding="utf-8-sig")
    if suffix in {".xlsx", ".xls", ".xlsm", ".xlsb"}:
        return pd.read_excel(path)
    raise ValueError(f"不支持的试跑输出文件格式: {suffix}")


def _infer_preview_side(value: Any) -> str:
    text = _as_text(value).lower()
    if text.startswith("right"):
        return "right"
    if text.startswith("left"):
        return "left"
    return "left"


def _format_trial_errors(errors: list[Any]) -> list[dict[str, Any]]:
    formatted: list[dict[str, Any]] = []
    for item in errors:
        if isinstance(item, dict):
            formatted.append(item)
        elif item is not None:
            formatted.append({"message": _as_text(item)})
    return formatted


def _build_proc_trial_inputs(
    *,
    uploaded_files: list[dict[str, Any]],
    sample_datasets: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], str | None]:
    validated_files: list[dict[str, Any]] = []
    source_samples: list[dict[str, Any]] = []
    warnings: list[str] = []
    temp_input_dir: str | None = None

    for item in uploaded_files:
        file_path = _as_text(item.get("file_path"))
        table_name = _as_text(item.get("table_name"))
        if not file_path or not table_name:
            continue
        file_name = _as_text(item.get("file_name")) or Path(file_path).name
        validated_files.append(
            {
                "file_name": file_name,
                "file_path": file_path,
                "table_name": table_name,
            }
        )
        preview_rows: list[dict[str, Any]] = []
        try:
            preview_rows = _dataframe_to_preview_rows(_read_preview_dataframe(file_path))
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"读取上传文件 {file_name} 抽样失败：{exc}")
        source_samples.append(
            {
                "side": _infer_preview_side(item.get("side") or table_name),
                "table_name": table_name,
                "display_name": _as_text(item.get("display_name") or file_name or table_name),
                "source_id": _as_text(item.get("source_id") or file_name or table_name),
                "rows": preview_rows,
            }
        )

    dataset_rows = [item for item in sample_datasets if isinstance(item, dict)]
    if dataset_rows:
        temp_input_dir = tempfile.mkdtemp(prefix="proc_trial_", dir=str(UPLOAD_ROOT))
        input_dir = Path(temp_input_dir)
        for index, item in enumerate(dataset_rows, start=1):
            table_name = _as_text(
                item.get("table_name")
                or item.get("resource_key")
                or item.get("dataset_code")
                or item.get("dataset_name")
                or item.get("source_id")
            )
            if not table_name:
                warnings.append(f"第 {index} 个样本数据集缺少 table_name，已跳过。")
                continue
            sample_rows = [
                _safe_dict(row)
                for row in _safe_list(item.get("sample_rows"))
                if isinstance(row, dict)
            ]
            if not sample_rows:
                warnings.append(f"{table_name} 未提供 sample_rows，已跳过。")
                continue
            sample_file_path = _write_trial_dataset_file(input_dir, table_name, sample_rows, index)
            validated_files.append(
                {
                    "file_name": sample_file_path.name,
                    "file_path": str(sample_file_path),
                    "table_name": table_name,
                }
            )
            source_samples.append(
                {
                    "side": _infer_preview_side(item.get("side") or table_name),
                    "table_name": table_name,
                    "display_name": _as_text(item.get("display_name") or item.get("dataset_name") or table_name),
                    "source_id": _as_text(item.get("source_id") or item.get("source_key") or table_name),
                    "rows": _rows_to_preview_rows(sample_rows),
                }
            )

    return validated_files, source_samples, warnings, temp_input_dir


def _pick_plan_id(arguments: dict[str, Any]) -> str:
    return _as_text(arguments.get("plan_id") or arguments.get("run_plan_id"))


def _resolve_scheme_code(company_id: str, arguments: dict[str, Any]) -> tuple[str | None, str | None]:
    scheme_code = _as_text(arguments.get("scheme_code"))
    if scheme_code:
        return scheme_code, None
    scheme_id = _as_text(arguments.get("scheme_id"))
    if not scheme_id:
        return None, None
    scheme = auth_db.get_execution_scheme(company_id=company_id, scheme_id=scheme_id)
    if not scheme:
        return None, "scheme_id 对应方案不存在"
    return _as_text(scheme.get("scheme_code")), None


def _resolve_plan_code(company_id: str, arguments: dict[str, Any]) -> tuple[str | None, str | None]:
    plan_code = _as_text(arguments.get("plan_code"))
    if plan_code:
        return plan_code, None
    plan_id = _pick_plan_id(arguments)
    if not plan_id:
        return None, None
    plan = auth_db.get_execution_run_plan(company_id=company_id, plan_id=plan_id)
    if not plan:
        return None, "run_plan_id 对应运行计划不存在"
    return _as_text(plan.get("plan_code")), None


def _ensure_allowed(value: str, allowed: set[str], field_name: str) -> str:
    normalized = _as_text(value).lower()
    if normalized not in allowed:
        raise ValueError(f"{field_name} 取值非法，可选：{', '.join(sorted(allowed))}")
    return normalized


def _scheme_list(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    items = auth_db.list_execution_schemes(
        company_id=str(user.get("company_id") or ""),
        include_disabled=_as_bool(arguments.get("include_disabled"), True),
        limit=_as_int(arguments.get("limit"), 100, minimum=1, maximum=500),
        offset=_as_int(arguments.get("offset"), 0, minimum=0),
    )
    return {"success": True, "count": len(items), "schemes": items}


def _scheme_get(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    scheme_id = str(arguments.get("scheme_id") or "").strip() or None
    scheme_code = str(arguments.get("scheme_code") or "").strip() or None
    if not scheme_id and not scheme_code:
        return {"success": False, "error": "scheme_id 或 scheme_code 至少提供一个"}
    item = auth_db.get_execution_scheme(
        company_id=str(user.get("company_id") or ""),
        scheme_id=scheme_id,
        scheme_code=scheme_code,
    )
    if not item:
        return {"success": False, "error": "方案不存在"}
    return {"success": True, "scheme": item}


def _scheme_create(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user.get("company_id") or "")
    scheme_name = _as_text(arguments.get("scheme_name"))
    recon_rule_code = _as_text(arguments.get("recon_rule_code"))
    scheme_meta_json = _safe_dict(arguments.get("scheme_meta_json"))
    embedded_recon_rule = _safe_dict(scheme_meta_json.get("recon_rule_json"))
    if not scheme_name:
        return {"success": False, "error": "scheme_name 不能为空"}
    if not recon_rule_code and not embedded_recon_rule:
        return {"success": False, "error": "recon_rule_code 不能为空，或在 scheme_meta_json 中提供 recon_rule_json"}
    scheme_type = _ensure_allowed(
        _as_text(arguments.get("scheme_type") or "recon"),
        _ALLOWED_SCHEME_TYPES,
        "scheme_type",
    )
    item = auth_db.create_execution_scheme(
        company_id=company_id,
        scheme_name=scheme_name,
        scheme_code=_as_text(arguments.get("scheme_code")),
        scheme_type=scheme_type,
        description=str(arguments.get("description") or ""),
        file_rule_code=str(arguments.get("file_rule_code") or ""),
        proc_rule_code=str(arguments.get("proc_rule_code") or ""),
        recon_rule_code=recon_rule_code,
        scheme_meta_json=scheme_meta_json,
        is_enabled=_as_bool(arguments.get("is_enabled"), True),
        created_by=str(user.get("user_id") or user.get("id") or "") or None,
    )
    if not item:
        return {"success": False, "error": "创建方案失败"}
    return {"success": True, "scheme": item}


def _scheme_update(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    scheme_id = str(arguments.get("scheme_id") or "").strip()
    if not scheme_id:
        return {"success": False, "error": "scheme_id 不能为空"}
    scheme_type = arguments.get("scheme_type")
    if scheme_type is not None:
        scheme_type = _ensure_allowed(
            _as_text(scheme_type),
            _ALLOWED_SCHEME_TYPES,
            "scheme_type",
        )
    is_enabled = arguments.get("is_enabled")
    item = auth_db.update_execution_scheme(
        company_id=str(user.get("company_id") or ""),
        scheme_id=scheme_id,
        scheme_name=arguments.get("scheme_name"),
        scheme_type=scheme_type,
        description=arguments.get("description"),
        file_rule_code=arguments.get("file_rule_code"),
        proc_rule_code=arguments.get("proc_rule_code"),
        recon_rule_code=arguments.get("recon_rule_code"),
        scheme_meta_json=arguments.get("scheme_meta_json"),
        is_enabled=_as_bool(is_enabled, True) if is_enabled is not None else None,
    )
    if not item:
        return {"success": False, "error": "方案不存在或更新失败"}
    return {"success": True, "scheme": item}


def _scheme_delete(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    scheme_id = str(arguments.get("scheme_id") or "").strip()
    if not scheme_id:
        return {"success": False, "error": "scheme_id 不能为空"}
    item = auth_db.disable_execution_scheme(
        company_id=str(user.get("company_id") or ""),
        scheme_id=scheme_id,
    )
    if not item:
        return {"success": False, "error": "方案不存在或停用失败"}
    return {"success": True, "scheme": item, "message": "方案已停用"}


def _plan_list(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user.get("company_id") or "")
    scheme_code, error = _resolve_scheme_code(company_id, arguments)
    if error:
        return {"success": False, "error": error}
    items = auth_db.list_execution_run_plans(
        company_id=company_id,
        scheme_code=scheme_code,
        include_disabled=_as_bool(arguments.get("include_disabled"), True),
        limit=_as_int(arguments.get("limit"), 100, minimum=1, maximum=500),
        offset=_as_int(arguments.get("offset"), 0, minimum=0),
    )
    return {"success": True, "count": len(items), "run_plans": items}


def _plan_get(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    plan_id = _pick_plan_id(arguments) or None
    plan_code = _as_text(arguments.get("plan_code")) or None
    if not plan_id and not plan_code:
        return {"success": False, "error": "plan_id 或 plan_code 至少提供一个"}
    item = auth_db.get_execution_run_plan(
        company_id=str(user.get("company_id") or ""),
        plan_id=plan_id,
        plan_code=plan_code,
    )
    if not item:
        return {"success": False, "error": "运行计划不存在"}
    return {"success": True, "run_plan": item}


def _plan_create(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user.get("company_id") or "")
    plan_name = _as_text(arguments.get("plan_name"))
    scheme_code = _as_text(arguments.get("scheme_code"))
    if not plan_name:
        return {"success": False, "error": "plan_name 不能为空"}
    if not scheme_code:
        return {"success": False, "error": "scheme_code 不能为空"}
    scheme = auth_db.get_execution_scheme(company_id=company_id, scheme_code=scheme_code)
    if not scheme:
        return {"success": False, "error": "scheme_code 对应方案不存在"}
    schedule_type = _ensure_allowed(
        _as_text(arguments.get("schedule_type") or "daily"),
        _ALLOWED_SCHEDULE_TYPES,
        "schedule_type",
    )
    item = auth_db.create_execution_run_plan(
        company_id=company_id,
        plan_name=plan_name,
        scheme_code=scheme_code,
        plan_code=_as_text(arguments.get("plan_code")),
        schedule_type=schedule_type,
        schedule_expr=str(arguments.get("schedule_expr") or ""),
        biz_date_offset=str(arguments.get("biz_date_offset") or "previous_day"),
        input_bindings_json=[v for v in _safe_list(arguments.get("input_bindings_json")) if isinstance(v, dict)],
        channel_config_id=_normalize_optional_uuid(arguments.get("channel_config_id")),
        owner_mapping_json=_safe_dict(arguments.get("owner_mapping_json")),
        plan_meta_json=_safe_dict(arguments.get("plan_meta_json")),
        is_enabled=_as_bool(arguments.get("is_enabled"), True),
        created_by=str(user.get("user_id") or user.get("id") or "") or None,
    )
    if not item:
        return {"success": False, "error": "创建运行计划失败"}
    return {"success": True, "run_plan": item}


def _plan_update(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user.get("company_id") or "")
    plan_id = _pick_plan_id(arguments)
    if not plan_id:
        return {"success": False, "error": "plan_id 不能为空"}
    schedule_type = arguments.get("schedule_type")
    if schedule_type is not None:
        schedule_type = _ensure_allowed(
            _as_text(schedule_type),
            _ALLOWED_SCHEDULE_TYPES,
            "schedule_type",
        )
    scheme_code = arguments.get("scheme_code")
    if scheme_code is not None and _as_text(scheme_code):
        scheme = auth_db.get_execution_scheme(company_id=company_id, scheme_code=_as_text(scheme_code))
        if not scheme:
            return {"success": False, "error": "scheme_code 对应方案不存在"}
    item = auth_db.update_execution_run_plan(
        company_id=company_id,
        plan_id=plan_id,
        plan_name=arguments.get("plan_name"),
        scheme_code=_as_text(scheme_code) if scheme_code is not None else None,
        schedule_type=schedule_type,
        schedule_expr=arguments.get("schedule_expr"),
        biz_date_offset=arguments.get("biz_date_offset"),
        input_bindings_json=arguments.get("input_bindings_json"),
        channel_config_id=_normalize_optional_uuid(arguments.get("channel_config_id")),
        owner_mapping_json=arguments.get("owner_mapping_json"),
        plan_meta_json=arguments.get("plan_meta_json"),
        is_enabled=arguments.get("is_enabled"),
    )
    if not item:
        return {"success": False, "error": "运行计划不存在或更新失败"}
    return {"success": True, "run_plan": item}


def _plan_delete(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user.get("company_id") or "")
    plan_id = _pick_plan_id(arguments)
    plan_code = _as_text(arguments.get("plan_code"))
    if not plan_id and not plan_code:
        return {"success": False, "error": "plan_id 或 plan_code 不能为空"}
    if not plan_id:
        plan = auth_db.get_execution_run_plan(company_id=company_id, plan_code=plan_code)
        if not plan:
            return {"success": False, "error": "运行计划不存在或删除失败"}
        plan_id = _as_text(plan.get("id"))
    item = auth_db.delete_execution_run_plan(
        company_id=company_id,
        plan_id=plan_id,
    )
    if not item and plan_id:
        plan = auth_db.get_execution_run_plan(company_id=company_id, plan_code=plan_id)
        if plan:
            resolved_plan_id = _as_text(plan.get("id"))
            item = auth_db.delete_execution_run_plan(
                company_id=company_id,
                plan_id=resolved_plan_id,
            )
    if not item:
        return {"success": False, "error": "运行计划不存在或删除失败"}
    return {"success": True, "run_plan": item, "message": "运行计划已删除"}


def _run_list(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user.get("company_id") or "")
    scheme_code, scheme_error = _resolve_scheme_code(company_id, arguments)
    if scheme_error:
        return {"success": False, "error": scheme_error}
    plan_code, plan_error = _resolve_plan_code(company_id, arguments)
    if plan_error:
        return {"success": False, "error": plan_error}
    items = auth_db.list_execution_runs(
        company_id=company_id,
        scheme_code=scheme_code,
        plan_code=plan_code,
        limit=_as_int(arguments.get("limit"), 100, minimum=1, maximum=500),
        offset=_as_int(arguments.get("offset"), 0, minimum=0),
    )
    return {"success": True, "count": len(items), "runs": items}


def _run_get(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    run_id = str(arguments.get("run_id") or "").strip() or None
    run_code = str(arguments.get("run_code") or "").strip() or None
    if not run_id and not run_code:
        return {"success": False, "error": "run_id 或 run_code 至少提供一个"}
    item = auth_db.get_execution_run(
        company_id=str(user.get("company_id") or ""),
        run_id=run_id,
        run_code=run_code,
    )
    if not item:
        return {"success": False, "error": "执行记录不存在"}
    return {"success": True, "run": item}


def _run_create(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user.get("company_id") or "")
    scheme_code = _as_text(arguments.get("scheme_code"))
    if not scheme_code:
        return {"success": False, "error": "scheme_code 不能为空"}
    scheme = auth_db.get_execution_scheme(company_id=company_id, scheme_code=scheme_code)
    if not scheme:
        return {"success": False, "error": "scheme_code 对应方案不存在"}
    plan_code = _as_text(arguments.get("plan_code")) or None
    if plan_code:
        plan = auth_db.get_execution_run_plan(company_id=company_id, plan_code=plan_code)
        if not plan:
            return {"success": False, "error": "plan_code 对应运行计划不存在"}
        if _as_text(plan.get("scheme_code")) and _as_text(plan.get("scheme_code")) != scheme_code:
            return {"success": False, "error": "plan_code 与 scheme_code 不匹配"}
    scheme_type = _ensure_allowed(
        _as_text(arguments.get("scheme_type") or "recon"),
        _ALLOWED_SCHEME_TYPES,
        "scheme_type",
    )
    trigger_type = _ensure_allowed(
        _as_text(arguments.get("trigger_type") or "chat"),
        _ALLOWED_TRIGGER_TYPES,
        "trigger_type",
    )
    entry_mode = _ensure_allowed(
        _as_text(arguments.get("entry_mode") or "file"),
        _ALLOWED_ENTRY_MODES,
        "entry_mode",
    )
    execution_status = _ensure_allowed(
        _as_text(arguments.get("execution_status") or "running"),
        _ALLOWED_EXECUTION_STATUS,
        "execution_status",
    )
    item = auth_db.create_execution_run(
        company_id=company_id,
        run_code=_as_text(arguments.get("run_code")),
        scheme_code=scheme_code,
        plan_code=plan_code,
        scheme_type=scheme_type,
        trigger_type=trigger_type,
        entry_mode=entry_mode,
        execution_status=execution_status,
        failed_stage=str(arguments.get("failed_stage") or ""),
        failed_reason=str(arguments.get("failed_reason") or ""),
        run_context_json=_safe_dict(arguments.get("run_context_json")),
        source_snapshot_json=_safe_dict(arguments.get("source_snapshot_json")),
        subtasks_json=[v for v in _safe_list(arguments.get("subtasks_json")) if isinstance(v, dict)],
        proc_result_json=_safe_dict(arguments.get("proc_result_json")),
        recon_result_summary_json=_safe_dict(arguments.get("recon_result_summary_json")),
        artifacts_json=_safe_dict(arguments.get("artifacts_json")),
        anomaly_count=_as_int(arguments.get("anomaly_count"), 0, minimum=0),
        started_at_now=_as_bool(arguments.get("started_at_now"), True),
        finished_at_now=_as_bool(arguments.get("finished_at_now"), False),
    )
    if not item:
        return {"success": False, "error": "创建执行记录失败"}
    return {"success": True, "run": item}


def _run_update(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    run_id = str(arguments.get("run_id") or "").strip()
    if not run_id:
        return {"success": False, "error": "run_id 不能为空"}
    execution_status = arguments.get("execution_status")
    if execution_status is not None:
        execution_status = _ensure_allowed(
            _as_text(execution_status),
            _ALLOWED_EXECUTION_STATUS,
            "execution_status",
        )
    item = auth_db.update_execution_run(
        company_id=str(user.get("company_id") or ""),
        run_id=run_id,
        execution_status=execution_status,
        failed_stage=arguments.get("failed_stage"),
        failed_reason=arguments.get("failed_reason"),
        run_context_json=arguments.get("run_context_json"),
        source_snapshot_json=arguments.get("source_snapshot_json"),
        subtasks_json=arguments.get("subtasks_json"),
        proc_result_json=arguments.get("proc_result_json"),
        recon_result_summary_json=arguments.get("recon_result_summary_json"),
        artifacts_json=arguments.get("artifacts_json"),
        anomaly_count=_as_int(arguments.get("anomaly_count"), 0, minimum=0)
        if arguments.get("anomaly_count") is not None
        else None,
        started_at_now=_as_bool(arguments.get("started_at_now"), False),
        finished_at_now=_as_bool(arguments.get("finished_at_now"), False),
    )
    if not item:
        return {"success": False, "error": "执行记录不存在或更新失败"}
    return {"success": True, "run": item}


def _run_exceptions(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user.get("company_id") or "")
    run_id = _as_text(arguments.get("run_id"))
    if not run_id:
        run_code = _as_text(arguments.get("run_code"))
        if run_code:
            run = auth_db.get_execution_run(company_id=company_id, run_code=run_code)
            run_id = _as_text((run or {}).get("id"))
    if not run_id:
        return {"success": False, "error": "run_id 不能为空（或提供有效 run_code）"}
    items = auth_db.list_execution_run_exceptions(
        company_id=company_id,
        run_id=run_id,
        limit=_as_int(arguments.get("limit"), 500, minimum=1, maximum=1000),
        offset=_as_int(arguments.get("offset"), 0, minimum=0),
    )
    return {"success": True, "count": len(items), "exceptions": items}


def _exception_get(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    exception_id = str(arguments.get("exception_id") or "").strip()
    if not exception_id:
        return {"success": False, "error": "exception_id 不能为空"}
    item = auth_db.get_execution_run_exception(
        company_id=str(user.get("company_id") or ""),
        exception_id=exception_id,
    )
    if not item:
        return {"success": False, "error": "执行异常不存在"}
    return {"success": True, "exception": item}


def _exception_create(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user.get("company_id") or "")
    run_id = _as_text(arguments.get("run_id"))
    anomaly_key = _as_text(arguments.get("anomaly_key"))
    anomaly_type = _as_text(arguments.get("anomaly_type"))
    summary = _as_text(arguments.get("summary"))
    if not run_id or not anomaly_key or not anomaly_type or not summary:
        return {
            "success": False,
            "error": "run_id、anomaly_key、anomaly_type、summary 不能为空",
        }
    run = auth_db.get_execution_run(company_id=company_id, run_id=run_id)
    if not run:
        return {"success": False, "error": "run_id 对应执行记录不存在"}
    scheme_code = _as_text(arguments.get("scheme_code")) or _as_text(run.get("scheme_code"))
    if not scheme_code:
        return {"success": False, "error": "缺少 scheme_code 且无法从 run 记录推断"}
    item = auth_db.create_execution_run_exception(
        company_id=company_id,
        run_id=run_id,
        scheme_code=scheme_code,
        anomaly_key=anomaly_key,
        anomaly_type=anomaly_type,
        summary=summary,
        detail_json=_safe_dict(arguments.get("detail_json")),
        owner_name=str(arguments.get("owner_name") or ""),
        owner_identifier=str(arguments.get("owner_identifier") or ""),
        owner_contact_json=_safe_dict(arguments.get("owner_contact_json")),
        reminder_status=str(arguments.get("reminder_status") or "pending"),
        processing_status=str(arguments.get("processing_status") or "pending"),
        fix_status=str(arguments.get("fix_status") or "pending"),
        latest_feedback=str(arguments.get("latest_feedback") or ""),
        feedback_json=_safe_dict(arguments.get("feedback_json")),
        is_closed=_as_bool(arguments.get("is_closed"), False),
    )
    if not item:
        return {"success": False, "error": "创建执行异常失败"}
    return {"success": True, "exception": item}


def _exception_update(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    exception_id = str(arguments.get("exception_id") or "").strip()
    if not exception_id:
        return {"success": False, "error": "exception_id 不能为空"}
    item = auth_db.update_execution_run_exception(
        company_id=str(user.get("company_id") or ""),
        exception_id=exception_id,
        owner_name=arguments.get("owner_name"),
        owner_identifier=arguments.get("owner_identifier"),
        owner_contact_json=arguments.get("owner_contact_json"),
        reminder_status=arguments.get("reminder_status"),
        processing_status=arguments.get("processing_status"),
        fix_status=arguments.get("fix_status"),
        latest_feedback=arguments.get("latest_feedback"),
        feedback_json=arguments.get("feedback_json"),
        is_closed=arguments.get("is_closed"),
    )
    if not item:
        return {"success": False, "error": "执行异常不存在或更新失败"}
    return {"success": True, "exception": item}


def _proc_draft_trial(arguments: dict[str, Any]) -> dict[str, Any]:
    _require_user(arguments.get("auth_token", ""))
    rule_json = arguments.get("proc_rule_json")
    if not isinstance(rule_json, dict):
        return {"success": False, "error": "proc_rule_json 必须是对象"}

    validation = validate_rule_record(
        {"rule_code": "draft_proc", "rule": rule_json},
        expected_kind="proc_entry",
    )
    if not validation.get("success"):
        errors = _safe_list(validation.get("validation_errors"))
        return {
            "success": False,
            "trial_status": "invalid",
            "backend": "schema_validator",
            "ready_for_confirm": False,
            "error": "proc 草稿校验失败",
            "errors": [item for item in errors if isinstance(item, dict)],
            "validation": validation,
        }

    uploaded_files = _safe_list(arguments.get("uploaded_files"))
    uploaded_file_dicts = [v for v in uploaded_files if isinstance(v, dict)]
    sample_datasets = [v for v in _safe_list(arguments.get("sample_datasets")) if isinstance(v, dict)]
    normalized_rule = _safe_dict(validation.get("rule"))
    expected_targets = {
        _as_text(_safe_dict(step).get("target_table"))
        for step in _safe_list(normalized_rule.get("steps"))
        if _as_text(_safe_dict(step).get("target_table"))
    }
    temp_input_dir: str | None = None
    temp_output_dir: str | None = None
    source_samples: list[dict[str, Any]] = []
    input_warnings: list[str] = []

    try:
        validated_files, source_samples, input_warnings, temp_input_dir = _build_proc_trial_inputs(
            uploaded_files=uploaded_file_dicts,
            sample_datasets=sample_datasets,
        )
        if not validated_files:
            return {
                "success": False,
                "trial_status": "input_missing",
                "backend": "trial_input_builder",
                "ready_for_confirm": False,
                "error": "缺少可用于试跑的数据样本，请先选择数据集或提供 sample_rows。",
                "errors": [{"message": "缺少可用于试跑的数据样本"}],
                "warnings": input_warnings,
                "highlights": [
                    f"上传文件条数: {len(uploaded_file_dicts)}",
                    f"样本数据集条数: {len(sample_datasets)}",
                ],
                "metrics": {
                    "uploaded_files_total": len(uploaded_files),
                    "uploaded_files_valid": len(uploaded_file_dicts),
                    "sample_datasets_total": len(sample_datasets),
                    "sample_datasets_valid": 0,
                    "step_nodes": len(_safe_list(normalized_rule.get("steps"))),
                },
                "normalized_rule": normalized_rule,
            }

        temp_output_dir = tempfile.mkdtemp(prefix="proc_trial_output_")
        from proc.mcp_server.steps_runtime import execute_steps_rule

        generated_files = execute_steps_rule(
            rule_code="draft_proc_trial",
            rule_data=normalized_rule,
            validated_files=validated_files,
            output_dir=temp_output_dir,
        )

        output_samples: list[dict[str, Any]] = []
        output_targets: set[str] = set()
        output_warnings: list[str] = []
        for item in generated_files:
            target_table = _as_text(item.get("target_table"))
            output_file = _as_text(item.get("output_file"))
            output_targets.add(target_table)
            preview_rows: list[dict[str, Any]] = []
            if output_file:
                try:
                    preview_rows = _dataframe_to_preview_rows(_read_output_dataframe(output_file))
                except Exception as exc:  # noqa: BLE001
                    output_warnings.append(f"读取输出 {target_table or output_file} 抽样失败：{exc}")
            output_samples.append(
                {
                    "side": _infer_preview_side(target_table),
                    "title": target_table or "output",
                    "target_table": target_table,
                    "row_count": _as_int(item.get("row_count"), 0, minimum=0),
                    "rows": preview_rows,
                    "output_file": output_file,
                }
            )

        has_left_output = "left_recon_ready" in output_targets
        has_right_output = "right_recon_ready" in output_targets
        ready_for_confirm = has_left_output and has_right_output
        warnings = [*input_warnings, *output_warnings]
        if expected_targets and not expected_targets.issubset(output_targets):
            missing_targets = sorted(expected_targets - output_targets)
            warnings.append(f"试跑未生成预期输出：{', '.join(missing_targets)}")
        if not ready_for_confirm:
            warnings.append("试跑未同时生成 left_recon_ready 与 right_recon_ready。")

        return {
            "success": True,
            "trial_status": "executed",
            "backend": "steps_runtime",
            "ready_for_confirm": ready_for_confirm,
            "message": (
                "proc 试跑执行完成。"
                if ready_for_confirm
                else "proc 试跑已执行，但整理结果还不能直接进入对账。"
            ),
            "summary": (
                "已完成数据整理试跑，左右两侧对账数据均已生成。"
                if ready_for_confirm
                else "已完成数据整理试跑，但左右对账输出仍不完整，请调整整理配置。"
            ),
            "rule_type": str(validation.get("rule_type") or ""),
            "uploaded_files_count": len(validated_files),
            "errors": [],
            "warnings": warnings,
            "highlights": [
                f"输入样本数: {len(source_samples)}",
                f"输出结果表: {', '.join(sorted(output_targets)) or '--'}",
            ],
            "metrics": {
                "uploaded_files_total": len(uploaded_files),
                "uploaded_files_valid": len(uploaded_file_dicts),
                "sample_datasets_total": len(sample_datasets),
                "sample_datasets_valid": len([item for item in source_samples if item.get('source_id')]),
                "step_nodes": len(_safe_list(normalized_rule.get("steps"))),
                "output_tables": len(output_targets),
            },
            "normalized_rule": normalized_rule,
            "source_samples": source_samples,
            "output_samples": output_samples,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "trial_status": "failed",
            "backend": "steps_runtime",
            "ready_for_confirm": False,
            "error": f"proc 试跑执行失败：{exc}",
            "errors": _format_trial_errors([exc]),
            "warnings": [],
            "highlights": [
                f"上传文件条数: {len(uploaded_file_dicts)}",
                f"样本数据集条数: {len(sample_datasets)}",
            ],
            "metrics": {
                "uploaded_files_total": len(uploaded_files),
                "uploaded_files_valid": len(uploaded_file_dicts),
                "sample_datasets_total": len(sample_datasets),
                "step_nodes": len(_safe_list(normalized_rule.get("steps"))),
            },
            "normalized_rule": normalized_rule,
            "warnings": input_warnings,
            "source_samples": source_samples,
        }
    finally:
        for path in (temp_input_dir, temp_output_dir):
            if path:
                shutil.rmtree(path, ignore_errors=True)


def _recon_draft_trial(arguments: dict[str, Any]) -> dict[str, Any]:
    _require_user(arguments.get("auth_token", ""))
    rule_json = arguments.get("recon_rule_json")
    if not isinstance(rule_json, dict):
        return {"success": False, "error": "recon_rule_json 必须是对象"}

    validation = validate_rule_record(
        {"rule_code": "draft_recon", "rule": rule_json},
        expected_kind="recon",
    )
    if not validation.get("success"):
        errors = _safe_list(validation.get("validation_errors"))
        return {
            "success": False,
            "trial_status": "invalid",
            "backend": "schema_validator",
            "ready_for_confirm": False,
            "error": "recon 草稿校验失败",
            "errors": [item for item in errors if isinstance(item, dict)],
            "validation": validation,
        }

    validated_inputs = _safe_list(arguments.get("validated_inputs"))
    validated_input_dicts = [v for v in validated_inputs if isinstance(v, dict)]
    recon_rules = _safe_list((validation.get("rule") or {}).get("rules"))
    highlights = [f"输入数据条目: {len(validated_input_dicts)}", "当前阶段为结构校验，尚未执行真实试跑"]
    return {
        "success": True,
        "trial_status": "validated_only",
        "backend": "schema_validator",
        "ready_for_confirm": True,
        "message": "当前为最小可用实现：仅完成规则结构校验，未执行正式试跑。",
        "summary": "recon 草稿结构校验通过",
        "rule_type": str(validation.get("rule_type") or ""),
        "validated_inputs_count": len(validated_input_dicts),
        "errors": [],
        "warnings": [],
        "highlights": highlights,
        "metrics": {
            "validated_inputs_total": len(validated_inputs),
            "validated_inputs_valid": len(validated_input_dicts),
            "recon_rules_count": len(recon_rules),
        },
        "normalized_rule": validation.get("rule") or {},
    }
