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
                    "company_id": {"type": "string", "description": "公司 ID（可选）"},
                    "department_id": {"type": "string", "description": "部门 ID（可选）"},
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
            name="delete_reconciliation_rule",
            description="删除对账规则（软删除，需要权限）",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string", "description": "JWT token"},
                    "rule_id": {"type": "string", "description": "规则 ID"},
                    "rule_name": {"type": "string", "description": "规则名称（可选，用于校验防止误删）"},
                },
                "required": ["auth_token", "rule_id"],
            },
        ),
        Tool(
            name="copy_reconciliation_rule",
            description="复制对账规则为个人规则",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string", "description": "JWT token"},
                    "source_rule_id": {"type": "string", "description": "源规则 ID"},
                    "new_rule_name": {"type": "string", "description": "新规则名称"},
                },
                "required": ["auth_token", "source_rule_id", "new_rule_name"],
            },
        ),

        # ── 管理员功能 ───────────────────────────────────────────────
        Tool(
            name="admin_login",
            description="管理员登录",
            inputSchema={
                "type": "object",
                "properties": {
                    "username": {"type": "string", "description": "管理员用户名"},
                    "password": {"type": "string", "description": "管理员密码"},
                },
                "required": ["username", "password"],
            },
        ),
        Tool(
            name="create_company",
            description="管理员创建公司",
            inputSchema={
                "type": "object",
                "properties": {
                    "admin_token": {"type": "string", "description": "管理员 token"},
                    "name": {"type": "string", "description": "公司名称"},
                },
                "required": ["admin_token", "name"],
            },
        ),
        Tool(
            name="create_department",
            description="管理员创建部门",
            inputSchema={
                "type": "object",
                "properties": {
                    "admin_token": {"type": "string", "description": "管理员 token"},
                    "company_id": {"type": "string", "description": "公司 ID"},
                    "name": {"type": "string", "description": "部门名称"},
                },
                "required": ["admin_token", "company_id", "name"],
            },
        ),
        Tool(
            name="list_companies",
            description="获取公司列表（管理员）",
            inputSchema={
                "type": "object",
                "properties": {
                    "admin_token": {"type": "string", "description": "管理员 token"},
                },
                "required": ["admin_token"],
            },
        ),
        Tool(
            name="get_admin_view",
            description="获取管理员视图 - 公司部门员工规则层级结构",
            inputSchema={
                "type": "object",
                "properties": {
                    "admin_token": {"type": "string", "description": "管理员 token"},
                },
                "required": ["admin_token"],
            },
        ),
        
        # ── 公开 API（无需认证）───────────────────────────────────────
        Tool(
            name="list_companies_public",
            description="获取公司列表（公开，用于注册）",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="list_departments_public",
            description="获取指定公司的部门列表（公开，用于注册）",
            inputSchema={
                "type": "object",
                "properties": {
                    "company_id": {"type": "string", "description": "公司 ID"},
                },
                "required": ["company_id"],
            },
        ),
        
        # ── 会话管理 ───────────────────────────────────────────────────
        Tool(
            name="create_conversation",
            description="创建新会话",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string", "description": "JWT token"},
                    "title": {"type": "string", "description": "会话标题（可选）"},
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="list_conversations",
            description="获取用户的会话列表",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string", "description": "JWT token"},
                    "limit": {"type": "integer", "description": "返回数量限制"},
                    "offset": {"type": "integer", "description": "偏移量"},
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="get_conversation",
            description="获取单个会话详情（包含消息）",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string", "description": "JWT token"},
                    "conversation_id": {"type": "string", "description": "会话 ID"},
                },
                "required": ["auth_token", "conversation_id"],
            },
        ),
        Tool(
            name="delete_conversation",
            description="删除会话",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string", "description": "JWT token"},
                    "conversation_id": {"type": "string", "description": "会话 ID"},
                },
                "required": ["auth_token", "conversation_id"],
            },
        ),
        Tool(
            name="save_message",
            description="保存消息到会话",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string", "description": "JWT token"},
                    "conversation_id": {"type": "string", "description": "会话 ID"},
                    "role": {"type": "string", "description": "消息角色 (user/assistant/system)"},
                    "content": {"type": "string", "description": "消息内容"},
                    "metadata": {"type": "object", "description": "附加数据"},
                },
                "required": ["auth_token", "conversation_id", "role", "content"],
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
        "delete_reconciliation_rule": _handle_delete_rule,
        "copy_reconciliation_rule": _handle_copy_rule,
        "admin_login": _handle_admin_login,
        "create_company": _handle_create_company,
        "create_department": _handle_create_department,
        "list_companies": _handle_list_companies,
        "get_admin_view": _handle_admin_view,
        "list_companies_public": _handle_list_companies_public,
        "list_departments_public": _handle_list_departments_public,
        # 会话管理
        "create_conversation": _handle_create_conversation,
        "list_conversations": _handle_list_conversations,
        "get_conversation": _handle_get_conversation,
        "delete_conversation": _handle_delete_conversation,
        "save_message": _handle_save_message,
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
    email = (args.get("email") or "").strip() or None
    phone = (args.get("phone") or "").strip() or None
    # 支持直接传入 company_id 和 department_id
    company_id = (args.get("company_id") or "").strip() or None
    department_id = (args.get("department_id") or "").strip() or None

    if not username or not password:
        return {"success": False, "error": "用户名和密码不能为空"}
    if len(password) < 6:
        return {"success": False, "error": "密码长度至少 6 位"}

    # 检查用户名是否已存在
    existing = auth_db.get_user_by_username(username)
    if existing:
        return {"success": False, "error": f"用户名 '{username}' 已存在"}

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
    # 支持 auth_token 或 guest_token
    auth_token = args.get("auth_token", "")
    guest_token = args.get("guest_token", "")
    
    if auth_token:
        valid, user_info, err = _require_auth(args)
        if not valid:
            return {"success": False, "error": err}
    elif guest_token:
        # 验证游客token
        token_info = auth_db.verify_guest_token(guest_token)
        if not token_info or not token_info.get("valid"):
            return {"success": False, "error": "无效的游客token或token已过期"}
        # 游客模式：返回所有活跃规则
        status = args.get("status", "active")
        rules = auth_db.list_all_active_rules(status=status)
        return {"success": True, "rules": rules, "count": len(rules)}
    else:
        return {"success": False, "error": "请提供 auth_token 或 guest_token"}

    status = args.get("status", "active")
    
    # 非管理员只能查询 active 状态
    user_role = user_info.get("role", "")
    if status != "active" and user_role != "admin":
        return {"success": False, "error": "无权查询已删除的规则"}
    
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
    
    # 验证用户是否有权限查看该规则
    user_id = user_info.get("user_id")
    user_role = user_info.get("role")
    rule_created_by = rule.get("created_by")
    rule_visibility = rule.get("visibility", "private")
    rule_department_id = rule.get("department_id")
    user_department_id = user_info.get("department_id")
    
    has_access = False
    if str(rule_created_by) == user_id:  # 创建者可以查看
        has_access = True
    elif rule_visibility == "company" and str(rule.get("company_id")) == str(user_info.get("company_id")):  # 公司可见
        has_access = True
    elif rule_visibility == "department" and str(rule_department_id) == str(user_department_id):  # 部门可见
        has_access = True
    elif user_role == "admin":  # admin 可以查看所有
        has_access = True
    
    if not has_access:
        return {"success": False, "error": "无权查看该规则"}

    return {"success": True, "rule": rule}


