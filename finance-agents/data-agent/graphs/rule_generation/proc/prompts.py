"""Prompts for proc rule generation."""

from __future__ import annotations

import json
from typing import Any


SOURCE_PROFILE_SAMPLE_ROW_LIMIT = 20


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
- formula 必须写成 {"type":"formula","expr":"...","bindings":{...}}，expr 必须是字符串，不能再嵌套一层对象。
- formula 只用于逐行计算，内联函数只支持 coalesce/is_null；禁止在 formula 中写 sum/min/avg/count 等聚合函数。
- 行过滤必须使用 write_dataset.step.filter，格式为 {"type":"formula","expr":"...","bindings":{...}}，不要输出 filters 数组。
- 逐行运行时函数必须用 value.type=function，function 只支持 current_date/add_months/month_of/fraction_numerator/earliest_date/to_decimal。
- 禁止输出 match.keys 或 match.type；当前执行器不支持这种 match 写法。
- match 只支持 match.sources，格式为 {"sources":[{"alias":"...","keys":[{"field":"源字段","target_field":"目标字段"}]}]}。
- 多源关联派生字段优先使用单一基础 alias，并用 lookup 从非基础 alias 读取字段。
- 无 match.sources 的 write_dataset 只能有一个基础 alias；不要在 formula bindings 中直接 source 引用非基础 alias。
- lookup 必须写成 {"type":"lookup","source_alias":"...","value_field":"...","keys":[{"lookup_field":"...","input":{"type":"source","source":{"alias":"基础alias","field":"基础字段"}}}]}。
- 聚合必须使用 write_dataset.step.aggregate，格式为 [{"source_alias":"基础alias","output_alias":"聚合alias","group_fields":["分组源字段"],"aggregations":[{"field":"被聚合源字段","operator":"sum|min","alias":"agg_输出字段"}]}]。
- 聚合结果必须通过 match.sources 读取聚合 alias，例如 {"alias":"聚合alias","keys":[{"field":"分组源字段","target_field":"目标分组字段"}]}，再在 mappings 中从聚合 alias 取 group_fields 或 agg_* 字段。
- reference_filter 用于按参考表过滤基础数据，格式为 {"source_alias":"...","reference_table":"...","keys":[{"source_field":"...","reference_field":"..."}]}。
- dynamic_mappings 用于循环上下文字段映射，必须同时配置 match.sources；target_field_template/template_source/context 只用于此类模板化场景。
- create_schema.schema.columns 必须包含生成输出字段，字段 data_type 只能是 string/date/decimal。
- source_name 常量必须用 formula，expr 必须是带引号的字符串字面量，例如 "'订单数据'"。
""".strip()


def build_understanding_prompt(context: dict[str, Any]) -> str:
    payload = _context_payload(context)
    return (
        "你是 Tally 财务 AI 的通用数据整理规则理解器。\n"
        "你只负责理解规则并输出结构化 JSON，不生成 proc DSL。\n"
        "不要把规则强行理解成对账场景；目标表、字段、步骤都以用户描述和 proc_json_examples 为准。\n"
        "返回 JSON 字段固定为：understanding、assumptions、ambiguities。\n"
        "understanding 必须包含：rule_summary、output_mode、source_references、output_specs、business_rules。\n"
        "output_mode 只允许 explicit、source_passthrough、unspecified。\n"
        "如果用户只描述过滤、排序、去重、保留哪些行，没有定义输出列，则 output_mode=source_passthrough，output_specs 留空，表示输出保留源表字段。\n"
        "如果用户定义了输出字段、派生字段、聚合字段、重命名字段，则 output_mode=explicit，并在 output_specs 中逐项声明。\n"
        "source_passthrough 只表示结果保留整行/全部源字段；如果 source_references 中存在用户希望进入结果的字段语义，必须改为 output_mode=explicit 并创建 output_specs。\n"
        "source_references 只放必须绑定到源数据集字段的引用，每项包含 ref_id/semantic_name/usage/must_bind/table_scope/candidate_fields/description/operator/value。\n"
        "usage 只允许 match_key、compare_field、time_field、filter_field、group_field、lookup_key、source_value。\n"
        "source_references.semantic_name 必须只保留字段语义短语，不要把整句过滤、公式、条件表达式放进来。\n"
        "source_references.table_scope 只能填写 source_profiles 中明确存在的 table_name、dataset_name 或 business_name；不要把字段名、公式、关联句子、过滤句子放进 table_scope。\n"
        "如果用户写的是订单号、订单时间这类泛化字段名，请按原文放入 semantic_name，不要改写为更具体字段。\n"
        "output_specs 只放目标输出列定义，每项包含 output_id/name/kind/source_ref_ids/rule_ids/expression/expression_hint/description。\n"
        "当用户写“A=...”或“A为...”时，A 是目标输出字段名，必须放入 output_specs.name；只有等号/为后面的真实来源字段才放入 source_references。\n"
        "如果 A 是派生输出名，即使它看起来像匹配字段、金额字段或时间字段，也不要把 A 放进 source_references。\n"
        "output_specs.kind 只允许 passthrough、rename、formula、aggregate、lookup、join_derived、constant、unknown。\n"
        "当输出列是公式、常量、聚合、函数计算或条件计算时，优先输出 expression，不要只写 expression_hint。\n"
        "expression 使用结构化 IR：ref/constant/add/subtract/multiply/divide/concat/function/conditional。\n"
        "示例1：订单金额+10 => {\"op\":\"add\",\"operands\":[{\"op\":\"ref\",\"ref_id\":\"...\"},{\"op\":\"constant\",\"value\":10}]}\n"
        "示例2：当前日期 => {\"op\":\"function\",\"name\":\"current_date\",\"args\":[]}\n"
        "示例3：如果 A>0 则 A 否则 0 => {\"op\":\"conditional\",\"when\":{predicate},\"then\":{expression},\"else\":{expression}}\n"
        "派生输出字段、聚合字段、公式字段不要求存在于 source_profiles 里，不要把它们塞进 source_references。\n"
        "business_rules 只放过滤、关联、聚合、推导、校验等规则，每项包含 rule_id/type/description/related_ref_ids/output_ids/predicate/params。\n"
        "凡是 join/aggregate/derive/filter 会影响某个输出字段，必须用 business_rules.output_ids 指向 output_specs.output_id，或用 output_specs.rule_ids 指向 business_rules.rule_id。\n"
        "聚合语义必须拆成 output_specs.kind=aggregate + business_rules.type=aggregate；不要把 sum/min 写入 expression.function。\n"
        "aggregate.params 必须包含 operator、value_ref_id、group_ref_ids；operator 只允许 sum/min。\n"
        "示例6：按客户订单号汇总销售金额 => output_specs 中金额 kind=aggregate/rule_ids=[rule_agg]；business_rules 中 params={\"operator\":\"sum\",\"value_ref_id\":\"销售金额ref\",\"group_ref_ids\":[\"客户订单号ref\"]}。\n"
        "当规则包含筛选条件、区间条件、枚举条件、逻辑组合条件时，优先输出 predicate，不要只写 description。\n"
        "predicate 使用结构化 IR：eq/neq/gt/gte/lt/lte/in/contains/and/or/not/exists。\n"
        "示例4：买家信息只取 buyer_1 => {\"op\":\"eq\",\"left\":{\"op\":\"ref\",\"ref_id\":\"...\"},\"right\":{\"op\":\"constant\",\"value\":\"buyer_1\"}}\n"
        "示例5：A=1 且 B>0 => {\"op\":\"and\",\"operands\":[{predicate1},{predicate2}]}\n"
        "订单号、流水号、会员号等长数字标识符必须作为字符串 constant 输出，禁止作为 JSON number 输出，避免尾数精度丢失。\n"
        "candidate_fields 用于给出 semantic_name 可能对应的数据集字段，候选必须来自 source_profiles[].fields[].raw_name。\n"
        "candidate_fields 每项包含 raw_name/display_name/source_table/reason；没有可信候选时返回空数组。\n"
        "candidate_fields 只用于聚焦用户确认范围，不代表已自动确认字段。\n"
        "只有会直接改变财务结果且无法推断的业务口径，才放入 ambiguities。\n"
        "ambiguities 每项包含 id/category/impact/resolved/confidence/candidates/evidence。\n\n"
        f"输入上下文：\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def build_ir_repair_prompt(context: dict[str, Any], *, failures: list[dict[str, Any]]) -> str:
    repair_stage = str(context.get("current_repair_stage") or "").strip() or _infer_repair_stage(context)
    repair_failures = failures or [
        item
        for item in list(context.get("current_repair_failures") or [])
        if isinstance(item, dict)
    ]
    repair_payload = {
        "context": _context_payload(context),
        "current_understanding": context.get("understanding") or {},
        "current_proc_rule_json": context.get("normalized_rule_json") or context.get("proc_rule_json") or {},
        "repair_stage": repair_stage,
        "repair_failures": repair_failures,
        "required_repairs": _required_repairs_payload(repair_failures),
        "validation_results": _validation_results_payload(context),
        "repair_history": [
            item
            for item in list(context.get("repair_history") or [])
            if isinstance(item, dict)
        ][-6:],
    }
    return (
        "你是 Tally 财务 AI 的规则 IR 修复器。\n"
        "你只修复 understanding 里的 IR 完整性和引用一致性，不生成 proc DSL。\n"
        "修复目标：让 source_references、output_specs、business_rules 足以稳定翻译成 proc DSL。\n"
        "请综合用户原始描述、当前 IR、当前 proc JSON、数据集字段、resolved_source_bindings、repair_failures、validation_results 和 repair_history 自行判断如何修复。\n"
        "必须遵守：\n"
        "- 不改变用户已经明确的业务口径。\n"
        "- 必须返回完整 understanding，不要只返回局部 patch。\n"
        "- 如果 repair_history 显示上一轮 changed_understanding=false 或同一 failure 重复出现，必须改变修复策略，不要重复输出相同 IR。\n"
        "- repair_failures 只是错误事实；required_repairs 是必须逐项处理的修复任务。\n"
        "- 如果 required_repairs 非空，禁止原样返回 current_understanding；每一项必须落实到 source_references、output_specs、business_rules、expression 或 predicate，除非确实需要用户确认并写入 ambiguities。\n"
        "- output_mode=source_passthrough 表示过滤/排序/去重后保留源表字段；此时不要为了源表字段逐个生成 output_specs。\n"
        "- output_mode=explicit 表示用户明确声明输出字段；此时必须用 output_specs 描述输出列。\n"
        "- 如果 repair_failures.reason=source_passthrough_has_unprojected_source_refs，说明当前 IR 已抽出应进入结果语义的源字段，却仍声明全字段透传；请改成 output_mode=explicit，并把这些 source_references 建成 output_specs。\n"
        "- 不把输出字段别名当作源数据字段。\n"
        "- 派生输出字段不要求存在于 source_profiles；它们应放在 output_specs.name。\n"
        "- source_references 只放真实源字段引用；字段候选必须来自 source_profiles[].fields[].raw_name。\n"
        "- 如果 repair_failures.reason=invalid_table_scope，说明 table_scope 被写成了字段名/长句/不存在的数据集名；请只把 table_scope 修成 source_profiles 里存在的 table_name、dataset_name 或 business_name，或在用户未限定来源时置为空数组。\n"
        "- 如果 repair_failures.reason=ir_lineage_missing_for_output，说明当前 proc JSON 的某个输出字段引用了真实源字段，但 IR lineage 没声明完整。\n"
        "- 遇到 ir_lineage_missing_for_output 时，请读取 repair_failures.target_field、missing_source_references、unexpected_sources 和 current_proc_rule_json 中对应 mapping，判断这些字段在用户描述中承担的作用。\n"
        "- 如果 repair_failures.reason=rule_text_field_mentions_missing_ir_refs，说明用户原始描述中显式提到了数据集字段，但当前 IR 没有建模；必须读取 repair_failures.missing_source_fields 或 required_repairs，把这些字段逐个补进 source_references，并判断它们属于过滤、关联、聚合、取数、公式还是输出 lineage。\n"
        "- 如果 repair_failures.reason=cross_table_outputs_missing_relation_rule 或 output_spec_cross_table_lineage_missing_rule，说明 IR 的输出引用已经跨多个数据集，但没有声明行级关系；请根据用户描述补 business_rules.type=join/lookup/aggregate/derive，并用 related_ref_ids、output_ids、output_specs.rule_ids 把关联键、取数字段和受影响输出连起来。\n"
        "- 如果 repair_failures.reason=output_spec_missing_lookup_value_ref，说明关联/查找输出只有关联键、缺少最终取数字段；请从用户原始描述中找出“取出/获取/得到”的字段，补进 source_references，并挂到对应 output_specs.source_ref_ids 与 join business_rule.related_ref_ids。\n"
        "- 如果这些字段是该输出计算/关联/查找/聚合/过滤的必要来源，请把它们补进 source_references，并挂到对应 output_specs.source_ref_ids、output_specs.rule_ids 或 business_rules.related_ref_ids/output_ids。\n"
        "- 如果字段来自关联/查找关系，请用 business_rules.type=join 描述关联，并把关联键、取数字段都放入 related_ref_ids，同时用 output_ids 指向受影响输出。\n"
        "- output_specs.source_ref_ids、business_rules.related_ref_ids、expression.ref_id、predicate.ref_id 必须引用已存在的 source_references.ref_id。\n"
        "- output_specs.rule_ids 必须引用已存在的 business_rules.rule_id；business_rules.output_ids 必须引用已存在的 output_specs.output_id。\n"
        "- formula/constant 输出必须补齐结构化 expression。\n"
        "- filter 规则必须补齐结构化 predicate；如果用户没有过滤规则，不要输出 filter 规则。\n"
        "- aggregate 规则必须补齐 params.operator/value_ref_id/group_ref_ids；operator 只能是 sum/min。\n"
        "- join/lookup/aggregate/derive/filter 必须补齐足够 lineage：关联键、分组字段、聚合字段、取数字段、输出字段定义要分层清楚，并绑定到受影响 output。\n"
        "- 如果确实存在会改变财务结果且无法推断的业务歧义，放入 ambiguities；不要用猜测修复。\n"
        "结构化 expression 只允许 ref/constant/add/subtract/multiply/divide/concat/function/conditional。\n"
        "结构化 predicate 只允许 eq/neq/gt/gte/lt/lte/in/contains/and/or/not/exists。\n"
        "返回 JSON 字段固定为：understanding、assumptions、ambiguities。\n\n"
        f"修复输入：\n{json.dumps(repair_payload, ensure_ascii=False, indent=2)}"
    )


def _infer_repair_stage(context: dict[str, Any]) -> str:
    ir_lint = context.get("ir_lint_result")
    if isinstance(ir_lint, dict) and ir_lint.get("source_stage"):
        return str(ir_lint.get("source_stage") or "")
    for stage, key in (
        ("diagnose_sample", "sample_diagnosis_result"),
        ("run_sample", "sample_result"),
        ("assert_output", "assert_result"),
        ("check_ir_dsl_consistency", "ir_dsl_consistency_result"),
        ("lint_proc_json", "lint_result"),
        ("lint_ir", "ir_lint_result"),
    ):
        result = context.get(key)
        if isinstance(result, dict) and result.get("success") is False:
            return stage
    return "unknown"


def _validation_results_payload(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "ir_structure_repair_reasons": _compact_list(context.get("ir_structure_repair_reasons")),
        "ir_lint_result": _compact_result(context.get("ir_lint_result")),
        "lint_proc_json_result": _compact_result(context.get("lint_result")),
        "ir_dsl_consistency_result": _compact_result(context.get("ir_dsl_consistency_result")),
        "sample_result": _compact_sample_result(context.get("sample_result")),
        "sample_diagnosis_result": _compact_result(context.get("sample_diagnosis_result")),
        "assert_result": _compact_result(context.get("assert_result")),
        "current_errors": _compact_list(context.get("errors")),
    }


def _required_repairs_payload(failures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    repairs: list[dict[str, Any]] = []
    seen_missing_fields: set[tuple[str, str]] = set()
    for failure in failures:
        if not isinstance(failure, dict):
            continue
        reason = str(failure.get("reason") or "").strip()
        if reason == "rule_text_field_mentions_missing_ir_refs":
            for field in list(failure.get("missing_source_fields") or []):
                if not isinstance(field, dict):
                    continue
                table_name = str(field.get("table_name") or "").strip()
                raw_name = str(field.get("name") or field.get("raw_name") or "").strip()
                if not table_name or not raw_name:
                    continue
                key = (table_name, raw_name)
                if key in seen_missing_fields:
                    continue
                seen_missing_fields.add(key)
                display_name = str(field.get("label") or field.get("display_name") or raw_name).strip()
                repairs.append({
                    "type": "add_missing_source_field_to_ir",
                    "reason": reason,
                    "table_name": table_name,
                    "raw_name": raw_name,
                    "display_name": display_name,
                    "instruction": (
                        "Add this source field as a source_reference, bind it to the relevant "
                        "output_spec/business_rule/expression/predicate according to the original rule text, "
                        "or create an ambiguity if the role cannot be inferred."
                    ),
                })
        elif reason == "output_spec_missing_lookup_value_ref":
            repairs.append({
                "type": "add_lookup_value_lineage",
                "reason": reason,
                "output_id": failure.get("output_id"),
                "instruction": (
                    "Find the field being retrieved by the lookup/join from the original rule text, "
                    "add it to source_references, and attach it to the lookup output lineage."
                ),
            })
        elif reason == "source_passthrough_has_unprojected_source_refs":
            repairs.append({
                "type": "convert_passthrough_to_explicit_outputs",
                "reason": reason,
                "unprojected_source_refs": failure.get("unprojected_source_refs") or [],
                "instruction": (
                    "The IR already contains source references that carry result semantics. "
                    "Change output_mode to explicit and create output_specs for those refs, "
                    "while keeping operational-only refs such as filters in business_rules."
                ),
            })
        elif reason == "business_rule_missing_filter_predicate":
            repairs.append({
                "type": "complete_filter_predicate",
                "reason": reason,
                "rule_id": failure.get("rule_id"),
                "instruction": (
                    "The IR has a filter business_rule with only natural-language description. "
                    "Read the original rule text and the rule description, identify the referenced "
                    "source field and condition, then add a structured predicate that references an "
                    "existing source_references.ref_id. For non-empty / non-null filters, use "
                    "exists with a ref operand. If the referenced field is missing from "
                    "source_references, add it first and bind it to the predicate."
                ),
            })
    return repairs


def _compact_result(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    compact: dict[str, Any] = {}
    for key in ("success", "status", "source_stage", "message", "error", "summary"):
        if key in value:
            compact[key] = value.get(key)
    errors = _compact_list(value.get("errors"))
    diagnostics = _compact_list(value.get("diagnostics"))
    if errors:
        compact["errors"] = errors
    if diagnostics:
        compact["diagnostics"] = diagnostics
    return compact


def _compact_sample_result(value: Any) -> dict[str, Any]:
    compact = _compact_result(value)
    if not isinstance(value, dict):
        return compact
    for key in ("ready_for_confirm", "backend", "warnings"):
        if key in value:
            compact[key] = value.get(key)
    output_samples = [
        {
            "target_table": item.get("target_table"),
            "row_count": len([row for row in list(item.get("rows") or []) if isinstance(row, dict)]),
        }
        for item in list(value.get("output_samples") or [])
        if isinstance(item, dict)
    ]
    if output_samples:
        compact["output_samples"] = output_samples[:6]
    return compact


def _compact_list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    compacted: list[Any] = []
    for item in value[:12]:
        if isinstance(item, dict):
            compacted.append({
                key: item.get(key)
                for key in (
                    "stage",
                    "reason",
                    "type",
                    "message",
                    "step_id",
                    "target_field",
                    "output_id",
                    "rule_id",
                    "ref_id",
                    "missing_source_fields",
                    "missing_source_references",
                    "unprojected_source_refs",
                    "unexpected_sources",
                )
                if key in item
            })
        else:
            compacted.append(item)
    return compacted


def _context_payload(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "side": context.get("side"),
        "target_table": context.get("target_table"),
        "target_tables": context.get("target_tables") or [],
        "rule_text": context.get("rule_text"),
        "source_profiles": [_source_profile_payload(source) for source in context.get("sources", [])],
        "proc_json_examples": context.get("proc_json_examples") or [],
        "understanding": context.get("understanding") or {},
        "output_mode": (context.get("understanding") or {}).get("output_mode") or "unspecified",
        "source_references": (context.get("understanding") or {}).get("source_references") or [],
        "output_specs": (context.get("understanding") or {}).get("output_specs") or [],
        "business_rules": (context.get("understanding") or {}).get("business_rules") or [],
        "resolved_source_bindings": _field_bindings_payload(context.get("field_bindings") or []),
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
            "usage": item.get("usage"),
            "mention": item.get("mention"),
            "description": item.get("description"),
            "operator": item.get("operator"),
            "value": item.get("value"),
            "must_bind": item.get("must_bind"),
            "table_scope": item.get("table_scope") or [],
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
    sample_rows = [
        row
        for row in list(source.get("sample_rows") or [])
        if isinstance(row, dict)
    ][:SOURCE_PROFILE_SAMPLE_ROW_LIMIT]
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
