"""Design-session executor abstraction.

LLM-first implementation with deterministic JSON parsing and fallback drafts.
"""

from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from config import PROJECT_ROOT
from models import SchemeDesignSession
from utils.llm import get_llm

from .rule_text_renderer import render_proc_draft_text, render_recon_draft_text
from .semantic_utils import ensure_dataset_semantic_context, infer_authoritative_raw_field_names
from .single_shot_generator import SingleShotGenerationResult, SingleShotRuleGenerator

logger = logging.getLogger(__name__)

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
            loaded_skills=[],
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
            "10. target_table 必须明确，供后续 recon 绑定；不要输出 proc_rule_json 外层包裹。\n"
            "11. sources[].table 必须使用数据集的 source_table_identifier 值（如 alipay_orders），禁止写字面量 table_name 或 source_table_identifier。\n"
            "12. biz_key/amount/biz_date/source_name 是标准输出字段，只能出现在 target_field，禁止用作 source.field。\n"
            "13. source_name 必须用 formula 类型输出固定中文字符串，禁止映射到源表任何列。\n\n"
            f"方案名称：{session.scheme_name or '未命名方案'}\n"
            f"业务目标：{session.biz_goal or '未提供'}\n"
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
        sample_rows = [row for row in list(resolved.get("sample_rows") or []) if isinstance(row, dict)][:3]
        field_label_map = (
            resolved.get("field_label_map") if isinstance(resolved.get("field_label_map"), dict) else {}
        )
        # Use only fields that appear in actual sample rows when available, so the AI
        # cannot reference stale schema columns absent from the published snapshot.
        if sample_rows:
            raw_field_names = list(dict.fromkeys(
                str(k).strip() for row in sample_rows for k in row.keys() if str(k).strip()
            ))
        else:
            raw_field_names = infer_authoritative_raw_field_names(resolved)
        display_pairs: list[dict[str, str]] = []
        for raw in raw_field_names:
            display = str(field_label_map.get(raw) or "").strip()
            display_pairs.append(
                {
                    "raw_name": raw,
                    "display_name": display or raw,
                    "display_with_raw": f"{display}({raw})" if display and display != raw else raw,
                }
            )
        return {
            "side": str(resolved.get("side") or "").strip(),
            "source_table_identifier": str(resolved.get("table_name") or "").strip(),
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
            "sample_rows": sample_rows,
            "field_label_map": field_label_map,
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

    _READY_FIELD_LABELS: dict[str, str] = {
        "biz_key": "业务主键",
        "amount": "金额",
        "biz_date": "业务日期",
        "source_name": "来源标识",
    }

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
            business_name = str(normalized.get("business_name") or "").strip()
            if business_name:
                for id_key in ("table_name", "resource_key", "dataset_code", "dataset_name", "source_id", "source_key"):
                    id_val = str(normalized.get(id_key) or "").strip()
                    if id_val and id_val != business_name:
                        table_label_map.setdefault(id_val, business_name)
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
        field_label_map, table_label_map = self._collect_display_maps(datasets)
        for raw, label in self._READY_FIELD_LABELS.items():
            field_label_map.setdefault(raw, label)
        return field_label_map, table_label_map

    def _collect_recon_display_maps(
        self,
        session: SchemeDesignSession,
    ) -> tuple[dict[str, str], dict[str, str]]:
        datasets = [item for item in session.sample_datasets if isinstance(item, dict)]
        field_label_map, table_label_map = self._collect_display_maps(datasets)
        for raw, label in self._READY_FIELD_LABELS.items():
            field_label_map.setdefault(raw, label)
        return field_label_map, table_label_map

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

    def _coerce_proc_step_shape_and_action(self, step: dict[str, Any]) -> None:
        for action_key in ("create_schema", "write_dataset"):
            nested = step.get(action_key)
            if not isinstance(nested, dict):
                continue
            normalized_nested = copy.deepcopy(nested)
            for passthrough_key in ("step_id", "target_table", "depends_on"):
                if passthrough_key not in normalized_nested and passthrough_key in step:
                    normalized_nested[passthrough_key] = copy.deepcopy(step.get(passthrough_key))
            normalized_nested.setdefault("action", action_key)
            step.clear()
            step.update(normalized_nested)
            return

        action = str(step.get("action") or "").strip()
        if action in {"create_schema", "write_dataset"}:
            return

        candidate_action = str(
            step.get("step_action")
            or step.get("operation")
            or step.get("op")
            or step.get("step_type")
            or step.get("type")
            or step.get("kind")
            or ""
        ).strip()
        if candidate_action in {"create_schema", "write_dataset"}:
            step["action"] = candidate_action
            return

        if isinstance(step.get("schema"), dict):
            step["action"] = "create_schema"
            return

        if any(
            key in step
            for key in (
                "sources",
                "mappings",
                "dynamic_mappings",
                "match",
                "aggregate",
                "filter",
                "reference_filter",
                "row_write_mode",
            )
        ):
            step["action"] = "write_dataset"

    def _coerce_proc_step_target_table(
        self,
        *,
        step: dict[str, Any],
        step_index: int,
        left_datasets: list[dict[str, Any]],
        right_datasets: list[dict[str, Any]],
    ) -> None:
        target_table = str(step.get("target_table") or "").strip()
        if target_table in {"left_recon_ready", "right_recon_ready"}:
            return

        hint_tokens = " ".join(
            str(value or "").strip().lower()
            for value in (
                step.get("target_table"),
                step.get("step_id"),
                step.get("name"),
                step.get("title"),
                step.get("description"),
                step.get("alias"),
            )
            if str(value or "").strip()
        )
        if hint_tokens:
            if any(token in hint_tokens for token in ("right", "右")):
                step["target_table"] = "right_recon_ready"
                return
            if any(token in hint_tokens for token in ("left", "左")):
                step["target_table"] = "left_recon_ready"
                return

        source_matches_left = False
        source_matches_right = False
        for source in list(step.get("sources") or []):
            if not isinstance(source, dict):
                continue
            if self._match_dataset_table(dataset_pool=left_datasets, source=source):
                source_matches_left = True
            if self._match_dataset_table(dataset_pool=right_datasets, source=source):
                source_matches_right = True
        if source_matches_left and not source_matches_right:
            step["target_table"] = "left_recon_ready"
            return
        if source_matches_right and not source_matches_left:
            step["target_table"] = "right_recon_ready"
            return

        step["target_table"] = "left_recon_ready" if step_index < 2 else "right_recon_ready"

    def _prepare_proc_draft_for_validation(
        self,
        session: SchemeDesignSession,
        rule: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(rule, dict):
            raise ValueError("proc 草稿不是 JSON 对象")
        normalized_rule = copy.deepcopy(rule)
        self._ensure_proc_dsl_constraints(normalized_rule)
        steps = normalized_rule.get("steps")
        if not isinstance(steps, list):
            steps = []
        steps = [copy.deepcopy(step) for step in steps if isinstance(step, dict)]
        normalized_rule["steps"] = steps

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

        for step_index, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            self._coerce_proc_step_shape_and_action(step)
            self._coerce_proc_step_target_table(
                step=step,
                step_index=step_index,
                left_datasets=left_datasets,
                right_datasets=right_datasets,
            )
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

        self._ensure_required_proc_steps(
            normalized_rule,
            source_profiles_by_side=source_profiles_by_side,
        )
        self._validate_proc_source_tables(normalized_rule, session=session)
        self._fix_formula_exprs(normalized_rule)
        return normalized_rule

    def _fix_formula_exprs(self, rule: dict[str, Any]) -> None:
        """Fix formula expr values that are bare unquoted strings.

        The LLM sometimes outputs `"expr": "业务订单数据"` (no quotes) for
        source_name constants.  Python's ast.parse then sees a bare Name node
        which is rejected by the runtime.  We detect and wrap such values in
        JSON string literals so they evaluate to the intended string constant.
        """
        import ast as _ast

        def _fix_expr(expr: str) -> str:
            text = expr.strip()
            if not text:
                return expr
            # Already a properly quoted string literal — leave it alone.
            if (text.startswith("'") and text.endswith("'")) or (
                text.startswith('"') and text.endswith('"')
            ):
                return expr
            # Contains formula-specific syntax — don't touch.
            if any(c in text for c in ("(", ")", "{", "}", "+", "*", "?", ":", "<", ">")):
                return expr
            try:
                tree = _ast.parse(text, mode="eval")
                if isinstance(tree.body, _ast.Name):
                    # Bare identifier (e.g. 业务订单数据) → quote it.
                    return json.dumps(text, ensure_ascii=False)
            except SyntaxError:
                # Unparseable as Python → likely Chinese with spaces → quote it.
                return json.dumps(text, ensure_ascii=False)
            return expr

        steps = rule.get("steps")
        if not isinstance(steps, list):
            return
        for step in steps:
            if not isinstance(step, dict):
                continue
            for mapping in list(step.get("mappings") or []):
                if not isinstance(mapping, dict):
                    continue
                value = mapping.get("value")
                if not isinstance(value, dict) or value.get("type") != "formula":
                    continue
                expr = value.get("expr")
                if not isinstance(expr, str):
                    continue
                fixed = _fix_expr(expr)
                if fixed != expr:
                    value["expr"] = fixed

    def _ensure_proc_dsl_constraints(self, rule: dict[str, Any]) -> None:
        raw_constraints = rule.get("dsl_constraints")
        normalized = dict(raw_constraints) if isinstance(raw_constraints, dict) else {}
        for key, value in _DEFAULT_PROC_DSL_CONSTRAINTS.items():
            normalized[key] = copy.deepcopy(value)
        rule["dsl_constraints"] = normalized

    def _normalize_proc_schema_step(self, step: dict[str, Any]) -> None:
        target_table = str(step.get("target_table") or "").strip()
        if target_table:
            step["step_id"] = f"create_{target_table}"
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
        target_table = str(step.get("target_table") or "").strip()
        if target_table:
            step["step_id"] = f"{side}_write_recon_ready"
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
        table_alias_map: dict[str, str] = {}
        alias_profile_map: dict[str, dict[str, Any]] = {}
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
            normalized_table = str(normalized_source.get("table") or "").strip()
            normalized_alias = str(normalized_source.get("alias") or "").strip()
            if normalized_table and normalized_alias:
                table_alias_map.setdefault(normalized_table, normalized_alias)
                matched_profile = profile_map.get(normalized_table)
                if matched_profile:
                    alias_profile_map[normalized_alias] = matched_profile
            normalized_sources.append(normalized_source)
        step["sources"] = normalized_sources

        row_write_mode = str(step.get("row_write_mode") or "").strip()
        if row_write_mode not in {"upsert", "insert_if_missing", "update_only"}:
            step["row_write_mode"] = "upsert"
        create_step_id = f"create_{target_table}" if target_table else ""
        if create_step_id:
            depends_on = [
                str(item).strip()
                for item in list(step.get("depends_on") or [])
                if str(item).strip()
            ]
            if create_step_id not in depends_on:
                step["depends_on"] = [create_step_id, *depends_on]

        self._normalize_proc_mapping_entries(
            step=step,
            alias_profile_map=alias_profile_map,
            table_alias_map=table_alias_map,
        )
        self._sanitize_proc_source_bindings(step=step, profile_map=profile_map)
        self._ensure_proc_standard_mappings(step, profile_map=profile_map)

    def _normalize_proc_mapping_entries(
        self,
        *,
        step: dict[str, Any],
        alias_profile_map: dict[str, dict[str, Any]],
        table_alias_map: dict[str, str],
    ) -> None:
        mappings = [item for item in list(step.get("mappings") or []) if isinstance(item, dict)]
        sources = [item for item in list(step.get("sources") or []) if isinstance(item, dict)]
        sole_alias = (
            str(sources[0].get("alias") or "").strip()
            if len(sources) == 1 and isinstance(sources[0], dict)
            else ""
        )

        normalized_mappings: list[dict[str, Any]] = []
        for raw_mapping in mappings:
            mapping = copy.deepcopy(raw_mapping)
            self._normalize_proc_mapping_value(
                mapping,
                table_alias_map=table_alias_map,
                sole_alias=sole_alias,
            )
            self._coerce_proc_mapping_target(
                mapping,
                alias_profile_map=alias_profile_map,
                sole_alias=sole_alias,
            )
            if not str(mapping.get("target_field") or "").strip() and not str(
                mapping.get("target_field_template") or ""
            ).strip():
                continue
            normalized_mappings.append(mapping)
        step["mappings"] = normalized_mappings

    def _normalize_proc_mapping_value(
        self,
        mapping: dict[str, Any],
        *,
        table_alias_map: dict[str, str],
        sole_alias: str,
    ) -> None:
        value = mapping.get("value")
        if not isinstance(value, dict):
            if isinstance(mapping.get("source"), dict):
                value = {
                    "type": "source",
                    "source": copy.deepcopy(mapping.get("source")),
                }
            else:
                source_field = str(
                    mapping.get("source_field")
                    or mapping.get("sourceField")
                    or ""
                ).strip()
                source_alias = str(
                    mapping.get("source_alias")
                    or mapping.get("sourceAlias")
                    or mapping.get("alias")
                    or ""
                ).strip()
                source_table = str(
                    mapping.get("source_table")
                    or mapping.get("sourceTable")
                    or ""
                ).strip()
                if source_field:
                    normalized_source: dict[str, Any] = {"field": source_field}
                    resolved_alias = source_alias or table_alias_map.get(source_table, "") or sole_alias
                    if resolved_alias:
                        normalized_source["alias"] = resolved_alias
                    elif source_table:
                        normalized_source["table"] = source_table
                    value = {"type": "source", "source": normalized_source}

        if not isinstance(value, dict):
            return

        if not str(value.get("type") or "").strip():
            if isinstance(value.get("source"), dict):
                value["type"] = "source"
            elif isinstance(value.get("expr"), str):
                value["type"] = "formula"

        source = value.get("source")
        if isinstance(source, dict):
            source_alias = str(source.get("alias") or "").strip()
            source_table = str(source.get("table") or "").strip()
            if not source_alias:
                resolved_alias = table_alias_map.get(source_table, "") or sole_alias
                if resolved_alias:
                    source["alias"] = resolved_alias

        mapping["value"] = value

    def _coerce_proc_mapping_target(
        self,
        mapping: dict[str, Any],
        *,
        alias_profile_map: dict[str, dict[str, Any]],
        sole_alias: str,
    ) -> None:
        target_template = str(
            mapping.get("target_field_template")
            or mapping.get("targetFieldTemplate")
            or ""
        ).strip()
        if target_template:
            mapping["target_field_template"] = target_template

        target_field = self._normalize_proc_target_field_name(mapping.get("target_field"))
        if not target_field and not target_template:
            for candidate_key in (
                "target",
                "target_name",
                "targetName",
                "targetField",
                "output_field",
                "outputField",
                "output_name",
                "outputName",
                "target_column",
                "targetColumn",
                "column_name",
                "columnName",
                "name",
            ):
                target_field = self._normalize_proc_target_field_name(mapping.get(candidate_key))
                if target_field:
                    break
        if not target_field and not target_template:
            target_field = self._infer_proc_mapping_target_field(
                mapping,
                alias_profile_map=alias_profile_map,
                sole_alias=sole_alias,
            )
        if target_field:
            mapping["target_field"] = target_field

    def _normalize_proc_target_field_name(self, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        compact = re.sub(r"[\s\-]+", "_", text).strip("_").lower()
        alias_map = {
            "biz_key": "biz_key",
            "bizkey": "biz_key",
            "business_key": "biz_key",
            "business_id": "biz_key",
            "match_key": "biz_key",
            "key": "biz_key",
            "业务主键": "biz_key",
            "主键": "biz_key",
            "金额": "amount",
            "amount": "amount",
            "amt": "amount",
            "业务日期": "biz_date",
            "日期": "biz_date",
            "时间": "biz_date",
            "biz_date": "biz_date",
            "bizdate": "biz_date",
            "来源标识": "source_name",
            "来源": "source_name",
            "来源名称": "source_name",
            "source_name": "source_name",
            "sourcename": "source_name",
        }
        return alias_map.get(compact, text)

    def _infer_proc_mapping_target_field(
        self,
        mapping: dict[str, Any],
        *,
        alias_profile_map: dict[str, dict[str, Any]],
        sole_alias: str,
    ) -> str:
        value = mapping.get("value")
        refs = self._collect_source_references(value if isinstance(value, dict) else mapping, sole_alias=sole_alias)
        for alias, field_name in refs:
            resolved_alias = alias or sole_alias
            profile = alias_profile_map.get(resolved_alias) or {}
            if not profile or not field_name:
                continue
            if field_name == str(profile.get("key_field") or "").strip():
                return "biz_key"
            if field_name == str(profile.get("amount_field") or "").strip():
                return "amount"
            if field_name == str(profile.get("date_field") or "").strip():
                return "biz_date"
            if field_name == str(profile.get("source_name_field") or "").strip():
                return "source_name"
        return ""

    def _ensure_required_proc_steps(
        self,
        rule: dict[str, Any],
        *,
        source_profiles_by_side: dict[str, dict[str, dict[str, Any]]],
    ) -> None:
        steps = rule.get("steps")
        if not isinstance(steps, list):
            steps = []
            rule["steps"] = steps

        keyed_steps: dict[tuple[str, str], dict[str, Any]] = {}
        extras: list[dict[str, Any]] = []
        for step in steps:
            if not isinstance(step, dict):
                continue
            action = str(step.get("action") or "").strip()
            target_table = str(step.get("target_table") or "").strip()
            key = (target_table, action)
            if action in {"create_schema", "write_dataset"} and target_table in {"left_recon_ready", "right_recon_ready"}:
                keyed_steps.setdefault(key, step)
            else:
                extras.append(step)

        ordered_steps: list[dict[str, Any]] = []
        for side, target_table in (("left", "left_recon_ready"), ("right", "right_recon_ready")):
            create_key = (target_table, "create_schema")
            write_key = (target_table, "write_dataset")
            create_step = keyed_steps.get(create_key)
            if not isinstance(create_step, dict):
                create_step = self._build_create_schema_step(target_table)
            else:
                create_step["step_id"] = f"create_{target_table}"
            write_step = keyed_steps.get(write_key)
            if not isinstance(write_step, dict):
                write_step = self._build_write_dataset_step(
                    side,
                    target_table,
                    list(source_profiles_by_side.get(side, {}).values()),
                )
            else:
                write_step["step_id"] = f"{side}_write_recon_ready"
                write_step.setdefault("target_table", target_table)
                write_step.setdefault("action", "write_dataset")
                depends_on = [
                    str(item).strip()
                    for item in list(write_step.get("depends_on") or [])
                    if str(item).strip()
                ]
                create_step_id = str(create_step.get("step_id") or f"create_{target_table}").strip()
                if create_step_id and create_step_id not in depends_on:
                    write_step["depends_on"] = [create_step_id, *depends_on]
            ordered_steps.extend([create_step, write_step])

        ordered_steps.extend(extras)
        rule["steps"] = ordered_steps

    def _sanitize_proc_source_bindings(
        self,
        *,
        step: dict[str, Any],
        profile_map: dict[str, dict[str, Any]],
    ) -> None:
        sources = [item for item in list(step.get("sources") or []) if isinstance(item, dict)]
        alias_field_map: dict[str, set[str]] = {}
        for source in sources:
            alias = str(source.get("alias") or "").strip()
            table_name = str(source.get("table") or "").strip()
            if not alias or not table_name:
                continue
            profile = profile_map.get(table_name) or {}
            alias_field_map[alias] = {
                str(field).strip()
                for field in list(profile.get("available_fields") or [])
                if str(field).strip()
            }

        sole_alias = next(iter(alias_field_map.keys()), "") if len(alias_field_map) == 1 else ""
        mappings = [item for item in list(step.get("mappings") or []) if isinstance(item, dict)]
        step["mappings"] = [
            mapping
            for mapping in mappings
            if not self._mapping_has_invalid_source_field(
                mapping,
                alias_field_map=alias_field_map,
                sole_alias=sole_alias,
            )
        ]

        match = step.get("match")
        if not isinstance(match, dict):
            return
        sanitized_match_sources: list[dict[str, Any]] = []
        for item in list(match.get("sources") or []):
            if not isinstance(item, dict):
                continue
            alias = str(item.get("alias") or sole_alias).strip()
            known_fields = alias_field_map.get(alias) or set()
            keys: list[dict[str, Any]] = []
            for key_item in list(item.get("keys") or []):
                if not isinstance(key_item, dict):
                    continue
                field_name = str(key_item.get("field") or "").strip()
                if known_fields and field_name and field_name not in known_fields:
                    continue
                keys.append(copy.deepcopy(key_item))
            if not keys:
                continue
            normalized_item = copy.deepcopy(item)
            normalized_item["keys"] = keys
            sanitized_match_sources.append(normalized_item)
        if sanitized_match_sources:
            match["sources"] = sanitized_match_sources
        else:
            match.pop("sources", None)

    def _mapping_has_invalid_source_field(
        self,
        mapping: dict[str, Any],
        *,
        alias_field_map: dict[str, set[str]],
        sole_alias: str,
    ) -> bool:
        for alias, field_name in self._collect_source_references(mapping, sole_alias=sole_alias):
            if not field_name:
                continue
            if alias and alias not in alias_field_map:
                return True
            known_fields = alias_field_map.get(alias) or set()
            if known_fields and field_name not in known_fields:
                return True
        return False

    def _collect_source_references(
        self,
        value: Any,
        *,
        sole_alias: str,
    ) -> list[tuple[str, str]]:
        refs: list[tuple[str, str]] = []
        if isinstance(value, dict):
            source = value.get("source")
            if isinstance(source, dict):
                refs.append(
                    (
                        str(source.get("alias") or sole_alias).strip(),
                        str(source.get("field") or "").strip(),
                    )
                )
            for key, nested in value.items():
                if key == "source":
                    continue
                refs.extend(self._collect_source_references(nested, sole_alias=sole_alias))
        elif isinstance(value, list):
            for item in value:
                refs.extend(self._collect_source_references(item, sole_alias=sole_alias))
        return refs

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
        return infer_authoritative_raw_field_names(dataset)

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
                    r"(^amt_|_amt_|amount|price|money|fee|balance)",
                    r"(金额|应收|应付|实收|实付)",
                ],
                allow_any_fallback=False,
            )
            date_field = self._pick_preferred_field(
                field_names,
                exact_candidates=[
                    "biz_date",
                    "trade_date",
                    "order_date",
                    "pay_date",
                    "paid_date",
                    "pay_time",
                    "paid_time",
                    "settle_date",
                    "settle_time",
                    "cycdate",
                    "created_at",
                    "created_time",
                    "date",
                    "pt",
                ],
                regex_candidates=[
                    r"(biz_)?date$",
                    r"(pay|paid|settle).*(date|time)$",
                    r"(created|updated|trade|order).*(date|time)$",
                    r"(日期|时间|账期)",
                ],
                allow_any_fallback=False,
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
                    "available_fields": field_names,
                    "key_field": key_field,
                    "amount_field": amount_field,
                    "date_field": date_field,
                    "source_name_field": source_name_field,
                    "source_name_literal": str(
                        dataset.get("business_name")
                        or dataset.get("dataset_name")
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
                "available_fields": [],
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

        path, message = self._extract_validation_error_details(validation)
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

        path, message = self._extract_validation_error_details(validation)
        raise ValueError(f"recon 草稿不符合引擎定义: {path} {message}".strip())

    def _extract_validation_error_details(self, validation: Any) -> tuple[str, str]:
        if not isinstance(validation, dict):
            message = str(validation).strip()
            return "$", message or "unknown"

        errors = validation.get("validation_errors")
        if isinstance(errors, dict):
            errors = [errors]
        elif isinstance(errors, str):
            errors = [errors]

        if isinstance(errors, list) and errors:
            return self._coerce_validation_error(errors[0])

        message = str(validation.get("error") or "unknown").strip()
        return "$", message or "unknown"

    def _coerce_validation_error(self, error: Any) -> tuple[str, str]:
        if isinstance(error, dict):
            path = str(error.get("path") or "$").strip()
            message = str(error.get("message") or "unknown").strip()
            return path or "$", message or "unknown"

        text = str(error).strip()
        if not text:
            return "$", "unknown"

        head, sep, tail = text.partition(" ")
        if sep and (head.startswith("$") or "." in head):
            return head.strip() or "$", tail.strip() or text
        return "$", text

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
                proc_draft_text = proc_result.draft_text or None
                notes = self._format_generation_notes("数据整理", proc_result)
                if notes:
                    generation_notes.append(notes)
                proc_generation_meta = {
                    "used_fallback": False,
                    "message": "AI 已生成数据整理配置。",
                    "details": proc_result.change_summary or proc_result.assumptions,
                }
            except Exception as exc:  # noqa: BLE001
                logger.warning("[scheme_design][proc] single-shot executor fallback: %s", exc)
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
                    "message": "AI 生成失败，请检查后重新点击AI生成整理配置。",
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
                recon_draft_text = recon_result.draft_text or None
                notes = self._format_generation_notes("对账逻辑", recon_result)
                if notes:
                    generation_notes.append(notes)
                recon_generation_meta = {
                    "used_fallback": False,
                    "message": "AI 已生成数据对账逻辑。",
                    "details": recon_result.change_summary or recon_result.assumptions,
                }
            except Exception as exc:  # noqa: BLE001
                logger.warning("[scheme_design][recon] single-shot executor fallback: %s", exc)
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
                    "message": "AI 生成失败，请检查后重新点击AI生成对账逻辑。",
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
