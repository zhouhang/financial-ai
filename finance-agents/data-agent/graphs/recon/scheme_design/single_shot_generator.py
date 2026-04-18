from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Literal

from config import PROJECT_ROOT
from models import SchemeDesignSession
from utils.llm import get_available_llm_providers, get_llm

from .semantic_utils import build_prompt_dataset_payload


logger = logging.getLogger(__name__)

Stage = Literal["proc", "recon"]


@dataclass(slots=True)
class SingleShotGenerationResult:
    effective_rule_json: dict[str, Any]
    assumptions: list[str] = field(default_factory=list)
    change_summary: list[str] = field(default_factory=list)
    unsupported_points: list[str] = field(default_factory=list)
    provider: str = ""
    provider_fallback_errors: list[str] = field(default_factory=list)
    raw_response: dict[str, Any] = field(default_factory=dict)


class SingleShotRuleGenerator:
    """Single-call rule generator for scheme design proc/recon steps."""

    def __init__(self) -> None:
        self._provider_order = get_available_llm_providers()
        if not self._provider_order:
            raise ValueError("未配置任何可用的 LLM provider，无法生成方案规则")
        self._skill_root = PROJECT_ROOT / "finance-agents" / "data-agent" / "skills"

    async def generate_proc_rule(
        self,
        *,
        session: SchemeDesignSession,
        user_message: str,
    ) -> SingleShotGenerationResult:
        prompt = self._build_proc_prompt(session=session, user_message=user_message)
        return await self._generate(stage="proc", prompt=prompt)

    async def generate_recon_rule(
        self,
        *,
        session: SchemeDesignSession,
        user_message: str,
    ) -> SingleShotGenerationResult:
        prompt = self._build_recon_prompt(session=session, user_message=user_message)
        return await self._generate(stage="recon", prompt=prompt)

    async def _generate(
        self,
        *,
        stage: Stage,
        prompt: str,
    ) -> SingleShotGenerationResult:
        errors: list[str] = []
        for provider in self._provider_order:
            try:
                logger.info("[scheme_design][%s] single-shot generator start provider=%s", stage, provider)
                llm = get_llm(provider=provider, temperature=0.05)
                response = await asyncio.wait_for(
                    asyncio.to_thread(llm.invoke, prompt),
                    timeout=45,
                )
                content = getattr(response, "content", "")
                if isinstance(content, list):
                    content = "".join(str(getattr(item, "text", item)) for item in content)
                parsed = self._parse_json_content(str(content or "").strip())
                result = self._normalize_envelope(parsed, stage=stage)
                result.provider = provider
                result.provider_fallback_errors = list(errors)
                logger.info("[scheme_design][%s] single-shot generator finished provider=%s", stage, provider)
                return result
            except Exception as exc:  # noqa: BLE001
                formatted_error = self._format_exception(exc)
                logger.warning(
                    "[scheme_design][%s] provider=%s failed: %s",
                    stage,
                    provider,
                    formatted_error,
                )
                errors.append(f"{provider}: {formatted_error}")
        raise RuntimeError("；".join(errors) if errors else "规则生成失败")

    def _build_proc_prompt(self, *, session: SchemeDesignSession, user_message: str) -> str:
        request_type = (
            "regenerate_proc_draft"
            if session.proc_step.effective_rule_json
            else "generate_proc_draft"
        )
        payload = {
            "request_type": request_type,
            "session_context": {
                "session_id": session.session_id,
                "scheme_name": session.scheme_name,
                "biz_goal": session.biz_goal,
            },
            "target_context": {
                "left_sources": self._dataset_payload(session.target_step.left_datasets),
                "right_sources": self._dataset_payload(session.target_step.right_datasets),
                "left_description": session.target_step.left_description,
                "right_description": session.target_step.right_description,
                "sample_datasets": self._dataset_payload(session.sample_datasets),
            },
            "rule_context": {
                "user_instruction_text": (user_message or "").strip(),
                "previous_effective_rule_json": session.proc_step.effective_rule_json,
                "previous_trial_feedback": session.proc_step.trial_result,
                "previous_validation_errors": session.proc_step.validation_result,
            },
        }
        return (
            "你是 Tally 财务 AI 的数据整理 JSON 单次生成器。\n"
            "你只负责返回一个 JSON 对象，不要输出 markdown，不要输出解释。\n"
            "后端会根据 effective_rule_json 自己渲染中文说明，所以你不要输出 draft_text。\n"
            "target_context 中会提供 business_name、field_label_map、fields 和 display_with_raw（如 订单金额(order_amount)）。\n"
            "这些字段仅用于理解业务语义，不能作为 JSON 字段名直接写入。\n"
            "如果用户当前编辑说明与现有 DSL 能力冲突，优先保证 JSON 合法，并把冲突写入 unsupported_points。\n"
            "如果上一轮试跑或校验失败，优先根据 previous_trial_feedback 和 previous_validation_errors 修正 JSON。\n"
            "返回 JSON 顶层字段固定为：effective_rule_json、assumptions、change_summary、unsupported_points。\n"
            "effective_rule_json 必须是当前 proc steps DSL 可接受的完整规则对象，且只能输出 left_recon_ready 与 right_recon_ready 两份结果。\n\n"
            "关键约束：\n"
            "1. effective_rule_json 中所有字段必须使用原始 raw_name（来自 schema_summary/sample_rows 的 key），禁止输出中文字段名。\n"
            "2. biz_date 必须映射到日期类型的字段（字段名含 date/time/日期/时间，或 schema_summary 中标注为 date/datetime 类型）。"
            "   若无明确日期字段，改用固定值 formula 输出空字符串，切勿将订单号、金额等非日期字段赋给 biz_date。\n"
            "3. source_name 必须使用 formula 类型输出数据来源的业务名称字符串（中文），禁止映射到源表的任意数据库字段。\n\n"
            "以下 reference 文档用于约束输出，禁止偏离：\n"
            f"{self._reference_bundle('proc')}\n\n"
            "本轮结构化输入如下：\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2, default=self._json_default)}\n\n"
            "请直接输出 JSON。"
        )

    def _build_recon_prompt(self, *, session: SchemeDesignSession, user_message: str) -> str:
        request_type = (
            "regenerate_recon_draft"
            if session.recon_step.effective_rule_json
            else "generate_recon_draft"
        )
        payload = {
            "request_type": request_type,
            "session_context": {
                "session_id": session.session_id,
                "scheme_name": session.scheme_name,
                "biz_goal": session.biz_goal,
            },
            "target_context": {
                "sample_datasets": self._dataset_payload(session.sample_datasets),
            },
            "rule_context": {
                "user_instruction_text": (user_message or "").strip(),
                "previous_effective_rule_json": session.recon_step.effective_rule_json,
                "previous_trial_feedback": session.recon_step.trial_result,
                "previous_validation_errors": session.recon_step.validation_result,
            },
        }
        return (
            "你是 Tally 财务 AI 的数据对账逻辑 JSON 单次生成器。\n"
            "你只负责返回一个 JSON 对象，不要输出 markdown，不要输出解释。\n"
            "后端会根据 effective_rule_json 自己渲染中文说明，所以你不要输出 draft_text。\n"
            "target_context 中会提供 business_name、field_label_map、fields 和 display_with_raw（如 订单金额(order_amount)）。\n"
            "这些字段仅用于理解业务语义，不能作为 JSON 字段名直接写入。\n"
            "如果用户当前编辑说明与现有 recon 引擎能力冲突，优先保证 JSON 合法，并把冲突写入 unsupported_points。\n"
            "如果上一轮试跑或校验失败，优先根据 previous_trial_feedback 和 previous_validation_errors 修正 JSON。\n"
            "返回 JSON 顶层字段固定为：effective_rule_json、assumptions、change_summary、unsupported_points。\n"
            "effective_rule_json 必须是当前 recon 引擎可接受的完整规则对象，且 source_file.table_name 固定为 left_recon_ready，"
            "target_file.table_name 固定为 right_recon_ready。\n\n"
            "关键约束：effective_rule_json 中匹配字段、金额字段等必须引用 raw_name，禁止输出中文字段名。\n\n"
            "以下 reference 文档用于约束输出，禁止偏离：\n"
            f"{self._reference_bundle('recon')}\n\n"
            "本轮结构化输入如下：\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2, default=self._json_default)}\n\n"
            "请直接输出 JSON。"
        )

    def _dataset_payload(self, datasets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []
        for dataset in datasets:
            if not isinstance(dataset, dict):
                continue
            payload.append(build_prompt_dataset_payload(dataset))
        return payload

    def _normalize_envelope(self, parsed: dict[str, Any], *, stage: Stage) -> SingleShotGenerationResult:
        if not isinstance(parsed, dict):
            raise ValueError("模型未返回 JSON 对象")
        rule_json = parsed.get("effective_rule_json")
        if not isinstance(rule_json, dict):
            for key in ("proc_rule_json", "recon_rule_json", "rule", "proc", "recon"):
                nested = parsed.get(key)
                if isinstance(nested, dict):
                    rule_json = nested
                    break
        if not isinstance(rule_json, dict) or not rule_json:
            if stage == "proc" and isinstance(parsed.get("steps"), list):
                rule_json = parsed
            elif stage == "recon" and isinstance(parsed.get("rules"), list):
                rule_json = parsed
            else:
                raise ValueError("模型未返回有效的 effective_rule_json")
        return SingleShotGenerationResult(
            effective_rule_json=rule_json,
            assumptions=self._to_string_list(parsed.get("assumptions")),
            change_summary=self._to_string_list(parsed.get("change_summary")),
            unsupported_points=self._to_string_list(parsed.get("unsupported_points")),
            raw_response=parsed,
        )

    def _parse_json_content(self, content: str) -> dict[str, Any]:
        text = content.strip()
        if not text:
            raise ValueError("模型未返回内容")
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = self._decode_first_json_object(text)
        if not isinstance(parsed, dict):
            raise ValueError("模型返回内容不是 JSON 对象")
        return parsed

    def _decode_first_json_object(self, text: str) -> dict[str, Any]:
        decoder = json.JSONDecoder()
        for start in [idx for idx, char in enumerate(text) if char == "{"]:
            try:
                value, _ = decoder.raw_decode(text[start:])
                if isinstance(value, dict):
                    return value
            except Exception:
                continue
        raise ValueError("返回内容中未找到可解析的 JSON 对象")

    def _to_string_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        result: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if text:
                result.append(text)
        return result

    @lru_cache(maxsize=2)
    def _reference_bundle(self, stage: Stage) -> str:
        if stage == "proc":
            references = [
                self._skill_root / "proc-config" / "references" / "input-contract.md",
                self._skill_root / "proc-config" / "references" / "proc-dsl-guardrails.md",
                self._skill_root / "proc-config" / "references" / "proc-examples.md",
            ]
        else:
            references = [
                self._skill_root / "recon-config" / "references" / "input-contract.md",
                self._skill_root / "recon-config" / "references" / "recon-dsl-guardrails.md",
                self._skill_root / "recon-config" / "references" / "recon-examples.md",
            ]
        sections: list[str] = []
        for path in references:
            sections.append(f"## {path.name}\n{path.read_text(encoding='utf-8').strip()}")
        return "\n\n".join(sections)

    def _json_default(self, value: Any) -> str:
        if hasattr(value, "isoformat"):
            try:
                return value.isoformat()
            except Exception:  # noqa: BLE001
                return str(value)
        return str(value)

    def _format_exception(self, exc: Exception) -> str:
        message = str(exc or "").strip()
        if message:
            return message
        return exc.__class__.__name__
