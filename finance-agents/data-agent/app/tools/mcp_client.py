"""调用 finance-mcp 对账工具的 HTTP 客户端包装器。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx

from app.config import (
    FINANCE_MCP_BASE_URL,
    RECONCILIATION_CONFIG_FILE,
    RECONCILIATION_SCHEMA_DIR,
)

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(120.0, connect=10.0)


# ---------------------------------------------------------------------------
# 底层：通过 SSE/messages 端点调用 MCP 工具
# ---------------------------------------------------------------------------

async def call_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """通过 HTTP API 调用 finance-mcp 工具。

    unified_mcp_server 通过 SSE+MCP 协议暴露工具。为了简化，
    我们在本地复制 reconciliation_start / reconciliation_status / 
    reconciliation_result 的工具处理器逻辑，调用 MCP 服务器的
    REST 类似端点（如果可用），或回退到直接 HTTP 调用。
    """
    url = f"{FINANCE_MCP_BASE_URL}/mcp"
    # MCP 服务器使用 SSE 传输，直接调用比较复杂。
    # 相反，当 MCP 服务器位于同一位置时，我们导入并在进程中调用
    # 工具处理器，或使用 httpx 进行远程调用。
    # 目前，我们使用直接导入方法，因为两个服务都在
    # 同一台机器上运行。
    try:
        return await _call_tool_in_process(tool_name, arguments)
    except Exception:
        logger.warning("进程内 MCP 调用失败，回退到 HTTP", exc_info=True)
        return await _call_tool_http(tool_name, arguments)


async def _call_tool_in_process(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """导入 finance-mcp 工具处理器并直接调用。"""
    import sys
    # 添加 finance-mcp 到路径，以便我们可以导入其模块
    mcp_root = str(Path(__file__).resolve().parents[3] / "finance-mcp")
    if mcp_root not in sys.path:
        sys.path.insert(0, mcp_root)

    from reconciliation.mcp_server.tools import handle_tool_call  # type: ignore
    result = await handle_tool_call(tool_name, arguments)
    return result


async def _call_tool_http(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """回退：POST 到简单的 JSON-RPC 风格端点。

    这假设 MCP 服务器已扩展了 /tool_call 端点，
    或者我们通过健康端点 + 直接逻辑模拟调用。
    为了健壮性，我们只是抛出异常，让调用者知道 HTTP 路径不可用。
    """
    raise NotImplementedError("基于 HTTP 的 MCP 工具调用未实现；使用进程内调用")


# ---------------------------------------------------------------------------
# 高级辅助函数
# ---------------------------------------------------------------------------

async def start_reconciliation(reconciliation_type: str, files: list[str]) -> dict[str, Any]:
    """通过 MCP 工具启动对账任务。"""
    return await call_mcp_tool("reconciliation_start", {
        "reconciliation_type": reconciliation_type,
        "files": files,
    })


async def get_reconciliation_status(task_id: str) -> dict[str, Any]:
    """轮询对账任务状态。"""
    return await call_mcp_tool("reconciliation_status", {"task_id": task_id})


async def get_reconciliation_result(task_id: str) -> dict[str, Any]:
    """获取对账结果。"""
    return await call_mcp_tool("reconciliation_result", {"task_id": task_id})


async def list_reconciliation_tasks() -> dict[str, Any]:
    """列出所有对账任务。"""
    return await call_mcp_tool("reconciliation_list_tasks", {})


# ---------------------------------------------------------------------------
# 模式/配置辅助函数（本地文件访问）
# ---------------------------------------------------------------------------

def _load_json_with_comments(path: str) -> dict:
    """加载可能包含 // 或 /* */ 注释的 JSON 文件。

    注意：需要跳过字符串内部的 // 和 /* */，避免破坏 URL 等内容。
    """
    text = Path(path).read_text(encoding="utf-8")

    result: list[str] = []
    i = 0
    in_string = False
    while i < len(text):
        ch = text[i]
        # 处理字符串内部（跳过转义字符）
        if in_string:
            result.append(ch)
            if ch == '\\' and i + 1 < len(text):
                result.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        # 字符串开始
        if ch == '"':
            in_string = True
            result.append(ch)
            i += 1
            continue
        # 多行注释 /* ... */
        if ch == '/' and i + 1 < len(text) and text[i + 1] == '*':
            end = text.find('*/', i + 2)
            i = end + 2 if end != -1 else len(text)
            continue
        # 单行注释 // ...
        if ch == '/' and i + 1 < len(text) and text[i + 1] == '/':
            end = text.find('\n', i + 2)
            i = end if end != -1 else len(text)
            continue
        result.append(ch)
        i += 1

    return json.loads("".join(result))


def list_available_rules() -> list[dict[str, str]]:
    """从配置文件返回对账类型的列表。"""
    try:
        config = _load_json_with_comments(RECONCILIATION_CONFIG_FILE)
        return [
            {"name_cn": t.get("name_cn", ""), "type_key": t.get("type_key", "")}
            for t in config.get("types", [])
        ]
    except Exception as e:
        logger.error(f"加载对账配置失败: {e}")
        return []


def load_schema_by_type(type_key: str) -> dict[str, Any] | None:
    """根据 type_key 加载对账模式。"""
    try:
        config = _load_json_with_comments(RECONCILIATION_CONFIG_FILE)
        for t in config.get("types", []):
            if t.get("type_key") == type_key:
                schema_filename = t.get("schema_path", "")
                schema_path = Path(RECONCILIATION_SCHEMA_DIR) / schema_filename
                if schema_path.exists():
                    return _load_json_with_comments(str(schema_path))
        return None
    except Exception as e:
        logger.error(f"加载 {type_key} 的模式失败: {e}")
        return None


def save_schema_to_config(name_cn: str, type_key: str, schema: dict[str, Any]) -> str:
    """保存新的模式 JSON 文件并将其注册到配置中。

    返回模式文件名。
    """
    schema_filename = f"{type_key}_schema.json"
    schema_path = Path(RECONCILIATION_SCHEMA_DIR) / schema_filename

    # 写入模式文件
    schema_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")

    # 更新配置
    config = _load_json_with_comments(RECONCILIATION_CONFIG_FILE)
    types_list: list[dict] = config.get("types", [])

    # 检查 type_key 是否已存在
    existing = next((t for t in types_list if t.get("type_key") == type_key), None)
    if existing:
        existing["name_cn"] = name_cn
        existing["schema_path"] = schema_filename
    else:
        types_list.append({
            "name_cn": name_cn,
            "type_key": type_key,
            "schema_path": schema_filename,
            "callback_url": "",
        })

    config["types"] = types_list
    Path(RECONCILIATION_CONFIG_FILE).write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return schema_filename