async def _handle_delete_rule(args: dict) -> dict:
    """删除规则
    
    流程:
    - 普通用户：软删除 (UPDATE status='archived')
    - 管理员：硬删除 (DELETE FROM)
    
    注意: PostgreSQL 是规则的主数据源。
    """
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

    # 校验：若调用方传入 rule_name，必须与数据库中的规则名完全一致，防止误删
    expected_name = args.get("rule_name", "").strip()
    rule_name = rule.get("name", "")
    if expected_name and expected_name != rule_name:
        logger.warning(f"删除校验失败: 期望规则名「{expected_name}」与实际「{rule_name}」不一致，拒绝删除")
        return {"success": False, "error": f"规则名称不匹配，拒绝删除（期望「{expected_name}」，实际「{rule_name}」）"}

    # 检查权限
    if not auth_db.can_user_modify_rule(user_info["user_id"], user_info["role"], rule):
        return {"success": False, "error": "无权删除此规则"}
    
    user_role = user_info.get("role", "")
    
    if user_role == "admin":
        success = auth_db.delete_rule(rule_id)
        if not success:
            return {"success": False, "error": "删除数据库记录失败"}
        logger.info(f"管理员删除规则（硬删除）: {rule_name} (id={rule_id})")
        return {
            "success": True,
            "message": f"规则「{rule_name}」已彻底删除（管理员硬删除）",
        }
    updated = auth_db.update_rule(rule_id, status="archived")
    if not updated:
        return {"success": False, "error": "软删除失败"}

    logger.info(f"普通用户删除规则（软删除）: {rule_name} (id={rule_id}), status -> archived")

    return {
        "success": True,
        "message": f"规则「{rule_name}」已删除（状态已归档）",
    }


