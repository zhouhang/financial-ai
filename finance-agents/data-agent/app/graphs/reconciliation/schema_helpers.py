"""Schema 辅助函数模块

包含 Schema 转换、验证、合并等功能。
"""

from __future__ import annotations

import copy
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _rewrite_schema_transforms_to_mapped_fields(schema: dict) -> None:
    """将 schema 中 transform/expression 的原始列名替换为映射后的角色名（原地修改）。

    LLM 生成的规则使用原始表头（如 sup订单号、roc_oid），
    但 data_cleaner 在字段映射之后执行 transform，此时列名已是角色名（order_id、amount）。
    保存前重写，确保生成的 JSON 文件使用映射字段名。
    """
    if not isinstance(schema, dict):
        return
    data_sources = schema.get("data_sources", {})
    cleaning_rules = schema.get("data_cleaning_rules", {})
    if not cleaning_rules:
        return

    def _rewrite_expr(expr: str, field_roles_all_sources: dict) -> str:
        """将 expr 中 row.get('orig_col', x) 替换为 row.get('role', x)"""
        if not expr or not isinstance(expr, str):
            return expr
        result = expr
        for orig_col, role in field_roles_all_sources.items():
            if orig_col == role:
                continue
            for q in ("'", '"'):
                old_pat = f"row.get({q}{orig_col}{q}"
                new_pat = f"row.get({q}{role}{q}"
                result = result.replace(old_pat, new_pat)
        return result

    # 合并所有数据源的 field_roles，构建 原始列名 -> 角色名
    orig_to_role = {}
    for _src, src_config in data_sources.items():
        for role, orig_cols in src_config.get("field_roles", {}).items():
            for orig in ([orig_cols] if isinstance(orig_cols, str) else orig_cols):
                orig_to_role[orig] = role

    for source_name, rules in cleaning_rules.items():
        for t in rules.get("field_transforms", []):
            for key in ("transform", "expression"):
                if key in t and t[key]:
                    t[key] = _rewrite_expr(t[key], orig_to_role)
        for rf in rules.get("row_filters", []):
            if "condition" in rf and rf["condition"]:
                rf["condition"] = _rewrite_expr(rf["condition"], orig_to_role)


def _preview_schema(schema: dict, analyses: list[dict]) -> dict:
    """简单统计预览。"""
    biz_count = 0
    fin_count = 0
    for a in analyses:
        src = a.get("guessed_source")
        cnt = a.get("row_count", 0)
        if src == "business":
            biz_count += cnt
        elif src == "finance":
            fin_count += cnt

    estimated_match = min(biz_count, fin_count)
    return {
        "biz_count": biz_count,
        "fin_count": fin_count,
        "estimated_match": estimated_match,
    }


def _build_dummy_analyses_from_mappings(mappings: dict[str, Any]) -> list[dict]:
    """从 mappings 构建虚拟 analyses，供编辑模式下 _adjust_field_mappings_with_llm 使用。"""
    analyses = []
    for src, label in [("business", "文件1"), ("finance", "文件2")]:
        cols = []
        for role, col in mappings.get(src, {}).items():
            if isinstance(col, list):
                cols.extend(col)
            elif col:
                cols.append(str(col))
        analyses.append({"guessed_source": src, "filename": label, "columns": cols})
    return analyses


