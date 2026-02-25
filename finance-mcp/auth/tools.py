"""认证和规则管理的 MCP 工具定义与处理"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, Any

import bcrypt
from mcp import types as mcp_types

from auth.jwt_utils import create_token, get_user_from_token
from auth import db as auth_db

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════════════════
# 配置路径（用于保存规则的 JSON 和更新配置文件）
# ════════════════════════════════════════════════════════════════════════════
try:
    # finance-mcp 的根目录
    FINANCE_MCP_DIR = Path(__file__).resolve().parent.parent
    SCHEMA_DIR = FINANCE_MCP_DIR / "reconciliation" / "schemas"
    RECONCILIATION_SCHEMAS_FILE = FINANCE_MCP_DIR / "reconciliation" / "config" / "reconciliation_schemas.json"
    
    # 确保目录存在
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    (FINANCE_MCP_DIR / "reconciliation" / "config").mkdir(parents=True, exist_ok=True)
except Exception as e:
    logger.error(f"初始化规则存储目录失败: {e}")
    SCHEMA_DIR = None
    RECONCILIATION_SCHEMAS_FILE = None


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
        Tool(
            name="search_rules_by_mapping",
            description="根据字段映射哈希搜索匹配的对账规则",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string", "description": "JWT token"},
                    "field_mapping_hash": {"type": "string", "description": "字段映射哈希值"},
                    "limit": {"type": "integer", "description": "返回结果数量限制", "default": 3},
                },
                "required": ["auth_token", "field_mapping_hash"],
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
        Tool(
            name="batch_get_reconciliation_rules",
            description="批量获取多个对账规则的详情（含 rule_template），用于规则推荐时的字段名匹配",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string", "description": "JWT token"},
                    "rule_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "规则 ID 列表",
                    },
                },
                "required": ["auth_token", "rule_ids"],
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
            name="list_departments",
            description="获取部门列表（可按公司筛选）",
            inputSchema={
                "type": "object",
                "properties": {
                    "admin_token": {"type": "string", "description": "管理员 token"},
                    "company_id": {"type": "string", "description": "公司 ID（可选）"},
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
            name="update_conversation",
            description="更新会话（标题、状态）",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string", "description": "JWT token"},
                    "conversation_id": {"type": "string", "description": "会话 ID"},
                    "title": {"type": "string", "description": "新标题"},
                    "status": {"type": "string", "description": "新状态"},
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
        "save_reconciliation_rule": _handle_save_rule,
        "update_reconciliation_rule": _handle_update_rule,
        "delete_reconciliation_rule": _handle_delete_rule,
        "search_rules_by_mapping": _handle_search_rules_by_mapping,
        "copy_reconciliation_rule": _handle_copy_rule,
        "batch_get_reconciliation_rules": _handle_batch_get_rules,
        "admin_login": _handle_admin_login,
        "create_company": _handle_create_company,
        "create_department": _handle_create_department,
        "list_companies": _handle_list_companies,
        "list_departments": _handle_list_departments,
        "get_admin_view": _handle_admin_view,
        "list_companies_public": _handle_list_companies_public,
        "list_departments_public": _handle_list_departments_public,
        # 会话管理
        "create_conversation": _handle_create_conversation,
        "list_conversations": _handle_list_conversations,
        "get_conversation": _handle_get_conversation,
        "update_conversation": _handle_update_conversation,
        "delete_conversation": _handle_delete_conversation,
        "save_message": _handle_save_message,
        # 游客认证
        "create_guest_token": _handle_create_guest_token,
        "verify_guest_token": _handle_verify_guest_token,
        "list_recommended_rules": _handle_list_recommended_rules,
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


# ════════════════════════════════════════════════════════════════════════════
# 规则存储辅助函数
# ════════════════════════════════════════════════════════════════════════════

def _translate_rule_name_to_type_key(name_cn: str) -> str:
    """将中文规则名称转换为英文 type_key
    例如: "南京飞翰直销对账" → "nanjing_feihan_direct_sales_reconciliation"
    """
    # 简化的转换（实际应用中可能需要更复杂的逻辑或 LLM）
    # 先转换为拼音，这里用简单的替换规则
    translation_map = {
        "南京": "nanjing",
        "飞翰": "feihan",
        "直销": "direct_sales",
        "对账": "reconciliation",
    }
    
    result = name_cn
    for cn, en in translation_map.items():
        result = result.replace(cn, en)
    
    # 如果没有匹配，用拼音库或简单的拉丁化
    # 保留字母和数字，替换其他字符为下划线
    result = re.sub(r'[^\w]', '_', result)
    result = re.sub(r'_+', '_', result)  # 合并多个下划线
    result = result.strip('_').lower()
    
    return result or "custom_rule"


def _save_schema_file(schema_dict: dict, rule_name_cn: str) -> tuple[bool, str, str]:
    """将 schema 保存为 JSON 文件
    
    返回: (是否成功, 文件名, 错误信息)
    """
    if not SCHEMA_DIR:
        return False, "", "SCHEMA_DIR 未初始化"
    
    try:
        # 生成 type_key 和文件名
        type_key = _translate_rule_name_to_type_key(rule_name_cn)
        schema_filename = f"{type_key}_schema.json"
        schema_filepath = SCHEMA_DIR / schema_filename
        
        # 保存 schema 为 JSON 文件
        with open(schema_filepath, 'w', encoding='utf-8') as f:
            json.dump(schema_dict, f, indent=2, ensure_ascii=False)
        
        logger.info(f"规则 schema 已保存: {schema_filepath}")
        return True, schema_filename, ""
        
    except Exception as e:
        logger.error(f"保存规则 schema 文件失败: {e}")
        return False, "", str(e)


def _update_reconciliation_schemas_config(rule_name_cn: str, schema_filename: str) -> tuple[bool, str]:
    """更新 reconciliation_schemas.json 配置文件，添加新规则类型
    
    返回: (是否成功, 错误信息)
    """
    if not RECONCILIATION_SCHEMAS_FILE:
        return False, "RECONCILIATION_SCHEMAS_FILE 未初始化"
    
    try:
        # 读取现有配置
        if RECONCILIATION_SCHEMAS_FILE.exists():
            with open(RECONCILIATION_SCHEMAS_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
        else:
            config = {"types": []}
        
        # 确保 types 列表存在
        if "types" not in config:
            config["types"] = []
        
        # 生成 type_key
        type_key = _translate_rule_name_to_type_key(rule_name_cn)
        
        # 检查是否已存在同名规则
        for type_config in config["types"]:
            if type_config.get("name_cn") == rule_name_cn:
                # 更新现有规则的 schema_path
                type_config["schema_path"] = schema_filename
                logger.info(f"已更新现有规则配置: {rule_name_cn}")
                break
        else:
            # 添加新规则类型
            new_type = {
                "name_cn": rule_name_cn,
                "type_key": type_key,
                "schema_path": schema_filename,
                "callback_url": "",
            }
            config["types"].append(new_type)
            logger.info(f"已添加新规则类型: {rule_name_cn}")
        
        # 写回配置文件
        with open(RECONCILIATION_SCHEMAS_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        logger.info(f"reconciliation_schemas.json 已更新")
        return True, ""
        
    except Exception as e:
        logger.error(f"更新规则配置文件失败: {e}")
        return False, str(e)


async def _handle_save_rule(args: dict) -> dict:
    """保存新规则
    
    流程:
    1. 保存到 PostgreSQL 数据库（主存储）
    2. 将 rule_template 保存为 JSON 文件（备份）
    3. 更新 reconciliation_schemas.json 配置文件（备份）
    
    注意: PostgreSQL 是规则的主数据源，JSON 文件仅作备份用途。
    规则的读取（get_reconciliation_rule）和使用（reconciliation_start）
    都直接从 PostgreSQL 数据库读取，不依赖 JSON 文件。
    """
    valid, user_info, err = _require_auth(args)
    if not valid:
        return {"success": False, "error": err}
    name = args.get("name", "").strip()
    description = args.get("description", name)
    rule_template = args.get("rule_template")
    visibility = args.get("visibility", "department")  # 默认改为 department
    tags = args.get("tags", [])

    if not name:
        return {"success": False, "error": "规则名称不能为空"}
    if not rule_template:
        return {"success": False, "error": "规则模板不能为空"}

    try:
        # 1️⃣ 保存到 PostgreSQL 数据库
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
        
        logger.info(f"规则已保存到数据库: {name} (id={rule.get('id')}), 创建者: {user_info['username']}")
        
        # 2️⃣ 保存 schema 为 JSON 文件（备份）
        success, schema_filename, save_error = _save_schema_file(rule_template, name)
        if not success:
            logger.warning(f"保存规则 schema 文件失败 (数据库保存已成功): {save_error}")
        
        # ✅ 成功（主要是保存到 PostgreSQL，JSON 文件失败不影响）
        return {
            "success": True,
            "rule": rule,
            "message": f"规则 '{name}' 已保存到 PostgreSQL",
            "details": {
                "saved_to_db": True,
                "schema_file": schema_filename if success else None,
            }
        }
        
    except Exception as e:
        logger.error(f"保存规则时发生异常: {e}")
        logger.exception(e)
        return {
            "success": False,
            "error": f"规则保存失败: {str(e)}"
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
    """删除规则
    
    流程:
    1. 从 PostgreSQL 数据库删除规则记录（主操作）
    2. 删除对应的 JSON schema 文件（备份）
    
    注意: PostgreSQL 是规则的主数据源，删除 PostgreSQL 记录即删除规则。
    JSON 文件的删除仅为了保持备份的一致性。
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

    # 检查权限
    if not auth_db.can_user_modify_rule(user_info["user_id"], user_info["role"], rule):
        return {"success": False, "error": "无权删除此规则"}

    rule_name = rule.get("name", "")
    
    # 1️⃣ 删除数据库记录（主操作）
    success = auth_db.delete_rule(rule_id)
    if not success:
        return {"success": False, "error": "删除数据库记录失败"}

    logger.info(f"规则已从 PostgreSQL 删除: {rule_name} (id={rule_id})")
    
    # 2️⃣ 删除对应的 JSON 文件备份
    try:
        type_key = _translate_rule_name_to_type_key(rule_name)
        schema_filename = f"{type_key}_schema.json"
        schema_path = SCHEMA_DIR / schema_filename
        
        if schema_path.exists():
            schema_path.unlink()
            logger.info(f"已删除 JSON 备份文件: {schema_path}")
        else:
            logger.info(f"JSON 备份文件不存在（无需删除）: {schema_path}")
    except Exception as e:
        logger.warning(f"删除 JSON 备份文件失败（不影响主操作）: {e}")

    return {
        "success": True,
        "message": f"规则「{rule_name}」已删除",
    }


