"""Design-session executor abstraction.

LLM-first implementation with deterministic JSON parsing and fallback drafts.
"""

from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from config import PROJECT_ROOT
from models import SchemeDesignSession
from skills.deep_agent_runner import DeepAgentSkillRunner, SkillGenerationResult, get_skill_runner
from utils.llm import get_llm

from .rule_text_renderer import render_proc_draft_text, render_recon_draft_text
from .semantic_utils import ensure_dataset_semantic_context
from .single_shot_generator import SingleShotGenerationResult, SingleShotRuleGenerator

_DEFAULT_RECON_OUTPUT_SHEETS = {
    "summary": "核对汇总",
    "source_only": "左侧独有",
    "target_only": "右侧独有",
    "matched_with_diff": "差异记录",
}

_DEFAULT_PROC_DSL_CONSTRAINTS = {
    "actions": ["create_schema", "write_dataset"],
    "builtin_functions": ["earliest_date", "current_date", "month_of"],
    "aggregate_operators": ["sum", "min"],
    "field_write_modes": ["overwrite", "increment"],
    "row_write_modes": ["insert_if_missing", "update_only", "upsert"],
    "column_data_types": ["string", "date", "decimal"],
    "value_node_types": ["source", "formula", "template_source", "function", "context"],
    "merge_strategies": ["union_distinct"],
    "loop_context_vars": ["month", "prev_month", "is_first_month"],
}

_PROC_STANDARD_COLUMN_ORDER = ("biz_key", "amount", "biz_date", "source_name")
_PROC_STANDARD_COLUMN_DEFS = {
    "biz_key": {"name": "biz_key", "data_type": "string", "nullable": False},
    "amount": {
        "name": "amount",
        "data_type": "decimal",
        "precision": 18,
        "scale": 2,
        "default": 0,
    },
    "biz_date": {"name": "biz_date", "data_type": "date", "nullable": True},
    "source_name": {"name": "source_name", "data_type": "string", "nullable": True},
}


@dataclass(slots=True)
class SchemeDesignExecutorResult:
    assistant_message: str
    loaded_skills: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    proc_draft_json: dict[str, Any] | None = None
    recon_draft_json: dict[str, Any] | None = None
    proc_draft_text: str | None = None
    recon_draft_text: str | None = None
    proc_generation_meta: dict[str, Any] | None = None
    recon_generation_meta: dict[str, Any] | None = None
    proc_trial_result: dict[str, Any] | None = None
    recon_trial_result: dict[str, Any] | None = None
    pending_interrupt: dict[str, Any] | None = None


class SchemeDesignExecutor(Protocol):
    """Adapter interface for design session turns."""

    name: str

    async def run_turn(
        self,
        *,
        session: SchemeDesignSession,
        user_message: str,
        is_resume: bool = False,
    ) -> SchemeDesignExecutorResult: ...


