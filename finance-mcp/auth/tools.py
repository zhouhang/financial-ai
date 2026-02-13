"""认证和规则管理的 MCP 工具定义与处理"""

import logging
from typing import Dict, Any

import bcrypt
from mcp import types as mcp_types

from auth.jwt_utils import create_token, get_user_from_token
from auth import db as auth_db

logger = logging.getLogger(__name__)


# ============================================================================
# 工具定义
# ============================================================================

def create_auth_tools() -> list[mcp_types.Tool]:
    """创建认证和规则管理相关的工具"""
    Tool = mcp_types.Tool
    return [
        # ── 认证 ──────────────────────────────────────────────
        Tool(
            name="auth_register",
            description="注册新用户账号",
            inputSchema={
                "type": "object",
                "properties": {
                    "username": {"type": "string", "description": "用户名（唯一）"},
                    "password": {"type": "string", "description": "密码"},
                    "email": {"type": "string", "description": "邮箱（可选）"},
                    "phone": {"type": "string", "description": "手机号（可选）"},
                    "company_code": {"type": "string", "description": "公司编码（可选，加入已有公司）"},
                    "department_code": {"type": "string", "description": "部门编码（可选）"},
                },
                "required": ["username", "password"],
            },
        ),
        Tool(
            name="auth_login",
            description="用户登录，返回 JWT token",
            inputSchema={
                "type": "object",
                "properties": {
                    "username": {"type": "string", "description": "用户名"},
                    "password": {"type": "string", "description": "密码"},
                },
                "required": ["username", "password"],
            },
        ),
        Tool(
            name="auth_me",
            description="获取当前登录用户的信息",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string", "description": "JWT token"},
                },
                "required": ["auth_token"],
            },
        ),

        # ── 规则管理（需要认证） ───────────────────────────────
        Tool(
            name="list_reconciliation_rules",
            description="查询当前用户可见的对账规则列表（基于权限过滤）",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string", "description": "JWT token"},
                    "status": {
                        "type": "string",
                        "description": "规则状态过滤：active/archived",
                        "default": "active",
                    },
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="get_reconciliation_rule",
            description="获取单条对账规则的详情（含 rule_template）",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string", "description": "JWT token"},
                    "rule_id": {"type": "string", "description": "规则 ID"},
                    "rule_name": {"type": "string", "description": "规则名称（与 rule_id 二选一）"},
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="save_reconciliation_rule",
            description="保存新的对账规则",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string", "description": "JWT token"},
                    "name": {"type": "string", "description": "规则名称"},
                    "description": {"type": "string", "description": "规则描述"},
                    "rule_template": {"type": "object", "description": "规则模板 JSON"},
                    "visibility": {
                        "type": "string",
                        "description": "可见性：private（仅自己）/ department（部门可见）/ company（公司可见）",
                        "default": "private",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "标签列表（可选）",
                    },
                },
                "required": ["auth_token", "name", "rule_template"],
            },
        ),
        Tool(
            name="update_reconciliation_rule",
            description="更新已有对账规则（需要权限）",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string", "description": "JWT token"},
                    "rule_id": {"type": "string", "description": "规则 ID"},
                    "name": {"type": "string", "description": "新的规则名称"},
                    "description": {"type": "string", "description": "新的描述"},
                    "rule_template": {"type": "object", "description": "新的规则模板"},
                    "visibility": {"type": "string", "description": "新的可见性"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["auth_token", "rule_id"],
            },
        ),
        Tool(
            name="delete_reconciliation_rule",
            description="删除对账规则（软删除，需要权限）",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string", "description": "JWT token"},
                    "rule_id": {"type": "string", "description": "规则 ID"},
                },
                "required": ["auth_token", "rule_id"],
            },
        ),
    ]


# ============================================================================
# 工具处理
# ============================================================================