async def _handle_search_rules_by_mapping(args: dict) -> dict:
    """根据字段映射哈希搜索匹配规则"""
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
    else:
        return {"success": False, "error": "请提供 auth_token 或 guest_token"}

    field_mapping_hash = args.get("field_mapping_hash")
    if not field_mapping_hash:
        return {"success": False, "error": "缺少 field_mapping_hash"}

    limit = args.get("limit", 3)

    try:
        rules = auth_db.search_rules_by_field_mapping(field_mapping_hash, limit)
        return {
            "success": True,
            "rules": rules,
            "count": len(rules),
        }
    except Exception as e:
        logger.error(f"搜索规则失败: {e}")
        return {"success": False, "error": str(e)}


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


async def _handle_batch_get_rules(args: dict) -> dict:
    """批量获取多个规则的详情（含 rule_template）"""
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
    else:
        return {"success": False, "error": "请提供 auth_token 或 guest_token"}

    rule_ids = args.get("rule_ids", [])
    if not rule_ids:
        return {"success": True, "rules": [], "count": 0}

    if not isinstance(rule_ids, list):
        return {"success": False, "error": "rule_ids 必须是数组"}

    # 限制单次请求最多 100 个规则
    if len(rule_ids) > 100:
        rule_ids = rule_ids[:100]
        logger.warning(f"batch_get_rules: 请求超过100条，已截断")

    try:
        rules = auth_db.batch_get_rules_by_ids(rule_ids)
        return {"success": True, "rules": rules, "count": len(rules)}
    except Exception as e:
        logger.error(f"批量获取规则失败: {e}")
        return {"success": False, "error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# 管理员功能
# ══════════════════════════════════════════════════════════════════════════════

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


async def _handle_list_departments(args: dict) -> dict:
    """获取部门列表"""
    admin_token = args.get("admin_token", "")
    company_id = args.get("company_id", "").strip() or None
    
    if not admin_token or admin_token not in ADMIN_TOKENS:
        return {"success": False, "error": "无效的管理员 token，请先登录"}
    
    departments = auth_db.list_departments(company_id)
    return {"success": True, "departments": departments}


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


async def _handle_update_conversation(args: dict) -> dict:
    """更新会话"""
    is_valid, user_info, error = _require_auth(args)
    if not is_valid:
        return {"success": False, "error": error}
    
    user_id = user_info["user_id"]
    conversation_id = args.get("conversation_id", "").strip()
    title = args.get("title", "").strip() or None
    status = args.get("status", "").strip() or None
    
    if not conversation_id:
        return {"success": False, "error": "会话 ID 不能为空"}
    
    conversation = auth_db.update_conversation(conversation_id, user_id, title, status)
    if not conversation:
        return {"success": False, "error": "更新会话失败"}
    
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


# ── 游客认证工具 ──────────────────────────────────────────────────────────

def _create_guest_tools() -> list[mcp_types.Tool]:
    """创建游客认证相关的工具"""
    Tool = mcp_types.Tool
    return [
        Tool(
            name="create_guest_token",
            description="创建游客临时token，用于未登录用户使用部分功能",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "会话ID"},
                    "ip_address": {"type": "string", "description": "用户IP地址（可选）"},
                    "user_agent": {"type": "string", "description": "用户浏览器信息（可选）"},
                },
                "required": ["session_id"],
            },
        ),
        Tool(
            name="verify_guest_token",
            description="验证游客token是否有效",
            inputSchema={
                "type": "object",
                "properties": {
                    "guest_token": {"type": "string", "description": "游客token"},
                },
                "required": ["guest_token"],
            },
        ),
        Tool(
            name="list_recommended_rules",
            description="获取系统推荐规则列表（游客专用，无需登录）",
            inputSchema={
                "type": "object",
                "properties": {
                    "guest_token": {"type": "string", "description": "游客token"},
                },
                "required": ["guest_token"],
            },
        ),
    ]


