"""
Rules MCP 工具定义和实现。

- get_rule         : 从 rule_detail 表获取指定 rule_code 的规则详情
- list_user_tasks   : 获取当前用户可用的任务列表
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from mcp import Tool

from auth.jwt_utils import get_user_from_token
from db_config import get_db_connection

logger = logging.getLogger("tools.rules")

_rule_cache: Dict[Tuple[str, Optional[str]], Optional[Dict[str, Any]]] = {}


def create_tools() -> list[Tool]:
    """创建 Rules MCP 工具列表。"""
    return [
        Tool(
            name="get_rule",
            description="从 rule_detail 表获取指定 rule_code 的规则详情。",
            inputSchema={
                "type": "object",
                "properties": {
                    "rule_code": {
                        "type": "string",
                        "description": "规则编码（rule_code）",
                    },
                    "auth_token": {
                        "type": "string",
                        "description": "JWT token，用于优先匹配当前用户的规则（可选）",
                    },
                },
                "required": ["rule_code"],
            },
        ),
        Tool(
            name="list_user_tasks",
            description="获取当前用户可用的任务列表。需要登录 token。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {
                        "type": "string",
                        "description": "JWT token，用户登录后获取的身份证书",
                    },
                },
                "required": ["auth_token"],
            },
        ),
    ]


async def handle_tool_call(name: str, arguments: dict) -> dict:
    """统一工具调用入口。"""
    try:
        if name == "get_rule":
            return await _handle_get_rule(arguments)
        if name == "list_user_tasks":
            return await _handle_list_user_tasks(arguments)
        return {"error": f"未知的工具: {name}"}
    except Exception as e:
        logger.error(f"工具调用失败 [{name}]: {e}", exc_info=True)
        return {"error": f"工具调用失败: {str(e)}"}


def _normalize_rule_payload(rule_payload: Any) -> Any:
    """将数据库中的 JSON 规则统一为 Python 对象。"""
    if isinstance(rule_payload, str):
        try:
            return json.loads(rule_payload)
        except json.JSONDecodeError:
            return rule_payload
    return rule_payload


def _infer_task_type(rule_payload: Any) -> str:
    """根据规则 JSON 结构推断任务入口。"""
    rule_obj = _normalize_rule_payload(rule_payload)
    if not isinstance(rule_obj, dict):
        return "proc"
    if "role_desc" in rule_obj or "merge_rules" in rule_obj:
        return "proc"
    if "global_settings" in rule_obj and "rules" in rule_obj:
        return "recon"
    return "proc"


def get_rule(rule_code: str, user_id: str | None = None) -> Optional[Dict[str, Any]]:
    """从 rule_detail 表获取指定 rule_code 的规则完整记录。"""
    cache_key = (rule_code, user_id)
    if cache_key in _rule_cache:
        logger.info(f"[Cache] 命中缓存: rule_code={rule_code}, user_id={user_id}")
        return _rule_cache[cache_key]

    conn = None
    try:
        logger.info(f"[SQL] 查询 rule_detail: rule_code={rule_code}, user_id={user_id}")
        conn = get_db_connection()
        cur = conn.cursor()

        if user_id:
            sql = """
                SELECT id, user_id, rule_code, rule, rule_type, remark
                FROM rule_detail
                WHERE rule_code = %s
                  AND (user_id = %s OR user_id IS NULL)
                ORDER BY CASE WHEN user_id = %s THEN 0 ELSE 1 END, id DESC
                LIMIT 1
            """
            cur.execute(sql, (rule_code, user_id, user_id))
        else:
            sql = """
                SELECT id, user_id, rule_code, rule, rule_type, remark
                FROM rule_detail
                WHERE rule_code = %s
                  AND user_id IS NULL
                ORDER BY id DESC
                LIMIT 1
            """
            cur.execute(sql, (rule_code,))

        row = cur.fetchone()
        cur.close()

        if row is None:
            logger.warning(f"[SQL] 未找到规则: rule_code={rule_code}, user_id={user_id}")
            _rule_cache[cache_key] = None
            return None

        result = {
            "id": row[0],
            "user_id": row[1],
            "rule_code": row[2],
            "rule": _normalize_rule_payload(row[3]),
            "rule_type": row[4],
            "remark": row[5],
        }
        _rule_cache[cache_key] = result
        return result
    except Exception as e:
        logger.error(f"[SQL] 查询 rule_detail 失败: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()


def _get_user_tasks(user_id: str) -> List[Dict[str, Any]]:
    """从 user_tasks 表获取当前用户可用任务。"""
    conn = None
    try:
        logger.info(f"[SQL] 开始查询任务列表: user_id={user_id}")
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, user_id, task_code, task_name, description
            FROM user_tasks
            WHERE user_id = %s OR user_id IS NULL
            ORDER BY id ASC
            """,
            (user_id,),
        )
        rows = cur.fetchall()
        cur.close()

        tasks: List[Dict[str, Any]] = []
        for row in rows:
            rule_detail = get_rule(row[2], user_id=user_id)
            if rule_detail is None:
                logger.warning(f"[SQL] 跳过未配置 rule_detail 的任务: task_code={row[2]}")
                continue

            rule_payload = rule_detail.get("rule") or {}
            file_rule_code = ""
            if isinstance(rule_payload, dict):
                file_rule_code = str(rule_payload.get("file_rule_code") or "")

            tasks.append(
                {
                    "id": row[0],
                    "user_id": row[1],
                    "task_code": row[2],
                    "task_name": row[3],
                    "description": row[4],
                    "task_type": _infer_task_type(rule_payload),
                    "file_rule_code": file_rule_code,
                }
            )

        logger.info(f"[SQL] 查询任务列表成功，返回 {len(tasks)} 条记录")
        return tasks
    except Exception as e:
        logger.error(f"[SQL] 获取任务列表失败: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()


async def _handle_get_rule(arguments: dict) -> dict:
    rule_code = arguments.get("rule_code", "").strip()
    auth_token = arguments.get("auth_token", "").strip()

    if not rule_code:
        return {"success": False, "error": "rule_code 不能为空"}

    user_id = None
    if auth_token:
        user = get_user_from_token(auth_token)
        if user:
            user_id = str(user.get("user_id") or user.get("id") or "")
            if not user_id:
                user_id = None

    try:
        rule = get_rule(rule_code, user_id=user_id)
        if rule is None:
            return {
                "success": False,
                "rule_code": rule_code,
                "error": f"未找到 rule_code 为 '{rule_code}' 的规则",
            }
        return {
            "success": True,
            "rule_code": rule_code,
            "data": rule,
            "message": "成功获取规则",
        }
    except Exception as e:
        logger.error(f"获取规则失败: {e}")
        return {"success": False, "error": f"获取规则失败: {str(e)}"}


async def _handle_list_user_tasks(arguments: dict) -> dict:
    auth_token = arguments.get("auth_token", "").strip()
    if not auth_token:
        return {"success": False, "error": "未提供认证 token，请先登录"}

    user = get_user_from_token(auth_token)
    if not user:
        return {"success": False, "error": "token 无效或已过期，请重新登录"}

    user_id = str(user.get("user_id") or user.get("id") or "")
    if not user_id:
        return {"success": False, "error": "token 中缺少用户标识"}

    try:
        tasks = _get_user_tasks(user_id)
        return {
            "success": True,
            "count": len(tasks),
            "tasks": tasks,
            "message": f"成功获取 {len(tasks)} 个任务",
        }
    except Exception as e:
        logger.error(f"获取任务列表失败: {e}")
        return {"success": False, "error": f"获取任务列表失败: {str(e)}"}
