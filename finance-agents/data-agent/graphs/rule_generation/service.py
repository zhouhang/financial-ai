"""Service layer for AI rule generation workflows."""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from graphs.rule_generation.common.events import NODE_LABELS, build_event
from graphs.rule_generation.common.llm_json import invoke_llm_json
from graphs.rule_generation.proc.assertions import assert_proc_output
from graphs.rule_generation.proc.ir_compiler import compile_understanding_into_rule
from graphs.rule_generation.proc.ir_dsl_consistency import check_ir_dsl_consistency
from graphs.rule_generation.proc.ir_linter import lint_rule_generation_ir
from graphs.rule_generation.proc.linter import lint_proc_rule
from graphs.rule_generation.proc.prompts import (
    build_ir_repair_prompt,
    build_understanding_prompt,
)
from graphs.rule_generation.proc.rule_builder import build_proc_rule_skeleton_from_ir
from graphs.rule_generation.proc.sample_diagnostics import diagnose_proc_sample
from graphs.rule_generation.proc.sample_runner import run_proc_sample
from graphs.rule_generation.proc.understanding import (
    OUTPUT_SPEC_KINDS,
    SOURCE_REFERENCE_USAGES,
    normalize_output_spec_kind,
    normalize_source_reference_usage,
    normalize_understanding,
)

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
        logger.info(
            "[rule_generation][proc_side] start run_id=%s side=%s target=%s sources=%s rule_text=%s",
            run_id,
            side,
            target_table,
            _log_json(_source_log_summary(context.get("sources") or [])),
            _truncate_log_text(context.get("rule_text"), limit=500),
        )

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
            max_lint_ir_retries = int(context.get("max_lint_ir_repair_attempts") or 3)
            while True:
                validate_attempt = int(context.get("structure_ir_repair_count") or 0) + 1
                yield self._node_started(context, "validate_ir_structure", attempt=validate_attempt)
                validation_event = await self._run_node(
                    context,
                    "validate_ir_structure",
                    self._validate_ir_structure,
                    attempt=validate_attempt,
                )
                yield validation_event
                if not context.get("ir_structure_needs_repair"):
                    break
                graph_failed = False
                async for event in self._repair_ir_and_validate(
                    context,
                    stage="validate_ir_structure",
                    failures=_stage_failures(
                        context,
                        "validate_ir_structure",
                        {"success": False, "errors": context.get("ir_structure_repair_reasons") or []},
                    ),
                    retry_key="structure_ir_repair_count",
                    max_retries=int(context.get("max_structure_ir_repair_attempts") or 3),
                    exhausted_category="llm_repair_failed",
                    exhausted_message="IR 结构多轮修复后仍未通过校验。",
                    compile_after_repair=False,
                ):
                    yield event
                    if event.get("event") == "graph_failed":
                        graph_failed = True
                if graph_failed:
                    return
                if not context.get("ir_structure_needs_repair"):
                    break
            yield self._node_started(context, "resolve_source_bindings")
            yield await self._run_node(context, "resolve_source_bindings", self._resolve_source_bindings)
            yield self._node_started(context, "semantic_resolution")
            yield await self._run_node(context, "semantic_resolution", self._semantic_resolution)
            yield self._node_started(context, "ambiguity_gate")
            yield await self._run_node(context, "ambiguity_gate", self._ambiguity_gate)
            if context.get("status") == "needs_user_input":
                yield self._needs_user_input_event(context)
                return
            while True:
                ir_attempt = int(context.get("lint_ir_repair_count") or 0) + 1
                yield self._node_started(context, "lint_ir", attempt=ir_attempt)
                yield await self._run_node(
                    context,
                    "lint_ir",
                    self._lint_ir,
                    attempt=ir_attempt,
                )
                if _node_success(context.get("ir_lint_result")):
                    break
                lint_route = _classify_ir_lint_failure(context)
                if lint_route.get("route") == "needs_user_input":
                    _set_ir_lint_questions(context, lint_route.get("errors") or [])
                    yield self._needs_user_input_event(context)
                    return
                graph_failed = False
                async for event in self._repair_ir_and_validate(
                    context,
                    stage="lint_ir",
                    failures=_stage_failures(context, "lint_ir", context.get("ir_lint_result")),
                    retry_key="lint_ir_repair_count",
                    max_retries=max_lint_ir_retries,
                    exhausted_category="llm_repair_failed",
                    exhausted_message="IR lint 多轮修复后仍未通过校验。",
                    compile_after_repair=False,
                ):
                    yield event
                    if event.get("event") == "graph_failed":
                        graph_failed = True
                if graph_failed:
                    return
                if context.get("status") == "needs_user_input":
                    yield self._needs_user_input_event(context)
                    return
                if _node_success(context.get("ir_lint_result")):
                    break

            max_retries = int(context.get("max_retries") or 2)
            yield self._node_started(context, "generate_proc_json")
            generation_event = await self._run_node(
                context,
                "generate_proc_json",
                self._generate_proc_json,
            )
            yield generation_event
            if _event_node_failed(generation_event):
                yield self._graph_failed(context)
                return

            while True:
                dsl_ok = True
                for event in await self._run_proc_json_lint_loop(context):
                    yield event
                    if event.get("event") == "graph_failed":
                        dsl_ok = False
                if not dsl_ok:
                    return

                for event in await self._run_ir_dsl_consistency_loop(context):
                    yield event
                    if event.get("event") == "graph_failed":
                        dsl_ok = False
                if not dsl_ok:
                    return
                if context.pop("restart_validation_loop", False):
                    continue
                runtime_attempt = int(context.get("sample_ir_repair_count") or 0) + 1

                yield self._node_started(context, "build_sample_inputs", attempt=runtime_attempt)
                yield await self._run_node(context, "build_sample_inputs", self._build_sample_inputs, attempt=runtime_attempt)
                if not _node_success(context.get("sample_input_result")):
                    yield self._graph_failed(context)
                    return

                yield self._node_started(context, "run_sample", attempt=runtime_attempt)
                yield await self._run_node(context, "run_sample", self._run_sample, attempt=runtime_attempt)
                if not _node_success(context.get("sample_result")):
                    async for event in self._diagnose_and_repair_runtime(
                        context,
                        max_retries=max_retries,
                        runtime_attempt=runtime_attempt,
                    ):
                        yield event
                    if context.pop("runtime_terminal_failure", False):
                        return
                    if context.pop("restart_validation_loop", False):
                        continue
                    yield self._graph_failed(context)
                    return

                yield self._node_started(context, "assert_output", attempt=runtime_attempt)
                yield await self._run_node(context, "assert_output", self._assert_output, attempt=runtime_attempt)
                if not _node_success(context.get("assert_result")):
                    async for event in self._diagnose_and_repair_runtime(
                        context,
                        max_retries=max_retries,
                        runtime_attempt=runtime_attempt,
                    ):
                        yield event
                    if context.pop("runtime_terminal_failure", False):
                        return
                    if context.pop("restart_validation_loop", False):
                        continue
                    yield self._graph_failed(context)
                    return
                break

            yield self._node_started(context, "result")
            yield await self._run_node(context, "result", self._result)
            yield self._graph_completed(context)
        except Exception as exc:  # noqa: BLE001
            logger.exception("rule_generation proc side failed")
            context.setdefault("errors", []).append({"message": str(exc), "type": exc.__class__.__name__})
            yield self._graph_failed(context)

    def _node_started(self, context: dict[str, Any], node_code: str, *, attempt: int = 1) -> dict[str, Any]:
        return build_event(
            "node_started",
            run_id=context["run_id"],
            side=context["side"],
            target_table=context["target_table"],
            node_code=node_code,
            node_status="running",
            attempt=attempt,
            message="",
        )

    async def _run_proc_json_lint_loop(
        self,
        context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        while True:
            attempt = 1
            events.append(self._node_started(context, "lint_proc_json", attempt=attempt))
            lint_event = await self._run_node(
                context,
                "lint_proc_json",
                self._lint_proc_json,
                attempt=attempt,
            )
            events.append(lint_event)
            if _node_success(context.get("lint_result")):
                return events
            failures = _stage_failures(context, "lint_proc_json", context.get("lint_result"))
            _mark_terminal_failure(
                context,
                category="compiler_error",
                stage="lint_proc_json",
                message="合法 IR 编译出的 proc JSON 未通过 DSL 校验，需要修复确定性编译器或补齐编译能力。",
                failures=failures,
            )
            events.append(self._graph_failed(context))
            return events

    async def _run_ir_dsl_consistency_loop(
        self,
        context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        while True:
            attempt = 1
            events.append(self._node_started(context, "check_ir_dsl_consistency", attempt=attempt))
            check_event = await self._run_node(
                context,
                "check_ir_dsl_consistency",
                self._check_ir_dsl_consistency,
                attempt=attempt,
            )
            events.append(check_event)
            if _node_success(context.get("ir_dsl_consistency_result")):
                return events
            failures = _stage_failures(
                context,
                "check_ir_dsl_consistency",
                context.get("ir_dsl_consistency_result"),
            )
            category = _classify_ir_dsl_consistency_failure(context)
            message = (
                "IR lint 未提前拦截的 lineage 缺口，需要补 IR 校验规则。"
                if category == "ir_linter_gap"
                else "IR 已声明的语义未能被 proc JSON 编译器正确落地，需要补编译器能力。"
            )
            _mark_terminal_failure(
                context,
                category=category,
                stage="check_ir_dsl_consistency",
                message=message,
                failures=failures,
            )
            events.append(self._graph_failed(context))
            return events

    async def _diagnose_and_repair_runtime(
        self,
        context: dict[str, Any],
        *,
        max_retries: int,
        runtime_attempt: int,
    ) -> AsyncIterator[dict[str, Any]]:
        yield self._node_started(context, "diagnose_sample", attempt=runtime_attempt)
        diagnosis_event = await self._run_node(
            context,
            "diagnose_sample",
            self._diagnose_sample,
            attempt=runtime_attempt,
        )
        yield diagnosis_event
        diagnosis = context.get("sample_diagnosis_result") or {}
        if diagnosis.get("terminal") or not diagnosis.get("repair_recommended"):
            _mark_terminal_failure(
                context,
                category="sample_data_issue",
                stage="diagnose_sample",
                message="样例数据诊断为非规则修复问题，已停止自动修复。",
                failures=_stage_failures(context, "diagnose_sample", diagnosis),
            )
            context["runtime_terminal_failure"] = True
            yield self._graph_failed(context)
            return
        async for event in self._repair_ir_and_validate(
            context,
            stage="diagnose_sample",
            failures=_stage_failures(context, "diagnose_sample", diagnosis),
            retry_key="sample_ir_repair_count",
            max_retries=int(context.get("max_sample_ir_repair_attempts") or max_retries),
            exhausted_category="llm_repair_failed",
            exhausted_message="样例执行问题多轮 IR 修复后仍未解决。",
            compile_after_repair=True,
        ):
            yield event
        if context.get("status") == "needs_user_input":
            yield self._needs_user_input_event(context)
            return
        if not context.get("restart_validation_loop"):
            context["runtime_terminal_failure"] = True

    async def _repair_ir_and_validate(
        self,
        context: dict[str, Any],
        *,
        stage: str,
        failures: list[dict[str, Any]],
        retry_key: str,
        max_retries: int,
        exhausted_category: str,
        exhausted_message: str,
        compile_after_repair: bool,
    ) -> AsyncIterator[dict[str, Any]]:
        """Repair only IR, then restart from deterministic IR validation."""
        if not _can_retry_key(context, retry_key, max_retries):
            _mark_terminal_failure(
                context,
                category=exhausted_category,
                stage=stage,
                message=exhausted_message,
                failures=failures,
            )
            yield self._graph_failed(context)
            return

        attempt = int(context.get(retry_key) or 0) + 1
        context[retry_key] = attempt
        normalized_failures = _safe_list_of_dicts(failures)
        if context.pop("last_repair_unchanged", False):
            normalized_failures.append({
                "stage": stage,
                "reason": "previous_repair_no_change",
                "message": "上一轮 repair_ir 返回的 IR 与修复前完全一致，说明修复没有改变失败路径。",
            })
        context["current_repair_stage"] = stage
        context["current_repair_attempt"] = attempt
        context["current_repair_failures"] = normalized_failures
        context["ir_lint_result"] = {
            "success": False,
            "status": "failed",
            "source_stage": stage,
            "errors": normalized_failures,
        }
        yield self._node_started(context, "repair_ir", attempt=attempt)
        repair_event = await self._run_node(context, "repair_ir", self._repair_ir, attempt=attempt)
        yield repair_event
        if _event_node_failed(repair_event):
            yield self._graph_failed(context)
            return

        yield self._node_started(context, "validate_ir_structure", attempt=attempt + 1)
        validation_event = await self._run_node(
            context,
            "validate_ir_structure",
            self._validate_ir_structure,
            attempt=attempt + 1,
        )
        yield validation_event
        if context.get("ir_structure_needs_repair"):
            if _can_retry_key(context, retry_key, max_retries):
                async for event in self._repair_ir_and_validate(
                        context,
                        stage="validate_ir_structure",
                        failures=_stage_failures(
                            context,
                            "validate_ir_structure",
                            {"success": False, "errors": context.get("ir_structure_repair_reasons") or []},
                        ),
                        retry_key=retry_key,
                        max_retries=max_retries,
                        exhausted_category=exhausted_category,
                        exhausted_message=exhausted_message,
                        compile_after_repair=compile_after_repair,
                ):
                    yield event
                return
            _mark_terminal_failure(
                context,
                category="llm_repair_failed",
                stage="validate_ir_structure",
                message="IR 多轮修复后仍未通过结构校验。",
                failures=_stage_failures(
                    context,
                    "validate_ir_structure",
                    {"success": False, "errors": context.get("ir_structure_repair_reasons") or []},
                ),
            )
            yield self._graph_failed(context)
            return

        yield self._node_started(context, "resolve_source_bindings", attempt=attempt + 1)
        bind_event = await self._run_node(
            context,
            "resolve_source_bindings",
            self._resolve_source_bindings,
            attempt=attempt + 1,
        )
        yield bind_event
        if _event_node_failed(bind_event):
            yield self._graph_failed(context)
            return

        yield self._node_started(context, "semantic_resolution", attempt=attempt + 1)
        semantic_event = await self._run_node(
            context,
            "semantic_resolution",
            self._semantic_resolution,
            attempt=attempt + 1,
        )
        yield semantic_event
        if _event_node_failed(semantic_event):
            yield self._graph_failed(context)
            return

        yield self._node_started(context, "ambiguity_gate", attempt=attempt + 1)
        ambiguity_event = await self._run_node(
            context,
            "ambiguity_gate",
            self._ambiguity_gate,
            attempt=attempt + 1,
        )
        yield ambiguity_event
        if context.get("status") == "needs_user_input":
            return

        yield self._node_started(context, "lint_ir", attempt=attempt + 1)
        lint_ir_event = await self._run_node(context, "lint_ir", self._lint_ir, attempt=attempt + 1)
        yield lint_ir_event
        if not _node_success(context.get("ir_lint_result")):
            lint_route = _classify_ir_lint_failure(context)
            if lint_route.get("route") == "needs_user_input":
                _set_ir_lint_questions(context, lint_route.get("errors") or [])
                return
            if _can_retry_key(context, retry_key, max_retries):
                async for event in self._repair_ir_and_validate(
                        context,
                        stage="lint_ir",
                        failures=_stage_failures(context, "lint_ir", context.get("ir_lint_result")),
                        retry_key=retry_key,
                        max_retries=max_retries,
                        exhausted_category=exhausted_category,
                        exhausted_message=exhausted_message,
                        compile_after_repair=compile_after_repair,
                ):
                    yield event
                return
            _mark_terminal_failure(
                context,
                category="ir_error",
                stage="lint_ir",
                message="IR 多轮修复后仍未通过校验。",
                failures=_stage_failures(context, "lint_ir", context.get("ir_lint_result")),
            )
            yield self._graph_failed(context)
            return

        if not compile_after_repair:
            return

        yield self._node_started(context, "generate_proc_json", attempt=attempt + 1)
        generation_event = await self._run_node(
            context,
            "generate_proc_json",
            self._generate_proc_json,
            attempt=attempt + 1,
        )
        yield generation_event
        if _event_node_failed(generation_event):
            yield self._graph_failed(context)
            return
        context["restart_validation_loop"] = True
        return

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
            error = {
                "stage": node_code,
                "node": node_code,
                "message": str(exc),
                "type": exc.__class__.__name__,
            }
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
            "rule_summary": rule_text,
            "target_table": context.get("target_table"),
            "source_references": _fallback_source_references(rule_text),
            "output_specs": [],
            "business_rules": [],
        }
        try:
            parsed = await invoke_llm_json(build_understanding_prompt(context), temperature=0.05, timeout_seconds=45)
            context["understanding"] = normalize_understanding(
                _safe_dict(parsed.get("understanding")) or fallback_understanding,
                rule_text=rule_text,
                target_table=str(context.get("target_table") or ""),
            )
            context["assumptions"] = _safe_list_of_dicts(parsed.get("assumptions"))
            context["ambiguities"] = _safe_list_of_dicts(parsed.get("ambiguities"))
            context["llm_understanding_used"] = True
            return {"message": "已使用 LLM 将规则描述转换为结构化理解。"}
        except Exception as exc:  # noqa: BLE001
            logger.warning("[rule_generation] understand_rule fallback: %s", exc)
            context.setdefault("warnings", []).append(f"规则理解 LLM 不可用，已使用确定性 fallback：{exc}")
            context["understanding"] = normalize_understanding(
                fallback_understanding,
                rule_text=rule_text,
                target_table=str(context.get("target_table") or ""),
            )
            context.setdefault("assumptions", [])
            context.setdefault("ambiguities", [])
        return {"message": "已将规则描述转换为结构化理解。"}

    async def _validate_ir_structure(self, context: dict[str, Any]) -> dict[str, Any]:
        normalized = normalize_understanding(
            context.get("understanding") or {},
            rule_text=str(context.get("rule_text") or ""),
            target_table=str(context.get("target_table") or ""),
        )
        context["understanding"] = normalized
        source_profiles = list(context.get("source_profiles") or [])
        issues = _validate_understanding(
            normalized,
            source_profiles=source_profiles,
            rule_text=str(context.get("rule_text") or ""),
        )
        context["ir_structure_repair_reasons"] = issues
        context["ir_structure_needs_repair"] = bool(issues)
        if issues:
            _replace_stage_error(context, "validate_ir_structure", issues)
            return {
                "success": False,
                "message": "规则理解结构待修复。",
                "summary": {"issue_count": len(issues)},
                "errors": issues,
            }
        _clear_stage_error(context, "validate_ir_structure")
        return {
            "success": True,
            "message": "规则理解结构校验通过。",
            "summary": {
                "source_reference_count": len(normalized.get("source_references") or []),
                "output_spec_count": len(normalized.get("output_specs") or []),
                "business_rule_count": len(normalized.get("business_rules") or []),
            },
        }

    async def _resolve_source_bindings(self, context: dict[str, Any]) -> dict[str, Any]:
        source_profiles = list(context.get("source_profiles") or [])
        source_references = _safe_list_of_dicts((context.get("understanding") or {}).get("source_references"))
        field_bindings = [_bind_source_reference(reference, source_profiles) for reference in source_references]
        context["field_bindings"] = field_bindings
        return {
            "message": "已将源字段引用绑定到数据集字段。",
            "summary": {
                "reference_count": len(source_references),
                "bound_count": len([item for item in field_bindings if item.get("status") == "bound"]),
                "ambiguous_count": len([item for item in field_bindings if item.get("must_bind") and item.get("status") != "bound"]),
            },
        }

    async def _lint_ir(self, context: dict[str, Any]) -> dict[str, Any]:
        result = lint_rule_generation_ir(
            context.get("understanding") or {},
            field_bindings=context.get("field_bindings") or [],
            rule_text=str(context.get("rule_text") or ""),
            source_profiles=list(context.get("source_profiles") or []),
        )
        context["ir_lint_result"] = result
        if result.get("success"):
            _clear_stage_error(context, "lint_ir")
        else:
            _replace_stage_error(context, "lint_ir", result.get("errors") or [])
        return {
            "success": bool(result.get("success")),
            "message": "规则 IR 校验通过。" if result.get("success") else "规则 IR 校验失败。",
            "summary": result.get("summary") or {},
            "errors": result.get("errors") or [],
        }

    async def _repair_ir(self, context: dict[str, Any]) -> dict[str, Any]:
        repair_stage = str(
            context.get("current_repair_stage")
            or (context.get("ir_lint_result") or {}).get("source_stage")
            or "unknown"
        ).strip()
        repair_attempt = int(context.get("current_repair_attempt") or 1)
        failures = _safe_list_of_dicts(context.get("current_repair_failures"))
        if not failures:
            failures = _safe_list_of_dicts((context.get("ir_lint_result") or {}).get("errors"))
        before_understanding = context.get("understanding") or {}
        parsed = await invoke_llm_json(
            build_ir_repair_prompt(context, failures=failures),
            temperature=0.05,
            timeout_seconds=45,
        )
        repaired_understanding = normalize_understanding(
            _safe_dict(parsed.get("understanding")) or {},
            rule_text=str(context.get("rule_text") or ""),
            target_table=str(context.get("target_table") or ""),
        )
        changed = _stable_json(before_understanding) != _stable_json(repaired_understanding)
        context["understanding"] = repaired_understanding
        context["last_repair_unchanged"] = not changed
        _append_repair_history(
            context,
            stage=repair_stage,
            attempt=repair_attempt,
            failures=failures,
            changed_understanding=changed,
            understanding=repaired_understanding,
        )
        logger.info(
            "[rule_generation] repair_ir stage=%s attempt=%s changed=%s failure_reasons=%s",
            repair_stage,
            repair_attempt,
            changed,
            [
                str(item.get("reason") or item.get("type") or item.get("message") or "")[:80]
                for item in failures[:5]
            ],
        )
        if parsed.get("assumptions") is not None:
            context["assumptions"] = _safe_list_of_dicts(parsed.get("assumptions"))
        if parsed.get("ambiguities") is not None:
            context["ambiguities"] = _safe_list_of_dicts(parsed.get("ambiguities"))
        context.pop("ir_lint_result", None)
        return {
            "message": "已修复规则 IR。",
            "summary": {
                "repair_stage": repair_stage,
                "changed_understanding": changed,
                "failure_count": len(failures),
            },
        }

    async def _semantic_resolution(self, context: dict[str, Any]) -> dict[str, Any]:
        assumptions = list(context.get("assumptions") or [])
        ambiguities = _normalize_ambiguity_candidates(
            list(context.get("ambiguities") or []),
            context.get("source_profiles", []),
        )
        understanding = _safe_dict(context.get("understanding"))
        context["source_references"] = _safe_list_of_dicts(understanding.get("source_references"))
        context["output_specs"] = _safe_list_of_dicts(understanding.get("output_specs"))
        context["business_rules"] = _safe_list_of_dicts(understanding.get("business_rules"))
        for binding in list(context.get("field_bindings") or []):
            if not isinstance(binding, dict) or binding.get("status") != "bound":
                continue
            selected_field = binding.get("selected_field")
            if not isinstance(selected_field, dict):
                continue
            role = _normalize_source_reference_role(binding.get("role") or binding.get("usage"))
            assumptions.append({
                "name": FIELD_BINDING_ROLES.get(role, {}).get("label") or "字段绑定",
                "value": str(selected_field.get("name") or ""),
                "display_value": _field_candidate_display(selected_field),
                "confidence": 0.96,
                "reason": "规则描述中的字段引用已通过数据集字段精确绑定。",
            })
        context["assumptions"] = assumptions
        context["ambiguities"] = ambiguities
        return {
            "message": "已自动处理可推断的字段语义。",
            "summary": {
                "assumptions": len(assumptions),
                "ambiguities": len(ambiguities),
            },
        }

    async def _ambiguity_gate(self, context: dict[str, Any]) -> dict[str, Any]:
        questions = []
        asked_roles: set[str] = set()
        for binding in list(context.get("field_bindings") or []):
            if (
                not isinstance(binding, dict)
                or binding.get("status") == "bound"
                or not binding.get("must_bind", True)
            ):
                continue
            role = str(binding.get("role") or binding.get("usage") or "field")
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
        context["status"] = "running"
        return {"message": "未发现需要打断用户的阻塞性业务歧义。", "summary": {"question_count": 0}}

    async def _generate_proc_json(self, context: dict[str, Any]) -> dict[str, Any]:
        rule = build_proc_rule_skeleton_from_ir(
            side=str(context.get("side") or ""),
            target_table=str(context.get("target_table") or ""),
            target_tables=list(context.get("target_tables") or []),
            rule_text=str(context.get("rule_text") or ""),
            sources=context.get("sources") or [],
            understanding=context.get("understanding") or {},
            field_bindings=context.get("field_bindings") or [],
        )
        context["llm_generation_used"] = False
        _apply_generated_proc_rule(context, rule)
        _clear_stage_error(context, "generate_proc_json")
        _clear_runtime_validation_state(context)
        return {
            "message": "已根据 IR 编译当前侧 proc JSON。",
            "summary": {
                "step_count": len((context.get("normalized_rule_json") or {}).get("steps", [])),
                "llm_used": False,
                "generation_mode": "ir_compiler",
            },
        }

    async def _check_ir_dsl_consistency(self, context: dict[str, Any]) -> dict[str, Any]:
        result = check_ir_dsl_consistency(
            context.get("normalized_rule_json") or {},
            understanding=context.get("understanding") or {},
            field_bindings=context.get("field_bindings") or [],
            sources=context.get("sources") or [],
            target_table=context["target_table"],
            target_tables=context.get("target_tables") or [],
            rule_text=str(context.get("rule_text") or ""),
        )
        context["ir_dsl_consistency_result"] = result
        if result.get("success"):
            _clear_stage_error(context, "check_ir_dsl_consistency")
        else:
            _replace_stage_error(context, "check_ir_dsl_consistency", result.get("errors") or [])
        return {
            "success": bool(result.get("success")),
            "message": "规则与 JSON 一致性检查通过。" if result.get("success") else "规则与 JSON 一致性检查失败。",
            "summary": result.get("summary") or {},
            "errors": result.get("errors") or [],
        }

    async def _lint_proc_json(self, context: dict[str, Any]) -> dict[str, Any]:
        result = lint_proc_rule(
            context.get("normalized_rule_json") or {},
            side=context["side"],
            target_table=context["target_table"],
            target_tables=context.get("target_tables") or [],
            sources=context.get("sources", []),
        )
        context["lint_result"] = result
        if not result.get("success"):
            _replace_stage_error(context, "lint_proc_json", result.get("errors") or [])
        else:
            _clear_stage_error(context, "lint_proc_json")
        return {
            "success": bool(result.get("success")),
            "message": "JSON 可执行性校验通过。" if result.get("success") else "JSON 可执行性校验失败。",
            "summary": {"error_count": len(result.get("errors") or []), "warning_count": len(result.get("warnings") or [])},
            "errors": result.get("errors") or [],
        }

    async def _build_sample_inputs(self, context: dict[str, Any]) -> dict[str, Any]:
        sample_inputs = []
        missing_sources: list[str] = []
        for source in context.get("sources", []):
            sample_rows = list(source.get("sample_rows") or [])
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
        sample_errors = _sample_result_errors(result)
        if not (result.get("success") and result.get("ready_for_confirm")):
            _replace_stage_error(context, "run_sample", sample_errors)
        else:
            _clear_stage_error(context, "run_sample")
        run_success = bool(result.get("success") and result.get("ready_for_confirm"))
        return {
            "success": run_success,
            "message": "样例执行通过。" if result.get("success") and result.get("ready_for_confirm") else "样例执行未通过。",
            "summary": {"ready_for_confirm": bool(result.get("ready_for_confirm")), "backend": result.get("backend")},
            "errors": [] if run_success else sample_errors,
        }

    async def _diagnose_sample(self, context: dict[str, Any]) -> dict[str, Any]:
        result = diagnose_proc_sample(
            rule_json=context.get("normalized_rule_json") or {},
            sample_result=context.get("sample_result") or {},
            sample_inputs=context.get("sample_inputs") or context.get("sources") or [],
            expected_target=context["target_table"],
            expected_targets=context.get("target_tables") or [],
            assert_result=context.get("assert_result") if isinstance(context.get("assert_result"), dict) else None,
            rule_text=str(context.get("rule_text") or ""),
        )
        context["sample_diagnosis_result"] = result
        if result.get("diagnostics"):
            _replace_stage_error(context, "diagnose_sample", result.get("errors") or [])
        else:
            _clear_stage_error(context, "diagnose_sample")
        return {
            "success": bool(result.get("success")),
            "message": str(result.get("message") or "样例诊断完成。"),
            "summary": result.get("summary") or {},
            "errors": result.get("errors") or [],
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

    def _graph_completed(self, context: dict[str, Any]) -> dict[str, Any]:
        logger.info(
            "[rule_generation][proc_side] completed run_id=%s side=%s target=%s output_fields=%d output_rows=%d steps=%d",
            context.get("run_id", ""),
            context.get("side", ""),
            context.get("target_table", ""),
            len(context.get("output_fields") or []),
            len(context.get("output_preview_rows") or []),
            len((context.get("normalized_rule_json") or {}).get("steps") or []),
        )
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
            understanding=context.get("understanding") or {},
            source_references=(context.get("understanding") or {}).get("source_references") or [],
            output_specs=(context.get("understanding") or {}).get("output_specs") or [],
            business_rules=(context.get("understanding") or {}).get("business_rules") or [],
            validations=[
                context.get("ir_lint_result") or {},
                context.get("ir_dsl_consistency_result") or {},
                context.get("lint_result") or {},
                context.get("sample_diagnosis_result") or {},
                context.get("assert_result") or {},
            ],
            warnings=context.get("warnings") or [],
        )

    def _graph_failed(self, context: dict[str, Any]) -> dict[str, Any]:
        errors = _all_context_errors(context)
        logger.info(
            "[rule_generation][proc_side] failed run_id=%s side=%s target=%s errors=%s",
            context.get("run_id", ""),
            context.get("side", ""),
            context.get("target_table", ""),
            _log_json(errors[:6]),
        )
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

    def _needs_user_input_event(self, context: dict[str, Any]) -> dict[str, Any]:
        return build_event(
            "needs_user_input",
            run_id=context.get("run_id", ""),
            side=context.get("side", ""),
            target_table=context.get("target_table", ""),
            node_code="ambiguity_gate",
            node_status="needs_user_input",
            message="规则存在需要确认的业务口径。",
            status="needs_user_input",
            phase="ambiguity_gate",
            questions=context.get("questions") or [],
            understanding=context.get("understanding") or {},
            field_bindings=context.get("field_bindings") or [],
            source_references=(context.get("understanding") or {}).get("source_references") or [],
            output_specs=(context.get("understanding") or {}).get("output_specs") or [],
            business_rules=(context.get("understanding") or {}).get("business_rules") or [],
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
        "max_lint_ir_repair_attempts": int(payload.get("max_lint_ir_repair_attempts") or 3),
        "max_sample_ir_repair_attempts": int(payload.get("max_sample_ir_repair_attempts") or 2),
        "errors": [],
        "warnings": [],
        "trace": [],
    }


def _apply_generated_proc_rule(
    context: dict[str, Any],
    rule: dict[str, Any],
    *,
    compile_ir: bool = True,
) -> None:
    context.pop("normalized_rule_json", None)
    context["proc_rule_json"] = rule
    normalized_rule = _normalize_generated_proc_rule(rule)
    if not compile_ir:
        context["normalized_rule_json"] = normalized_rule
        return
    context["normalized_rule_json"] = compile_understanding_into_rule(
        normalized_rule,
        understanding=context.get("understanding") or {},
        field_bindings=context.get("field_bindings") or [],
        sources=context.get("sources") or [],
        target_table=str(context.get("target_table") or ""),
        target_tables=list(context.get("target_tables") or []),
    )


def _source_profile(source: dict[str, Any]) -> dict[str, Any]:
    field_candidates = _field_candidates(source)
    fields = [candidate["name"] for candidate in field_candidates]
    table_name = str(source.get("table_name") or source.get("resource_key") or source.get("id") or "")
    scope_aliases = _source_scope_aliases(source, table_name=table_name)
    return {
        "table_name": table_name,
        "scope_aliases": scope_aliases,
        "field_count": len(fields),
        "fields": fields,
        "field_candidates": field_candidates,
    }


def _source_scope_aliases(source: dict[str, Any], *, table_name: str) -> list[str]:
    aliases: list[str] = []
    for value in (
        table_name,
        source.get("business_name"),
        source.get("dataset_name"),
        source.get("name"),
        source.get("resource_key"),
        source.get("dataset_code"),
        source.get("dataset_id"),
        source.get("source_id"),
        source.get("id"),
    ):
        text = str(value or "").strip()
        if text and text not in aliases:
            aliases.append(text)
    return aliases


FIELD_BINDING_ROLES = {
    "match_key": {"label": "匹配字段"},
    "compare_field": {"label": "对比字段"},
    "time_field": {"label": "时间字段"},
    "filter_field": {"label": "过滤字段"},
    "group_field": {"label": "分组字段"},
    "lookup_key": {"label": "查找字段"},
    "source_value": {"label": "源字段"},
}


FIELD_REFERENCE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("match_key", r"(?P<mention>[^，,。；;\n]{1,30}?)(?:作为|做为|为|是|当作|用作)?(?:匹配字段|匹配键|对账字段|关联字段|主键)"),
    ("compare_field", r"(?P<mention>[^，,。；;\n]{1,30}?)(?:作为|做为|为|是|当作|用作)?(?:对比字段|比较字段|核对字段)"),
    ("time_field", r"(?P<mention>[^，,。；;\n]{1,30}?)(?:作为|做为|为|是|当作|用作)?(?:时间字段|日期字段)"),
    ("filter_field", r"(?P<mention>[^，,。；;\n]{1,30}?)(?:只取|仅取|筛选|过滤|取)(?P<value>[A-Za-z0-9_\-.]+)的数据"),
)


