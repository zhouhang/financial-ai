"""HTTP API source connector."""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import urlsplit

import requests

from connectors.base import BaseDataSourceConnector

logger = logging.getLogger(__name__)

_DATASET_CODE_PATTERN = re.compile(r"[^a-z0-9_]+")
_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}
_AUTH_TEMPLATE_PATTERN = re.compile(r"\{([^{}]+)\}")


def _sanitize_dataset_code(*parts: str) -> str:
    text = "_".join(part.strip().lower() for part in parts if part and part.strip())
    text = _DATASET_CODE_PATTERN.sub("_", text).strip("_")
    if not text:
        return "api_dataset"
    return text[:120]


def _normalize_method(value: Any) -> str:
    method = str(value or "GET").strip().upper()
    return method if method else "GET"


def _normalize_path(value: Any) -> str:
    path = str(value or "").strip()
    if not path:
        return "/"
    return path if path.startswith("/") else f"/{path}"


def _normalize_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _extract_value_by_path(payload: Any, path: str) -> Any:
    current = payload
    if not path:
        return current
    for raw_part in path.split("."):
        part = raw_part.strip()
        if not part:
            continue
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        if isinstance(current, list) and part.isdigit():
            index = int(part)
            if 0 <= index < len(current):
                current = current[index]
                continue
        return None
    return current


def _is_absolute_url(value: Any) -> bool:
    raw = str(value or "").strip()
    return raw.startswith("http://") or raw.startswith("https://")


def _render_auth_value_template(payload: Any, template: str) -> str:
    raw_template = str(template or "").strip()
    if not raw_template:
        return ""

    if _AUTH_TEMPLATE_PATTERN.search(raw_template):
        def _replace(match: re.Match[str]) -> str:
            extracted = _extract_value_by_path(payload, match.group(1).strip())
            if extracted is None:
                return ""
            if isinstance(extracted, (dict, list)):
                raise ValueError("Header 取值对应的响应路径不是字符串")
            return str(extracted)

        return _AUTH_TEMPLATE_PATTERN.sub(_replace, raw_template).strip()

    extracted = _extract_value_by_path(payload, raw_template)
    if extracted is None:
        return raw_template
    if isinstance(extracted, (dict, list)):
        raise ValueError("Header 取值对应的响应路径不是字符串")
    return str(extracted).strip()


