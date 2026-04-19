from __future__ import annotations

import json
from typing import Any

from .semantic_utils import format_field_display, format_table_display, format_table_label


_PROC_TARGET_LABELS = {
    "left_recon_ready": "左侧整理结果表",
    "right_recon_ready": "右侧整理结果表",
}

_RECON_OUTPUT_LABELS = {
    "summary": "核对汇总",
    "source_only": "左侧独有",
    "target_only": "右侧独有",
    "matched_with_diff": "差异记录",
}

_FILTER_OPERATOR_LABELS: dict[str, str] = {
    "=": "等于",
    "==": "等于",
    "!=": "不等于",
    "<>": "不等于",
    ">": "大于",
    ">=": "大于等于",
    "<": "小于",
    "<=": "小于等于",
    "in": "在范围内",
    "not_in": "不在范围内",
    "in_list": "在列表中",
    "not_in_list": "不在列表中",
    "is_null": "为空",
    "is_not_null": "不为空",
    "contains": "包含",
    "not_contains": "不包含",
    "starts_with": "以…开头",
    "ends_with": "以…结尾",
    "between": "介于",
}

_META_GOAL_MARKERS = (
    "json 单次生成器",
    "单次生成器",
    "tally 财务 ai",
    "不要输出",
    "只负责返回",
    "skill",
    "generator",
)


def _target_label(target_table: str) -> str:
    normalized = str(target_table or "").strip()
    return _PROC_TARGET_LABELS.get(normalized, normalized or "结果表")


def _normalize_goal_text(goal_hint: str, fallback: str) -> str:
    for raw_text in (goal_hint, fallback):
        text = str(raw_text or "").strip()
        lowered = text.lower()
        if not text:
            continue
        if any(marker in lowered for marker in _META_GOAL_MARKERS):
            continue
        return text
    return ""


def _stringify_formula(expr: Any, *, max_length: int = 48) -> str:
    text = str(expr or "").strip()
    if not text:
        return "公式"
    return text if len(text) <= max_length else f"{text[:max_length]}..."


def _describe_proc_value(
    value: Any,
    *,
    field_label_map: dict[str, str] | None = None,
    table_label_map: dict[str, str] | None = None,
) -> str:
    if not isinstance(value, dict):
        return "未知表达式"
    value_type = str(value.get("type") or "").strip()
    if value_type == "source":
        source = value.get("source")
        if isinstance(source, dict):
            alias = str(source.get("alias") or "").strip()
            field = str(source.get("field") or "").strip()
            if field:
                field_display = format_field_display(field, field_label_map)
                if alias:
                    table_label = format_table_label(alias, table_label_map)
                    # 只在 alias 有业务名翻译时才展示表前缀，否则省略
                    if table_label != alias:
                        return f"{table_label}.{field_display}"
                return field_display
        return "源字段"
    if value_type == "formula":
        expr = value.get("expr")
        # 字符串字面量显示为"固定值"而非"公式"
        if isinstance(expr, str) and expr:
            return f"固定值：{expr}"
        return f"公式 {_stringify_formula(expr)}"
    if value_type == "template_source":
        source = value.get("source")
        if isinstance(source, dict):
            alias = str(source.get("alias") or "").strip()
            field = str(source.get("field") or "").strip()
            if field:
                field_display = format_field_display(field, field_label_map)
                if alias:
                    table_display = format_table_display(alias, table_label_map)
                    if table_display != alias:
                        return f"模板 {table_display}.{field_display}"
                return f"模板 {field_display}"
        return "模板字段"
    if value_type == "function":
        func_name = str(value.get("name") or value.get("function") or "").strip()
        return f"函数 {func_name}" if func_name else "函数计算"
    if value_type == "context":
        context_name = str(value.get("name") or value.get("context") or "").strip()
        return f"上下文 {context_name}" if context_name else "上下文值"
    if value_type == "lookup":
        lookup_table = str(value.get("lookup_table") or value.get("table") or "").strip()
        return f"lookup {lookup_table}" if lookup_table else "lookup"
    return value_type or "未知表达式"


