"""Bounded skill runner powered by a DeepAgent-style prompt wrapper.

This module centralises all prompt construction for scheme design skills so
that both proc/recon generation share the same contract defined in
`docs/recon-scheme-ai-skill-contract.md`.

The implementation deliberately keeps the surface minimal:

* Build a structured payload (session context, target context, rule context).
* Attach the relevant skill/reference documents so the model always sees the
  latest DSL guardrails.
* Force the model to respond with a strict JSON object that mirrors the
  contract (draft text + candidate rule JSON + metadata fields).
* Parse/validate the response before handing it back to the executor.

In the future this module can be swapped to LangGraph's built-in
`create_deep_agent` without touching the rest of the codebase. For now we keep
the dependency footprint small and rely on the existing LLM helper.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

from config import PROJECT_ROOT
from models import SchemeDesignSession
from utils.llm import get_llm


SkillRequestType = Literal[
    "generate_proc_draft",
    "regenerate_proc_draft",
    "generate_recon_draft",
    "regenerate_recon_draft",
]


@dataclass(slots=True)
class SkillGenerationResult:
    draft_text: str
    candidate_rule_json: dict[str, Any]
    assumptions: list[str]
    change_summary: list[str]
    unsupported_points: list[str]
    raw_response: dict[str, Any]


class DeepAgentSkillRunner:
    """Encapsulates prompt building + JSON parsing for scheme design skills."""

    def __init__(self) -> None:
        root = PROJECT_ROOT
        self._proc_references = self._load_references(
            (
                root / "finance-agents" / "data-agent" / "skills" / "proc-config" / "SKILL.md",
                root / "finance-skills" / "generate-proc-rule-json" / "SKILL.md",
            )
        )
        self._recon_references = self._load_references(
            (
                root / "finance-agents" / "data-agent" / "skills" / "recon-config" / "SKILL.md",
                root / "finance-skills" / "generate-recon-rule-json" / "SKILL.md",
            )
        )

    async def generate_proc_draft(
        self,
        *,
        session: SchemeDesignSession,
        user_message: str,
    ) -> SkillGenerationResult:
        request_type: SkillRequestType = (
            "regenerate_proc_draft"
            if session.proc_step.normalized_rule_json or session.proc_step.candidate_rule_json
            else "generate_proc_draft"
        )
        payload = self._build_payload(
            session=session,
            user_message=user_message,
            request_type=request_type,
            stage="proc",
        )
        prompt = self._build_prompt(
            stage="proc",
            references=self._proc_references,
            payload=payload,
        )
        response = await self._invoke_llm(prompt)
        return self._parse_skill_response(response, stage="proc")

    async def generate_recon_draft(
        self,
        *,
        session: SchemeDesignSession,
        user_message: str,
    ) -> SkillGenerationResult:
        request_type: SkillRequestType = (
            "regenerate_recon_draft"
            if session.recon_step.normalized_rule_json or session.recon_step.candidate_rule_json
            else "generate_recon_draft"
        )
        payload = self._build_payload(
            session=session,
            user_message=user_message,
            request_type=request_type,
            stage="recon",
        )
        prompt = self._build_prompt(
            stage="recon",
            references=self._recon_references,
            payload=payload,
        )
        response = await self._invoke_llm(prompt)
        return self._parse_skill_response(response, stage="recon")

    def _build_payload(
        self,
        *,
        session: SchemeDesignSession,
        user_message: str,
        request_type: SkillRequestType,
        stage: Literal["proc", "recon"],
    ) -> dict[str, Any]:
        target_context = {
            "left_sources": session.target_step.left_datasets,
            "right_sources": session.target_step.right_datasets,
            "left_description": session.target_step.left_description,
            "right_description": session.target_step.right_description,
            "sample_datasets": session.sample_datasets,
        }

        if stage == "proc":
            previous_rule = session.proc_step.normalized_rule_json or session.proc_step.candidate_rule_json
            previous_trial = session.proc_step.trial_result
            validation_errors = session.proc_step.validation_result
        else:
            previous_rule = session.recon_step.normalized_rule_json or session.recon_step.candidate_rule_json
            previous_trial = session.recon_step.trial_result
            validation_errors = session.recon_step.validation_result

        rule_context = {
            "user_instruction_text": user_message,
            "previous_candidate_rule_json": previous_rule,
            "previous_trial_feedback": previous_trial,
            "previous_validation_errors": validation_errors,
        }

        payload = {
            "request_type": request_type,
            "session_context": {
                "session_id": session.session_id,
                "scheme_name": session.scheme_name,
                "biz_goal": session.biz_goal,
            },
            "target_context": target_context,
            "rule_context": rule_context,
            "reference_bundle": {
                "skill_docs": [
                    "finance-agents/data-agent/skills/proc-config/SKILL.md"
                    if stage == "proc"
                    else "finance-agents/data-agent/skills/recon-config/SKILL.md",
                    "finance-skills/generate-proc-rule-json/SKILL.md"
                    if stage == "proc"
                    else "finance-skills/generate-recon-rule-json/SKILL.md",
                ],
            },
        }
        return payload

    def _build_prompt(
        self,
        *,
        stage: Literal["proc", "recon"],
        references: str,
        payload: dict[str, Any],
    ) -> str:
        response_contract = (
            "{\n"
            '  "success": true,\n'
            '  "request_type": "generate_proc_draft",\n'
            '  "draft_text_candidate": "",\n'
            '  "candidate_rule_json": { },\n'
            '  "unsupported_points": [],\n'
            '  "assumptions": [],\n'
            '  "change_summary": [],\n'
            '  "compatibility_report": {"status": "unknown", "issues": []}\n'
            "}"
        )
        stage_label = "数据整理 (proc)" if stage == "proc" else "对账逻辑 (recon)"
        return (
            f"你是 Tally 财务 AI DeepAgent 的 {stage_label} skill。\n"
            "请严格按照输入 payload 和参考文档生成草稿。\n"
            "输出必须是一个 JSON 对象，键名固定，且 `candidate_rule_json` 必须满足当前 DSL。\n"
            "禁止输出多余的自然语言。\n"
            "\n"
            "# Skill References\n"
            f"{references}\n\n"
            "# 输入 Payload\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2, default=self._json_default)}\n\n"
            "# 输出格式\n"
            f"返回与下列结构一致的 JSON：\n{response_contract}\n"
        )

    async def _invoke_llm(self, prompt: str) -> dict[str, Any]:
        llm = get_llm(temperature=0.1)
        response = await asyncio.wait_for(asyncio.to_thread(llm.invoke, prompt), timeout=120)
        content = getattr(response, "content", "")
        if isinstance(content, list):
            content = "".join(str(getattr(item, "text", item)) for item in content)
        text = str(content or "").strip()
        if not text:
            raise ValueError("LLM 未返回有效内容")
        return self._parse_json_output(text)

    def _parse_skill_response(self, payload: dict[str, Any], *, stage: Literal["proc", "recon"]) -> SkillGenerationResult:
        draft_text = str(payload.get("draft_text_candidate") or "").strip()
        candidate = payload.get("candidate_rule_json")
        if not isinstance(candidate, dict):
            raise ValueError("skill 返回的 candidate_rule_json 不是对象")
        assumptions = self._ensure_list_of_str(payload.get("assumptions"))
        change_summary = self._ensure_list_of_str(payload.get("change_summary"))
        unsupported = self._ensure_list_of_str(payload.get("unsupported_points"))
        if not draft_text:
            draft_text = "基于最新 JSON 自动生成的配置说明。"
        return SkillGenerationResult(
            draft_text=draft_text,
            candidate_rule_json=candidate,
            assumptions=assumptions,
            change_summary=change_summary,
            unsupported_points=unsupported,
            raw_response=payload,
        )

    def _parse_json_output(self, content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            text = text.split("```", 2)[1]
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        decoder = json.JSONDecoder()
        for idx, ch in enumerate(text):
            if ch != "{":
                continue
            try:
                value, _ = decoder.raw_decode(text[idx:])
                if isinstance(value, dict):
                    return value
            except Exception:
                continue
        raise ValueError("未能解析 skill 返回内容中的 JSON")

    def _load_references(self, paths: tuple[Path, ...]) -> str:
        chunks: list[str] = []
        for path in paths:
            try:
                text = path.read_text(encoding="utf-8").strip()
            except FileNotFoundError:
                text = f"(missing reference: {path})"
            chunks.append(f"## {path.relative_to(PROJECT_ROOT)}\n{text}")
        return "\n\n".join(chunks)

    def _ensure_list_of_str(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        result: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if text:
                result.append(text)
        return result

    def _json_default(self, value: Any) -> Any:
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        return str(value)


def get_skill_runner() -> DeepAgentSkillRunner:
    """Singleton accessor used by the executor."""

    global _skill_runner
    try:
        runner = _skill_runner
    except NameError:  # pragma: no cover - first access branch
        runner = None
    if runner is None:
        runner = DeepAgentSkillRunner()
        _skill_runner = runner
    return runner

