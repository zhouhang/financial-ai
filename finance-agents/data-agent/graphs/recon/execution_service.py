"""recon 执行公共服务。

将 recon 执行核心逻辑下沉为可复用服务，供：
- 聊天子图节点（recon_task_execution_node）
- 内部 API（cron/程序触发）
共同调用。
"""

from __future__ import annotations

import logging
from typing import Any

from graphs.main_graph.public_nodes import _build_upload_name_maps
from tools.mcp_client import execute_recon

logger = logging.getLogger(__name__)


def _normalize_recon_input_item(item: dict[str, Any]) -> dict[str, Any] | None:
    """归一化单条 recon 输入。"""
    if not isinstance(item, dict):
        return None

    table_name = str(item.get("table_name") or "").strip()
    if not table_name:
        return None

    payload = item.get("payload")
    if not isinstance(payload, dict):
        payload = {}

    # 兼容平铺写法
    file_path = str(item.get("file_path") or "").strip()
    if file_path and "file_path" not in payload:
        payload["file_path"] = file_path

    dataset_ref = item.get("dataset_ref")
    if isinstance(dataset_ref, dict) and "dataset_ref" not in payload:
        payload["dataset_ref"] = dataset_ref

    input_type = str(item.get("input_type") or "").strip().lower()
    if not input_type:
        input_type = "file" if payload.get("file_path") else "dataset"

    return {
        "table_name": table_name,
        "input_type": input_type,
        "payload": payload,
    }


def normalize_recon_inputs(raw_inputs: list[Any]) -> list[dict[str, Any]]:
    """归一化 recon_inputs 数组。"""
    result: list[dict[str, Any]] = []
    for item in raw_inputs:
        normalized = _normalize_recon_input_item(item if isinstance(item, dict) else {})
        if normalized is not None:
            result.append(normalized)
    return result


def build_recon_inputs_from_file_matches(
    *,
    file_match_results: list[dict[str, Any]],
    uploaded_files_raw: list[Any],
) -> tuple[list[dict[str, Any]], dict[str, str], str | None]:
    """将文件校验结果转换为统一 recon_inputs。"""
    if not file_match_results:
        return [], {}, "未找到文件校验结果，请先完成文件校验步骤"

    file_path_map, ref_to_display_name = _build_upload_name_maps(uploaded_files_raw)
    recon_inputs: list[dict[str, Any]] = []

    for match in file_match_results:
        file_name = str(match.get("file_name") or "").strip()
        table_name = str(match.get("table_name") or "").strip()
        if not file_name or not table_name:
            continue
        file_path = str(file_path_map.get(file_name) or "").strip()
        if not file_path:
            continue
        recon_inputs.append(
            {
                "table_name": table_name,
                "input_type": "file",
                "payload": {
                    "file_path": file_path,
                    "file_name": file_name,
                    "table_id": match.get("table_id"),
                },
            }
        )

    if not recon_inputs:
        return [], ref_to_display_name, "无法构建文件路径映射，请检查上传文件状态"
    return recon_inputs, ref_to_display_name, None


def resolve_recon_inputs(
    *,
    state: dict[str, Any],
    ctx: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, str], str | None]:
    """统一解析 recon 输入。

    优先读取 ctx.recon_inputs，缺失时回退到文件校验结果+上传文件的旧路径。
    """
    raw_inputs = list(ctx.get("recon_inputs") or [])
    recon_inputs = normalize_recon_inputs(raw_inputs)
    if recon_inputs:
        # 仅用于展示文件名映射，dataset 模式通常为空。
        _, ref_to_display_name = _build_upload_name_maps(list(state.get("uploaded_files") or []))
        return recon_inputs, ref_to_display_name, None

    return build_recon_inputs_from_file_matches(
        file_match_results=list(ctx.get("file_match_results") or []),
        uploaded_files_raw=list(state.get("uploaded_files") or []),
    )


def build_execution_request(
    *,
    rule_code: str,
    rule_id: str,
    auth_token: str,
    recon_inputs: list[dict[str, Any]],
    run_context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str | None]:
    """构建统一执行请求。"""
    validated_inputs: list[dict[str, Any]] = []
    validated_files: list[dict[str, str]] = []

    for item in recon_inputs:
        table_name = str(item.get("table_name") or "").strip()
        input_type = str(item.get("input_type") or "").strip().lower()
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        if not table_name:
            continue

        if input_type == "file":
            file_path = str(payload.get("file_path") or "").strip()
            if not file_path:
                continue
            validated_inputs.append(
                {
                    "table_name": table_name,
                    "input_type": "file",
                    "file_path": file_path,
                }
            )
            validated_files.append(
                {
                    "table_name": table_name,
                    "file_path": file_path,
                }
            )
            continue

        if input_type == "dataset":
            dataset_ref = payload.get("dataset_ref")
            if not isinstance(dataset_ref, dict) or not dataset_ref:
                dataset_ref = dict(payload)
            validated_inputs.append(
                {
                    "table_name": table_name,
                    "input_type": "dataset",
                    "dataset_ref": dataset_ref,
                }
            )
            continue

        logger.warning(f"[recon] 忽略未知 input_type: {input_type}, table_name={table_name}")

    if not validated_inputs:
        return {}, "recon_inputs 为空或无有效输入，无法执行对账"

    request: dict[str, Any] = {
        "rule_code": rule_code,
        "rule_id": rule_id,
        "validated_inputs": validated_inputs,
        # 兼容未升级的 MCP：仍保留文件模式参数
        "validated_files": validated_files,
        "run_context": run_context or {},
    }
    if auth_token:
        request["auth_token"] = auth_token
    return request, None


async def run_recon_execution(execution_request: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """执行 recon，返回 MCP 原始结果。"""
    try:
        recon_result = await execute_recon(
            validated_inputs=list(execution_request.get("validated_inputs") or []),
            validated_files=list(execution_request.get("validated_files") or []),
            rule_code=str(execution_request.get("rule_code") or ""),
            rule_id=str(execution_request.get("rule_id") or ""),
            auth_token=str(execution_request.get("auth_token") or ""),
        )
        return recon_result, None
    except Exception as exc:
        return {}, f"调用对账服务失败: {exc}"
