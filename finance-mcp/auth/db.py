"""认证模块的数据库操作"""

import os
import logging
from typing import Optional, Any
from contextlib import contextmanager
import time

import psycopg2
import psycopg2.extras
from psycopg2 import OperationalError, InterfaceError

logger = logging.getLogger(__name__)


def _serialize_datetimes(d: dict) -> dict:
    """将字典中所有 datetime 对象转为 ISO 格式字符串（原地修改并返回）"""
    from datetime import datetime, date
    for k, v in d.items():
        if isinstance(v, (datetime, date)):
            d[k] = v.isoformat()
    return d


def _get_db_config() -> dict:
    """获取数据库连接配置 - 引用统一的 db_config"""
    from db_config import db_config
    return db_config.get_connection_params()


def get_conn(max_retries=3, retry_delay=1):
    """获取数据库连接的上下文管理器，带重试机制"""
    for attempt in range(max_retries):
        try:
            conn = psycopg2.connect(**_get_db_config())
            return _ConnectionContextManager(conn)
        except (OperationalError, InterfaceError) as e:
            logger.warning(f"数据库连接失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                logger.error(f"数据库连接失败，已达到最大重试次数: {e}")
                raise


class _ConnectionContextManager:
    """数据库连接的上下文管理器类"""
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            self.conn.close()

    def cursor(self, cursor_factory=None):
        """获取游标，自动处理连接失效"""
        try:
            # 检查连接是否仍然有效
            with self.conn.cursor() as test_cursor:
                test_cursor.execute('SELECT 1')
        except (OperationalError, InterfaceError):
            logger.warning("数据库连接已失效，尝试重新连接")
            self.conn.close()
            # 重新建立连接
            self.conn = psycopg2.connect(**_get_db_config())
        
        return self.conn.cursor(cursor_factory=cursor_factory)

    def commit(self):
        """提交事务"""
        self.conn.commit()

    def rollback(self):
        """回滚事务"""
        self.conn.rollback()


# ── 用户操作 ──────────────────────────────────────────────────────────

def get_user_by_username(username: str) -> Optional[dict]:
    """根据用户名查询用户"""
    sql = """
    SELECT u.id, u.username, u.password_hash, u.email, u.phone, u.role, u.status,
           u.company_id, u.department_id,
           c.name AS company_name,
           d.name AS department_name
    FROM users u
    LEFT JOIN company c ON u.company_id = c.id
    LEFT JOIN departments d ON u.department_id = d.id
    WHERE u.username = %s
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (username,))
                return cur.fetchone()
    except Exception as e:
        logger.error(f"查询用户失败 (username={username}): {e}")
        return None


def get_user_by_id(user_id: str) -> Optional[dict]:
    """根据 ID 查询用户"""
    sql = """
    SELECT u.id, u.username, u.email, u.phone, u.role, u.status,
           u.company_id, u.department_id,
           c.name AS company_name,
           d.name AS department_name
    FROM users u
    LEFT JOIN company c ON u.company_id = c.id
    LEFT JOIN departments d ON u.department_id = d.id
    WHERE u.id = %s
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (user_id,))
                return cur.fetchone()
    except Exception as e:
        logger.error(f"查询用户失败 (user_id={user_id}): {e}")
        return None