def _render_proc_mapping_summary(
    mappings: list[dict[str, Any]],
    *,
    field_label_map: dict[str, str] | None = None,
    table_label_map: dict[str, str] | None = None,
    limit: int = 8,
) -> str:
    rendered: list[str] = []
    for mapping in mappings:
        if not isinstance(mapping, dict):
            continue
        target_field = str(mapping.get("target_field") or mapping.get("target_field_template") or "").strip()
        if not target_field:
            continue
        rendered.append(
            f"{format_field_display(target_field, field_label_map)} ← "
            f"{_describe_proc_value(mapping.get('value'), field_label_map=field_label_map, table_label_map=table_label_map)}"
        )
        if len(rendered) >= limit:
            break
    if not rendered:
        return ""
    hidden_count = max(len([item for item in mappings if isinstance(item, dict)]) - len(rendered), 0)
    suffix = f" 等 {hidden_count + len(rendered)} 个字段" if hidden_count else ""
    return f"字段写入：{'；'.join(rendered)}{suffix}。"


def _render_proc_match_summary(match: Any, *, field_label_map: dict[str, str] | None = None) -> str:
    if not isinstance(match, dict):
        return ""
    sources = [item for item in list(match.get("sources") or []) if isinstance(item, dict)]
    rendered: list[str] = []
    for source in sources:
        alias = str(source.get("alias") or "").strip()
        keys = [item for item in list(source.get("keys") or []) if isinstance(item, dict)]
        for key in keys:
            field = str(key.get("field") or "").strip()
            target_field = str(key.get("target_field") or "").strip()
            if field and target_field:
                field_text = format_field_display(field, field_label_map)
                target_text = format_field_display(target_field, field_label_map)
                rendered.append(
                    f"{alias}.{field_text} → {target_text}" if alias else f"{field_text} → {target_text}"
                )
    if not rendered:
        return ""
    return f"对齐键：{'；'.join(rendered[:6])}。"


def _render_proc_filter_summary(
    filter_value: Any,
    *,
    field_label_map: dict[str, str] | None = None,
) -> str:
    if not isinstance(filter_value, dict):
        return ""
    conditions = [item for item in list(filter_value.get("conditions") or []) if isinstance(item, dict)]
    rendered: list[str] = []
    for condition in conditions[:4]:
        column = str(condition.get("column") or condition.get("field") or "").strip()
        operator = str(condition.get("operator") or "").strip()
        if not column or not operator:
            continue
        column_text = format_field_display(column, field_label_map)
        operator_label = _FILTER_OPERATOR_LABELS.get(operator, operator)
        if "value" in condition:
            rendered.append(
                f"{column_text} {operator_label} {json.dumps(condition.get('value'), ensure_ascii=False)}"
            )
        elif condition.get("values") is not None:
            rendered.append(
                f"{column_text} {operator_label} {json.dumps(condition.get('values'), ensure_ascii=False)}"
            )
        else:
            rendered.append(f"{column_text} {operator_label}")
    if not rendered:
        return ""
    logic = str(filter_value.get("logic") or "and").strip().lower()
    connector = " 或 " if logic == "or" else " 且 "
    return f"过滤条件：{connector.join(rendered)}。"