class FallbackSchemeDesignExecutor:
    """LLM-first executor with deterministic fallback."""

    name = "llm-with-fallback"

    async def run_turn(
        self,
        *,
        session: SchemeDesignSession,
        user_message: str,
        is_resume: bool = False,
    ) -> SchemeDesignExecutorResult:
        text = (user_message or "").strip()
        normalized = text.lower()
        focus = self._infer_focus(text, normalized)
        should_build_proc = focus in {"proc", "both"} and (
            focus == "proc" or not session.drafts.proc_draft_json
        )
        should_build_recon = focus in {"recon", "both"} and (
            focus == "recon" or not session.drafts.recon_draft_json
        )

        proc_draft: dict[str, Any] | None = None
        recon_draft: dict[str, Any] | None = None
        llm_errors: list[str] = []

        if should_build_proc:
            try:
                proc_draft = await self._generate_proc_draft(session, text)
            except Exception as exc:
                llm_errors.append(f"proc 生成失败：{exc}")
                proc_draft = self._build_proc_draft(session)

        if should_build_recon:
            try:
                recon_draft = await self._generate_recon_draft(session, text)
            except Exception as exc:
                llm_errors.append(f"recon 生成失败：{exc}")
                recon_draft = self._build_recon_draft(session)

        open_questions = self._build_open_questions(session)
        phase = "恢复会话" if is_resume else "处理消息"
        if llm_errors:
            assistant_message = (
                f"[{phase}] 已尝试使用 LLM 生成配置，但存在回退："
                + "；".join(llm_errors)
                + "。当前已返回可继续编辑的 JSON 草稿。"
            )
        else:
            assistant_message = (
                f"[{phase}] 已根据对账目标、数据集描述和数据结构生成最新草稿。"
                " 你可以直接继续试跑验证或补充约束后重新生成。"
            )

        return SchemeDesignExecutorResult(
            assistant_message=assistant_message,
            loaded_skills=["proc-config", "recon-config"],
            open_questions=open_questions,
            proc_draft_json=proc_draft,
            recon_draft_json=recon_draft,
            proc_draft_text=self._safe_proc_summary(proc_draft),
            recon_draft_text=self._safe_recon_summary(recon_draft),
            pending_interrupt={
                "type": "design_review",
                "message": "请确认当前草稿方向，或继续补充约束。",
            },
        )

    def _infer_focus(self, text: str, normalized: str) -> str:
        compact = re.sub(r"\s+", "", normalized)
        if any(keyword in compact for keyword in ("只生成proc", "仅生成proc", "生成proc", "proconly")):
            return "proc"
        if any(keyword in compact for keyword in ("只生成recon", "仅生成recon", "生成recon", "recononly")):
            return "recon"
        if any(keyword in normalized for keyword in ("proc only", "generate proc")):
            return "proc"
        if any(keyword in normalized for keyword in ("recon only", "generate recon")):
            return "recon"
        if "整理" in text and "对账" not in text:
            return "proc"
        if "对账" in text or "核对" in text:
            return "recon"
        return "both"

    async def _generate_proc_draft(self, session: SchemeDesignSession, user_message: str) -> dict[str, Any]:
        prompt = self._build_proc_prompt(session, user_message)
        content = await self._invoke_llm(prompt)
        parsed = self._parse_json_content(content)
        parsed = self._unwrap_rule_payload(parsed, ("proc_rule_json", "proc", "rule"))
        if not isinstance(parsed, dict) or not isinstance(parsed.get("steps"), list):
            raise ValueError("LLM 返回的 proc 草稿不是合法对象")
        parsed = self._prepare_proc_draft_for_validation(session, parsed)
        return self._normalize_proc_draft(parsed)

    async def _generate_recon_draft(self, session: SchemeDesignSession, user_message: str) -> dict[str, Any]:
        prompt = self._build_recon_prompt(session, user_message)
        content = await self._invoke_llm(prompt)
        parsed = self._parse_json_content(content)
        parsed = self._unwrap_rule_payload(parsed, ("recon_rule_json", "recon", "rule"))
        rules = parsed.get("rules") if isinstance(parsed, dict) else None
        if not isinstance(parsed, dict) or not isinstance(rules, list) or not rules:
            raise ValueError("LLM 返回的 recon 草稿不是合法对象")
        return self._normalize_recon_draft(parsed)

    async def _invoke_llm(self, prompt: str) -> str:
        llm = get_llm(temperature=0.1)
        response = await asyncio.wait_for(
            asyncio.to_thread(llm.invoke, prompt),
            timeout=90,
        )
        content = getattr(response, "content", "")
        if isinstance(content, list):
            content = "".join(str(getattr(item, "text", item)) for item in content)
        text = str(content or "").strip()
        if not text:
            raise ValueError("LLM 未返回有效内容")
        return text

    def _parse_json_content(self, content: str) -> dict[str, Any]:
        stripped = self._strip_markdown_fence(content)
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            parsed = self._decode_first_json_object(stripped)
        if not isinstance(parsed, dict):
            raise ValueError("返回内容不是 JSON 对象")
        return parsed

    def _strip_markdown_fence(self, content: str) -> str:
        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        return text.strip()

    def _decode_first_json_object(self, text: str) -> dict[str, Any]:
        decoder = json.JSONDecoder()
        # 优先从文本中的每个 `{` 起点尝试 raw_decode，避免贪婪正则误匹配。
        for start in [idx for idx, ch in enumerate(text) if ch == "{"]:
            try:
                value, _ = decoder.raw_decode(text[start:])
                if isinstance(value, dict):
                    return value
            except Exception:
                continue
        raise ValueError("LLM 返回内容中未找到可解析的 JSON 对象")

    def _unwrap_rule_payload(
        self,
        parsed: dict[str, Any],
        candidate_keys: tuple[str, ...],
    ) -> dict[str, Any]:
        for key in candidate_keys:
            nested = parsed.get(key)
            if isinstance(nested, dict):
                return nested
        return parsed

    def _build_proc_prompt(self, session: SchemeDesignSession, user_message: str) -> str:
        return (
            "你是 Tally 财务 AI 的数据整理规则生成器。"
            "请只输出一个合法 JSON 对象，不要输出解释，不要使用 markdown。"
            "目标 JSON 必须兼容当前 proc steps DSL。"
            "要求：\n"
            "1. 顶层包含 role_desc/version/metadata/global_config/file_rule_code/dsl_constraints/steps。\n"
            "2. 必须输出 left_recon_ready 和 right_recon_ready 两份整理后数据。\n"
            "3. steps 只使用 create_schema 与 write_dataset。\n"
            "4. 输出字段至少包含 biz_key、amount、biz_date、source_name。\n"
            "5. 多数据源时使用 sources/match/mappings 组织，不要发明新字段。\n"
            "6. 每个 step 都必须有唯一 step_id；write_dataset 需要 row_write_mode。\n"
            "7. create_schema 的 schema.columns 必须是数组，列对象仅使用 name/data_type/nullable/default/precision/scale。\n"
            "8. mappings 仅使用 target_field 或 target_field_template，value.type 仅使用 source/formula/template_source/function/context/lookup。\n"
            "9. 需要的 DSL 节点只允许使用 schema.columns/schema.primary_key/sources/match/aggregate/filter/reference_filter/mappings/dynamic_mappings/depends_on。\n"
            "10. target_table 必须明确，供后续 recon 绑定；不要输出 proc_rule_json 外层包裹。\n\n"
            f"方案名称：{session.scheme_name or '未命名方案'}\n"
            f"业务目标：{session.biz_goal or '未提供'}\n"
            f"数据源描述：{session.source_description or '未提供'}\n"
            f"用户补充：{user_message or '无'}\n"
            f"样本数据集：\n{self._summarize_dataset_inputs(session)}\n"
        )

    def _build_recon_prompt(self, session: SchemeDesignSession, user_message: str) -> str:
        return (
            "你是 Tally 财务 AI 的数据对账规则生成器。"
            "请只输出一个合法 JSON 对象，不要输出解释，不要使用 markdown。"
            "目标 JSON 必须兼容当前 recon 引擎定义。"
            "要求：\n"
            "1. 顶层包含 rule_id/rule_name/description/file_rule_code/schema_version/rules。\n"
            "2. 输入固定绑定 left_recon_ready 与 right_recon_ready。\n"
            "3. recon.key_columns.mappings、recon.compare_columns.columns 必须完整。\n"
            "4. compare_columns 仅使用 numeric compare_type。\n"
            "5. tolerance 必须是数字。\n"
            "6. output.sheets 必须是对象，且包含 summary/source_only/target_only/matched_with_diff 四个 key，每个 key 下使用 name/enabled。\n"
            "7. 匹配主键、金额字段必须来自整理后样本字段，不要虚构不存在的字段名。\n"
            "8. 仅输出当前 recon 规则 JSON，不要输出额外说明，不要输出外层包裹。\n\n"
            f"方案名称：{session.scheme_name or '未命名方案'}\n"
            f"业务目标：{session.biz_goal or '未提供'}\n"
            f"数据源描述：{session.source_description or '未提供'}\n"
            f"用户补充：{user_message or '无'}\n"
            f"样本数据集：\n{self._summarize_dataset_inputs(session)}\n"
        )

    def _summarize_dataset_inputs(self, session: SchemeDesignSession) -> str:
        lines: list[str] = []
        for index, item in enumerate(session.sample_datasets, start=1):
            if not isinstance(item, dict):
                continue
            dataset_payload = self._build_dataset_prompt_payload(item, index=index)
            lines.append(
                json.dumps(dataset_payload, ensure_ascii=False)
            )
        if not lines and session.sample_files:
            for file_path in session.sample_files:
                lines.append(json.dumps({"file_name": Path(file_path).name}, ensure_ascii=False))
        return "\n".join(lines) if lines else "无"

    def _build_dataset_prompt_payload(self, dataset: dict[str, Any], *, index: int) -> dict[str, Any]:
        resolved = ensure_dataset_semantic_context(dict(dataset))
        schema_summary = resolved.get("schema_summary") if isinstance(resolved.get("schema_summary"), dict) else {}
        sample_rows = [row for row in list(resolved.get("sample_rows") or []) if isinstance(row, dict)][:3]
        field_label_map = (
            resolved.get("field_label_map") if isinstance(resolved.get("field_label_map"), dict) else {}
        )
        display_pairs: list[dict[str, str]] = []
        for raw_name, display_name in field_label_map.items():
            raw = str(raw_name or "").strip()
            display = str(display_name or "").strip()
            if not raw:
                continue
            display_pairs.append(
                {
                    "raw_name": raw,
                    "display_name": display or raw,
                    "display_with_raw": f"{display}({raw})" if display and display != raw else raw,
                }
            )
        return {
            "side": str(resolved.get("side") or "").strip(),
            "table_name": str(resolved.get("table_name") or "").strip(),
            "dataset_name": str(
                resolved.get("dataset_name")
                or resolved.get("table_name")
                or resolved.get("dataset_code")
                or f"dataset_{index}"
            ).strip(),
            "business_name": str(resolved.get("business_name") or "").strip(),
            "source_kind": str(resolved.get("source_kind") or "").strip(),
            "provider_code": str(resolved.get("provider_code") or "").strip(),
            "description": str(resolved.get("description") or "").strip(),
            "schema_summary": schema_summary,
            "sample_rows": sample_rows,
            "field_label_map": field_label_map,
            "fields": resolved.get("fields") if isinstance(resolved.get("fields"), list) else [],
            "field_display_pairs": display_pairs,
        }

    def _build_open_questions(self, session: SchemeDesignSession) -> list[str]:
        questions: list[str] = []
        if not session.biz_goal.strip():
            questions.append("请补充业务目标（例如：平台结算对账、回款核对）。")
        if not session.source_description.strip():
            questions.append("请补充左右数据来源说明（文件/数据集来源及用途）。")
        if not session.sample_files and not session.sample_datasets:
            questions.append("请至少提供一个样本文件或样本数据集。")
        if not session.drafts.proc_draft_json:
            questions.append("是否需要先做数据准备（proc）？若需要请说明目标表。")
        if not session.drafts.recon_draft_json:
            questions.append("请确认对账主键、金额字段和容差。")
        return questions

    def _collect_display_maps(
        self,
        datasets: list[dict[str, Any]],
    ) -> tuple[dict[str, str], dict[str, str]]:
        field_label_map: dict[str, str] = {}
        table_label_map: dict[str, str] = {}
        for item in datasets:
            if not isinstance(item, dict):
                continue
            normalized = ensure_dataset_semantic_context(dict(item))
            table_name = str(normalized.get("table_name") or "").strip()
            business_name = str(normalized.get("business_name") or "").strip()
            if table_name and business_name:
                table_label_map[table_name] = business_name
            raw_map = (
                normalized.get("field_label_map")
                if isinstance(normalized.get("field_label_map"), dict)
                else {}
            )
            for raw_name, display_name in raw_map.items():
                raw = str(raw_name or "").strip()
                display = str(display_name or "").strip()
                if not raw:
                    continue
                if display:
                    field_label_map.setdefault(raw, display)
                else:
                    field_label_map.setdefault(raw, raw)
        return field_label_map, table_label_map

    def _collect_proc_display_maps(
        self,
        session: SchemeDesignSession,
    ) -> tuple[dict[str, str], dict[str, str]]:
        datasets = [
            *(item for item in session.target_step.left_datasets if isinstance(item, dict)),
            *(item for item in session.target_step.right_datasets if isinstance(item, dict)),
            *(item for item in session.sample_datasets if isinstance(item, dict)),
        ]
        return self._collect_display_maps(datasets)

    def _collect_recon_display_maps(
        self,
        session: SchemeDesignSession,
    ) -> tuple[dict[str, str], dict[str, str]]:
        datasets = [item for item in session.sample_datasets if isinstance(item, dict)]
        return self._collect_display_maps(datasets)

    def _safe_proc_summary(self, rule: dict[str, Any] | None) -> str | None:
        if not isinstance(rule, dict) or not rule:
            return None
        steps = rule.get("steps")
        if not isinstance(steps, list) or not steps:
            return None
        for index, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                continue
            action = str(step.get("action") or "").strip()
            if action != "write_dataset":
                continue
            target_table = str(step.get("target_table") or "结果表").strip()
            source_tables = [
                str(source.get("table") or "").strip()
                for source in step.get("sources") or []
                if isinstance(source, dict) and str(source.get("table") or "").strip()
            ]
            if source_tables:
                return f"步骤{index}：将{'、'.join(source_tables)}整理后写入 {target_table}。"
        return None

    def _safe_recon_summary(self, rule: dict[str, Any] | None) -> str | None:
        if not isinstance(rule, dict) or not rule:
            return None
        rules = rule.get("rules")
        if not isinstance(rules, list) or not rules:
            return None
        first_rule = rules[0] if isinstance(rules[0], dict) else {}
        mappings = first_rule.get("recon", {}).get("key_columns", {}).get("mappings", [])
        columns = first_rule.get("recon", {}).get("compare_columns", {}).get("columns", [])
        first_mapping = mappings[0] if isinstance(mappings, list) and mappings and isinstance(mappings[0], dict) else {}
        first_column = columns[0] if isinstance(columns, list) and columns and isinstance(columns[0], dict) else {}
        key_name = str(first_mapping.get("source_field") or "biz_key").strip()
        amount_name = str(first_column.get("source_column") or "amount").strip()
        tolerance = first_column.get("tolerance", 0.01)
        return f"按 {key_name} 做精确匹配，比对金额字段 {amount_name}，容差 {tolerance}。"

    def _prepare_proc_draft_for_validation(
        self,
        session: SchemeDesignSession,
        rule: dict[str, Any],
    ) -> dict[str, Any]:
        normalized_rule = copy.deepcopy(rule)
        self._ensure_proc_dsl_constraints(normalized_rule)
        steps = normalized_rule.get("steps")
        if not isinstance(steps, list):
            return normalized_rule

        left_datasets = [
            item for item in session.target_step.left_datasets
            if isinstance(item, dict)
        ]
        right_datasets = [
            item for item in session.target_step.right_datasets
            if isinstance(item, dict)
        ]
        source_profiles_by_side = {
            "left": {
                str(profile.get("table_name") or "").strip(): profile
                for profile in self._build_side_source_profiles(session, side="left")
            },
            "right": {
                str(profile.get("table_name") or "").strip(): profile
                for profile in self._build_side_source_profiles(session, side="right")
            },
        }

        for step in steps:
            if not isinstance(step, dict):
                continue
            target_table = str(step.get("target_table") or "").strip()
            if target_table not in {"left_recon_ready", "right_recon_ready"}:
                continue
            side = "right" if target_table == "right_recon_ready" else "left"
            dataset_pool = right_datasets if side == "right" else left_datasets
            profile_map = source_profiles_by_side[side]
            action = str(step.get("action") or "").strip()
            if action == "create_schema":
                self._normalize_proc_schema_step(step)
                continue
            if action != "write_dataset":
                continue
            self._normalize_proc_write_dataset_step(
                step=step,
                dataset_pool=dataset_pool,
                profile_map=profile_map,
                side=side,
            )

        self._validate_proc_source_tables(normalized_rule, session=session)
        return normalized_rule

    def _ensure_proc_dsl_constraints(self, rule: dict[str, Any]) -> None:
        raw_constraints = rule.get("dsl_constraints")
        normalized = dict(raw_constraints) if isinstance(raw_constraints, dict) else {}
        for key, value in _DEFAULT_PROC_DSL_CONSTRAINTS.items():
            normalized[key] = copy.deepcopy(value)
        rule["dsl_constraints"] = normalized

    def _normalize_proc_schema_step(self, step: dict[str, Any]) -> None:
        schema = step.get("schema")
        if not isinstance(schema, dict):
            schema = {}
            step["schema"] = schema
        raw_columns = list(schema.get("columns") or [])
        columns_by_name: dict[str, dict[str, Any]] = {}

        for raw_column in raw_columns:
            if not isinstance(raw_column, dict):
                continue
            column_name = str(raw_column.get("name") or "").strip()
            if not column_name or column_name in columns_by_name:
                continue
            normalized_column = copy.deepcopy(raw_column)
            normalized_column["name"] = column_name
            normalized_column["data_type"] = self._normalize_proc_column_data_type(
                raw_column.get("data_type"),
                column_name=column_name,
            )
            if column_name == "biz_key":
                normalized_column["nullable"] = False
            elif column_name in {"biz_date", "source_name"} and "nullable" not in normalized_column:
                normalized_column["nullable"] = True
            if column_name == "amount":
                normalized_column.setdefault("precision", 18)
                normalized_column.setdefault("scale", 2)
                normalized_column.setdefault("default", 0)
            columns_by_name[column_name] = normalized_column

        normalized_columns: list[dict[str, Any]] = []
        for column_name in _PROC_STANDARD_COLUMN_ORDER:
            column = columns_by_name.pop(column_name, None)
            if column is None:
                column = copy.deepcopy(_PROC_STANDARD_COLUMN_DEFS[column_name])
            else:
                column["data_type"] = _PROC_STANDARD_COLUMN_DEFS[column_name]["data_type"]
                if column_name == "biz_key":
                    column["nullable"] = False
                elif column_name == "amount":
                    column.setdefault("precision", 18)
                    column.setdefault("scale", 2)
                    column.setdefault("default", 0)
                elif column_name in {"biz_date", "source_name"} and "nullable" not in column:
                    column["nullable"] = True
            normalized_columns.append(column)

        normalized_columns.extend(columns_by_name.values())
        schema["columns"] = normalized_columns

        primary_key = schema.get("primary_key")
        primary_key_list = [str(item).strip() for item in primary_key] if isinstance(primary_key, list) else []
        primary_key_list = [item for item in primary_key_list if item]
        if "biz_key" not in primary_key_list:
            primary_key_list = ["biz_key", *primary_key_list]
        schema["primary_key"] = list(dict.fromkeys(primary_key_list))

    def _normalize_proc_column_data_type(self, raw_data_type: Any, *, column_name: str) -> str:
        standard_column = _PROC_STANDARD_COLUMN_DEFS.get(column_name)
        if standard_column is not None:
            return str(standard_column["data_type"])

        data_type = str(raw_data_type or "").strip().lower()
        if data_type in {"string", "date", "decimal"}:
            return data_type
        if data_type in {"text", "varchar", "char", "character varying", "json", "jsonb"}:
            return "string"
        if data_type in {
            "int",
            "integer",
            "bigint",
            "smallint",
            "number",
            "numeric",
            "decimal",
            "float",
            "double",
            "double precision",
            "real",
        }:
            return "decimal"
        if data_type in {"date", "datetime", "timestamp", "timestamp without time zone"}:
            return "date"
        return "string"

    def _normalize_proc_write_dataset_step(
        self,
        *,
        step: dict[str, Any],
        dataset_pool: list[dict[str, Any]],
        profile_map: dict[str, dict[str, Any]],
        side: str,
    ) -> None:
        sources = step.get("sources")
        if not isinstance(sources, list) or not sources:
            sources = [
                {
                    "alias": str(profile.get("alias") or f"{side}_source_{index + 1}"),
                    "table": table_name,
                }
                for index, (table_name, profile) in enumerate(profile_map.items())
                if table_name
            ]
            step["sources"] = sources

        allowed_tables = [table_name for table_name in profile_map.keys() if table_name]
        unassigned_tables = list(allowed_tables)
        normalized_sources: list[dict[str, Any]] = []
        for index, source in enumerate(list(step.get("sources") or []), start=1):
            if not isinstance(source, dict):
                continue
            normalized_source = copy.deepcopy(source)
            current_table = str(normalized_source.get("table") or "").strip()
            matched_table = ""
            if current_table in allowed_tables:
                matched_table = current_table
            else:
                matched_table = self._match_dataset_table(dataset_pool=dataset_pool, source=normalized_source)
                if not matched_table and len(allowed_tables) == 1:
                    matched_table = allowed_tables[0]
                if not matched_table and not current_table and unassigned_tables:
                    matched_table = unassigned_tables[0]
            if matched_table:
                normalized_source["table"] = matched_table
                if matched_table in unassigned_tables:
                    unassigned_tables.remove(matched_table)
            normalized_source["alias"] = str(
                normalized_source.get("alias")
                or (profile_map.get(str(normalized_source.get("table") or "").strip()) or {}).get("alias")
                or f"{side}_source_{index}"
            ).strip()
            normalized_sources.append(normalized_source)
        step["sources"] = normalized_sources

        row_write_mode = str(step.get("row_write_mode") or "").strip()
        if row_write_mode not in {"upsert", "insert_if_missing", "update_only"}:
            step["row_write_mode"] = "upsert"

        self._ensure_proc_standard_mappings(step, profile_map=profile_map)

    def _ensure_proc_standard_mappings(
        self,
        step: dict[str, Any],
        *,
        profile_map: dict[str, dict[str, Any]],
    ) -> None:
        sources = [item for item in list(step.get("sources") or []) if isinstance(item, dict)]
        mappings = [copy.deepcopy(item) for item in list(step.get("mappings") or []) if isinstance(item, dict)]
        match = step.get("match")
        if not isinstance(match, dict):
            match = {}
            step["match"] = match
        match_sources = [copy.deepcopy(item) for item in list(match.get("sources") or []) if isinstance(item, dict)]

        for source in sources:
            alias = str(source.get("alias") or "").strip()
            table_name = str(source.get("table") or "").strip()
            if not alias or not table_name:
                continue
            profile = profile_map.get(table_name) or {}
            key_field = str(profile.get("key_field") or "").strip()
            amount_field = str(profile.get("amount_field") or "").strip()
            date_field = str(profile.get("date_field") or "").strip()
            source_name_field = str(profile.get("source_name_field") or "").strip()
            source_name_literal = str(profile.get("source_name_literal") or table_name).strip() or table_name

            if key_field:
                match_sources = self._upsert_match_source(match_sources, alias=alias, key_field=key_field)
            if key_field and not self._has_target_mapping(mappings, target_field="biz_key", alias=alias, source_count=len(sources)):
                mappings.append(
                    {
                        "target_field": "biz_key",
                        "value": {"type": "source", "source": {"alias": alias, "field": key_field}},
                        "field_write_mode": "overwrite",
                    }
                )
            if amount_field and not self._has_target_mapping(mappings, target_field="amount", alias=alias, source_count=len(sources)):
                mappings.append(
                    {
                        "target_field": "amount",
                        "value": {"type": "source", "source": {"alias": alias, "field": amount_field}},
                        "field_write_mode": "overwrite",
                    }
                )
            if date_field and not self._has_target_mapping(mappings, target_field="biz_date", alias=alias, source_count=len(sources)):
                mappings.append(
                    {
                        "target_field": "biz_date",
                        "value": {"type": "source", "source": {"alias": alias, "field": date_field}},
                        "field_write_mode": "overwrite",
                    }
                )
            if not self._has_target_mapping(mappings, target_field="source_name", alias=alias, source_count=len(sources)):
                if source_name_field:
                    mappings.append(
                        {
                            "target_field": "source_name",
                            "value": {"type": "source", "source": {"alias": alias, "field": source_name_field}},
                            "field_write_mode": "overwrite",
                        }
                    )
                else:
                    mappings.append(
                        self._build_constant_source_name_mapping(
                            alias=alias,
                            profile=profile,
                            literal=source_name_literal,
                            source_count=len(sources),
                        )
                    )

        step["mappings"] = mappings
        if match_sources:
            match["sources"] = match_sources

    def _upsert_match_source(
        self,
        match_sources: list[dict[str, Any]],
        *,
        alias: str,
        key_field: str,
    ) -> list[dict[str, Any]]:
        for item in match_sources:
            if str(item.get("alias") or "").strip() != alias:
                continue
            keys = [copy.deepcopy(key) for key in list(item.get("keys") or []) if isinstance(key, dict)]
            has_biz_key = any(
                str(key.get("target_field") or "").strip() == "biz_key"
                for key in keys
            )
            if not has_biz_key:
                keys.append({"field": key_field, "target_field": "biz_key"})
            item["keys"] = keys
            return match_sources
        match_sources.append(
            {
                "alias": alias,
                "keys": [{"field": key_field, "target_field": "biz_key"}],
            }
        )
        return match_sources

    def _has_target_mapping(
        self,
        mappings: list[dict[str, Any]],
        *,
        target_field: str,
        alias: str,
        source_count: int,
    ) -> bool:
        for mapping in mappings:
            if str(mapping.get("target_field") or "").strip() != target_field:
                continue
            aliases = self._collect_mapping_aliases(mapping)
            if alias in aliases:
                return True
            if not aliases and source_count == 1:
                return True
        return False

    def _collect_mapping_aliases(self, value: Any) -> set[str]:
        aliases: set[str] = set()
        if isinstance(value, dict):
            alias = str(value.get("alias") or "").strip()
            if alias:
                aliases.add(alias)
            for nested in value.values():
                aliases.update(self._collect_mapping_aliases(nested))
        elif isinstance(value, list):
            for item in value:
                aliases.update(self._collect_mapping_aliases(item))
        return aliases

    def _build_constant_source_name_mapping(
        self,
        *,
        alias: str,
        profile: dict[str, Any],
        literal: str,
        source_count: int,
    ) -> dict[str, Any]:
        if source_count <= 1:
            return {
                "target_field": "source_name",
                "value": {"type": "formula", "expr": json.dumps(literal, ensure_ascii=False)},
                "field_write_mode": "overwrite",
            }
        anchor_field = next(
            (
                str(profile.get(key) or "").strip()
                for key in ("key_field", "amount_field", "date_field", "source_name_field")
                if str(profile.get(key) or "").strip()
            ),
            "",
        )
        if not anchor_field:
            return {
                "target_field": "source_name",
                "value": {"type": "formula", "expr": json.dumps(literal, ensure_ascii=False)},
                "field_write_mode": "overwrite",
            }
        return {
            "target_field": "source_name",
            "value": {
                "type": "formula",
                "expr": json.dumps(literal, ensure_ascii=False),
                "bindings": {
                    "_alias_anchor": {
                        "type": "source",
                        "source": {"alias": alias, "field": anchor_field},
                    }
                },
            },
            "field_write_mode": "overwrite",
        }

    def _match_dataset_table(
        self,
        *,
        dataset_pool: list[dict[str, Any]],
        source: dict[str, Any],
    ) -> str:
        hint_values = {
            str(source.get("table") or "").strip().lower(),
            str(source.get("name") or "").strip().lower(),
            str(source.get("alias") or "").strip().lower(),
        }
        hint_values.discard("")
        hint_values.discard("unknown")
        if not hint_values:
            return ""

        for dataset in dataset_pool:
            candidates = {
                str(dataset.get("table_name") or "").strip().lower(),
                str(dataset.get("resource_key") or "").strip().lower(),
                str(dataset.get("dataset_code") or "").strip().lower(),
                str(dataset.get("dataset_name") or "").strip().lower(),
                str(dataset.get("source_key") or "").strip().lower(),
                str(dataset.get("source_id") or "").strip().lower(),
            }
            candidates.discard("")
            if hint_values & candidates:
                return self._resolve_dataset_table_name(dataset)
        return ""

    def _resolve_dataset_table_name(self, dataset: dict[str, Any]) -> str:
        return str(
            dataset.get("table_name")
            or dataset.get("resource_key")
            or dataset.get("dataset_code")
            or dataset.get("dataset_name")
            or dataset.get("source_id")
            or ""
        ).strip()

    def _validate_proc_source_tables(
        self,
        rule: dict[str, Any],
        *,
        session: SchemeDesignSession | None = None,
    ) -> None:
        steps = rule.get("steps")
        if not isinstance(steps, list):
            return
        missing_tables: list[str] = []
        invalid_tables: list[str] = []
        for step in steps:
            if not isinstance(step, dict):
                continue
            if str(step.get("action") or "").strip() != "write_dataset":
                continue
            step_id = str(step.get("step_id") or "unknown_step").strip()
            target_table = str(step.get("target_table") or "").strip()
            allowed_tables = self._resolve_allowed_tables_for_target(session, target_table)
            for index, source in enumerate(step.get("sources") or [], start=1):
                if not isinstance(source, dict):
                    continue
                table_name = str(source.get("table") or "").strip()
                if table_name and table_name.lower() != "unknown":
                    if allowed_tables and table_name not in allowed_tables:
                        alias = str(source.get("alias") or f"source_{index}").strip()
                        invalid_tables.append(f"{step_id}:{alias}->{table_name}")
                    continue
                alias = str(source.get("alias") or f"source_{index}").strip()
                missing_tables.append(f"{step_id}:{alias}")
        if missing_tables:
            joined = "；".join(missing_tables[:6])
            raise ValueError(f"proc 草稿缺少源表绑定，请检查 write_dataset.sources[].table：{joined}")
        if invalid_tables:
            joined = "；".join(invalid_tables[:6])
            raise ValueError(
                "proc 草稿的 sources[].table 必须绑定本轮输入数据集真实 table_name："
                f"{joined}"
            )

    def _resolve_allowed_tables_for_target(
        self,
        session: SchemeDesignSession | None,
        target_table: str,
    ) -> set[str]:
        if session is None:
            return set()
        if target_table == "right_recon_ready":
            dataset_pool = session.target_step.right_datasets
        elif target_table == "left_recon_ready":
            dataset_pool = session.target_step.left_datasets
        else:
            dataset_pool = []
        return {
            table_name
            for table_name in (
                self._resolve_dataset_table_name(item)
                for item in dataset_pool
                if isinstance(item, dict)
            )
            if table_name
        }

    def _build_proc_draft(self, session: SchemeDesignSession) -> dict[str, Any]:
        left_sources = self._build_side_source_profiles(session, side="left")
        right_sources = self._build_side_source_profiles(session, side="right")
        timestamp = datetime.now(timezone.utc).isoformat()
        return {
            "role_desc": session.scheme_name.strip() or session.biz_goal.strip() or "fallback proc draft",
            "version": "4.5",
            "metadata": {
                "created_at": timestamp,
                "author": "fallback-executor",
                "tags": ["数据整理", "对账方案"],
            },
            "global_config": {
                "default_round_precision": 2,
                "date_format": "YYYY-MM-DD",
                "null_value_handling": "keep",
                "error_handling": "stop",
            },
            "file_rule_code": "",
            "dsl_constraints": copy.deepcopy(_DEFAULT_PROC_DSL_CONSTRAINTS),
            "steps": [
                self._build_create_schema_step("left_recon_ready"),
                self._build_write_dataset_step("left", "left_recon_ready", left_sources),
                self._build_create_schema_step("right_recon_ready"),
                self._build_write_dataset_step("right", "right_recon_ready", right_sources),
            ],
        }

    def _build_recon_draft(self, session: SchemeDesignSession) -> dict[str, Any]:
        source_table = "left_recon_ready"
        target_table = "right_recon_ready"
        return {
            "rule_id": self._build_rule_id(session.scheme_name or "draft_recon_rule"),
            "rule_name": session.scheme_name or "draft_recon_rule",
            "description": session.biz_goal or "fallback recon draft",
            "file_rule_code": "",
            "schema_version": "1.6",
            "rules": [
                {
                    "enabled": True,
                    "source_file": {
                        "table_name": source_table,
                        "identification": {
                            "match_by": "table_name",
                            "match_value": source_table,
                            "match_strategy": "exact",
                        },
                    },
                    "target_file": {
                        "table_name": target_table,
                        "identification": {
                            "match_by": "table_name",
                            "match_value": target_table,
                            "match_strategy": "exact",
                        },
                    },
                    "recon": {
                        "key_columns": {
                            "mappings": [{"source_field": "biz_key", "target_field": "biz_key"}],
                            "match_type": "exact",
                            "transformations": {"source": {}, "target": {}},
                        },
                        "compare_columns": {
                            "columns": [
                                {
                                    "name": "金额差异",
                                    "compare_type": "numeric",
                                    "source_column": "amount",
                                    "target_column": "amount",
                                    "tolerance": 0.01,
                                }
                            ]
                        },
                        "aggregation": {"enabled": False, "group_by": [], "aggregations": []},
                    },
                    "output": {
                        "format": "xlsx",
                        "file_name_template": "{rule_name}_核对结果_{timestamp}",
                        "sheets": {
                            "summary": {"name": "核对汇总", "enabled": True},
                            "source_only": {"name": "左侧独有", "enabled": True},
                            "target_only": {"name": "右侧独有", "enabled": True},
                            "matched_with_diff": {"name": "差异记录", "enabled": True},
                        },
                    },
                }
            ],
        }

    def _extract_dataset_field_names(self, dataset: dict[str, Any]) -> list[str]:
        field_names: list[str] = []
        schema_summary = dataset.get("schema_summary")
        if isinstance(schema_summary, dict):
            columns = schema_summary.get("columns")
            if isinstance(columns, list):
                for column in columns:
                    if not isinstance(column, dict):
                        continue
                    field_name = str(column.get("name") or column.get("column_name") or "").strip()
                    if field_name and field_name not in field_names:
                        field_names.append(field_name)
            else:
                for key in schema_summary.keys():
                    field_name = str(key).strip()
                    if field_name and field_name != "columns" and field_name not in field_names:
                        field_names.append(field_name)
        if field_names:
            return field_names

        sample_rows = [row for row in list(dataset.get("sample_rows") or []) if isinstance(row, dict)]
        for row in sample_rows[:3]:
            for key in row.keys():
                field_name = str(key).strip()
                if field_name and field_name not in field_names:
                    field_names.append(field_name)
        return field_names

    def _pick_preferred_field(
        self,
        field_names: list[str],
        *,
        exact_candidates: list[str],
        regex_candidates: list[str],
        allow_any_fallback: bool = True,
    ) -> str:
        normalized_lookup = {field.lower(): field for field in field_names}
        for candidate in exact_candidates:
            matched = normalized_lookup.get(candidate.lower())
            if matched:
                return matched
        for field_name in field_names:
            lowered = field_name.lower()
            if any(re.search(pattern, lowered) for pattern in regex_candidates):
                return field_name
        if allow_any_fallback:
            return field_names[0] if field_names else ""
        return ""

    def _build_side_source_profiles(
        self,
        session: SchemeDesignSession,
        *,
        side: str,
    ) -> list[dict[str, Any]]:
        target_datasets = (
            session.target_step.left_datasets if side == "left" else session.target_step.right_datasets
        )
        raw_datasets = [dict(item) for item in target_datasets if isinstance(item, dict)]
        if not raw_datasets:
            raw_datasets = [
                dict(item)
                for item in session.sample_datasets
                if isinstance(item, dict) and str(item.get("side") or "").strip() == side
            ]

        profiles: list[dict[str, Any]] = []
        for index, dataset in enumerate(raw_datasets, start=1):
            table_name = self._resolve_dataset_table_name(dataset) or f"{side}_source_table_{index}"
            field_names = self._extract_dataset_field_names(dataset)
            key_field = self._pick_preferred_field(
                field_names,
                exact_candidates=[
                    "biz_key",
                    "order_id",
                    "order_no",
                    "order_code",
                    "trade_id",
                    "trade_no",
                    "biz_id",
                    "id",
                ],
                regex_candidates=[
                    r"order.*(id|no|code)$",
                    r"trade.*(id|no|code)$",
                    r"(id|no|code)$",
                    r"(订单|流水|单号)",
                ],
            )
            amount_field = self._pick_preferred_field(
                field_names,
                exact_candidates=[
                    "amount",
                    "trade_amount",
                    "pay_amount",
                    "paid_amount",
                    "payment_amount",
                    "settle_amount",
                    "total_amount",
                ],
                regex_candidates=[
                    r"(amount|amt|price|money|fee|balance)$",
                    r"(金额|应收|应付|实收|实付)",
                ],
            )
            date_field = self._pick_preferred_field(
                field_names,
                exact_candidates=[
                    "biz_date",
                    "trade_date",
                    "order_date",
                    "cycdate",
                    "created_at",
                    "created_time",
                    "date",
                    "pt",
                ],
                regex_candidates=[
                    r"(biz_)?date$",
                    r"(created|updated|trade|order).*(date|time)$",
                    r"(日期|时间|账期)",
                ],
            )
            source_name_field = self._pick_preferred_field(
                field_names,
                exact_candidates=[
                    "source_name",
                    "organize_name",
                    "shop_name",
                    "platform_name",
                    "supplier_name",
                    "merchant_name",
                    "company_name",
                ],
                regex_candidates=[
                    r"(source|shop|platform|supplier|merchant|company|organize)_name$",
                    r"(名称|主体|店铺)",
                ],
                allow_any_fallback=False,
            )
            profiles.append(
                {
                    "alias": f"{side}_source_{index}",
                    "table_name": table_name,
                    "key_field": key_field,
                    "amount_field": amount_field,
                    "date_field": date_field,
                    "source_name_field": source_name_field,
                    "source_name_literal": str(
                        dataset.get("dataset_name")
                        or dataset.get("resource_key")
                        or dataset.get("dataset_code")
                        or table_name
                    ).strip()
                    or table_name,
                }
            )

        if profiles:
            return profiles

        fallback_table = f"{side}_source_table"
        return [
            {
                "alias": f"{side}_source_1",
                "table_name": fallback_table,
                "key_field": "",
                "amount_field": "",
                "date_field": "",
                "source_name_field": "",
                "source_name_literal": fallback_table,
            }
        ]

    def _build_create_schema_step(self, target_table: str) -> dict[str, Any]:
        return {
            "step_id": f"create_{target_table}",
            "action": "create_schema",
            "target_table": target_table,
            "schema": {
                "columns": [
                    copy.deepcopy(_PROC_STANDARD_COLUMN_DEFS[name])
                    for name in _PROC_STANDARD_COLUMN_ORDER
                ],
                "primary_key": ["biz_key"],
                "export_enabled": True,
            },
        }

    def _build_write_dataset_step(
        self,
        side: str,
        target_table: str,
        source_profiles: list[dict[str, Any]],
    ) -> dict[str, Any]:
        sources = [
            {
                "alias": str(item.get("alias") or f"{side}_source_{index + 1}"),
                "table": str(item.get("table_name") or f"{side}_source_table_{index + 1}"),
            }
            for index, item in enumerate(source_profiles)
        ]
        match_sources = []
        mappings: list[dict[str, Any]] = []

        for index, profile in enumerate(source_profiles, start=1):
            alias = str(profile.get("alias") or f"{side}_source_{index}")
            key_field = str(profile.get("key_field") or "").strip()
            amount_field = str(profile.get("amount_field") or "").strip()
            date_field = str(profile.get("date_field") or "").strip()
            source_name_field = str(profile.get("source_name_field") or "").strip()
            source_name_literal = str(profile.get("source_name_literal") or profile.get("table_name") or alias).strip() or alias

            if key_field:
                match_sources.append(
                    {
                        "alias": alias,
                        "keys": [{"field": key_field, "target_field": "biz_key"}],
                    }
                )
                mappings.append(
                    {
                        "target_field": "biz_key",
                        "value": {
                            "type": "source",
                            "source": {"alias": alias, "field": key_field},
                        },
                        "field_write_mode": "overwrite",
                    }
                )

            if amount_field:
                mappings.append(
                    {
                        "target_field": "amount",
                        "value": {
                            "type": "source",
                            "source": {"alias": alias, "field": amount_field},
                        },
                        "field_write_mode": "overwrite",
                    }
                )

            if date_field:
                mappings.append(
                    {
                        "target_field": "biz_date",
                        "value": {
                            "type": "source",
                            "source": {"alias": alias, "field": date_field},
                        },
                        "field_write_mode": "overwrite",
                    }
                )

            if source_name_field:
                mappings.append(
                    {
                        "target_field": "source_name",
                        "value": {
                            "type": "source",
                            "source": {"alias": alias, "field": source_name_field},
                        },
                        "field_write_mode": "overwrite",
                    }
                )
            else:
                mappings.append(
                    {
                        "target_field": "source_name",
                        "value": {
                            "type": "formula",
                            "expr": json.dumps(source_name_literal, ensure_ascii=False),
                        },
                        "field_write_mode": "overwrite",
                    }
                )

        step: dict[str, Any] = {
            "step_id": f"{side}_write_recon_ready",
            "action": "write_dataset",
            "target_table": target_table,
            "depends_on": [f"create_{target_table}"],
            "row_write_mode": "upsert",
            "sources": sources,
            "mappings": mappings,
        }
        if match_sources:
            step["match"] = {"sources": match_sources}
        return step

    def _build_rule_id(self, name: str) -> str:
        normalized = "".join(char if char.isalnum() else "_" for char in name.strip()).strip("_")
        return (normalized or "draft_recon_rule").upper()

    def _normalize_proc_draft(self, parsed: dict[str, Any]) -> dict[str, Any]:
        rule_schema = _load_finance_mcp_rule_schema_module()
        validation = rule_schema.validate_rule_record(
            {"rule_code": "draft_proc", "rule": parsed},
            expected_kind="proc_steps",
        )
        if validation.get("success"):
            normalized_rule = validation.get("rule")
            if isinstance(normalized_rule, dict):
                return self._require_proc_targets(normalized_rule)
            return self._require_proc_targets(parsed)

        errors = validation.get("validation_errors") or []
        first_error = errors[0] if isinstance(errors, list) and errors else {}
        path = str(first_error.get("path") or "$").strip()
        message = str(first_error.get("message") or "unknown").strip()
        raise ValueError(f"proc 草稿不符合 steps DSL: {path} {message}".strip())

    def _normalize_recon_draft(self, parsed: dict[str, Any]) -> dict[str, Any]:
        rule_schema = _load_finance_mcp_rule_schema_module()
        validation = rule_schema.validate_rule_record(
            {"rule_code": "draft_recon", "rule": parsed},
            expected_kind="recon",
        )
        if validation.get("success"):
            normalized_rule = validation.get("rule")
            if isinstance(normalized_rule, dict):
                return self._require_recon_tables(normalized_rule)
            return self._require_recon_tables(parsed)

        errors = validation.get("validation_errors") or []
        first_error = errors[0] if isinstance(errors, list) and errors else {}
        path = str(first_error.get("path") or "$").strip()
        message = str(first_error.get("message") or "unknown").strip()
        raise ValueError(f"recon 草稿不符合引擎定义: {path} {message}".strip())

    def _require_proc_targets(self, rule: dict[str, Any]) -> dict[str, Any]:
        steps = rule.get("steps")
        if not isinstance(steps, list):
            raise ValueError("proc 草稿缺少 steps 数组")
        target_tables = {
            str(step.get("target_table") or "").strip()
            for step in steps
            if isinstance(step, dict)
        }
        required = {"left_recon_ready", "right_recon_ready"}
        if not required.issubset(target_tables):
            raise ValueError("proc 草稿必须同时输出 left_recon_ready 与 right_recon_ready")
        return rule

    def _require_recon_tables(self, rule: dict[str, Any]) -> dict[str, Any]:
        rules = rule.get("rules")
        if not isinstance(rules, list) or not rules:
            raise ValueError("recon 草稿缺少 rules 列表")
        first_rule = rules[0] if isinstance(rules[0], dict) else {}
        source_table = str(first_rule.get("source_file", {}).get("table_name") or "").strip()
        target_table = str(first_rule.get("target_file", {}).get("table_name") or "").strip()
        if source_table != "left_recon_ready" or target_table != "right_recon_ready":
            raise ValueError("recon 草稿必须绑定 left_recon_ready (source) 与 right_recon_ready (target)")
        compare_columns = first_rule.get("recon", {}).get("compare_columns", {})
        columns = compare_columns.get("columns")
        if not isinstance(columns, list) or not columns:
            raise ValueError("recon 草稿缺少 compare_columns 列配置")
        first_column = columns[0] if isinstance(columns[0], dict) else {}
        for rule_item in rules:
            if not isinstance(rule_item, dict):
                continue
            output = rule_item.get("output")
            if not isinstance(output, dict):
                output = {}
                rule_item["output"] = output
            output["sheets"] = self._normalize_recon_output_sheets(output.get("sheets"))
        tolerance = first_column.get("tolerance")
        if isinstance(tolerance, (int, float)):
            return rule
        try:
            numeric = float(tolerance)
        except (TypeError, ValueError) as exc:  # noqa: F841 - keep variable for debugging
            raise ValueError("recon 草稿的容差必须是数字")
        first_column["tolerance"] = numeric
        return rule

    def _normalize_recon_output_sheets(self, raw_sheets: Any) -> dict[str, dict[str, Any]]:
        if isinstance(raw_sheets, list):
            enabled_keys: set[str] = set()
            custom_names: dict[str, str] = {}
            for item in raw_sheets:
                if isinstance(item, str):
                    key = item.strip()
                    if key in _DEFAULT_RECON_OUTPUT_SHEETS:
                        enabled_keys.add(key)
                    continue
                if not isinstance(item, dict):
                    continue
                key = str(
                    item.get("key") or item.get("type") or item.get("sheet") or item.get("name") or ""
                ).strip()
                if key not in _DEFAULT_RECON_OUTPUT_SHEETS:
                    continue
                enabled_keys.add(key)
                custom_name = str(item.get("name") or "").strip()
                if custom_name:
                    custom_names[key] = custom_name
            normalized = {
                key: {
                    "name": custom_names.get(key, default_name),
                    "enabled": key in enabled_keys,
                }
                for key, default_name in _DEFAULT_RECON_OUTPUT_SHEETS.items()
            }
        else:
            sheets_dict = raw_sheets if isinstance(raw_sheets, dict) else {}
            normalized = {}
            for key, default_name in _DEFAULT_RECON_OUTPUT_SHEETS.items():
                raw_item = sheets_dict.get(key)
                if isinstance(raw_item, str):
                    normalized[key] = {"name": raw_item.strip() or default_name, "enabled": True}
                    continue
                if raw_item is False:
                    normalized[key] = {"name": default_name, "enabled": False}
                    continue
                raw_dict = raw_item if isinstance(raw_item, dict) else {}
                normalized[key] = {
                    "name": str(raw_dict.get("name") or "").strip() or default_name,
                    "enabled": bool(raw_dict.get("enabled", True)),
                }
        if not any(bool(item.get("enabled")) for item in normalized.values()):
            normalized["summary"] = {"name": _DEFAULT_RECON_OUTPUT_SHEETS["summary"], "enabled": True}
        return normalized


