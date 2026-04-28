"""Unified data source RESTful API routes."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import RedirectResponse

from tools.mcp_client import (
    data_source_authorize,
    data_source_create,
    data_source_delete,
    data_source_disable_dataset,
    data_source_disable,
    data_source_discover_datasets,
    data_source_get,
    data_source_get_dataset,
    data_source_get_dataset_collection_detail,
    data_source_list_collection_records,
    data_source_list_dataset_candidates,
    data_source_get_sync_job,
    data_source_handle_callback,
    data_source_import_openapi,
    data_source_list,
    data_source_list_datasets,
    data_source_list_events,
    data_source_list_sync_jobs,
    data_source_refresh_dataset_semantic_profile,
    data_source_preflight_rule_binding,
    data_source_publish_dataset,
    data_source_preview,
    data_source_test,
    data_source_trigger_dataset_collection,
    data_source_trigger_sync,
    data_source_unpublish_dataset,
    data_source_upsert_dataset,
    data_source_update_dataset_semantic_profile,
    data_source_update,
)

router = APIRouter(tags=["data-source"])
logger = logging.getLogger(__name__)

_DOCUMENT_TEXT_LIMIT = 18000
_JSON_FENCE_PATTERN = re.compile(r"```(?:json)?\s*(\[[\s\S]*\]|\{[\s\S]*\})\s*```", re.IGNORECASE)


def _extract_auth_token(authorization: Optional[str]) -> str:
    if not authorization:
        return ""
    return authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization


def _safe_result_error(result: dict[str, Any], fallback: str) -> str:
    detail = str(result.get("message") or result.get("error") or "").strip()
    if not detail:
        return fallback
    lowered = detail.lower()
    if any(marker in lowered for marker in ("traceback", "jsonrpc", "runtimeerror", "exception", "stack")):
        return fallback
    if len(detail) > 180:
        return fallback
    if "unknown tool" in lowered or "未知的工具" in lowered:
        return "后端能力尚未部署完成，请联系管理员检查数据连接服务"
    if "timeout" in lowered or "超时" in lowered:
        return "服务处理超时，请稍后重试"
    return detail


def _strip_markdown_fence(text: str) -> str:
    match = _JSON_FENCE_PATTERN.search(text)
    if match:
        return match.group(1).strip()
    return text.strip()


def _looks_like_openapi_spec(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    paths = value.get("paths")
    return isinstance(paths, dict) and ("openapi" in value or "swagger" in value)


def _try_parse_openapi_spec(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value if _looks_like_openapi_spec(value) else None
    if not isinstance(value, str) or not value.strip():
        return None

    raw = value.strip()
    try:
        parsed = json.loads(raw)
        if _looks_like_openapi_spec(parsed):
            return parsed
    except Exception:
        pass

    try:
        import yaml  # type: ignore

        parsed_yaml = yaml.safe_load(raw)
        if _looks_like_openapi_spec(parsed_yaml):
            return parsed_yaml
    except Exception:
        return None
    return None


def _clean_document_text(raw_text: str, content_type: str = "") -> str:
    text = str(raw_text or "").strip()
    lowered_content_type = content_type.lower()
    lowered_text = text[:1000].lower()
    if "html" in lowered_content_type or "<html" in lowered_text or "<body" in lowered_text:
        text = re.sub(r"(?is)<script.*?>.*?</script>", " ", text)
        text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:_DOCUMENT_TEXT_LIMIT]


async def _load_document_payload(input_mode: str, document_url: str, document_content: str) -> tuple[str, str]:
    normalized_mode = (input_mode or "url").strip().lower()
    if normalized_mode == "content":
        content = str(document_content or "").strip()
        if not content:
            raise ValueError("请先填写文档内容")
        return content, ""

    url = str(document_url or "").strip()
    if not url:
        raise ValueError("请先填写文档地址")

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.text, str(response.headers.get("content-type") or "")


def _normalize_manual_endpoint_input(raw: dict[str, Any]) -> dict[str, Any]:
    method = str(raw.get("method") or "GET").strip().upper() or "GET"
    request_param_type = str(raw.get("request_param_type") or raw.get("param_type") or "params").strip().lower()
    if request_param_type not in {"json", "params"}:
        request_param_type = "params"

    request_params = raw.get("request_params")
    if not isinstance(request_params, dict):
        request_params = raw.get("params") if isinstance(raw.get("params"), dict) else {}

    endpoint: dict[str, Any] = {
        "dataset_name": str(raw.get("dataset_name") or raw.get("name") or "").strip(),
        "path": str(raw.get("path") or raw.get("endpoint") or raw.get("url") or raw.get("api_url") or "").strip(),
        "method": method,
    }
    if request_param_type == "json":
        endpoint["body"] = request_params
    else:
        endpoint["query"] = request_params

    response_data_path = str(raw.get("response_data_path") or "").strip()
    if response_data_path:
        endpoint["response_data_path"] = response_data_path

    description = str(raw.get("description") or "").strip()
    if description:
        endpoint["description"] = description

    return endpoint


async def _extract_manual_endpoints_from_document(document_text: str) -> list[dict[str, Any]]:
    from utils.llm import get_llm

    prompt = (
        "你是 API 数据建模助手。"
        "请从下面的接口文档中提取适合生成 Tally API 数据集的 endpoint 定义。"
        "只返回 JSON 数组，不要输出任何解释。\n\n"
        "每个数组元素必须是对象，字段如下：\n"
        '- "dataset_name": 中文数据集名称\n'
        '- "path": 接口路径或完整 URL\n'
        '- "method": GET 或 POST\n'
        '- "request_param_type": "params" 或 "json"\n'
        '- "request_params": 对象，填入常见请求参数示例，没有则返回 {}\n'
        '- "response_data_path": 响应体中列表数据所在路径，没有就返回 ""\n'
        '- "description": 一句简短说明\n\n'
        "只提取真正可用于取数的接口，最多返回 12 个。\n\n"
        f"文档内容：\n{document_text}"
    )

    llm = get_llm(temperature=0.1)
    response = await asyncio.to_thread(llm.invoke, prompt)
    content = str(getattr(response, "content", "") or "").strip()
    if not content:
        raise ValueError("LLM 未返回可用的接口定义")

    parsed = json.loads(_strip_markdown_fence(content))
    if not isinstance(parsed, list):
        raise ValueError("LLM 返回结果不是 JSON 数组")

    endpoints: list[dict[str, Any]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        normalized = _normalize_manual_endpoint_input(item)
        if normalized.get("path"):
            endpoints.append(normalized)
    if not endpoints:
        raise ValueError("未从文档中提取到可用接口")
    return endpoints


async def _resolve_discover_inputs(body: "DataSourceDiscoverRequest") -> dict[str, Any]:
    discover_mode = str(body.discover_mode or "").strip().lower()
    if discover_mode == "document":
        raw_document, content_type = await _load_document_payload(
            body.document_input_mode,
            body.document_url,
            body.document_content,
        )
        openapi_spec = _try_parse_openapi_spec(raw_document)
        if openapi_spec is not None:
            return {
                "discover_mode": "openapi",
                "openapi_spec": openapi_spec,
                "manual_endpoints": [],
            }

        document_text = _clean_document_text(raw_document, content_type)
        if not document_text:
            raise ValueError("文档内容为空，无法生成 API 数据集")
        manual_endpoints = await _extract_manual_endpoints_from_document(document_text)
        return {
            "discover_mode": "manual",
            "openapi_spec": None,
            "manual_endpoints": manual_endpoints,
        }

    manual_endpoints = [item for item in body.manual_endpoints if isinstance(item, dict)]
    if body.manual_endpoint:
        manual_endpoints.append(_normalize_manual_endpoint_input(body.manual_endpoint))

    return {
        "discover_mode": discover_mode,
        "openapi_spec": body.openapi_spec,
        "openapi_url": body.openapi_url,
        "manual_endpoints": manual_endpoints,
    }


def _resolve_binding_scope(task_code: str = "", binding_scope: str = "") -> str:
    scope = str(binding_scope or task_code or "").strip().lower()
    if scope in {"proc", "recon"}:
        return scope
    return ""


def _build_callback_redirect_url(
    return_path: str,
    *,
    source_id: str,
    success: bool,
    message: str,
) -> str:
    raw_target = (return_path or "/").strip() or "/"
    if not raw_target.startswith("/"):
        raw_target = "/"

    parsed = urlsplit(raw_target)
    query_pairs = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query_pairs.update(
        {
            "section": "data-connections",
            "data_source_auth_status": "success" if success else "failed",
            "data_source_id": source_id,
            "data_source_auth_message": message,
        }
    )
    return urlunsplit(("", "", parsed.path or "/", urlencode(query_pairs), ""))


class DataSourceItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    name: str = ""
    code: str = ""
    source_kind: str
    domain_type: str
    provider_code: str = ""
    execution_mode: str = "deterministic"
    status: str = "active"
    enabled: bool = True
    capabilities: list[str] = Field(default_factory=list)
    auth_status: str = ""
    description: str = ""
    connection_config: dict[str, Any] = Field(default_factory=dict)
    extract_config: dict[str, Any] = Field(default_factory=dict)
    mapping_config: dict[str, Any] = Field(default_factory=dict)
    runtime_config: dict[str, Any] = Field(default_factory=dict)
    source_summary: dict[str, Any] = Field(default_factory=dict)
    dataset_summary: dict[str, Any] = Field(default_factory=dict)
    health_summary: dict[str, Any] = Field(default_factory=dict)
    datasets: list[dict[str, Any]] = Field(default_factory=list)
    recent_events: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    health_status: str = ""
    last_checked_at: Optional[str] = None
    last_error_message: str = ""
    last_sync_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DataSourceListResponse(BaseModel):
    success: bool
    mode: str = "mock"
    count: int = 0
    sources: list[DataSourceItem] = Field(default_factory=list)
    message: str = ""


class DataSourceGetResponse(BaseModel):
    success: bool
    mode: str = "mock"
    source: Optional[DataSourceItem] = None
    message: str = ""


class DataSourceCreateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = ""
    source_kind: str
    domain_type: str
    provider_code: str = ""
    execution_mode: str = ""
    description: str = ""
    connection_config: dict[str, Any] = Field(default_factory=dict)
    auth_config: dict[str, Any] = Field(default_factory=dict)
    extract_config: dict[str, Any] = Field(default_factory=dict)
    mapping_config: dict[str, Any] = Field(default_factory=dict)
    runtime_config: dict[str, Any] = Field(default_factory=dict)


class DataSourceUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: Optional[str] = None
    provider_code: Optional[str] = None
    domain_type: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    connection_config: Optional[dict[str, Any]] = None
    auth_config: Optional[dict[str, Any]] = None
    extract_config: Optional[dict[str, Any]] = None
    mapping_config: Optional[dict[str, Any]] = None
    runtime_config: Optional[dict[str, Any]] = None


class DataSourceUpsertResponse(BaseModel):
    success: bool
    mode: str = "mock"
    source: Optional[DataSourceItem] = None
    message: str = ""


class DataSourceDisableRequest(BaseModel):
    reason: str = ""
    mode: str = ""


class DataSourceTestRequest(BaseModel):
    mode: str = ""
    connection_config: dict[str, Any] = Field(default_factory=dict)
    auth_config: dict[str, Any] = Field(default_factory=dict)


class DataSourceDeleteResponse(BaseModel):
    success: bool
    mode: str = "mock"
    source: Optional[DataSourceItem] = None
    message: str = ""


class DataSourceAuthorizeRequest(BaseModel):
    return_path: str = "/"
    mode: str = ""


class DataSourceAuthorizeResponse(BaseModel):
    success: bool
    mode: str = "mock"
    source_id: str
    session_id: str = ""
    state: str = ""
    auth_url: str = ""
    expires_in: int = 0
    message: str = ""


class DataSourceHandleCallbackRequest(BaseModel):
    state: str = ""
    code: str = ""
    error: str = ""
    error_description: str = ""
    mode: str = ""


class DataSourceHandleCallbackResponse(BaseModel):
    success: bool
    mode: str = "mock"
    source_id: str
    message: str = ""
    return_path: str = "/"
    source: Optional[DataSourceItem] = None


class DataSourceTriggerSyncRequest(BaseModel):
    idempotency_key: str = ""
    window_start: str = ""
    window_end: str = ""
    params: dict[str, Any] = Field(default_factory=dict)
    mode: str = ""


class DataSourceSyncJobResponse(BaseModel):
    success: bool
    mode: str = "mock"
    source_id: Optional[str] = None
    job: dict[str, Any] | None = None
    reused: Optional[bool] = None
    message: str = ""


class DataSourceSyncJobsListResponse(BaseModel):
    success: bool
    mode: str = "mock"
    count: int = 0
    jobs: list[dict[str, Any]] = Field(default_factory=list)
    message: str = ""


class DataSourcePreviewRequest(BaseModel):
    limit: int = 20
    mode: str = ""


class DataSourcePreviewResponse(BaseModel):
    success: bool
    mode: str = "mock"
    source_id: str
    count: int = 0
    rows: list[dict[str, Any]] = Field(default_factory=list)
    message: str = ""


class DataSourceDatasetCollectionDetailResponse(BaseModel):
    success: bool
    mode: str = "mock"
    source_id: str = ""
    resource_key: str = ""
    dataset: dict[str, Any] | None = None
    collection_stats: dict[str, Any] = Field(default_factory=dict)
    jobs: list[dict[str, Any]] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    count: int = 0
    row_count: int = 0
    message: str = ""


class DataSourceCollectionRecordsResponse(BaseModel):
    success: bool
    mode: str = "mock"
    source_id: str = ""
    resource_key: str = ""
    dataset: dict[str, Any] | None = None
    records: list[dict[str, Any]] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    count: int = 0
    record_count: int = 0
    message: str = ""


class DataSourceDatasetListResponse(BaseModel):
    success: bool
    mode: str = "mock"
    source_id: str = ""
    count: int = 0
    total: int = 0
    page: int = 1
    page_size: int = 50
    datasets: list[dict[str, Any]] = Field(default_factory=list)
    dataset_summary: dict[str, Any] = Field(default_factory=dict)
    source_summary: dict[str, Any] = Field(default_factory=dict)
    health_summary: dict[str, Any] = Field(default_factory=dict)
    message: str = ""


class DataSourceDatasetGetResponse(BaseModel):
    success: bool
    mode: str = "mock"
    source_id: str = ""
    dataset: dict[str, Any] | None = None
    source_summary: dict[str, Any] = Field(default_factory=dict)
    health_summary: dict[str, Any] = Field(default_factory=dict)
    message: str = ""


class DataSourceDatasetUpsertRequest(BaseModel):
    dataset_code: str
    dataset_name: str = ""
    resource_key: str = ""
    dataset_kind: str = "table"
    origin_type: str = "manual"
    schema_name: str = ""
    object_name: str = ""
    object_type: str = ""
    publish_status: str = ""
    business_domain: str = ""
    business_object_type: str = ""
    grain: str = ""
    verified_status: str = ""
    usage_count: int | None = None
    last_used_at: str = ""
    search_text: str = ""
    extract_config: dict[str, Any] = Field(default_factory=dict)
    schema_summary: dict[str, Any] = Field(default_factory=dict)
    sync_strategy: dict[str, Any] = Field(default_factory=dict)
    status: str = "active"
    enabled: bool = True
    health_status: str = "unknown"
    last_checked_at: str = ""
    last_sync_at: str = ""
    last_error_message: str = ""
    meta: dict[str, Any] = Field(default_factory=dict)
    mode: str = ""


class DataSourceDatasetDisableRequest(BaseModel):
    reason: str = ""
    mode: str = ""


class DataSourceDatasetPublishRequest(BaseModel):
    dataset_code: str = ""
    resource_key: str = ""
    business_name: str = ""
    business_description: str = ""
    key_fields: list[str] = Field(default_factory=list)
    field_label_map: dict[str, Any] = Field(default_factory=dict)
    fields: list[dict[str, Any]] = Field(default_factory=list)
    status: str = ""
    schema_name: str = ""
    object_name: str = ""
    object_type: str = ""
    business_domain: str = ""
    business_object_type: str = ""
    grain: str = ""
    verified_status: str = ""
    search_text: str = ""
    usage_count: int | None = None
    last_used_at: str = ""
    catalog_profile: dict[str, Any] = Field(default_factory=dict)
    collection_config: dict[str, Any] = Field(default_factory=dict)
    mode: str = ""


class DataSourceDatasetUnpublishRequest(BaseModel):
    dataset_code: str = ""
    resource_key: str = ""
    reason: str = ""
    catalog_profile: dict[str, Any] = Field(default_factory=dict)
    mode: str = ""


class DataSourceDatasetSemanticRefreshRequest(BaseModel):
    dataset_code: str = ""
    resource_key: str = ""
    sample_limit: int = 10
    mode: str = ""


class DataSourceDatasetSemanticUpdateRequest(BaseModel):
    dataset_code: str = ""
    resource_key: str = ""
    semantic_profile: dict[str, Any] = Field(default_factory=dict)
    business_name: str = ""
    business_description: str = ""
    key_fields: list[str] = Field(default_factory=list)
    field_label_map: dict[str, Any] = Field(default_factory=dict)
    fields: list[dict[str, Any]] = Field(default_factory=list)
    status: str = ""
    mode: str = ""


class DataSourceDatasetCollectionTriggerRequest(BaseModel):
    resource_key: str = ""
    biz_date: str = ""
    background: bool = True
    params: dict[str, Any] = Field(default_factory=dict)
    mode: str = ""


def _default_collection_biz_date() -> str:
    """服务器侧统一计算手动采集默认业务日期：T-1。"""
    return (datetime.now() - timedelta(days=1)).date().isoformat()


class DataSourceDatasetUpsertResponse(BaseModel):
    success: bool
    mode: str = "mock"
    source_id: str = ""
    dataset: dict[str, Any] | None = None
    source_summary: dict[str, Any] = Field(default_factory=dict)
    message: str = ""


class DataSourceDatasetCandidatesRequest(BaseModel):
    binding_scope: str = "scheme"
    scene_type: str = "recon"
    role_code: str = ""
    keyword: str = ""
    filters: dict[str, Any] = Field(default_factory=dict)
    page: int = 1
    page_size: int = 30
    mode: str = ""


class DataSourceDatasetCandidatesResponse(BaseModel):
    success: bool
    mode: str = "mock"
    binding_scope: str = "scheme"
    scene_type: str = "recon"
    role_code: str = ""
    count: int = 0
    total: int = 0
    page: int = 1
    page_size: int = 30
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    message: str = ""


class DataSourceDiscoverRequest(BaseModel):
    persist: bool = True
    limit: int = 500
    offset: int = 0
    schema_whitelist: list[str] = Field(default_factory=list)
    target_resource_keys: list[str] = Field(default_factory=list)
    discover_mode: str = ""
    document_input_mode: str = ""
    document_url: str = ""
    document_content: str = ""
    openapi_url: str = ""
    openapi_spec: dict[str, Any] | str | None = None
    manual_endpoints: list[dict[str, Any]] = Field(default_factory=list)
    manual_endpoint: dict[str, Any] | None = None
    mode: str = ""
    connection_config: dict[str, Any] = Field(default_factory=dict)
    auth_config: dict[str, Any] = Field(default_factory=dict)


class DataSourceDiscoverResponse(BaseModel):
    success: bool
    mode: str = "mock"
    source_id: str
    provider_code: str = ""
    dataset_count: int = 0
    datasets: list[dict[str, Any]] = Field(default_factory=list)
    persist: bool = True
    persisted_count: int = 0
    scan_summary: dict[str, Any] = Field(default_factory=dict)
    discover_summary: dict[str, Any] = Field(default_factory=dict)
    message: str = ""


class DataSourceImportOpenAPIRequest(BaseModel):
    openapi_url: str = ""
    openapi_spec: dict[str, Any] | str | None = None
    persist: bool = True
    mode: str = ""


class DataSourceEventsResponse(BaseModel):
    success: bool
    mode: str = "mock"
    source_id: str = ""
    count: int = 0
    events: list[dict[str, Any]] = Field(default_factory=list)
    message: str = ""


class DataSourcePreflightRequest(BaseModel):
    task_code: str = ""
    rule_code: str = ""
    binding_scope: str = ""
    binding_code: str = ""
    stale_after_minutes: int = 24 * 60
    mode: str = ""


class DataSourcePreflightResponse(BaseModel):
    success: bool
    mode: str = "mock"
    ready: bool = False
    binding_scope: str = ""
    binding_code: str = ""
    summary: dict[str, Any] = Field(default_factory=dict)
    preflight: dict[str, Any] = Field(default_factory=dict)
    message: str = ""


@router.get("/data-sources", response_model=DataSourceListResponse)
async def list_data_sources(
    source_kind: str = Query("", description="可选：按数据源类型筛选"),
    domain_type: str = Query("", description="可选：按业务域筛选"),
    mode: str = Query("", description="mock 或 real；为空时使用服务默认模式"),
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    result = await data_source_list(
        auth_token,
        mode=mode,
        source_kind=source_kind,
        domain_type=domain_type,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=_safe_result_error(result, "获取数据源列表失败"))

    return DataSourceListResponse(
        success=True,
        mode=str(result.get("mode") or mode or "mock"),
        count=int(result.get("count") or len(result.get("sources") or [])),
        sources=result.get("sources") or [],
        message=str(result.get("message") or ""),
    )


@router.post("/data-sources/dataset-candidates", response_model=DataSourceDatasetCandidatesResponse)
async def list_dataset_candidates(
    body: DataSourceDatasetCandidatesRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    result = await data_source_list_dataset_candidates(
        auth_token,
        binding_scope=body.binding_scope,
        scene_type=body.scene_type,
        role_code=body.role_code,
        keyword=body.keyword,
        filters=body.filters,
        page=body.page,
        page_size=body.page_size,
        mode=body.mode,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=_safe_result_error(result, "获取候选数据集失败"))
    return DataSourceDatasetCandidatesResponse(
        success=True,
        mode=str(result.get("mode") or body.mode or "mock"),
        binding_scope=str(result.get("binding_scope") or body.binding_scope),
        scene_type=str(result.get("scene_type") or body.scene_type),
        role_code=str(result.get("role_code") or body.role_code),
        count=int(result.get("count") or len(result.get("candidates") or [])),
        total=int(result.get("total") or result.get("count") or len(result.get("candidates") or [])),
        page=int(result.get("page") or body.page),
        page_size=int(result.get("page_size") or body.page_size),
        candidates=result.get("candidates") or [],
        message=str(result.get("message") or ""),
    )


@router.get("/data-sources/{source_id}", response_model=DataSourceGetResponse)
async def get_data_source(
    source_id: str,
    mode: str = Query("", description="mock 或 real；为空时使用服务默认模式"),
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    result = await data_source_get(auth_token, source_id, mode=mode)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=_safe_result_error(result, "数据源不存在"))
    return DataSourceGetResponse(
        success=True,
        mode=str(result.get("mode") or mode or "mock"),
        source=result.get("source"),
        message=str(result.get("message") or ""),
    )


@router.post("/data-sources", response_model=DataSourceUpsertResponse)
async def create_data_source(
    body: DataSourceCreateRequest,
    mode: str = Query("", description="mock 或 real；为空时使用服务默认模式"),
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    payload = body.model_dump(exclude_none=True)
    result = await data_source_create(auth_token, payload, mode=mode)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "创建数据源失败"))
    return DataSourceUpsertResponse(
        success=True,
        mode=str(result.get("mode") or mode or "mock"),
        source=result.get("source"),
        message=str(result.get("message") or ""),
    )


@router.patch("/data-sources/{source_id}", response_model=DataSourceUpsertResponse)
async def update_data_source(
    source_id: str,
    body: DataSourceUpdateRequest,
    mode: str = Query("", description="mock 或 real；为空时使用服务默认模式"),
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    payload = body.model_dump(exclude_none=True)
    result = await data_source_update(auth_token, source_id, payload, mode=mode)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "更新数据源失败"))
    return DataSourceUpsertResponse(
        success=True,
        mode=str(result.get("mode") or mode or "mock"),
        source=result.get("source"),
        message=str(result.get("message") or ""),
    )


@router.post("/data-sources/{source_id}/disable", response_model=DataSourceUpsertResponse)
async def disable_data_source(
    source_id: str,
    body: DataSourceDisableRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    result = await data_source_disable(auth_token, source_id, reason=body.reason, mode=body.mode)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "停用数据源失败"))
    return DataSourceUpsertResponse(
        success=True,
        mode=str(result.get("mode") or body.mode or "mock"),
        source=result.get("source"),
        message=str(result.get("message") or "数据源已停用"),
    )


@router.delete("/data-sources/{source_id}", response_model=DataSourceDeleteResponse)
async def delete_data_source(
    source_id: str,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    result = await data_source_delete(auth_token, source_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "删除数据源失败"))
    return DataSourceDeleteResponse(
        success=True,
        mode=str(result.get("mode") or "mock"),
        source=result.get("source"),
        message=str(result.get("message") or "数据源已删除"),
    )


@router.post("/data-sources/{source_id}/test")
async def test_data_source(
    source_id: str,
    body: DataSourceTestRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    result = await data_source_test(
        auth_token,
        source_id,
        mode=body.mode,
        connection_config=body.connection_config,
        auth_config=body.auth_config,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "数据源测试失败"))
    return result


@router.post("/data-sources/{source_id}/authorize", response_model=DataSourceAuthorizeResponse)
async def authorize_data_source(
    source_id: str,
    body: DataSourceAuthorizeRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    result = await data_source_authorize(
        auth_token,
        source_id,
        return_path=body.return_path,
        mode=body.mode,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "数据源授权发起失败"))
    return DataSourceAuthorizeResponse(
        success=True,
        mode=str(result.get("mode") or body.mode or "mock"),
        source_id=source_id,
        session_id=str(result.get("session_id") or ""),
        state=str(result.get("state") or ""),
        auth_url=str(result.get("auth_url") or ""),
        expires_in=int(result.get("expires_in") or 0),
        message=str(result.get("message") or ""),
    )


@router.get("/data-sources/auth/callback/{source_id}")
async def handle_data_source_callback_redirect(
    source_id: str,
    state: str = Query("", description="授权会话状态"),
    code: str = Query("", description="授权码"),
    error: str = Query("", description="授权错误码"),
    error_description: str = Query("", description="授权错误描述"),
    mode: str = Query("", description="mock 或 real；为空时使用服务默认模式"),
):
    result = await data_source_handle_callback(
        source_id,
        state=state,
        code=code,
        error=error,
        error_description=error_description,
        mode=mode,
    )
    success = bool(result.get("success"))
    message = str(result.get("message") or result.get("error") or "授权失败，请重试")
    redirect_to = _build_callback_redirect_url(
        str(result.get("return_path") or "/"),
        source_id=source_id,
        success=success,
        message=message,
    )
    return RedirectResponse(url=redirect_to, status_code=303)


@router.post("/data-sources/{source_id}/handle-callback", response_model=DataSourceHandleCallbackResponse)
async def handle_data_source_callback(
    source_id: str,
    body: DataSourceHandleCallbackRequest,
):
    result = await data_source_handle_callback(
        source_id,
        state=body.state,
        code=body.code,
        error=body.error,
        error_description=body.error_description,
        mode=body.mode,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "处理授权回调失败"))
    return DataSourceHandleCallbackResponse(
        success=True,
        mode=str(result.get("mode") or body.mode or "mock"),
        source_id=source_id,
        message=str(result.get("message") or ""),
        return_path=str(result.get("return_path") or "/"),
        source=result.get("source"),
    )


@router.post("/data-sources/{source_id}/sync", response_model=DataSourceSyncJobResponse)
async def trigger_data_source_sync(
    source_id: str,
    body: DataSourceTriggerSyncRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    result = await data_source_trigger_sync(
        auth_token,
        source_id,
        idempotency_key=body.idempotency_key,
        window_start=body.window_start,
        window_end=body.window_end,
        params=body.params,
        mode=body.mode,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "触发同步失败"))
    return DataSourceSyncJobResponse(
        success=True,
        mode=str(result.get("mode") or body.mode or "mock"),
        source_id=str(result.get("source_id") or source_id),
        job=result.get("job"),
        reused=result.get("reused"),
        message=str(result.get("message") or ""),
    )


@router.get("/sync-jobs/{sync_job_id}", response_model=DataSourceSyncJobResponse)
async def get_sync_job(
    sync_job_id: str,
    mode: str = Query("", description="mock 或 real；为空时使用服务默认模式"),
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    result = await data_source_get_sync_job(auth_token, sync_job_id, mode=mode)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "同步任务不存在"))
    return DataSourceSyncJobResponse(
        success=True,
        mode=str(result.get("mode") or mode or "mock"),
        source_id=str((result.get("job") or {}).get("source_id") or ""),
        job=result.get("job"),
        reused=result.get("reused"),
        message=str(result.get("message") or ""),
    )


@router.get("/sync-jobs", response_model=DataSourceSyncJobsListResponse)
async def list_sync_jobs(
    source_id: str = Query("", description="可选：按 source_id 过滤"),
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
    mode: str = Query("", description="mock 或 real；为空时使用服务默认模式"),
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    result = await data_source_list_sync_jobs(
        auth_token,
        source_id=source_id,
        limit=limit,
        mode=mode,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "获取同步任务列表失败"))
    return DataSourceSyncJobsListResponse(
        success=True,
        mode=str(result.get("mode") or mode or "mock"),
        count=int(result.get("count") or len(result.get("jobs") or [])),
        jobs=result.get("jobs") or [],
        message=str(result.get("message") or ""),
    )


@router.get(
    "/data-sources/{source_id}/datasets/{dataset_id}/collection-detail",
    response_model=DataSourceDatasetCollectionDetailResponse,
)
async def get_dataset_collection_detail(
    source_id: str,
    dataset_id: str,
    resource_key: str = Query("", description="可选：物理资源 key；为空时按 dataset_id 查找"),
    limit: int = Query(10, ge=1, le=50, description="最近采集任务数量"),
    sample_limit: int = Query(10, ge=1, le=50, description="最新样本行数量"),
    mode: str = Query("", description="mock 或 real；为空时使用服务默认模式"),
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    result = await data_source_get_dataset_collection_detail(
        auth_token,
        source_id,
        dataset_id=dataset_id,
        resource_key=resource_key,
        limit=limit,
        sample_limit=sample_limit,
        mode=mode,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "获取采集详情失败"))
    return DataSourceDatasetCollectionDetailResponse(
        success=True,
        mode=str(result.get("mode") or mode or "mock"),
        source_id=str(result.get("source_id") or source_id),
        resource_key=str(result.get("resource_key") or resource_key or ""),
        dataset=result.get("dataset"),
        collection_stats=result.get("collection_stats") or {},
        jobs=result.get("jobs") or [],
        rows=result.get("rows") or [],
        count=int(result.get("count") or len(result.get("jobs") or [])),
        row_count=int(result.get("row_count") or len(result.get("rows") or [])),
        message=str(result.get("message") or ""),
    )


@router.get(
    "/data-sources/{source_id}/datasets/{dataset_id}/collection-records",
    response_model=DataSourceCollectionRecordsResponse,
)
async def list_dataset_collection_records(
    source_id: str,
    dataset_id: str,
    resource_key: str = Query("", description="可选：物理资源 key；为空时按 dataset_id 查找"),
    biz_date: str = Query("", description="可选：业务日期，用于筛选本次采集数据"),
    limit: int = Query(20, ge=1, le=1000, description="返回记录数量"),
    mode: str = Query("", description="mock 或 real；为空时使用服务默认模式"),
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    result = await data_source_list_collection_records(
        auth_token,
        source_id,
        dataset_id=dataset_id,
        resource_key=resource_key,
        biz_date=biz_date,
        limit=limit,
        mode=mode,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "获取采集记录失败"))
    records = [item for item in (result.get("records") or result.get("rows") or []) if isinstance(item, dict)]
    return DataSourceCollectionRecordsResponse(
        success=True,
        mode=str(result.get("mode") or mode or "mock"),
        source_id=str(result.get("source_id") or source_id),
        resource_key=str(result.get("resource_key") or resource_key or ""),
        dataset=result.get("dataset"),
        records=records,
        rows=records,
        count=int(result.get("count") or result.get("record_count") or len(records)),
        record_count=int(result.get("record_count") or result.get("count") or len(records)),
        message=str(result.get("message") or ""),
    )


@router.post("/data-sources/{source_id}/datasets/{dataset_id}/collection")
async def trigger_dataset_collection(
    source_id: str,
    dataset_id: str,
    body: DataSourceDatasetCollectionTriggerRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    result = await data_source_trigger_dataset_collection(
        auth_token,
        source_id,
        dataset_id=dataset_id,
        resource_key=body.resource_key,
        biz_date=body.biz_date or _default_collection_biz_date(),
        background=body.background,
        params=body.params,
        mode=body.mode,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "触发数据集采集失败"))
    return result


@router.post("/data-sources/{source_id}/preview", response_model=DataSourcePreviewResponse)
async def preview_data_source(
    source_id: str,
    body: DataSourcePreviewRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    result = await data_source_preview(auth_token, source_id, limit=body.limit, mode=body.mode)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "预览数据失败"))
    return DataSourcePreviewResponse(
        success=True,
        mode=str(result.get("mode") or body.mode or "mock"),
        source_id=source_id,
        count=int(result.get("count") or len(result.get("rows") or [])),
        rows=result.get("rows") or [],
        message=str(result.get("message") or ""),
    )


@router.get("/data-sources/{source_id}/datasets", response_model=DataSourceDatasetListResponse)
async def list_data_source_datasets(
    source_id: str,
    status: str = Query("", description="可选：按状态过滤"),
    include_deleted: bool = Query(False, description="是否包含 deleted"),
    keyword: str = Query("", description="关键词搜索"),
    schema_name: str = Query("", description="按 schema 名称过滤"),
    object_type: str = Query("", description="按对象类型过滤"),
    publish_status: str = Query("", description="按发布状态过滤"),
    business_object_type: str = Query("", description="按业务对象类型过滤"),
    verified_status: str = Query("", description="按验证状态过滤"),
    only_published: bool = Query(False, description="仅返回已发布数据集"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=200, description="每页数量"),
    sort_by: str = Query("-updated_at", description="排序字段，支持 -updated_at"),
    include_heavy: bool = Query(False, description="是否返回 schema_summary 等重字段"),
    limit: int = Query(500, ge=1, le=2000, description="兼容旧参数：返回条数"),
    mode: str = Query("", description="mock 或 real；为空时使用服务默认模式"),
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    result = await data_source_list_datasets(
        auth_token,
        source_id=source_id,
        status=status,
        include_deleted=include_deleted,
        keyword=keyword,
        schema_name=schema_name,
        object_type=object_type,
        publish_status=publish_status,
        business_object_type=business_object_type,
        verified_status=verified_status,
        only_published=only_published,
        page=page,
        page_size=page_size if page_size else limit,
        sort_by=sort_by,
        include_heavy=include_heavy,
        limit=limit,
        mode=mode,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=_safe_result_error(result, "获取数据集列表失败"))
    return DataSourceDatasetListResponse(
        success=True,
        mode=str(result.get("mode") or mode or "mock"),
        source_id=source_id,
        count=int(result.get("count") or len(result.get("datasets") or [])),
        total=int(result.get("total") or result.get("count") or len(result.get("datasets") or [])),
        page=int(result.get("page") or page),
        page_size=int(result.get("page_size") or page_size),
        datasets=result.get("datasets") or [],
        dataset_summary=result.get("dataset_summary") or {},
        source_summary=result.get("source_summary") or {},
        health_summary=result.get("health_summary") or {},
        message=str(result.get("message") or ""),
    )


@router.get("/data-sources/{source_id}/datasets/{dataset_id}", response_model=DataSourceDatasetGetResponse)
async def get_data_source_dataset(
    source_id: str,
    dataset_id: str,
    mode: str = Query("", description="mock 或 real；为空时使用服务默认模式"),
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    result = await data_source_get_dataset(
        auth_token,
        dataset_id=dataset_id,
        source_id=source_id,
        mode=mode,
    )
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=_safe_result_error(result, "数据集不存在"))
    return DataSourceDatasetGetResponse(
        success=True,
        mode=str(result.get("mode") or mode or "mock"),
        source_id=source_id,
        dataset=result.get("dataset"),
        source_summary=result.get("source_summary") or {},
        health_summary=result.get("health_summary") or {},
        message=str(result.get("message") or ""),
    )


@router.post("/data-sources/{source_id}/datasets", response_model=DataSourceDatasetUpsertResponse)
async def upsert_data_source_dataset(
    source_id: str,
    body: DataSourceDatasetUpsertRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    payload = body.model_dump(exclude_none=True, exclude={"mode"})
    result = await data_source_upsert_dataset(
        auth_token,
        source_id,
        payload,
        mode=body.mode,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=_safe_result_error(result, "更新数据集失败"))
    return DataSourceDatasetUpsertResponse(
        success=True,
        mode=str(result.get("mode") or body.mode or "mock"),
        source_id=source_id,
        dataset=result.get("dataset"),
        source_summary=result.get("source_summary") or {},
        message=str(result.get("message") or ""),
    )


@router.post("/data-sources/{source_id}/datasets/{dataset_id}/disable", response_model=DataSourceDatasetUpsertResponse)
async def disable_data_source_dataset(
    source_id: str,
    dataset_id: str,
    body: DataSourceDatasetDisableRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    result = await data_source_disable_dataset(
        auth_token,
        dataset_id,
        reason=body.reason,
        mode=body.mode,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=_safe_result_error(result, "停用数据集失败"))
    return DataSourceDatasetUpsertResponse(
        success=True,
        mode=str(result.get("mode") or body.mode or "mock"),
        source_id=source_id,
        dataset=result.get("dataset"),
        source_summary=result.get("source_summary") or {},
        message=str(result.get("message") or "数据集已停用"),
    )


@router.post("/data-sources/{source_id}/datasets/{dataset_id}/publish", response_model=DataSourceDatasetUpsertResponse)
async def publish_data_source_dataset(
    source_id: str,
    dataset_id: str,
    body: DataSourceDatasetPublishRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    payload = body.model_dump(exclude_none=True, exclude={"mode", "dataset_code", "resource_key"})
    result = await data_source_publish_dataset(
        auth_token,
        dataset_id=dataset_id,
        source_id=source_id,
        dataset_code=body.dataset_code,
        resource_key=body.resource_key,
        payload=payload,
        mode=body.mode,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=_safe_result_error(result, "发布数据集失败"))
    return DataSourceDatasetUpsertResponse(
        success=True,
        mode=str(result.get("mode") or body.mode or "mock"),
        source_id=source_id,
        dataset=result.get("dataset"),
        source_summary=result.get("source_summary") or {},
        message=str(result.get("message") or "数据集已发布"),
    )


@router.post("/data-sources/{source_id}/datasets/{dataset_id}/unpublish", response_model=DataSourceDatasetUpsertResponse)
async def unpublish_data_source_dataset(
    source_id: str,
    dataset_id: str,
    body: DataSourceDatasetUnpublishRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    payload = body.model_dump(exclude_none=True, exclude={"mode", "dataset_code", "resource_key"})
    result = await data_source_unpublish_dataset(
        auth_token,
        dataset_id=dataset_id,
        source_id=source_id,
        dataset_code=body.dataset_code,
        resource_key=body.resource_key,
        payload=payload,
        mode=body.mode,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=_safe_result_error(result, "取消发布失败"))
    return DataSourceDatasetUpsertResponse(
        success=True,
        mode=str(result.get("mode") or body.mode or "mock"),
        source_id=source_id,
        dataset=result.get("dataset"),
        source_summary=result.get("source_summary") or {},
        message=str(result.get("message") or "数据集已取消发布"),
    )


@router.post("/data-sources/{source_id}/datasets/{dataset_id}/semantic-profile", response_model=DataSourceDatasetUpsertResponse)
async def refresh_data_source_dataset_semantic_profile(
    source_id: str,
    dataset_id: str,
    body: DataSourceDatasetSemanticRefreshRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    result = await data_source_refresh_dataset_semantic_profile(
        auth_token,
        dataset_id=dataset_id,
        source_id=source_id,
        dataset_code=body.dataset_code,
        resource_key=body.resource_key,
        sample_limit=body.sample_limit,
        mode=body.mode,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=_safe_result_error(result, "刷新数据集语义层失败"))
    return DataSourceDatasetUpsertResponse(
        success=True,
        mode=str(result.get("mode") or body.mode or "mock"),
        source_id=source_id,
        dataset=result.get("dataset"),
        source_summary=result.get("source_summary") or {},
        message=str(result.get("message") or "数据集语义层已刷新"),
    )


@router.patch("/data-sources/{source_id}/datasets/{dataset_id}/semantic-profile", response_model=DataSourceDatasetUpsertResponse)
async def update_data_source_dataset_semantic_profile(
    source_id: str,
    dataset_id: str,
    body: DataSourceDatasetSemanticUpdateRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    result = await data_source_update_dataset_semantic_profile(
        auth_token,
        dataset_id=dataset_id,
        source_id=source_id,
        dataset_code=body.dataset_code,
        resource_key=body.resource_key,
        semantic_profile=body.semantic_profile,
        business_name=body.business_name,
        business_description=body.business_description,
        key_fields=body.key_fields,
        field_label_map=body.field_label_map,
        fields=body.fields,
        status=body.status,
        mode=body.mode,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=_safe_result_error(result, "更新数据集语义层失败"))
    return DataSourceDatasetUpsertResponse(
        success=True,
        mode=str(result.get("mode") or body.mode or "mock"),
        source_id=source_id,
        dataset=result.get("dataset"),
        source_summary=result.get("source_summary") or {},
        message=str(result.get("message") or "数据集语义层已更新"),
    )


@router.post("/data-sources/{source_id}/discover", response_model=DataSourceDiscoverResponse)
async def discover_data_source_datasets(
    source_id: str,
    body: DataSourceDiscoverRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    try:
        discover_inputs = await _resolve_discover_inputs(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        logger.warning("load api document failed: %s", exc)
        raise HTTPException(status_code=400, detail="加载文档失败，请检查文档地址是否可访问") from exc
    except Exception as exc:
        logger.error("resolve discover inputs failed", exc_info=True)
        raise HTTPException(status_code=400, detail="API 数据集生成失败，请检查文档或 endpoint 配置") from exc

    result = await data_source_discover_datasets(
        auth_token,
        source_id,
        persist=body.persist,
        limit=body.limit,
        offset=body.offset,
        schema_whitelist=body.schema_whitelist,
        target_resource_keys=body.target_resource_keys,
        discover_mode=str(discover_inputs.get("discover_mode") or body.discover_mode),
        openapi_url=str(discover_inputs.get("openapi_url") or body.openapi_url),
        openapi_spec=discover_inputs.get("openapi_spec"),
        manual_endpoints=discover_inputs.get("manual_endpoints"),
        mode=body.mode,
        connection_config=body.connection_config,
        auth_config=body.auth_config,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=_safe_result_error(result, "发现数据集失败"))
    return DataSourceDiscoverResponse(
        success=True,
        mode=str(result.get("mode") or body.mode or "mock"),
        source_id=source_id,
        provider_code=str(result.get("provider_code") or ""),
        datasets=result.get("datasets") or [],
        dataset_count=int(result.get("dataset_count") or len(result.get("datasets") or [])),
        persist=bool(result.get("persist", body.persist)),
        persisted_count=int(result.get("persisted_count") or 0),
        scan_summary=result.get("scan_summary") or {},
        discover_summary=result.get("discover_summary") or {},
        message=str(result.get("message") or ""),
    )


@router.post("/data-sources/{source_id}/import-openapi", response_model=DataSourceDiscoverResponse)
async def import_data_source_openapi(
    source_id: str,
    body: DataSourceImportOpenAPIRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    result = await data_source_import_openapi(
        auth_token,
        source_id,
        openapi_url=body.openapi_url,
        openapi_spec=body.openapi_spec,
        persist=body.persist,
        mode=body.mode,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=_safe_result_error(result, "导入 OpenAPI 数据集失败"))
    return DataSourceDiscoverResponse(
        success=True,
        mode=str(result.get("mode") or body.mode or "mock"),
        source_id=source_id,
        provider_code=str(result.get("provider_code") or ""),
        datasets=result.get("datasets") or [],
        dataset_count=int(result.get("dataset_count") or len(result.get("datasets") or [])),
        persist=bool(result.get("persist", body.persist)),
        persisted_count=int(result.get("persisted_count") or 0),
        message=str(result.get("message") or ""),
    )


@router.get("/data-sources/{source_id}/events", response_model=DataSourceEventsResponse)
async def list_data_source_events(
    source_id: str,
    sync_job_id: str = Query("", description="可选：按 sync_job_id 过滤"),
    event_level: str = Query("", description="可选：按事件等级过滤"),
    limit: int = Query(200, ge=1, le=1000, description="返回条数"),
    mode: str = Query("", description="mock 或 real；为空时使用服务默认模式"),
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    result = await data_source_list_events(
        auth_token,
        source_id=source_id,
        sync_job_id=sync_job_id,
        event_level=event_level,
        limit=limit,
        mode=mode,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=_safe_result_error(result, "获取健康事件失败"))
    return DataSourceEventsResponse(
        success=True,
        mode=str(result.get("mode") or mode or "mock"),
        source_id=source_id,
        count=int(result.get("count") or len(result.get("events") or [])),
        events=result.get("events") or [],
        message=str(result.get("message") or ""),
    )


@router.post("/data-sources/preflight", response_model=DataSourcePreflightResponse)
async def preflight_rule_binding(
    body: DataSourcePreflightRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    binding_scope = _resolve_binding_scope(body.task_code, body.binding_scope)
    binding_code = str(body.binding_code or body.rule_code or "").strip()
    if not binding_scope:
        raise HTTPException(status_code=400, detail="任务类型无效，仅支持 proc 或 recon")
    if not binding_code:
        raise HTTPException(status_code=400, detail="规则编码不能为空")

    result = await data_source_preflight_rule_binding(
        auth_token,
        binding_scope=binding_scope,
        binding_code=binding_code,
        stale_after_minutes=body.stale_after_minutes,
        mode=body.mode,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=_safe_result_error(result, "任务前检查失败"))
    return DataSourcePreflightResponse(
        success=True,
        mode=str(result.get("mode") or body.mode or "mock"),
        ready=bool(result.get("ready")),
        binding_scope=str(result.get("binding_scope") or binding_scope),
        binding_code=str(result.get("binding_code") or binding_code),
        summary=result.get("summary") or {},
        preflight=result.get("preflight") or {},
        message=str(result.get("message") or ""),
    )
