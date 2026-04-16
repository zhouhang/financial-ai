"""
Rules MCP 工具定义和实现。

- get_rule         : 从 rule_detail 表获取指定 rule_code 的规则详情
- list_user_tasks  : 获取当前用户可用的任务列表及其下属规则
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from mcp import Tool

from auth.jwt_utils import get_user_from_token
from db_config import get_db_connection

logger = logging.getLogger("tools.rules")

RULE_CACHE_TTL_SECONDS = 5
_rule_cache: Dict[Tuple[str, Optional[str]], Tuple[float, Optional[Dict[str, Any]]]] = {}
_ALLOWED_ENTRY_MODES = {"upload", "dataset"}


def _normalize_db_user_id(user_id: Any) -> Optional[str]:
    """Normalize user_id before touching UUID columns.

    Scheduler/system tokens may use non-UUID principals such as
    ``finance-cron:<company_id>``. Those values cannot be compared with
    ``rule_detail.user_id`` and should be treated as system context.
    """
    text = str(user_id or "").strip()
    if not text:
        return None
    try:
        return str(uuid.UUID(text))
    except (ValueError, TypeError, AttributeError):
        return None


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
            name="save_rule",
            description="保存或更新 rule_detail 规则记录。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {
                        "type": "string",
                        "description": "JWT token，用户登录后获取的身份证书",
                    },
                    "rule_code": {
                        "type": "string",
                        "description": "规则编码（全局唯一）",
                    },
                    "name": {
                        "type": "string",
                        "description": "规则名称",
                    },
                    "rule": {
                        "type": "object",
                        "description": "规则 JSON",
                    },
                    "rule_type": {
                        "type": "string",
                        "description": "规则类型：file/proc/recon",
                    },
                    "remark": {
                        "type": "string",
                        "description": "备注",
                    },
                    "task_id": {
                        "type": ["integer", "null"],
                        "description": "可选：关联任务 ID",
                    },
                    "supported_entry_modes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "可选：规则支持的入口模式 ['upload','dataset']",
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": "若 rule_code 已存在，是否覆盖当前用户自己的规则",
                    },
                },
                "required": ["auth_token", "rule_code", "name", "rule", "rule_type"],
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
        if name == "save_rule":
            return await _handle_save_rule(arguments)
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
    rules = rule_obj.get("rules")
    if isinstance(rules, list) and rules:
        first_rule = rules[0] or {}
        if isinstance(first_rule, dict) and (
            "recon" in first_rule
            or ("source_file" in first_rule and "target_file" in first_rule)
            or ("rule_id" in rule_obj and "rule_name" in rule_obj)
        ):
            return "recon"
    if "rule_id" in rule_obj and "rule_name" in rule_obj and "file_rule_code" in rule_obj:
        return "recon"
    return "proc"


def _normalize_task_type(rule_type: Any, rule_payload: Any) -> str:
    """优先使用表中 rule_type，缺失时再回退到规则内容推断。"""
    if isinstance(rule_type, str):
        normalized = rule_type.strip().lower()
        if normalized in {"proc", "recon"}:
            return normalized
    return _infer_task_type(rule_payload)


def _default_entry_modes(rule_type: Any, rule_payload: Any | None = None) -> list[str]:
    normalized = str(rule_type or "").strip().lower()
    if normalized == "file":
        return ["upload"]
    if isinstance(rule_payload, dict):
        file_rule_code = str(rule_payload.get("file_rule_code") or "").strip()
        if file_rule_code:
            return ["upload"]
    return ["dataset"]


def _normalize_entry_modes(
    entry_modes: list[Any] | tuple[Any, ...] | None,
    *,
    rule_type: Any,
    rule_payload: Any | None,
) -> list[str]:
    normalized_modes: list[str] = []
    for item in list(entry_modes or []):
        value = str(item or "").strip().lower()
        if value in _ALLOWED_ENTRY_MODES and value not in normalized_modes:
            normalized_modes.append(value)
    if normalized_modes:
        return normalized_modes
    return _default_entry_modes(rule_type, rule_payload)


def get_rule(rule_code: str, user_id: str | None = None) -> Optional[Dict[str, Any]]:
    """从 rule_detail 表获取指定 rule_code 的规则完整记录。"""
    normalized_user_id = _normalize_db_user_id(user_id)
    cache_key = (rule_code, normalized_user_id or "<system>")
    cached = _rule_cache.get(cache_key)
    now = time.time()
    if cached is not None:
        cached_at, cached_value = cached
        if now - cached_at < RULE_CACHE_TTL_SECONDS:
            logger.info(f"[Cache] 命中缓存: rule_code={rule_code}, user_id={user_id}")
            return cached_value
        _rule_cache.pop(cache_key, None)

    conn = None
    try:
        logger.info(
            f"[SQL] 查询 rule_detail: rule_code={rule_code}, "
            f"user_id={user_id}, normalized_user_id={normalized_user_id}"
        )
        conn = get_db_connection()
        cur = conn.cursor()

        if normalized_user_id:
            sql = """
                SELECT id, user_id, task_id, rule_code, name, rule, rule_type, remark, supported_entry_modes
                FROM rule_detail
                WHERE rule_code = %s
                  AND (user_id = %s OR user_id IS NULL)
                ORDER BY CASE WHEN user_id = %s THEN 0 ELSE 1 END, id DESC
                LIMIT 1
            """
            cur.execute(sql, (rule_code, normalized_user_id, normalized_user_id))
        else:
            sql = """
                SELECT id, user_id, task_id, rule_code, name, rule, rule_type, remark, supported_entry_modes
                FROM rule_detail
                WHERE rule_code = %s
                ORDER BY id DESC
                LIMIT 1
            """
            cur.execute(sql, (rule_code,))

        row = cur.fetchone()
        cur.close()

        if row is None:
            logger.warning(
                f"[SQL] 未找到规则: rule_code={rule_code}, "
                f"user_id={user_id}, normalized_user_id={normalized_user_id}"
            )
            _rule_cache[cache_key] = (now, None)
            return None

        rule_payload = row[5]
        rule_type = row[6]
        result = {
            "id": row[0],
            "user_id": row[1],
            "task_id": row[2],
            "rule_code": row[3],
            "name": row[4],
            "rule": rule_payload,
            "rule_type": rule_type,
            "remark": row[7],
            "supported_entry_modes": _normalize_entry_modes(
                row[8],
                rule_type=rule_type,
                rule_payload=rule_payload if isinstance(rule_payload, dict) else {},
            ),
        }
        _rule_cache[cache_key] = (now, result)
        return result
    except Exception as e:
        logger.error(f"[SQL] 查询 rule_detail 失败: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()


def _clear_rule_cache(rule_code: str) -> None:
    keys = [key for key in _rule_cache if key[0] == rule_code]
    for key in keys:
        _rule_cache.pop(key, None)


def save_rule(
    *,
    rule_code: str,
    name: str,
    rule: dict[str, Any],
    rule_type: str,
    user_id: str | None,
    remark: str = "",
    task_id: int | None = None,
    supported_entry_modes: list[str] | tuple[str, ...] | None = None,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """保存或更新 rule_detail。"""
    normalized_rule_code = rule_code.strip()
    normalized_name = name.strip()
    normalized_rule_type = rule_type.strip().lower()
    normalized_remark = remark.strip()
    normalized_user_id = _normalize_db_user_id(user_id)
    if not normalized_rule_code:
        raise ValueError("rule_code 不能为空")
    if not normalized_name:
        raise ValueError("name 不能为空")
    if normalized_rule_type not in {"file", "proc", "recon"}:
        raise ValueError("rule_type 仅支持 file/proc/recon")

    normalized_entry_modes = _normalize_entry_modes(
        supported_entry_modes,
        rule_type=normalized_rule_type,
        rule_payload=rule,
    )

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, user_id
            FROM rule_detail
            WHERE rule_code = %s
            LIMIT 1
            """,
            (normalized_rule_code,),
        )
        row = cur.fetchone()

        if row:
            existing_id = row[0]
            existing_user_id = str(row[1] or "")
            if not overwrite:
                raise ValueError(f"rule_code '{normalized_rule_code}' 已存在")
            if existing_user_id and existing_user_id != (normalized_user_id or ""):
                raise ValueError(f"rule_code '{normalized_rule_code}' 不属于当前用户，不能覆盖")
            cur.execute(
                """
                UPDATE rule_detail
                   SET name = %s,
                       rule = %s::jsonb,
                       remark = %s,
                       rule_type = %s,
                       user_id = %s,
                       task_id = %s,
                       supported_entry_modes = %s
                 WHERE id = %s
             RETURNING id, user_id, task_id, rule_code, name, rule, rule_type, remark, supported_entry_modes
                """,
                (
                    normalized_name,
                    json.dumps(rule, ensure_ascii=False),
                    normalized_remark,
                    normalized_rule_type,
                    normalized_user_id,
                    task_id,
                    normalized_entry_modes,
                    existing_id,
                ),
            )
        else:
            # 兼容历史 rule_detail 结构：id 为整数主键，但库里未配置默认序列。
            cur.execute("LOCK TABLE public.rule_detail IN EXCLUSIVE MODE")
            cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM public.rule_detail")
            next_rule_id_row = cur.fetchone()
            next_rule_id = int(next_rule_id_row[0]) if next_rule_id_row and next_rule_id_row[0] is not None else 1
            cur.execute(
                """
                INSERT INTO rule_detail (id, rule_code, rule, remark, rule_type, user_id, name, task_id, supported_entry_modes)
                VALUES (%s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s)
             RETURNING id, user_id, task_id, rule_code, name, rule, rule_type, remark, supported_entry_modes
                """,
                (
                    next_rule_id,
                    normalized_rule_code,
                    json.dumps(rule, ensure_ascii=False),
                    normalized_remark,
                    normalized_rule_type,
                    normalized_user_id,
                    normalized_name,
                    task_id,
                    normalized_entry_modes,
                ),
            )

        saved = cur.fetchone()
        conn.commit()
        _clear_rule_cache(normalized_rule_code)
        return {
            "id": saved[0],
            "user_id": saved[1],
            "task_id": saved[2],
            "rule_code": saved[3],
            "name": saved[4],
            "rule": saved[5],
            "rule_type": saved[6],
            "remark": saved[7],
            "supported_entry_modes": saved[8],
        }
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


