"""DeepAgent-backed skill runner for scheme design.

This module uses LangChain Deep Agents' ``create_deep_agent`` API with a
``StateBackend`` so proc/recon skill assets are loaded through the official
progressive-disclosure path instead of being stuffed into a single prompt.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from time import perf_counter
from typing import Any, Literal

from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import AliasChoices, BaseModel, Field

from config import PROJECT_ROOT
from models import SchemeDesignSession
from utils.llm import get_available_llm_providers, get_llm


SkillRequestType = Literal[
    "generate_proc_draft",
    "regenerate_proc_draft",
    "generate_recon_draft",
    "regenerate_recon_draft",
]
SkillStage = Literal["proc", "recon"]

_RUNTIME_SKILLS_ROOT = "/skills"
logger = logging.getLogger(__name__)


def _extract_semantic_profile(dataset: dict[str, Any]) -> dict[str, Any]:
    direct = dataset.get("semantic_profile")
    if isinstance(direct, dict):
        return direct
    for key in ("meta", "metadata", "dataset_meta"):
        container = dataset.get(key)
        if not isinstance(container, dict):
            continue
        profile = container.get("semantic_profile")
        if isinstance(profile, dict):
            return profile
    return {}


def _normalize_field_label_map(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    result: dict[str, str] = {}
    for raw_key, raw_value in raw.items():
        key = str(raw_key or "").strip()
        if not key:
            continue
        value = str(raw_value or "").strip()
        result[key] = value or key
    return result


def _infer_raw_fields(dataset: dict[str, Any]) -> list[str]:
    field_names: list[str] = []
    schema_summary = dataset.get("schema_summary")
    if isinstance(schema_summary, dict):
        columns = schema_summary.get("columns")
        if isinstance(columns, list):
            for column in columns:
                if not isinstance(column, dict):
                    continue
                name = str(column.get("name") or column.get("column_name") or "").strip()
                if name and name not in field_names:
                    field_names.append(name)
        else:
            for key in schema_summary.keys():
                name = str(key or "").strip()
                if name and name != "columns" and name not in field_names:
                    field_names.append(name)
    rows = [row for row in list(dataset.get("sample_rows") or []) if isinstance(row, dict)]
    for row in rows[:3]:
        for key in row.keys():
            name = str(key or "").strip()
            if name and name not in field_names:
                field_names.append(name)
    return field_names


def _field_display(raw_name: str, field_label_map: dict[str, str]) -> str:
    raw = str(raw_name or "").strip()
    if not raw:
        return ""
    display = str(field_label_map.get(raw) or "").strip()
    if display and display != raw:
        return f"{display}({raw})"
    return raw


def _build_prompt_dataset_payload(dataset: dict[str, Any]) -> dict[str, Any]:
    resolved = dict(dataset)
    profile = _extract_semantic_profile(resolved)
    field_label_map = _normalize_field_label_map(profile.get("field_label_map"))
    field_label_map.update(_normalize_field_label_map(resolved.get("field_label_map")))
    for raw_name in _infer_raw_fields(resolved):
        field_label_map.setdefault(raw_name, raw_name)
    sample_rows = [row for row in list(resolved.get("sample_rows") or []) if isinstance(row, dict)][:3]
    fields = resolved.get("fields")
    if not isinstance(fields, list):
        fields = resolved.get("semantic_fields")
    if not isinstance(fields, list):
        fields = profile.get("fields") if isinstance(profile.get("fields"), list) else []
    if isinstance(fields, list):
        for item in fields:
            if not isinstance(item, dict):
                continue
            raw_name = str(
                item.get("raw_name")
                or item.get("field_name")
                or item.get("name")
                or ""
            ).strip()
            if not raw_name:
                continue
            display_name = str(
                item.get("display_name")
                or item.get("display_name_zh")
                or item.get("label")
                or field_label_map.get(raw_name)
                or raw_name
            ).strip() or raw_name
            field_label_map[raw_name] = display_name
    field_display_pairs = [
        {
            "raw_name": raw_name,
            "display_name": field_label_map.get(raw_name, raw_name),
            "display_with_raw": _field_display(raw_name, field_label_map),
        }
        for raw_name in _infer_raw_fields(resolved)
    ]
    sample_rows_with_display_fields = [
        {_field_display(str(key), field_label_map): value for key, value in row.items()}
        for row in sample_rows
    ]
    return {
        "side": str(resolved.get("side") or "").strip(),
        "business_name": str(
            resolved.get("business_name")
            or profile.get("business_name")
            or resolved.get("dataset_name")
            or resolved.get("table_name")
            or ""
        ).strip(),
        "dataset_name": str(resolved.get("dataset_name") or "").strip(),
        "table_name": str(resolved.get("table_name") or "").strip(),
        "resource_key": str(resolved.get("resource_key") or "").strip(),
        "description": str(resolved.get("description") or "").strip(),
        "schema_summary": resolved.get("schema_summary") if isinstance(resolved.get("schema_summary"), dict) else {},
        "sample_rows": sample_rows,
        "field_label_map": field_label_map,
        "fields": fields,
        "field_display_pairs": field_display_pairs,
        "sample_rows_with_display_fields": sample_rows_with_display_fields,
    }


def _tool_name(tool: Any) -> str | None:
    if isinstance(tool, dict):
        name = tool.get("name")
        return name if isinstance(name, str) else None
    name = getattr(tool, "name", None)
    return name if isinstance(name, str) else None


class _ReadOnlySkillToolFilterMiddleware(AgentMiddleware[Any, Any, Any]):
    """Limit DeepAgent to the minimum tool surface needed for skill execution."""

    _allowed_tools = frozenset({"read_file"})

    def _filter_request(self, request: Any) -> Any:
        filtered = [
            tool
            for tool in getattr(request, "tools", []) or []
            if _tool_name(tool) in self._allowed_tools
        ]
        return request.override(tools=filtered)

    def wrap_model_call(self, request: Any, handler: Any) -> Any:
        return handler(self._filter_request(request))

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        return await handler(self._filter_request(request))


@dataclass(slots=True)
class SkillGenerationResult:
    draft_text: str
    effective_rule_json: dict[str, Any]
    assumptions: list[str]
    change_summary: list[str]
    unsupported_points: list[str]
    raw_response: dict[str, Any]
    provider: str = ""
    provider_fallback_errors: list[str] = field(default_factory=list)


class CompatibilityReport(BaseModel):
    status: str = "unknown"
    issues: list[str] = Field(default_factory=list)


class SkillResponseEnvelope(BaseModel):
    success: bool = True
    request_type: str
    draft_text: str = Field(
        default="",
        validation_alias=AliasChoices("draft_text", "draft_text_candidate"),
    )
    effective_rule_json: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("effective_rule_json", "candidate_rule_json"),
    )
    rule_summary: str = ""
    unsupported_points: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    change_summary: list[str] = Field(default_factory=list)
    compatibility_report: CompatibilityReport = Field(default_factory=CompatibilityReport)


class ProcSkillResponseEnvelope(SkillResponseEnvelope):
    request_type: Literal["generate_proc_draft", "regenerate_proc_draft"]


class ReconSkillResponseEnvelope(SkillResponseEnvelope):
    request_type: Literal["generate_recon_draft", "regenerate_recon_draft"]


class DeepAgentSkillRunner:
    """Generate proc/recon drafts through ``create_deep_agent``."""

    def __init__(self) -> None:
        self._skill_root = PROJECT_ROOT / "finance-agents" / "data-agent" / "skills"
        self._backend = StateBackend()
        self._checkpointer = InMemorySaver()
        self._provider_order = get_available_llm_providers()
        if not self._provider_order:
            raise ValueError("未配置任何可用的 LLM provider，无法初始化 DeepAgent skill runner")
        self._disabled_providers: dict[str, str] = {}
        self._proc_files = self._load_skill_files("proc-config")
        self._recon_files = self._load_skill_files("recon-config")
        self._agents: dict[tuple[SkillStage, str], Any] = {}

    async def generate_proc_draft(
        self,
        *,
        session: SchemeDesignSession,
        user_message: str,
    ) -> SkillGenerationResult:
        request_type: SkillRequestType = (
            "regenerate_proc_draft"
            if session.proc_step.effective_rule_json
            else "generate_proc_draft"
        )
        payload = self._build_payload(
            session=session,
            user_message=user_message,
            request_type=request_type,
            stage="proc",
        )
        result = await self._invoke_agent(
            stage="proc",
            session_id=session.session_id,
            payload=payload,
        )
        return self._parse_skill_response(result, stage="proc")

    async def generate_recon_draft(
        self,
        *,
        session: SchemeDesignSession,
        user_message: str,
    ) -> SkillGenerationResult:
        request_type: SkillRequestType = (
            "regenerate_recon_draft"
            if session.recon_step.effective_rule_json
            else "generate_recon_draft"
        )
        payload = self._build_payload(
            session=session,
            user_message=user_message,
            request_type=request_type,
            stage="recon",
        )
        result = await self._invoke_agent(
            stage="recon",
            session_id=session.session_id,
            payload=payload,
        )
        return self._parse_skill_response(result, stage="recon")

    def _build_agent(
        self,
        *,
        stage: SkillStage,
        provider: str,
        response_model: type[SkillResponseEnvelope],
    ) -> Any:
        stage_label = "数据整理" if stage == "proc" else "数据对账逻辑"
        skill_name = self._skill_name(stage)
        return create_deep_agent(
            model=get_llm(provider=provider, temperature=0.1),
            tools=[],
            system_prompt=(
                f"你是 Tally 财务 AI 的{stage_label}配置代理。"
                f"当前只能处理 `{skill_name}` skill 对应的任务。"
                "必须先阅读 skill 入口文件，再按需阅读 references。"
                "不要列目录、不要搜索、不要写文件、不要执行命令。"
                "你只需要使用 `read_file` 读取明确给出的 skill/reference 路径。"
                "默认先读取 SKILL.md；若其中信息已足够，就直接输出。"
                "只有缺少 DSL 约束或示例时，才继续读取 reference 文件。"
                "目标是在尽量少的工具调用与模型轮次内，返回最终结构化结果。"
                "最终回复必须是一个 JSON 对象，不要 Markdown，不要解释性前后缀。"
            ),
            middleware=[_ReadOnlySkillToolFilterMiddleware()],
            skills=[f"{_RUNTIME_SKILLS_ROOT}/"],
            backend=self._backend,
            checkpointer=self._checkpointer,
            response_format=response_model,
            name=f"tally-scheme-design-{stage}-{provider}",
        )

    def _load_skill_files(self, skill_name: str) -> dict[str, dict[str, Any]]:
        skill_dir = self._skill_root / skill_name
        if not skill_dir.exists():
            raise FileNotFoundError(f"Skill 目录不存在: {skill_dir}")

        files: dict[str, dict[str, Any]] = {}
        for file_path in sorted(skill_dir.rglob("*")):
            if not file_path.is_file():
                continue
            runtime_path = f"{_RUNTIME_SKILLS_ROOT}/{skill_name}/{file_path.relative_to(skill_dir).as_posix()}"
            files[runtime_path] = self._build_file_payload(file_path.read_text(encoding="utf-8"))
        return files

    def _build_payload(
        self,
        *,
        session: SchemeDesignSession,
        user_message: str,
        request_type: SkillRequestType,
        stage: SkillStage,
    ) -> dict[str, Any]:
        if stage == "proc":
            previous_rule = session.proc_step.effective_rule_json
            previous_trial = session.proc_step.trial_result
            validation_errors = session.proc_step.validation_result
        else:
            previous_rule = session.recon_step.effective_rule_json
            previous_trial = session.recon_step.trial_result
            validation_errors = session.recon_step.validation_result

        return {
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
                "user_instruction_text": user_message,
                "previous_effective_rule_json": previous_rule,
                "previous_trial_feedback": previous_trial,
                "previous_validation_errors": validation_errors,
            },
            "reference_bundle": {
                "skill_entry_path": self._skill_entry_path(stage),
                "reference_paths": self._reference_paths(stage),
            },
        }

    async def _invoke_agent(
        self,
        *,
        stage: SkillStage,
        session_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        skill_name = self._skill_name(stage)
        files = self._proc_files if stage == "proc" else self._recon_files
        response_contract = {
            "success": True,
            "request_type": "generate_proc_draft" if stage == "proc" else "generate_recon_draft",
            "draft_text": "给用户编辑的中文说明",
            "effective_rule_json": {"rule": "真实规则 JSON"},
            "assumptions": ["可选假设"],
            "change_summary": ["本次调整摘要"],
            "unsupported_points": ["超出 DSL 的点则写这里"],
            "compatibility_report": {
                "status": "unknown",
                "issues": [],
            },
        }
        user_message = (
            f"请处理当前 Tally 方案配置任务，并显式使用 `{skill_name}` skill。\n"
            f"先读取 `{self._skill_entry_path(stage)}`，再按需读取 `references/` 下文件。\n"
            "不要猜测 DSL，不要写文件，不要执行命令。\n"
            "最终回复必须严格是一个 JSON 对象，字段名固定为 success/request_type/draft_text/effective_rule_json/"
            "assumptions/change_summary/unsupported_points/compatibility_report。\n"
            "不要输出 ```json，不要输出任何额外解释。\n"
            f"返回格式示例：{json.dumps(response_contract, ensure_ascii=False)}\n"
            "下面是本轮结构化输入，请基于它返回最终结构化结果。\n"
            "注意：target_context 中的中文显示字段（display_with_raw / business_name）只用于语义理解，"
            "effective_rule_json 中字段名必须使用 raw_name，不允许输出中文字段名。\n"
            f"```json\n{json.dumps(payload, ensure_ascii=False, indent=2, default=self._json_default)}\n```"
        )
        errors: list[str] = []
        active_providers = [provider for provider in self._provider_order if provider not in self._disabled_providers]
        if not active_providers:
            disabled_details = " | ".join(
                f"{provider}: {reason}" for provider, reason in self._disabled_providers.items()
            )
            raise RuntimeError("DeepAgent 当前无可用 provider：" + disabled_details)

        for index, provider in enumerate(active_providers):
            response_model: type[SkillResponseEnvelope]
            response_model = ProcSkillResponseEnvelope if stage == "proc" else ReconSkillResponseEnvelope
            agent = self._get_or_create_agent(
                stage=stage,
                provider=provider,
                response_model=response_model,
            )
            thread_id = f"scheme-design::{stage}::{provider}::{session_id}::{uuid.uuid4().hex}"
            started_at = perf_counter()
            try:
                logger.info(
                    "[scheme_design][%s] DeepAgent start provider=%s session_id=%s thread_id=%s",
                    stage,
                    provider,
                    session_id,
                    thread_id,
                )
                result = await agent.ainvoke(
                    {
                        "messages": [HumanMessage(content=user_message)],
                        "files": files,
                    },
                    config={"configurable": {"thread_id": thread_id}},
                )
                parsed = self._coerce_agent_output(result)
                parsed["_skill_provider"] = provider
                logger.info(
                    "[scheme_design][%s] DeepAgent finished provider=%s session_id=%s elapsed=%.2fs",
                    stage,
                    provider,
                    session_id,
                    perf_counter() - started_at,
                )
                if errors:
                    parsed["_skill_provider_fallback_errors"] = list(errors)
                    logger.warning(
                        "[scheme_design][%s] DeepAgent provider fallback -> %s, previous_errors=%s",
                        stage,
                        provider,
                        errors,
                    )
                return parsed
            except Exception as exc:  # noqa: BLE001
                error_text = f"{provider}: {exc}"
                errors.append(error_text)
                logger.warning(
                    "[scheme_design][%s] DeepAgent provider failed (%s/%s) after %.2fs: %s",
                    stage,
                    index + 1,
                    len(active_providers),
                    perf_counter() - started_at,
                    error_text,
                )
                if self._is_terminal_provider_error(exc):
                    self._disabled_providers[provider] = str(exc)
                continue

        raise RuntimeError("DeepAgent 全部 provider 调用失败：" + " | ".join(errors))

    def _get_or_create_agent(
        self,
        *,
        stage: SkillStage,
        provider: str,
        response_model: type[SkillResponseEnvelope] | None = None,
    ) -> Any:
        key = (stage, provider)
        agent = self._agents.get(key)
        if agent is None:
            if response_model is None:
                raise ValueError("response_model 不能为空")
            agent = self._build_agent(stage=stage, provider=provider, response_model=response_model)
            self._agents[key] = agent
        return agent

    def _coerce_agent_output(self, result: Any) -> dict[str, Any]:
        if isinstance(result, dict):
            structured = result.get("structured_response")
            if isinstance(structured, BaseModel):
                return structured.model_dump()
            if isinstance(structured, dict):
                return structured
            messages = result.get("messages")
            parsed = self._parse_messages_for_json(messages)
            if parsed:
                return parsed
        if isinstance(result, BaseModel):
            return result.model_dump()
        raise ValueError("DeepAgent 未返回可解析的结构化结果")

    def _parse_messages_for_json(self, messages: Any) -> dict[str, Any] | None:
        if not isinstance(messages, list):
            return None
        for message in reversed(messages):
            if not isinstance(message, BaseMessage):
                continue
            text = self._message_to_text(message)
            if not text:
                continue
            try:
                return self._parse_json_output(text)
            except ValueError:
                continue
        return None

    def _parse_skill_response(self, payload: dict[str, Any], *, stage: SkillStage) -> SkillGenerationResult:
        envelope_type: type[SkillResponseEnvelope]
        envelope_type = ProcSkillResponseEnvelope if stage == "proc" else ReconSkillResponseEnvelope
        envelope = envelope_type.model_validate(payload)
        draft_text = str(envelope.draft_text or "").strip()
        effective_rule_json = envelope.effective_rule_json
        if not effective_rule_json:
            raise ValueError("skill 返回的 effective_rule_json 为空")
        return SkillGenerationResult(
            draft_text=draft_text or "AI 已基于当前 JSON 自动生成说明。",
            effective_rule_json=effective_rule_json,
            assumptions=list(envelope.assumptions),
            change_summary=list(envelope.change_summary),
            unsupported_points=list(envelope.unsupported_points),
            raw_response=payload,
            provider=str(payload.get("_skill_provider") or ""),
            provider_fallback_errors=self._ensure_list_of_str(payload.get("_skill_provider_fallback_errors")),
        )

    def _message_to_text(self, message: BaseMessage) -> str:
        content = getattr(message, "content", "")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if isinstance(item, dict):
                    text = item.get("text")
                    if text:
                        parts.append(str(text))
            return "\n".join(part.strip() for part in parts if part and str(part).strip()).strip()
        return str(content or "").strip()

    def _parse_json_output(self, content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        decoder = json.JSONDecoder()
        for index, char in enumerate(text):
            if char != "{":
                continue
            try:
                candidate, _ = decoder.raw_decode(text[index:])
            except Exception:
                continue
            if isinstance(candidate, dict):
                return candidate
        raise ValueError("未能解析 DeepAgent 返回内容中的 JSON")

    def _ensure_list_of_str(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        result: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if text:
                result.append(text)
        return result

    def _skill_name(self, stage: SkillStage) -> str:
        return "proc-config" if stage == "proc" else "recon-config"

    def _skill_entry_path(self, stage: SkillStage) -> str:
        return f"{_RUNTIME_SKILLS_ROOT}/{self._skill_name(stage)}/SKILL.md"

    def _reference_paths(self, stage: SkillStage) -> list[str]:
        skill_name = self._skill_name(stage)
        references_dir = self._skill_root / skill_name / "references"
        return [
            f"{_RUNTIME_SKILLS_ROOT}/{skill_name}/references/{path.name}"
            for path in sorted(references_dir.glob("*"))
            if path.is_file()
        ]

    def _build_file_payload(self, content: str) -> dict[str, Any]:
        timestamp = datetime.now(UTC).isoformat()
        return {
            "content": content,
            "encoding": "utf-8",
            "created_at": timestamp,
            "modified_at": timestamp,
        }

    def _json_default(self, value: Any) -> Any:
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        return str(value)

    def _dataset_payload(self, datasets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []
        for dataset in datasets:
            if not isinstance(dataset, dict):
                continue
            payload.append(_build_prompt_dataset_payload(dataset))
        return payload

    def _is_terminal_provider_error(self, exc: Exception) -> bool:
        message = str(exc or "").lower()
        terminal_markers = (
            "incorrect api key",
            "invalid api key",
            "invalid_api_key",
            "insufficient balance",
            "quota",
            "authentication",
            "unauthorized",
            "401",
            "402",
        )
        return any(marker in message for marker in terminal_markers)


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