def _validate_and_deduplicate_rules(schema: dict) -> dict:
    """验证和去重规则，特别是防止重复的字段转换规则。

    问题场景：
    1. 有两个订单号规则：第一个"去单引号截取21位"，第二个"去单引号截取21位、104开头"
    2. 这会导致重复处理同一字段
    3. 两个数据源都有相同的row_filters会导致对账结果显示0个差异

    解决方案：
    1. 检测重复的字段transforms（相同字段的多个规则）
    2. 对于同一字段的多个rules，合并为一个（先format后filter）
    3. 将过滤逻辑转移到row_filters
    4. 检测并删除business中的row_filters（row_filters只应该用于finance）
    """
    result = copy.deepcopy(schema)

    for source in ["business", "finance"]:
        cleaning_rules = result.get("data_cleaning_rules", {}).get(source, {})
        field_transforms = cleaning_rules.get("field_transforms", [])

        # 检测同一字段的多个transforms
        field_groups = {}
        for idx, transform in enumerate(field_transforms):
            field = transform.get("field")
            if field not in field_groups:
                field_groups[field] = []
            field_groups[field].append((idx, transform))

        # 对于订单号字段，特殊处理去重
        if "order_id" in field_groups and len(field_groups["order_id"]) > 1:
            order_id_rules = field_groups["order_id"]
            logger.warning(f"⚠️ 检测到 {source} 中有 {len(order_id_rules)} 个订单号transform规则，可能存在重复")

            # 检查是否有两个非常相似的规则（都是去单引号截取21位）
            descriptions = [r[1].get("description", "") for r in order_id_rules]
            if any("去单引号" in d and "21" in d for d in descriptions) and len(descriptions) > 1:
                # 保留第一个规则，删除其他相似的
                rules_to_keep = []
                found_format_rule = False

                for idx, transform in order_id_rules:
                    desc = transform.get("description", "")
                    is_format_rule = "去单引号" in desc and "21" in desc and "104" not in desc

                    if is_format_rule:
                        if not found_format_rule:
                            rules_to_keep.append((idx, transform))
                            found_format_rule = True
                        else:
                            logger.warning(f"  删除重复的规则（保留第一个）: {desc}")
                    else:
                        rules_to_keep.append((idx, transform))

                # 重建field_transforms，只保留未重复的规则
                if len(rules_to_keep) < len(order_id_rules):
                    new_field_transforms = []
                    for idx, transform in enumerate(field_transforms):
                        field = transform.get("field")
                        if field == "order_id":
                            # 只保留rules_to_keep中的
                            if any(kk[1] == transform for kk in rules_to_keep):
                                new_field_transforms.append(transform)
                        else:
                            new_field_transforms.append(transform)

                    result["data_cleaning_rules"][source]["field_transforms"] = new_field_transforms
                    logger.info(f"✅ 去重后 {source} 的订单号transform规则数: {len([r for r in new_field_transforms if r.get('field') == 'order_id'])}")

    # 🔴 关键检查：防止对账结果显示0个差异的情况
    # 如果两个数据源有相同的row_filters，会导致和数据被过滤成相同，无法对账
    business_row_filters = result.get("data_cleaning_rules", {}).get("business", {}).get("row_filters", [])
    finance_row_filters = result.get("data_cleaning_rules", {}).get("finance", {}).get("row_filters", [])

    if business_row_filters and finance_row_filters:
        # 检查是否有相同的条件
        business_conditions = {json.dumps(f.get("condition"), sort_keys=True): f for f in business_row_filters}
        finance_conditions = {json.dumps(f.get("condition"), sort_keys=True): f for f in finance_row_filters}

        common_conditions = set(business_conditions.keys()) & set(finance_conditions.keys())
        if common_conditions:
            logger.error("🔴 严重问题：业务数据和财务数据有相同的row_filters，会导致对账失败！")
            logger.error(f"   相同的条件: {common_conditions}")
            logger.error("   这会导致两个数据源过滤后记录数相同，无法显示实际差异")
            logger.error("   正确做法：row_filters只应该用于财务数据，用于排除特殊内部记录（如加款单）")

            # 自动删除业务数据的row_filters
            logger.warning(f"⚠️  已自动删除业务数据中的 {len(business_row_filters)} 个row_filters")
            if "data_cleaning_rules" in result and "business" in result["data_cleaning_rules"]:
                result["data_cleaning_rules"]["business"]["row_filters"] = []
    elif business_row_filters and not finance_row_filters:
        logger.warning("⚠️ 检测到业务数据有row_filters但财务数据没有，这可能不符合预期")
        logger.warning("   row_filters通常只应该用于财务数据，用于排除加款单等特殊记录")
        logger.warning(f"   正在删除业务数据的{len(business_row_filters)}个row_filters")
        if "data_cleaning_rules" in result and "business" in result["data_cleaning_rules"]:
            result["data_cleaning_rules"]["business"]["row_filters"] = []

    return result


def _merge_json_snippets(base_schema: dict, snippets: list[dict]) -> dict:
    """将多个JSON片段合并到基础schema中。

    Args:
        base_schema: 基础schema（从模板或默认值）
        snippets: JSON片段列表，每个片段包含要合并的配置（支持 json_snippet 包装或直接 dict）

    Returns:
        合并后的完整schema
    """
    result = copy.deepcopy(base_schema)

    for snippet_info in snippets:
        snippet = snippet_info.get("json_snippet", snippet_info) if isinstance(snippet_info, dict) else {}
        if not snippet:
            continue

        # 深度合并（排除 custom_validations，仅使用 base_schema 的，避免 LLM 误输出导致 format 报错）
        _skip_keys = frozenset({"custom_validations"})

        def deep_merge(target: dict, source: dict) -> None:
            for key, value in source.items():
                if key in _skip_keys:
                    continue
                if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                    deep_merge(target[key], value)
                elif key in target and isinstance(target[key], list) and isinstance(value, list):
                    # 对于列表，追加新项（避免完全重复的项）
                    for item in value:
                        # 简单去重：如果item是dict，检查是否已存在相同的项
                        if isinstance(item, dict):
                            # 通过JSON字符串比较来判断是否重复
                            item_str = json.dumps(item, sort_keys=True)
                            exists = any(
                                json.dumps(existing, sort_keys=True) == item_str
                                for existing in target[key]
                                if isinstance(existing, dict)
                            )
                            if not exists:
                                target[key].append(item)
                        else:
                            if item not in target[key]:
                                target[key].append(item)
                else:
                    # 直接覆盖（如 tolerance.amount_diff_max）
                    target[key] = value

        deep_merge(result, snippet)

    return result


__all__ = [
    "_rewrite_schema_transforms_to_mapped_fields",
    "_preview_schema",
    "_build_dummy_analyses_from_mappings",
    "_validate_and_deduplicate_rules",
    "_merge_json_snippets",
]
