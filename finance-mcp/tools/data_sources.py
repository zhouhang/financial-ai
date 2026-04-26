"""Unified data source MCP tools.

Phase-1 goals:
- Persist data sources / configs / sync jobs in PostgreSQL
- Keep `platform_*` tools intact and reuse them for OAuth platforms
- Support published datasets and asset-layer collection records for deterministic syncs
- Reserve browser / desktop_cli for future agent-assisted execution
"""

from __future__ import annotations

import asyncio
import inspect
import hashlib
import json
import logging
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg2.extras
import pandas as pd
import requests
from dotenv import dotenv_values
from mcp import Tool

from auth import db as auth_db
from auth.jwt_utils import get_user_from_token
from connectors.factory import build_connector
from security_utils import UPLOAD_ROOT
from tools.platform_connections import handle_tool_call as handle_platform_tool_call

logger = logging.getLogger("tools.data_sources")
CONNECTOR_SYNC_TIMEOUT_SECONDS = int(os.getenv("CONNECTOR_SYNC_TIMEOUT_SECONDS", "180"))

SOURCE_KINDS = {
    "platform_oauth",
    "database",
    "api",
    "file",
    "browser",
    "desktop_cli",
}

DOMAIN_TYPES = {
    "ecommerce",
    "bank",
    "finance_mid",
    "erp",
    "supplier",
    "internal_business",
}

CONFIG_TYPES = ("connection", "extract", "mapping", "runtime")
AGENT_ASSISTED_KINDS = {"browser", "desktop_cli"}
HEALTH_STATUSES = {"unknown", "healthy", "warning", "error", "auth_expired", "disabled"}
DATASET_ORIGIN_TYPES = {"fixed", "discovered", "imported_openapi", "manual"}
AUTO_DISCOVER_DATASET_LIMIT = 300
AUTO_SAMPLE_DATASET_LIMIT = 20
AUTO_SAMPLE_ROW_LIMIT = 10
SEMANTIC_STATUS_VALUES = {"generated_basic", "generated_with_samples", "llm_generated", "manual_updated"}
SEMANTIC_FIELD_CONFIDENCE_THRESHOLD = 0.75
SEMANTIC_SAMPLE_ROW_LIMIT = 10
PUBLISH_STATUS_VALUES = {"published", "unpublished", "draft", "archived"}
VERIFIED_STATUS_VALUES = {"verified", "unverified", "rejected", "unknown"}
DATASET_CANDIDATE_SCENES = {"recon", "proc", "insight"}
DATASET_CANDIDATE_ROLES = {"left", "right", "source", "target"}
DATASET_CANDIDATE_BATCH_SIZE = 200
DATASET_CANDIDATE_MAX_SCAN_PAGES = 200
_SEMANTIC_ENV_CACHE: dict[str, str] | None = None


def _is_hologres_source(source_row: dict[str, Any] | None) -> bool:
    provider_code = str((source_row or {}).get("provider_code") or "").strip().lower()
    return provider_code in {"hologres", "holo"}


_CANDIDATE_CONTRACT_LIBRARY: dict[str, dict[str, Any]] = {
    "business_order": {
        "label": "业务订单",
        "hint_aliases": ("业务订单", "订单", "销售订单", "采购订单", "出库单"),
        "business_object_types": ("business_order", "sales_order", "order", "purchase_order"),
        "grains": ("order",),
        "required_field_alias_groups": (
            ("订单号", "订单编号", "商户订单号", "order_id", "orderid", "biz_order_no"),
            ("订单金额", "实付金额", "金额", "order_amount", "pay_amount", "amount", "trade_amount"),
            ("业务日期", "订单时间", "下单时间", "创建时间", "biz_date", "order_date", "created_at"),
        ),
    },
    "payment_bill": {
        "label": "支付账单",
        "hint_aliases": ("支付", "流水", "银行", "交易单", "收款", "到账"),
        "business_object_types": ("payment_bill", "bank_statement", "statement", "payment_statement"),
        "grains": ("payment", "trade"),
        "required_field_alias_groups": (
            ("支付单号", "交易单号", "流水号", "payment_id", "pay_no", "trade_no", "transaction_id"),
            ("支付金额", "流水金额", "到账金额", "pay_amount", "trade_amount", "bank_amount", "amount"),
            ("支付时间", "交易时间", "到账时间", "pay_time", "trade_time", "transaction_time", "bank_time"),
        ),
    },
    "platform_order": {
        "label": "平台订单",
        "hint_aliases": ("平台订单", "店铺订单", "电商订单", "淘宝订单", "抖店订单"),
        "business_object_types": ("platform_order", "shop_order", "trade_order"),
        "grains": ("order",),
        "required_field_alias_groups": (
            ("平台订单号", "店铺订单号", "trade_order_id", "platform_order_id", "tid"),
            ("订单金额", "支付金额", "实付金额", "order_amount", "pay_amount", "amount"),
            ("下单时间", "订单时间", "创建时间", "order_time", "created_at", "pay_time"),
        ),
    },
    "settlement_bill": {
        "label": "结算单",
        "hint_aliases": ("结算", "结算单", "结算账单", "结算明细"),
        "business_object_types": ("settlement_bill", "settlement_statement", "settlement"),
        "grains": ("settlement", "daily_summary"),
        "required_field_alias_groups": (
            ("结算单号", "结算编号", "settlement_id", "settle_no"),
            ("结算金额", "应结金额", "settlement_amount", "settle_amount", "amount"),
            ("结算时间", "结算日期", "settlement_time", "settle_date", "biz_date"),
        ),
    },
}

_FIELD_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")
_FIELD_CAMEL_BOUNDARY = re.compile(r"([a-z0-9])([A-Z])")
_SEMANTIC_ROLE_HINTS: dict[str, tuple[tuple[str, ...], str, str, str]] = {
    "order_no": (("order", "id"), "identifier", "订单号", "订单唯一编号"),
    "trade_no": (("trade", "id"), "identifier", "交易号", "交易流水编号"),
    "biz_date": (("biz", "date"), "date", "业务日期", "业务发生日期"),
    "settle_date": (("settle", "date"), "date", "结算日期", "结算发生日期"),
    "created_at": (("created", "at"), "datetime", "创建时间", "记录创建时间"),
    "updated_at": (("updated", "at"), "datetime", "更新时间", "记录更新时间"),
    "pay_amount": (("pay", "amount"), "amount", "支付金额", "支付相关金额"),
    "order_amount": (("order", "amount"), "amount", "订单金额", "订单相关金额"),
    "total_amount": (("total", "amount"), "amount", "总金额", "汇总金额"),
    "refund_amount": (("refund", "amount"), "amount", "退款金额", "退款相关金额"),
    "bank_amount": (("bank", "amount"), "amount", "银行金额", "银行侧金额"),
    "quantity": (("quantity",), "number", "数量", "数量字段"),
    "status": (("status",), "status", "状态", "状态字段"),
    "shop_name": (("shop", "name"), "dimension", "店铺名称", "店铺名称"),
    "shop_id": (("shop", "id"), "identifier", "店铺ID", "店铺唯一标识"),
}
_BUSINESS_NAME_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("bank", "flow"), "银行流水"),
    (("bank", "statement"), "银行流水"),
    (("refund",), "退款明细"),
    (("settle",), "结算明细"),
    (("recon",), "对账明细"),
    (("order", "pay"), "订单支付明细"),
    (("order",), "订单明细"),
    (("trade",), "交易明细"),
    (("inventory",), "库存明细"),
    (("stock",), "库存明细"),
    (("invoice",), "发票明细"),
]
_SEMANTIC_FIELD_SOURCE_VALUES = {"rule_fallback", "llm_generated", "manual_confirmed", "manual_updated"}
_FIELD_TOKEN_LABELS: dict[str, str] = {
    "account": "账户",
    "actual": "实付",
    "alipay": "支付宝",
    "api": "接口",
    "bank": "银行",
    "base": "基础",
    "batch": "批次",
    "biz": "业务",
    "buyer": "买家",
    "cash": "现金",
    "channel": "渠道",
    "code": "编码",
    "company": "公司",
    "coupon": "优惠券",
    "create": "创建",
    "created": "创建",
    "crm": "CRM",
    "customer": "客户",
    "date": "日期",
    "discount": "优惠",
    "fee": "费用",
    "goods": "商品",
    "id": "ID",
    "invoice": "发票",
    "item": "明细",
    "jd": "京东",
    "merchant": "商户",
    "money": "金额",
    "name": "名称",
    "no": "编号",
    "number": "编号",
    "open": "开放",
    "openid": "OpenID",
    "order": "订单",
    "paid": "已付",
    "pay": "支付",
    "payment": "支付",
    "pdd": "拼多多",
    "platform": "平台",
    "price": "价格",
    "product": "商品",
    "qty": "数量",
    "quantity": "数量",
    "receivable": "应收",
    "record": "记录",
    "refund": "退款",
    "seller": "卖家",
    "settle": "结算",
    "settlement": "结算",
    "shop": "店铺",
    "sku": "SKU",
    "source": "来源",
    "status": "状态",
    "submit": "提交",
    "success": "成功",
    "target": "目标",
    "tax": "税费",
    "time": "时间",
    "total": "总",
    "trade": "交易",
    "transaction": "交易",
    "txn": "交易",
    "type": "类型",
    "uid": "用户ID",
    "unionid": "UnionID",
    "update": "更新",
    "updated": "更新",
    "user": "用户",
    "wechat": "微信",
    "weixin": "微信",
    "wx": "微信",
}
_FIELD_SUFFIX_LABELS: dict[str, str] = {
    "amount": "金额",
    "amout": "金额",
    "amt": "金额",
    "code": "编码",
    "count": "数量",
    "date": "日期",
    "fee": "费用",
    "id": "ID",
    "money": "金额",
    "name": "名称",
    "no": "编号",
    "num": "数量",
    "number": "编号",
    "order": "订单号",
    "price": "价格",
    "qty": "数量",
    "quantity": "数量",
    "sn": "序号",
    "status": "状态",
    "time": "时间",
    "type": "类型",
}
_FIELD_COMPOUND_SUFFIX_LABELS: dict[str, str] = {
    "created_at": "创建时间",
    "order_code": "订单编码",
    "order_id": "订单ID",
    "order_no": "订单号",
    "paid_at": "支付时间",
    "pay_time": "支付时间",
    "refund_at": "退款时间",
    "trade_code": "交易编码",
    "trade_id": "交易ID",
    "trade_no": "交易号",
    "updated_at": "更新时间",
}


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_semantic_status(value: Any, *, default: str = "generated_basic") -> str:
    status = _safe_text(value).lower() or default
    if status not in SEMANTIC_STATUS_VALUES:
        return default
    return status


def _normalize_semantic_field_source(value: Any, *, default: str = "rule_fallback") -> str:
    source = _safe_text(value).lower() or default
    if source not in _SEMANTIC_FIELD_SOURCE_VALUES:
        return default
    return source