def _render_proc_aggregate_summary(
    aggregate_value: Any,
    *,
    field_label_map: dict[str, str] | None = None,
) -> str:
    if not isinstance(aggregate_value, dict):
        return ""
    group_by = [
        format_field_display(str(item).strip(), field_label_map)
        for item in list(aggregate_value.get("group_by") or [])
        if str(item).strip()
    ]
    aggregations = [item for item in list(aggregate_value.get("aggregations") or []) if isinstance(item, dict)]
    if not group_by and not aggregations:
        return ""
    parts: list[str] = []
    if group_by:
        parts.append(f"按 {'、'.join(group_by)} 分组")
    if aggregations:
        agg_rendered: list[str] = []
        for item in aggregations[:4]:
            alias = str(item.get("alias") or item.get("name") or "").strip()
            function = str(item.get("function") or "").strip()
            field = str(item.get("field") or item.get("source_field") or item.get("column") or "").strip()
            field = format_field_display(field, field_label_map)
            text = f"{function}({field})" if function and field else alias or function or field
            if alias and alias != text:
                text = f"{alias}={text}"
            if text:
                agg_rendered.append(text)
        if agg_rendered:
            parts.append(f"聚合计算 {'；'.join(agg_rendered)}")
    return f"聚合规则：{'，'.join(parts)}。" if parts else ""


def render_proc_rule_summary(
    rule_json: dict[str, Any],
    *,
    field_label_map: dict[str, str] | None = None,
    table_label_map: dict[str, str] | None = None,
) -> str:
    steps = rule_json.get("steps")
    if not isinstance(steps, list) or not steps:
        return ""
    side_sources: dict[str, list[str]] = {"left_recon_ready": [], "right_recon_ready": []}
    for step in steps:
        if not isinstance(step, dict) or str(step.get("action") or "").strip() != "write_dataset":
            continue
        target_table = str(step.get("target_table") or "").strip()
        if target_table not in side_sources:
            continue
        side_sources[target_table] = [
            str(source.get("table") or source.get("alias") or "").strip()
            for source in list(step.get("sources") or [])
            if isinstance(source, dict) and str(source.get("table") or source.get("alias") or "").strip()
        ]
    parts: list[str] = []
    for target_table in ("left_recon_ready", "right_recon_ready"):
        sources = "、".join(side_sources.get(target_table) or [])
        if sources:
            display_sources = "、".join(
                format_table_label(source, table_label_map) for source in side_sources.get(target_table) or []
            )
            parts.append(f"{_target_label(target_table)}来自 {display_sources or sources}")
    return "；".join(parts) + "。" if parts else "输出左右两份可对账数据。"


def render_proc_draft_text(
    rule_json: dict[str, Any],
    *,
    goal_hint: str = "",
    field_label_map: dict[str, str] | None = None,
    table_label_map: dict[str, str] | None = None,
) -> str:
    steps = rule_json.get("steps")
    if not isinstance(steps, list) or not steps:
        return ""
    lines: list[str] = ["数据整理配置说明"]
    role_desc = _normalize_goal_text(goal_hint, str(rule_json.get("role_desc") or ""))
    if role_desc:
        lines.append(f"目标：{role_desc}")
    summary = render_proc_rule_summary(
        rule_json,
        field_label_map=field_label_map,
        table_label_map=table_label_map,
    )
    if summary:
        lines.append(summary)
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            continue
        action = str(step.get("action") or "").strip()
        target_table = str(step.get("target_table") or "").strip()
        target_label = _target_label(target_table)
        if action == "create_schema":
            schema = step.get("schema")
            columns = []
            if isinstance(schema, dict):
                for column in list(schema.get("columns") or []):
                    if not isinstance(column, dict):
                        continue
                    column_name = str(column.get("name") or "").strip()
                    if column_name:
                        columns.append(column_name)
            if columns:
                lines.append(
                    "步骤"
                    f"{index}：定义{target_label}，输出字段："
                    f"{'、'.join(format_field_display(column, field_label_map) for column in columns)}。"
                )
            else:
                lines.append(f"步骤{index}：定义{target_label}的输出结构。")
            continue
        if action == "write_dataset":
            sources = [
                str(source.get("table") or source.get("alias") or "").strip()
                for source in list(step.get("sources") or [])
                if isinstance(source, dict) and str(source.get("table") or source.get("alias") or "").strip()
            ]
            source_text = "、".join(
                format_table_label(source, table_label_map) for source in sources
            ) if sources else "当前数据集"
            line_parts = [
                f"步骤{index}：将 {source_text} 整理后写入{target_label}。"
            ]
            match_summary = _render_proc_match_summary(step.get("match"), field_label_map=field_label_map)
            if match_summary:
                line_parts.append(match_summary)
            filter_summary = _render_proc_filter_summary(
                step.get("filter"),
                field_label_map=field_label_map,
            )
            if filter_summary:
                line_parts.append(filter_summary)
            aggregate_summary = _render_proc_aggregate_summary(
                step.get("aggregate"),
                field_label_map=field_label_map,
            )
            if aggregate_summary:
                line_parts.append(aggregate_summary)
            mapping_summary = _render_proc_mapping_summary(
                [item for item in list(step.get("mappings") or []) if isinstance(item, dict)],
                field_label_map=field_label_map,
                table_label_map=table_label_map,
            )
            if mapping_summary:
                line_parts.append(mapping_summary)
            lines.append(" ".join(line_parts).strip())
            continue
        lines.append(f"步骤{index}：对{_target_label(target_table)}执行数据处理操作。")
    return "\n".join(lines).strip()