def create_user(username: str, password_hash: str, email: str = None,
                phone: str = None, company_id: str = None,
                department_id: str = None, role: str = "member") -> dict:
    """创建新用户，返回用户信息"""
    sql = """
    INSERT INTO users (username, password_hash, email, phone, company_id, department_id, role)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    RETURNING id, username, email, phone, company_id, department_id, role, status
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (username, password_hash, email, phone,
                                  company_id, department_id, role))
                user = cur.fetchone()
                conn.commit()
                return dict(user)
    except Exception as e:
        logger.error(f"创建用户失败 (username={username}): {e}")
        raise


def update_last_login(user_id: str):
    """更新最后登录时间"""
    sql = "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s"
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (user_id,))
                conn.commit()
    except Exception as e:
        logger.error(f"更新登录时间失败 (user_id={user_id}): {e}")
        # Don't raise here as this is not critical for login


# ── 公司/部门查询 ────────────────────────────────────────────────────

def list_companies() -> list[dict]:
    """获取公司列表。"""
    sql = "SELECT id, name, created_at FROM company ORDER BY created_at DESC"
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql)
                return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logger.error(f"查询公司列表失败: {e}")
        return []


def list_departments(company_id: str | None = None) -> list[dict]:
    """获取部门列表，可按公司筛选。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if company_id:
                    cur.execute(
                        """
                        SELECT id, company_id, name, created_at
                        FROM departments
                        WHERE company_id = %s
                        ORDER BY created_at DESC
                        """,
                        (company_id,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, company_id, name, created_at
                        FROM departments
                        ORDER BY created_at DESC
                        """
                    )
                return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logger.error(f"查询部门列表失败 (company_id={company_id}): {e}")
        return []

# ══════════════════════════════════════════════════════════════════════════════
# 公司部门管理
# ══════════════════════════════════════════════════════════════════════════════

def create_company(name: str) -> dict | None:
    """创建公司，返回公司dict或None（如果已存在）"""
    import uuid
    conn = get_conn()
    try:
        with conn as c:
            with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # 检查是否已存在
                cur.execute("SELECT id FROM company WHERE name = %s", (name,))
                if cur.fetchone():
                    return None
                
                # 生成唯一的 code
                code = f"COMP_{uuid.uuid4().hex[:8].upper()}"
                
                cur.execute(
                    "INSERT INTO company (name, code) VALUES (%s, %s) RETURNING id, name, code, created_at",
                    (name, code)
                )
                row = cur.fetchone()
                c.commit()
                return dict(row)
    except Exception as e:
        logger.error(f"创建公司失败: {e}")
        return None


def create_department(company_id: str, name: str) -> dict | None:
    """创建部门，返回部门dict或None（如果已存在）"""
    import uuid
    conn = get_conn()
    try:
        with conn as c:
            with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # 检查是否已存在
                cur.execute(
                    "SELECT id FROM departments WHERE company_id = %s AND name = %s",
                    (company_id, name)
                )
                if cur.fetchone():
                    return None
                
                # 生成唯一的 code
                code = f"DEPT_{uuid.uuid4().hex[:8].upper()}"
                
                cur.execute(
                    "INSERT INTO departments (company_id, name, code) VALUES (%s, %s, %s) RETURNING id, company_id, name, code, created_at",
                    (company_id, name, code)
                )
                row = cur.fetchone()
                c.commit()
                return dict(row)
    except Exception as e:
        logger.error(f"创建部门失败: {e}")
        return None

def get_admin_view() -> dict:
    """获取管理员视图 - 公司部门员工层级"""
    conn = get_conn()
    result = {"companies": []}
    
    try:
        with conn as c:
            with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # 获取所有公司
                cur.execute("SELECT id, name, created_at FROM company ORDER BY name")
                companies = cur.fetchall()
                
                for company in companies:
                    company_id = company["id"]
                    company_data = {
                        "id": str(company["id"]),
                        "name": company["name"],
                        "departments": []
                    }
                    
                    # 获取该公司的部门
                    cur.execute(
                        "SELECT id, name FROM departments WHERE company_id = %s ORDER BY name",
                        (company_id,)
                    )
                    departments = cur.fetchall()
                    
                    for dept in departments:
                        dept_id = dept["id"]
                        dept_data = {
                            "id": str(dept["id"]),
                            "name": dept["name"],
                            "employees": [],
                        }
                        
                        # 获取该部门的员工
                        cur.execute(
                            "SELECT id, username, email FROM users WHERE department_id = %s",
                            (dept_id,)
                        )
                        employees = cur.fetchall()
                        for emp in employees:
                            dept_data["employees"].append({
                                "id": str(emp["id"]),
                                "username": emp["username"],
                                "email": emp.get("email")
                            })
                        
                        company_data["departments"].append(dept_data)
                    
                    result["companies"].append(company_data)
        
        return result
    except Exception as e:
        logger.error(f"获取管理员视图失败: {e}")
        return {"companies": [], "error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# 会话管理
# ══════════════════════════════════════════════════════════════════════════════

def create_conversation(user_id: str, title: str = None) -> dict | None:
    """创建新会话"""
    conn = get_conn()
    try:
        with conn as c:
            with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """INSERT INTO conversations (user_id, title) 
                       VALUES (%s, %s) 
                       RETURNING id, user_id, title, created_at, updated_at, status""",
                    (user_id, title)
                )
                row = cur.fetchone()
                c.commit()
                result = dict(row)
                result["id"] = str(result["id"])
                result["user_id"] = str(result["user_id"])
                _serialize_datetimes(result)
                return result
    except Exception as e:
        logger.error(f"创建会话失败: {e}")
        return None


def get_conversation(conversation_id: str, user_id: str) -> dict | None:
    """获取单个会话（验证所有权）"""
    conn = get_conn()
    try:
        with conn as c:
            with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """SELECT id, user_id, title, created_at, updated_at, status 
                       FROM conversations 
                       WHERE id = %s AND user_id = %s""",
                    (conversation_id, user_id)
                )
                row = cur.fetchone()
                if row:
                    result = dict(row)
                    result["id"] = str(result["id"])
                    result["user_id"] = str(result["user_id"])
                    _serialize_datetimes(result)
                    return result
                return None
    except Exception as e:
        logger.error(f"获取会话失败: {e}")
        return None


def list_conversations(user_id: str, limit: int = 50, offset: int = 0) -> list[dict]:
    """获取用户的会话列表"""
    conn = get_conn()
    try:
        with conn as c:
            with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """SELECT id, user_id, title, created_at, updated_at, status 
                       FROM conversations 
                       WHERE user_id = %s AND status = 'active'
                       ORDER BY updated_at DESC
                       LIMIT %s OFFSET %s""",
                    (user_id, limit, offset)
                )
                rows = cur.fetchall()
                result = []
                for row in rows:
                    item = dict(row)
                    item["id"] = str(item["id"])
                    item["user_id"] = str(item["user_id"])
                    _serialize_datetimes(item)
                    result.append(item)
                return result
    except Exception as e:
        logger.error(f"获取会话列表失败: {e}")
        return []


def update_conversation(conversation_id: str, user_id: str, title: str = None, status: str = None) -> dict | None:
    """更新会话"""
    conn = get_conn()
    try:
        with conn as c:
            with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # 构建更新语句
                updates = []
                params = []
                if title is not None:
                    updates.append("title = %s")
                    params.append(title)
                if status is not None:
                    updates.append("status = %s")
                    params.append(status)
                
                if not updates:
                    return get_conversation(conversation_id, user_id)
                
                params.extend([conversation_id, user_id])
                cur.execute(
                    f"""UPDATE conversations 
                        SET {', '.join(updates)}
                        WHERE id = %s AND user_id = %s
                        RETURNING id, user_id, title, created_at, updated_at, status""",
                    params
                )
                row = cur.fetchone()
                c.commit()
                if row:
                    result = dict(row)
                    result["id"] = str(result["id"])
                    result["user_id"] = str(result["user_id"])
                    _serialize_datetimes(result)
                    return result
                return None
    except Exception as e:
        logger.error(f"更新会话失败: {e}")
        return None


def delete_conversation(conversation_id: str, user_id: str) -> bool:
    """删除会话（物理删除）及关联的历史消息"""
    conn_manager = get_conn()
    try:
        with conn_manager as c:
            with c.cursor() as cur:
                # 1. 删除该会话下的所有消息
                cur.execute("DELETE FROM messages WHERE conversation_id = %s", (conversation_id,))
                # 2. 物理删除会话
                cur.execute(
                    "DELETE FROM conversations WHERE id = %s AND user_id = %s",
                    (conversation_id, user_id)
                )
                c.commit()
                return cur.rowcount > 0
    except Exception as e:
        logger.error(f"删除会话失败: {e}")
        try:
            conn_manager.rollback()
        except Exception:
            pass
        return False


def save_message(conversation_id: str, role: str, content: str, metadata: dict = None, attachments: list = None) -> dict | None:
    """保存消息（支持附件，向后兼容）"""
    import json
    conn = get_conn()
    try:
        with conn as c:
            with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # 尝试使用新的 attachments 列（如果存在）
                try:
                    cur.execute(
                        """INSERT INTO messages (conversation_id, role, content, metadata, attachments)
                           VALUES (%s, %s, %s, %s, %s)
                           RETURNING id, conversation_id, role, content, metadata, attachments, created_at""",
                        (conversation_id, role, content, json.dumps(metadata or {}), json.dumps(attachments or []))
                    )
                    row = cur.fetchone()
                except Exception as column_error:
                    # 如果 attachments 列不存在，回退到旧版本（不包含 attachments）
                    logger.warning(f"attachments 列不存在，使用旧版本保存: {column_error}")
                    cur.execute(
                        """INSERT INTO messages (conversation_id, role, content, metadata)
                           VALUES (%s, %s, %s, %s)
                           RETURNING id, conversation_id, role, content, metadata, created_at""",
                        (conversation_id, role, content, json.dumps(metadata or {}))
                    )
                    row = cur.fetchone()

                # 同时更新会话的 updated_at
                cur.execute(
                    "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                    (conversation_id,)
                )

                c.commit()
                if row:
                    result = dict(row)
                    result["id"] = str(result["id"])
                    result["conversation_id"] = str(result["conversation_id"])
                    # 确保总是返回 attachments 字段（即使是空数组）
                    if "attachments" not in result:
                        result["attachments"] = []
                    _serialize_datetimes(result)
                    return result
                return None
    except Exception as e:
        logger.error(f"保存消息失败: {e}")
        return None


def should_display_message(role: str, content: str, metadata: dict = None) -> bool:
    """判断消息是否应该显示给用户。

    过滤掉以下类型的消息：
    - JSON响应（意图识别等）
    - HTML表单
    - 代码块
    - 系统消息
    - 进度提示消息（包含SPINNER等临时标记）

    Args:
        role: 消息角色 (user/assistant/system)
        content: 消息内容
        metadata: 可选的元数据

    Returns:
        True 表示应该显示，False 表示应该过滤掉
    """
    if not content:
        return False

    content_stripped = content.strip()

    # 过滤JSON响应
    if content_stripped.startswith("{") or content_stripped.startswith("["):
        return False

    # 过滤代码块
    if content_stripped.startswith("```"):
        return False

    # 过滤HTML表单
    if content_stripped.startswith("<"):
        return False

    # 过滤系统消息
    if role == "system":
        return False

    # 过滤进度消息（临时指示器）
    progress_patterns = [
        "{{SPINNER}}",
        "正在保存",
        "📊 进度：",
    ]
    for pattern in progress_patterns:
        if pattern in content:
            return False

    return True


def get_messages(conversation_id: str, limit: int = 100, offset: int = 0) -> list[dict]:
    """获取会话的消息列表（已过滤不应显示的消息，向后兼容）"""
    conn = get_conn()
    try:
        with conn as c:
            with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # 尝试查询包含 attachments 列
                try:
                    cur.execute(
                        """SELECT id, conversation_id, role, content, metadata, attachments, created_at
                           FROM messages
                           WHERE conversation_id = %s
                           ORDER BY created_at ASC
                           LIMIT %s OFFSET %s""",
                        (conversation_id, limit, offset)
                    )
                except Exception as column_error:
                    # 如果 attachments 列不存在，查询不包含它
                    logger.warning(f"attachments 列不存在，使用旧版本查询: {column_error}")
                    cur.execute(
                        """SELECT id, conversation_id, role, content, metadata, created_at
                           FROM messages
                           WHERE conversation_id = %s
                           ORDER BY created_at ASC
                           LIMIT %s OFFSET %s""",
                        (conversation_id, limit, offset)
                    )

                rows = cur.fetchall()
                result = []
                for row in rows:
                    # 应用过滤器：只返回应该显示的消息
                    if should_display_message(row["role"], row["content"], row.get("metadata")):
                        item = dict(row)
                        item["id"] = str(item["id"])
                        item["conversation_id"] = str(item["conversation_id"])
                        # 确保 attachments 总是一个列表
                        if "attachments" not in item or item.get("attachments") is None:
                            item["attachments"] = []
                        _serialize_datetimes(item)
                        result.append(item)
                return result
    except Exception as e:
        logger.error(f"获取消息列表失败: {e}")
        return []