async def _handle_copy_rule(args: dict) -> dict:
    """复制对账规则为个人规则"""
    valid, user_info, err = _require_auth(args)
    if not valid:
        return {"success": False, "error": err}

    source_rule_id = args.get("source_rule_id")
    new_rule_name = args.get("new_rule_name")

    if not source_rule_id:
        return {"success": False, "error": "缺少 source_rule_id"}
    if not new_rule_name:
        return {"success": False, "error": "缺少 new_rule_name"}

    user_id = user_info["user_id"]

    try:
        new_rule = auth_db.copy_rule(source_rule_id, new_rule_name, user_id)
        logger.info(f"用户 {user_id} 复制规则 {source_rule_id} 为 {new_rule_name}")
        return {
            "success": True,
            "message": f"规则已复制为 '{new_rule_name}'",
            "rule": new_rule,
        }
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"复制规则失败: {e}")
        return {"success": False, "error": str(e)}


import hashlib

ADMIN_TOKENS = {}  # 简单的内存存储：admin_token -> admin_info

def _verify_admin(username: str, password: str) -> dict | None:
    """验证管理员账号密码"""
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    
    conn = auth_db.get_conn()
    try:
        with conn as c:
            with c.cursor() as cur:
                cur.execute(
                    "SELECT id, username FROM admins WHERE username = %s AND password = %s",
                    (username, password_hash)
                )
                row = cur.fetchone()
                if row:
                    return {"id": row[0], "username": row[1]}
    except Exception as e:
        logger.error(f"验证管理员失败: {e}")
    return None


async def _handle_admin_login(args: dict) -> dict:
    """管理员登录"""
    username = args.get("username", "").strip()
    password = args.get("password", "").strip()
    
    if not username or not password:
        return {"success": False, "error": "用户名和密码不能为空"}
    
    admin = _verify_admin(username, password)
    if not admin:
        return {"success": False, "error": "用户名或密码错误"}
    
    import time
    admin_token = f"admin_{int(time.time())}_{username}"
    ADMIN_TOKENS[admin_token] = admin
    
    return {
        "success": True,
        "admin_token": admin_token,
        "username": admin["username"],
    }


async def _handle_create_company(args: dict) -> dict:
    """创建公司"""
    admin_token = args.get("admin_token", "")
    name = args.get("name", "").strip()
    
    if not admin_token or admin_token not in ADMIN_TOKENS:
        return {"success": False, "error": "无效的管理员 token，请先登录"}
    
    if not name:
        return {"success": False, "error": "公司名称不能为空"}
    
    company = auth_db.create_company(name)
    if not company:
        return {"success": False, "error": "公司名称已存在"}
    
    return {"success": True, "company": company}


async def _handle_create_department(args: dict) -> dict:
    """创建部门"""
    admin_token = args.get("admin_token", "")
    company_id = args.get("company_id", "").strip()
    name = args.get("name", "").strip()
    
    if not admin_token or admin_token not in ADMIN_TOKENS:
        return {"success": False, "error": "无效的管理员 token，请先登录"}
    
    if not company_id or not name:
        return {"success": False, "error": "公司ID和部门名称不能为空"}
    
    department = auth_db.create_department(company_id, name)
    if not department:
        return {"success": False, "error": "该公司下已存在此部门名称"}
    
    return {"success": True, "department": department}


async def _handle_list_companies(args: dict) -> dict:
    """获取公司列表"""
    admin_token = args.get("admin_token", "")
    
    if not admin_token or admin_token not in ADMIN_TOKENS:
        return {"success": False, "error": "无效的管理员 token，请先登录"}
    
    companies = auth_db.list_companies()
    return {"success": True, "companies": companies}