def _render_key_mapping_summary(
    mappings: list[dict[str, Any]],
    *,
    field_label_map: dict[str, str] | None = None,
) -> str:
    rendered: list[str] = []
    for mapping in mappings:
        if not isinstance(mapping, dict):
            continue
        source_field = str(mapping.get("source_field") or "").strip()
        target_field = str(mapping.get("target_field") or "").strip()
        if source_field and target_field:
            # fold biz_key = biz_key into a human-readable shorthand
            if source_field == "biz_key" and target_field == "biz_key":
                rendered.append("业务主键")
            else:
                rendered.append(
                    f"{format_field_display(source_field, field_label_map)} = "
                    f"{format_field_display(target_field, field_label_map)}"
                )
    return "；".join(rendered[:6])


def _render_compare_columns_summary(
    columns: list[dict[str, Any]],
    *,
    field_label_map: dict[str, str] | None = None,
) -> str:
    rendered: list[str] = []
    for column in columns:
        if not isinstance(column, dict):
            continue
        source_column = str(column.get("source_column") or column.get("column") or "").strip()
        target_column = str(column.get("target_column") or column.get("column") or "").strip()
        tolerance = column.get("tolerance", 0)
        name = str(column.get("name") or "").strip()
        if source_column and target_column:
            source_text = format_field_display(source_column, field_label_map)
            target_text = format_field_display(target_column, field_label_map)
            prefix = f"{name}：" if name else ""
            rendered.append(f"{prefix}{source_text} 对比 {target_text}，容差 {tolerance}")
    return "；".join(rendered[:6])


def render_recon_rule_summary(
    rule_json: dict[str, Any],
    *,
    field_label_map: dict[str, str] | None = None,
) -> str:
    rules = rule_json.get("rules")
    if not isinstance(rules, list) or not rules:
        return ""
    first_rule = rules[0] if isinstance(rules[0], dict) else {}
    recon = first_rule.get("recon") if isinstance(first_rule, dict) else {}
    if not isinstance(recon, dict):
        recon = {}
    key_columns = recon.get("key_columns") if isinstance(recon.get("key_columns"), dict) else {}
    compare_columns = (
        recon.get("compare_columns") if isinstance(recon.get("compare_columns"), dict) else {}
    )
    mapping_summary = _render_key_mapping_summary(
        [item for item in list(key_columns.get("mappings") or []) if isinstance(item, dict)],
        field_label_map=field_label_map,
    )
    compare_summary = _render_compare_columns_summary(
        [item for item in list(compare_columns.get("columns") or []) if isinstance(item, dict)],
        field_label_map=field_label_map,
    )
    parts: list[str] = []
    if mapping_summary:
        parts.append(f"按 {mapping_summary} 匹配")
    if compare_summary:
        parts.append(f"比对 {compare_summary}")
    return "；".join(parts) + "。" if parts else "按左右整理结果执行金额对账。"


