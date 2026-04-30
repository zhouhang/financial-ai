"""LLM 工厂 — 根据 LLM_PROVIDER 配置创建对应的 ChatOpenAI 实例。

支持的提供商：openai / qwen / deepseek
三者均兼容 OpenAI 接口，统一使用 ChatOpenAI 类。
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from langchain_openai import ChatOpenAI

from config import (
    LLM_PROVIDER,
    OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL,
    QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL,
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
)

logger = logging.getLogger(__name__)

# 提供商 → (api_key, base_url, model) 的映射
_PROVIDER_MAP: dict[str, tuple[str, str, str]] = {
    "openai": (OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL),
    "qwen": (QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL),
    "deepseek": (DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL),
}

_PLACEHOLDER_MARKERS = (
    "your-key",
    "your-qwen-key",
    "your-openai-key",
    "sk-your",
    "replace-me",
    "placeholder",
    "demo-key",
    "example-key",
)


def _is_effective_api_key(api_key: str) -> bool:
    normalized = str(api_key or "").strip()
    if not normalized:
        return False
    lowered = normalized.lower()
    return not any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


def get_available_llm_providers(*, preferred: str | None = None) -> list[str]:
    """返回当前已配置 API Key 的 provider 顺序。

    Args:
        preferred: 优先放在第一位的 provider，为 None 时使用全局默认值。
    """
    preferred_name = (preferred or LLM_PROVIDER).lower().strip()
    ordered_names = [preferred_name, "qwen", "openai", "deepseek"]

    available: list[str] = []
    seen: set[str] = set()
    for name in ordered_names:
        if name in seen or name not in _PROVIDER_MAP:
            continue
        seen.add(name)
        api_key, _, _ = _PROVIDER_MAP[name]
        if _is_effective_api_key(api_key):
            available.append(name)
    return available


def get_llm(
    *,
    provider: str | None = None,
    temperature: float = 0.3,
    model_kwargs: dict[str, Any] | None = None,
    extra_body: dict[str, Any] | None = None,
) -> ChatOpenAI:
    """获取 LLM 实例。

    Args:
        provider: 指定提供商，为 None 时使用 .env 中的 LLM_PROVIDER。
        temperature: 温度参数。
    """
    name = (provider or LLM_PROVIDER).lower().strip()
    if name not in _PROVIDER_MAP:
        logger.warning(f"未知的 LLM 提供商 '{name}'，回退到 openai")
        name = "openai"

    api_key, base_url, model = _PROVIDER_MAP[name]

    if not _is_effective_api_key(api_key):
        raise ValueError(
            f"LLM 提供商 '{name}' 的 API Key 未配置或仍为占位符，"
            f"请在 .env 中设置 {name.upper()}_API_KEY"
        )

    logger.info(f"创建 LLM 实例: provider={name}, model={model}, streaming=True")
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        streaming=True,  # 启用流式输出
        request_timeout=60,
        model_kwargs=model_kwargs or {},
        extra_body=extra_body,
    )