def _fallback_source_references(rule_text: str) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    for usage, pattern in FIELD_REFERENCE_PATTERNS:
        for match in re.finditer(pattern, rule_text or ""):
            semantic_name = _clean_field_mention(match.group("mention"))
            if not semantic_name:
                continue
            references.append({
                "ref_id": f"fallback_{usage}_{len(references) + 1}",
                "semantic_name": semantic_name,
                "usage": usage,
                "must_bind": True,
                "operator": "eq" if "value" in match.groupdict() else "",
                "value": match.group("value") if "value" in match.groupdict() else None,
                "candidate_fields": [],
            })
    return references


def _normalize_source_reference_role(value: Any) -> str:
    role = normalize_source_reference_usage(value)
    return role if role in FIELD_BINDING_ROLES else "source_value"


def _clean_field_mention(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^(把|将|用|按|以|根据|其中|并且|且|同时)", "", text).strip()
    text = re.sub(r"(字段|列|口径)$", "", text).strip()
    return text


def _bind_source_reference(reference: dict[str, Any], source_profiles: list[dict[str, Any]]) -> dict[str, Any]:
    role = _normalize_source_reference_role(reference.get("usage"))
    mention = str(reference.get("semantic_name") or "").strip()
    candidates = _candidate_fields_for_reference(reference, source_profiles)
    match_result = _match_field_mention(mention, candidates)
    llm_candidates = _resolve_llm_field_candidates(
        {"llm_candidates": list(reference.get("candidate_fields") or []), "semantic_name": mention},
        candidates,
    )
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
        "intent_id": str(reference.get("ref_id") or f"{role}_{mention}"),
        "role": role,
        "usage": str(reference.get("usage") or role),
        "mention": mention,
        "description": str(reference.get("description") or "").strip(),
        "operator": reference.get("operator") or "",
        "value": reference.get("value"),
        "must_bind": bool(reference.get("must_bind", True)),
        "table_scope": [str(item).strip() for item in list(reference.get("table_scope") or []) if str(item).strip()],
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
    mention = str(
        intent.get("mention")
        or intent.get("semantic_name")
        or ""
    ).strip()
    normalized_mention = _normalize_text_for_match(mention)
    for hint in list(intent.get("llm_candidates") or []):
        if not isinstance(hint, dict):
            continue
        matched = _find_actual_field_candidate(hint, candidates)
        if not matched:
            continue
        if normalized_mention and not _is_close_field_candidate(normalized_mention, matched):
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
        return not source_table or _candidate_matches_table_scope(candidate, {source_table})

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


def _candidate_fields_for_reference(reference: dict[str, Any], source_profiles: list[dict[str, Any]]) -> list[dict[str, str]]:
    table_scope = {
        str(item).strip()
        for item in list(reference.get("table_scope") or [])
        if str(item).strip()
    }
    all_candidates: list[dict[str, str]] = []
    for profile in source_profiles:
        table_name = str(profile.get("table_name") or "")
        scope_aliases = [
            str(item).strip()
            for item in list(profile.get("scope_aliases") or [])
            if str(item).strip()
        ]
        if table_scope and not _scope_aliases_match(table_scope, scope_aliases or [table_name]):
            continue
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
                "scope_aliases": scope_aliases,
            })
    return _dedupe_field_candidates(all_candidates)


