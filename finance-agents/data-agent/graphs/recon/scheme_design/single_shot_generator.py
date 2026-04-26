from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from models import SchemeDesignSession
from utils.llm import get_available_llm_providers, get_llm

from .semantic_utils import build_prompt_dataset_payload


logger = logging.getLogger(__name__)

Stage = Literal["proc", "recon"]

_PROC_REFERENCE_BUNDLE = """
- 只允许生成一个完整 proc steps DSL JSON，不要输出 markdown 或解释。
- 顶层必须包含 role_desc、file_rule_code、steps。
- steps 只允许 create_schema 和 write_dataset，两侧输出表固定为 left_recon_ready / right_recon_ready。
- 所有 source.field、match.keys.field 必须来自输入数据集 field_display_pairs/raw_name，禁止发明字段。
- 标准输出字段固定为 biz_key、amount、biz_date、source_name。
- biz_date 只能映射日期/时间字段；若找不到明确日期字段，使用 formula 输出空字符串。
- source_name 必须输出固定中文来源名，不要引用源表字段。
- sources[].table 只能使用 source_table_identifier。
- write_dataset 需要 row_write_mode，推荐 upsert。
""".strip()

_RECON_REFERENCE_BUNDLE = """
- 只允许生成一个完整 recon JSON，不要输出 markdown 或解释。
- source_file.table_name 固定为 left_recon_ready，target_file.table_name 固定为 right_recon_ready。
- 匹配字段、金额字段必须来自整理后样例中的 raw_name，禁止发明字段。
- compare_columns 仅使用 numeric compare_type，tolerance 必须是数字。
- output.sheets 必须包含 summary、source_only、target_only、matched_with_diff。
""".strip()


@dataclass(slots=True)
class SingleShotGenerationResult:
    effective_rule_json: dict[str, Any]
    draft_text: str = ""
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
        self._provider = self._provider_order[0]

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
        provider = self._provider
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
            raise RuntimeError(f"{provider}: {formatted_error}") from exc

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
                "sample_datasets": self._dataset_payload(session.sample_datasets),
            },
            "rule_context": {
                "user_instruction_text": (user_message or "").strip(),
                "current_draft_text": str(session.proc_step.draft_text or "").strip(),
                "previous_effective_rule_json": session.proc_step.effective_rule_json,
                "previous_trial_feedback": session.proc_step.trial_result,
                "previous_validation_errors": session.proc_step.validation_result,
            },
        }
        return (
            "你是 Tally 财务 AI 的数据整理 JSON 单次生成器。\n"
            "你只负责返回一个 JSON 对象，不要输出 markdown，不要输出解释。\n"
            "target_context 中会提供 business_name、field_label_map 和 display_with_raw（如 订单金额(order_amount)）。\n"
            "如果用户已经在页面配置了目标输出字段，target_context 还会提供 prepared_output_fields；"
            "你应优先按这些目标输出字段生成 left_recon_ready / right_recon_ready 的结构和 mappings。\n"
            "这些字段仅用于理解业务语义，不能作为 JSON 字段名直接写入。\n"
            "如果 rule_context.current_draft_text 非空，说明用户已经手工修改了整理说明；"
            "本轮必须优先依据这份说明生成 JSON，不能被 previous_effective_rule_json 覆盖。\n"
            "如果用户当前编辑说明与现有 DSL 能力冲突，优先保证 JSON 合法，并把冲突写入 unsupported_points。\n"
            "如果上一轮试跑或校验失败，优先根据 previous_trial_feedback 和 previous_validation_errors 修正 JSON。\n"
            "返回 JSON 顶层字段固定为：effective_rule_json、draft_text、assumptions、change_summary、unsupported_points。\n"
            "effective_rule_json 必须是当前 proc steps DSL 可接受的完整规则对象，且只能输出 left_recon_ready 与 right_recon_ready 两份结果。\n"
            "draft_text 是面向用户的中文配置说明，使用 business_name 和 display_with_raw 中的中文名称，不要出现原始英文字段名或表名，"
            "格式参考：首行【数据整理配置说明】，然后【左侧数据整理】和【右侧数据整理】两节，每节列出关键步骤。\n\n"
            "关键约束：\n"
            "1. effective_rule_json 中所有字段必须使用原始 raw_name（来自 field_label_map 或 sample_rows 的 key），禁止输出中文字段名。\n"
            "2. mappings、match.sources.keys、aggregate 等所有引用源字段的地方，只能使用对应数据集 field_display_pairs 中列出的 raw_name，"
            "禁止引用不在列表中的字段名，previous_effective_rule_json 中的字段名仅供参考结构，不可直接复用。\n"
            "3. biz_date 必须映射到日期类型的字段（字段名含 date/time/日期/时间）。"
            "   若无明确日期字段，改用固定值 formula 输出空字符串，切勿将订单号、金额等非日期字段赋给 biz_date。\n"
            "4. source_name 必须使用 formula 类型输出数据来源的业务名称字符串（中文），expr 必须是带引号的 Python 字符串字面量，"
            "例如 \"expr\": \"'支付宝订单数据'\"（注意 expr 值本身要包含单引号），禁止映射到源表的任意数据库字段。\n\n"
            "生成约束摘要如下，禁止偏离：\n"
            f"{_PROC_REFERENCE_BUNDLE}\n\n"
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
            "target_context 中会提供 business_name、field_label_map 和 display_with_raw（如 订单金额(order_amount)）。\n"
            "这些字段仅用于理解业务语义，不能作为 JSON 字段名直接写入。\n"
            "如果用户当前编辑说明与现有 recon 引擎能力冲突，优先保证 JSON 合法，并把冲突写入 unsupported_points。\n"
            "如果上一轮试跑或校验失败，优先根据 previous_trial_feedback 和 previous_validation_errors 修正 JSON。\n"
            "返回 JSON 顶层字段固定为：effective_rule_json、draft_text、assumptions、change_summary、unsupported_points。\n"
            "effective_rule_json 必须是当前 recon 引擎可接受的完整规则对象，且 source_file.table_name 固定为 left_recon_ready，"
            "target_file.table_name 固定为 right_recon_ready。\n"
            "draft_text 是面向用户的中文对账逻辑说明，使用 display_with_raw 中的中文名称，不要出现原始英文字段名。\n\n"
            "关键约束：effective_rule_json 中匹配字段、金额字段等必须引用 raw_name，禁止输出中文字段名。\n\n"
            "生成约束摘要如下，禁止偏离：\n"
            f"{_RECON_REFERENCE_BUNDLE}\n\n"
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
            draft_text=str(parsed.get("draft_text") or "").strip(),
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
