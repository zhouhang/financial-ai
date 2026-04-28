"""LLM JSON invocation helpers for rule generation."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from utils.llm import get_available_llm_providers, get_llm

logger = logging.getLogger(__name__)


class LlmJsonGenerationError(RuntimeError):
    """Raised when no configured LLM provider returns parseable JSON."""


async def invoke_llm_json(
    prompt: str,
    *,
    temperature: float = 0.05,
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    """Invoke the first available LLM provider and parse a JSON object response."""
    provider_errors: list[str] = []
    providers = get_available_llm_providers()
    if not providers:
        raise LlmJsonGenerationError("未配置可用 LLM provider")

    for provider in providers:
        try:
            logger.info("[rule_generation] invoke LLM provider=%s", provider)
            llm = get_llm(provider=provider, temperature=temperature)
            response = await asyncio.wait_for(
                asyncio.to_thread(llm.invoke, prompt),
                timeout=timeout_seconds,
            )
            content = getattr(response, "content", "")
            if isinstance(content, list):
                content = "".join(str(getattr(item, "text", item)) for item in content)
            return parse_json_content(str(content or ""))
        except Exception as exc:  # noqa: BLE001
            message = f"{provider}: {exc}"
            provider_errors.append(message)
            logger.warning("[rule_generation] provider failed: %s", message)
    raise LlmJsonGenerationError("; ".join(provider_errors) or "LLM JSON 生成失败")


def parse_json_content(content: str) -> dict[str, Any]:
    """Parse a JSON object from an LLM response, allowing markdown fences."""
    text = content.strip()
    if not text:
        raise ValueError("模型未返回内容")
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = _decode_first_json_object(text)
    if not isinstance(parsed, dict):
        raise ValueError("模型返回内容不是 JSON 对象")
    return parsed


def _decode_first_json_object(text: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for start in [index for index, char in enumerate(text) if char == "{"]:
        try:
            value, _ = decoder.raw_decode(text[start:])
            if isinstance(value, dict):
                return value
        except Exception:
            continue
    raise ValueError("返回内容中未找到可解析的 JSON 对象")