def _extract_schema_columns(schema: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(schema, dict):
        return []
    if schema.get("type") != "object":
        return []
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return []
    required_set = set(schema.get("required") or [])
    columns: list[dict[str, Any]] = []
    for field_name, field_schema in properties.items():
        if not isinstance(field_schema, dict):
            field_schema = {}
        columns.append(
            {
                "name": str(field_name),
                "data_type": str(field_schema.get("type") or "unknown"),
                "nullable": field_name not in required_set,
                "description": str(field_schema.get("description") or ""),
            }
        )
    return columns


def _resolve_response_schema(operation: dict[str, Any]) -> dict[str, Any] | None:
    responses = operation.get("responses")
    if not isinstance(responses, dict):
        return None
    for status_code in ("200", "201", "default"):
        response = responses.get(status_code)
        if not isinstance(response, dict):
            continue
        content = response.get("content")
        if not isinstance(content, dict):
            continue
        for media_type in ("application/json", "application/*+json"):
            media = content.get(media_type)
            if isinstance(media, dict) and isinstance(media.get("schema"), dict):
                return media["schema"]
    return None


class ApiConnector(BaseDataSourceConnector):
    source_kind = "api"
    execution_mode = "deterministic"

    @property
    def capabilities(self) -> list[str]:
        return ["test", "discover_datasets", "list_datasets", "list_events"]

    def _resolved_connection_config(self) -> dict[str, Any]:
        connection_config = dict(self.ctx.config.get("connection_config") or {})
        auth_config = dict(self.ctx.config.get("auth_config") or {})

        auth_mode = str(connection_config.get("auth_mode") or "").strip().lower()
        if not auth_mode:
            auth_mode = "request" if connection_config.get("auth_request_url") else "none"
            connection_config["auth_mode"] = auth_mode

        credential_kind = str(connection_config.get("credential_kind") or "").strip().lower()
        if not credential_kind:
            legacy_auth_type = str(connection_config.get("auth_type") or auth_config.get("auth_type") or "").strip().lower()
            if legacy_auth_type in {"bearer", "api_key", "basic"}:
                credential_kind = legacy_auth_type
            else:
                credential_kind = "bearer"
            connection_config["credential_kind"] = credential_kind

        connection_config["auth_request_configured"] = bool(
            connection_config.get("auth_request_url")
            or auth_config.get("auth_request_params")
            or auth_config.get("auth_request_json_payload")
            or auth_config.get("auth_request_payload")
            or auth_config.get("auth_request_headers")
            or connection_config.get("auth_type")
            or auth_config.get("token")
            or auth_config.get("api_key")
            or auth_config.get("basic_auth_header")
            or connection_config.get("auth_apply_header_name")
            or connection_config.get("auth_apply_value_template")
        )
        return connection_config

    def _build_legacy_headers(self, cfg: dict[str, Any]) -> dict[str, str]:
        headers: dict[str, str] = {}
        auth_type = str(cfg.get("auth_type") or "none").strip().lower()
        if auth_type == "bearer":
            token = str(cfg.get("token") or self.ctx.config.get("auth_config", {}).get("token") or "").strip()
            if token:
                headers["Authorization"] = f"Bearer {token}"
        elif auth_type == "api_key":
            api_key = str(cfg.get("api_key") or self.ctx.config.get("auth_config", {}).get("api_key") or "").strip()
            api_key_header = (
                str(
                    cfg.get("api_key_header")
                    or self.ctx.config.get("auth_config", {}).get("api_key_header")
                    or "X-API-Key"
                ).strip()
                or "X-API-Key"
            )
            if api_key:
                headers[api_key_header] = api_key
        elif auth_type == "basic":
            basic_header = str(
                cfg.get("basic_auth_header") or self.ctx.config.get("auth_config", {}).get("basic_auth_header") or ""
            ).strip()
            if basic_header:
                headers["Authorization"] = basic_header
        return headers

    def _request_auth_headers(self, cfg: dict[str, Any]) -> dict[str, str]:
        auth_url = str(cfg.get("auth_request_url") or "").strip()
        if not auth_url:
            return {}

        auth_request_method = _normalize_method(cfg.get("auth_request_method") or "POST")
        auth_request_payload_type = str(cfg.get("auth_request_payload_type") or "json").strip().lower()
        if auth_request_payload_type not in {"json", "params", "form"}:
            auth_request_payload_type = "json"

        auth_config = dict(self.ctx.config.get("auth_config") or {})
        request_headers = {
            str(key).strip(): str(value)
            for key, value in _normalize_object(auth_config.get("auth_request_headers")).items()
            if str(key).strip()
        }
        request_params = _normalize_object(
            auth_config.get("auth_request_params") or auth_config.get("auth_request_payload")
        )
        request_json_payload = _normalize_object(auth_config.get("auth_request_json_payload"))

        request_kwargs: dict[str, Any] = {
            "headers": request_headers,
            "timeout": 5.0,
        }
        if auth_request_method == "GET":
            request_kwargs["params"] = request_params
        elif auth_request_payload_type == "params":
            request_kwargs["params"] = request_params
        elif auth_request_payload_type == "form":
            request_kwargs["data"] = request_params
        else:
            request_kwargs["json"] = request_json_payload

        try:
            response = requests.request(auth_request_method, auth_url, **request_kwargs)
            response.raise_for_status()
        except Exception as exc:
            raise ValueError(f"鉴权请求失败: {exc}") from exc

        response_payload: Any
        try:
            response_payload = response.json()
        except Exception:
            response_payload = response.text

        header_name = str(cfg.get("auth_apply_header_name") or "").strip()
        if not header_name:
            raise ValueError("缺少写入 Header 名称")
        header_value_template = str(cfg.get("auth_apply_value_template") or "").strip()
        if not header_value_template:
            raise ValueError("缺少 Header 取值配置")
        credential_text = _render_auth_value_template(response_payload, header_value_template)
        if not credential_text:
            raise ValueError("未从鉴权响应中提取到凭证")
        return {header_name: credential_text}

    def _build_headers(self, cfg: dict[str, Any]) -> dict[str, str]:
        auth_mode = str(cfg.get("auth_mode") or "none").strip().lower()
        if auth_mode == "request" or cfg.get("auth_request_url"):
            return self._request_auth_headers(cfg)
        return self._build_legacy_headers(cfg)

    def test_connection(self, arguments):
        cfg = self._resolved_connection_config()
        auth_mode = str(cfg.get("auth_mode") or "none").strip().lower()
        headers: dict[str, str]
        try:
            headers = self._build_headers(cfg)
        except ValueError as exc:
            return {
                "success": False,
                "source_id": self.ctx.source_id,
                "error": str(exc),
                "message": str(exc),
            }

        if auth_mode == "request" or cfg.get("auth_request_url"):
            return {
                "success": True,
                "source_id": self.ctx.source_id,
                "provider_code": self.ctx.provider_code,
                "message": "鉴权请求校验通过",
            }

        base_url = str(cfg.get("base_url") or "").strip()
        if not base_url:
            return {
                "success": True,
                "source_id": self.ctx.source_id,
                "provider_code": self.ctx.provider_code,
                "message": "当前无需鉴权，也未配置固定 Base URL",
            }

        test_url = base_url
        try:
            response = requests.get(
                test_url,
                headers=headers,
                timeout=5.0,
            )
        except Exception as exc:
            logger.error("api test connection failed: %s", exc, exc_info=True)
            return {
                "success": False,
                "source_id": self.ctx.source_id,
                "error": str(exc),
                "message": "API 连通性检查失败",
            }

        if response.status_code >= 500:
            return {
                "success": False,
                "source_id": self.ctx.source_id,
                "error": f"HTTP {response.status_code}",
                "message": "API 服务端返回异常状态码",
            }
        return {
            "success": True,
            "source_id": self.ctx.source_id,
            "provider_code": self.ctx.provider_code,
            "status_code": int(response.status_code),
            "message": "API 连通性检查通过",
        }

    def discover_datasets(self, arguments: dict[str, Any]) -> dict[str, Any]:
        cfg = self._resolved_connection_config()
        mode = str(arguments.get("discover_mode") or "").strip().lower() or "auto"
        if mode not in {"auto", "openapi", "manual"}:
            mode = "auto"

        datasets: list[dict[str, Any]] = []
        openapi_spec = self._load_openapi_spec(arguments)
        base_url = str(cfg.get("base_url") or self._resolve_openapi_base_url(openapi_spec) or "").strip()
        manual_endpoints = self._load_manual_endpoints(arguments)

        if mode in {"auto", "openapi"} and openapi_spec:
            datasets.extend(self._build_openapi_datasets(openapi_spec, base_url=base_url))
        if mode in {"auto", "manual"} and manual_endpoints:
            datasets.extend(self._build_manual_datasets(manual_endpoints, base_url=base_url))

        # auto 模式下，如果没有 openapi 且没有 manual，给出清晰错误。
        if not datasets and mode == "auto":
            return {
                "success": False,
                "source_id": self.ctx.source_id,
                "provider_code": self.ctx.provider_code,
                "datasets": [],
                "dataset_count": 0,
                "error": "missing_discovery_inputs",
                "message": "未提供可解析的 OpenAPI 文档或手工 endpoint 定义",
            }

        if not datasets:
            return {
                "success": False,
                "source_id": self.ctx.source_id,
                "provider_code": self.ctx.provider_code,
                "datasets": [],
                "dataset_count": 0,
                "error": "empty_discovery_result",
                "message": "未发现可用 API 数据集定义",
            }

        deduped: dict[str, dict[str, Any]] = {}
        for item in datasets:
            deduped[str(item.get("dataset_code") or "")] = item
        final_datasets = list(deduped.values())
        return {
            "success": True,
            "source_id": self.ctx.source_id,
            "provider_code": self.ctx.provider_code,
            "datasets": final_datasets,
            "dataset_count": len(final_datasets),
            "message": f"已发现 {len(final_datasets)} 个 API 数据集",
        }

    def _resolve_openapi_base_url(self, spec: dict[str, Any] | None) -> str:
        if not isinstance(spec, dict):
            return ""
        servers = spec.get("servers")
        if not isinstance(servers, list):
            return ""
        for item in servers:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            if url:
                return url
        return ""

    def _load_openapi_spec(self, arguments: dict[str, Any]) -> dict[str, Any] | None:
        explicit = arguments.get("openapi_spec")
        if isinstance(explicit, dict):
            return explicit
        if isinstance(explicit, str) and explicit.strip():
            try:
                parsed = json.loads(explicit)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                try:
                    import yaml  # type: ignore

                    parsed_yaml = yaml.safe_load(explicit)
                    if isinstance(parsed_yaml, dict):
                        return parsed_yaml
                except Exception:
                    logger.warning("openapi_spec string is neither valid JSON nor YAML, ignore")

        openapi_url = str(arguments.get("openapi_url") or "").strip()
        if not openapi_url:
            runtime_config = self.ctx.config.get("runtime_config") or {}
            openapi_url = str((runtime_config or {}).get("openapi_url") or "").strip()
        if not openapi_url:
            return None

        timeout_seconds = float(arguments.get("openapi_timeout_seconds") or 8.0)
        response = requests.get(openapi_url, timeout=timeout_seconds)
        response.raise_for_status()
        body_text = response.text
        try:
            loaded_json = response.json()
            if isinstance(loaded_json, dict):
                return loaded_json
        except Exception:
            pass
        try:
            import yaml  # type: ignore

            loaded_yaml = yaml.safe_load(body_text)
            if isinstance(loaded_yaml, dict):
                return loaded_yaml
        except Exception as exc:
            logger.warning("openapi_url response parse failed: %s", exc)
        return None

    def _load_manual_endpoints(self, arguments: dict[str, Any]) -> list[dict[str, Any]]:
        raw = arguments.get("manual_endpoints")
        if raw is None:
            runtime_config = self.ctx.config.get("runtime_config") or {}
            raw = (runtime_config or {}).get("manual_endpoints")
        if not isinstance(raw, list):
            return []
        result: list[dict[str, Any]] = []
        for item in raw:
            if isinstance(item, dict):
                result.append(item)
        return result

    def _build_openapi_datasets(
        self,
        spec: dict[str, Any],
        *,
        base_url: str,
    ) -> list[dict[str, Any]]:
        paths = spec.get("paths")
        if not isinstance(paths, dict):
            return []

        datasets: list[dict[str, Any]] = []
        for raw_path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue
            path = _normalize_path(raw_path)
            for method, operation in path_item.items():
                if method.lower() not in _HTTP_METHODS or not isinstance(operation, dict):
                    continue
                method_upper = method.upper()
                operation_id = str(operation.get("operationId") or "").strip()
                dataset_code = _sanitize_dataset_code(operation_id or f"{method_lower(method)}_{path}")
                dataset_name = str(operation.get("summary") or operation.get("description") or "").strip()
                if not dataset_name:
                    dataset_name = f"{method_upper} {path}"

                response_schema = _resolve_response_schema(operation)
                columns = _extract_schema_columns(response_schema)
                parameters = operation.get("parameters")
                parameter_defs = parameters if isinstance(parameters, list) else []
                datasets.append(
                    {
                        "dataset_code": dataset_code,
                        "dataset_name": dataset_name[:255],
                        "resource_key": operation_id or f"{method_upper} {path}",
                        "dataset_kind": "api_endpoint",
                        "origin_type": "imported_openapi",
                        "extract_config": {
                            "base_url": base_url,
                            "url": f"{base_url.rstrip('/')}{path}" if base_url else "",
                            "path": path,
                            "method": method_upper,
                            "operation_id": operation_id,
                            "parameters": parameter_defs,
                        },
                        "schema_summary": {
                            "source": "openapi",
                            "columns": columns,
                        },
                        "sync_strategy": {"mode": "full"},
                        "meta": {"discovered_by": "api_openapi_import"},
                    }
                )
        return datasets

    def _build_manual_datasets(
        self,
        manual_endpoints: list[dict[str, Any]],
        *,
        base_url: str,
    ) -> list[dict[str, Any]]:
        datasets: list[dict[str, Any]] = []
        for item in manual_endpoints:
            raw_endpoint = str(item.get("path") or item.get("endpoint") or item.get("url") or "").strip()
            absolute_url = raw_endpoint if _is_absolute_url(raw_endpoint) else ""
            path = _normalize_path(urlsplit(absolute_url).path if absolute_url else raw_endpoint)
            method_upper = _normalize_method(item.get("method"))
            dataset_name = str(item.get("name") or item.get("dataset_name") or "").strip()
            if not dataset_name:
                dataset_name = f"{method_upper} {path}"
            dataset_code = str(item.get("dataset_code") or "").strip()
            if not dataset_code:
                dataset_code = _sanitize_dataset_code(method_upper, path)
            request_param_type = str(item.get("request_param_type") or "").strip().lower()
            request_params = item.get("request_params") if isinstance(item.get("request_params"), dict) else {}
            query = item.get("query") if isinstance(item.get("query"), dict) else {}
            body = item.get("body") if isinstance(item.get("body"), dict) else {}
            if request_param_type == "json" and request_params:
                body = request_params
            elif request_param_type == "params" and request_params:
                query = request_params
            cursor_field = str(item.get("cursor_field") or "").strip()
            sync_strategy: dict[str, Any] = {"mode": "full"}
            if cursor_field:
                sync_strategy = {"mode": "incremental", "cursor_field": cursor_field}
            columns = []
            if isinstance(item.get("columns"), list):
                columns = [column for column in item.get("columns") if isinstance(column, dict)]

            datasets.append(
                {
                    "dataset_code": dataset_code,
                    "dataset_name": dataset_name[:255],
                    "resource_key": str(item.get("resource_key") or f"{method_upper} {path}"),
                    "dataset_kind": "api_endpoint",
                    "origin_type": "manual",
                    "extract_config": {
                        "base_url": base_url,
                        "url": absolute_url,
                        "path": path,
                        "method": method_upper,
                        "query": query,
                        "headers": item.get("headers") if isinstance(item.get("headers"), dict) else {},
                        "body": body,
                        "response_data_path": str(item.get("response_data_path") or "").strip(),
                    },
                    "schema_summary": {
                        "source": "manual",
                        "columns": columns,
                    },
                    "sync_strategy": sync_strategy,
                    "meta": {"discovered_by": "api_manual_config"},
                }
            )
        return datasets


def method_lower(method: str) -> str:
    return str(method or "").strip().lower()