class SingleShotSchemeDesignExecutor(FallbackSchemeDesignExecutor):
    """Executor backed by a single LLM call plus deterministic rendering."""

    name = "single-shot-json-generator"

    def __init__(self, generator: SingleShotRuleGenerator | None = None) -> None:
        super().__init__()
        self._generator = generator or SingleShotRuleGenerator()

    async def run_turn(
        self,
        *,
        session: SchemeDesignSession,
        user_message: str,
        is_resume: bool = False,
    ) -> SchemeDesignExecutorResult:
        text = (user_message or "").strip()
        normalized = text.lower()
        focus = self._infer_focus(text, normalized)
        should_build_proc = focus in {"proc", "both"} and (
            focus == "proc" or not session.drafts.proc_draft_json
        )
        should_build_recon = focus in {"recon", "both"} and (
            focus == "recon" or not session.drafts.recon_draft_json
        )

        proc_draft: dict[str, Any] | None = None
        recon_draft: dict[str, Any] | None = None
        proc_draft_text: str | None = None
        recon_draft_text: str | None = None
        llm_errors: list[str] = []
        generation_notes: list[str] = []

        if should_build_proc:
            try:
                proc_result = await self._generator.generate_proc_rule(
                    session=session,
                    user_message=text,
                )
                proc_draft = self._normalize_proc_draft(
                    self._prepare_proc_draft_for_validation(session, proc_result.effective_rule_json)
                )
                proc_field_labels, proc_table_labels = self._collect_proc_display_maps(session)
                proc_draft_text = render_proc_draft_text(
                    proc_draft,
                    goal_hint=session.biz_goal,
                    field_label_map=proc_field_labels,
                    table_label_map=proc_table_labels,
                )
                notes = self._format_generation_notes("数据整理", proc_result)
                if notes:
                    generation_notes.append(notes)
                proc_generation_meta = {
                    "used_fallback": False,
                    "message": "AI 已生成数据整理配置。",
                    "details": proc_result.change_summary or proc_result.assumptions,
                }
            except Exception as exc:  # noqa: BLE001
                llm_errors.append(f"proc 生成失败：{exc}")
                proc_draft = self._build_proc_draft(session)
                proc_field_labels, proc_table_labels = self._collect_proc_display_maps(session)
                proc_draft_text = render_proc_draft_text(
                    proc_draft,
                    goal_hint=session.biz_goal,
                    field_label_map=proc_field_labels,
                    table_label_map=proc_table_labels,
                )
                proc_generation_meta = {
                    "used_fallback": True,
                    "message": "AI 生成失败，已回退为兜底规则，请重点检查后再试跑。",
                    "details": [str(exc).strip() or exc.__class__.__name__],
                }
        else:
            proc_generation_meta = None

        if should_build_recon:
            try:
                recon_result = await self._generator.generate_recon_rule(
                    session=session,
                    user_message=text,
                )
                recon_draft = self._normalize_recon_draft(recon_result.effective_rule_json)
                recon_field_labels, _ = self._collect_recon_display_maps(session)
                recon_draft_text = render_recon_draft_text(
                    recon_draft,
                    goal_hint=session.biz_goal,
                    field_label_map=recon_field_labels,
                )
                notes = self._format_generation_notes("对账逻辑", recon_result)
                if notes:
                    generation_notes.append(notes)
                recon_generation_meta = {
                    "used_fallback": False,
                    "message": "AI 已生成数据对账逻辑。",
                    "details": recon_result.change_summary or recon_result.assumptions,
                }
            except Exception as exc:  # noqa: BLE001
                llm_errors.append(f"recon 生成失败：{exc}")
                recon_draft = self._build_recon_draft(session)
                recon_field_labels, _ = self._collect_recon_display_maps(session)
                recon_draft_text = render_recon_draft_text(
                    recon_draft,
                    goal_hint=session.biz_goal,
                    field_label_map=recon_field_labels,
                )
                recon_generation_meta = {
                    "used_fallback": True,
                    "message": "AI 生成失败，已回退为兜底规则，请重点检查后再试跑。",
                    "details": [str(exc).strip() or exc.__class__.__name__],
                }
        else:
            recon_generation_meta = None

        open_questions = self._build_open_questions(session)
        phase = "恢复会话" if is_resume else "处理消息"
        if llm_errors:
            assistant_message = (
                f"[{phase}] 已尝试生成最新草稿，但部分阶段回退到了确定性默认规则："
                + "；".join(llm_errors)
                + "。你可以直接修改说明后重新生成，或继续试跑验证。"
            )
        else:
            assistant_message = (
                f"[{phase}] 已根据当前目标、数据集描述和样例数据生成最新草稿。"
                " 你可以直接继续试跑验证，或修改说明后重新生成。"
            )
        if generation_notes:
            assistant_message += "\n" + "\n".join(generation_notes)

        return SchemeDesignExecutorResult(
            assistant_message=assistant_message,
            loaded_skills=["proc-generator", "recon-generator"],
            open_questions=open_questions,
            proc_draft_json=proc_draft,
            recon_draft_json=recon_draft,
            proc_draft_text=proc_draft_text,
            recon_draft_text=recon_draft_text,
            proc_generation_meta=proc_generation_meta,
            recon_generation_meta=recon_generation_meta,
            pending_interrupt={
                "type": "design_review",
                "message": "请确认当前草稿方向，或继续补充约束。",
            },
        )

    def _format_generation_notes(self, title: str, result: SingleShotGenerationResult) -> str:
        sections: list[str] = []
        if result.provider:
            sections.append(f"生成器 provider：{result.provider}")
        if result.provider_fallback_errors:
            sections.append(f"前序 provider 回退：{'；'.join(result.provider_fallback_errors)}")
        if result.assumptions:
            sections.append(f"假设：{'；'.join(result.assumptions)}")
        if result.change_summary:
            sections.append(f"调整摘要：{'；'.join(result.change_summary)}")
        if result.unsupported_points:
            sections.append(f"暂不支持：{'；'.join(result.unsupported_points)}")
        if not sections:
            return ""
        return f"{title} 生成提示：" + " | ".join(sections)


