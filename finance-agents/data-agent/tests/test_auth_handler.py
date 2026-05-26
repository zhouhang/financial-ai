from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import HumanMessage


DATA_AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(DATA_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(DATA_AGENT_ROOT))

from graphs.main_graph import nodes


class _FakeLlm:
    def __init__(self, content: str) -> None:
        self.content = content

    def invoke(self, messages: list[object]) -> SimpleNamespace:
        return SimpleNamespace(content=self.content)


def test_guest_register_intent_returns_inline_register_form(monkeypatch) -> None:
    async def fake_list_company(*args: object, **kwargs: object) -> dict[str, object]:
        return {"companies": [{"id": "company-1", "name": "测试公司"}]}

    monkeypatch.setattr(nodes, "get_llm", lambda: _FakeLlm('{"intent": "show_register_form"}'))
    monkeypatch.setattr(nodes, "list_company", fake_list_company)

    result = asyncio.run(nodes.auth_handler({"messages": [HumanMessage(content="我要注册")]}))

    assert result is not None
    content = result["messages"][0].content
    assert '<form id="select_company-form"' in content
    assert "用户注册 - 第1步：选择公司" in content
    assert "测试公司" in content
