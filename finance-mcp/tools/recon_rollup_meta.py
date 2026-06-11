"""Derive recon daily digest rollup metadata for execution run plans."""
from __future__ import annotations

from copy import deepcopy
from typing import Any


_DOMAIN = "ecom"
_ROLLUP_WARNING = "无法从对账规则推导日报 rollup 字段映射"


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _first_rule(recon_rule: dict[str, Any]) -> dict[str, Any]:
    for item in _safe_list(_safe_dict(recon_rule).get("rules")):
        if isinstance(item, dict):
            return item
    return {}


def _first_key_mapping(recon_config: dict[str, Any]) -> tuple[str, str]:
    key_columns = _safe_dict(recon_config.get("key_columns"))
    for item in _safe_list(key_columns.get("mappings")):
        mapping = _safe_dict(item)
        source_field = _text(mapping.get("source_field"))
        target_field = _text(mapping.get("target_field"))
        if source_field and target_field:
            return source_field, target_field
    return _text(key_columns.get("source_field")), _text(key_columns.get("target_field"))


def _first_compare_mapping(recon_config: dict[str, Any]) -> tuple[str, str]:
    columns = _safe_dict(recon_config.get("compare_columns"))
    for item in _safe_list(columns.get("columns")):
        column = _safe_dict(item)
        source_column = _text(column.get("source_column"))
        target_column = _text(column.get("target_column"))
        if source_column and target_column:
            return source_column, target_column
    return "", ""


def _infer_recon_type(plan_name: str, source_amount: str, target_amount: str) -> str:
    if "订单" in plan_name and "资金" not in plan_name:
        return "order"
    if "资金" in plan_name:
        return "fund"
    if target_amount in {"订单实际金额（元）", "订单实际金额", "实际打款金额", "打款金额"}:
        return "fund"
    if source_amount in {"含税销售金额", "销售金额"}:
        return "order"
    return "fund"


def _display_date_field(input_bindings: list[dict[str, Any]], side: str) -> str:
    for raw_binding in input_bindings:
        binding = _safe_dict(raw_binding)
        binding_side = _text(binding.get("side")).lower()
        if binding_side and binding_side != side:
            continue
        query = _safe_dict(binding.get("query"))
        if not query:
            query = _safe_dict(_safe_dict(binding.get("filter_config")).get("query"))
        value = _text(query.get("display_date_field"), query.get("date_field"), query.get("biz_date_field"))
        if value:
            return value
    return ""


def _canonical_field_mapping(
    *,
    recon_type: str,
    source_order_field: str,
    target_order_field: str,
    source_amount: str,
    target_amount: str,
    input_bindings: list[dict[str, Any]],
) -> dict[str, Any]:
    source_date = _display_date_field(input_bindings, "left")
    target_date = _display_date_field(input_bindings, "right")
    if recon_type == "order":
        source_date = _text(source_date, "订单完成时间", "order_finish_time")
        target_date = _text(target_date, "订单付款时间")
    else:
        source_date = _text(source_date, "订单付款时间")
        target_date = _text(target_date, "打款时间")

    return {
        "domain": _DOMAIN,
        "canonical": {
            "order_no": {"side": "source", "from": source_order_field, "type": "id"},
            "receivable_amount": {"side": "source", "from": source_amount, "type": "money"},
            "refund_amount": {
                "side": "source",
                "from": "退款金额",
                "type": "money",
                "default": 0,
            },
            "pay_time": {"side": "source", "from": source_date, "type": "datetime"},
            "settled_amount": {"side": "target", "from": target_amount, "type": "money"},
            "settle_time": {"side": "target", "from": target_date, "type": "datetime"},
        },
    }


def enrich_plan_meta_with_rollup(
    *,
    plan_name: str,
    schedule_type: str,
    plan_meta_json: dict[str, Any] | None,
    recon_rule: dict[str, Any] | None,
    input_bindings_json: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Return plan metadata with inferred daily digest rollup config when possible.

    Existing rollup metadata is treated as user-authored and preserved.
    """
    meta = deepcopy(_safe_dict(plan_meta_json))
    if _safe_dict(meta.get("rollup")):
        return meta, []
    if _text(schedule_type) != "daily":
        return meta, []

    rule = _first_rule(_safe_dict(recon_rule))
    recon_config = _safe_dict(rule.get("recon"))
    source_order_field, target_order_field = _first_key_mapping(recon_config)
    source_amount, target_amount = _first_compare_mapping(recon_config)
    if not all([source_order_field, target_order_field, source_amount, target_amount]):
        return meta, [_ROLLUP_WARNING]

    recon_type = _infer_recon_type(_text(plan_name), source_amount, target_amount)
    meta["rollup"] = {
        "enabled": True,
        "domain": _DOMAIN,
        "recon_type": recon_type,
        "field_mapping": _canonical_field_mapping(
            recon_type=recon_type,
            source_order_field=source_order_field,
            target_order_field=target_order_field,
            source_amount=source_amount,
            target_amount=target_amount,
            input_bindings=[item for item in _safe_list(input_bindings_json) if isinstance(item, dict)],
        ),
    }
    return meta, []


def has_enabled_rollup(plan_meta_json: dict[str, Any] | None) -> bool:
    rollup = _safe_dict(_safe_dict(plan_meta_json).get("rollup"))
    if not rollup or rollup.get("enabled") is False:
        return False
    field_mapping = _safe_dict(rollup.get("field_mapping"))
    canonical = _safe_dict(field_mapping.get("canonical"))
    required = {
        "order_no",
        "receivable_amount",
        "refund_amount",
        "settled_amount",
        "pay_time",
        "settle_time",
    }
    return required.issubset(set(canonical))