def render_recon_draft_text(
    rule_json: dict[str, Any],
    *,
    goal_hint: str = "",
    field_label_map: dict[str, str] | None = None,
) -> str:
    rules = rule_json.get("rules")
    if not isinstance(rules, list) or not rules:
        return ""
    first_rule = rules[0] if isinstance(rules[0], dict) else {}
    recon = first_rule.get("recon") if isinstance(first_rule, dict) else {}
    output = first_rule.get("output") if isinstance(first_rule, dict) else {}
    if not isinstance(recon, dict):
        recon = {}
    if not isinstance(output, dict):
        output = {}
    key_columns = recon.get("key_columns") if isinstance(recon.get("key_columns"), dict) else {}
    compare_columns = (
        recon.get("compare_columns") if isinstance(recon.get("compare_columns"), dict) else {}
    )
    aggregation = recon.get("aggregation") if isinstance(recon.get("aggregation"), dict) else {}

    lines: list[str] = ["数据对账逻辑说明"]
    description = _normalize_goal_text(goal_hint, str(rule_json.get("description") or ""))
    if description:
        lines.append(f"目标：{description}")
    lines.append("输入：左侧整理后数据与右侧整理后数据。")

    mapping_summary = _render_key_mapping_summary(
        [item for item in list(key_columns.get("mappings") or []) if isinstance(item, dict)],
        field_label_map=field_label_map,
    )
    if mapping_summary:
        match_type = str(key_columns.get("match_type") or "exact").strip()
        match_type_display = {"exact": "精确"}.get(match_type, match_type)
        lines.append(f"1. 匹配规则：按 {mapping_summary} 做{match_type_display}匹配。")

    compare_summary = _render_compare_columns_summary(
        [item for item in list(compare_columns.get("columns") or []) if isinstance(item, dict)],
        field_label_map=field_label_map,
    )
    if compare_summary:
        lines.append(f"2. 金额比对：{compare_summary}。")

    if aggregation.get("enabled"):
        group_by = []
        for item in list(aggregation.get("group_by") or []):
            if not isinstance(item, dict):
                continue
            source_field = str(item.get("source_field") or "").strip()
            target_field = str(item.get("target_field") or "").strip()
            if source_field and target_field:
                group_by.append(
                    f"{format_field_display(source_field, field_label_map)}="
                    f"{format_field_display(target_field, field_label_map)}"
                )
        aggregation_items = []
        for item in list(aggregation.get("aggregations") or []):
            if not isinstance(item, dict):
                continue
            function = str(item.get("function") or "").strip()
            source_field = str(item.get("source_field") or item.get("source_column") or "").strip()
            target_field = str(item.get("target_field") or item.get("target_column") or "").strip()
            alias = str(item.get("alias") or "").strip()
            if function and source_field and target_field:
                text = (
                    f"{function}("
                    f"{format_field_display(source_field, field_label_map)}/"
                    f"{format_field_display(target_field, field_label_map)})"
                )
                if alias:
                    text = f"{alias}={text}"
                aggregation_items.append(text)
        detail_parts: list[str] = []
        if group_by:
            detail_parts.append(f"按 {'、'.join(group_by)} 聚合")
        if aggregation_items:
            detail_parts.append(f"聚合字段 {'；'.join(aggregation_items)}")
        lines.append(f"3. 聚合：{'，'.join(detail_parts) or '启用聚合后再对账'}。")
    else:
        lines.append("3. 聚合：不启用聚合，直接逐条匹配并比对金额。")

    sheets = output.get("sheets") if isinstance(output.get("sheets"), dict) else {}
    enabled_outputs = [
        str(item.get("name") or _RECON_OUTPUT_LABELS.get(key) or key).strip()
        for key, item in sheets.items()
        if isinstance(item, dict) and item.get("enabled") is not False
    ]
    if not enabled_outputs:
        enabled_outputs = list(_RECON_OUTPUT_LABELS.values())
    lines.append(f"4. 输出结果：{('、'.join(enabled_outputs))}。")
    return "\n".join(lines).strip()