async def _handle_admin_view(args: dict) -> dict:
    """获取管理员视图 - 公司部门员工规则层级"""
    admin_token = args.get("admin_token", "")
    
    if not admin_token or admin_token not in ADMIN_TOKENS:
        return {"success": False, "error": "无效的管理员 token，请先登录"}
    
    data = auth_db.get_admin_view()
    return {"success": True, "data": data}


async def _handle_list_companies_public(args: dict) -> dict:
    """获取公司列表（公开，用于注册）"""
    companies = auth_db.list_companies()
    return {"success": True, "companies": companies}


async def _handle_list_departments_public(args: dict) -> dict:
    """获取指定公司的部门列表（公开，用于注册）"""
    company_id = args.get("company_id", "").strip()
    if not company_id:
        return {"success": False, "error": "公司 ID 不能为空"}
    
    departments = auth_db.list_departments(company_id)
    return {"success": True, "departments": departments}


# ══════════════════════════════════════════════════════════════════════════════
# 会话管理
# ══════════════════════════════════════════════════════════════════════════════

async def _handle_create_conversation(args: dict) -> dict:
    """创建新会话"""
    is_valid, user_info, error = _require_auth(args)
    if not is_valid:
        return {"success": False, "error": error}
    
    title = args.get("title", "").strip() or None
    user_id = user_info["user_id"]
    
    conversation = auth_db.create_conversation(user_id, title)
    if not conversation:
        return {"success": False, "error": "创建会话失败"}
    
    return {"success": True, "conversation": conversation}


async def _handle_list_conversations(args: dict) -> dict:
    """获取用户的会话列表"""
    is_valid, user_info, error = _require_auth(args)
    if not is_valid:
        return {"success": False, "error": error}
    
    user_id = user_info["user_id"]
    limit = int(args.get("limit", 50))
    offset = int(args.get("offset", 0))
    
    conversations = auth_db.list_conversations(user_id, limit, offset)
    return {"success": True, "conversations": conversations}


async def _handle_get_conversation(args: dict) -> dict:
    """获取单个会话详情（包含消息）"""
    is_valid, user_info, error = _require_auth(args)
    if not is_valid:
        return {"success": False, "error": error}
    
    user_id = user_info["user_id"]
    conversation_id = args.get("conversation_id", "").strip()
    
    if not conversation_id:
        return {"success": False, "error": "会话 ID 不能为空"}
    
    conversation = auth_db.get_conversation(conversation_id, user_id)
    if not conversation:
        return {"success": False, "error": "会话不存在"}
    
    # 获取消息列表
    messages = auth_db.get_messages(conversation_id)
    conversation["messages"] = messages
    
    return {"success": True, "conversation": conversation}


async def _handle_delete_conversation(args: dict) -> dict:
    """删除会话"""
    is_valid, user_info, error = _require_auth(args)
    if not is_valid:
        return {"success": False, "error": error}
    
    user_id = user_info["user_id"]
    conversation_id = args.get("conversation_id", "").strip()
    
    if not conversation_id:
        return {"success": False, "error": "会话 ID 不能为空"}
    
    success = auth_db.delete_conversation(conversation_id, user_id)
    if not success:
        return {"success": False, "error": "删除会话失败"}
    
    return {"success": True, "message": "会话已删除"}


async def _handle_save_message(args: dict) -> dict:
    """保存消息到会话（支持附件）"""
    is_valid, user_info, error = _require_auth(args)
    if not is_valid:
        return {"success": False, "error": error}

    user_id = user_info["user_id"]
    conversation_id = args.get("conversation_id", "").strip()
    role = args.get("role", "").strip()
    content = args.get("content", "")
    metadata = args.get("metadata", {})
    attachments = args.get("attachments", [])  # 新增：文件附件列表

    if not conversation_id:
        return {"success": False, "error": "会话 ID 不能为空"}
    if not role:
        return {"success": False, "error": "消息角色不能为空"}
    if role not in ("user", "assistant", "system"):
        return {"success": False, "error": "无效的消息角色"}

    # 验证会话所有权
    conversation = auth_db.get_conversation(conversation_id, user_id)
    if not conversation:
        return {"success": False, "error": "会话不存在"}

    message = auth_db.save_message(conversation_id, role, content, metadata, attachments)  # 传递附件参数
    if not message:
        return {"success": False, "error": "保存消息失败"}

    return {"success": True, "message": message}
