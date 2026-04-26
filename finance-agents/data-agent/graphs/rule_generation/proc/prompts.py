"""Prompts for proc rule generation."""

from __future__ import annotations

import json
from typing import Any


PROC_DSL_CONSTRAINTS = """
- 只输出 JSON 对象，不要 markdown，不要解释。
- 顶层必须包含 role_desc、version、metadata、global_config、file_rule_code、dsl_constraints、steps。
- steps 只允许 create_schema 和 write_dataset。
- 每个 step 必须直接写 action，不允许用 type 代替 action。
- 每个 step 必须把 target_table 放在 step 顶层，不允许只放在 schema 或 write_dataset 子对象里。
- create_schema step 的 schema 必须直接包含 columns，不允许嵌套成 schema.schema.columns。
- schema.columns 每列必须用 name 表示字段名，不允许用 field_name 代替 name。
- write_dataset step 的 sources 和 mappings 必须放在 step 顶层，不允许嵌套在 write_dataset 子对象里。
- 如果上下文提供 target_tables，生成的目标表必须只来自 target_tables；如果未提供，可按规则描述自行创建目标表。
- sources[].table 必须使用 source_profiles[].table_name，禁止发明表名。
- 所有 source.field、match.keys.field、lookup_field 必须来自对应 source_profiles[].fields[].raw_name。
- source value 必须写成 {"type":"source","source":{"alias":"...","field":"..."}}，不允许 source 是字符串。
- write_dataset 必须有 row_write_mode，推荐 upsert。
- mappings 必须有 target_field 或 target_field_template。
- value.type 只能使用 source、formula、template_source、function、context、lookup。
- formula 中的 {变量} 必须在 bindings 中定义。
- create_schema.schema.columns 必须包含生成输出字段，字段 data_type 只能是 string/date/decimal。
- source_name 常量必须用 formula，expr 必须是带引号的字符串字面量，例如 "'订单数据'"。
""".strip()


