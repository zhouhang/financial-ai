"""
Rules MCP 工具定义和实现。

- get_rule         : 从 rule_detail 表获取指定 rule_code 的规则详情
- list_user_tasks  : 获取当前用户可用的任务列表及其下属规则
"""
from __future__ import annotations

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
                "required": ["rule_code", "auth_token"],
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


def _infer_task_type(rule_payload: Any) -> str:
    """根据规则 JSON 结构推断任务入口。"""
    rule_obj = rule_payload
    if not isinstance(rule_obj, dict):
        return "proc"
    if "role_desc" in rule_obj or "merge_rules" in rule_obj:
        return "proc"
    if "global_settings" in rule_obj and "rules" in rule_obj:
        return "recon"
    return "proc"


def _normalize_task_type(rule_type: Any, rule_payload: Any) -> str:
    """优先使用表中 rule_type，缺失时再回退到规则内容推断。"""
    if isinstance(rule_type, str):
        normalized = rule_type.strip().lower()
        if normalized in {"proc", "recon"}:
            return normalized
    return _infer_task_type(rule_payload)


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
                SELECT id, user_id, task_id, rule_code, name, rule, rule_type, remark
                FROM rule_detail
                WHERE rule_code = %s
                  AND (user_id = %s OR user_id IS NULL)
                ORDER BY CASE WHEN user_id = %s THEN 0 ELSE 1 END, id DESC
                LIMIT 1
            """
            cur.execute(sql, (rule_code, user_id, user_id))
        else:
            sql = """
                SELECT id, user_id, task_id, rule_code, name, rule, rule_type, remark
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
            "task_id": row[2],
            "rule_code": row[3],
            "name": row[4],
            "rule": row[5],
            "rule_type": row[6],
            "remark": row[7],
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
            SELECT
                ut.id,
                ut.user_id,
                ut.task_code,
                ut.task_name,
                ut.description,
                rd.id,
                rd.user_id,
                rd.task_id,
                rd.rule_code,
                rd.name,
                rd.rule,
                rd.rule_type,
                rd.remark
            FROM user_tasks AS ut
            LEFT JOIN rule_detail AS rd
              ON rd.task_id = ut.id
             AND rd.rule_type IN ('proc', 'recon')
             AND (rd.user_id = %s OR rd.user_id IS NULL)
            WHERE ut.user_id = %s
            ORDER BY ut.id ASC, rd.id ASC
            """,
            (user_id, user_id),
        )
        rows = cur.fetchall()
        cur.close()

        task_map: Dict[int, Dict[str, Any]] = {}
        tasks: List[Dict[str, Any]] = []

        for row in rows:
            task_id = row[0]
            task = task_map.get(task_id)
            if task is None:
                task = {
                    "id": row[0],
                    "user_id": row[1],
                    "task_code": row[2],
                    "task_name": row[3],
                    "description": row[4],
                    "task_type": "proc",
                    "rules": [],
                }
                task_map[task_id] = task
                tasks.append(task)

            rule_id = row[5]
            if rule_id is None:
                continue

            rule_payload = row[10] or {}
            task_type = _normalize_task_type(row[11], rule_payload)
            task["task_type"] = task_type
            file_rule_code = ""
            if isinstance(rule_payload, dict):
                file_rule_code = str(rule_payload.get("file_rule_code") or "")

            task["rules"].append(
                {
                    "id": row[5],
                    "user_id": row[6],
                    "task_id": row[7],
                    "rule_code": row[8],
                    "name": row[9],
                    "rule_type": row[11],
                    "remark": row[12],
                    "task_code": row[2],
                    "task_name": row[3],
                    "task_type": task_type,
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
    if not auth_token:
        return {"success": False, "error": "未提供认证 token，请先登录"}

    user = get_user_from_token(auth_token)
    if not user:
        return {"success": False, "error": "token 无效或已过期，请重新登录"}

    user_id = str(user.get("user_id") or user.get("id") or "")
    if not user_id:
        return {"success": False, "error": "token 中缺少用户标识"}

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