def _get_user_tasks(user_id: str) -> List[Dict[str, Any]]:
    """从 user_tasks 表获取当前用户可用任务。"""
    normalized_user_id = _normalize_db_user_id(user_id)
    if not normalized_user_id:
        logger.info("[SQL] user_id 非 UUID，跳过用户任务查询: user_id=%s", user_id)
        return []

    conn = None
    try:
        logger.info(f"[SQL] 开始查询任务列表: user_id={normalized_user_id}")
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
                rd.remark,
                rd.supported_entry_modes
            FROM user_tasks AS ut
            LEFT JOIN rule_detail AS rd
              ON rd.task_id = ut.id
             AND rd.rule_type IN ('proc', 'recon')
             AND (rd.user_id = %s OR rd.user_id IS NULL)
            WHERE ut.user_id = %s
            ORDER BY ut.id ASC, rd.id ASC
            """,
            (normalized_user_id, normalized_user_id),
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
            supported_modes = _normalize_entry_modes(
                row[13],
                rule_type=row[11],
                rule_payload=rule_payload if isinstance(rule_payload, dict) else {},
            )

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
                    "supported_entry_modes": supported_modes,
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
        rule = get_rule(rule_code, user_id=_normalize_db_user_id(user_id))
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


async def _handle_save_rule(arguments: dict) -> dict:
    auth_token = str(arguments.get("auth_token") or "").strip()
    if not auth_token:
        return {"success": False, "error": "未提供认证 token，请先登录"}

    user = get_user_from_token(auth_token)
    if not user:
        return {"success": False, "error": "token 无效或已过期，请重新登录"}

    user_id = str(user.get("user_id") or user.get("id") or "")
    if not user_id:
        return {"success": False, "error": "token 中缺少用户标识"}

    rule_code = str(arguments.get("rule_code") or "").strip()
    name = str(arguments.get("name") or "").strip()
    rule = arguments.get("rule")
    rule_type = str(arguments.get("rule_type") or "").strip()
    remark = str(arguments.get("remark") or "").strip()
    overwrite = bool(arguments.get("overwrite", False))
    task_id_raw = arguments.get("task_id")
    task_id = int(task_id_raw) if isinstance(task_id_raw, int) else None
    entry_modes_arg = arguments.get("supported_entry_modes")
    supported_entry_modes = (
        list(entry_modes_arg)
        if isinstance(entry_modes_arg, (list, tuple))
        else None
    )

    if not isinstance(rule, dict):
        return {"success": False, "error": "rule 必须是对象"}

    try:
        saved = save_rule(
            rule_code=rule_code,
            name=name,
            rule=rule,
            rule_type=rule_type,
            user_id=_normalize_db_user_id(user_id),
            remark=remark,
            task_id=task_id,
            supported_entry_modes=supported_entry_modes,
            overwrite=overwrite,
        )
        return {
            "success": True,
            "rule_code": str(saved.get("rule_code") or ""),
            "data": saved,
            "message": "规则保存成功",
        }
    except Exception as e:
        logger.error(f"保存规则失败: {e}", exc_info=True)
        return {"success": False, "error": f"保存规则失败: {str(e)}"}


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
