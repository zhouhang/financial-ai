"""认证、组织管理和会话管理的 MCP 工具定义与处理"""

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
    """创建认证、组织管理和会话管理相关的工具"""
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
            name="list_company",
            description="获取公司列表（注册与管理员流程共用；admin_token 可选）",
            inputSchema={
                "type": "object",
                "properties": {
                    "admin_token": {"type": "string", "description": "管理员 token"},
                },
                "required": [],
            },
        ),
        Tool(
            name="get_admin_view",
            description="获取管理员视图 - 公司部门员工层级结构",
            inputSchema={
                "type": "object",
                "properties": {
                    "admin_token": {"type": "string", "description": "管理员 token"},
                },
                "required": ["admin_token"],
            },
        ),
        
        Tool(
            name="list_departments",
            description="获取指定公司的部门列表（注册与管理员流程共用）",
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
    """处理认证、组织管理和会话管理工具调用"""
    handlers = {
        "auth_register": _handle_register,
        "auth_login": _handle_login,
        "auth_me": _handle_me,
        "admin_login": _handle_admin_login,
        "create_company": _handle_create_company,
        "create_department": _handle_create_department,
        "list_company": _handle_list_company,
        "get_admin_view": _handle_admin_view,
        "list_departments": _handle_list_departments,
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


async def _handle_list_company(args: dict) -> dict:
    """获取公司列表。

    admin_token 可选：
    - 传入时校验管理员身份，供后台管理流程复用
    - 不传时允许公开读取，供注册流程复用
    """
    admin_token = (args.get("admin_token") or "").strip()
    if admin_token and admin_token not in ADMIN_TOKENS:
        return {"success": False, "error": "无效的管理员 token，请先登录"}

    companies = auth_db.list_companies()
    return {"success": True, "companies": companies}


async def _handle_admin_view(args: dict) -> dict:
    """获取管理员视图 - 公司部门员工层级"""
    admin_token = args.get("admin_token", "")
    
    if not admin_token or admin_token not in ADMIN_TOKENS:
        return {"success": False, "error": "无效的管理员 token，请先登录"}
    
    data = auth_db.get_admin_view()
    return {"success": True, "data": data}


async def _handle_list_departments(args: dict) -> dict:
    """获取指定公司的部门列表。"""
    company_id = (args.get("company_id") or "").strip()
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
