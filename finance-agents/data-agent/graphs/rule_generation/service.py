"""Service layer for AI rule generation workflows."""

from __future__ import annotations

import logging
import re
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from graphs.rule_generation.common.events import NODE_LABELS, build_event
from graphs.rule_generation.common.llm_json import invoke_llm_json, unwrap_rule_json
from graphs.rule_generation.proc.assertions import assert_proc_output
from graphs.rule_generation.proc.linter import lint_proc_rule
from graphs.rule_generation.proc.prompts import (
    build_proc_generation_prompt,
    build_proc_repair_prompt,
    build_understanding_prompt,
)
from graphs.rule_generation.proc.rule_builder import build_fallback_proc_rule
from graphs.rule_generation.proc.sample_runner import run_proc_sample

logger = logging.getLogger(__name__)


class RuleGenerationService:
    """Runs single-side proc rule generation with deterministic validation gates."""

    async def run_proc_side(self, *, auth_token: str, payload: dict[str, Any]) -> dict[str, Any]:
        events: list[dict[str, Any]] = []
        async for event in self.stream_proc_side(auth_token=auth_token, payload=payload):
            events.append(event)
        for event in reversed(events):
            if event.get("event") in {"graph_completed", "needs_user_input", "graph_failed"}:
                return event
        return {"status": "failed", "error": "rule_generation 未返回最终状态", "events": events}

    async def run_proc(self, *, auth_token: str, payload: dict[str, Any]) -> dict[str, Any]:
        events: list[dict[str, Any]] = []
        async for event in self.stream_proc(auth_token=auth_token, payload=payload):
            events.append(event)
        for event in reversed(events):
            if event.get("event") in {"graph_completed", "needs_user_input", "graph_failed"}:
                return event
        return {"status": "failed", "error": "rule_generation 未返回最终状态", "events": events}

    async def stream_proc(
        self,
        *,
        auth_token: str,
        payload: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        target_tables = [str(item).strip() for item in list(payload.get("target_tables") or []) if str(item).strip()]
        generic_payload = {
            **payload,
            "mode": "generic_proc",
            "side": "generic",
            "target_table": str(payload.get("target_table") or (target_tables[0] if target_tables else "")).strip(),
            "target_tables": target_tables,
        }
        async for event in self.stream_proc_side(auth_token=auth_token, payload=generic_payload):
            yield event

    async def stream_proc_side(
        self,
        *,
        auth_token: str,
        payload: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        side = str(payload.get("side") or "").strip()
        target_table = str(payload.get("target_table") or "").strip()
        run_id = str(payload.get("run_id") or f"rg_{uuid.uuid4().hex[:12]}")
        context = _initial_context(auth_token=auth_token, payload=payload, run_id=run_id)

        yield build_event(
            "graph_started",
            run_id=run_id,
            side=side,
            target_table=target_table,
            message="开始生成当前侧数据整理规则。",
            status="running",
        )

        try:
            yield self._node_started(context, "prepare_context")
            yield await self._run_node(context, "prepare_context", self._prepare_context)
            if context.get("errors"):
                yield self._graph_failed(context)
                return

            yield self._node_started(context, "understand_rule")
            yield await self._run_node(context, "understand_rule", self._understand_rule)
            if context.get("mode") != "generic_proc":
                yield self._node_started(context, "field_binding")
                yield await self._run_node(context, "field_binding", self._field_binding)
            yield self._node_started(context, "semantic_resolution")
            yield await self._run_node(context, "semantic_resolution", self._semantic_resolution)
            yield self._node_started(context, "ambiguity_gate")
            yield await self._run_node(context, "ambiguity_gate", self._ambiguity_gate)
            if context.get("status") == "needs_user_input":
                yield build_event(
                    "needs_user_input",
                    run_id=run_id,
                    side=side,
                    target_table=target_table,
                    node_code="ambiguity_gate",
                    node_status="needs_user_input",
                    message="规则存在需要确认的业务口径。",
                    status="needs_user_input",
                    phase="ambiguity_gate",
                    questions=context.get("questions") or [],
                    understanding=context.get("understanding") or {},
                    field_bindings=context.get("field_bindings") or [],
                )
                return

            max_retries = int(context.get("max_retries") or 2)
            while True:
                attempt = int(context.get("retry_count") or 0) + 1
                yield self._node_started(context, "generate_or_repair_json", attempt=attempt)
                yield await self._run_node(
                    context,
                    "generate_or_repair_json",
                    self._generate_or_repair_json,
                    attempt=attempt,
                )

                yield self._node_started(context, "lint_json", attempt=attempt)
                yield await self._run_node(context, "lint_json", self._lint_json, attempt=attempt)
                if not _node_success(context.get("lint_result")):
                    if not _can_retry(context, max_retries):
                        yield self._graph_failed(context)
                        return
                    context["retry_count"] = attempt
                    yield self._repair_started(context, reason="规则校验失败，正在修复规则。")
                    continue

                yield self._node_started(context, "build_sample_inputs", attempt=attempt)
                yield await self._run_node(context, "build_sample_inputs", self._build_sample_inputs, attempt=attempt)
                if not _node_success(context.get("sample_input_result")):
                    yield self._graph_failed(context)
                    return
                yield self._node_started(context, "run_sample", attempt=attempt)
                yield await self._run_node(context, "run_sample", self._run_sample, attempt=attempt)
                if not _node_success(context.get("sample_result")):
                    if not _can_retry(context, max_retries):
                        yield self._graph_failed(context)
                        return
                    context["retry_count"] = attempt
                    yield self._repair_started(context, reason="样例执行失败，正在修复规则。")
                    continue

                yield self._node_started(context, "assert_output", attempt=attempt)
                yield await self._run_node(context, "assert_output", self._assert_output, attempt=attempt)
                if not _node_success(context.get("assert_result")):
                    if not _can_retry(context, max_retries):
                        yield self._graph_failed(context)
                        return
                    context["retry_count"] = attempt
                    yield self._repair_started(context, reason="输出断言失败，正在修复规则。")
                    continue
                break

            yield self._node_started(context, "result")
            yield await self._run_node(context, "result", self._result)
            yield self._graph_completed(context)
        except Exception as exc:  # noqa: BLE001
            logger.exception("rule_generation proc side failed")
            context.setdefault("errors", []).append({"message": str(exc), "type": exc.__class__.__name__})
            yield self._graph_failed(context)

    def _node_started(self, context: dict[str, Any], node_code: str, *, attempt: int = 1) -> dict[str, Any]:
        node_name = None
        if node_code == "generate_or_repair_json":
            node_name = "生成规则" if attempt <= 1 else "修复规则"
        return build_event(
            "node_started",
            run_id=context["run_id"],
            side=context["side"],
            target_table=context["target_table"],
            node_code=node_code,
            node_name=node_name,
            node_status="running",
            attempt=attempt,
            message="",
        )

    async def _run_node(
        self,
        context: dict[str, Any],
        node_code: str,
        fn,
        *,
        attempt: int = 1,
    ) -> dict[str, Any]:
        start = time.perf_counter()
        context["phase"] = node_code
        try:
            result = await fn(context) if hasattr(fn, "__call__") else {}
            duration_ms = int((time.perf_counter() - start) * 1000)
            node_failed = result.get("success") is False
            event = build_event(
                "node_failed" if node_failed else "node_completed",
                run_id=context["run_id"],
                side=context["side"],
                target_table=context["target_table"],
                node_code=node_code,
                node_name=_node_display_name(node_code, attempt),
                node_status="failed" if node_failed else "completed",
                attempt=attempt,
                message=str(result.get("message") or _node_completed_message(node_code, attempt)),
                summary=result.get("summary") or {},
                errors=result.get("errors") or [],
                duration_ms=duration_ms,
            )
            context.setdefault("trace", []).append(event)
            return event
        except Exception as exc:  # noqa: BLE001
            duration_ms = int((time.perf_counter() - start) * 1000)
            error = {"node": node_code, "message": str(exc), "type": exc.__class__.__name__}
            context.setdefault("errors", []).append(error)
            return build_event(
                "node_failed",
                run_id=context["run_id"],
                side=context["side"],
                target_table=context["target_table"],
                node_code=node_code,
                node_status="failed",
                attempt=attempt,
                message=str(exc),
                errors=[error],
                duration_ms=duration_ms,
            )

    async def _prepare_context(self, context: dict[str, Any]) -> dict[str, Any]:
        side = context.get("side")
        if context.get("mode") == "generic_proc":
            context["target_tables"] = [str(item).strip() for item in list(context.get("target_tables") or []) if str(item).strip()]
            if not context.get("target_table") and context["target_tables"]:
                context["target_table"] = context["target_tables"][0]
        else:
            expected_target = "left_recon_ready" if side == "left" else "right_recon_ready" if side == "right" else ""
            if side not in {"left", "right"}:
                context.setdefault("errors", []).append({"message": "side 必须是 left 或 right"})
            if context.get("target_table") != expected_target:
                context.setdefault("errors", []).append({"message": f"{side} 侧 target_table 必须是 {expected_target}"})
        if not context.get("sources"):
            context.setdefault("errors", []).append({"message": "请先选择数据集"})
        context["source_profiles"] = [_source_profile(source) for source in context.get("sources", [])]
        return {
            "success": not context.get("errors"),
            "message": "已准备数据集字段、中文名和样例行。" if not context.get("errors") else "上下文校验失败。",
            "summary": {"source_count": len(context.get("sources", []))},
            "errors": context.get("errors") or [],
        }

    async def _understand_rule(self, context: dict[str, Any]) -> dict[str, Any]:
        rule_text = str(context.get("rule_text") or "").strip()
        fallback_understanding = {
            "rule_text": rule_text,
            "target_table": context.get("target_table"),
            "source_count": len(context.get("sources", [])),
            "intent": "generate_proc_json",
        }
        try:
            parsed = await invoke_llm_json(build_understanding_prompt(context), temperature=0.05, timeout_seconds=45)
            context["understanding"] = _safe_dict(parsed.get("understanding")) or fallback_understanding
            context["assumptions"] = _safe_list_of_dicts(parsed.get("assumptions"))
            context["ambiguities"] = _safe_list_of_dicts(parsed.get("ambiguities"))
            context["llm_understanding_used"] = True
            return {"message": "已使用 LLM 将规则描述转换为结构化理解。"}
        except Exception as exc:  # noqa: BLE001
            logger.warning("[rule_generation] understand_rule fallback: %s", exc)
            context.setdefault("warnings", []).append(f"规则理解 LLM 不可用，已使用确定性 fallback：{exc}")
            context["understanding"] = fallback_understanding
            context.setdefault("assumptions", [])
            context.setdefault("ambiguities", [])
        return {"message": "已将规则描述转换为结构化理解。"}

    async def _semantic_resolution(self, context: dict[str, Any]) -> dict[str, Any]:
        assumptions = list(context.get("assumptions") or [])
        ambiguities = _normalize_ambiguity_candidates(
            list(context.get("ambiguities") or []),
            context.get("source_profiles", []),
        )
        for binding in list(context.get("field_bindings") or []):
            if not isinstance(binding, dict) or binding.get("status") != "bound":
                continue
            selected_field = binding.get("selected_field")
            if not isinstance(selected_field, dict):
                continue
            role = _normalize_field_role(binding.get("role"))
            assumptions.append({
                "name": FIELD_BINDING_ROLES.get(role, {}).get("label") or "字段绑定",
                "value": str(selected_field.get("name") or ""),
                "display_value": _field_candidate_display(selected_field),
                "confidence": 0.96,
                "reason": "规则描述中的字段引用已通过数据集字段精确绑定。",
            })
        context["assumptions"] = assumptions
        context["ambiguities"] = ambiguities
        return {"message": "已自动处理可推断的字段语义。", "summary": {"assumptions": len(assumptions), "ambiguities": len(ambiguities)}}

    async def _field_binding(self, context: dict[str, Any]) -> dict[str, Any]:
        field_intents = _extract_field_intents(context)
        source_profiles = list(context.get("source_profiles") or [])
        field_bindings = [_bind_field_intent(intent, source_profiles) for intent in field_intents]
        context["field_intents"] = field_intents
        context["field_bindings"] = field_bindings
        return {
            "message": "已将规则描述中的字段引用绑定到数据集字段。",
            "summary": {
                "intent_count": len(field_intents),
                "bound_count": len([item for item in field_bindings if item.get("status") == "bound"]),
                "ambiguous_count": len([item for item in field_bindings if item.get("status") != "bound"]),
            },
        }

    async def _ambiguity_gate(self, context: dict[str, Any]) -> dict[str, Any]:
        questions = []
        asked_roles: set[str] = set()
        for binding in list(context.get("field_bindings") or []):
            if not isinstance(binding, dict) or binding.get("status") == "bound":
                continue
            role = str(binding.get("role") or "field")
            asked_roles.add(role)
            candidates = [
                _field_candidate_payload(candidate)
                for candidate in list(binding.get("candidates") or [])
                if isinstance(candidate, dict)
            ]
            questions.append({
                "id": str(binding.get("intent_id") or "field_binding"),
                "type": "field_binding",
                "role": role,
                "mention": str(binding.get("mention") or ""),
                "question": _field_binding_question(binding),
                "candidates": candidates,
                "evidence": list(binding.get("evidence") or []),
            })
        for ambiguity in list(context.get("ambiguities") or []):
            if not _should_ask_user(ambiguity):
                continue
            role = _ambiguity_role(ambiguity)
            if role in asked_roles:
                continue
            candidates = list(ambiguity.get("candidates") or [])
            questions.append({
                "id": str(ambiguity.get("id") or "business_ambiguity"),
                "type": str(ambiguity.get("category") or "business_ambiguity"),
                "role": role,
                "question": _ambiguity_question(ambiguity),
                "candidates": candidates,
                "evidence": list(ambiguity.get("evidence") or []),
            })
        context["questions"] = questions[:3]
        if questions:
            context["status"] = "needs_user_input"
            return {"message": "发现需要确认的业务口径。", "summary": {"question_count": len(context["questions"])}}
        return {"message": "未发现需要打断用户的阻塞性业务歧义。", "summary": {"question_count": 0}}

    async def _generate_or_repair_json(self, context: dict[str, Any]) -> dict[str, Any]:
        failures = _collect_failures(context)
        try:
            prompt = (
                build_proc_repair_prompt(context, failures=failures)
                if failures
                else build_proc_generation_prompt(context)
            )
            parsed = await invoke_llm_json(prompt, temperature=0.05, timeout_seconds=60)
            rule = unwrap_rule_json(parsed)
            context["llm_generation_used"] = True
        except Exception as exc:  # noqa: BLE001
            if context.get("mode") == "generic_proc":
                raise
            logger.warning("[rule_generation] generate_or_repair fallback: %s", exc)
            context.setdefault("warnings", []).append(f"proc JSON 生成 LLM 不可用，已使用确定性 fallback：{exc}")
            rule = build_fallback_proc_rule(
                side=context["side"],
                target_table=context["target_table"],
                rule_text=context.get("rule_text", ""),
                sources=context.get("sources", []),
                field_bindings=context.get("field_bindings") or [],
            )
        context["proc_rule_json"] = rule
        context["normalized_rule_json"] = _normalize_generated_proc_rule(rule)
        _clear_runtime_validation_state(context)
        return {
            "message": "已生成当前侧 proc JSON。" if not failures else "已根据校验结果修复当前侧 proc JSON。",
            "summary": {
                "step_count": len((context.get("normalized_rule_json") or {}).get("steps", [])),
                "llm_used": bool(context.get("llm_generation_used")),
            },
        }

    async def _lint_json(self, context: dict[str, Any]) -> dict[str, Any]:
        result = lint_proc_rule(
            context.get("normalized_rule_json") or {},
            side=context["side"],
            target_table=context["target_table"],
            target_tables=context.get("target_tables") or [],
            sources=context.get("sources", []),
        )
        context["lint_result"] = result
        if not result.get("success"):
            _replace_stage_error(context, "lint_json", result.get("errors") or [])
        else:
            _clear_stage_error(context, "lint_json")
        return {
            "success": bool(result.get("success")),
            "message": "JSON 校验通过。" if result.get("success") else "JSON 校验失败。",
            "summary": {"error_count": len(result.get("errors") or []), "warning_count": len(result.get("warnings") or [])},
            "errors": result.get("errors") or [],
        }

    async def _build_sample_inputs(self, context: dict[str, Any]) -> dict[str, Any]:
        sample_inputs = []
        missing_sources: list[str] = []
        for source in context.get("sources", []):
            sample_rows = list(source.get("sample_rows") or [])[:5]
            if not sample_rows:
                missing_sources.append(_source_display_name(source))
            sample_inputs.append({**source, "sample_rows": sample_rows})
        context["sample_inputs"] = sample_inputs
        if missing_sources:
            errors = [
                {
                    "message": (
                        f"数据集 {source_name} 缺少真实 sample_rows，"
                        "请先完成数据采集后再执行 AI 生成规则。"
                    )
                }
                for source_name in missing_sources
            ]
            result = {
                "success": False,
                "message": "缺少真实样例数据，已停止样例执行。",
                "summary": {
                    "sample_dataset_count": len(sample_inputs),
                    "missing_sample_dataset_count": len(missing_sources),
                },
                "errors": errors,
            }
            context["sample_input_result"] = result
            _replace_stage_error(context, "build_sample_inputs", errors)
            return result
        result = {
            "success": True,
            "message": "已从数据集自身读取真实样例输入。",
            "summary": {"sample_dataset_count": len(sample_inputs)},
        }
        context["sample_input_result"] = result
        _clear_stage_error(context, "build_sample_inputs")
        return result

    async def _run_sample(self, context: dict[str, Any]) -> dict[str, Any]:
        result = await run_proc_sample(
            auth_token=context.get("auth_token", ""),
            rule_json=context.get("normalized_rule_json") or {},
            sources=context.get("sample_inputs") or context.get("sources") or [],
            expected_target=context["target_table"],
            expected_targets=context.get("target_tables") or [],
        )
        context["sample_result"] = result
        if not (result.get("success") and result.get("ready_for_confirm")):
            _replace_stage_error(context, "run_sample", result.get("errors") or [{"message": result.get("error") or result.get("message") or "样例执行未通过"}])
        else:
            _clear_stage_error(context, "run_sample")
        run_success = bool(result.get("success") and result.get("ready_for_confirm"))
        return {
            "success": run_success,
            "message": "样例执行通过。" if result.get("success") and result.get("ready_for_confirm") else "样例执行未通过。",
            "summary": {"ready_for_confirm": bool(result.get("ready_for_confirm")), "backend": result.get("backend")},
            "errors": [] if run_success else result.get("errors") or [{"message": result.get("error") or result.get("message") or "样例执行未通过"}],
        }

    async def _assert_output(self, context: dict[str, Any]) -> dict[str, Any]:
        result = assert_proc_output(
            context.get("sample_result") or {},
            expected_target=context["target_table"],
            expected_targets=context.get("target_tables") or [],
            sources=context.get("sample_inputs") or context.get("sources") or [],
        )
        context["assert_result"] = result
        context["output_fields"] = result.get("output_fields") or []
        context["output_preview_rows"] = result.get("output_preview_rows") or []
        if not result.get("success"):
            _replace_stage_error(context, "assert_output", result.get("errors") or [])
        else:
            _clear_stage_error(context, "assert_output")
        return {
            "success": bool(result.get("success")),
            "message": "输出结果已通过样例断言。" if result.get("success") else "输出结果断言未通过。",
            "summary": {"field_count": len(context.get("output_fields") or []), "row_count": len(context.get("output_preview_rows") or [])},
            "errors": result.get("errors") or [],
        }

    async def _result(self, context: dict[str, Any]) -> dict[str, Any]:
        context["status"] = "succeeded"
        return {"message": "当前侧 AI 生成输出数据完成。"}

    def _repair_started(self, context: dict[str, Any], *, reason: str) -> dict[str, Any]:
        return build_event(
            "repair_started",
            run_id=context["run_id"],
            side=context["side"],
            target_table=context["target_table"],
            node_code="generate_or_repair_json",
            node_status="running",
            attempt=int(context.get("retry_count") or 0) + 1,
            message=reason,
            node_name="修复规则",
        )

    def _graph_completed(self, context: dict[str, Any]) -> dict[str, Any]:
        return build_event(
            "graph_completed",
            run_id=context["run_id"],
            side=context["side"],
            target_table=context["target_table"],
            message="AI 生成输出数据完成。",
            status="succeeded",
            proc_rule_json=context.get("normalized_rule_json") or {},
            output_fields=context.get("output_fields") or [],
            output_preview_rows=context.get("output_preview_rows") or [],
            output_samples=(context.get("sample_result") or {}).get("output_samples") or [],
            assumptions=context.get("assumptions") or [],
            field_bindings=context.get("field_bindings") or [],
            validations=[context.get("lint_result") or {}, context.get("assert_result") or {}],
            warnings=context.get("warnings") or [],
        )

    def _graph_failed(self, context: dict[str, Any]) -> dict[str, Any]:
        errors = _all_context_errors(context)
        return build_event(
            "graph_failed",
            run_id=context.get("run_id", ""),
            side=context.get("side", ""),
            target_table=context.get("target_table", ""),
            message="AI 生成输出数据失败。",
            status="failed",
            errors=errors,
            proc_rule_json=context.get("normalized_rule_json") or {},
        )


def _initial_context(*, auth_token: str, payload: dict[str, Any], run_id: str) -> dict[str, Any]:
    return {
        "auth_token": auth_token,
        "run_id": run_id,
        "side": str(payload.get("side") or "").strip(),
        "target_table": str(payload.get("target_table") or "").strip(),
        "target_tables": [str(item).strip() for item in list(payload.get("target_tables") or []) if str(item).strip()],
        "mode": str(payload.get("mode") or "side_proc").strip() or "side_proc",
        "rule_text": str(payload.get("rule_text") or "").strip(),
        "proc_json_examples": [item for item in list(payload.get("proc_json_examples") or []) if isinstance(item, dict)],
        "sources": [source for source in list(payload.get("sources") or []) if isinstance(source, dict)],
        "status": "running",
        "phase": "prepare_context",
        "retry_count": 0,
        "max_retries": int(payload.get("max_retries") or 2),
        "errors": [],
        "warnings": [],
        "trace": [],
    }


def _source_profile(source: dict[str, Any]) -> dict[str, Any]:
    field_candidates = _field_candidates(source)
    fields = [candidate["name"] for candidate in field_candidates]
    return {
        "table_name": str(source.get("table_name") or source.get("resource_key") or source.get("id") or ""),
        "field_count": len(fields),
        "fields": fields,
        "field_candidates": field_candidates,
    }


FIELD_BINDING_ROLES = {
    "match_key": {"label": "匹配字段"},
    "compare_field": {"label": "对比字段"},
    "time_field": {"label": "时间字段"},
    "filter_field": {"label": "过滤字段"},
    "group_field": {"label": "分组字段"},
    "output_field": {"label": "输出字段"},
}


FIELD_INTENT_PATTERNS: tuple[tuple[str, str], ...] = (
    ("match_key", r"(?P<mention>[^，,。；;\n]{1,30}?)(?:作为|做为|为|是|当作|用作)?(?:匹配字段|匹配键|对账字段|关联字段|主键)"),
    ("compare_field", r"(?P<mention>[^，,。；;\n]{1,30}?)(?:作为|做为|为|是|当作|用作)?(?:对比字段|比较字段|核对字段)"),
    ("time_field", r"(?P<mention>[^，,。；;\n]{1,30}?)(?:作为|做为|为|是|当作|用作)?(?:时间字段|日期字段)"),
    ("filter_field", r"(?P<mention>[^，,。；;\n]{1,30}?)(?:只取|仅取|筛选|过滤|取)(?P<value>[A-Za-z0-9_\-.]+)的数据"),
)


def _extract_field_intents(context: dict[str, Any]) -> list[dict[str, Any]]:
    intents: list[dict[str, Any]] = []
    understanding = _safe_dict(context.get("understanding"))
    for item in _safe_list_of_dicts(understanding.get("field_intents")):
        role = _normalize_field_role(item.get("role"))
        mention = _clean_field_mention(item.get("mention") or item.get("field") or item.get("name"))
        if not role or not mention:
            continue
        intents.append({
            "intent_id": str(item.get("intent_id") or item.get("id") or f"{role}_{len(intents) + 1}"),
            "role": role,
            "mention": mention,
            "operation": str(item.get("operation") or "").strip(),
            "operator": str(item.get("operator") or "").strip(),
            "value": item.get("value"),
            "llm_candidates": _extract_llm_field_candidates(item),
        })

    rule_text = str(context.get("rule_text") or "")
    for role, pattern in FIELD_INTENT_PATTERNS:
        for match in re.finditer(pattern, rule_text):
            mention = _clean_field_mention(match.group("mention"))
            if not mention:
                continue
            intent = {
                "intent_id": f"{role}_{len(intents) + 1}",
                "role": role,
                "mention": mention,
                "operation": "filter_eq" if role == "filter_field" else f"use_as_{role}",
            }
            if "value" in match.groupdict():
                intent["operator"] = "eq"
                intent["value"] = match.group("value")
            intents.append(intent)
    return _dedupe_field_intents(intents)


def _normalize_field_role(value: Any) -> str:
    role = str(value or "").strip().lower()
    aliases = {
        "join_key": "match_key",
        "key_field": "match_key",
        "date_field": "time_field",
        "filter": "filter_field",
    }
    return aliases.get(role, role if role in FIELD_BINDING_ROLES else "")


def _clean_field_mention(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^(把|将|用|按|以|根据|其中|并且|且|同时)", "", text).strip()
    text = re.sub(r"(字段|列|口径)$", "", text).strip()
    return text


def _dedupe_field_intents(intents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for intent in intents:
        key = (str(intent.get("role") or ""), str(intent.get("mention") or ""), str(intent.get("value") or ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append({**intent, "intent_id": str(intent.get("intent_id") or f"{intent.get('role')}_{len(deduped) + 1}")})
    return deduped


def _bind_field_intent(intent: dict[str, Any], source_profiles: list[dict[str, Any]]) -> dict[str, Any]:
    role = _normalize_field_role(intent.get("role"))
    mention = str(intent.get("mention") or "").strip()
    candidates = _candidate_fields_for_role(role, source_profiles)
    match_result = _match_field_mention(mention, candidates)
    llm_candidates = _resolve_llm_field_candidates(intent, candidates)
    if match_result["status"] != "bound" and llm_candidates:
        match_result = {
            "status": "ambiguous",
            "candidates": llm_candidates,
            "evidence": [
                *list(match_result.get("evidence") or []),
                "LLM 理解阶段给出候选字段，已校验候选存在于当前数据集。",
            ],
        }
    status = "bound" if match_result["status"] == "bound" else match_result["status"]
    selected = match_result.get("selected_field") if status == "bound" else None
    return {
        "intent_id": str(intent.get("intent_id") or f"{role}_{mention}"),
        "role": role,
        "mention": mention,
        "operation": intent.get("operation") or "",
        "operator": intent.get("operator") or "",
        "value": intent.get("value"),
        "status": status,
        "selected_field": selected,
        "candidates": match_result.get("candidates") or candidates[:8],
        "evidence": match_result.get("evidence") or [],
    }


def _extract_llm_field_candidates(item: dict[str, Any]) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for key in ("candidate_fields", "field_candidates", "suggested_fields", "candidates"):
        value = item.get(key)
        if not isinstance(value, list):
            continue
        for candidate in value:
            if isinstance(candidate, dict):
                raw_name = str(
                    candidate.get("raw_name")
                    or candidate.get("name")
                    or candidate.get("field")
                    or candidate.get("field_name")
                    or ""
                ).strip()
                display_name = str(
                    candidate.get("display_name")
                    or candidate.get("label")
                    or candidate.get("business_name")
                    or raw_name
                ).strip()
                source_table = str(candidate.get("source_table") or candidate.get("table_name") or candidate.get("table") or "").strip()
                reason = str(candidate.get("reason") or candidate.get("evidence") or "").strip()
            else:
                raw_name = str(candidate or "").strip()
                display_name = raw_name
                source_table = ""
                reason = ""
            if not raw_name and not display_name:
                continue
            candidates.append({
                "raw_name": raw_name,
                "display_name": display_name or raw_name,
                "source_table": source_table,
                "reason": reason,
            })
    return candidates


def _resolve_llm_field_candidates(
    intent: dict[str, Any],
    candidates: list[dict[str, str]],
) -> list[dict[str, str]]:
    resolved: list[dict[str, str]] = []
    for hint in list(intent.get("llm_candidates") or []):
        if not isinstance(hint, dict):
            continue
        matched = _find_actual_field_candidate(hint, candidates)
        if not matched:
            continue
        resolved.append(matched)
    return _dedupe_field_candidates(resolved)


def _find_actual_field_candidate(
    hint: dict[str, Any],
    candidates: list[dict[str, str]],
) -> dict[str, str] | None:
    raw_name = str(hint.get("raw_name") or hint.get("name") or "").strip()
    display_name = str(hint.get("display_name") or hint.get("label") or "").strip()
    source_table = str(hint.get("source_table") or hint.get("table_name") or "").strip()
    normalized_raw = _normalize_text_for_match(raw_name)
    normalized_display = _normalize_text_for_match(display_name)

    def table_matches(candidate: dict[str, str]) -> bool:
        return not source_table or str(candidate.get("table_name") or "") == source_table

    if raw_name:
        for candidate in candidates:
            if table_matches(candidate) and str(candidate.get("name") or "") == raw_name:
                return candidate
    if display_name:
        for candidate in candidates:
            if table_matches(candidate) and str(candidate.get("label") or "") == display_name:
                return candidate
    for normalized_hint in (normalized_raw, normalized_display):
        if not normalized_hint:
            continue
        for candidate in candidates:
            if table_matches(candidate) and normalized_hint in _field_match_terms(candidate):
                return candidate
    return None


def _candidate_fields_for_role(role: str, source_profiles: list[dict[str, Any]]) -> list[dict[str, str]]:
    if role not in FIELD_BINDING_ROLES:
        return []
    all_candidates: list[dict[str, str]] = []
    for profile in source_profiles:
        table_name = str(profile.get("table_name") or "")
        for candidate in list(profile.get("field_candidates") or []):
            if not isinstance(candidate, dict):
                continue
            raw_name = str(candidate.get("name") or "").strip()
            if not raw_name:
                continue
            all_candidates.append({
                "name": raw_name,
                "label": str(candidate.get("label") or raw_name).strip() or raw_name,
                "table_name": table_name,
            })
    return _dedupe_field_candidates(all_candidates)


def _dedupe_field_candidates(candidates: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for candidate in candidates:
        key = (str(candidate.get("table_name") or ""), str(candidate.get("name") or ""))
        if not key[1] or key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _match_field_mention(mention: str, candidates: list[dict[str, str]]) -> dict[str, Any]:
    normalized_mention = _normalize_text_for_match(mention)
    if not normalized_mention:
        return {"status": "missing", "candidates": candidates[:8], "evidence": ["规则描述缺少字段名称"]}
    exact_matches = [candidate for candidate in candidates if normalized_mention in _field_match_terms(candidate)]
    if len(exact_matches) == 1:
        exact_candidate = exact_matches[0]
        more_specific = [
            candidate
            for candidate in candidates
            if candidate is not exact_candidate
            and any(
                normalized_mention in term and normalized_mention != term
                for term in _field_match_terms(candidate)
            )
        ]
        if more_specific:
            return {
                "status": "ambiguous",
                "candidates": [exact_candidate, *more_specific],
                "evidence": [f"规则描述中的“{mention}”同时可能对应多个更具体字段"],
            }
        return {
            "status": "bound",
            "selected_field": exact_candidate,
            "candidates": [exact_candidate],
            "evidence": [f"规则描述中的“{mention}”明确命中字段“{_field_candidate_display(exact_candidate)}”"],
        }
    if len(exact_matches) > 1:
        return {
            "status": "ambiguous",
            "candidates": exact_matches,
            "evidence": [f"规则描述中的“{mention}”命中多个同名字段"],
        }

    partial_matches = [
        candidate
        for candidate in candidates
        if any(normalized_mention in term or term in normalized_mention for term in _field_match_terms(candidate))
    ]
    if partial_matches:
        return {
            "status": "ambiguous",
            "candidates": _rank_field_candidates(mention, partial_matches)[:8],
            "evidence": [f"规则描述中的“{mention}”不是字段完整名称，只能部分匹配候选字段"],
        }
    suggested_candidates = _suggest_field_candidates(mention, candidates)
    return {
        "status": "missing",
        "candidates": suggested_candidates[:8],
        "evidence": [f"规则描述中的“{mention}”未匹配到数据集字段"],
    }


def _suggest_field_candidates(mention: str, candidates: list[dict[str, str]]) -> list[dict[str, str]]:
    normalized_mention = _normalize_text_for_match(mention)
    if not normalized_mention:
        return []
    ranked = _rank_field_candidates(mention, candidates)
    suggestions: list[dict[str, str]] = []
    for candidate in ranked:
        if _is_close_field_candidate(normalized_mention, candidate):
            suggestions.append(candidate)
    return suggestions


def _is_close_field_candidate(normalized_mention: str, candidate: dict[str, str]) -> bool:
    for term in _field_match_terms(candidate):
        if not term:
            continue
        if normalized_mention in term or term in normalized_mention:
            return True
        lcs_len = _longest_common_subsequence_length(normalized_mention, term)
        if lcs_len >= 2 and lcs_len / max(len(normalized_mention), 1) >= 0.75:
            return True
    return False


def _rank_field_candidates(mention: str, candidates: list[dict[str, str]]) -> list[dict[str, str]]:
    normalized_mention = _normalize_text_for_match(mention)
    return sorted(
        candidates,
        key=lambda candidate: _field_similarity_score(normalized_mention, candidate),
        reverse=True,
    )


def _field_similarity_score(normalized_mention: str, candidate: dict[str, str]) -> tuple[int, int, int]:
    scores: list[tuple[int, int, int]] = []
    for term in _field_match_terms(candidate):
        if not term or not normalized_mention:
            scores.append((0, 0, -len(term)))
            continue
        if term == normalized_mention:
            scores.append((1000, len(term), -len(term)))
            continue
        if normalized_mention in term or term in normalized_mention:
            scores.append((800 + min(len(term), len(normalized_mention)), min(len(term), len(normalized_mention)), -len(term)))
            continue
        lcs_len = _longest_common_subsequence_length(normalized_mention, term)
        common_prefix = _common_prefix_length(normalized_mention, term)
        scores.append((lcs_len, common_prefix, -len(term)))
    return max(scores) if scores else (0, 0, 0)


def _longest_common_subsequence_length(left: str, right: str) -> int:
    if not left or not right:
        return 0
    previous = [0] * (len(right) + 1)
    for left_char in left:
        current = [0]
        for index, right_char in enumerate(right, start=1):
            if left_char == right_char:
                current.append(previous[index - 1] + 1)
            else:
                current.append(max(previous[index], current[index - 1]))
        previous = current
    return previous[-1]


def _common_prefix_length(left: str, right: str) -> int:
    count = 0
    for left_char, right_char in zip(left, right, strict=False):
        if left_char != right_char:
            break
        count += 1
    return count


def _field_candidate_payload(candidate: dict[str, Any]) -> dict[str, str]:
    raw_name = str(candidate.get("name") or candidate.get("raw_name") or "").strip()
    display_name = str(candidate.get("label") or candidate.get("display_name") or raw_name).strip() or raw_name
    table_name = str(candidate.get("table_name") or candidate.get("source_table") or "").strip()
    return {
        "raw_name": raw_name,
        "name": raw_name,
        "display_name": display_name,
        "label": display_name,
        "source_table": table_name,
        "table_name": table_name,
    }


def _field_binding_question(binding: dict[str, Any]) -> str:
    mention = str(binding.get("mention") or "该字段").strip() or "该字段"
    role = _normalize_field_role(binding.get("role"))
    status = str(binding.get("status") or "").strip()
    action = "未匹配到数据集字段" if status == "missing" else "未明确对应哪个字段"
    templates = {
        "match_key": f"当前规则中的“{mention}”{action}，请在描述中改为完整、明确的匹配字段中文名。",
        "compare_field": f"当前规则中的“{mention}”{action}，请在描述中改为完整、明确的对比字段中文名。",
        "time_field": f"当前规则中的“{mention}”{action}，请在描述中改为完整、明确的时间字段中文名。",
        "filter_field": f"当前规则中的“{mention}”{action}，请在描述中改为完整、明确的过滤字段中文名。",
        "group_field": f"当前规则中的“{mention}”{action}，请在描述中改为完整、明确的分组字段中文名。",
        "output_field": f"当前规则中的“{mention}”{action}，请在描述中改为完整、明确的输出字段中文名。",
    }
    return templates.get(role, f"当前规则中的“{mention}”{action}，请在描述中改为完整、明确的字段中文名。")


def _ambiguity_role(ambiguity: dict[str, Any]) -> str:
    category = str(ambiguity.get("category") or "").strip()
    mapping = {
        "amount_metric": "compare_field",
        "date_metric": "time_field",
        "join_key": "match_key",
        "filter_boundary": "filter_field",
        "aggregation_grain": "group_field",
    }
    return mapping.get(category, "business_rule")


def _ambiguity_question(ambiguity: dict[str, Any]) -> str:
    role = _ambiguity_role(ambiguity)
    questions = {
        "compare_field": "当前规则未明确金额/对比口径，请修改上方完整规则描述后重新生成。",
        "time_field": "当前规则未明确时间口径，请修改上方完整规则描述后重新生成。",
        "match_key": "当前规则未明确匹配字段，请修改上方完整规则描述后重新生成。",
        "filter_field": "当前规则未明确过滤条件边界，请修改上方完整规则描述后重新生成。",
        "group_field": "当前规则未明确汇总粒度，请修改上方完整规则描述后重新生成。",
    }
    return questions.get(role, "当前规则存在会影响结果的业务歧义，请修改上方完整规则描述后重新生成。")


def _field_candidates(source: dict[str, Any]) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    labels = source.get("field_label_map") if isinstance(source.get("field_label_map"), dict) else {}

    def add_candidate(name: Any, label: Any = "") -> None:
        raw_name = str(name or "").strip()
        if not raw_name:
            return
        display_name = str(label or labels.get(raw_name) or raw_name).strip() or raw_name
        for candidate in candidates:
            if candidate["name"] == raw_name:
                if candidate.get("label") == raw_name and display_name != raw_name:
                    candidate["label"] = display_name
                return
        candidates.append({"name": raw_name, "label": display_name})

    for field in list(source.get("fields") or []):
        if not isinstance(field, dict):
            continue
        add_candidate(
            field.get("name") or field.get("raw_name") or field.get("field_name") or field.get("key"),
            field.get("label") or field.get("display_name") or field.get("business_name"),
        )
    for key, label in labels.items():
        add_candidate(key, label)
    for row in list(source.get("sample_rows") or []):
        if isinstance(row, dict):
            for key in row.keys():
                add_candidate(key)
    return candidates


def _field_names(source: dict[str, Any]) -> list[str]:
    return [candidate["name"] for candidate in _field_candidates(source)]


def _normalize_generated_proc_rule(rule: Any) -> dict[str, Any]:
    if not isinstance(rule, dict):
        return {}
    normalized = dict(rule)
    normalized["steps"] = [
        _normalize_generated_step(step, index)
        for index, step in enumerate(list(rule.get("steps") or []), start=1)
        if isinstance(step, dict)
    ]
    return normalized


def _normalize_generated_step(step: dict[str, Any], index: int) -> dict[str, Any]:
    action = str(step.get("action") or step.get("type") or step.get("step") or "").strip()
    nested = step.get(action) if isinstance(step.get(action), dict) else {}
    if action not in {"create_schema", "write_dataset"}:
        if isinstance(step.get("schema"), dict) and not step.get("sources"):
            action = "create_schema"
        elif isinstance(step.get("write_dataset"), dict) or step.get("sources") or step.get("mappings"):
            action = "write_dataset"
    if action == "create_schema":
        return _normalize_create_schema_step(step, nested, index)
    if action == "write_dataset":
        return _normalize_write_dataset_step(step, nested, index)
    return {**step, "step_id": _step_id(step, action, index), "action": action}


def _normalize_create_schema_step(step: dict[str, Any], nested: dict[str, Any], index: int) -> dict[str, Any]:
    schema = _safe_dict(step.get("schema")) or _safe_dict(nested.get("schema"))
    if "schema" in schema and isinstance(schema.get("schema"), dict):
        nested_schema = _safe_dict(schema.get("schema"))
        target_table = step.get("target_table") or schema.get("target_table") or nested.get("target_table")
        schema = nested_schema
    else:
        target_table = step.get("target_table") or nested.get("target_table") or schema.get("target_table")
    columns = [_normalize_schema_column(column) for column in list(schema.get("columns") or []) if isinstance(column, dict)]
    return {
        **{key: value for key, value in step.items() if key not in {"type", "schema"}},
        "step_id": _step_id(step, "create_schema", index),
        "action": "create_schema",
        "target_table": target_table,
        "schema": {**schema, "columns": columns},
    }


def _normalize_write_dataset_step(step: dict[str, Any], nested: dict[str, Any], index: int) -> dict[str, Any]:
    merged = {**nested, **{key: value for key, value in step.items() if key not in {"type", "write_dataset"}}}
    return {
        **merged,
        "step_id": _step_id(merged, "write_dataset", index),
        "action": "write_dataset",
        "target_table": merged.get("target_table"),
        "sources": [_normalize_step_source(source) for source in list(merged.get("sources") or []) if isinstance(source, dict)],
        "mappings": [_normalize_mapping(mapping) for mapping in list(merged.get("mappings") or []) if isinstance(mapping, dict)],
    }


def _normalize_schema_column(column: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(column)
    if not normalized.get("name") and normalized.get("field_name"):
        normalized["name"] = normalized.get("field_name")
    normalized.pop("field_name", None)
    return normalized


def _step_id(step: dict[str, Any], action: str, index: int) -> str:
    existing = str(step.get("step_id") or step.get("id") or "").strip()
    if existing:
        return existing
    suffix = action or "step"
    return f"step_{index}_{suffix}"


def _normalize_step_source(source: dict[str, Any]) -> dict[str, Any]:
    table = source.get("table") or source.get("table_name") or source.get("source")
    alias = source.get("alias") or table
    return {**source, "table": table, "alias": alias}


def _normalize_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    value = _normalize_value_node(mapping.get("value"), default_alias=str(mapping.get("source") or ""))
    return {**mapping, "value": value}


def _normalize_value_node(value: Any, *, default_alias: str = "") -> Any:
    if isinstance(value, list):
        return [_normalize_value_node(item, default_alias=default_alias) for item in value]
    if not isinstance(value, dict):
        return value
    value_type = str(value.get("type") or "").strip()
    normalized = dict(value)
    if value_type == "source":
        source = normalized.get("source")
        if isinstance(source, str):
            normalized["source"] = {"alias": source or default_alias, "field": normalized.get("field")}
            normalized.pop("field", None)
        elif isinstance(source, dict):
            source_field = source.get("field") or normalized.get("field")
            source_alias = source.get("alias") or source.get("table") or source.get("source") or default_alias
            normalized["source"] = {**source, "alias": source_alias, "field": source_field}
            normalized.pop("field", None)
        elif not isinstance(source, dict):
            normalized["source"] = {"alias": default_alias, "field": normalized.get("field")}
            normalized.pop("field", None)
    if value_type == "formula" and not normalized.get("expr") and normalized.get("formula"):
        normalized["expr"] = normalized.get("formula")
        normalized.pop("formula", None)
    for key, nested in list(normalized.items()):
        if key in {"source"}:
            continue
        normalized[key] = _normalize_value_node(nested, default_alias=default_alias)
    return normalized


def _normalize_text_for_match(value: Any) -> str:
    return str(value or "").replace(" ", "").lower()


def _field_match_terms(candidate: dict[str, str]) -> list[str]:
    terms: list[str] = []
    for name in (candidate.get("name"), candidate.get("label")):
        for variant in _text_match_variants(name):
            term = _normalize_text_for_match(variant)
            if term and term not in terms:
                terms.append(term)
    return terms


def _text_match_variants(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    variants = [text]
    stripped = re.sub(r"[（(][^（）()]{1,12}[）)]$", "", text).strip()
    if stripped and stripped != text:
        variants.append(stripped)
    return variants


def _field_candidate_display(candidate: dict[str, str]) -> str:
    raw_name = str(candidate.get("name") or "").strip()
    label = str(candidate.get("label") or raw_name).strip()
    if label and raw_name and label != raw_name:
        return f"{label}（{raw_name}）"
    return label or raw_name


def _normalize_ambiguity_candidates(
    ambiguities: list[dict[str, Any]],
    source_profiles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    field_candidates = _candidate_fields_for_role("match_key", source_profiles)

    for ambiguity in ambiguities:
        if not isinstance(ambiguity, dict):
            continue
        item = dict(ambiguity)
        if not item.get("candidates") and field_candidates:
            item["candidates"] = [_field_candidate_display(candidate) for candidate in field_candidates[:8]]
            item["raw_candidates"] = [candidate["name"] for candidate in field_candidates[:8]]
        normalized.append(item)
    return normalized


def _source_display_name(source: dict[str, Any]) -> str:
    return str(
        source.get("business_name")
        or source.get("dataset_name")
        or source.get("table_name")
        or source.get("resource_key")
        or source.get("id")
        or "未命名数据集"
    ).strip()


def _rule_text_mentions_any(rule_text: str, candidates: list[str]) -> bool:
    compact_rule = rule_text.replace(" ", "").lower()
    if not compact_rule:
        return False
    return any(str(candidate).replace(" ", "").lower() in compact_rule for candidate in candidates)


def _should_ask_user(ambiguity: dict[str, Any]) -> bool:
    if ambiguity.get("impact") != "changes_output_result":
        return False
    if ambiguity.get("resolved"):
        return False
    try:
        confidence = float(ambiguity.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0
    return confidence < 0.75


def _node_display_name(node_code: str, attempt: int) -> str | None:
    if node_code == "generate_or_repair_json":
        return "生成规则" if attempt <= 1 else "修复规则"
    return None


def _node_completed_message(node_code: str, attempt: int) -> str:
    if node_code == "generate_or_repair_json":
        return "生成规则完成。" if attempt <= 1 else "修复规则完成。"
    return f"{NODE_LABELS.get(node_code, node_code)}完成。"


def _node_success(result: Any) -> bool:
    if not isinstance(result, dict) or not result.get("success"):
        return False
    if "ready_for_confirm" in result:
        return bool(result.get("ready_for_confirm"))
    return True


def _can_retry(context: dict[str, Any], max_retries: int) -> bool:
    return int(context.get("retry_count") or 0) < max_retries


def _collect_failures(context: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for key in ("lint_result", "sample_result", "assert_result"):
        result = context.get(key)
        if not isinstance(result, dict) or _node_success(result):
            continue
        failures.append({
            "stage": key,
            "error": result.get("error") or result.get("message") or "",
            "errors": result.get("errors") or [],
            "warnings": result.get("warnings") or [],
        })
    return failures


def _clear_runtime_validation_state(context: dict[str, Any]) -> None:
    for key in ("lint_result", "sample_input_result", "sample_result", "assert_result", "output_fields", "output_preview_rows"):
        context.pop(key, None)
    for stage in ("lint_json", "build_sample_inputs", "run_sample", "assert_output"):
        _clear_stage_error(context, stage)


def _replace_stage_error(context: dict[str, Any], stage: str, errors: list[Any]) -> None:
    current_errors = [
        item
        for item in list(context.get("errors") or [])
        if isinstance(item, dict) and item.get("stage") != stage
    ]
    for error in errors:
        if isinstance(error, dict):
            current_errors.append({"stage": stage, **error})
        else:
            current_errors.append({"stage": stage, "message": str(error)})
    context["errors"] = current_errors


def _clear_stage_error(context: dict[str, Any], stage: str) -> None:
    context["errors"] = [
        item
        for item in list(context.get("errors") or [])
        if isinstance(item, dict) and item.get("stage") != stage
    ]


def _all_context_errors(context: dict[str, Any]) -> list[dict[str, Any]]:
    errors = [item for item in list(context.get("errors") or []) if isinstance(item, dict)]
    for stage, key in (("lint_json", "lint_result"), ("build_sample_inputs", "sample_input_result"), ("run_sample", "sample_result"), ("assert_output", "assert_result")):
        result = context.get(key)
        if not isinstance(result, dict) or _node_success(result):
            continue
        for error in list(result.get("errors") or []):
            if isinstance(error, dict):
                errors.append({"stage": stage, **error})
            else:
                errors.append({"stage": stage, "message": str(error)})
        if not result.get("errors") and (result.get("error") or result.get("message")):
            errors.append({"stage": stage, "message": str(result.get("error") or result.get("message"))})
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for error in errors:
        key = (
            str(error.get("stage") or error.get("node") or ""),
            str(error.get("step_id") or ""),
            str(error.get("step_index") or ""),
            str(error.get("message") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(error)
    return deduped


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


_service: RuleGenerationService | None = None


def get_rule_generation_service() -> RuleGenerationService:
    global _service
    if _service is None:
        _service = RuleGenerationService()
    return _service