def _is_enabled_flag(value: Any, *, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _is_effective_llm_api_key(value: Any) -> bool:
    api_key = _safe_text(value)
    if not api_key:
        return False
    lowered = api_key.lower()
    placeholder_markers = (
        "your-key",
        "your-qwen-key",
        "your-openai-key",
        "sk-your",
        "replace-me",
        "placeholder",
        "demo-key",
        "example-key",
    )
    return not any(marker in lowered for marker in placeholder_markers)


def _load_semantic_env_values() -> dict[str, str]:
    global _SEMANTIC_ENV_CACHE
    if _SEMANTIC_ENV_CACHE is not None:
        return _SEMANTIC_ENV_CACHE

    merged: dict[str, str] = {}
    project_root = Path(__file__).resolve().parents[2]
    candidate_paths = (
        project_root / ".env",
        project_root / "finance-mcp" / ".env",
        project_root / "finance-agents" / "data-agent" / ".env",
    )
    for path in candidate_paths:
        if not path.exists():
            continue
        try:
            for key, value in dotenv_values(path).items():
                normalized_key = _safe_text(key)
                normalized_value = _safe_text(value)
                if normalized_key and normalized_value and normalized_key not in merged:
                    merged[normalized_key] = normalized_value
        except Exception as exc:
            logger.warning("load semantic env file failed: path=%s error=%s", path, exc)
    _SEMANTIC_ENV_CACHE = merged
    return merged


def _get_semantic_env(name: str, default: Any = "") -> Any:
    runtime_value = _safe_text(os.getenv(name))
    if runtime_value:
        return runtime_value
    file_value = _safe_text(_load_semantic_env_values().get(name))
    if file_value:
        return file_value
    return default


def _get_semantic_llm_config() -> dict[str, Any] | None:
    if not _is_enabled_flag(_get_semantic_env("DATASET_SEMANTIC_ENABLE_LLM", None), default=True):
        return None

    provider = _safe_text(_get_semantic_env("LLM_PROVIDER", "openai")).lower() or "openai"
    provider_map = {
        "openai": {
            "api_key": _get_semantic_env("OPENAI_API_KEY"),
            "base_url": _get_semantic_env("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            "model": _get_semantic_env("OPENAI_MODEL", "gpt-4o"),
        },
        "qwen": {
            "api_key": _get_semantic_env("QWEN_API_KEY"),
            "base_url": _get_semantic_env("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            "model": _get_semantic_env("QWEN_MODEL", "qwen-plus"),
        },
        "deepseek": {
            "api_key": _get_semantic_env("DEEPSEEK_API_KEY"),
            "base_url": _get_semantic_env("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
            "model": _get_semantic_env("DEEPSEEK_MODEL", "deepseek-chat"),
        },
    }
    ordered_names = [provider, "qwen", "openai", "deepseek"]
    seen: set[str] = set()
    for name in ordered_names:
        if name in seen or name not in provider_map:
            continue
        seen.add(name)
        config = provider_map[name]
        if _is_effective_llm_api_key(config["api_key"]):
            try:
                timeout = max(5.0, float(_get_semantic_env("DATASET_SEMANTIC_LLM_TIMEOUT_SECONDS", "45")))
            except (TypeError, ValueError):
                timeout = 45.0
            return {
                "provider": name,
                "api_key": _safe_text(config["api_key"]),
                "base_url": _safe_text(config["base_url"]).rstrip("/"),
                "model": _safe_text(config["model"]),
                "timeout": timeout,
            }
    return None


def _extract_json_object(text: str) -> dict[str, Any] | None:
    raw = _safe_text(text)
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass

    fenced_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, flags=re.DOTALL | re.IGNORECASE)
    if fenced_match:
        try:
            parsed = json.loads(fenced_match.group(1))
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(raw[start : end + 1])
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None
    return None


def _tokenize_identifier(value: Any) -> list[str]:
    text = _FIELD_CAMEL_BOUNDARY.sub(r"\1_\2", _safe_text(value)).lower()
    if not text:
        return []
    tokens = [token for token in _FIELD_TOKEN_SPLIT.split(text) if token]
    if tokens:
        return tokens
    return [text]


def _truncate_text(value: Any, *, limit: int = 80) -> str:
    raw = _safe_text(value)
    if len(raw) <= limit:
        return raw
    return f"{raw[: max(0, limit - 1)]}…"


def _extract_dataset_columns(dataset_row: dict[str, Any], sample_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    schema_summary = dict(dataset_row.get("schema_summary") or {})
    columns = schema_summary.get("columns")
    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()

    if isinstance(columns, list):
        for item in columns:
            if not isinstance(item, dict):
                continue
            name = _safe_text(item.get("name"))
            if not name or name in seen:
                continue
            seen.add(name)
            ordered.append(
                {
                    "name": name,
                    "data_type": _safe_text(item.get("data_type")) or "unknown",
                    "nullable": bool(item.get("nullable", True)),
                }
            )

    for row in sample_rows:
        if not isinstance(row, dict):
            continue
        for key, value in row.items():
            name = _safe_text(key)
            if not name or name in seen:
                continue
            seen.add(name)
            ordered.append(
                {
                    "name": name,
                    "data_type": type(value).__name__,
                    "nullable": value is None,
                }
            )
    return ordered


def _guess_business_name(dataset_row: dict[str, Any], source_row: dict[str, Any] | None = None) -> str:
    dataset_name = _safe_text(dataset_row.get("dataset_name"))
    resource_key = _safe_text(dataset_row.get("resource_key"))
    dataset_code = _safe_text(dataset_row.get("dataset_code"))
    raw = " ".join([dataset_name, resource_key, dataset_code])
    tokens = set(_tokenize_identifier(raw))

    for hints, label in _BUSINESS_NAME_HINTS:
        if all(hint in tokens for hint in hints):
            return label

    source_kind = _safe_text((source_row or {}).get("source_kind")).lower()
    if source_kind == "api":
        return "API 数据集"
    if source_kind == "database":
        return "数据库数据集"
    if source_kind == "browser":
        return "网页采集数据集"
    if source_kind == "desktop_cli":
        return "桌面端采集数据集"
    if source_kind == "file":
        return "文件数据集"
    return "业务数据集"


def _combine_field_label(prefix_label: str, suffix_label: str) -> str:
    if not prefix_label:
        return suffix_label
    if suffix_label == "订单号":
        return f"{prefix_label}号" if prefix_label.endswith("订单") else f"{prefix_label}{suffix_label}"
    if suffix_label in {"订单ID", "订单编码"}:
        return f"{prefix_label}{suffix_label[2:]}" if prefix_label.endswith("订单") else f"{prefix_label}{suffix_label}"
    if suffix_label.startswith(prefix_label):
        return suffix_label
    return f"{prefix_label}{suffix_label}"


def _translate_field_tokens(tokens: list[str]) -> str:
    labels: list[str] = []
    for token in tokens:
        labels.append(_FIELD_TOKEN_LABELS.get(token) or token.upper())
    return "".join(labels)


def _infer_field_display_name(field_name: str) -> str:
    tokens = _tokenize_identifier(field_name)
    if not tokens:
        return field_name
    if len(tokens) >= 2:
        compound_suffix = f"{tokens[-2]}_{tokens[-1]}"
        compound_label = _FIELD_COMPOUND_SUFFIX_LABELS.get(compound_suffix)
        if compound_label:
            return _combine_field_label(_translate_field_tokens(tokens[:-2]), compound_label)
    suffix_label = _FIELD_SUFFIX_LABELS.get(tokens[-1])
    if suffix_label:
        return _combine_field_label(_translate_field_tokens(tokens[:-1]), suffix_label)
    return _translate_field_tokens(tokens) or field_name


def _guess_field_semantic(
    field_name: str,
    data_type: str,
    *,
    has_sample_rows: bool,
) -> dict[str, Any]:
    tokens = _tokenize_identifier(field_name)
    token_set = set(tokens)
    inferred_label = _infer_field_display_name(field_name)
    default_label = inferred_label or field_name
    semantic_type = "unknown"
    business_role = "unknown"
    description = ""
    confidence = 0.55
    semantic_source = "rule_fallback"

    for _, (hints, semantic, label, desc) in _SEMANTIC_ROLE_HINTS.items():
        if all(h in token_set for h in hints):
            semantic_type = semantic
            if semantic == "identifier":
                business_role = "identifier"
            elif semantic == "datetime":
                business_role = "time"
            elif semantic == "amount":
                business_role = "amount"
            elif semantic == "status":
                business_role = "status"
            elif semantic == "dimension" and "name" in token_set:
                business_role = "name"
            else:
                business_role = "_".join(hints)
            default_label = inferred_label or label
            description = desc
            confidence = 0.88 if has_sample_rows else 0.72
            break

    if semantic_type == "unknown":
        lowered_type = _safe_text(data_type).lower()
        if "time" in token_set or "date" in token_set or lowered_type in {"date", "datetime", "timestamp"}:
            semantic_type = "datetime"
            business_role = "time"
            default_label = inferred_label or "时间"
            description = f"{default_label}字段"
            confidence = 0.76 if has_sample_rows else 0.68
        elif any(token in token_set for token in {"amount", "amt", "money", "price", "fee", "balance"}):
            semantic_type = "amount"
            business_role = "amount"
            default_label = inferred_label or "金额"
            description = f"{default_label}字段"
            confidence = 0.8 if has_sample_rows else 0.7
        elif any(token in token_set for token in {"id", "no", "code", "uid", "sn"}):
            semantic_type = "identifier"
            business_role = "identifier"
            default_label = inferred_label or "标识"
            description = f"{default_label}，用于唯一定位业务记录"
            confidence = 0.74 if has_sample_rows else 0.66
        elif any(token in token_set for token in {"status", "state", "flag"}):
            semantic_type = "status"
            business_role = "status"
            default_label = inferred_label or "状态"
            description = f"{default_label}字段"
            confidence = 0.72 if has_sample_rows else 0.64
        elif "type" in token_set:
            semantic_type = "enum"
            business_role = "type"
            default_label = inferred_label or "类型"
            description = f"{default_label}字段"
            confidence = 0.68 if has_sample_rows else 0.62
        elif "name" in token_set:
            semantic_type = "text"
            business_role = "name"
            default_label = inferred_label or "名称"
            description = f"{default_label}字段"
            confidence = 0.66 if has_sample_rows else 0.6

    if not has_sample_rows:
        confidence = min(confidence, 0.74)

    return {
        "raw_name": field_name,
        "display_name": default_label,
        "semantic_type": semantic_type,
        "business_role": business_role,
        "description": description,
        "confidence": round(float(confidence), 4),
        "source": semantic_source,
    }


def _collect_sample_values(
    sample_rows: list[dict[str, Any]],
    field_name: str,
    *,
    max_values: int = 3,
    max_length: int = 40,
) -> list[str]:
    values: list[str] = []
    for row in sample_rows:
        if not isinstance(row, dict) or field_name not in row:
            continue
        value = row.get(field_name)
        if value is None:
            continue
        normalized = _truncate_text(value, limit=max_length)
        if not normalized:
            continue
        if normalized in values:
            continue
        values.append(normalized)
        if len(values) >= max_values:
            break
    return values


def _coerce_confidence(value: Any, *, default: float = 0.82) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = default
    return round(max(0.0, min(confidence, 1.0)), 4)


def _build_semantic_llm_request_fields(
    *,
    columns: list[dict[str, Any]],
    sample_rows: list[dict[str, Any]],
    include_samples: bool,
) -> list[dict[str, Any]]:
    request_fields: list[dict[str, Any]] = []
    for column in columns:
        raw_name = _safe_text(column.get("name"))
        if not raw_name:
            continue
        request_field = {
            "raw_name": raw_name,
            "data_type": _safe_text(column.get("data_type")) or "unknown",
            "nullable": bool(column.get("nullable", True)),
        }
        if include_samples:
            request_field["sample_values"] = _collect_sample_values(
                sample_rows,
                raw_name,
                max_values=2,
                max_length=24,
            )
        request_fields.append(request_field)
    return request_fields


def _semantic_llm_completion_url(base_url: str) -> str:
    normalized = _safe_text(base_url).rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def _semantic_llm_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                parts.append(_safe_text(item.get("text")))
            else:
                parts.append(_safe_text(item))
        return "\n".join(part for part in parts if part)
    if isinstance(content, dict):
        return _safe_text(content.get("text"))
    return _safe_text(content)


def _call_semantic_llm(
    *,
    llm_config: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    url = _semantic_llm_completion_url(_safe_text(llm_config.get("base_url")))
    headers = {
        "Authorization": f"Bearer {_safe_text(llm_config.get('api_key'))}",
        "Content-Type": "application/json",
    }
    request_body = {
        "model": _safe_text(llm_config.get("model")),
        "temperature": 0.1,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是金融数据语义治理助手。"
                    "请根据输入的数据集信息返回一个 JSON 对象，不要输出 Markdown、解释或额外文本。"
                    "字段 raw_name 必须与输入完全一致；display_name 必须尽量输出自然中文；"
                    "key_fields 只能填写真实存在的技术字段名；如果拿不准就保守输出。"
                    "请优先输出贴近业务的中文，不要机械复述英文字段名，也不要只输出“标识”“编码”这类过泛词。"
                    "description 保持简洁，尽量一句话说清字段含义。"
                ),
            },
            {
                "role": "user",
                "content": _json_safe(
                    {
                        "task": (
                            "为当前数据集生成发布前语义建议。"
                            "请输出 business_name、business_description、key_fields、fields。"
                            "fields 中每个元素包含 raw_name、display_name、semantic_type、business_role、"
                            "description、confidence、is_unique_identifier。"
                            "对于 *_id、*_code、*_no、*_amount、*_order 等字段，请结合前缀和上下文补全自然中文。"
                        ),
                        "dataset": payload,
                    }
                ),
            },
        ],
    }
    try:
        response = requests.post(
            url,
            headers=headers,
            json=request_body,
            timeout=float(llm_config.get("timeout") or 45),
        )
        response.raise_for_status()
        response_payload = response.json()
        choices = response_payload.get("choices") or []
        if not choices:
            logger.warning(
                "semantic llm response missing choices: provider=%s model=%s",
                llm_config.get("provider"),
                llm_config.get("model"),
            )
            return None
        message = dict(choices[0].get("message") or {})
        parsed = _extract_json_object(_semantic_llm_content_text(message.get("content")))
        if not parsed:
            logger.warning(
                "semantic llm response missing json payload: provider=%s model=%s",
                llm_config.get("provider"),
                llm_config.get("model"),
            )
        return parsed
    except Exception as exc:
        logger.warning(
            "semantic llm request failed: provider=%s model=%s error=%s",
            llm_config.get("provider"),
            llm_config.get("model"),
            exc,
        )
        return None


def _build_llm_semantic_profile(
    *,
    dataset_row: dict[str, Any],
    source_row: dict[str, Any] | None,
    sample_rows: list[dict[str, Any]],
    columns: list[dict[str, Any]],
    base_profile: dict[str, Any],
    llm_config: dict[str, Any],
) -> dict[str, Any] | None:
    if not columns:
        return None

    base_fields = [
        dict(item)
        for item in base_profile.get("fields") or []
        if isinstance(item, dict) and _safe_text(item.get("raw_name"))
    ]
    base_fields_by_name = {
        _safe_text(item.get("raw_name")): dict(item)
        for item in base_fields
        if _safe_text(item.get("raw_name"))
    }

    def build_payload(*, include_samples: bool, request_mode: str) -> dict[str, Any]:
        return {
            "request_mode": request_mode,
            "source": {
                "name": _safe_text((source_row or {}).get("name")),
                "source_kind": _safe_text((source_row or {}).get("source_kind")),
                "provider_code": _safe_text((source_row or {}).get("provider_code")),
            },
            "dataset": {
                "dataset_name": _safe_text(dataset_row.get("dataset_name")),
                "dataset_code": _safe_text(dataset_row.get("dataset_code")),
                "resource_key": _safe_text(dataset_row.get("resource_key")),
                "dataset_kind": _safe_text(dataset_row.get("dataset_kind")),
            },
            "fields": _build_semantic_llm_request_fields(
                columns=columns,
                sample_rows=sample_rows,
                include_samples=include_samples,
            ),
        }

    llm_response = _call_semantic_llm(
        llm_config=llm_config,
        payload=build_payload(include_samples=True, request_mode="standard"),
    )
    if not llm_response:
        return None

    llm_fields_by_name: dict[str, dict[str, Any]] = {}
    llm_unique_field_names: list[str] = []
    for item in llm_response.get("fields") or []:
        if not isinstance(item, dict):
            continue
        raw_name = _safe_text(item.get("raw_name") or item.get("field_name") or item.get("name"))
        if not raw_name or raw_name in llm_fields_by_name or raw_name not in base_fields_by_name:
            continue
        fallback_field = dict(base_fields_by_name[raw_name])
        llm_field = {
            **fallback_field,
            "display_name": _safe_text(item.get("display_name") or item.get("display_name_zh") or item.get("label"))
            or _safe_text(fallback_field.get("display_name"))
            or raw_name,
            "semantic_type": _safe_text(item.get("semantic_type") or item.get("type")).lower()
            or _safe_text(fallback_field.get("semantic_type"))
            or "unknown",
            "business_role": _safe_text(item.get("business_role") or item.get("role")).lower()
            or _safe_text(fallback_field.get("business_role"))
            or "unknown",
            "description": _safe_text(item.get("description")) or _safe_text(fallback_field.get("description")),
            "confidence": _coerce_confidence(
                item.get("confidence"),
                default=max(float(fallback_field.get("confidence") or 0.0), 0.86 if sample_rows else 0.8),
            ),
            "source": "llm_generated",
        }
        llm_fields_by_name[raw_name] = llm_field
        if _is_enabled_flag(item.get("is_unique_identifier"), default=False):
            llm_unique_field_names.append(raw_name)

    candidate_key_fields: list[str] = []
    seen_key_fields: set[str] = set()
    llm_key_field_count = 0

    def add_key_field(raw_name: Any) -> bool:
        normalized = _safe_text(raw_name)
        if (
            not normalized
            or normalized in seen_key_fields
            or normalized not in base_fields_by_name
        ):
            return False
        seen_key_fields.add(normalized)
        candidate_key_fields.append(normalized)
        return True

    for raw_name in llm_response.get("key_fields") or []:
        if add_key_field(raw_name):
            llm_key_field_count += 1
    for raw_name in llm_unique_field_names:
        if add_key_field(raw_name):
            llm_key_field_count += 1
    if not candidate_key_fields:
        for raw_name in base_profile.get("key_fields") or []:
            add_key_field(raw_name)

    merged_fields: list[dict[str, Any]] = []
    for base_field in base_fields:
        raw_name = _safe_text(base_field.get("raw_name"))
        merged_field = dict(llm_fields_by_name.get(raw_name) or base_field)
        merged_field["source"] = _normalize_semantic_field_source(
            merged_field.get("source"),
            default="llm_generated" if raw_name in llm_fields_by_name else "rule_fallback",
        )
        merged_fields.append(merged_field)

    merged_field_label_map = {
        _safe_text(item.get("raw_name")): _safe_text(item.get("display_name")) or _safe_text(item.get("raw_name"))
        for item in merged_fields
        if _safe_text(item.get("raw_name"))
    }
    low_confidence_fields = [
        _safe_text(item.get("raw_name"))
        for item in merged_fields
        if _safe_text(item.get("raw_name"))
        and float(item.get("confidence") or 0.0) < SEMANTIC_FIELD_CONFIDENCE_THRESHOLD
        and not bool(item.get("confirmed_by_user"))
    ]

    business_name = _safe_text(llm_response.get("business_name")) or _safe_text(base_profile.get("business_name"))
    business_description = _safe_text(llm_response.get("business_description")) or _safe_text(
        base_profile.get("business_description")
    )
    llm_used = (
        bool(llm_fields_by_name)
        or bool(_safe_text(llm_response.get("business_name")))
        or bool(_safe_text(llm_response.get("business_description")))
        or llm_key_field_count > 0
    )
    if not llm_used:
        return None

    return {
        **dict(base_profile),
        "status": "llm_generated",
        "business_name": business_name,
        "business_description": business_description,
        "key_fields": candidate_key_fields[:6],
        "field_label_map": merged_field_label_map,
        "fields": merged_fields,
        "low_confidence_fields": low_confidence_fields,
        "semantic_generator": {
            "mode": "llm_cached",
            "provider": _safe_text(llm_config.get("provider")),
            "model": _safe_text(llm_config.get("model")),
            "llm_enabled": True,
            "field_source_default": "rule_fallback",
            "llm_field_count": len(llm_fields_by_name),
            "fallback_field_count": max(0, len(merged_fields) - len(llm_fields_by_name)),
        },
        "updated_at": _now_iso(),
    }


def _build_semantic_profile(
    *,
    dataset_row: dict[str, Any],
    source_row: dict[str, Any] | None,
    sample_rows: list[dict[str, Any]],
    status: str,
    allow_llm: bool = False,
) -> dict[str, Any]:
    columns = _extract_dataset_columns(dataset_row, sample_rows)
    has_sample_rows = bool(sample_rows)
    field_items: list[dict[str, Any]] = []
    field_label_map: dict[str, str] = {}
    low_confidence_fields: list[str] = []

    for column in columns:
        name = _safe_text(column.get("name"))
        if not name:
            continue
        semantic = _guess_field_semantic(
            name,
            _safe_text(column.get("data_type")),
            has_sample_rows=has_sample_rows,
        )
        sample_values = _collect_sample_values(sample_rows, name)
        field_item = {
            **semantic,
            "sample_values": sample_values,
            "confirmed_by_user": False,
        }
        field_items.append(field_item)
        field_label_map[name] = _safe_text(semantic.get("display_name")) or name
        if float(semantic.get("confidence") or 0.0) < SEMANTIC_FIELD_CONFIDENCE_THRESHOLD:
            low_confidence_fields.append(name)

    key_fields: list[str] = []
    for field in field_items:
        role = _safe_text(field.get("business_role")).lower()
        raw_name = _safe_text(field.get("raw_name"))
        if role == "identifier" and raw_name and raw_name not in key_fields:
            key_fields.append(raw_name)
        if len(key_fields) >= 6:
            break

    business_name = _guess_business_name(dataset_row, source_row=source_row)
    business_description = (
        f"{business_name}，用于{_safe_text((source_row or {}).get('source_kind')) or '数据源'}侧的数据采集与分析。"
    )
    if key_fields:
        key_field_labels = [
            f"{field_label_map.get(raw_name) or raw_name}({raw_name})"
            for raw_name in key_fields[:6]
        ]
        business_description = f"{business_name}，唯一标识字段候选包含：{', '.join(key_field_labels)}。"

    schema_summary = dict(dataset_row.get("schema_summary") or {})
    generated_from = {
        "source_kind": _safe_text((source_row or {}).get("source_kind")),
        "provider_code": _safe_text((source_row or {}).get("provider_code")),
        "dataset_kind": _safe_text(dataset_row.get("dataset_kind")),
        "resource_key": _safe_text(dataset_row.get("resource_key")),
        "schema_hash": _hash_payload(schema_summary),
        "sample_hash": _hash_payload(sample_rows[:SEMANTIC_SAMPLE_ROW_LIMIT]) if has_sample_rows else "",
        "has_sample_rows": has_sample_rows,
    }
    semantic_status = _normalize_semantic_status(
        status,
        default="generated_with_samples" if has_sample_rows else "generated_basic",
    )
    base_profile = {
        "version": 1,
        "status": semantic_status,
        "business_name": business_name,
        "business_description": business_description,
        "key_fields": key_fields,
        "field_label_map": field_label_map,
        "fields": field_items,
        "low_confidence_fields": low_confidence_fields,
        "generated_from": generated_from,
        "semantic_generator": {
            "mode": "rules_cached",
            "llm_enabled": False,
            "field_source_default": "rule_fallback",
        },
        "updated_at": _now_iso(),
    }
    llm_config = _get_semantic_llm_config() if allow_llm else None
    if llm_config:
        llm_profile = _build_llm_semantic_profile(
            dataset_row=dataset_row,
            source_row=source_row,
            sample_rows=sample_rows,
            columns=columns,
            base_profile=base_profile,
            llm_config=llm_config,
        )
        if llm_profile:
            return llm_profile
        base_profile["semantic_generator"] = {
            **dict(base_profile.get("semantic_generator") or {}),
            "llm_enabled": True,
            "provider": _safe_text(llm_config.get("provider")),
            "model": _safe_text(llm_config.get("model")),
        }
    return base_profile


def _extract_semantic_profile(dataset_row: dict[str, Any]) -> dict[str, Any]:
    meta = dict(dataset_row.get("meta") or {})
    semantic_profile = meta.get("semantic_profile")
    if not isinstance(semantic_profile, dict):
        return {}
    return semantic_profile


def _semantic_profile_has_manual_field_overrides(profile: dict[str, Any]) -> bool:
    manual_overrides = profile.get("manual_overrides")
    if isinstance(manual_overrides, dict) and any(bool(value) for value in manual_overrides.values()):
        return True

    for item in profile.get("fields") or []:
        if not isinstance(item, dict):
            continue
        if bool(item.get("confirmed_by_user")):
            return True
        source = _normalize_semantic_field_source(item.get("source"), default="rule_fallback")
        if source in {"manual_confirmed", "manual_updated"}:
            return True
    return False


def _derive_semantic_pending_fields(profile: dict[str, Any]) -> list[str]:
    pending_fields: list[str] = []
    seen: set[str] = set()

    def add(raw_name: Any) -> None:
        name = _safe_text(raw_name)
        if not name or name in seen:
            return
        seen.add(name)
        pending_fields.append(name)

    for raw_name in profile.get("low_confidence_fields") or []:
        add(raw_name)

    for item in profile.get("fields") or []:
        if not isinstance(item, dict):
            continue
        raw_name = _safe_text(item.get("raw_name") or item.get("name"))
        if not raw_name or bool(item.get("confirmed_by_user")):
            continue
        try:
            confidence = float(item.get("confidence"))
        except Exception:
            continue
        if confidence < SEMANTIC_FIELD_CONFIDENCE_THRESHOLD:
            add(raw_name)

    return pending_fields


def _flatten_semantic_profile(dataset_row: dict[str, Any]) -> dict[str, Any]:
    profile = _extract_semantic_profile(dataset_row)
    if not profile:
        return {
            "semantic_status": "missing",
            "semantic_updated_at": "",
            "business_name": "",
            "business_description": "",
            "key_fields": [],
            "field_label_map": {},
            "semantic_fields": [],
            "low_confidence_fields": [],
            "semantic_pending_count": 0,
        }
    low_confidence_fields = _derive_semantic_pending_fields(profile)
    return {
        "semantic_status": _normalize_semantic_status(
            profile.get("status"),
            default="generated_with_samples" if bool(profile.get("generated_from", {}).get("has_sample_rows")) else "generated_basic",
        ),
        "semantic_updated_at": _safe_text(profile.get("updated_at")),
        "business_name": _safe_text(profile.get("business_name")),
        "business_description": _safe_text(profile.get("business_description")),
        "key_fields": [str(item) for item in profile.get("key_fields") or [] if _safe_text(item)],
        "field_label_map": dict(profile.get("field_label_map") or {}),
        "semantic_fields": [item for item in profile.get("fields") or [] if isinstance(item, dict)],
        "low_confidence_fields": low_confidence_fields,
        "semantic_pending_count": len(low_confidence_fields),
    }


def _default_execution_mode(source_kind: str) -> str:
    return "agent_assisted" if source_kind in AGENT_ASSISTED_KINDS else "deterministic"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def _hash_payload(payload: Any) -> str:
    return hashlib.sha1(_json_safe(payload).encode("utf-8")).hexdigest()


def _require_user(auth_token: str) -> dict[str, Any]:
    token = str(auth_token or "").strip()
    if not token:
        raise ValueError("未提供认证 token，请先登录")
    user = get_user_from_token(token)
    if not user:
        raise ValueError("token 无效或已过期，请重新登录")
    if not user.get("company_id"):
        raise ValueError("当前用户未绑定公司，无法配置数据源")
    return user


def _require_scheduler_user(auth_token: str) -> dict[str, Any]:
    token = str(auth_token or "").strip()
    if not token:
        raise ValueError("未提供认证 token")
    user = get_user_from_token(token)
    if not user:
        raise ValueError("token 无效或已过期")
    role = str(user.get("role") or "").strip().lower()
    if role not in {"system", "scheduler"}:
        raise ValueError("当前 token 无权限执行调度器内部调用")
    return user


def _normalize_source_kind(value: Any) -> str:
    source_kind = str(value or "").strip().lower()
    if source_kind not in SOURCE_KINDS:
        raise ValueError(f"不支持的 source_kind: {source_kind}")
    return source_kind


def _normalize_domain_type(value: Any) -> str:
    domain_type = str(value or "").strip().lower() or "internal_business"
    if domain_type not in DOMAIN_TYPES:
        raise ValueError(f"不支持的 domain_type: {domain_type}")
    return domain_type


def _normalize_execution_mode(source_kind: str, value: Any) -> str:
    mode = str(value or "").strip().lower() or _default_execution_mode(source_kind)
    if mode not in {"deterministic", "agent_assisted"}:
        raise ValueError(f"不支持的 execution_mode: {mode}")
    if source_kind in AGENT_ASSISTED_KINDS:
        return "agent_assisted"
    return mode


def _normalize_status(value: Any, *, default: str = "active") -> str:
    status = str(value or "").strip().lower() or default
    if status not in {"active", "disabled", "deleted"}:
        raise ValueError(f"不支持的 status: {status}")
    return status


def _normalize_publish_status(value: Any, *, default: str = "unpublished") -> str:
    status = str(value or "").strip().lower() or default
    if status not in PUBLISH_STATUS_VALUES:
        return default
    return status


def _normalize_verified_status(value: Any, *, default: str = "unverified") -> str:
    status = str(value or "").strip().lower() or default
    if status not in VERIFIED_STATUS_VALUES:
        return default
    return status


def _normalize_scene_type(value: Any) -> str:
    scene_type = str(value or "").strip().lower()
    if not scene_type:
        return ""
    if scene_type in DATASET_CANDIDATE_SCENES:
        return scene_type
    return ""


def _normalize_role_code(value: Any) -> str:
    role_code = str(value or "").strip().lower()
    if not role_code:
        return ""
    if role_code in DATASET_CANDIDATE_ROLES:
        return role_code
    return ""


def _normalize_bool(value: Any, *, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _source_id_from_args(arguments: dict[str, Any]) -> str:
    return str(arguments.get("source_id") or arguments.get("data_source_id") or "").strip()


def _dataset_id_from_args(arguments: dict[str, Any]) -> str:
    return str(arguments.get("dataset_id") or arguments.get("id") or "").strip()


def _resource_key_from_args(arguments: dict[str, Any]) -> str:
    if str(arguments.get("resource_key") or "").strip():
        return str(arguments.get("resource_key")).strip()
    params = arguments.get("params") or {}
    if isinstance(params, dict) and str(params.get("resource_key") or "").strip():
        return str(params.get("resource_key")).strip()
    return "default"


def _window_from_args(arguments: dict[str, Any]) -> tuple[str | None, str | None]:
    window_start = str(arguments.get("window_start") or "").strip() or None
    window_end = str(arguments.get("window_end") or "").strip() or None
    window = arguments.get("window") or {}
    if isinstance(window, dict):
        window_start = window_start or str(window.get("start") or window.get("window_start") or "").strip() or None
        window_end = window_end or str(window.get("end") or window.get("window_end") or "").strip() or None
    return window_start, window_end


def _collection_biz_date_from_args(arguments: dict[str, Any]) -> str:
    explicit = str(arguments.get("biz_date") or "").strip()
    if explicit:
        return explicit
    params = arguments.get("params") or {}
    if isinstance(params, dict):
        return str(params.get("biz_date") or "").strip()
    return ""


def _dataset_collection_config(dataset_row: dict[str, Any] | None) -> dict[str, Any]:
    if not dataset_row:
        return {}
    profile = _extract_catalog_profile(dataset_row)
    config = profile.get("collection_config")
    return dict(config) if isinstance(config, dict) else {}


def _dataset_collection_key_fields(dataset_row: dict[str, Any] | None) -> list[str]:
    if not dataset_row:
        return []

    candidates: list[Any] = []
    semantic_profile = _extract_semantic_profile(dataset_row)
    if isinstance(semantic_profile.get("key_fields"), list):
        candidates.extend(semantic_profile.get("key_fields") or [])

    for container_key in ("key_fields", "collection_key_fields", "primary_key_fields"):
        value = dataset_row.get(container_key)
        if isinstance(value, list):
            candidates.extend(value)

    for container_key in ("meta", "schema_summary", "extract_config", "sync_strategy"):
        container = dataset_row.get(container_key)
        if not isinstance(container, dict):
            continue
        for key in ("key_fields", "collection_key_fields", "primary_key_fields"):
            value = container.get(key)
            if isinstance(value, list):
                candidates.extend(value)

    fields: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        field = _safe_text(item)
        if not field or field in seen:
            continue
        seen.add(field)
        fields.append(field)
    return fields


def _collection_context_from_args(arguments: dict[str, Any]) -> dict[str, Any]:
    params = arguments.get("params") if isinstance(arguments.get("params"), dict) else {}
    dataset_id = _safe_text(params.get("dataset_id") or arguments.get("dataset_id"))
    if not dataset_id:
        return {}
    return {
        "dataset_id": dataset_id,
        "dataset_code": _safe_text(params.get("dataset_code") or arguments.get("dataset_code")),
        "biz_date": _safe_text(params.get("biz_date") or arguments.get("biz_date")),
        "key_fields": [
            _safe_text(item)
            for item in params.get("key_fields") or arguments.get("key_fields") or []
            if _safe_text(item)
        ],
    }


def _collection_key_value_is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _build_collection_records(
    *,
    rows: list[dict[str, Any]],
    key_fields: list[str],
) -> list[dict[str, Any]]:
    if not key_fields:
        raise ValueError("数据集缺少 key_fields，无法生成采集记录唯一标识")

    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        key_values = {field: row.get(field) for field in key_fields}
        if all(_collection_key_value_is_empty(value) for value in key_values.values()):
            raise ValueError(f"第 {index + 1} 行 key_fields 值全为空，采集失败")
        item_key = _hash_payload({"key_fields": key_fields, "values": key_values})
        if item_key in seen:
            continue
        seen.add(item_key)
        records.append(
            {
                "item_key": item_key,
                "item_key_values": key_values,
                "item_hash": _hash_payload(row),
                "payload": row,
            }
        )
    return records


def _collection_schedule_time(config: dict[str, Any]) -> str:
    schedule = config.get("schedule") if isinstance(config.get("schedule"), dict) else {}
    return _safe_text(
        schedule.get("time")
        or schedule.get("time_of_day")
        or config.get("schedule_time")
        or config.get("time")
    )


def _collection_date_field(config: dict[str, Any]) -> str:
    return _safe_text(
        config.get("date_field")
        or config.get("collection_date_field")
        or config.get("physical_date_field")
    )


def _collection_display_date_field(config: dict[str, Any]) -> str:
    return _safe_text(
        config.get("display_date_field")
        or config.get("date_field_label")
        or config.get("collection_date_field_label")
    )


def _generate_source_code(source_kind: str, provider_code: str, name: str) -> str:
    if source_kind == "platform_oauth":
        return f"{source_kind}__{provider_code}"
    base = f"{source_kind}__{provider_code or 'default'}"
    digest = hashlib.sha1(f"{base}:{name}:{uuid.uuid4()}".encode("utf-8")).hexdigest()[:10]
    return f"{base}__{digest}"


def _resolve_provider_code(
    source_kind: str,
    *,
    provider_code: Any = "",
    connection_config: dict[str, Any] | None = None,
    current_provider_code: str = "",
) -> str:
    explicit = str(provider_code or "").strip().lower()
    if explicit:
        return explicit

    if current_provider_code.strip():
        return current_provider_code.strip().lower()

    cfg = dict(connection_config or {})
    if source_kind == "platform_oauth":
        return "platform_oauth"
    if source_kind == "database":
        db_type = str(cfg.get("db_type") or "").strip().lower()
        return db_type or "database"
    if source_kind == "api":
        return "custom_api"
    if source_kind == "file":
        return "manual_file"
    if source_kind == "browser":
        return "browser"
    if source_kind == "desktop_cli":
        return "desktop_cli"
    return source_kind


def _query_source_any_company(source_id: str) -> dict[str, Any] | None:
    conn_manager = auth_db.get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, code, name, source_kind, domain_type, provider_code,
                           execution_mode, description, status, is_enabled,
                           health_status, last_checked_at, last_error_message, meta,
                           created_at, updated_at
                    FROM data_sources
                    WHERE id = %s
                    LIMIT 1
                    """,
                    (source_id,),
                )
                row = cur.fetchone()
                return auth_db._normalize_record(dict(row)) if row else None
    except Exception as exc:
        logger.error("query source by id failed: %s", exc, exc_info=True)
        return None


def _extract_collection_payload_rows(records: list[dict[str, Any]], *, limit: int = SEMANTIC_SAMPLE_ROW_LIMIT) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in records:
        payload = item.get("payload") or item.get("item_payload") or item.get("record_payload")
        if not isinstance(payload, dict):
            continue
        rows.append(dict(payload))
        if len(rows) >= max(1, min(limit, 100)):
            break
    return rows


def _load_dataset_sample_rows_from_collection_records(
    *,
    company_id: str,
    data_source_id: str,
    dataset_id: str = "",
    dataset_code: str = "",
    resource_key: str,
    limit: int = SEMANTIC_SAMPLE_ROW_LIMIT,
) -> list[dict[str, Any]]:
    records = auth_db.list_dataset_collection_records(
        company_id=company_id,
        data_source_id=data_source_id,
        dataset_id=_safe_text(dataset_id) or None,
        dataset_code=_safe_text(dataset_code) or None,
        resource_key=resource_key or "default",
        limit=max(1, min(limit, 100)),
        offset=0,
    )
    return _extract_collection_payload_rows(records, limit=limit)


def _collection_record_filter_matches(row_value: Any, expected_value: Any) -> bool:
    actual = str(row_value or "").strip()
    expected = str(expected_value or "").strip()
    if not expected:
        return actual == expected
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", expected):
        return actual.startswith(expected)
    return actual == expected


def _export_collection_records_to_excel(
    *,
    company_id: str,
    data_source_id: str,
    dataset_id: str = "",
    dataset_code: str = "",
    resource_key: str = "",
    biz_date: str = "",
    table_name: str,
    query: dict[str, Any] | None = None,
) -> tuple[str, int]:
    records = auth_db.list_dataset_collection_records(
        company_id=company_id,
        data_source_id=data_source_id,
        dataset_id=_safe_text(dataset_id) or None,
        dataset_code=_safe_text(dataset_code) or None,
        resource_key=_safe_text(resource_key) or None,
        biz_date=_safe_text(biz_date) or None,
        limit=None,
        offset=0,
    )
    payload_rows = _extract_collection_payload_rows(records, limit=max(len(records), 1))
    filters = dict((query or {}).get("filters") or {}) if isinstance(query, dict) else {}
    if filters:
        payload_rows = [
            row for row in payload_rows
            if all(_collection_record_filter_matches(row.get(key), value) for key, value in filters.items())
        ]

    export_root = UPLOAD_ROOT / "collection_record_exports"
    export_root.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix="collection_records_export_", dir=str(export_root)))
    safe_name = "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in table_name).strip("_") or "dataset"
    output_path = temp_dir / f"{safe_name}.xlsx"
    df = pd.DataFrame(payload_rows)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    return str(output_path), len(payload_rows)


def _persist_dataset_semantic_profile(
    *,
    dataset_row: dict[str, Any],
    semantic_profile: dict[str, Any],
) -> dict[str, Any] | None:
    dataset_id = _safe_text(dataset_row.get("id"))
    if not dataset_id:
        return None
    meta = dict(dataset_row.get("meta") or {})
    meta["semantic_profile"] = semantic_profile
    return auth_db.update_unified_data_source_dataset_meta(
        dataset_id=dataset_id,
        meta=meta,
    )


def _merge_existing_semantic_profile(
    *,
    generated_profile: dict[str, Any],
    existing_profile: dict[str, Any],
) -> dict[str, Any]:
    if not existing_profile:
        return generated_profile

    merged_profile = dict(generated_profile)
    existing_status = _normalize_semantic_status(
        existing_profile.get("status"),
        default="generated_basic",
    )
    generated_status = _normalize_semantic_status(
        generated_profile.get("status"),
        default="generated_basic",
    )
    valid_field_names = {
        _safe_text(item.get("raw_name"))
        for item in generated_profile.get("fields") or []
        if isinstance(item, dict) and _safe_text(item.get("raw_name"))
    }

    next_field_label_map = dict(generated_profile.get("field_label_map") or {})
    generated_fields = [
        dict(item)
        for item in generated_profile.get("fields") or []
        if isinstance(item, dict) and _safe_text(item.get("raw_name"))
    ]
    generated_fields_by_name = {
        _safe_text(item.get("raw_name")): item
        for item in generated_fields
        if _safe_text(item.get("raw_name"))
    }

    existing_field_label_map = dict(existing_profile.get("field_label_map") or {})
    existing_fields = [
        dict(item)
        for item in existing_profile.get("fields") or []
        if isinstance(item, dict) and _safe_text(item.get("raw_name"))
    ]
    existing_fields_by_name = {
        _safe_text(item.get("raw_name")): item
        for item in existing_fields
        if _safe_text(item.get("raw_name"))
    }

    preserve_manual_profile = (
        existing_status == "manual_updated" and _semantic_profile_has_manual_field_overrides(existing_profile)
    )
    preserve_cached_llm_profile = existing_status == "llm_generated" and generated_status != "llm_generated"
    if preserve_manual_profile:
        business_name = _safe_text(existing_profile.get("business_name"))
        if business_name:
            merged_profile["business_name"] = business_name
        business_description = _safe_text(existing_profile.get("business_description"))
        if business_description:
            merged_profile["business_description"] = business_description
        key_fields = [
            _safe_text(item)
            for item in existing_profile.get("key_fields") or []
            if _safe_text(item)
        ]
        if key_fields:
            merged_profile["key_fields"] = key_fields
        merged_profile["status"] = "manual_updated"
    elif preserve_cached_llm_profile:
        business_name = _safe_text(existing_profile.get("business_name"))
        if business_name:
            merged_profile["business_name"] = business_name
        business_description = _safe_text(existing_profile.get("business_description"))
        if business_description:
            merged_profile["business_description"] = business_description
        key_fields = [
            _safe_text(item)
            for item in existing_profile.get("key_fields") or []
            if _safe_text(item)
        ]
        if key_fields:
            merged_profile["key_fields"] = key_fields
        merged_profile["status"] = "llm_generated"
        if isinstance(existing_profile.get("semantic_generator"), dict):
            merged_profile["semantic_generator"] = dict(existing_profile.get("semantic_generator") or {})

    for raw_name in valid_field_names:
        existing_field = existing_fields_by_name.get(raw_name)
        existing_label = _safe_text(existing_field_label_map.get(raw_name))
        generated_field = dict(generated_fields_by_name.get(raw_name) or {"raw_name": raw_name})
        existing_source = _normalize_semantic_field_source(
            (existing_field or {}).get("source"),
            default="rule_fallback",
        )
        generated_source = _normalize_semantic_field_source(
            generated_field.get("source"),
            default="rule_fallback",
        )
        preserve_field = (
            bool(existing_field and existing_field.get("confirmed_by_user"))
            or existing_source in {"manual_confirmed", "manual_updated"}
            or (existing_source == "llm_generated" and generated_source != "llm_generated")
        )
        if not preserve_field and not (
            preserve_cached_llm_profile and existing_source == "llm_generated"
        ):
            continue

        if existing_label:
            generated_field["display_name"] = existing_label
            next_field_label_map[raw_name] = existing_label
        for key in ("semantic_type", "business_role", "description", "source"):
            value = _safe_text((existing_field or {}).get(key))
            if value:
                generated_field[key] = (
                    _normalize_semantic_field_source(value)
                    if key == "source"
                    else value
                )
        if existing_field is not None and existing_field.get("confidence") is not None:
            try:
                generated_field["confidence"] = round(
                    max(0.0, min(float(existing_field.get("confidence")), 1.0)),
                    4,
                )
            except (TypeError, ValueError):
                pass
        if existing_field is not None:
            generated_field["confirmed_by_user"] = bool(existing_field.get("confirmed_by_user", False))
            generated_field["source"] = _normalize_semantic_field_source(
                existing_field.get("source"),
                default="manual_confirmed" if generated_field.get("confirmed_by_user") else generated_source,
            )
        elif existing_label:
            generated_field["confirmed_by_user"] = False
            generated_field["source"] = generated_source
        generated_fields_by_name[raw_name] = generated_field

    merged_fields = [
        generated_fields_by_name.get(_safe_text(item.get("raw_name")), item)
        for item in generated_fields
    ]
    low_confidence_fields = [
        _safe_text(item.get("raw_name"))
        for item in merged_fields
        if _safe_text(item.get("raw_name"))
        and float(item.get("confidence") or 0.0) < SEMANTIC_FIELD_CONFIDENCE_THRESHOLD
        and not bool(item.get("confirmed_by_user"))
    ]

    merged_profile["field_label_map"] = next_field_label_map
    merged_profile["fields"] = merged_fields
    merged_profile["low_confidence_fields"] = low_confidence_fields
    return merged_profile


def _refresh_dataset_semantic_profile(
    *,
    dataset_row: dict[str, Any],
    source_row: dict[str, Any] | None,
    sample_rows: list[dict[str, Any]] | None = None,
    status: str = "",
    allow_llm: bool = False,
) -> dict[str, Any] | None:
    rows = [row for row in (sample_rows or []) if isinstance(row, dict)]
    semantic_profile = _build_semantic_profile(
        dataset_row=dataset_row,
        source_row=source_row,
        sample_rows=rows,
        status=status or ("generated_with_samples" if rows else "generated_basic"),
        allow_llm=allow_llm,
    )
    semantic_profile = _merge_existing_semantic_profile(
        generated_profile=semantic_profile,
        existing_profile=_extract_semantic_profile(dataset_row),
    )
    updated = _persist_dataset_semantic_profile(
        dataset_row=dataset_row,
        semantic_profile=semantic_profile,
    )
    return updated or dataset_row


def _resolve_dataset_row(
    *,
    company_id: str,
    arguments: dict[str, Any],
) -> dict[str, Any] | None:
    dataset_id = _dataset_id_from_args(arguments)
    if dataset_id:
        dataset_row = auth_db.get_unified_data_source_dataset_by_id(
            company_id=company_id,
            dataset_id=dataset_id,
        )
        if dataset_row:
            return dataset_row

    source_id = _source_id_from_args(arguments)
    if not source_id:
        return None
    dataset_code = _sanitize_dataset_code(arguments.get("dataset_code"))
    resource_key = _safe_text(arguments.get("resource_key"))
    rows = auth_db.list_unified_data_source_datasets(
        company_id=company_id,
        data_source_id=source_id,
        status=None,
        include_deleted=True,
        limit=2000,
    )
    if dataset_code:
        return next((item for item in rows if _safe_text(item.get("dataset_code")) == dataset_code), None)
    if resource_key:
        return next((item for item in rows if _safe_text(item.get("resource_key")) == resource_key), None)
    return rows[0] if rows else None


def _normalize_manual_semantic_patch(
    arguments: dict[str, Any],
    *,
    valid_field_names: set[str],
) -> dict[str, Any]:
    patch = dict(arguments.get("semantic_profile") or {})
    for key in ("business_name", "business_description", "key_fields", "field_label_map", "fields", "status"):
        if arguments.get(key) is not None:
            patch[key] = arguments.get(key)

    normalized: dict[str, Any] = {}
    if patch.get("business_name") is not None:
        name = _safe_text(patch.get("business_name"))
        if name:
            normalized["business_name"] = name
    if patch.get("business_description") is not None:
        normalized["business_description"] = _safe_text(patch.get("business_description"))

    key_fields = patch.get("key_fields")
    if isinstance(key_fields, list):
        normalized["key_fields"] = [_safe_text(item) for item in key_fields if _safe_text(item)]

    field_label_map = patch.get("field_label_map")
    fields = patch.get("fields")
    if (isinstance(field_label_map, dict) or isinstance(fields, list)) and not valid_field_names:
        raise ValueError("当前数据集缺少 schema 字段定义，无法更新字段中文名或字段语义")

    if isinstance(field_label_map, dict):
        cleaned_map: dict[str, str] = {}
        for raw_name, display_name in field_label_map.items():
            raw_key = _safe_text(raw_name)
            if not raw_key:
                continue
            if raw_key not in valid_field_names:
                raise ValueError(f"field_label_map 包含不存在字段: {raw_key}")
            cleaned_map[raw_key] = _safe_text(display_name) or raw_key
        normalized["field_label_map"] = cleaned_map

    if isinstance(fields, list):
        cleaned_fields: list[dict[str, Any]] = []
        for item in fields:
            if not isinstance(item, dict):
                continue
            raw_name = _safe_text(item.get("raw_name"))
            if not raw_name:
                continue
            if raw_name not in valid_field_names:
                raise ValueError(f"fields 包含不存在字段: {raw_name}")
            confidence_value = item.get("confidence")
            try:
                confidence = float(confidence_value)
            except (TypeError, ValueError):
                confidence = 0.5
            cleaned_fields.append(
                {
                    "raw_name": raw_name,
                    "display_name": _safe_text(item.get("display_name")) or raw_name,
                    "semantic_type": _safe_text(item.get("semantic_type")) or "unknown",
                    "business_role": _safe_text(item.get("business_role")) or "unknown",
                    "description": _safe_text(item.get("description")),
                    "confidence": round(max(0.0, min(confidence, 1.0)), 4),
                    "sample_values": [str(v) for v in item.get("sample_values") or [] if _safe_text(v)],
                    "confirmed_by_user": bool(item.get("confirmed_by_user", False)),
                    "source": _normalize_semantic_field_source(
                        item.get("source"),
                        default="manual_confirmed" if bool(item.get("confirmed_by_user", False)) else "rule_fallback",
                    ),
                }
            )
        normalized["fields"] = cleaned_fields

    status = patch.get("status")
    if status is not None:
        normalized["status"] = _normalize_semantic_status(status, default="manual_updated")
    return normalized

def _load_source_configs(source_id: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for config_type in CONFIG_TYPES:
        config_row = auth_db.get_unified_data_source_config(
            data_source_id=source_id,
            config_type=config_type,
            active_only=True,
        )
        result[config_type] = dict((config_row or {}).get("config") or {})
    return result


async def _auto_refresh_datasets_and_samples(
    *,
    auth_token: str,
    company_id: str,
    source_row: dict[str, Any],
    mode: str = "",
    reason: str = "",
) -> dict[str, int]:
    summary = {"discovered": 0}
    source_kind = str(source_row.get("source_kind") or "")
    if source_kind != "database" or not auth_token:
        return summary

    source_id = str(source_row.get("id") or "")
    try:
        discover_args = {
            "auth_token": auth_token,
            "source_id": source_id,
            "persist": True,
            "limit": AUTO_DISCOVER_DATASET_LIMIT,
            "mode": mode,
        }
        discover_result = await _handle_data_source_discover_datasets(discover_args)
        if not discover_result.get("success"):
            return summary
        summary["discovered"] = int(discover_result.get("dataset_count") or 0)

        return summary
    except Exception as exc:
        logger.error("auto refresh datasets and samples failed: %s", exc, exc_info=True)
        return summary


def _load_runtime_source(
    source_row: dict[str, Any],
    *,
    include_secret: bool,
) -> dict[str, Any]:
    source_id = str(source_row.get("id") or "")
    configs = _load_source_configs(source_id)
    credential = auth_db.get_unified_data_source_credentials(
        data_source_id=source_id,
        credential_type="default",
        include_secret=include_secret,
    )
    runtime_source = {
        **source_row,
        "connection_config": configs.get("connection") or {},
        "extract_config": configs.get("extract") or {},
        "mapping_config": configs.get("mapping") or {},
        "runtime_config": configs.get("runtime") or {},
        "auth_config": dict((credential or {}).get("credential_payload") or {}),
    }
    connector = build_connector(runtime_source)
    runtime_source["capabilities"] = connector.capabilities
    return runtime_source


def _merge_runtime_overrides(runtime_source: dict[str, Any], arguments: dict[str, Any]) -> dict[str, Any]:
    connection_override = arguments.get("connection_config")
    if isinstance(connection_override, dict) and connection_override:
        runtime_source["connection_config"] = {
            **dict(runtime_source.get("connection_config") or {}),
            **connection_override,
        }

    auth_override = arguments.get("auth_config")
    if isinstance(auth_override, dict) and auth_override:
        runtime_source["auth_config"] = {
            **dict(runtime_source.get("auth_config") or {}),
            **auth_override,
        }

    return runtime_source


def _normalize_health_status(value: Any, *, default: str = "unknown") -> str:
    health_status = str(value or "").strip().lower() or default
    if health_status not in HEALTH_STATUSES:
        return default
    return health_status


def _normalize_dataset_origin_type(value: Any, *, default: str = "manual") -> str:
    origin_type = str(value or "").strip().lower() or default
    if origin_type not in DATASET_ORIGIN_TYPES:
        return default
    return origin_type


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _pick_latest_iso(values: list[Any]) -> str:
    latest: datetime | None = None
    for value in values:
        parsed = _parse_datetime(value)
        if not parsed:
            continue
        if latest is None or parsed > latest:
            latest = parsed
    return latest.isoformat() if latest else ""


def _sanitize_dataset_code(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    chars: list[str] = []
    for ch in text:
        chars.append(ch if ch.isalnum() else "_")
    cleaned = "".join(chars).strip("_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned[:128]


def _extract_catalog_profile(dataset_row: dict[str, Any]) -> dict[str, Any]:
    meta = dict(dataset_row.get("meta") or {})
    profile = meta.get("catalog_profile")
    if isinstance(profile, dict):
        return dict(profile)
    return {}


def _guess_schema_object_names(dataset_row: dict[str, Any]) -> tuple[str, str]:
    extract_config = dict(dataset_row.get("extract_config") or {})
    schema_name = _safe_text(dataset_row.get("schema_name")) or _safe_text(extract_config.get("schema"))
    object_name = (
        _safe_text(dataset_row.get("object_name"))
        or _safe_text(extract_config.get("table"))
        or _safe_text(extract_config.get("endpoint"))
    )
    if schema_name and object_name:
        return schema_name, object_name
    resource_key = _safe_text(dataset_row.get("resource_key"))
    if "." in resource_key and not schema_name:
        schema, name = resource_key.split(".", 1)
        return schema_name or _safe_text(schema), object_name or _safe_text(name)
    return schema_name, object_name


def _extract_dataset_field_names(dataset_row: dict[str, Any]) -> list[str]:
    names: list[str] = []
    schema_summary = dict(dataset_row.get("schema_summary") or {})
    columns = schema_summary.get("columns")
    if isinstance(columns, list):
        for item in columns:
            if not isinstance(item, dict):
                continue
            name = _safe_text(item.get("name") or item.get("column_name"))
            if name and name not in names:
                names.append(name)
    fields = schema_summary.get("fields")
    if isinstance(fields, list):
        for item in fields:
            name = _safe_text(item)
            if name and name not in names:
                names.append(name)
    semantic_profile = _extract_semantic_profile(dataset_row)
    for item in semantic_profile.get("fields") or []:
        if not isinstance(item, dict):
            continue
        raw_name = _safe_text(item.get("raw_name"))
        if raw_name and raw_name not in names:
            names.append(raw_name)
    return names


def _build_dataset_search_text(dataset_row: dict[str, Any], *, semantic_flat: dict[str, Any]) -> str:
    catalog_profile = _extract_catalog_profile(dataset_row)
    schema_name, object_name = _guess_schema_object_names(dataset_row)
    field_names = _extract_dataset_field_names(dataset_row)
    parts = [
        _safe_text(dataset_row.get("dataset_code")),
        _safe_text(dataset_row.get("dataset_name")),
        _safe_text(dataset_row.get("resource_key")),
        _safe_text(dataset_row.get("object_type")),
        _safe_text(schema_name),
        _safe_text(object_name),
        _safe_text(catalog_profile.get("business_domain")),
        _safe_text(catalog_profile.get("business_object_type")),
        _safe_text(catalog_profile.get("grain")),
        _safe_text(catalog_profile.get("search_text")),
        _safe_text(semantic_flat.get("business_name")),
        _safe_text(semantic_flat.get("business_description")),
    ]
    parts.extend(field_names[:100])
    token_text = " ".join(part for part in parts if part)
    return re.sub(r"\s+", " ", token_text).strip()


def _build_dataset_base_view(dataset_row: dict[str, Any]) -> dict[str, Any]:
    dataset_code = _safe_text(dataset_row.get("dataset_code"))
    semantic_flat = _flatten_semantic_profile(dataset_row)
    catalog_profile = _extract_catalog_profile(dataset_row)
    schema_name_guess, object_name_guess = _guess_schema_object_names(dataset_row)
    publish_status = _normalize_publish_status(
        dataset_row.get("publish_status")
        or catalog_profile.get("publish_status")
        or catalog_profile.get("status"),
        default="unpublished",
    )
    verified_status = _normalize_verified_status(
        dataset_row.get("verified_status") or catalog_profile.get("verified_status"),
        default="unverified",
    )
    object_type = (
        _safe_text(dataset_row.get("object_type"))
        or _safe_text(catalog_profile.get("object_type"))
        or _safe_text(dataset_row.get("dataset_kind"))
        or "table"
    )
    usage_count_value = (
        dataset_row.get("usage_count")
        if dataset_row.get("usage_count") is not None
        else catalog_profile.get("usage_count")
    )
    try:
        usage_count = max(0, int(usage_count_value or 0))
    except Exception:
        usage_count = 0
    last_used_at = dataset_row.get("last_used_at") or catalog_profile.get("last_used_at")
    schema_name = _safe_text(dataset_row.get("schema_name")) or _safe_text(catalog_profile.get("schema_name")) or schema_name_guess
    object_name = _safe_text(dataset_row.get("object_name")) or _safe_text(catalog_profile.get("object_name")) or object_name_guess
    search_text = _safe_text(dataset_row.get("search_text")) or _safe_text(catalog_profile.get("search_text"))
    if not search_text:
        search_text = _build_dataset_search_text(dataset_row, semantic_flat=semantic_flat)
    source_context = {
        "id": _safe_text(dataset_row.get("data_source_id") or dataset_row.get("source_id")),
        "name": _safe_text(dataset_row.get("source_name"))
        or _safe_text(dataset_row.get("data_source_name"))
        or _safe_text(dataset_row.get("data_source_id") or dataset_row.get("source_id")),
        "source_kind": _safe_text(dataset_row.get("source_kind")),
        "provider_code": _safe_text(dataset_row.get("provider_code")),
    }
    return {
        "id": _safe_text(dataset_row.get("id")),
        "data_source_id": _safe_text(dataset_row.get("data_source_id")),
        "source_name": _safe_text(dataset_row.get("source_name")) or _safe_text(dataset_row.get("data_source_name")),
        "data_source_name": _safe_text(dataset_row.get("data_source_name")) or _safe_text(dataset_row.get("source_name")),
        "source_kind": _safe_text(dataset_row.get("source_kind")),
        "provider_code": _safe_text(dataset_row.get("provider_code")),
        "dataset_code": dataset_code,
        "dataset_name": _safe_text(dataset_row.get("dataset_name")) or dataset_code,
        "resource_key": _safe_text(dataset_row.get("resource_key")) or "default",
        "dataset_kind": _safe_text(dataset_row.get("dataset_kind")) or "table",
        "origin_type": _safe_text(dataset_row.get("origin_type")) or "manual",
        "status": _safe_text(dataset_row.get("status")) or "active",
        "enabled": bool(dataset_row.get("is_enabled", True)),
        "health_status": _normalize_health_status(dataset_row.get("health_status")),
        "last_checked_at": dataset_row.get("last_checked_at"),
        "last_sync_at": dataset_row.get("last_sync_at"),
        "last_error_message": _safe_text(dataset_row.get("last_error_message")),
        "publish_status": publish_status,
        "business_domain": _safe_text(dataset_row.get("business_domain")) or _safe_text(catalog_profile.get("business_domain")),
        "business_object_type": _safe_text(dataset_row.get("business_object_type"))
        or _safe_text(catalog_profile.get("business_object_type")),
        "grain": _safe_text(dataset_row.get("grain")) or _safe_text(catalog_profile.get("grain")),
        "verified_status": verified_status,
        "schema_name": schema_name,
        "object_name": object_name,
        "object_type": object_type,
        "usage_count": usage_count,
        "last_used_at": last_used_at,
        "search_text": search_text,
        "semantic_status": semantic_flat["semantic_status"],
        "semantic_updated_at": semantic_flat["semantic_updated_at"],
        "business_name": semantic_flat["business_name"] or (_safe_text(dataset_row.get("dataset_name")) or dataset_code),
        "business_description": semantic_flat["business_description"],
        "key_fields": semantic_flat["key_fields"],
        "semantic_pending_count": semantic_flat["semantic_pending_count"],
        "source": source_context,
        "created_at": dataset_row.get("created_at"),
        "updated_at": dataset_row.get("updated_at"),
    }


def _build_dataset_view(dataset_row: dict[str, Any], *, include_heavy: bool = True) -> dict[str, Any]:
    base = _build_dataset_base_view(dataset_row)
    if not include_heavy:
        return base
    semantic_flat = _flatten_semantic_profile(dataset_row)
    return {
        **base,
        "extract_config": dict(dataset_row.get("extract_config") or {}),
        "schema_summary": dict(dataset_row.get("schema_summary") or {}),
        "sync_strategy": dict(dataset_row.get("sync_strategy") or {}),
        "metadata": dict(dataset_row.get("meta") or {}),
        "collection_config": dict(_extract_catalog_profile(dataset_row).get("collection_config") or {}),
        "field_label_map": semantic_flat["field_label_map"],
        "semantic_fields": semantic_flat["semantic_fields"],
        "low_confidence_fields": semantic_flat["low_confidence_fields"],
    }


def _enrich_dataset_rows_with_source_context(*, company_id: str, dataset_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_ids = {
        _safe_text(row.get("data_source_id"))
        for row in dataset_rows
        if isinstance(row, dict) and _safe_text(row.get("data_source_id"))
    }
    if not source_ids:
        return dataset_rows

    try:
        source_rows = auth_db.list_unified_data_sources(company_id=company_id, include_deleted=False)
    except Exception as exc:
        logger.warning("list dataset candidates source enrichment skipped: company_id=%s error=%s", company_id, exc)
        return dataset_rows
    source_map = {
        _safe_text(item.get("id")): item
        for item in source_rows
        if isinstance(item, dict) and _safe_text(item.get("id")) in source_ids
    }
    if not source_map:
        return dataset_rows

    enriched_rows: list[dict[str, Any]] = []
    for row in dataset_rows:
        if not isinstance(row, dict):
            continue
        enriched = dict(row)
        source_row = source_map.get(_safe_text(enriched.get("data_source_id")))
        if source_row:
            source_name = _safe_text(source_row.get("name"))
            enriched["source_name"] = _safe_text(enriched.get("source_name")) or source_name
            enriched["data_source_name"] = _safe_text(enriched.get("data_source_name")) or source_name
            enriched["source_kind"] = _safe_text(enriched.get("source_kind")) or _safe_text(source_row.get("source_kind"))
            enriched["provider_code"] = _safe_text(enriched.get("provider_code")) or _safe_text(source_row.get("provider_code"))
        enriched_rows.append(enriched)
    return enriched_rows


def _summarize_datasets(dataset_rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    by_health: dict[str, int] = {}
    by_publish_status: dict[str, int] = {}
    by_verified_status: dict[str, int] = {}
    enabled_count = 0
    active_count = 0
    published_count = 0
    for row in dataset_rows:
        status = str(row.get("status") or "active")
        health_status = _normalize_health_status(row.get("health_status"))
        publish_status = _normalize_publish_status(
            row.get("publish_status") or _extract_catalog_profile(row).get("publish_status"),
            default="unpublished",
        )
        verified_status = _normalize_verified_status(
            row.get("verified_status") or _extract_catalog_profile(row).get("verified_status"),
            default="unverified",
        )
        by_status[status] = by_status.get(status, 0) + 1
        by_health[health_status] = by_health.get(health_status, 0) + 1
        by_publish_status[publish_status] = by_publish_status.get(publish_status, 0) + 1
        by_verified_status[verified_status] = by_verified_status.get(verified_status, 0) + 1
        if bool(row.get("is_enabled", True)):
            enabled_count += 1
        if status == "active":
            active_count += 1
        if publish_status == "published":
            published_count += 1
    return {
        "total": len(dataset_rows),
        "active_count": active_count,
        "enabled_count": enabled_count,
        "published_count": published_count,
        "by_status": by_status,
        "by_health_status": by_health,
        "by_publish_status": by_publish_status,
        "by_verified_status": by_verified_status,
        "last_sync_at": _pick_latest_iso([row.get("last_sync_at") for row in dataset_rows]),
        "last_checked_at": _pick_latest_iso([row.get("last_checked_at") for row in dataset_rows]),
    }


def _build_source_summary(source_row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(source_row.get("id") or ""),
        "code": str(source_row.get("code") or ""),
        "name": str(source_row.get("name") or ""),
        "source_kind": str(source_row.get("source_kind") or ""),
        "provider_code": str(source_row.get("provider_code") or ""),
        "domain_type": str(source_row.get("domain_type") or ""),
        "execution_mode": str(source_row.get("execution_mode") or ""),
        "status": str(source_row.get("status") or "active"),
        "enabled": bool(source_row.get("is_enabled", True)),
    }


def _build_health_summary(source_row: dict[str, Any], dataset_rows: list[dict[str, Any]]) -> dict[str, Any]:
    source_status = str(source_row.get("status") or "active")
    source_enabled = bool(source_row.get("is_enabled", True))
    source_health_status = _normalize_health_status(source_row.get("health_status"))
    source_last_error = str(source_row.get("last_error_message") or "")
    source_last_checked_at = source_row.get("last_checked_at")
    dataset_summary = _summarize_datasets(dataset_rows)
    dataset_health = dict(dataset_summary.get("by_health_status") or {})

    overall_status = "unknown"
    if source_status == "disabled" or not source_enabled:
        overall_status = "disabled"
    elif source_health_status in {"error", "auth_expired", "disabled"}:
        overall_status = "error"
    elif (dataset_health.get("error", 0) + dataset_health.get("auth_expired", 0) + dataset_health.get("disabled", 0)) > 0:
        overall_status = "error"
    elif source_health_status == "warning" or dataset_health.get("warning", 0) > 0:
        overall_status = "warning"
    elif source_health_status == "healthy" or dataset_health.get("healthy", 0) > 0:
        overall_status = "healthy"

    return {
        "overall_status": overall_status,
        "source": {
            "health_status": source_health_status,
            "last_checked_at": source_last_checked_at,
            "last_error_message": source_last_error,
        },
        "datasets": {
            "total": int(dataset_summary.get("total") or 0),
            "by_health_status": dataset_health,
            "last_checked_at": dataset_summary.get("last_checked_at"),
            "last_sync_at": dataset_summary.get("last_sync_at"),
        },
    }


def _list_datasets_with_compat(
    *,
    company_id: str,
    data_source_id: str | None = None,
    status: str | None = None,
    include_deleted: bool = False,
    keyword: str = "",
    schema_name: str = "",
    object_type: str = "",
    publish_status: str = "",
    business_object_type: str = "",
    verified_status: str = "",
    only_published: bool = False,
    page: int = 1,
    page_size: int = 50,
    sort_by: str = "",
    lightweight: bool = False,
) -> list[dict[str, Any]]:
    # 兼容不同版本 db.py：如果新签名存在就透传，不存在则回退到基础查询+内存过滤。
    fn = auth_db.list_unified_data_source_datasets
    signature = inspect.signature(fn)
    params = signature.parameters
    requested: dict[str, Any] = {
        "company_id": company_id,
        "data_source_id": data_source_id,
        "status": status,
        "include_deleted": include_deleted,
        "keyword": keyword,
        "schema_name": schema_name,
        "object_type": object_type,
        "publish_status": publish_status,
        "business_object_type": business_object_type,
        "verified_status": verified_status,
        "only_published": only_published,
        "limit": max(500, min(page * page_size + page_size, 2000)),
        "page": page,
        "page_size": page_size,
        "sort_by": sort_by,
        "lightweight": lightweight,
    }
    kwargs = {key: value for key, value in requested.items() if key in params and value is not None}
    rows = fn(**kwargs)
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, dict)]


def _query_datasets_with_compat(
    *,
    company_id: str,
    data_source_id: str | None = None,
    status: str | None = None,
    include_deleted: bool = False,
    keyword: str = "",
    schema_name: str = "",
    object_type: str = "",
    publish_status: str = "",
    business_object_type: str = "",
    verified_status: str = "",
    only_published: bool = False,
    page: int = 1,
    page_size: int = 50,
    sort_by: str = "",
    lightweight: bool = False,
) -> dict[str, Any] | None:
    query_fn = getattr(auth_db, "query_unified_data_source_datasets", None)
    if not callable(query_fn):
        return None

    signature = inspect.signature(query_fn)
    params = signature.parameters
    requested: dict[str, Any] = {
        "company_id": company_id,
        "data_source_id": data_source_id,
        "status": status,
        "include_deleted": include_deleted,
        "keyword": keyword,
        "schema_name": schema_name,
        "object_type": object_type,
        "publish_status": publish_status,
        "business_object_type": business_object_type,
        "verified_status": verified_status,
        "only_published": only_published,
        "page": page,
        "page_size": page_size,
        "sort_by": sort_by,
        "lightweight": lightweight,
        "limit": max(500, min(page * page_size + page_size, 2000)),
    }
    kwargs = {key: value for key, value in requested.items() if key in params and value is not None}
    result = query_fn(**kwargs)
    if not isinstance(result, dict):
        return None
    items = [dict(row) for row in (result.get("items") or []) if isinstance(row, dict)]
    return {
        "items": items,
        "total": int(result.get("total") or len(items)),
        "page": int(result.get("page") or page),
        "page_size": int(result.get("page_size") or page_size),
    }


def _contains_tokens(value: str, keyword: str) -> bool:
    normalized = value.lower()
    tokens = [token for token in _tokenize_identifier(keyword) if token]
    if not tokens:
        return True
    return all(token in normalized for token in tokens)


def _normalize_candidate_token(value: Any) -> str:
    text = _safe_text(value).lower()
    if not text:
        return ""
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text)


def _extract_dataset_field_tokens(dataset_row: dict[str, Any]) -> set[str]:
    tokens: set[str] = set()

    def add(value: Any) -> None:
        normalized = _normalize_candidate_token(value)
        if normalized:
            tokens.add(normalized)

    for name in _extract_dataset_field_names(dataset_row):
        add(name)

    semantic_profile = _extract_semantic_profile(dataset_row)
    field_label_map = dict(semantic_profile.get("field_label_map") or {})
    for raw_name, display_name in field_label_map.items():
        add(raw_name)
        add(display_name)
    for item in semantic_profile.get("fields") or []:
        if not isinstance(item, dict):
            continue
        add(item.get("raw_name"))
        add(item.get("display_name"))
        add(item.get("name"))
        add(item.get("semantic_role"))
        add(item.get("description"))
    for item in semantic_profile.get("key_fields") or []:
        add(item)

    return tokens


def _field_alias_group_matches(field_tokens: set[str], aliases: tuple[str, ...] | list[str]) -> bool:
    normalized_aliases = [_normalize_candidate_token(item) for item in aliases if _normalize_candidate_token(item)]
    if not normalized_aliases:
        return False
    for alias in normalized_aliases:
        for token in field_tokens:
            if token == alias:
                return True
            if len(alias) >= 4 and alias in token:
                return True
            if len(token) >= 4 and token in alias:
                return True
    return False


def _dataset_alias_group_coverage(
    dataset_row: dict[str, Any],
    alias_groups: list[tuple[str, ...]] | tuple[tuple[str, ...], ...],
) -> float:
    groups = [tuple(group) for group in alias_groups if group]
    if not groups:
        return 1.0
    field_tokens = _extract_dataset_field_tokens(dataset_row)
    if not field_tokens:
        return 0.0
    matched = len([group for group in groups if _field_alias_group_matches(field_tokens, group)])
    return matched / max(1, len(groups))


def _normalize_candidate_string_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [_safe_text(item).lower() for item in value if _safe_text(item)]
    text = _safe_text(value).lower()
    return [text] if text else []


def _resolve_dataset_candidate_contract(
    *,
    scene_type: str,
    role_code: str,
    filters: dict[str, Any] | None,
) -> dict[str, Any]:
    flt = dict(filters or {})
    explicit_object_types = _normalize_candidate_string_list(
        flt.get("business_object_types") or flt.get("business_object_type")
    )
    explicit_grains = _normalize_candidate_string_list(flt.get("grains") or flt.get("grain"))
    explicit_required_fields = [
        _safe_text(item)
        for item in (flt.get("required_fields") or [])
        if _safe_text(item)
    ]
    explicit_alias_groups = [
        tuple(_safe_text(alias) for alias in group if _safe_text(alias))
        for group in (flt.get("required_field_alias_groups") or [])
        if isinstance(group, (list, tuple))
    ]
    strict_contract = _normalize_bool(flt.get("strict_contract"), default=False)

    if explicit_object_types or explicit_grains or explicit_required_fields or explicit_alias_groups:
        alias_groups = explicit_alias_groups or [tuple([field]) for field in explicit_required_fields]
        return {
            "label": _safe_text(flt.get("contract_label")) or "显式契约",
            "business_object_types": explicit_object_types,
            "grains": explicit_grains,
            "required_field_alias_groups": alias_groups,
            "strict": strict_contract,
        }

    if scene_type not in {"recon", "proc"}:
        return {}

    hint_texts = [
        _safe_text(item)
        for item in (flt.get("hints") or [])
        if _safe_text(item)
    ]
    if not hint_texts:
        return {}

    normalized_hint_text = " ".join(_normalize_candidate_token(item) for item in hint_texts if item)
    if not normalized_hint_text:
        return {}

    best_name = ""
    best_score = 0
    for contract_name, contract in _CANDIDATE_CONTRACT_LIBRARY.items():
        score = 0
        for alias in contract.get("hint_aliases") or ():
            normalized_alias = _normalize_candidate_token(alias)
            if normalized_alias and normalized_alias in normalized_hint_text:
                score += 1
        if role_code in {"left", "right"} and contract_name in {"business_order", "payment_bill", "platform_order"}:
            score += 1
        if score > best_score:
            best_name = contract_name
            best_score = score

    if not best_name:
        return {}

    contract = dict(_CANDIDATE_CONTRACT_LIBRARY[best_name])
    return {
        "label": _safe_text(contract.get("label") or best_name),
        "business_object_types": [item.lower() for item in contract.get("business_object_types") or () if _safe_text(item)],
        "grains": [item.lower() for item in contract.get("grains") or () if _safe_text(item)],
        "required_field_alias_groups": [
            tuple(_safe_text(alias) for alias in group if _safe_text(alias))
            for group in contract.get("required_field_alias_groups") or ()
            if group
        ],
        "strict": strict_contract,
    }


def _dataset_matches_filters(
    dataset_row: dict[str, Any],
    *,
    keyword: str = "",
    schema_name: str = "",
    object_type: str = "",
    publish_status: str = "",
    business_object_type: str = "",
    verified_status: str = "",
    only_published: bool = False,
) -> bool:
    view = _build_dataset_base_view(dataset_row)
    if only_published and view.get("publish_status") != "published":
        return False
    if publish_status and _safe_text(view.get("publish_status")).lower() != publish_status:
        return False
    if schema_name and _safe_text(view.get("schema_name")).lower() != schema_name:
        return False
    if object_type and _safe_text(view.get("object_type")).lower() != object_type:
        return False
    if business_object_type and _safe_text(view.get("business_object_type")).lower() != business_object_type:
        return False
    if verified_status and _safe_text(view.get("verified_status")).lower() != verified_status:
        return False
    if keyword:
        search_text = _safe_text(view.get("search_text"))
        if not _contains_tokens(search_text, keyword):
            return False
    return True


def _sort_datasets(dataset_rows: list[dict[str, Any]], sort_by: str) -> list[dict[str, Any]]:
    normalized = _safe_text(sort_by).lower()
    if not normalized:
        normalized = "-updated_at"
    reverse = normalized.startswith("-") or normalized.endswith(":desc") or normalized.endswith("_desc")
    field = normalized[1:] if normalized.startswith("-") else normalized
    field = field.replace(":desc", "").replace(":asc", "").replace("_desc", "").replace("_asc", "")
    if field not in {
        "updated_at",
        "created_at",
        "dataset_name",
        "business_name",
        "usage_count",
        "last_used_at",
        "last_sync_at",
        "publish_status",
        "verified_status",
    }:
        field = "updated_at"
        reverse = True

    def _sort_key(row: dict[str, Any]) -> Any:
        view = _build_dataset_base_view(row)
        value = view.get(field)
        if field in {"updated_at", "created_at", "last_used_at", "last_sync_at"}:
            parsed = _parse_datetime(value)
            return parsed or datetime.fromtimestamp(0, timezone.utc)
        if field == "usage_count":
            try:
                return int(value or 0)
            except Exception:
                return 0
        return _safe_text(value).lower()

    return sorted(dataset_rows, key=_sort_key, reverse=reverse)


def _paginate_rows(rows: list[dict[str, Any]], *, page: int, page_size: int) -> tuple[list[dict[str, Any]], int]:
    total = len(rows)
    start = max(0, (page - 1) * page_size)
    end = start + page_size
    return rows[start:end], total


def _dataset_field_coverage(dataset_row: dict[str, Any], required_fields: list[str]) -> float:
    required = {_safe_text(item).lower() for item in required_fields if _safe_text(item)}
    if not required:
        return 1.0
    actual = {_safe_text(item).lower() for item in _extract_dataset_field_names(dataset_row)}
    if not actual:
        return 0.0
    matched = len([item for item in required if item in actual])
    return matched / max(1, len(required))


def _score_dataset_candidate(
    dataset_row: dict[str, Any],
    *,
    role_code: str = "",
    filters: dict[str, Any] | None = None,
) -> tuple[float, str]:
    view = _build_dataset_base_view(dataset_row)
    flt = dict(filters or {})
    score = 0.0
    reasons: list[str] = []
    if view.get("publish_status") == "published":
        score += 45.0
        reasons.append("已发布")
    if view.get("status") == "active" and bool(view.get("enabled")):
        score += 20.0
        reasons.append("可用状态")
    if view.get("verified_status") == "verified":
        score += 20.0
        reasons.append("已验证")
    elif view.get("verified_status") == "unverified":
        score += 8.0
        reasons.append("未验证")
    usage_count = int(view.get("usage_count") or 0)
    if usage_count > 0:
        score += min(10.0, usage_count / 5.0)
        reasons.append("历史复用")
    expected_object_types = _normalize_candidate_string_list(
        flt.get("business_object_types") or flt.get("business_object_type")
    )
    actual_business_object_type = _safe_text(view.get("business_object_type")).lower()
    if expected_object_types:
        if actual_business_object_type in expected_object_types:
            score += 10.0
            reasons.append("业务类型匹配")
        else:
            score -= 8.0
    expected_grains = _normalize_candidate_string_list(flt.get("grains") or flt.get("grain"))
    actual_grain = _safe_text(view.get("grain")).lower()
    if expected_grains:
        if actual_grain in expected_grains:
            score += 6.0
            reasons.append("粒度匹配")
        else:
            score -= 4.0
    required_fields = [item for item in flt.get("required_fields") or [] if isinstance(item, str)]
    required_field_alias_groups = [
        tuple(_safe_text(alias) for alias in group if _safe_text(alias))
        for group in (flt.get("required_field_alias_groups") or [])
        if isinstance(group, (list, tuple))
    ]
    coverage_scores: list[float] = []
    if required_fields:
        coverage_scores.append(_dataset_field_coverage(dataset_row, required_fields))
    if required_field_alias_groups:
        coverage_scores.append(_dataset_alias_group_coverage(dataset_row, required_field_alias_groups))
    coverage = max(coverage_scores) if coverage_scores else 1.0
    if required_fields or required_field_alias_groups:
        score += coverage * 15.0
        reasons.append(f"字段覆盖率 {int(round(coverage * 100))}%")
    if role_code in {"left", "right"}:
        score += 2.0
    if not reasons:
        reasons.append("基础匹配")
    return round(score, 2), "；".join(reasons[:4])


def _build_catalog_patch(arguments: dict[str, Any], *, publish_status_default: str) -> dict[str, Any]:
    patch = dict(arguments.get("catalog_profile") or {})
    direct_fields = {
        "schema_name",
        "object_name",
        "object_type",
        "publish_status",
        "business_domain",
        "business_object_type",
        "grain",
        "verified_status",
        "usage_count",
        "last_used_at",
        "search_text",
    }
    for key in direct_fields:
        if arguments.get(key) is not None:
            patch[key] = arguments.get(key)
    if isinstance(arguments.get("collection_config"), dict):
        patch["collection_config"] = dict(arguments.get("collection_config") or {})
    patch["publish_status"] = _normalize_publish_status(patch.get("publish_status"), default=publish_status_default)
    patch["verified_status"] = _normalize_verified_status(patch.get("verified_status"), default="unverified")
    patch["schema_name"] = _safe_text(patch.get("schema_name"))
    patch["object_name"] = _safe_text(patch.get("object_name"))
    patch["object_type"] = _safe_text(patch.get("object_type"))
    patch["business_domain"] = _safe_text(patch.get("business_domain"))
    patch["business_object_type"] = _safe_text(patch.get("business_object_type"))
    patch["grain"] = _safe_text(patch.get("grain"))
    patch["search_text"] = _safe_text(patch.get("search_text"))
    patch["last_used_at"] = _safe_text(patch.get("last_used_at"))
    if patch.get("usage_count") is not None:
        try:
            patch["usage_count"] = max(0, int(patch["usage_count"]))
        except Exception:
            patch["usage_count"] = 0
    patch["updated_at"] = _now_iso()
    return patch


def _upsert_dataset_with_profile(dataset_row: dict[str, Any], *, catalog_patch: dict[str, Any]) -> dict[str, Any] | None:
    meta = dict(dataset_row.get("meta") or {})
    current_catalog_profile = _extract_catalog_profile(dataset_row)
    next_catalog_profile = {**current_catalog_profile, **catalog_patch}
    semantic_profile = _extract_semantic_profile(dataset_row)
    if semantic_profile:
        if catalog_patch.get("publish_status"):
            semantic_profile["publish_status"] = catalog_patch.get("publish_status")
        if catalog_patch.get("verified_status"):
            semantic_profile["verified_status"] = catalog_patch.get("verified_status")
    meta["catalog_profile"] = next_catalog_profile
    if semantic_profile:
        meta["semantic_profile"] = semantic_profile

    kwargs: dict[str, Any] = {
        "company_id": _safe_text(dataset_row.get("company_id")),
        "data_source_id": _safe_text(dataset_row.get("data_source_id")),
        "dataset_code": _safe_text(dataset_row.get("dataset_code")),
        "dataset_name": _safe_text(dataset_row.get("dataset_name")),
        "resource_key": _safe_text(dataset_row.get("resource_key")) or "default",
        "dataset_kind": _safe_text(dataset_row.get("dataset_kind")) or "table",
        "origin_type": _safe_text(dataset_row.get("origin_type")) or "manual",
        "extract_config": dict(dataset_row.get("extract_config") or {}),
        "schema_summary": dict(dataset_row.get("schema_summary") or {}),
        "sync_strategy": dict(dataset_row.get("sync_strategy") or {}),
        "status": _safe_text(dataset_row.get("status")) or "active",
        "is_enabled": bool(dataset_row.get("is_enabled", True)),
        "health_status": _normalize_health_status(dataset_row.get("health_status")),
        "last_checked_at": dataset_row.get("last_checked_at"),
        "last_sync_at": dataset_row.get("last_sync_at"),
        "last_error_message": _safe_text(dataset_row.get("last_error_message")),
        "meta": meta,
    }
    optional_top_level = {
        "schema_name": catalog_patch.get("schema_name"),
        "object_name": catalog_patch.get("object_name"),
        "object_type": catalog_patch.get("object_type"),
        "publish_status": catalog_patch.get("publish_status"),
        "business_domain": catalog_patch.get("business_domain"),
        "business_object_type": catalog_patch.get("business_object_type"),
        "grain": catalog_patch.get("grain"),
        "verified_status": catalog_patch.get("verified_status"),
        "usage_count": catalog_patch.get("usage_count"),
        "last_used_at": catalog_patch.get("last_used_at"),
        "search_text": catalog_patch.get("search_text"),
    }
    supported = set(inspect.signature(auth_db.upsert_unified_data_source_dataset).parameters)
    for key, value in optional_top_level.items():
        if key in supported and value not in (None, ""):
            kwargs[key] = value
    return auth_db.upsert_unified_data_source_dataset(**kwargs)


def _load_source_datasets(company_id: str, source_id: str) -> list[dict[str, Any]]:
    return auth_db.list_unified_data_source_datasets(
        company_id=company_id,
        data_source_id=source_id,
        status=None,
        include_deleted=False,
        limit=2000,
    )


def _update_dataset_health_by_resource(
    *,
    company_id: str,
    source_id: str,
    resource_key: str,
    health_status: str,
    last_error_message: str = "",
    last_sync_at: str | None = None,
) -> dict[str, Any] | None:
    dataset_row = auth_db.get_unified_data_source_dataset_by_source_resource(
        company_id=company_id,
        data_source_id=source_id,
        resource_key=resource_key,
        status=None,
    )
    if not dataset_row:
        return None
    return auth_db.update_unified_data_source_dataset_health(
        dataset_id=str(dataset_row.get("id") or ""),
        health_status=_normalize_health_status(health_status, default="unknown"),
        last_sync_at=last_sync_at,
        last_error_message=last_error_message,
    )


def _normalize_discovered_dataset(item: dict[str, Any], source_row: dict[str, Any], index: int) -> dict[str, Any]:
    resource_key = str(item.get("resource_key") or item.get("dataset_code") or f"default_{index + 1}").strip()
    dataset_code = _sanitize_dataset_code(item.get("dataset_code") or resource_key)
    if not dataset_code:
        dataset_code = f"dataset_{index + 1}"
    dataset_name = str(item.get("dataset_name") or resource_key or dataset_code).strip() or dataset_code
    return {
        "dataset_code": dataset_code[:128],
        "dataset_name": dataset_name[:255],
        "resource_key": resource_key[:100] or "default",
        "dataset_kind": str(item.get("dataset_kind") or "table")[:30],
        "origin_type": _normalize_dataset_origin_type(item.get("origin_type"), default="discovered"),
        "extract_config": dict(item.get("extract_config") or {}),
        "schema_summary": dict(item.get("schema_summary") or {}),
        "sync_strategy": dict(item.get("sync_strategy") or {}),
        "status": _normalize_status(item.get("status"), default="active"),
        "is_enabled": _normalize_bool(item.get("is_enabled"), default=True),
        "health_status": _normalize_health_status(item.get("health_status"), default="unknown"),
        "last_checked_at": item.get("last_checked_at"),
        "last_sync_at": item.get("last_sync_at"),
        "last_error_message": str(item.get("last_error_message") or ""),
        "meta": {
            **dict(item.get("meta") or {}),
            "discovered_from": str(source_row.get("source_kind") or ""),
            "discovered_provider": str(source_row.get("provider_code") or ""),
        },
    }


def _build_data_source_view(
    source_row: dict[str, Any],
    *,
    datasets: list[dict[str, Any]] | None = None,
    include_dataset_details: bool = False,
) -> dict[str, Any]:
    runtime_source = _load_runtime_source(source_row, include_secret=False)
    source_id = str(source_row.get("id") or "")
    company_id = str(source_row.get("company_id") or "")
    dataset_rows = datasets if datasets is not None else _load_source_datasets(company_id, source_id)
    dataset_summary = _summarize_datasets(dataset_rows)
    health_summary = _build_health_summary(source_row, dataset_rows)
    latest_jobs = auth_db.list_unified_sync_jobs(
        company_id=company_id,
        data_source_id=source_id,
        limit=1,
    )
    latest_job = latest_jobs[0] if latest_jobs else None
    meta = dict(source_row.get("meta") or {})
    result = {
        "id": str(source_row.get("id") or ""),
        "code": str(source_row.get("code") or ""),
        "name": str(source_row.get("name") or ""),
        "source_kind": str(source_row.get("source_kind") or ""),
        "domain_type": str(source_row.get("domain_type") or ""),
        "provider_code": str(source_row.get("provider_code") or ""),
        "execution_mode": str(source_row.get("execution_mode") or ""),
        "status": str(source_row.get("status") or "active"),
        "enabled": bool(source_row.get("is_enabled", True)),
        "capabilities": list(runtime_source.get("capabilities") or []),
        "auth_status": str(meta.get("auth_status") or ""),
        "description": str(source_row.get("description") or ""),
        "connection_config": dict(runtime_source.get("connection_config") or {}),
        "extract_config": dict(runtime_source.get("extract_config") or {}),
        "mapping_config": dict(runtime_source.get("mapping_config") or {}),
        "runtime_config": dict(runtime_source.get("runtime_config") or {}),
        "source_summary": _build_source_summary(source_row),
        "dataset_summary": dataset_summary,
        "health_summary": health_summary,
        "health_status": _normalize_health_status(source_row.get("health_status")),
        "last_checked_at": source_row.get("last_checked_at"),
        "last_error_message": str(source_row.get("last_error_message") or ""),
        "last_sync_at": (latest_job or {}).get("completed_at") or (latest_job or {}).get("updated_at"),
        "last_sync_job_id": str((latest_job or {}).get("id") or ""),
        "last_sync_status": str((latest_job or {}).get("job_status") or ""),
        "created_at": source_row.get("created_at"),
        "updated_at": source_row.get("updated_at"),
        "discover_summary": dict(meta.get("discover_summary") or {}),
        "metadata": meta,
    }
    if include_dataset_details:
        result["datasets"] = [_build_dataset_view(row) for row in dataset_rows]
    return result


def _update_source_meta(source_row: dict[str, Any], *, meta_updates: dict[str, Any]) -> dict[str, Any] | None:
    meta = dict(source_row.get("meta") or {})
    meta.update(meta_updates)
    return auth_db.upsert_unified_data_source(
        company_id=str(source_row.get("company_id") or ""),
        code=str(source_row.get("code") or ""),
        name=str(source_row.get("name") or ""),
        source_kind=str(source_row.get("source_kind") or ""),
        domain_type=str(source_row.get("domain_type") or ""),
        provider_code=str(source_row.get("provider_code") or ""),
        execution_mode=str(source_row.get("execution_mode") or "deterministic"),
        description=str(source_row.get("description") or ""),
        status=str(source_row.get("status") or "active"),
        is_enabled=bool(source_row.get("is_enabled", True)),
        health_status=str(source_row.get("health_status") or "unknown"),
        last_checked_at=source_row.get("last_checked_at"),
        last_error_message=str(source_row.get("last_error_message") or ""),
        meta=meta,
    )


def _build_discover_summary(
    *,
    dataset_summary: dict[str, Any],
    scan_summary: dict[str, Any] | None,
    status: str,
    error_message: str = "",
) -> dict[str, Any]:
    scan = dict(scan_summary or {})
    return {
        "discovered_count": int(dataset_summary.get("total") or 0),
        "enabled_count": int(dataset_summary.get("enabled_count") or 0),
        "last_discover_at": datetime.now(timezone.utc).isoformat(),
        "last_discover_status": status,
        "last_discover_error": error_message or None,
        "scan_mode": str(scan.get("mode") or "batch"),
        "scanned_count": int(scan.get("scanned_count") or 0),
        "total_count": int(scan.get("total_count") or 0),
        "offset": int(scan.get("offset") or 0),
        "requested_limit": int(scan.get("requested_limit") or 0),
        "has_more": bool(scan.get("has_more")),
        "next_offset": int(scan.get("next_offset")) if scan.get("next_offset") is not None else None,
        "requested_count": int(scan.get("requested_count") or 0),
        "matched_count": int(scan.get("matched_count") or 0),
        "missing_targets": [str(item) for item in (scan.get("missing_targets") or []) if str(item).strip()],
    }


def _upsert_source_configs(company_id: str, source_id: str, arguments: dict[str, Any]) -> None:
    config_mapping = {
        "connection_config": "connection",
        "extract_config": "extract",
        "mapping_config": "mapping",
        "runtime_config": "runtime",
    }
    for arg_key, config_type in config_mapping.items():
        if arguments.get(arg_key) is None:
            continue
        auth_db.upsert_unified_data_source_config(
            company_id=company_id,
            data_source_id=source_id,
            config_type=config_type,
            config=dict(arguments.get(arg_key) or {}),
            is_active=True,
        )

    if arguments.get("auth_config") is not None:
        auth_db.upsert_unified_data_source_credentials(
            company_id=company_id,
            data_source_id=source_id,
            credential_type="default",
            credential_payload=dict(arguments.get("auth_config") or {}),
            extra={},
        )


def _sync_rows_from_payload(result: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(result.get("rows"), list):
        return [row for row in result.get("rows") if isinstance(row, dict)]
    if isinstance(result.get("records"), list):
        return [row for row in result.get("records") if isinstance(row, dict)]
    payload = result.get("payload")
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        nested_rows = payload.get("rows")
        if isinstance(nested_rows, list):
            return [row for row in nested_rows if isinstance(row, dict)]
        if payload:
            return [payload]
    return []


def _build_raw_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for index, row in enumerate(rows):
        source_record_key = str(
            row.get("id")
            or row.get("item_key")
            or row.get("record_id")
            or row.get("biz_key")
            or row.get("shop_id")
            or index + 1
        )
        payload_hash = _hash_payload(row)
        dedupe_key = (source_record_key, payload_hash)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        records.append(
            {
                "source_record_key": source_record_key,
                "source_event_time": row.get("event_time") or row.get("updated_at"),
                "payload": row,
                "payload_hash": payload_hash,
            }
        )
    return records


def _build_snapshot_items(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for index, row in enumerate(rows):
        item_key = str(
            row.get("id")
            or row.get("item_key")
            or row.get("record_id")
            or row.get("biz_key")
            or row.get("shop_id")
            or index + 1
        )
        item_hash = _hash_payload(row)
        dedupe_key = (item_key, item_hash)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        items.append(
            {
                "item_key": item_key,
                "item_payload": row,
                "item_hash": item_hash,
            }
        )
    return items


def _build_checkpoint_after(
    before: dict[str, Any] | None,
    *,
    window_start: str | None,
    window_end: str | None,
    rows_count: int,
    result: dict[str, Any],
) -> dict[str, Any]:
    next_checkpoint = result.get("next_checkpoint")
    if isinstance(next_checkpoint, dict) and next_checkpoint:
        return next_checkpoint
    checkpoint_after = dict(before or {})
    checkpoint_after.update(
        {
            "last_window_start": window_start or "",
            "last_window_end": window_end or "",
            "last_synced_at": _now_iso(),
            "last_row_count": rows_count,
        }
    )
    return checkpoint_after


async def _run_connector_sync(
    source: dict[str, Any],
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if source["source_kind"] == "platform_oauth":
        list_result = await handle_platform_tool_call(
            "platform_list_connections",
            {
                "auth_token": arguments.get("auth_token"),
                "platform_code": source.get("provider_code"),
                "mode": arguments.get("mode", ""),
            },
        )
        if not list_result.get("success"):
            return list_result
        rows = []
        for item in list_result.get("connections") or []:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "shop_id": item.get("external_shop_id"),
                    "shop_name": item.get("external_shop_name"),
                    "auth_status": item.get("auth_status"),
                    "status": item.get("status"),
                    "last_sync_at": item.get("last_sync_at"),
                }
            )
        return {
            "success": True,
            "rows": rows,
            "healthy": True,
            "message": "平台店铺连接已同步为快照",
        }

    connector = build_connector(source)
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(connector.trigger_sync, arguments),
            timeout=max(1, CONNECTOR_SYNC_TIMEOUT_SECONDS),
        )
    except TimeoutError:
        return {
            "success": False,
            "healthy": False,
            "error": "采集查询超时或任务中断，请重新采集",
            "message": "采集查询超时或任务中断，请重新采集",
        }
    params = arguments.get("params") or {}
    if not _sync_rows_from_payload(result) and isinstance(params, dict) and isinstance(params.get("rows"), list):
        result = {
            **result,
            "rows": [row for row in params.get("rows") or [] if isinstance(row, dict)],
            "healthy": result.get("healthy", True),
        }
    return result


def _attach_aliases_to_job(job: dict[str, Any] | None) -> dict[str, Any] | None:
    if not job:
        return None
    return {
        **job,
        "sync_job_id": str(job.get("id") or ""),
        "source_id": str(job.get("data_source_id") or ""),
        "status": str(job.get("job_status") or ""),
        "finished_at": job.get("completed_at"),
    }


def create_tools() -> list[Tool]:
    source_id_schema = {
        "source_id": {"type": "string"},
        "data_source_id": {"type": "string", "description": "兼容旧字段名"},
    }
    dataset_id_schema = {
        "dataset_id": {"type": "string"},
        "id": {"type": "string", "description": "兼容字段名"},
    }
    return [
        Tool(
            name="data_source_list",
            description="列出当前企业的数据源配置。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "source_kind": {"type": "string"},
                    "domain_type": {"type": "string"},
                    "status": {"type": "string"},
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="data_source_get",
            description="获取单个数据源详情。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **source_id_schema,
                },
                "required": ["auth_token", "source_id"],
            },
        ),
        Tool(
            name="data_source_discover_datasets",
            description="自动发现数据源可用数据集，可选持久化为目录。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **source_id_schema,
                    "persist": {"type": "boolean"},
                    "limit": {"type": "integer"},
                    "schema_whitelist": {"type": "array", "items": {"type": "string"}},
                    "discover_mode": {"type": "string"},
                    "openapi_url": {"type": "string"},
                    "openapi_spec": {"type": ["object", "string"]},
                    "manual_endpoints": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["auth_token", "source_id"],
            },
        ),
        Tool(
            name="data_source_list_datasets",
            description="列出数据源的数据集目录。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **source_id_schema,
                    "status": {"type": "string"},
                    "include_deleted": {"type": "boolean"},
                    "limit": {"type": "integer"},
                    "keyword": {"type": "string"},
                    "schema_name": {"type": "string"},
                    "object_type": {"type": "string"},
                    "publish_status": {"type": "string"},
                    "business_object_type": {"type": "string"},
                    "verified_status": {"type": "string"},
                    "only_published": {"type": "boolean"},
                    "page": {"type": "integer"},
                    "page_size": {"type": "integer"},
                    "sort_by": {"type": "string"},
                    "include_heavy": {"type": "boolean"},
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="data_source_get_dataset",
            description="获取单个数据集目录详情。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **dataset_id_schema,
                    **source_id_schema,
                    "dataset_code": {"type": "string"},
                    "resource_key": {"type": "string"},
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="data_source_upsert_dataset",
            description="创建或更新数据集目录。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **source_id_schema,
                    "dataset_code": {"type": "string"},
                    "dataset_name": {"type": "string"},
                    "resource_key": {"type": "string"},
                    "dataset_kind": {"type": "string"},
                    "origin_type": {"type": "string"},
                    "extract_config": {"type": "object"},
                    "schema_summary": {"type": "object"},
                    "sync_strategy": {"type": "object"},
                    "status": {"type": "string"},
                    "enabled": {"type": "boolean"},
                    "health_status": {"type": "string"},
                    "last_checked_at": {"type": "string"},
                    "last_sync_at": {"type": "string"},
                    "last_error_message": {"type": "string"},
                    "meta": {"type": "object"},
                },
                "required": ["auth_token", "source_id", "dataset_code"],
            },
        ),
        Tool(
            name="data_source_disable_dataset",
            description="停用数据集目录项。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **dataset_id_schema,
                    "reason": {"type": "string"},
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="data_source_refresh_dataset_semantic_profile",
            description="基于 schema 与样本刷新数据集语义层（business_name/字段中文名等）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **dataset_id_schema,
                    **source_id_schema,
                    "dataset_code": {"type": "string"},
                    "resource_key": {"type": "string"},
                    "sample_limit": {"type": "integer"},
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="data_source_update_dataset_semantic_profile",
            description="手动更新数据集语义层（业务名称、字段中文名等）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **dataset_id_schema,
                    **source_id_schema,
                    "dataset_code": {"type": "string"},
                    "resource_key": {"type": "string"},
                    "semantic_profile": {"type": "object"},
                    "business_name": {"type": "string"},
                    "business_description": {"type": "string"},
                    "key_fields": {"type": "array", "items": {"type": "string"}},
                    "field_label_map": {"type": "object"},
                    "fields": {"type": "array", "items": {"type": "object"}},
                    "status": {"type": "string"},
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="data_source_publish_dataset",
            description="发布数据集并维护目录业务字段。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **dataset_id_schema,
                    **source_id_schema,
                    "dataset_code": {"type": "string"},
                    "resource_key": {"type": "string"},
                    "schema_name": {"type": "string"},
                    "object_name": {"type": "string"},
                    "object_type": {"type": "string"},
                    "business_domain": {"type": "string"},
                    "business_object_type": {"type": "string"},
                    "grain": {"type": "string"},
                    "verified_status": {"type": "string"},
                    "search_text": {"type": "string"},
                    "usage_count": {"type": "integer"},
                    "last_used_at": {"type": "string"},
                    "business_name": {"type": "string"},
                    "business_description": {"type": "string"},
                    "key_fields": {"type": "array", "items": {"type": "string"}},
                    "field_label_map": {"type": "object"},
                    "fields": {"type": "array", "items": {"type": "object"}},
                    "status": {"type": "string"},
                    "catalog_profile": {"type": "object"},
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="data_source_unpublish_dataset",
            description="取消发布数据集。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **dataset_id_schema,
                    **source_id_schema,
                    "dataset_code": {"type": "string"},
                    "resource_key": {"type": "string"},
                    "reason": {"type": "string"},
                    "catalog_profile": {"type": "object"},
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="data_source_list_dataset_candidates",
            description="按场景查询可选数据集候选。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "binding_scope": {"type": "string"},
                    "scene_type": {"type": "string"},
                    "role_code": {"type": "string"},
                    "keyword": {"type": "string"},
                    "filters": {"type": "object"},
                    "page": {"type": "integer"},
                    "page_size": {"type": "integer"},
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="data_source_import_openapi",
            description="通过 OpenAPI 文档导入 API 数据集（discover+upsert 封装）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **source_id_schema,
                    "openapi_url": {"type": "string"},
                    "openapi_spec": {"type": ["object", "string"]},
                    "persist": {"type": "boolean"},
                },
                "required": ["auth_token", "source_id"],
            },
        ),
        Tool(
            name="data_source_preflight_rule_binding",
            description="执行规则绑定预检，返回阻塞问题与健康摘要。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "binding_scope": {"type": "string"},
                    "binding_code": {"type": "string"},
                    "stale_after_minutes": {"type": "integer"},
                },
                "required": ["auth_token", "binding_scope", "binding_code"],
            },
        ),
        Tool(
            name="data_source_list_events",
            description="查询数据源事件日志。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **source_id_schema,
                    "sync_job_id": {"type": "string"},
                    "event_level": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="data_source_create",
            description="创建数据源配置。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "name": {"type": "string"},
                    "source_kind": {"type": "string"},
                    "provider_code": {"type": "string"},
                    "domain_type": {"type": "string"},
                    "execution_mode": {"type": "string"},
                    "description": {"type": "string"},
                    "status": {"type": "string"},
                    "enabled": {"type": "boolean"},
                    "connection_config": {"type": "object"},
                    "auth_config": {"type": "object"},
                    "extract_config": {"type": "object"},
                    "mapping_config": {"type": "object"},
                    "runtime_config": {"type": "object"},
                },
                "required": ["auth_token", "name", "source_kind"],
            },
        ),
        Tool(
            name="data_source_update",
            description="更新数据源配置。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **source_id_schema,
                    "name": {"type": "string"},
                    "provider_code": {"type": "string"},
                    "domain_type": {"type": "string"},
                    "execution_mode": {"type": "string"},
                    "description": {"type": "string"},
                    "status": {"type": "string"},
                    "enabled": {"type": "boolean"},
                    "connection_config": {"type": "object"},
                    "auth_config": {"type": "object"},
                    "extract_config": {"type": "object"},
                    "mapping_config": {"type": "object"},
                    "runtime_config": {"type": "object"},
                },
                "required": ["auth_token", "source_id"],
            },
        ),
        Tool(
            name="data_source_disable",
            description="停用数据源。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **source_id_schema,
                    "reason": {"type": "string"},
                },
                "required": ["auth_token", "source_id"],
            },
        ),
        Tool(
            name="data_source_delete",
            description="删除数据源（标记为 deleted 并禁用）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **source_id_schema,
                },
                "required": ["auth_token", "source_id"],
            },
        ),
        Tool(
            name="data_source_test",
            description="测试数据源连接能力。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **source_id_schema,
                    "mode": {"type": "string"},
                },
                "required": ["auth_token", "source_id"],
            },
        ),
        Tool(
            name="data_source_authorize",
            description="发起授权（主要用于 platform_oauth）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **source_id_schema,
                    "return_path": {"type": "string"},
                    "redirect_uri": {"type": "string"},
                    "mode": {"type": "string"},
                },
                "required": ["auth_token", "source_id"],
            },
        ),
        Tool(
            name="data_source_handle_callback",
            description="处理授权回调（主要用于 platform_oauth）。",
            inputSchema={
                "type": "object",
                "properties": {
                    **source_id_schema,
                    "state": {"type": "string"},
                    "code": {"type": "string"},
                    "error": {"type": "string"},
                    "error_description": {"type": "string"},
                    "callback_payload": {"type": "object"},
                    "mode": {"type": "string"},
                },
                "required": ["source_id", "state"],
            },
        ),
        Tool(
            name="data_source_trigger_sync",
            description="触发一次同步任务（幂等）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **source_id_schema,
                    "idempotency_key": {"type": "string"},
                    "resource_key": {"type": "string"},
                    "window_start": {"type": "string"},
                    "window_end": {"type": "string"},
                    "window": {"type": "object"},
                    "params": {"type": "object"},
                },
                "required": ["auth_token", "source_id"],
            },
        ),
        Tool(
            name="data_source_scheduler_list_collection_plans",
            description="列出启用了自动采集计划的已发布数据集，供 finance-cron 调度使用。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "company_id": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="data_source_trigger_dataset_collection",
            description="按已发布数据集触发一次独立采集任务。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **source_id_schema,
                    "dataset_id": {"type": "string"},
                    "dataset_code": {"type": "string"},
                    "resource_key": {"type": "string"},
                    "biz_date": {"type": "string"},
                    "trigger_mode": {"type": "string"},
                    "window_start": {"type": "string"},
                    "window_end": {"type": "string"},
                    "window": {"type": "object"},
                    "params": {"type": "object"},
                },
                "required": ["auth_token", "source_id"],
            },
        ),
        Tool(
            name="data_source_get_sync_job",
            description="查询单个同步任务。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "sync_job_id": {"type": "string"},
                },
                "required": ["auth_token", "sync_job_id"],
            },
        ),
        Tool(
            name="data_source_list_sync_jobs",
            description="列出同步任务。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **source_id_schema,
                    "status": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="data_source_get_dataset_collection_detail",
            description="获取某个已发布数据集的采集详情、最近采集任务和最新样本行。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **source_id_schema,
                    "dataset_id": {"type": "string"},
                    "resource_key": {"type": "string"},
                    "limit": {"type": "integer"},
                    "sample_limit": {"type": "integer"},
                },
                "required": ["auth_token", "source_id"],
            },
        ),
        Tool(
            name="data_source_list_collection_records",
            description="读取数据资产层 dataset_collection_records 采集记录。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **source_id_schema,
                    "dataset_id": {"type": "string"},
                    "dataset_code": {"type": "string"},
                    "resource_key": {"type": "string"},
                    "biz_date": {"type": "string"},
                    "item_key": {"type": "string"},
                    "limit": {"type": "integer"},
                    "offset": {"type": "integer"},
                },
                "required": ["auth_token", "source_id"],
            },
        ),
        Tool(
            name="data_source_export_collection_records",
            description="将数据资产层 dataset_collection_records 导出为临时 Excel 文件，供 proc/recon 运行时复用。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **source_id_schema,
                    "dataset_id": {"type": "string"},
                    "dataset_code": {"type": "string"},
                    "resource_key": {"type": "string"},
                    "biz_date": {"type": "string"},
                    "table_name": {"type": "string"},
                    "query": {"type": "object"},
                },
                "required": ["auth_token", "source_id"],
            },
        ),
        Tool(
            name="data_source_preview",
            description="预览数据源数据样例。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **source_id_schema,
                    "limit": {"type": "integer"},
                },
                "required": ["auth_token", "source_id"],
            },
        ),
    ]


async def handle_tool_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        if name == "data_source_list":
            return await _handle_data_source_list(arguments)
        if name == "data_source_get":
            return await _handle_data_source_get(arguments)
        if name == "data_source_discover_datasets":
            return await _handle_data_source_discover_datasets(arguments)
        if name == "data_source_list_datasets":
            return await _handle_data_source_list_datasets(arguments)
        if name == "data_source_get_dataset":
            return await _handle_data_source_get_dataset(arguments)
        if name == "data_source_upsert_dataset":
            return await _handle_data_source_upsert_dataset(arguments)
        if name == "data_source_disable_dataset":
            return await _handle_data_source_disable_dataset(arguments)
        if name == "data_source_refresh_dataset_semantic_profile":
            return await _handle_data_source_refresh_dataset_semantic_profile(arguments)
        if name == "data_source_update_dataset_semantic_profile":
            return await _handle_data_source_update_dataset_semantic_profile(arguments)
        if name == "data_source_publish_dataset":
            return await _handle_data_source_publish_dataset(arguments)
        if name == "data_source_unpublish_dataset":
            return await _handle_data_source_unpublish_dataset(arguments)
        if name == "data_source_list_dataset_candidates":
            return await _handle_data_source_list_dataset_candidates(arguments)
        if name == "data_source_import_openapi":
            return await _handle_data_source_import_openapi(arguments)
        if name == "data_source_preflight_rule_binding":
            return await _handle_data_source_preflight_rule_binding(arguments)
        if name == "data_source_list_events":
            return await _handle_data_source_list_events(arguments)
        if name == "data_source_create":
            return await _handle_data_source_create(arguments)
        if name == "data_source_update":
            return await _handle_data_source_update(arguments)
        if name == "data_source_disable":
            return await _handle_data_source_disable(arguments)
        if name == "data_source_delete":
            return await _handle_data_source_delete(arguments)
        if name == "data_source_test":
            return await _handle_data_source_test(arguments)
        if name == "data_source_authorize":
            return await _handle_data_source_authorize(arguments)
        if name == "data_source_handle_callback":
            return await _handle_data_source_callback(arguments)
        if name == "data_source_trigger_sync":
            return await _handle_data_source_trigger_sync(arguments)
        if name == "data_source_scheduler_list_collection_plans":
            return await _handle_data_source_scheduler_list_collection_plans(arguments)
        if name == "data_source_trigger_dataset_collection":
            return await _handle_data_source_trigger_dataset_collection(arguments)
        if name == "data_source_get_sync_job":
            return await _handle_data_source_get_sync_job(arguments)
        if name == "data_source_list_sync_jobs":
            return await _handle_data_source_list_sync_jobs(arguments)
        if name == "data_source_get_dataset_collection_detail":
            return await _handle_data_source_get_dataset_collection_detail(arguments)
        if name == "data_source_list_collection_records":
            return await _handle_data_source_list_collection_records(arguments)
        if name == "data_source_export_collection_records":
            return await _handle_data_source_export_collection_records(arguments)
        if name == "data_source_preview":
            return await _handle_data_source_preview(arguments)
        return {"success": False, "error": f"未知工具: {name}"}
    except Exception as exc:
        logger.error("data_source tool error: %s", exc, exc_info=True)
        return {"success": False, "error": str(exc)}


async def _handle_data_source_list(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_kind = str(arguments.get("source_kind") or "").strip().lower() or None
    domain_type = str(arguments.get("domain_type") or "").strip().lower() or None
    status = str(arguments.get("status") or "").strip().lower() or None
    rows = auth_db.list_unified_data_sources(
        company_id=company_id,
        source_kind=source_kind,
        domain_type=domain_type,
        status=status,
        include_deleted=False,
    )
    dataset_rows = auth_db.list_unified_data_source_datasets(
        company_id=company_id,
        data_source_id=None,
        status=None,
        include_deleted=False,
        limit=5000,
    )
    datasets_by_source: dict[str, list[dict[str, Any]]] = {}
    for dataset_row in dataset_rows:
        source_id = str(dataset_row.get("data_source_id") or "")
        datasets_by_source.setdefault(source_id, []).append(dataset_row)

    sources = [
        _build_data_source_view(
            row,
            datasets=datasets_by_source.get(str(row.get("id") or ""), []),
            include_dataset_details=False,
        )
        for row in rows
    ]
    source_kind_counts: dict[str, int] = {}
    for row in rows:
        kind = str(row.get("source_kind") or "")
        source_kind_counts[kind] = source_kind_counts.get(kind, 0) + 1
    health_counts: dict[str, int] = {}
    for item in sources:
        health_status = str((item.get("health_summary") or {}).get("overall_status") or "unknown")
        health_counts[health_status] = health_counts.get(health_status, 0) + 1
    return {
        "success": True,
        "count": len(sources),
        "sources": sources,
        "source_summary": {
            "total": len(sources),
            "by_source_kind": source_kind_counts,
            "by_health_status": health_counts,
        },
    }


async def _handle_data_source_get(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_id = _source_id_from_args(arguments)
    source_row = auth_db.get_unified_data_source_by_id(
        company_id=company_id,
        data_source_id=source_id,
    )
    if not source_row:
        return {"success": False, "error": "数据源不存在"}
    include_datasets = _normalize_bool(arguments.get("include_datasets"), default=True)
    dataset_rows = _load_source_datasets(company_id, source_id)
    source_view = _build_data_source_view(
        source_row,
        datasets=dataset_rows,
        include_dataset_details=include_datasets,
    )
    return {
        "success": True,
        "source": source_view,
        "source_summary": dict(source_view.get("source_summary") or {}),
        "dataset_summary": dict(source_view.get("dataset_summary") or {}),
        "health_summary": dict(source_view.get("health_summary") or {}),
    }


async def _handle_data_source_discover_datasets(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_id = _source_id_from_args(arguments)
    source_row = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id)
    if not source_row:
        return {"success": False, "error": "数据源不存在"}

    runtime_source = _merge_runtime_overrides(
        _load_runtime_source(source_row, include_secret=True),
        arguments,
    )
    connector = build_connector(runtime_source)
    discover_result = connector.discover_datasets(arguments)
    discover_scan_summary = (
        discover_result.get("scan_summary")
        if isinstance(discover_result.get("scan_summary"), dict)
        else {}
    )
    if not bool(discover_result.get("success")):
        message = str(discover_result.get("message") or discover_result.get("error") or "发现数据集失败")
        updated_source = auth_db.update_unified_data_source_health(
            data_source_id=source_id,
            health_status="error",
            last_error_message=message,
        ) or source_row
        existing_datasets = _load_source_datasets(company_id, source_id)
        discover_summary = _build_discover_summary(
            dataset_summary=_summarize_datasets(existing_datasets),
            scan_summary=discover_scan_summary,
            status="error",
            error_message=message,
        )
        _update_source_meta(updated_source, meta_updates={"discover_summary": discover_summary})
        auth_db.create_unified_data_source_event(
            company_id=company_id,
            data_source_id=source_id,
            event_type="dataset_discover_failed",
            event_level="error",
            event_message=message,
            event_payload={"arguments": arguments, "scan_summary": discover_scan_summary},
        )
        return {
            "success": False,
            "source_id": source_id,
            "datasets": [],
            "dataset_count": 0,
            "scan_summary": discover_scan_summary,
            "discover_summary": discover_summary,
            "error": str(discover_result.get("error") or "discover_failed"),
            "message": message,
        }

    discovered_raw = [item for item in discover_result.get("datasets") or [] if isinstance(item, dict)]
    normalized = [
        _normalize_discovered_dataset(item, source_row=source_row, index=index)
        for index, item in enumerate(discovered_raw)
    ]
    persist = _normalize_bool(arguments.get("persist"), default=True)
    dataset_rows: list[dict[str, Any]] = []
    persisted_rows: list[dict[str, Any]] = []
    persist_errors: list[str] = []
    if persist:
        for item in normalized:
            upserted = auth_db.upsert_unified_data_source_dataset(
                company_id=company_id,
                data_source_id=source_id,
                dataset_code=item["dataset_code"],
                dataset_name=item["dataset_name"],
                resource_key=item["resource_key"],
                dataset_kind=item["dataset_kind"],
                origin_type=item["origin_type"],
                extract_config=item["extract_config"],
                schema_summary=item["schema_summary"],
                sync_strategy=item["sync_strategy"],
                status=item["status"],
                is_enabled=item["is_enabled"],
                health_status=item["health_status"],
                last_checked_at=item.get("last_checked_at"),
                last_sync_at=item.get("last_sync_at"),
                last_error_message=item.get("last_error_message") or "",
                meta=item["meta"],
            )
            if upserted:
                persisted_rows.append(upserted)
            else:
                persist_errors.append(item["dataset_code"])

    if persist:
        dataset_rows = _load_source_datasets(company_id, source_id)
        datasets = [_build_dataset_view(item) for item in dataset_rows]
    else:
        datasets = [
            _build_dataset_view(
                {
                    "id": "",
                    "data_source_id": source_id,
                    **item,
                    "meta": dict(item.get("meta") or {}),
                    "created_at": None,
                    "updated_at": None,
                }
            )
            for item in normalized
        ]
        dataset_rows = normalized
    dataset_summary = _summarize_datasets(
        [
            {
                "status": item.get("status"),
                "is_enabled": item.get("enabled"),
                "health_status": item.get("health_status"),
                "last_sync_at": item.get("last_sync_at"),
                "last_checked_at": item.get("last_checked_at"),
            }
            for item in datasets
        ]
    )

    updated_source = auth_db.update_unified_data_source_health(
        data_source_id=source_id,
        health_status="healthy" if not persist_errors else "warning",
        last_error_message="" if not persist_errors else f"部分数据集写入失败: {', '.join(persist_errors[:5])}",
    ) or source_row
    discover_summary = _build_discover_summary(
        dataset_summary=dataset_summary,
        scan_summary=discover_scan_summary,
        status="success" if not persist_errors else "warning",
        error_message="" if not persist_errors else f"部分数据集写入失败: {', '.join(persist_errors[:5])}",
    )
    refreshed_source = _update_source_meta(updated_source, meta_updates={"discover_summary": discover_summary}) or updated_source
    auth_db.create_unified_data_source_event(
        company_id=company_id,
        data_source_id=source_id,
        event_type="datasets_discovered",
        event_level="info" if not persist_errors else "warn",
        event_message=f"发现 {len(normalized)} 个数据集，写入 {len(persisted_rows)} 个",
        event_payload={
            "persist": persist,
            "dataset_count": len(normalized),
            "persisted_count": len(persisted_rows),
            "persist_errors": persist_errors,
            "scan_summary": discover_scan_summary,
        },
    )
    return {
        "success": True,
        "source_id": source_id,
        "persist": persist,
        "dataset_count": len(datasets),
        "persisted_count": len(persisted_rows),
        "persist_error_count": len(persist_errors),
        "scan_summary": discover_scan_summary,
        "discover_summary": discover_summary,
        "datasets": datasets,
        "dataset_summary": dataset_summary,
        "source": _build_data_source_view(refreshed_source, datasets=dataset_rows),
        "message": str(discover_result.get("message") or f"发现 {len(normalized)} 个数据集"),
    }


async def _handle_data_source_list_datasets(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_id = _source_id_from_args(arguments) or None
    status = str(arguments.get("status") or "").strip().lower() or None
    include_deleted = _normalize_bool(arguments.get("include_deleted"), default=False)
    keyword = _safe_text(arguments.get("keyword")).lower()
    schema_name = _safe_text(arguments.get("schema_name")).lower()
    object_type = _safe_text(arguments.get("object_type")).lower()
    publish_status = _safe_text(arguments.get("publish_status")).lower()
    business_object_type = _safe_text(arguments.get("business_object_type")).lower()
    verified_status = _safe_text(arguments.get("verified_status")).lower()
    only_published = _normalize_bool(arguments.get("only_published"), default=False)
    page = max(1, int(arguments.get("page") or 1))
    page_size = max(1, min(int(arguments.get("page_size") or arguments.get("limit") or 50), 200))
    sort_by = _safe_text(arguments.get("sort_by"))
    include_heavy = _normalize_bool(arguments.get("include_heavy"), default=False)

    source_row = None
    if source_id:
        source_row = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id)
        if not source_row:
            return {"success": False, "error": "数据源不存在"}

    query_result = _query_datasets_with_compat(
        company_id=company_id,
        data_source_id=source_id,
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
        page_size=page_size,
        sort_by=sort_by,
        lightweight=not include_heavy,
    )
    if query_result is not None:
        filtered_rows = list(query_result.get("items") or [])
        paged_rows = filtered_rows
        total = int(query_result.get("total") or len(filtered_rows))
        result_page = int(query_result.get("page") or page)
        result_page_size = int(query_result.get("page_size") or page_size)
    else:
        rows = _list_datasets_with_compat(
            company_id=company_id,
            data_source_id=source_id,
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
            page_size=page_size,
            sort_by=sort_by,
            lightweight=not include_heavy,
        )
        filtered_rows = [
            row
            for row in rows
            if _dataset_matches_filters(
                row,
                keyword=keyword,
                schema_name=schema_name,
                object_type=object_type,
                publish_status=publish_status,
                business_object_type=business_object_type,
                verified_status=verified_status,
                only_published=only_published,
            )
        ]
        sorted_rows = _sort_datasets(filtered_rows, sort_by=sort_by)
        paged_rows, total = _paginate_rows(sorted_rows, page=page, page_size=page_size)
        result_page = page
        result_page_size = page_size
    datasets = [_build_dataset_view(row, include_heavy=include_heavy) for row in paged_rows]
    result: dict[str, Any] = {
        "success": True,
        "count": len(datasets),
        "total": total,
        "page": result_page,
        "page_size": result_page_size,
        "datasets": datasets,
        "dataset_summary": _summarize_datasets(filtered_rows),
    }
    if source_row:
        result["source_summary"] = _build_source_summary(source_row)
        result["health_summary"] = _build_health_summary(source_row, filtered_rows)
    return result


async def _handle_data_source_scheduler_list_collection_plans(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_scheduler_user(arguments.get("auth_token", ""))
    company_filter = _safe_text(arguments.get("company_id"))
    limit = max(1, min(int(arguments.get("limit") or 500), 1000))
    company_ids = [company_filter or _safe_text(user.get("company_id"))]
    if not company_ids[0]:
        company_ids = [_safe_text(row.get("id")) for row in auth_db.list_companies() if _safe_text(row.get("id"))]

    plans: list[dict[str, Any]] = []
    for company_id in company_ids:
        rows = _list_datasets_with_compat(
            company_id=company_id,
            status="active",
            include_deleted=False,
            only_published=True,
            page=1,
            page_size=limit,
            lightweight=False,
        )
        for row in rows:
            config = _dataset_collection_config(row)
            schedule_time = _collection_schedule_time(config)
            if not schedule_time:
                continue
            date_field = _collection_date_field(config)
            if not date_field:
                continue
            source_id = _safe_text(row.get("data_source_id"))
            source_row = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id)
            if not source_row:
                continue
            if str(source_row.get("status") or "") != "active" or not bool(source_row.get("is_enabled", True)):
                continue
            dataset_view = _build_dataset_view(row, include_heavy=False)
            plans.append(
                {
                    "company_id": company_id,
                    "source_id": source_id,
                    "dataset_id": _safe_text(row.get("id")),
                    "dataset_code": _safe_text(row.get("dataset_code")),
                    "dataset_name": dataset_view.get("business_name") or row.get("dataset_name"),
                    "resource_key": _safe_text(row.get("resource_key")) or "default",
                    "schedule_type": "daily",
                    "schedule_expr": schedule_time,
                    "date_field": date_field,
                    "display_date_field": _collection_display_date_field(config),
                    "collection_config": config,
                }
            )
    return {"success": True, "collection_plans": plans, "count": len(plans)}


async def _handle_data_source_get_dataset(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    row = _resolve_dataset_row(company_id=company_id, arguments=arguments)
    if not row:
        return {"success": False, "error": "数据集不存在"}

    source_row = auth_db.get_unified_data_source_by_id(
        company_id=company_id,
        data_source_id=str(row.get("data_source_id") or ""),
    )
    source_datasets = []
    if source_row:
        source_datasets = _load_source_datasets(company_id, str(source_row.get("id") or ""))
    return {
        "success": True,
        "dataset": _build_dataset_view(row),
        "source_summary": _build_source_summary(source_row) if source_row else {},
        "health_summary": _build_health_summary(source_row, source_datasets) if source_row else {},
    }


async def _handle_data_source_upsert_dataset(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_id = _source_id_from_args(arguments)
    source_row = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id)
    if not source_row:
        return {"success": False, "error": "数据源不存在"}

    dataset_code = _sanitize_dataset_code(arguments.get("dataset_code"))
    if not dataset_code:
        return {"success": False, "error": "dataset_code 不能为空"}
    resource_key = str(arguments.get("resource_key") or dataset_code).strip() or "default"
    dataset_name = str(arguments.get("dataset_name") or resource_key).strip() or dataset_code
    enabled = _normalize_bool(arguments.get("enabled"), default=True)
    status = _normalize_status(arguments.get("status"), default="active" if enabled else "disabled")
    health_status = _normalize_health_status(arguments.get("health_status"), default="unknown")

    upsert_kwargs: dict[str, Any] = {
        "company_id": company_id,
        "data_source_id": source_id,
        "dataset_code": dataset_code,
        "dataset_name": dataset_name,
        "resource_key": resource_key,
        "dataset_kind": str(arguments.get("dataset_kind") or "table"),
        "origin_type": _normalize_dataset_origin_type(arguments.get("origin_type"), default="manual"),
        "extract_config": dict(arguments.get("extract_config") or {}),
        "schema_summary": dict(arguments.get("schema_summary") or {}),
        "sync_strategy": dict(arguments.get("sync_strategy") or {}),
        "status": status,
        "is_enabled": enabled,
        "health_status": health_status,
        "last_checked_at": arguments.get("last_checked_at"),
        "last_sync_at": arguments.get("last_sync_at"),
        "last_error_message": str(arguments.get("last_error_message") or ""),
        "meta": dict(arguments.get("meta") or {}),
    }
    optional_top_level_fields = {
        "schema_name": arguments.get("schema_name"),
        "object_name": arguments.get("object_name"),
        "object_type": arguments.get("object_type"),
        "publish_status": arguments.get("publish_status"),
        "business_domain": arguments.get("business_domain"),
        "business_object_type": arguments.get("business_object_type"),
        "grain": arguments.get("grain"),
        "verified_status": arguments.get("verified_status"),
        "usage_count": arguments.get("usage_count"),
        "last_used_at": arguments.get("last_used_at"),
        "search_text": arguments.get("search_text"),
    }
    supported = set(inspect.signature(auth_db.upsert_unified_data_source_dataset).parameters)
    for key, value in optional_top_level_fields.items():
        if key in supported and value not in (None, ""):
            upsert_kwargs[key] = value

    row = auth_db.upsert_unified_data_source_dataset(**upsert_kwargs)
    if not row:
        return {"success": False, "error": "写入数据集失败"}

    auth_db.create_unified_data_source_event(
        company_id=company_id,
        data_source_id=source_id,
        event_type="dataset_upserted",
        event_level="info",
        event_message=f"更新数据集：{dataset_name}",
        event_payload={
            "dataset_id": str(row.get("id") or ""),
            "dataset_code": dataset_code,
            "resource_key": resource_key,
        },
    )
    return {
        "success": True,
        "dataset": _build_dataset_view(row),
        "source_summary": _build_source_summary(source_row),
        "message": "数据集已更新",
    }


async def _handle_data_source_disable_dataset(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    dataset_id = _dataset_id_from_args(arguments)
    if not dataset_id:
        return {"success": False, "error": "dataset_id 不能为空"}
    current = auth_db.get_unified_data_source_dataset_by_id(company_id=company_id, dataset_id=dataset_id)
    if not current:
        return {"success": False, "error": "数据集不存在"}
    updated = auth_db.update_unified_data_source_dataset_status(
        dataset_id=dataset_id,
        status="disabled",
        is_enabled=False,
    )
    if not updated:
        return {"success": False, "error": "停用数据集失败"}
    reason = str(arguments.get("reason") or "数据集已停用")
    health_updated = auth_db.update_unified_data_source_dataset_health(
        dataset_id=dataset_id,
        health_status="disabled",
        last_error_message=reason,
    )
    auth_db.create_unified_data_source_event(
        company_id=company_id,
        data_source_id=str(current.get("data_source_id") or ""),
        event_type="dataset_disabled",
        event_level="warn",
        event_message=reason,
        event_payload={"dataset_id": dataset_id, "reason": reason},
    )
    return {
        "success": True,
        "dataset": _build_dataset_view(health_updated or updated),
        "message": "数据集已停用",
    }


async def _handle_data_source_refresh_dataset_semantic_profile(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    dataset_row = _resolve_dataset_row(company_id=company_id, arguments=arguments)
    if not dataset_row:
        return {"success": False, "error": "数据集不存在"}

    source_id = _safe_text(dataset_row.get("data_source_id"))
    source_row = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id)
    if not source_row:
        return {"success": False, "error": "数据源不存在"}

    sample_limit = max(1, min(int(arguments.get("sample_limit") or SEMANTIC_SAMPLE_ROW_LIMIT), 100))
    resource_key = _safe_text(dataset_row.get("resource_key")) or "default"
    sample_rows = _load_dataset_sample_rows_from_collection_records(
        company_id=company_id,
        data_source_id=source_id,
        dataset_id=_safe_text(dataset_row.get("id")),
        dataset_code=_safe_text(dataset_row.get("dataset_code")),
        resource_key=resource_key,
        limit=sample_limit,
    )
    sample_source = "collection_records" if sample_rows else "none"

    if not sample_rows and str(source_row.get("source_kind") or "") not in AGENT_ASSISTED_KINDS:
        try:
            runtime_source = _load_runtime_source(source_row, include_secret=True)
            connector = build_connector(runtime_source)
            preview_result = connector.preview(
                {
                    "resource_key": resource_key,
                    "dataset_code": _safe_text(dataset_row.get("dataset_code")),
                    "limit": sample_limit,
                    "dataset": {
                        "dataset_code": _safe_text(dataset_row.get("dataset_code")),
                        "resource_key": resource_key,
                        "extract_config": dict(dataset_row.get("extract_config") or {}),
                    },
                }
            )
            sample_rows = [item for item in preview_result.get("rows") or [] if isinstance(item, dict)]
            if sample_rows:
                sample_source = "connector_preview"
        except Exception as exc:
            logger.warning(
                "refresh dataset semantic profile preview fallback failed: dataset_id=%s error=%s",
                dataset_row.get("id"),
                exc,
            )

    refreshed = _refresh_dataset_semantic_profile(
        dataset_row=dataset_row,
        source_row=source_row,
        sample_rows=sample_rows,
        status="generated_with_samples" if sample_rows else "generated_basic",
        allow_llm=True,
    )
    if not refreshed:
        return {"success": False, "error": "刷新语义层失败"}

    auth_db.create_unified_data_source_event(
        company_id=company_id,
        data_source_id=source_id,
        event_type="dataset_semantic_refreshed",
        event_level="info",
        event_message=f"刷新数据集语义层：{_safe_text(dataset_row.get('dataset_name')) or _safe_text(dataset_row.get('dataset_code'))}",
        event_payload={
            "dataset_id": _safe_text(dataset_row.get("id")),
            "sample_rows_count": len(sample_rows),
            "sample_source": sample_source,
            "semantic_status": _flatten_semantic_profile(refreshed).get("semantic_status"),
        },
    )
    return {
        "success": True,
        "dataset": _build_dataset_view(refreshed),
        "sample_rows_count": len(sample_rows),
        "sample_source": sample_source,
        "message": "数据集语义层已刷新",
    }


async def _handle_data_source_update_dataset_semantic_profile(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    dataset_row = _resolve_dataset_row(company_id=company_id, arguments=arguments)
    if not dataset_row:
        logger.warning(
            "update semantic dataset not found: company_id=%s source_id=%s dataset_id=%s dataset_code=%s resource_key=%s",
            company_id,
            _source_id_from_args(arguments),
            _dataset_id_from_args(arguments),
            _sanitize_dataset_code(arguments.get("dataset_code")),
            _safe_text(arguments.get("resource_key")),
        )
        return {"success": False, "error": "数据集不存在"}

    source_id = _safe_text(dataset_row.get("data_source_id"))
    source_row = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id)
    if not source_row:
        return {"success": False, "error": "数据源不存在"}

    sample_rows = _load_dataset_sample_rows_from_collection_records(
        company_id=company_id,
        data_source_id=source_id,
        dataset_id=_safe_text(dataset_row.get("id")),
        dataset_code=_safe_text(dataset_row.get("dataset_code")),
        resource_key=_safe_text(dataset_row.get("resource_key")) or "default",
        limit=SEMANTIC_SAMPLE_ROW_LIMIT,
    )
    valid_field_names = {item.get("name") for item in _extract_dataset_columns(dataset_row, sample_rows) if _safe_text(item.get("name"))}
    try:
        patch = _normalize_manual_semantic_patch(
            arguments,
            valid_field_names={str(name) for name in valid_field_names if name},
        )
    except ValueError as exc:
        return {"success": False, "error": str(exc)}
    if not patch:
        return {"success": False, "error": "缺少可更新的语义层字段"}

    base_profile = _extract_semantic_profile(dataset_row)
    if not base_profile:
        base_profile = _build_semantic_profile(
            dataset_row=dataset_row,
            source_row=source_row,
            sample_rows=sample_rows,
            status="generated_with_samples" if sample_rows else "generated_basic",
        )
    next_profile = dict(base_profile)

    if "business_name" in patch:
        next_profile["business_name"] = patch["business_name"]
    if "business_description" in patch:
        next_profile["business_description"] = patch["business_description"]
    if "key_fields" in patch:
        next_profile["key_fields"] = patch["key_fields"]

    next_field_label_map = dict(next_profile.get("field_label_map") or {})
    if "field_label_map" in patch:
        next_field_label_map.update(dict(patch["field_label_map"]))

    existing_fields = [item for item in next_profile.get("fields") or [] if isinstance(item, dict)]
    fields_by_name = {_safe_text(item.get("raw_name")): dict(item) for item in existing_fields if _safe_text(item.get("raw_name"))}
    if "fields" in patch:
        for item in patch["fields"]:
            raw_name = _safe_text(item.get("raw_name"))
            if not raw_name:
                continue
            fields_by_name[raw_name] = item
            next_field_label_map[raw_name] = _safe_text(item.get("display_name")) or raw_name

    merged_fields = list(fields_by_name.values())
    low_confidence_fields = [
        _safe_text(item.get("raw_name"))
        for item in merged_fields
        if _safe_text(item.get("raw_name"))
        and float(item.get("confidence") or 0.0) < SEMANTIC_FIELD_CONFIDENCE_THRESHOLD
        and not bool(item.get("confirmed_by_user"))
    ]

    next_profile["field_label_map"] = next_field_label_map
    next_profile["fields"] = merged_fields
    next_profile["low_confidence_fields"] = low_confidence_fields
    next_profile["status"] = _normalize_semantic_status(patch.get("status"), default="manual_updated")
    next_profile["updated_at"] = _now_iso()
    next_profile["version"] = 1
    next_profile["generated_from"] = {
        **dict(next_profile.get("generated_from") or {}),
        "source_kind": _safe_text(source_row.get("source_kind")),
        "provider_code": _safe_text(source_row.get("provider_code")),
        "dataset_kind": _safe_text(dataset_row.get("dataset_kind")),
        "resource_key": _safe_text(dataset_row.get("resource_key")),
        "schema_hash": _hash_payload(dict(dataset_row.get("schema_summary") or {})),
        "sample_hash": _hash_payload(sample_rows[:SEMANTIC_SAMPLE_ROW_LIMIT]) if sample_rows else "",
        "has_sample_rows": bool(sample_rows),
    }

    updated = _persist_dataset_semantic_profile(
        dataset_row=dataset_row,
        semantic_profile=next_profile,
    )
    if not updated:
        return {"success": False, "error": "更新语义层失败"}

    auth_db.create_unified_data_source_event(
        company_id=company_id,
        data_source_id=source_id,
        event_type="dataset_semantic_updated",
        event_level="info",
        event_message=f"更新数据集语义层：{_safe_text(dataset_row.get('dataset_name')) or _safe_text(dataset_row.get('dataset_code'))}",
        event_payload={
            "dataset_id": _safe_text(dataset_row.get("id")),
            "semantic_status": next_profile.get("status"),
        },
    )
    return {
        "success": True,
        "dataset": _build_dataset_view(updated),
        "message": "数据集语义层已更新",
    }


async def _handle_data_source_publish_dataset(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    dataset_row = _resolve_dataset_row(company_id=company_id, arguments=arguments)
    if not dataset_row:
        logger.warning(
            "publish dataset not found: company_id=%s source_id=%s dataset_id=%s dataset_code=%s resource_key=%s",
            company_id,
            _source_id_from_args(arguments),
            _dataset_id_from_args(arguments),
            _sanitize_dataset_code(arguments.get("dataset_code")),
            _safe_text(arguments.get("resource_key")),
        )
        return {"success": False, "error": "数据集不存在"}

    semantic_fields = (
        "semantic_profile",
        "business_name",
        "business_description",
        "key_fields",
        "field_label_map",
        "fields",
        "status",
    )
    should_update_semantic = any(
        key in arguments and arguments.get(key) not in (None, "", [], {})
        for key in semantic_fields
    )
    if should_update_semantic:
        semantic_result = await _handle_data_source_update_dataset_semantic_profile(arguments)
        if not semantic_result.get("success"):
            return semantic_result
        dataset_row = dict(semantic_result.get("dataset") or dataset_row)
        dataset_row = _resolve_dataset_row(
            company_id=company_id,
            arguments={"dataset_id": _safe_text(dataset_row.get("id"))},
        ) or dataset_row

    catalog_patch = _build_catalog_patch(arguments, publish_status_default="published")
    catalog_patch["publish_status"] = "published"
    updated = _upsert_dataset_with_profile(dataset_row, catalog_patch=catalog_patch)
    if not updated:
        return {"success": False, "error": "发布数据集失败"}

    auth_db.create_unified_data_source_event(
        company_id=company_id,
        data_source_id=_safe_text(updated.get("data_source_id")),
        event_type="dataset_published",
        event_level="info",
        event_message=f"发布数据集：{_safe_text(updated.get('dataset_name')) or _safe_text(updated.get('dataset_code'))}",
        event_payload={
            "dataset_id": _safe_text(updated.get("id")),
            "dataset_code": _safe_text(updated.get("dataset_code")),
            "publish_status": "published",
        },
    )
    return {
        "success": True,
        "dataset": _build_dataset_view(updated),
        "message": "数据集已发布",
    }


async def _handle_data_source_unpublish_dataset(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    dataset_row = _resolve_dataset_row(company_id=company_id, arguments=arguments)
    if not dataset_row:
        logger.warning(
            "unpublish dataset not found: company_id=%s source_id=%s dataset_id=%s dataset_code=%s resource_key=%s",
            company_id,
            _source_id_from_args(arguments),
            _dataset_id_from_args(arguments),
            _sanitize_dataset_code(arguments.get("dataset_code")),
            _safe_text(arguments.get("resource_key")),
        )
        return {"success": False, "error": "数据集不存在"}

    catalog_patch = _build_catalog_patch(arguments, publish_status_default="unpublished")
    catalog_patch["publish_status"] = "unpublished"
    updated = _upsert_dataset_with_profile(dataset_row, catalog_patch=catalog_patch)
    if not updated:
        return {"success": False, "error": "取消发布失败"}

    reason = _safe_text(arguments.get("reason")) or "手动取消发布"
    auth_db.create_unified_data_source_event(
        company_id=company_id,
        data_source_id=_safe_text(updated.get("data_source_id")),
        event_type="dataset_unpublished",
        event_level="warn",
        event_message=f"取消发布数据集：{_safe_text(updated.get('dataset_name')) or _safe_text(updated.get('dataset_code'))}",
        event_payload={
            "dataset_id": _safe_text(updated.get("id")),
            "dataset_code": _safe_text(updated.get("dataset_code")),
            "publish_status": "unpublished",
            "reason": reason,
        },
    )
    return {
        "success": True,
        "dataset": _build_dataset_view(updated),
        "message": "数据集已取消发布",
    }


async def _handle_data_source_list_dataset_candidates(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    binding_scope = _safe_text(arguments.get("binding_scope")).lower() or "scheme"
    scene_type = _normalize_scene_type(arguments.get("scene_type")) or "recon"
    role_code = _normalize_role_code(arguments.get("role_code"))
    keyword = _safe_text(arguments.get("keyword")).lower()
    filters = dict(arguments.get("filters") or {})
    page = max(1, int(arguments.get("page") or 1))
    page_size = max(1, min(int(arguments.get("page_size") or 30), 200))

    source_id = _safe_text(filters.get("source_id") or filters.get("data_source_id")) or None
    requested_status = _safe_text(filters.get("status")).lower() or "active"
    only_published = _normalize_bool(filters.get("only_published"), default=True)
    query_kwargs = {
        "company_id": company_id,
        "data_source_id": source_id,
        "status": requested_status,
        "include_deleted": False,
        "keyword": keyword,
        "schema_name": _safe_text(filters.get("schema_name")).lower(),
        "object_type": _safe_text(filters.get("object_type")).lower(),
        "publish_status": _safe_text(filters.get("publish_status")).lower(),
        "business_object_type": _safe_text(filters.get("business_object_type")).lower(),
        "verified_status": _safe_text(filters.get("verified_status")).lower(),
        "only_published": only_published,
        "sort_by": "last_used_desc",
        "lightweight": False,
    }
    rows: list[dict[str, Any]] = []
    seen_dataset_ids: set[str] = set()
    scan_page_size = max(DATASET_CANDIDATE_BATCH_SIZE, page_size)
    query_result = _query_datasets_with_compat(
        **query_kwargs,
        page=1,
        page_size=scan_page_size,
    )
    if query_result is not None:
        total = int(query_result.get("total") or 0)
        for item in (query_result.get("items") or []):
            if not isinstance(item, dict):
                continue
            dataset_id = _safe_text(item.get("id"))
            if dataset_id and dataset_id in seen_dataset_ids:
                continue
            if dataset_id:
                seen_dataset_ids.add(dataset_id)
            rows.append(dict(item))
        current_page = 1
        max_pages = max(1, min(DATASET_CANDIDATE_MAX_SCAN_PAGES, (total + scan_page_size - 1) // scan_page_size))
        while total and current_page < max_pages:
            current_page += 1
            batch_result = _query_datasets_with_compat(
                **query_kwargs,
                page=current_page,
                page_size=scan_page_size,
            )
            if not batch_result:
                break
            batch_items = [dict(item) for item in (batch_result.get("items") or []) if isinstance(item, dict)]
            if not batch_items:
                break
            for item in batch_items:
                dataset_id = _safe_text(item.get("id"))
                if dataset_id and dataset_id in seen_dataset_ids:
                    continue
                if dataset_id:
                    seen_dataset_ids.add(dataset_id)
                rows.append(item)
            if current_page * scan_page_size >= total:
                break
    else:
        rows = _list_datasets_with_compat(
            company_id=company_id,
            data_source_id=source_id,
            status=requested_status,
            include_deleted=False,
            keyword=keyword,
            schema_name=_safe_text(filters.get("schema_name")).lower(),
            object_type=_safe_text(filters.get("object_type")).lower(),
            publish_status=_safe_text(filters.get("publish_status")).lower(),
            business_object_type=_safe_text(filters.get("business_object_type")).lower(),
            verified_status=_safe_text(filters.get("verified_status")).lower(),
            only_published=only_published,
            page=1,
            page_size=max(2000, page_size),
        )

    rows = _enrich_dataset_rows_with_source_context(company_id=company_id, dataset_rows=rows)

    allowed_source_ids = {
        _safe_text(item)
        for item in (filters.get("source_ids") or filters.get("data_source_ids") or [])
        if _safe_text(item)
    }
    allowed_dataset_ids = {_safe_text(item) for item in (filters.get("dataset_ids") or []) if _safe_text(item)}
    excluded_dataset_ids = {_safe_text(item) for item in (filters.get("exclude_dataset_ids") or []) if _safe_text(item)}
    required_fields = [item for item in filters.get("required_fields") or [] if isinstance(item, str)]
    candidate_contract = _resolve_dataset_candidate_contract(
        scene_type=scene_type,
        role_code=role_code,
        filters=filters,
    )
    contract_score_filters = {
        **filters,
        "business_object_types": candidate_contract.get("business_object_types") or filters.get("business_object_types"),
        "grains": candidate_contract.get("grains") or filters.get("grains"),
        "required_field_alias_groups": candidate_contract.get("required_field_alias_groups")
        or filters.get("required_field_alias_groups"),
        "required_fields": required_fields,
    }

    candidates: list[dict[str, Any]] = []
    for row in rows:
        view = _build_dataset_base_view(row)
        dataset_id = _safe_text(view.get("id"))
        if allowed_source_ids and _safe_text(view.get("data_source_id")) not in allowed_source_ids:
            continue
        if allowed_dataset_ids and dataset_id not in allowed_dataset_ids:
            continue
        if dataset_id in excluded_dataset_ids:
            continue
        if view.get("publish_status") != "published":
            continue
        if view.get("status") != "active":
            continue
        if not bool(view.get("enabled")):
            continue
        if _safe_text(view.get("verified_status")) not in {"verified", "unverified"}:
            continue
        if keyword and not _contains_tokens(_safe_text(view.get("search_text")), keyword):
            continue
        contract_coverage = _dataset_alias_group_coverage(
            row,
            candidate_contract.get("required_field_alias_groups") or (),
        )
        contract_object_types = [item.lower() for item in candidate_contract.get("business_object_types") or [] if _safe_text(item)]
        contract_grains = [item.lower() for item in candidate_contract.get("grains") or [] if _safe_text(item)]
        object_type_matches = (
            not contract_object_types
            or _safe_text(view.get("business_object_type")).lower() in contract_object_types
        )
        grain_matches = not contract_grains or _safe_text(view.get("grain")).lower() in contract_grains
        if candidate_contract.get("strict") and candidate_contract:
            required_alias_groups = candidate_contract.get("required_field_alias_groups") or ()
            if required_alias_groups and contract_coverage < 0.34:
                continue
            if contract_object_types and not object_type_matches:
                continue
            if contract_grains and not grain_matches:
                continue
        score, reason = _score_dataset_candidate(
            row,
            role_code=role_code,
            filters=contract_score_filters,
        )
        semantic_flat = _flatten_semantic_profile(row)
        candidates.append(
            {
                **_build_dataset_view(row, include_heavy=False),
                "field_label_map": semantic_flat["field_label_map"],
                "semantic_fields": semantic_flat["semantic_fields"],
                "score": score,
                "reason": reason,
                "contract_label": candidate_contract.get("label") or "",
                "contract_field_coverage": round(contract_coverage, 4),
            }
        )

    candidates.sort(
        key=lambda item: (
            -float(item.get("score") or 0.0),
            -int(item.get("usage_count") or 0),
            -(
                (_parse_datetime(item.get("updated_at")) or datetime.fromtimestamp(0, timezone.utc)).timestamp()
            ),
        ),
    )
    paged_candidates, total = _paginate_rows(candidates, page=page, page_size=page_size)
    return {
        "success": True,
        "binding_scope": binding_scope,
        "scene_type": scene_type,
        "role_code": role_code,
        "count": len(paged_candidates),
        "total": total,
        "page": page,
        "page_size": page_size,
        "candidates": paged_candidates,
    }


async def _handle_data_source_import_openapi(arguments: dict[str, Any]) -> dict[str, Any]:
    payload = dict(arguments or {})
    payload["discover_mode"] = "openapi"
    payload["persist"] = _normalize_bool(payload.get("persist"), default=True)
    return await _handle_data_source_discover_datasets(payload)


async def _handle_data_source_preflight_rule_binding(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    binding_scope = str(arguments.get("binding_scope") or "").strip().lower()
    binding_code = str(arguments.get("binding_code") or "").strip()
    if not binding_scope or not binding_code:
        return {"success": False, "error": "binding_scope 和 binding_code 不能为空"}
    stale_after_minutes = max(1, min(int(arguments.get("stale_after_minutes") or 24 * 60), 30 * 24 * 60))
    preflight = auth_db.evaluate_unified_rule_binding_preflight(
        company_id=company_id,
        binding_scope=binding_scope,
        binding_code=binding_code,
        stale_after_minutes=stale_after_minutes,
    )
    issues = [item for item in preflight.get("issues") or [] if isinstance(item, dict)]
    issue_level_count: dict[str, int] = {}
    issue_code_count: dict[str, int] = {}
    for item in issues:
        level = str(item.get("level") or "unknown")
        code = str(item.get("code") or "unknown")
        issue_level_count[level] = issue_level_count.get(level, 0) + 1
        issue_code_count[code] = issue_code_count.get(code, 0) + 1
    return {
        "success": True,
        "ready": bool(preflight.get("ready")),
        "binding_scope": binding_scope,
        "binding_code": binding_code,
        "summary": {
            "issue_count": int(preflight.get("issue_count") or 0),
            "blocking_issue_count": int(preflight.get("blocking_issue_count") or 0),
            "requirement_count": len(preflight.get("requirements") or []),
            "issue_level_count": issue_level_count,
            "issue_code_count": issue_code_count,
        },
        "preflight": preflight,
    }


async def _handle_data_source_list_events(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_id = _source_id_from_args(arguments) or None
    if source_id:
        source_row = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id)
        if not source_row:
            return {"success": False, "error": "数据源不存在"}
    events = auth_db.list_unified_data_source_events(
        company_id=company_id,
        data_source_id=source_id,
        sync_job_id=str(arguments.get("sync_job_id") or "").strip() or None,
        event_level=str(arguments.get("event_level") or "").strip().lower() or None,
        limit=max(1, min(int(arguments.get("limit") or 200), 1000)),
    )
    return {
        "success": True,
        "count": len(events),
        "events": events,
    }


async def _handle_data_source_create(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_kind = _normalize_source_kind(arguments.get("source_kind"))
    provider_code = _resolve_provider_code(
        source_kind,
        provider_code=arguments.get("provider_code"),
        connection_config=dict(arguments.get("connection_config") or {}),
    )
    domain_type = _normalize_domain_type(arguments.get("domain_type"))
    execution_mode = _normalize_execution_mode(source_kind, arguments.get("execution_mode"))
    name = str(arguments.get("name") or "").strip() or f"{provider_code} 数据源"
    enabled = _normalize_bool(arguments.get("enabled"), default=source_kind not in AGENT_ASSISTED_KINDS)
    status = _normalize_status(
        arguments.get("status"),
        default="active" if enabled else "disabled",
    )
    code = _generate_source_code(source_kind, provider_code, name)
    meta = {"auth_status": "unauthorized" if source_kind == "platform_oauth" else ""}

    row = auth_db.upsert_unified_data_source(
        company_id=company_id,
        code=code,
        name=name,
        source_kind=source_kind,
        domain_type=domain_type,
        provider_code=provider_code,
        execution_mode=execution_mode,
        description=str(arguments.get("description") or ""),
        status=status,
        is_enabled=enabled,
        meta=meta,
    )
    if not row:
        return {"success": False, "error": "创建数据源失败，请检查数据库迁移是否已执行"}

    _upsert_source_configs(company_id, str(row["id"]), arguments)
    created_source = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=str(row["id"]))
    auth_db.create_unified_data_source_event(
        company_id=company_id,
        data_source_id=str(row["id"]),
        event_type="data_source_created",
        event_message=f"创建数据源：{name}",
        event_payload={"source_kind": source_kind, "provider_code": provider_code},
    )
    return {
        "success": True,
        "source": _build_data_source_view(created_source or row),
        "message": "数据源创建成功",
    }


async def _handle_data_source_update(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_id = _source_id_from_args(arguments)
    current = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id)
    if not current:
        return {"success": False, "error": "数据源不存在"}

    source_kind = str(current.get("source_kind") or "")
    provider_code = _resolve_provider_code(
        source_kind,
        provider_code=arguments.get("provider_code"),
        current_provider_code=str(current.get("provider_code") or ""),
        connection_config=dict(arguments.get("connection_config") or {}),
    )
    domain_type = _normalize_domain_type(arguments.get("domain_type") or current.get("domain_type"))
    execution_mode = _normalize_execution_mode(source_kind, arguments.get("execution_mode") or current.get("execution_mode"))
    enabled = _normalize_bool(arguments.get("enabled"), default=bool(current.get("is_enabled", True)))
    status = _normalize_status(
        arguments.get("status"),
        default="active" if enabled else "disabled",
    )
    row = auth_db.upsert_unified_data_source(
        company_id=company_id,
        code=str(current.get("code") or ""),
        name=str(arguments.get("name") or current.get("name") or ""),
        source_kind=source_kind,
        domain_type=domain_type,
        provider_code=provider_code,
        execution_mode=execution_mode,
        description=str(arguments.get("description") or current.get("description") or ""),
        status=status,
        is_enabled=enabled,
        meta=dict(current.get("meta") or {}),
    )
    if not row:
        return {"success": False, "error": "更新数据源失败"}

    _upsert_source_configs(company_id, source_id, arguments)
    updated_source = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id)
    auth_db.create_unified_data_source_event(
        company_id=company_id,
        data_source_id=source_id,
        event_type="data_source_updated",
        event_message=f"更新数据源：{updated_source.get('name') if updated_source else current.get('name')}",
        event_payload={"source_id": source_id},
    )
    return {
        "success": True,
        "source": _build_data_source_view(updated_source or row),
        "message": "数据源更新成功",
    }


async def _handle_data_source_disable(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_id = _source_id_from_args(arguments)
    current = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id)
    if not current:
        return {"success": False, "error": "数据源不存在"}
    row = auth_db.update_unified_data_source_status(
        data_source_id=source_id,
        status="disabled",
        is_enabled=False,
    )
    if not row:
        return {"success": False, "error": "停用数据源失败"}
    auth_db.create_unified_data_source_event(
        company_id=company_id,
        data_source_id=source_id,
        event_type="data_source_disabled",
        event_level="warn",
        event_message=str(arguments.get("reason") or "数据源已停用"),
        event_payload={"reason": str(arguments.get("reason") or "")},
    )
    return {
        "success": True,
        "source": _build_data_source_view(row),
        "message": "数据源已停用",
    }


async def _handle_data_source_delete(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_id = _source_id_from_args(arguments)
    current = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id)
    if not current:
        return {"success": False, "error": "数据源不存在"}

    row = auth_db.update_unified_data_source_status(
        data_source_id=source_id,
        status="deleted",
        is_enabled=False,
    )
    if not row:
        return {"success": False, "error": "删除数据源失败"}

    auth_db.create_unified_data_source_event(
        company_id=company_id,
        data_source_id=source_id,
        event_type="data_source_deleted",
        event_level="warn",
        event_message="数据源已删除",
        event_payload={"source_id": source_id},
    )
    return {
        "success": True,
        "source": _build_data_source_view(row),
        "message": "数据源已删除",
    }


async def _handle_data_source_test(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_id = _source_id_from_args(arguments)
    source_row = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id)
    if not source_row:
        return {"success": False, "error": "数据源不存在"}
    runtime_source = _merge_runtime_overrides(
        _load_runtime_source(source_row, include_secret=True),
        arguments,
    )
    connector = build_connector(runtime_source)

    if runtime_source["source_kind"] == "platform_oauth":
        platform_result = await handle_platform_tool_call(
            "platform_list_connections",
            {
                "auth_token": arguments.get("auth_token"),
                "platform_code": runtime_source.get("provider_code"),
                "mode": arguments.get("mode", ""),
            },
        )
        success = bool(platform_result.get("success"))
        result = {
            "status": "ok" if success else "error",
            "authorized_shop_count": len(platform_result.get("connections") or []),
            "message": str(platform_result.get("message") or ""),
        }
    else:
        connector_result = connector.test_connection(arguments)
        success = bool(connector_result.get("success"))
        result = {
            "status": "ok" if success else "error",
            "execution_mode": runtime_source.get("execution_mode"),
            "message": str(connector_result.get("message") or connector_result.get("error") or ""),
        }
        for key in ("db_type", "provider_code", "source_id"):
            if connector_result.get(key) is not None:
                result[key] = connector_result.get(key)

    source_health_status = "healthy" if success else "error"
    if not success and runtime_source["source_kind"] == "platform_oauth":
        source_health_status = "auth_expired"
    auth_db.update_unified_data_source_health(
        data_source_id=source_id,
        health_status=source_health_status,
        last_error_message="" if success else result["message"],
    )
    auth_db.create_unified_data_source_event(
        company_id=company_id,
        data_source_id=source_id,
        event_type="data_source_tested",
        event_level="info" if success else "error",
        event_message=result["message"],
        event_payload=result,
    )
    response = {
        "success": success,
        "source_id": source_id,
        "result": result,
        "message": result["message"],
    }
    if not success:
        response["error"] = result["message"] or "数据源测试失败"
    return response


async def _handle_data_source_authorize(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_id = _source_id_from_args(arguments)
    source_row = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id)
    if not source_row:
        return {"success": False, "error": "数据源不存在"}
    if str(source_row.get("source_kind") or "") != "platform_oauth":
        return {"success": False, "error": "仅 platform_oauth 支持授权"}

    redirect_uri = str(arguments.get("redirect_uri") or "").strip() or (
        f"https://tally-placeholder.example.com/api/data-sources/auth/callback/{source_id}"
    )
    result = await handle_platform_tool_call(
        "platform_create_auth_session",
        {
            "auth_token": arguments.get("auth_token"),
            "platform_code": source_row.get("provider_code"),
            "return_path": arguments.get("return_path", "/"),
            "redirect_uri": redirect_uri,
            "mode": arguments.get("mode", ""),
        },
    )
    if result.get("success"):
        meta = dict(source_row.get("meta") or {})
        meta["auth_status"] = "authorizing"
        auth_db.upsert_unified_data_source(
            company_id=company_id,
            code=str(source_row.get("code") or ""),
            name=str(source_row.get("name") or ""),
            source_kind="platform_oauth",
            domain_type=str(source_row.get("domain_type") or "ecommerce"),
            provider_code=str(source_row.get("provider_code") or ""),
            execution_mode=str(source_row.get("execution_mode") or "deterministic"),
            description=str(source_row.get("description") or ""),
            status=str(source_row.get("status") or "active"),
            is_enabled=bool(source_row.get("is_enabled", True)),
            meta=meta,
        )
    return result


async def _handle_data_source_callback(arguments: dict[str, Any]) -> dict[str, Any]:
    source_id = _source_id_from_args(arguments)
    source_row = _query_source_any_company(source_id)
    if not source_row:
        return {"success": False, "error": "数据源不存在"}
    if str(source_row.get("source_kind") or "") != "platform_oauth":
        return {"success": False, "error": "仅 platform_oauth 支持回调"}

    result = await handle_platform_tool_call(
        "platform_handle_auth_callback",
        {
            "platform_code": source_row.get("provider_code"),
            "state": arguments.get("state", ""),
            "code": arguments.get("code", ""),
            "error": arguments.get("error", ""),
            "error_description": arguments.get("error_description", ""),
            "callback_payload": arguments.get("callback_payload") or {},
            "mode": arguments.get("mode", ""),
        },
    )
    meta = dict(source_row.get("meta") or {})
    meta["auth_status"] = "authorized" if result.get("success") else "unauthorized"
    auth_db.upsert_unified_data_source(
        company_id=str(source_row.get("company_id") or ""),
        code=str(source_row.get("code") or ""),
        name=str(source_row.get("name") or ""),
        source_kind="platform_oauth",
        domain_type=str(source_row.get("domain_type") or "ecommerce"),
        provider_code=str(source_row.get("provider_code") or ""),
        execution_mode=str(source_row.get("execution_mode") or "deterministic"),
        description=str(source_row.get("description") or ""),
        status=str(source_row.get("status") or "active"),
        is_enabled=bool(source_row.get("is_enabled", True)),
        meta=meta,
    )
    refreshed = _query_source_any_company(source_id)
    return {
        **result,
        "source": _build_data_source_view(refreshed) if refreshed else None,
    }


def _fail_sync_job(
    *,
    company_id: str,
    source_id: str,
    resource_key: str,
    job_id: str,
    attempt_id: str,
    checkpoint_before: dict[str, Any],
    message: str,
) -> None:
    auth_db.update_unified_sync_job_attempt(
        attempt_id=attempt_id,
        attempt_status="failed",
        error_message=message,
        metrics={},
        checkpoint_after=checkpoint_before,
    )
    auth_db.update_unified_sync_job_status(
        sync_job_id=job_id,
        job_status="failed",
        error_message=message,
        checkpoint_after=checkpoint_before,
        finish_job=True,
    )
    auth_db.update_unified_data_source_health(
        data_source_id=source_id,
        health_status="error",
        last_error_message=message,
    )
    _update_dataset_health_by_resource(
        company_id=company_id,
        source_id=source_id,
        resource_key=resource_key,
        health_status="error",
        last_error_message=message,
    )


async def _execute_sync_job(
    *,
    company_id: str,
    source_id: str,
    resource_key: str,
    runtime_source: dict[str, Any],
    arguments: dict[str, Any],
    job: dict[str, Any],
    attempt: dict[str, Any],
    checkpoint_before: dict[str, Any],
    window_start: str | None,
    window_end: str | None,
) -> dict[str, Any]:
    job_id = _safe_text(job.get("id"))
    attempt_id = _safe_text(attempt.get("id"))
    try:
        result = await _run_connector_sync(runtime_source, arguments)
        rows = _sync_rows_from_payload(result)
        collection_context = _collection_context_from_args(arguments)
        collection_summary: dict[str, Any] = {}
        collection_records: list[dict[str, Any]] = []
        if collection_context:
            collection_records = _build_collection_records(
                rows=rows,
                key_fields=list(collection_context.get("key_fields") or []),
            )
        data_hash = _hash_payload(rows)
        healthy = bool(result.get("healthy", result.get("success", False)))
        if not bool(result.get("success")) or not healthy:
            message = str(result.get("error") or result.get("message") or "同步失败")
            auth_db.update_unified_sync_job_attempt(
                attempt_id=attempt_id,
                attempt_status="failed",
                error_message=message,
                metrics={"row_count": len(rows), "data_hash": data_hash, "collection_upserted": 0},
                checkpoint_after=checkpoint_before,
            )
            auth_db.update_unified_sync_job_status(
                sync_job_id=job_id,
                job_status="failed",
                error_message=message,
                checkpoint_after=checkpoint_before,
                finish_job=True,
            )
            auth_db.create_unified_data_source_event(
                company_id=company_id,
                data_source_id=source_id,
                sync_job_id=job_id,
                event_type="sync_failed",
                event_level="error",
                event_message=message,
                event_payload={"rows": len(rows), "resource_key": resource_key},
            )
            auth_db.update_unified_data_source_health(
                data_source_id=source_id,
                health_status="error",
                last_error_message=message,
            )
            _update_dataset_health_by_resource(
                company_id=company_id,
                source_id=source_id,
                resource_key=resource_key,
                health_status="error",
                last_error_message=message,
            )
            return {
                "success": False,
                "source_id": source_id,
                "job": _attach_aliases_to_job(auth_db.get_unified_sync_job_by_id(job_id)),
                "reused": False,
                "error": message,
                "message": message,
            }

        if collection_context:
            collection_summary = auth_db.upsert_dataset_collection_records(
                company_id=company_id,
                data_source_id=source_id,
                dataset_id=str(collection_context.get("dataset_id") or ""),
                dataset_code=str(collection_context.get("dataset_code") or ""),
                resource_key=resource_key,
                biz_date=str(collection_context.get("biz_date") or ""),
                sync_job_id=job_id,
                records=collection_records,
            )
            collection_summary.update(
                {
                    "dataset_id": str(collection_context.get("dataset_id") or ""),
                    "dataset_code": str(collection_context.get("dataset_code") or ""),
                    "biz_date": str(collection_context.get("biz_date") or ""),
                    "key_fields": list(collection_context.get("key_fields") or []),
                    "record_count": collection_summary.get("upserted_count", 0),
                }
            )
        checkpoint_after = _build_checkpoint_after(
            checkpoint_before,
            window_start=window_start,
            window_end=window_end,
            rows_count=int(collection_summary.get("upserted_count") or len(rows)),
            result=result,
        )
        auth_db.update_unified_sync_job_attempt(
            attempt_id=attempt_id,
            attempt_status="success",
            error_message="",
            metrics={
                "row_count": len(rows),
                "data_hash": data_hash,
                "collection_input": int(collection_summary.get("input_count") or 0),
                "collection_upserted": int(collection_summary.get("upserted_count") or 0),
                "collection_inserted": int(collection_summary.get("inserted_count") or 0),
                "collection_updated": int(collection_summary.get("updated_count") or 0),
                "collection_unchanged": int(collection_summary.get("unchanged_count") or 0),
            },
            checkpoint_after=checkpoint_after,
        )
        updated_job = auth_db.update_unified_sync_job_status(
            sync_job_id=job_id,
            job_status="success",
            error_message="",
            checkpoint_after=checkpoint_after,
            finish_job=True,
        )
        auth_db.create_unified_data_source_event(
            company_id=company_id,
            data_source_id=source_id,
            sync_job_id=job_id,
            event_type="sync_succeeded",
            event_level="info",
            event_message=str(result.get("message") or "同步成功"),
            event_payload={
                "rows": len(rows),
                "resource_key": resource_key,
                "collection_summary": collection_summary,
            },
        )
        auth_db.update_unified_data_source_health(
            data_source_id=source_id,
            health_status="healthy",
            last_error_message="",
        )
        _update_dataset_health_by_resource(
            company_id=company_id,
            source_id=source_id,
            resource_key=resource_key,
            health_status="healthy",
            last_error_message="",
            last_sync_at=_now_iso(),
        )
        return {
            "success": True,
            "source_id": source_id,
            "job": _attach_aliases_to_job(updated_job),
            "collection_summary": collection_summary,
            "reused": False,
            "message": "同步成功并写入采集记录",
        }
    except Exception as exc:  # noqa: BLE001
        message = str(exc) or "采集任务执行异常"
        logger.error("数据集采集任务执行失败: job_id=%s error=%s", job_id, message, exc_info=True)
        _fail_sync_job(
            company_id=company_id,
            source_id=source_id,
            resource_key=resource_key,
            job_id=job_id,
            attempt_id=attempt_id,
            checkpoint_before=checkpoint_before,
            message=message,
        )
        return {"success": False, "source_id": source_id, "error": message}


async def _handle_data_source_trigger_sync(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_id = _source_id_from_args(arguments)
    source_row = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id)
    if not source_row:
        return {"success": False, "error": "数据源不存在"}
    if str(source_row.get("status") or "") != "active" or not bool(source_row.get("is_enabled", True)):
        auth_db.update_unified_data_source_health(
            data_source_id=source_id,
            health_status="disabled",
            last_error_message="数据源未启用，无法触发同步",
        )
        return {"success": False, "error": "数据源未启用，无法触发同步"}

    runtime_source = _load_runtime_source(source_row, include_secret=True)
    if runtime_source["source_kind"] in AGENT_ASSISTED_KINDS:
        connector = build_connector(runtime_source)
        result = connector.trigger_sync(arguments)
        auth_db.update_unified_data_source_health(
            data_source_id=source_id,
            health_status="warning",
            last_error_message=str(result.get("message") or "该数据源需由 agent loop 执行"),
        )
        return {
            "success": False,
            "source_id": source_id,
            "error": str(result.get("error") or "agent_assisted_required"),
            "message": str(result.get("message") or "该数据源需由 agent loop 执行"),
        }

    resource_key = _resource_key_from_args(arguments)
    window_start, window_end = _window_from_args(arguments)
    checkpoint_before: dict[str, Any] = {}
    job = auth_db.create_unified_sync_job(
        company_id=company_id,
        data_source_id=source_id,
        trigger_mode=_safe_text(arguments.get("trigger_mode")) or "manual",
        resource_key=resource_key,
        idempotency_key=_safe_text(arguments.get("idempotency_key")),
        window_start=window_start,
        window_end=window_end,
        request_payload=dict(arguments.get("params") or {}),
        checkpoint_before=checkpoint_before,
    )
    if not job:
        return {"success": False, "error": "创建同步任务失败"}

    attempt = auth_db.create_unified_sync_job_attempt(
        company_id=company_id,
        sync_job_id=str(job["id"]),
        attempt_no=int(job.get("current_attempt") or 0) + 1,
        checkpoint_before=checkpoint_before,
    )
    if not attempt:
        return {"success": False, "error": "创建同步任务尝试失败"}

    execute_kwargs = {
        "company_id": company_id,
        "source_id": source_id,
        "resource_key": resource_key,
        "runtime_source": runtime_source,
        "arguments": dict(arguments),
        "job": job,
        "attempt": attempt,
        "checkpoint_before": checkpoint_before,
        "window_start": window_start,
        "window_end": window_end,
    }
    if _normalize_bool(arguments.get("background"), default=False):
        asyncio.create_task(_execute_sync_job(**execute_kwargs))
        return {
            "success": True,
            "source_id": source_id,
            "job": _attach_aliases_to_job(auth_db.get_unified_sync_job_by_id(str(job["id"])) or job),
            "reused": False,
            "queued": True,
            "message": "采集任务已创建，正在后台执行",
        }

    return await _execute_sync_job(**execute_kwargs)


async def _handle_data_source_trigger_dataset_collection(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_id = _source_id_from_args(arguments)
    dataset_row = _resolve_dataset_row(company_id=company_id, arguments=arguments)
    if not dataset_row:
        return {"success": False, "error": "发布数据集不存在"}

    resource_key = _safe_text(dataset_row.get("resource_key")) or _resource_key_from_args(arguments)
    biz_date = _collection_biz_date_from_args(arguments)
    config = _dataset_collection_config(dataset_row)
    key_fields = _dataset_collection_key_fields(dataset_row)
    if not key_fields:
        return {"success": False, "error": "数据集缺少 key_fields，无法生成采集记录唯一标识"}
    params = dict(arguments.get("params") or {})
    query = dict(params.get("query") or {})
    query.update(
        {
            "resource_key": resource_key,
            "date_field": _collection_date_field(config),
        }
    )
    params.update(
        {
            "biz_date": biz_date,
            "resource_key": resource_key,
            "dataset_id": _safe_text(dataset_row.get("id")),
            "dataset_code": _safe_text(dataset_row.get("dataset_code")),
            "collection_config": config,
            "date_field": _collection_date_field(config),
            "key_fields": key_fields,
            "query": query,
        }
    )

    payload = {
        **arguments,
        "source_id": source_id,
        "resource_key": resource_key,
        "idempotency_key": "",
        "background": False,
        "params": params,
    }
    result = await _handle_data_source_trigger_sync(payload)
    if isinstance(result.get("job"), dict):
        result["job"]["collection_scope"] = "dataset"
    return {
        **result,
        "dataset_id": _safe_text(dataset_row.get("id")),
        "dataset_code": _safe_text(dataset_row.get("dataset_code")),
        "resource_key": resource_key,
        "biz_date": biz_date,
    }


async def _handle_data_source_get_sync_job(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    job = auth_db.get_unified_sync_job_by_id(str(arguments.get("sync_job_id") or ""))
    if not job or str(job.get("company_id") or "") != company_id:
        return {"success": False, "error": "同步任务不存在"}
    return {
        "success": True,
        "job": _attach_aliases_to_job(job),
    }


async def _handle_data_source_list_sync_jobs(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_id = _source_id_from_args(arguments) or None
    status = str(arguments.get("status") or "").strip().lower() or None
    limit = int(arguments.get("limit") or 20)
    jobs = auth_db.list_unified_sync_jobs(
        company_id=company_id,
        data_source_id=source_id,
        job_status=status,
        limit=max(1, min(limit, 100)),
    )
    return {
        "success": True,
        "count": len(jobs),
        "jobs": [_attach_aliases_to_job(job) for job in jobs],
    }


async def _handle_data_source_get_dataset_collection_detail(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_id = _source_id_from_args(arguments)
    source_row = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id)
    if not source_row:
        return {"success": False, "error": "数据源不存在"}

    dataset_row = _resolve_dataset_row(company_id=company_id, arguments=arguments)
    resource_key = _resource_key_from_args(arguments)
    if dataset_row:
        resource_key = _safe_text(dataset_row.get("resource_key")) or resource_key
    if not resource_key:
        return {"success": False, "error": "缺少 resource_key"}

    limit = max(1, min(int(arguments.get("limit") or 10), 50))
    sample_limit = max(1, min(int(arguments.get("sample_limit") or 10), 50))
    jobs = [
        job
        for job in auth_db.list_unified_sync_jobs(
            company_id=company_id,
            data_source_id=source_id,
            limit=100,
        )
        if _safe_text(job.get("resource_key")) == resource_key
    ][:limit]
    stats = auth_db.get_dataset_collection_record_stats(
        company_id=company_id,
        data_source_id=source_id,
        dataset_id=_safe_text((dataset_row or {}).get("id")) or None,
        dataset_code=_safe_text((dataset_row or {}).get("dataset_code")) or None,
        resource_key=resource_key,
    )
    collection_records = auth_db.list_dataset_collection_records(
        company_id=company_id,
        data_source_id=source_id,
        dataset_id=_safe_text((dataset_row or {}).get("id")) or None,
        dataset_code=_safe_text((dataset_row or {}).get("dataset_code")) or None,
        resource_key=resource_key,
        limit=sample_limit,
        offset=0,
    )
    sample_rows = [
        dict(item.get("payload") or {})
        for item in collection_records
        if isinstance(item, dict) and isinstance(item.get("payload"), dict)
    ]

    return {
        "success": True,
        "source_id": source_id,
        "resource_key": resource_key,
        "dataset": _build_dataset_view(dataset_row) if dataset_row else None,
        "collection_stats": stats,
        "collection_records": collection_records,
        "jobs": [_attach_aliases_to_job(job) for job in jobs],
        "rows": sample_rows,
        "count": len(jobs),
        "row_count": len(sample_rows),
        "message": "已获取采集详情",
    }


async def _handle_data_source_list_collection_records(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_id = _source_id_from_args(arguments)
    source_row = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id)
    if not source_row:
        return {"success": False, "error": "数据源不存在"}

    dataset_row = _resolve_dataset_row(company_id=company_id, arguments=arguments)
    dataset_id = _safe_text((dataset_row or {}).get("id")) or _dataset_id_from_args(arguments) or None
    dataset_code = _safe_text((dataset_row or {}).get("dataset_code")) or _sanitize_dataset_code(arguments.get("dataset_code")) or None
    resource_key = _resource_key_from_args(arguments)
    if dataset_row:
        resource_key = _safe_text(dataset_row.get("resource_key")) or resource_key

    limit = max(1, min(int(arguments.get("limit") or 100), 1000))
    offset = max(0, int(arguments.get("offset") or 0))
    records = auth_db.list_dataset_collection_records(
        company_id=company_id,
        data_source_id=source_id,
        dataset_id=dataset_id,
        dataset_code=dataset_code,
        resource_key=resource_key or None,
        biz_date=_safe_text(arguments.get("biz_date")) or None,
        item_key=_safe_text(arguments.get("item_key")) or None,
        limit=limit,
        offset=offset,
    )
    stats = auth_db.get_dataset_collection_record_stats(
        company_id=company_id,
        data_source_id=source_id,
        dataset_id=dataset_id,
        dataset_code=dataset_code,
        resource_key=resource_key or None,
        biz_date=_safe_text(arguments.get("biz_date")) or None,
    )
    return {
        "success": True,
        "source_id": source_id,
        "dataset_id": dataset_id or "",
        "dataset_code": dataset_code or "",
        "resource_key": resource_key or "",
        "records": records,
        "stats": stats,
        "count": len(records),
        "limit": limit,
        "offset": offset,
    }


async def _handle_data_source_export_collection_records(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_id = _source_id_from_args(arguments)
    source_row = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id)
    if not source_row:
        return {"success": False, "error": "数据源不存在"}

    dataset_row = _resolve_dataset_row(company_id=company_id, arguments=arguments)
    dataset_id = _safe_text((dataset_row or {}).get("id")) or _dataset_id_from_args(arguments)
    dataset_code = _safe_text((dataset_row or {}).get("dataset_code")) or _sanitize_dataset_code(arguments.get("dataset_code"))
    resource_key = _resource_key_from_args(arguments)
    if dataset_row:
        resource_key = _safe_text(dataset_row.get("resource_key")) or resource_key

    query = arguments.get("query") if isinstance(arguments.get("query"), dict) else {}
    table_name = _safe_text(
        arguments.get("table_name")
        or (dataset_row or {}).get("business_name")
        or (dataset_row or {}).get("dataset_name")
        or dataset_code
        or resource_key
        or source_id
    )
    biz_date = _safe_text(arguments.get("biz_date") or query.get("biz_date"))
    file_path, row_count = _export_collection_records_to_excel(
        company_id=company_id,
        data_source_id=source_id,
        dataset_id=dataset_id,
        dataset_code=dataset_code,
        resource_key=resource_key,
        biz_date=biz_date,
        table_name=table_name,
        query=query,
    )
    return {
        "success": True,
        "source_id": source_id,
        "dataset_id": dataset_id,
        "dataset_code": dataset_code,
        "resource_key": resource_key,
        "biz_date": biz_date,
        "table_name": table_name,
        "file_path": file_path,
        "row_count": row_count,
        "query": query,
        "message": "已导出采集记录",
    }


async def _handle_data_source_preview(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_id = _source_id_from_args(arguments)
    limit = int(arguments.get("limit") or 20)
    source_row = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id)
    if not source_row:
        return {"success": False, "error": "数据源不存在"}

    dataset_row = _resolve_dataset_row(company_id=company_id, arguments=arguments)
    collection_rows = _load_dataset_sample_rows_from_collection_records(
        company_id=company_id,
        data_source_id=source_id,
        dataset_id=_safe_text((dataset_row or {}).get("id")),
        dataset_code=_safe_text((dataset_row or {}).get("dataset_code")),
        resource_key=_safe_text((dataset_row or {}).get("resource_key")) or _resource_key_from_args(arguments),
        limit=limit,
    )
    if collection_rows:
        return {
            "success": True,
            "source_id": source_id,
            "count": len(collection_rows),
            "rows": collection_rows,
            "message": "已返回采集记录样例",
        }

    runtime_source = _load_runtime_source(source_row, include_secret=True)
    if runtime_source["source_kind"] == "platform_oauth":
        result = await handle_platform_tool_call(
            "platform_list_connections",
            {
                "auth_token": arguments.get("auth_token"),
                "platform_code": runtime_source.get("provider_code"),
                "mode": arguments.get("mode", ""),
            },
        )
        rows = []
        for item in result.get("connections") or []:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "shop_id": item.get("external_shop_id"),
                    "shop_name": item.get("external_shop_name"),
                    "auth_status": item.get("auth_status"),
                    "status": item.get("status"),
                }
            )
        return {
            "success": bool(result.get("success", True)),
            "source_id": source_id,
            "count": min(len(rows), limit),
            "rows": rows[: max(1, min(limit, 100))],
            "message": str(result.get("message") or ""),
        }

    connector = build_connector(runtime_source)
    result = connector.preview(arguments)
    rows = []
    for row in result.get("rows") or []:
        if isinstance(row, dict):
            rows.append(row)
    return {
        "success": bool(result.get("success", True)),
        "source_id": source_id,
        "count": len(rows[: max(1, min(limit, 100))]),
        "rows": rows[: max(1, min(limit, 100))],
        "message": str(result.get("message") or ""),
    }