def build_understanding_prompt(context: dict[str, Any]) -> str:
    payload = _context_payload(context)
    if context.get("mode") == "generic_proc":
        return (
            "你是 Tally 财务 AI 的通用数据整理规则理解器。\n"
            "你只负责理解规则并输出结构化 JSON，不生成 proc DSL。\n"
            "不要把规则强行理解成对账场景；目标表、字段、步骤都以用户描述和 proc_json_examples 为准。\n"
            "只有会直接改变结果且无法从描述、字段结构、样例数据、示例 JSON 推断的业务口径，才放入 ambiguities。\n"
            "返回 JSON 字段固定为：understanding、assumptions、ambiguities。\n"
            "ambiguities 每项包含 id/category/impact/resolved/confidence/candidates/evidence。\n\n"
            f"输入上下文：\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )
    return (
        "你是 Tally 财务 AI 的数据整理规则理解器。\n"
        "你只负责理解规则并输出结构化 JSON，不生成 proc DSL。\n"
        "请抽取用户明确声明的字段意图，但不要替用户静默改写成更具体字段。\n"
        "understanding.field_intents 用于列出字段引用，每项包含 role/mention/operation/operator/value/candidate_fields。\n"
        "role 只允许 match_key、compare_field、time_field、filter_field、group_field、output_field。\n"
        "如果用户写的是订单号、订单时间这类泛化字段名，请按原文放入 mention，不要改写为更具体字段。\n"
        "candidate_fields 用于给出该 mention 可能对应的数据集字段，候选必须来自 source_profiles[].fields[].raw_name。\n"
        "candidate_fields 每项包含 raw_name/display_name/source_table/reason；没有可信候选时返回空数组。\n"
        "candidate_fields 只用于聚焦用户确认范围，不代表已自动确认字段。\n"
        "只有会直接改变财务结果且无法推断的业务口径，才放入 ambiguities。\n"
        "返回 JSON 字段固定为：understanding、assumptions、ambiguities。\n"
        "ambiguities 每项包含 id/category/impact/resolved/confidence/candidates/evidence。\n\n"
        f"输入上下文：\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def build_proc_generation_prompt(context: dict[str, Any]) -> str:
    payload = _context_payload(context)
    if context.get("mode") == "generic_proc":
        return (
            "你是 Tally 财务 AI 的通用 proc JSON 生成器。\n"
            "请根据用户规则描述、数据集字段/样例和 proc_json_examples，生成完整 proc steps DSL JSON。\n"
            "不要强行生成 left_recon_ready/right_recon_ready；目标表按规则描述和 target_tables 决定。\n"
            "所有 source.field 必须来自 source_profiles.fields[].raw_name，禁止发明输入字段。\n"
            "不要输出 markdown 或解释。\n\n"
            f"DSL 约束：\n{PROC_DSL_CONSTRAINTS}\n\n"
            f"输入上下文：\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )
    return (
        "你是 Tally 财务 AI 的 proc JSON 生成器。\n"
        "请根据已确认的 understanding/assumptions/field_bindings 生成当前 side 的完整 proc steps DSL JSON。\n"
        "字段必须使用 field_bindings 中 status=bound 的 selected_field.name；不要自行猜测未绑定字段。\n"
        "不要生成另一侧目标表。不要输出 markdown 或解释。\n\n"
        f"DSL 约束：\n{PROC_DSL_CONSTRAINTS}\n\n"
        f"输入上下文：\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def build_proc_repair_prompt(context: dict[str, Any], *, failures: list[dict[str, Any]]) -> str:
    payload = _context_payload(context)
    repair_payload = {
        "context": payload,
        "current_proc_rule_json": context.get("normalized_rule_json") or context.get("proc_rule_json") or {},
        "failures": failures,
    }
    return (
        "你是 Tally 财务 AI 的 proc JSON 修复器。\n"
        "只能修复 JSON 实现错误，不要改变已确认的业务口径。\n"
        "请根据 failures 修复 current_proc_rule_json，并返回完整 proc JSON 对象。\n"
        "不要输出 markdown 或解释。\n\n"
        f"DSL 约束：\n{PROC_DSL_CONSTRAINTS}\n\n"
        f"修复输入：\n{json.dumps(repair_payload, ensure_ascii=False, indent=2)}"
    )


def _context_payload(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "side": context.get("side"),
        "target_table": context.get("target_table"),
        "target_tables": context.get("target_tables") or [],
        "rule_text": context.get("rule_text"),
        "source_profiles": [_source_profile_payload(source) for source in context.get("sources", [])],
        "proc_json_examples": context.get("proc_json_examples") or [],
        "understanding": context.get("understanding") or {},
        "field_intents": context.get("field_intents") or [],
        "field_bindings": _field_bindings_payload(context.get("field_bindings") or []),
        "assumptions": context.get("assumptions") or [],
        "ambiguities": context.get("ambiguities") or [],
    }


def _field_bindings_payload(bindings: list[Any]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for item in bindings:
        if not isinstance(item, dict):
            continue
        selected_field = item.get("selected_field") if isinstance(item.get("selected_field"), dict) else {}
        payload.append({
            "intent_id": item.get("intent_id"),
            "role": item.get("role"),
            "mention": item.get("mention"),
            "operation": item.get("operation"),
            "operator": item.get("operator"),
            "value": item.get("value"),
            "status": item.get("status"),
            "selected_field": {
                "name": selected_field.get("name"),
                "display_name": selected_field.get("label") or selected_field.get("display_name"),
                "source_table": selected_field.get("table_name") or selected_field.get("source_table"),
            } if selected_field else None,
        })
    return payload


def _source_profile_payload(source: dict[str, Any]) -> dict[str, Any]:
    field_label_map = source.get("field_label_map") if isinstance(source.get("field_label_map"), dict) else {}
    sample_rows = [row for row in list(source.get("sample_rows") or []) if isinstance(row, dict)][:5]
    fields = []
    seen = set()
    for field in list(source.get("fields") or []):
        if not isinstance(field, dict):
            continue
        raw_name = str(field.get("name") or field.get("raw_name") or field.get("field_name") or "").strip()
        if not raw_name or raw_name in seen:
            continue
        seen.add(raw_name)
        fields.append({
            "raw_name": raw_name,
            "display_name": str(field.get("label") or field_label_map.get(raw_name) or raw_name),
            "data_type": str(field.get("data_type") or field.get("schema_type") or "string"),
        })
    for row in sample_rows:
        for key in row.keys():
            raw_name = str(key).strip()
            if raw_name and raw_name not in seen:
                seen.add(raw_name)
                fields.append({
                    "raw_name": raw_name,
                    "display_name": str(field_label_map.get(raw_name) or raw_name),
                    "data_type": "string",
                })
    return {
        "table_name": str(source.get("table_name") or source.get("resource_key") or source.get("dataset_id") or source.get("id") or ""),
        "dataset_name": str(source.get("dataset_name") or source.get("business_name") or source.get("name") or ""),
        "business_name": str(source.get("business_name") or source.get("dataset_name") or source.get("name") or ""),
        "fields": fields,
        "sample_rows": sample_rows,
    }