def _candidate_matches_table_scope(candidate: dict[str, Any], table_scope: set[str]) -> bool:
    return _scope_aliases_match(
        table_scope,
        [
            str(candidate.get("table_name") or "").strip(),
            *[
                str(item).strip()
                for item in list(candidate.get("scope_aliases") or [])
                if str(item).strip()
            ],
        ],
    )


def _scope_aliases_match(table_scope: set[str], aliases: list[str]) -> bool:
    if not table_scope:
        return True
    normalized_scope = {_normalize_text_for_match(item) for item in table_scope if item}
    normalized_aliases = {_normalize_text_for_match(item) for item in aliases if item}
    return bool(normalized_scope & normalized_aliases)


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
    role = _normalize_source_reference_role(binding.get("role") or binding.get("usage"))
    status = str(binding.get("status") or "").strip()
    action = "未匹配到数据集字段" if status == "missing" else "未明确对应哪个字段"
    templates = {
        "match_key": f"当前规则中的“{mention}”{action}，请在描述中改为完整、明确的匹配字段中文名。",
        "compare_field": f"当前规则中的“{mention}”{action}，请在描述中改为完整、明确的对比字段中文名。",
        "time_field": f"当前规则中的“{mention}”{action}，请在描述中改为完整、明确的时间字段中文名。",
        "filter_field": f"当前规则中的“{mention}”{action}，请在描述中改为完整、明确的过滤字段中文名。",
        "group_field": f"当前规则中的“{mention}”{action}，请在描述中改为完整、明确的分组字段中文名。",
        "lookup_key": f"当前规则中的“{mention}”{action}，请在描述中改为完整、明确的查找字段中文名。",
        "source_value": f"当前规则中的“{mention}”{action}，请在描述中改为完整、明确的源字段中文名。",
    }
    return templates.get(role, f"当前规则中的“{mention}”{action}，请在描述中改为完整、明确的字段中文名。")


