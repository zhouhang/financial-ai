"""Design-session executor abstraction.

LLM-first implementation with deterministic JSON parsing and fallback drafts.
"""

from __future__ import annotations

import asyncio
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


@dataclass(slots=True)
class SchemeDesignExecutorResult:
    assistant_message: str
    loaded_skills: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    proc_draft_json: dict[str, Any] | None = None
    recon_draft_json: dict[str, Any] | None = None
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
            "6. output.sheets 需包含 summary/source_only/target_only/matched_with_diff。\n"
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
            name = str(
                item.get("dataset_name")
                or item.get("table_name")
                or item.get("dataset_code")
                or f"dataset_{index}"
            ).strip()
            side = str(item.get("side") or "").strip()
            description = str(item.get("description") or "").strip()
            source_kind = str(item.get("source_kind") or "").strip()
            provider_code = str(item.get("provider_code") or "").strip()
            schema_summary = item.get("schema_summary") if isinstance(item.get("schema_summary"), dict) else {}
            sample_rows = item.get("sample_rows") if isinstance(item.get("sample_rows"), list) else []
            lines.append(
                json.dumps(
                    {
                        "side": side,
                        "table_name": str(item.get("table_name") or "").strip(),
                        "dataset_name": name,
                        "source_kind": source_kind,
                        "provider_code": provider_code,
                        "description": description,
                        "schema_summary": schema_summary,
                        "sample_rows": sample_rows[:3],
                    },
                    ensure_ascii=False,
                )
            )
        if not lines and session.sample_files:
            for file_path in session.sample_files:
                lines.append(json.dumps({"file_name": Path(file_path).name}, ensure_ascii=False))
        return "\n".join(lines) if lines else "无"

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

    def _build_proc_draft(self, session: SchemeDesignSession) -> dict[str, Any]:
        source_tables = self._collect_source_tables(session)
        left_sources = source_tables[:1] or ["left_source_table"]
        right_sources = source_tables[1:2] or ["right_source_table"]
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
            "dsl_constraints": {
                "actions": ["create_schema", "write_dataset"],
                "builtin_functions": ["earliest_date", "current_date", "month_of"],
                "aggregate_operators": ["sum", "min"],
                "field_write_modes": ["overwrite", "increment"],
                "row_write_modes": ["insert_if_missing", "update_only", "upsert"],
                "column_data_types": ["string", "date", "decimal"],
                "value_node_types": ["source", "formula", "template_source", "function", "context"],
                "merge_strategies": ["union_distinct"],
                "loop_context_vars": ["month", "prev_month", "is_first_month"],
            },
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

    def _collect_source_tables(self, session: SchemeDesignSession) -> list[str]:
        tables: list[str] = []
        for item in session.sample_datasets:
            table_name = str(item.get("table_name") or item.get("dataset_code") or "").strip()
            if table_name:
                tables.append(table_name)
        for file_path in session.sample_files:
            table_name = Path(str(file_path or "")).stem.strip()
            if table_name:
                tables.append(table_name)
        return tables

    def _build_create_schema_step(self, target_table: str) -> dict[str, Any]:
        return {
            "step_id": f"create_{target_table}",
            "action": "create_schema",
            "target_table": target_table,
            "schema": {
                "columns": [
                    {"name": "biz_key", "data_type": "string", "nullable": False},
                    {"name": "amount", "data_type": "decimal", "precision": 18, "scale": 2, "default": 0},
                    {"name": "biz_date", "data_type": "date", "nullable": True},
                    {"name": "source_name", "data_type": "string", "nullable": True},
                ],
                "primary_key": ["biz_key"],
                "export_enabled": True,
            },
        }

    def _build_write_dataset_step(
        self,
        side: str,
        target_table: str,
        source_tables: list[str],
    ) -> dict[str, Any]:
        return {
            "step_id": f"{side}_write_recon_ready",
            "action": "write_dataset",
            "target_table": target_table,
            "depends_on": [f"create_{target_table}"],
            "row_write_mode": "upsert",
            "sources": [
                {"alias": f"{side}_source_{index + 1}", "table": table_name}
                for index, table_name in enumerate(source_tables)
            ],
            "match": {
                "sources": [
                    {
                        "alias": f"{side}_source_{index + 1}",
                        "keys": [{"field": "biz_key", "target_field": "biz_key"}],
                    }
                    for index, _ in enumerate(source_tables)
                ]
            },
            "mappings": [
                {
                    "target_field": "amount",
                    "value": {
                        "type": "source",
                        "source": {"alias": f"{side}_source_{index + 1}", "field": "amount"},
                    },
                    "field_write_mode": "overwrite",
                }
                for index, _ in enumerate(source_tables)
            ]
            + [
                {
                    "target_field": "biz_date",
                    "value": {
                        "type": "source",
                        "source": {"alias": f"{side}_source_{index + 1}", "field": "biz_date"},
                    },
                    "field_write_mode": "overwrite",
                }
                for index, _ in enumerate(source_tables)
            ]
            + [
                {
                    "target_field": "source_name",
                    "value": {
                        "type": "source",
                        "source": {"alias": f"{side}_source_{index + 1}", "field": "source_name"},
                    },
                    "field_write_mode": "overwrite",
                }
                for index, _ in enumerate(source_tables)
            ],
        }

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
                return normalized_rule
            return parsed

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
                return normalized_rule
            return parsed

        errors = validation.get("validation_errors") or []
        first_error = errors[0] if isinstance(errors, list) and errors else {}
        path = str(first_error.get("path") or "$").strip()
        message = str(first_error.get("message") or "unknown").strip()
        raise ValueError(f"recon 草稿不符合引擎定义: {path} {message}".strip())


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
        llm_errors: list[str] = []
        skill_notes: list[str] = []

        if should_build_proc:
            try:
                proc_result = await self._skill_runner.generate_proc_draft(session=session, user_message=text)
                proc_draft = self._normalize_proc_draft(proc_result.candidate_rule_json)
                notes = self._format_skill_notes("数据整理", proc_result)
                if notes:
                    skill_notes.append(notes)
            except Exception as exc:  # noqa: BLE001
                llm_errors.append(f"proc 生成失败：{exc}")
                proc_draft = self._build_proc_draft(session)

        if should_build_recon:
            try:
                recon_result = await self._skill_runner.generate_recon_draft(session=session, user_message=text)
                recon_draft = self._normalize_recon_draft(recon_result.candidate_rule_json)
                notes = self._format_skill_notes("对账逻辑", recon_result)
                if notes:
                    skill_notes.append(notes)
            except Exception as exc:  # noqa: BLE001
                llm_errors.append(f"recon 生成失败：{exc}")
                recon_draft = self._build_recon_draft(session)

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
            pending_interrupt={
                "type": "design_review",
                "message": "请确认当前草稿方向，或继续补充约束。",
            },
        )

    def _format_skill_notes(self, title: str, result: SkillGenerationResult) -> str:
        sections: list[str] = []
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