async def handle_auth_tool_call(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """处理认证和规则管理工具调用"""
    handlers = {
        "auth_register": _handle_register,
        "auth_login": _handle_login,
        "auth_me": _handle_me,
        "list_reconciliation_rules": _handle_list_rules,
        "get_reconciliation_rule": _handle_get_rule,
        "save_reconciliation_rule": _handle_save_rule,
        "update_reconciliation_rule": _handle_update_rule,
        "delete_reconciliation_rule": _handle_delete_rule,
    }
    handler = handlers.get(tool_name)
    if not handler:
        return {"success": False, "error": f"未知的工具: {tool_name}"}
    try:
        return await handler(arguments)
    except Exception as e:
        logger.error(f"工具 {tool_name} 执行失败: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# ── 辅助：认证检查 ────────────────────────────────────────────────────

def _require_auth(args: dict) -> tuple[bool, dict | None, str | None]:
    """验证 auth_token，返回 (is_valid, user_info, error_msg)"""
    token = args.get("auth_token", "")
    if not token:
        return False, None, "未提供认证 token，请先登录"
    user = get_user_from_token(token)
    if not user:
        return False, None, "token 无效或已过期，请重新登录"
    return True, user, None


# ── 认证工具处理 ──────────────────────────────────────────────────────

async def _handle_register(args: dict) -> dict:
    """注册新用户"""
    username = args.get("username", "").strip()
    password = args.get("password", "").strip()
    email = args.get("email", "").strip() or None
    phone = args.get("phone", "").strip() or None
    company_code = args.get("company_code", "").strip() or None
    department_code = args.get("department_code", "").strip() or None

    if not username or not password:
        return {"success": False, "error": "用户名和密码不能为空"}
    if len(password) < 6:
        return {"success": False, "error": "密码长度至少 6 位"}

    # 检查用户名是否已存在
    existing = auth_db.get_user_by_username(username)
    if existing:
        return {"success": False, "error": f"用户名 '{username}' 已存在"}

    # 查找公司和部门
    company_id = None
    department_id = None

    if company_code:
        companies = auth_db.list_companies()
        company = next((c for c in companies if c["code"] == company_code), None)
        if not company:
            return {"success": False, "error": f"公司编码 '{company_code}' 不存在"}
        company_id = str(company["id"])

        if department_code and company_id:
            departments = auth_db.list_departments(company_id)
            dept = next((d for d in departments if d["code"] == department_code), None)
            if not dept:
                return {"success": False, "error": f"部门编码 '{department_code}' 不存在"}
            department_id = str(dept["id"])

    # 密码哈希
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    # 创建用户
    user = auth_db.create_user(
        username=username,
        password_hash=password_hash,
        email=email,
        phone=phone,
        company_id=company_id,
        department_id=department_id,
    )

    # 生成 token
    token = create_token(
        user_id=str(user["id"]),
        username=user["username"],
        role=user["role"],
        company_id=company_id,
        department_id=department_id,
    )

    return {
        "success": True,
        "message": f"注册成功！欢迎 {username}",
        "token": token,
        "user": {
            "id": str(user["id"]),
            "username": user["username"],
            "role": user["role"],
            "company_id": company_id,
            "department_id": department_id,
        },
    }


async def _handle_login(args: dict) -> dict:
    """用户登录"""
    username = args.get("username", "").strip()
    password = args.get("password", "").strip()

    if not username or not password:
        return {"success": False, "error": "用户名和密码不能为空"}

    user = auth_db.get_user_by_username(username)
    if not user:
        return {"success": False, "error": "用户名或密码错误"}

    if user.get("status") != "active":
        return {"success": False, "error": "账号已被禁用"}

    # 验证密码
    if not bcrypt.checkpw(password.encode("utf-8"), user["password_hash"].encode("utf-8")):
        return {"success": False, "error": "用户名或密码错误"}

    # 更新最后登录时间
    auth_db.update_last_login(str(user["id"]))

    # 生成 token
    token = create_token(
        user_id=str(user["id"]),
        username=user["username"],
        role=user["role"],
        company_id=str(user["company_id"]) if user.get("company_id") else None,
        department_id=str(user["department_id"]) if user.get("department_id") else None,
    )

    return {
        "success": True,
        "message": f"登录成功！欢迎回来，{username}",
        "token": token,
        "user": {
            "id": str(user["id"]),
            "username": user["username"],
            "role": user["role"],
            "company_id": str(user["company_id"]) if user.get("company_id") else None,
            "department_id": str(user["department_id"]) if user.get("department_id") else None,
            "company_name": user.get("company_name"),
            "department_name": user.get("department_name"),
        },
    }


async def _handle_me(args: dict) -> dict:
    """获取当前用户信息"""
    valid, user_info, err = _require_auth(args)
    if not valid:
        return {"success": False, "error": err}

    user = auth_db.get_user_by_id(user_info["user_id"])
    if not user:
        return {"success": False, "error": "用户不存在"}

    return {
        "success": True,
        "user": {
            "id": str(user["id"]),
            "username": user["username"],
            "email": user.get("email"),
            "phone": user.get("phone"),
            "role": user["role"],
            "status": user["status"],
            "company_id": str(user["company_id"]) if user.get("company_id") else None,
            "department_id": str(user["department_id"]) if user.get("department_id") else None,
            "company_name": user.get("company_name"),
            "department_name": user.get("department_name"),
        },
    }


# ── 规则管理工具处理 ──────────────────────────────────────────────────

async def _handle_list_rules(args: dict) -> dict:
    """列出用户可见的规则"""
    valid, user_info, err = _require_auth(args)
    if not valid:
        return {"success": False, "error": err}

    status = args.get("status", "active")
    rules = auth_db.list_rules_for_user(
        user_id=user_info["user_id"],
        company_id=user_info.get("company_id"),
        department_id=user_info.get("department_id"),
        status=status,
    )
    return {"success": True, "rules": rules, "count": len(rules)}


async def _handle_get_rule(args: dict) -> dict:
    """获取规则详情"""
    valid, user_info, err = _require_auth(args)
    if not valid:
        return {"success": False, "error": err}

    rule_id = args.get("rule_id")
    rule_name = args.get("rule_name")

    rule = None
    if rule_id:
        rule = auth_db.get_rule_by_id(rule_id)
    elif rule_name:
        rule = auth_db.get_rule_by_name(rule_name, created_by=user_info["user_id"])
        if not rule:
            # 如果自己没有，也查找可见的
            rule = auth_db.get_rule_by_name(rule_name)

    if not rule:
        return {"success": False, "error": "规则不存在"}

    return {"success": True, "rule": rule}


async def _handle_save_rule(args: dict) -> dict:
    """保存新规则"""
    valid, user_info, err = _require_auth(args)
    if not valid:
        return {"success": False, "error": err}

    name = args.get("name", "").strip()
    description = args.get("description", name)
    rule_template = args.get("rule_template")
    visibility = args.get("visibility", "private")
    tags = args.get("tags", [])

    if not name:
        return {"success": False, "error": "规则名称不能为空"}
    if not rule_template:
        return {"success": False, "error": "规则模板不能为空"}

    rule = auth_db.create_rule(
        name=name,
        description=description,
        created_by=user_info["user_id"],
        company_id=user_info.get("company_id"),
        department_id=user_info.get("department_id"),
        rule_template=rule_template,
        visibility=visibility,
        tags=tags,
    )

    logger.info(f"规则已保存: {name} (id={rule.get('id')}), 创建者: {user_info['username']}")

    return {
        "success": True,
        "rule": rule,
        "message": f"规则 '{name}' 保存成功",
    }


async def _handle_update_rule(args: dict) -> dict:
    """更新规则"""
    valid, user_info, err = _require_auth(args)
    if not valid:
        return {"success": False, "error": err}

    rule_id = args.get("rule_id")
    if not rule_id:
        return {"success": False, "error": "缺少 rule_id"}

    # 检查规则是否存在
    rule = auth_db.get_rule_by_id(rule_id)
    if not rule:
        return {"success": False, "error": "规则不存在"}

    # 检查权限
    if not auth_db.can_user_modify_rule(user_info["user_id"], user_info["role"], rule):
        return {"success": False, "error": "无权修改此规则"}

    # 构建更新字段
    update_kwargs = {}
    for field in ["name", "description", "rule_template", "visibility", "tags"]:
        if field in args and args[field] is not None:
            update_kwargs[field] = args[field]

    if not update_kwargs:
        return {"success": False, "error": "没有需要更新的字段"}

    updated = auth_db.update_rule(rule_id, **update_kwargs)
    if not updated:
        return {"success": False, "error": "更新失败"}

    return {
        "success": True,
        "rule": updated,
        "message": f"规则更新成功",
    }


async def _handle_delete_rule(args: dict) -> dict:
    """删除规则"""
    valid, user_info, err = _require_auth(args)
    if not valid:
        return {"success": False, "error": err}

    rule_id = args.get("rule_id")
    if not rule_id:
        return {"success": False, "error": "缺少 rule_id"}

    # 检查规则是否存在
    rule = auth_db.get_rule_by_id(rule_id)
    if not rule:
        return {"success": False, "error": "规则不存在"}

    # 检查权限
    if not auth_db.can_user_modify_rule(user_info["user_id"], user_info["role"], rule):
        return {"success": False, "error": "无权删除此规则"}

    success = auth_db.delete_rule(rule_id)
    if not success:
        return {"success": False, "error": "删除失败"}

    return {
        "success": True,
        "message": f"规则 '{rule.get('name')}' 已删除",
    }