def _validate_understanding(
    understanding: dict[str, Any],
    *,
    source_profiles: list[dict[str, Any]],
    rule_text: str = "",
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    source_references = _safe_list_of_dicts(understanding.get("source_references"))
    output_specs = _safe_list_of_dicts(understanding.get("output_specs"))
    business_rules = _safe_list_of_dicts(understanding.get("business_rules"))

    if not source_references and not output_specs and not business_rules:
        issues.append({
            "message": "规则理解结果为空，未提取出源字段引用、输出定义或业务规则。",
            "reason": "empty_understanding",
        })
        return issues

    for reference in source_references:
        usage = _normalize_source_reference_role(reference.get("usage"))
        semantic_name = str(reference.get("semantic_name") or "").strip()
        must_bind = bool(reference.get("must_bind", True))
        if not semantic_name:
            issues.append({
                "message": "存在缺少 semantic_name 的 source_reference。",
                "reason": "empty_source_reference_name",
                "ref_id": reference.get("ref_id"),
            })
            continue
        if usage not in SOURCE_REFERENCE_USAGES:
            issues.append({
                "message": f"source_reference“{semantic_name}”的 usage 不合法。",
                "reason": "invalid_source_reference_usage",
                "ref_id": reference.get("ref_id"),
            })
            continue
        scope_issue = _validate_reference_table_scope(reference, source_profiles)
        if scope_issue:
            issues.append(scope_issue)
            continue
        candidate_fields = _candidate_fields_for_reference(reference, source_profiles)
        match_result = _match_field_mention(semantic_name, candidate_fields)
        output_alias = _matching_output_definition_name(
            semantic_name,
            output_specs=output_specs,
            rule_text=rule_text,
        )
        if output_alias:
            issues.append({
                "message": (
                    f"source_reference“{semantic_name}”看起来是输出字段“{output_alias}”，"
                    "不是源数据字段。请把等号/为左侧保留为 output_specs.name，"
                    "并从右侧规则中提取真实源字段引用。"
                ),
                "reason": "source_reference_is_output_field_alias",
                "ref_id": reference.get("ref_id"),
                "semantic_name": semantic_name,
                "output_name": output_alias,
                "candidates": [_field_candidate_payload(candidate) for candidate in list(match_result.get("candidates") or [])[:3]],
            })
            continue
        if _source_reference_looks_like_clause(reference, candidate_fields):
            issues.append({
                "message": f"source_reference“{semantic_name}”看起来包含整句条件，不是纯字段短语。",
                "reason": "source_reference_contains_clause",
                "ref_id": reference.get("ref_id"),
                "semantic_name": semantic_name,
                "candidates": [_field_candidate_payload(candidate) for candidate in candidate_fields[:3]],
            })
            continue
        if must_bind and match_result.get("status") == "missing" and not list(match_result.get("candidates") or []):
            issues.append({
                "message": f"source_reference“{semantic_name}”无法映射到任何源字段，可能被错误分到了 source_references。",
                "reason": "source_reference_unmatched_needs_reclassification",
                "ref_id": reference.get("ref_id"),
                "semantic_name": semantic_name,
            })

    for spec in output_specs:
        name = str(spec.get("name") or "").strip()
        kind = normalize_output_spec_kind(spec.get("kind"))
        if not name:
            issues.append({
                "message": "存在缺少 name 的 output_spec。",
                "reason": "empty_output_spec_name",
                "output_id": spec.get("output_id"),
            })
        if kind not in OUTPUT_SPEC_KINDS:
            issues.append({
                "message": f"output_spec“{name or spec.get('output_id') or 'unknown'}”的 kind 不合法。",
                "reason": "invalid_output_spec_kind",
                "output_id": spec.get("output_id"),
            })
            continue

    return issues


def _validate_reference_table_scope(
    reference: dict[str, Any],
    source_profiles: list[dict[str, Any]],
) -> dict[str, Any] | None:
    table_scope = [
        str(item).strip()
        for item in list(reference.get("table_scope") or [])
        if str(item).strip()
    ]
    if not table_scope:
        return None
    valid_scope_groups = _valid_source_scope_groups(source_profiles)
    for scope in table_scope:
        if any(_scope_aliases_match({scope}, group["aliases"]) for group in valid_scope_groups):
            continue
        semantic_name = str(reference.get("semantic_name") or "").strip()
        return {
            "message": f"source_reference“{semantic_name}”的 table_scope 无法匹配任何已选数据集。",
            "reason": "invalid_table_scope",
            "ref_id": reference.get("ref_id"),
            "semantic_name": semantic_name,
            "table_scope": table_scope,
            "valid_table_scopes": valid_scope_groups,
        }
    return None


def _valid_source_scope_groups(source_profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for profile in source_profiles:
        table_name = str(profile.get("table_name") or "").strip()
        aliases = [
            str(item).strip()
            for item in list(profile.get("scope_aliases") or [])
            if str(item).strip()
        ]
        if table_name and table_name not in aliases:
            aliases.insert(0, table_name)
        if not aliases:
            continue
        groups.append({
            "table_name": table_name,
            "aliases": aliases,
        })
    return groups


def _matching_output_definition_name(
    semantic_name: str,
    *,
    output_specs: list[dict[str, Any]],
    rule_text: str,
) -> str:
    normalized_name = _normalize_output_definition_name(semantic_name)
    if not normalized_name:
        return ""
    for spec in output_specs:
        output_name = str(spec.get("name") or "").strip()
        if not output_name:
            continue
        if _normalize_output_definition_name(output_name) != normalized_name:
            continue
        if _rule_text_defines_output_name(rule_text, output_name):
            return output_name
    return ""


def _normalize_output_definition_name(value: Any) -> str:
    normalized = _normalize_text_for_match(value)
    return re.sub(r"(字段|列|口径)$", "", normalized)


def _rule_text_defines_output_name(rule_text: str, output_name: str) -> bool:
    text = str(rule_text or "")
    name = str(output_name or "").strip()
    if not text or not name:
        return False
    escaped_name = re.escape(name)
    return bool(
        re.search(
            rf"(^|[\n\r,，;；。])\s*{escaped_name}\s*(?:字段|列|口径)?\s*(?:=|＝|:=|:|：|为|等于)\s*\S",
            text,
        )
    )


def _source_reference_looks_like_clause(
    reference: dict[str, Any],
    candidates: list[dict[str, str]],
) -> bool:
    semantic_name = str(reference.get("semantic_name") or "").strip()
    if not semantic_name:
        return False
    best = _best_candidate_for_reference_name(semantic_name, candidates)
    if not best:
        return False
    best_term = str(best.get("label") or best.get("name") or "").strip()
    if not best_term:
        return False
    normalized_name = _normalize_text_for_match(semantic_name)
    normalized_best = _normalize_text_for_match(best_term)
    if not normalized_best or normalized_name == normalized_best:
        return False
    return normalized_best in normalized_name and (len(normalized_name) - len(normalized_best)) >= 4


def _best_candidate_for_reference_name(
    semantic_name: str,
    candidates: list[dict[str, str]],
) -> dict[str, str] | None:
    ranked = _rank_field_candidates(semantic_name, candidates)
    return ranked[0] if ranked else None


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
    sources = [_normalize_step_source(source) for source in list(merged.get("sources") or []) if isinstance(source, dict)]
    mappings = [_normalize_mapping(mapping) for mapping in list(merged.get("mappings") or []) if isinstance(mapping, dict)]
    normalized_filter = _normalize_step_filter(
        merged.get("filter"),
        filters=merged.get("filters"),
        sources=sources,
    )
    return {
        **merged,
        "step_id": _step_id(merged, "write_dataset", index),
        "action": "write_dataset",
        "target_table": merged.get("target_table"),
        "sources": sources,
        "mappings": mappings,
        **({"filter": normalized_filter} if normalized_filter else {}),
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
    if value_type == "formula" and isinstance(normalized.get("expr"), dict):
        nested_expr = normalized.get("expr") or {}
        if not normalized.get("bindings") and isinstance(nested_expr.get("bindings"), dict):
            normalized["bindings"] = nested_expr.get("bindings")
        normalized["expr"] = nested_expr.get("expr") or nested_expr.get("formula") or ""
    for key, nested in list(normalized.items()):
        if key in {"source"}:
            continue
        normalized[key] = _normalize_value_node(nested, default_alias=default_alias)
    return normalized


def _normalize_step_filter(
    filter_value: Any,
    *,
    filters: Any,
    sources: list[dict[str, Any]],
) -> dict[str, Any] | None:
    normalized_filter = _normalize_value_node(filter_value) if isinstance(filter_value, dict) else None
    if isinstance(normalized_filter, dict) and normalized_filter:
        return normalized_filter
    filter_items = [item for item in list(filters or []) if isinstance(item, dict)]
    if not filter_items:
        return None
    primary_alias = ""
    if sources:
        primary_alias = str(sources[0].get("alias") or sources[0].get("table") or "").strip()
    bindings: dict[str, Any] = {}
    clauses: list[str] = []
    operator_map = {
        "=": "==",
        "==": "==",
        "!=": "!=",
        "<>": "!=",
        ">": ">",
        ">=": ">=",
        "<": "<",
        "<=": "<=",
    }
    for index, item in enumerate(filter_items, start=1):
        field = str(item.get("field") or "").strip()
        operator = operator_map.get(str(item.get("operator") or "").strip(), "")
        value = item.get("value")
        if not field or not operator or value in {None, ""}:
            continue
        field_token = f"filter_field_{index}"
        value_token = f"filter_value_{index}"
        clauses.append(f"{{{field_token}}} {operator} {{{value_token}}}")
        bindings[field_token] = {
            "type": "source",
            "source": {
                "alias": primary_alias,
                "field": field,
            },
        }
        bindings[value_token] = {
            "type": "formula",
            "expr": repr(str(value)),
        }
    if not clauses:
        return None
    return {
        "type": "formula",
        "expr": " and ".join(clauses),
        "bindings": bindings,
    }


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
    field_candidates = _candidate_fields_for_reference({}, source_profiles)

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
    return None


def _node_completed_message(node_code: str, attempt: int) -> str:
    return f"{NODE_LABELS.get(node_code, node_code)}完成。"


def _node_success(result: Any) -> bool:
    if not isinstance(result, dict) or not result.get("success"):
        return False
    if "ready_for_confirm" in result:
        return bool(result.get("ready_for_confirm"))
    return True


def _event_node_failed(event: dict[str, Any]) -> bool:
    node = event.get("node") if isinstance(event.get("node"), dict) else {}
    return event.get("event") == "node_failed" or node.get("status") == "failed"


def _can_retry_key(context: dict[str, Any], key: str, max_retries: int) -> bool:
    return int(context.get(key) or 0) < max_retries


def _classify_ir_dsl_consistency_failure(context: dict[str, Any]) -> str:
    result = context.get("ir_dsl_consistency_result")
    if not isinstance(result, dict):
        return "compiler_error"
    errors = [item for item in list(result.get("errors") or []) if isinstance(item, dict)]
    if any(str(item.get("reason") or "").strip() == "ir_lineage_missing_for_output" for item in errors):
        return "ir_linter_gap"
    return "compiler_error"


def _classify_ir_lint_failure(context: dict[str, Any]) -> dict[str, Any]:
    result = context.get("ir_lint_result")
    errors = [
        item
        for item in list((result or {}).get("errors") or [])
        if isinstance(item, dict)
    ] if isinstance(result, dict) else []
    user_input_errors = [
        error
        for error in errors
        if _ir_lint_error_needs_user_input(error, rule_text=str(context.get("rule_text") or ""))
    ]
    if user_input_errors:
        return {"route": "needs_user_input", "errors": user_input_errors}
    return {"route": "repair_ir", "errors": errors}


def _ir_lint_error_needs_user_input(error: dict[str, Any], *, rule_text: str) -> bool:
    reason = str(error.get("reason") or "").strip()
    if reason == "aggregate_rule_missing_group_refs":
        return not _rule_text_has_hint(rule_text, r"(按|根据|以|相同|同一|分组|汇总|合并|聚合|累加|求和|统计)")
    if reason == "aggregate_rule_missing_operator":
        return not _rule_text_has_hint(rule_text, r"(累加|求和|合计|汇总|总和|sum|最小|min)")
    if reason == "aggregate_rule_missing_value_ref":
        return not _rule_text_has_hint(rule_text, r"(金额|余额|数量|单价|价|费|款|amount|amt|price|fee|qty)")
    if reason == "output_spec_insufficient_join_lineage":
        return not _rule_text_has_hint(rule_text, r"(关联|匹配|连接|查找|取出|获取|得到|join|lookup)")
    if reason == "output_spec_missing_lookup_value_ref":
        return not _rule_text_has_hint(rule_text, r"(取出|获取|得到|取|读取|输出)")
    if reason == "lookup_key_not_in_aggregate_grain":
        return True
    if reason == "output_spec_missing_expression":
        return not _rule_text_has_hint(rule_text, r"(=|＝|加|减|乘|除|\+|-|\*|/|等于|计算|公式)")
    if reason == "business_rule_missing_filter_predicate":
        return False
    return False


def _rule_text_has_hint(rule_text: str, pattern: str) -> bool:
    return bool(re.search(pattern, str(rule_text or ""), flags=re.IGNORECASE))


def _set_ir_lint_questions(context: dict[str, Any], errors: list[dict[str, Any]]) -> None:
    questions: list[dict[str, Any]] = []
    for index, error in enumerate(errors[:3], start=1):
        role = _ir_lint_question_role(error)
        candidates = [] if role == "business_rule" else [
            _field_candidate_payload(candidate)
            for candidate in _candidate_fields_for_reference({"usage": role}, context.get("source_profiles", []))[:8]
        ]
        questions.append({
            "id": f"ir_lint_{role}_{index}",
            "type": "business_ambiguity",
            "role": role,
            "question": _ir_lint_question_text(error),
            "candidates": candidates,
            "evidence": [str(error.get("message") or "").strip()] if error.get("message") else [],
        })
    context["questions"] = questions
    context["status"] = "needs_user_input"


def _ir_lint_question_role(error: dict[str, Any]) -> str:
    reason = str(error.get("reason") or "").strip()
    if reason == "aggregate_rule_missing_group_refs":
        return "group_field"
    if reason in {"aggregate_rule_missing_value_ref", "output_spec_missing_single_source_ref"}:
        return "source_value"
    if reason == "aggregate_rule_missing_operator":
        return "business_rule"
    if reason == "output_spec_insufficient_join_lineage":
        return "lookup_key"
    if reason == "output_spec_missing_lookup_value_ref":
        return "source_value"
    if reason == "lookup_key_not_in_aggregate_grain":
        return "business_rule"
    if reason == "business_rule_missing_filter_predicate":
        return "filter_field"
    return "business_rule"


def _ir_lint_question_text(error: dict[str, Any]) -> str:
    reason = str(error.get("reason") or "").strip()
    if reason == "aggregate_rule_missing_group_refs":
        return "当前聚合规则缺少分组字段，请在规则描述中明确按哪个字段汇总后重新生成。"
    if reason == "aggregate_rule_missing_operator":
        return "当前聚合规则缺少聚合方式，请明确使用求和、最小值等口径后重新生成。"
    if reason == "aggregate_rule_missing_value_ref":
        return "当前聚合规则缺少被聚合字段，请明确对哪个字段做聚合后重新生成。"
    if reason == "output_spec_insufficient_join_lineage":
        return "当前关联/查找输出缺少关联键或取数字段，请明确如何关联以及取哪个字段后重新生成。"
    if reason == "output_spec_missing_lookup_value_ref":
        return "当前关联/查找输出缺少取数字段，请明确关联后要取哪个字段后重新生成。"
    if reason == "lookup_key_not_in_aggregate_grain":
        return "当前规则先做了聚合，又使用不在聚合分组中的字段做关联取数；请明确输出粒度，或说明该字段需要加入分组，或说明取最早/最晚等聚合口径后重新生成。"
    if reason == "output_spec_missing_expression":
        return "当前计算输出缺少可执行计算逻辑，请明确字段如何计算后重新生成。"
    if reason == "business_rule_missing_filter_predicate":
        return "当前过滤规则缺少过滤条件，请明确保留或排除哪些数据后重新生成。"
    return "当前规则缺少会影响结果的业务信息，请补充完整规则描述后重新生成。"


def _stage_failures(context: dict[str, Any], stage: str, result: Any) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    if isinstance(result, dict):
        for diagnostic in list(result.get("diagnostics") or []):
            if isinstance(diagnostic, dict):
                failures.append({"stage": stage, **diagnostic})
        for error in list(result.get("errors") or []):
            if isinstance(error, dict):
                failures.append({"stage": stage, **error})
            else:
                failures.append({"stage": stage, "message": str(error)})
        message = str(result.get("error") or result.get("message") or "").strip()
        if message and not failures:
            failures.append({"stage": stage, "message": message})
    if not failures:
        failures = [
            item
            for item in list(context.get("errors") or [])
            if isinstance(item, dict) and str(item.get("stage") or "") == stage
        ]
    if not failures:
        failures.append({"stage": stage, "message": f"{stage} 校验失败。"})
    return failures


def _mark_terminal_failure(
    context: dict[str, Any],
    *,
    category: str,
    stage: str,
    message: str,
    failures: list[dict[str, Any]],
) -> None:
    context["failure_category"] = category
    normalized_failures = [item for item in failures if isinstance(item, dict)]
    normalized_failures.append({
        "stage": stage,
        "category": category,
        "terminal": True,
        "message": message,
    })
    _replace_stage_error(context, stage, normalized_failures)


def _sample_result_errors(result: dict[str, Any]) -> list[dict[str, Any]]:
    errors = [item for item in list(result.get("errors") or []) if isinstance(item, dict)]
    if errors:
        return errors
    messages = []
    for warning in list(result.get("warnings") or []):
        text = str(warning or "").strip()
        if text:
            messages.append(text)
    for key in ("error", "message", "summary"):
        text = str(result.get(key) or "").strip()
        if text:
            messages.append(text)
    if not messages:
        messages.append("样例执行未通过")
    return [{"message": message} for message in dict.fromkeys(messages)]


def _clear_runtime_validation_state(context: dict[str, Any]) -> None:
    for key in (
        "lint_result",
        "ir_dsl_consistency_result",
        "sample_input_result",
        "sample_result",
        "sample_diagnosis_result",
        "assert_result",
        "output_fields",
        "output_preview_rows",
    ):
        context.pop(key, None)
    for stage in ("lint_proc_json", "check_ir_dsl_consistency", "build_sample_inputs", "run_sample", "diagnose_sample", "assert_output"):
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
    for stage, key in (
        ("check_ir_dsl_consistency", "ir_dsl_consistency_result"),
        ("lint_proc_json", "lint_result"),
        ("build_sample_inputs", "sample_input_result"),
        ("run_sample", "sample_result"),
        ("diagnose_sample", "sample_diagnosis_result"),
        ("assert_output", "assert_result"),
    ):
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


def _append_repair_history(
    context: dict[str, Any],
    *,
    stage: str,
    attempt: int,
    failures: list[dict[str, Any]],
    changed_understanding: bool,
    understanding: dict[str, Any],
) -> None:
    history = [
        item
        for item in list(context.get("repair_history") or [])
        if isinstance(item, dict)
    ]
    history.append({
        "stage": stage,
        "attempt": attempt,
        "changed_understanding": changed_understanding,
        "failure_reasons": [
            str(item.get("reason") or item.get("type") or "").strip()
            for item in failures
            if str(item.get("reason") or item.get("type") or "").strip()
        ][:8],
        "failure_messages": [
            str(item.get("message") or "").strip()
            for item in failures
            if str(item.get("message") or "").strip()
        ][:8],
        "understanding_summary": _understanding_summary(understanding),
    })
    context["repair_history"] = history[-6:]


def _understanding_summary(understanding: dict[str, Any]) -> dict[str, Any]:
    source_references = _safe_list_of_dicts((understanding or {}).get("source_references"))
    output_specs = _safe_list_of_dicts((understanding or {}).get("output_specs"))
    business_rules = _safe_list_of_dicts((understanding or {}).get("business_rules"))
    return {
        "source_references": [
            {
                "ref_id": item.get("ref_id"),
                "semantic_name": item.get("semantic_name"),
                "usage": item.get("usage"),
                "table_scope": item.get("table_scope") or [],
            }
            for item in source_references[:12]
        ],
        "output_specs": [
            {
                "output_id": item.get("output_id"),
                "name": item.get("name"),
                "kind": item.get("kind"),
                "source_ref_ids": item.get("source_ref_ids") or [],
                "rule_ids": item.get("rule_ids") or [],
            }
            for item in output_specs[:12]
        ],
        "business_rules": [
            {
                "rule_id": item.get("rule_id"),
                "type": item.get("type"),
                "related_ref_ids": item.get("related_ref_ids") or [],
                "output_ids": item.get("output_ids") or [],
            }
            for item in business_rules[:12]
        ],
    }


def _stable_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except TypeError:
        return json.dumps(str(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _log_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        return str(value)


def _truncate_log_text(value: Any, *, limit: int = 320) -> str:
    text = str(value or "").replace("\n", "\\n")
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def _source_log_summary(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for source in list(sources or []):
        if not isinstance(source, dict):
            continue
        sample_rows = [row for row in list(source.get("sample_rows") or []) if isinstance(row, dict)]
        fields = source.get("fields") if isinstance(source.get("fields"), list) else []
        summary.append({
            "id": source.get("id") or source.get("dataset_id") or source.get("source_id"),
            "table": source.get("table_name") or source.get("resource_key") or source.get("dataset_code"),
            "business_name": source.get("business_name") or source.get("dataset_name") or source.get("name"),
            "field_count": len(fields),
            "sample_rows": len(sample_rows),
        })
    return summary


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