async def _handle_create_guest_token(args: dict) -> dict:
    """创建游客临时token"""
    session_id = args.get("session_id", "").strip()
    if not session_id:
        return {"success": False, "error": "session_id 不能为空"}
    
    ip_address = args.get("ip_address")
    user_agent = args.get("user_agent")
    
    result = auth_db.create_guest_token(session_id, ip_address, user_agent)
    if not result:
        return {"success": False, "error": "创建游客token失败"}
    
    return {
        "success": True,
        "token": result["token"],
        "usage_count": result["usage_count"],
        "max_usage": result["max_usage"],
        "expires_at": result["expires_at"]
    }


async def _handle_verify_guest_token(args: dict) -> dict:
    """验证游客token"""
    guest_token = args.get("guest_token", "").strip()
    if not guest_token:
        return {"success": False, "error": "guest_token 不能为空"}
    
    result = auth_db.verify_guest_token(guest_token)
    if not result:
        return {"success": False, "valid": False, "error": "token无效"}
    
    if not result.get("valid"):
        return {"success": False, "valid": False, "error": result.get("error", "token已过期")}
    
    return {
        "success": True,
        "valid": True,
        "usage_count": result["usage_count"],
        "max_usage": result["max_usage"],
        "remaining_usage": result["max_usage"] - result["usage_count"]
    }


async def _handle_list_recommended_rules(args: dict) -> dict:
    """获取系统推荐规则列表（游客专用）"""
    guest_token = args.get("guest_token", "").strip()
    if not guest_token:
        return {"success": False, "error": "guest_token 不能为空"}
    
    # 验证token
    token_info = auth_db.verify_guest_token(guest_token)
    if not token_info or not token_info.get("valid"):
        return {"success": False, "error": "无效的token或token已过期"}
    
    # 检查使用次数
    if token_info["usage_count"] >= token_info["max_usage"]:
        return {
            "success": False, 
            "error": "游客使用次数已达上限，请登录后继续使用",
            "code": "GUEST_LIMIT_REACHED"
        }
    
    # 获取推荐规则
    rules = auth_db.list_recommended_rules()
    
    return {
        "success": True,
        "rules": rules,
        "remaining_usage": token_info["max_usage"] - token_info["usage_count"]
    }
