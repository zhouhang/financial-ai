"""模式构建器 – 根据用户答案构建对账 JSON 模式。"""

from __future__ import annotations

from typing import Any


def build_schema(
    *,
    description: str,
    business_file_patterns: list[str],
    finance_file_patterns: list[str],
    business_field_roles: dict[str, str | list[str]],
    finance_field_roles: dict[str, str | list[str]],
    key_field_role: str = "order_id",
    order_id_pattern: str | None = None,
    amount_tolerance: float = 0.1,
    check_order_status: bool = True,
    business_cleaning: dict[str, Any] | None = None,
    finance_cleaning: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构建与 finance-mcp 兼容的完整对账模式字典。"""

    schema: dict[str, Any] = {
        "version": "1.0",
        "description": description,
        "data_sources": {
            "business": {
                "file_pattern": business_file_patterns,
                "field_roles": business_field_roles,
            },
            "finance": {
                "file_pattern": finance_file_patterns,
                "field_roles": finance_field_roles,
            },
        },
        "key_field_role": key_field_role,
        "tolerance": {
            "date_format": "%Y-%m-%d",
            "amount_diff_max": amount_tolerance,
        },
    }

    # --- 数据清理规则 ---
    cleaning: dict[str, Any] = {}

    if business_cleaning:
        cleaning["business"] = business_cleaning
    else:
        biz_transforms: list[dict] = [
            {"field": "amount", "operation": "round", "decimals": 2, "description": "金额保留2位小数"},
            {"field": "order_id", "operation": "strip", "description": "订单号去除首尾空格"},
        ]
        biz_filters: list[dict] = []
        if order_id_pattern:
            biz_filters.append({
                "condition": f"str(row.get('order_id', '')).startswith('{order_id_pattern}')",
                "description": f"只保留{order_id_pattern}开头的订单号",
            })
        cleaning["business"] = {
            "field_transforms": biz_transforms,
            "row_filters": biz_filters,
            "aggregations": [],  # 不添加默认聚合，用户通过配置项添加「相同订单号按金额累加」等
            "global_transforms": [
                {"operation": "drop_na", "subset": ["order_id"], "description": "删除订单号为空的记录"}
            ],
        }

    if finance_cleaning:
        cleaning["finance"] = finance_cleaning
    else:
        fin_transforms: list[dict] = [
            {"field": "amount", "operation": "abs", "description": "金额取绝对值"},
            {"field": "amount", "operation": "round", "decimals": 2, "description": "金额保留2位小数"},
            {"field": "order_id", "operation": "strip", "description": "订单号去除首尾空格"},
        ]
        fin_filters: list[dict] = []
        if order_id_pattern:
            fin_filters.append({
                "condition": f"str(row.get('order_id', '')).startswith('{order_id_pattern}')",
                "description": f"只保留{order_id_pattern}开头的订单号",
            })
        cleaning["finance"] = {
            "field_transforms": fin_transforms,
            "row_filters": fin_filters,
            "aggregations": [],  # 不添加默认聚合，用户通过配置项添加「相同订单号按金额累加」等
            "global_transforms": [
                {"operation": "drop_na", "subset": ["order_id", "amount"], "description": "删除关键字段为空的记录"}
            ],
        }

    cleaning["global"] = {
        "global_transforms": [
            {"operation": "drop_duplicates", "subset": ["order_id"], "keep": "first", "description": "全局去重"}
        ]
    }
    schema["data_cleaning_rules"] = cleaning

    # --- 自定义验证 ---
    validations: list[dict] = [
        {
            "name": "missing_in_business",
            "condition_expr": "fin_exists and not biz_exists",
            "issue_type": "missing_in_business",
            "detail_template": "{fin_file}存在，{biz_file}无此订单记录",
        },
        {
            "name": "missing_in_finance",
            "condition_expr": "biz_exists and not fin_exists",
            "issue_type": "missing_in_finance",
            "detail_template": "{biz_file}存在，{fin_file}无此订单记录",
        },
        {
            "name": "amount_mismatch",
            "condition_expr": (
                "biz_exists and fin_exists and biz.get('amount') is not None "
                "and fin.get('amount') is not None "
                "and abs(float(biz.get('amount', 0)) - float(fin.get('amount', 0))) > amount_diff_max"
            ),
            "issue_type": "amount_mismatch",
            "detail_template": (
                "{biz_file}金额 {biz[amount]} vs {fin_file}金额 {fin[amount]}，"
                "差额 {amount_diff_formatted} 超出容差 {amount_diff_max}"
            ),
        },
    ]

    # 仅当用户配置了 status 字段映射且明确要求检查状态时，才添加 order_status_mismatch
    # 用户未配置 status 时不应添加，避免误报
    has_status_mapping = "status" in business_field_roles
    if check_order_status and has_status_mapping:
        validations.append({
            "name": "order_status_mismatch",
            "condition_expr": (
                "biz_exists and str(biz.get('status', '')).lower() != 'success' "
                "and str(biz.get('status', '')).lower() != '成功' "
                "and str(biz.get('status', '')).lower() != '交易成功'"
            ),
            "issue_type": "order_status_mismatch",
            "detail_template": "订单状态不一致：状态为 {biz[status]}，不是允许的成功状态",
        })

    schema["custom_validations"] = validations
    return schema