class DeepAgentSchemeDesignExecutor(FallbackSchemeDesignExecutor):
    """Executor that defers generation to the DeepAgent skill runner."""

    name = "deep-agent-skills"

    def __init__(self, runner: DeepAgentSkillRunner | None = None) -> None:
        super().__init__()
        self._skill_runner = runner or get_skill_runner()

    async def run_turn(
        self,
        *,
        session: SchemeDesignSession,
        user_message: str,
        is_resume: bool = False,
    ) -> SchemeDesignExecutorResult:
        text = (user_message or "").strip()
        normalized = text.lower()
        focus = self._infer_focus(text, normalized)
        should_build_proc = focus in {"proc", "both"} and (
            focus == "proc" or not session.drafts.proc_draft_json
        )
        should_build_recon = focus in {"recon", "both"} and (
            focus == "recon" or not session.drafts.recon_draft_json
        )

        proc_draft: dict[str, Any] | None = None
        recon_draft: dict[str, Any] | None = None
        proc_draft_text: str | None = None
        recon_draft_text: str | None = None
        llm_errors: list[str] = []
        skill_notes: list[str] = []

        if should_build_proc:
            try:
                proc_result = await self._skill_runner.generate_proc_draft(session=session, user_message=text)
                proc_draft = self._normalize_proc_draft(
                    self._prepare_proc_draft_for_validation(session, proc_result.effective_rule_json)
                )
                proc_field_labels, proc_table_labels = self._collect_proc_display_maps(session)
                proc_draft_text = render_proc_draft_text(
                    proc_draft,
                    goal_hint=session.biz_goal,
                    field_label_map=proc_field_labels,
                    table_label_map=proc_table_labels,
                )
                notes = self._format_skill_notes("数据整理", proc_result)
                if notes:
                    skill_notes.append(notes)
            except Exception as exc:  # noqa: BLE001
                llm_errors.append(f"proc 生成失败：{exc}")
                proc_draft = self._build_proc_draft(session)
                proc_field_labels, proc_table_labels = self._collect_proc_display_maps(session)
                proc_draft_text = render_proc_draft_text(
                    proc_draft,
                    goal_hint=session.biz_goal,
                    field_label_map=proc_field_labels,
                    table_label_map=proc_table_labels,
                )

        if should_build_recon:
            try:
                recon_result = await self._skill_runner.generate_recon_draft(session=session, user_message=text)
                recon_draft = self._normalize_recon_draft(recon_result.effective_rule_json)
                recon_field_labels, _ = self._collect_recon_display_maps(session)
                recon_draft_text = render_recon_draft_text(
                    recon_draft,
                    goal_hint=session.biz_goal,
                    field_label_map=recon_field_labels,
                )
                notes = self._format_skill_notes("对账逻辑", recon_result)
                if notes:
                    skill_notes.append(notes)
            except Exception as exc:  # noqa: BLE001
                llm_errors.append(f"recon 生成失败：{exc}")
                recon_draft = self._build_recon_draft(session)
                recon_field_labels, _ = self._collect_recon_display_maps(session)
                recon_draft_text = render_recon_draft_text(
                    recon_draft,
                    goal_hint=session.biz_goal,
                    field_label_map=recon_field_labels,
                )

        open_questions = self._build_open_questions(session)
        phase = "恢复会话" if is_resume else "处理消息"
        if llm_errors:
            assistant_message = (
                f"[{phase}] 已尝试使用 DeepAgent skill 生成配置，但存在回退："
                + "；".join(llm_errors)
                + "。当前已返回可继续编辑的 JSON 草稿。"
            )
        else:
            assistant_message = (
                f"[{phase}] 已根据当前目标、数据集描述和样例数据生成最新草稿。"
                " 你可以直接继续试跑验证或补充约束后重新生成。"
            )
        if skill_notes:
            assistant_message += "\n" + "\n".join(skill_notes)

        return SchemeDesignExecutorResult(
            assistant_message=assistant_message,
            loaded_skills=["proc-config", "recon-config"],
            open_questions=open_questions,
            proc_draft_json=proc_draft,
            recon_draft_json=recon_draft,
            proc_draft_text=proc_draft_text,
            recon_draft_text=recon_draft_text,
            pending_interrupt={
                "type": "design_review",
                "message": "请确认当前草稿方向，或继续补充约束。",
            },
        )

    def _format_skill_notes(self, title: str, result: SkillGenerationResult) -> str:
        sections: list[str] = []
        if result.provider:
            sections.append(f"生成 provider：{result.provider}")
        if result.provider_fallback_errors:
            sections.append(f"前序 provider 回退：{'；'.join(result.provider_fallback_errors)}")
        if result.assumptions:
            sections.append(f"假设：{'；'.join(result.assumptions)}")
        if result.change_summary:
            sections.append(f"调整摘要：{'；'.join(result.change_summary)}")
        if result.unsupported_points:
            sections.append(f"暂不支持：{'；'.join(result.unsupported_points)}")
        if not sections:
            return ""
        return f"{title} Skill 提示：" + " | ".join(sections)


@lru_cache(maxsize=1)
def _load_finance_mcp_rule_schema_module() -> Any:
    module_path = PROJECT_ROOT / "finance-mcp" / "tools" / "rule_schema.py"
    spec = importlib.util.spec_from_file_location("finance_mcp_rule_schema", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载规则校验模块: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for model_name in (
        "ProcRuleSetModel",
        "ProcStepsRuleSetModel",
        "ProcMergeRuleSetModel",
        "ReconRuleSetModel",
        "FileValidationRuleModel",
    ):
        model = getattr(module, model_name, None)
        rebuild = getattr(model, "model_rebuild", None)
        if callable(rebuild):
            rebuild(_types_namespace=vars(module))
    return module
