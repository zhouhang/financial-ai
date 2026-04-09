"""认证模块的数据库操作"""

import logging
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
import time

import psycopg2
import psycopg2.extras
from psycopg2 import OperationalError, InterfaceError

try:
    from auth.crypto import open_secret, seal_secret
except Exception:
    # Fallback to plain text in environments where encryption helpers are unavailable.
    def seal_secret(value: str) -> str:
        return value or ""

    def open_secret(value: str) -> str:
        return value or ""

logger = logging.getLogger(__name__)


def _serialize_datetimes(d: dict) -> dict:
    """将字典中所有 datetime 对象转为 ISO 格式字符串（原地修改并返回）"""
    from datetime import datetime, date
    for k, v in d.items():
        if isinstance(v, (datetime, date)):
            d[k] = v.isoformat()
    return d


def _normalize_record(row: dict, decrypt_fields: list[str] | None = None) -> dict:
    """标准化数据库记录（UUID/Datetime 转字符串，可选解密字段）。"""
    from datetime import datetime, date
    import uuid

    result: dict = {}
    for key, value in row.items():
        if isinstance(value, uuid.UUID):
            result[key] = str(value)
        elif isinstance(value, (datetime, date)):
            result[key] = value.isoformat()
        else:
            result[key] = value

    if decrypt_fields:
        for field in decrypt_fields:
            if field in result:
                result[field] = open_secret(result.get(field) or "")

    return result


def _seal_json_payload(payload: Any) -> str:
    """将结构化 payload 序列化后密封存储。"""
    if payload in (None, "", {}):
        return ""
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return seal_secret(raw)


def _open_json_payload(value: str | None) -> dict[str, Any]:
    """读取密封后的 JSON payload。"""
    raw = open_secret(value or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except Exception:
        return {"raw": raw}


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


def get_company_channel_config(
    company_id: str | None = None,
    provider: str = "dingtalk_dws",
    channel_code: str = "default",
) -> dict | None:
    """查询一个公司的启用 channel 配置；未传 company_id 时返回默认配置。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if company_id:
                    cur.execute(
                        """
                        SELECT id, company_id, provider, channel_code, name,
                               client_id, client_secret, robot_code, extra,
                               is_default, is_enabled, created_at, updated_at
                        FROM company_channel_configs
                        WHERE company_id = %s
                          AND provider = %s
                          AND is_enabled = TRUE
                        ORDER BY
                          (channel_code = %s) DESC,
                          is_default DESC,
                          updated_at DESC,
                          created_at DESC
                        LIMIT 1
                        """,
                        (company_id, provider, channel_code),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, company_id, provider, channel_code, name,
                               client_id, client_secret, robot_code, extra,
                               is_default, is_enabled, created_at, updated_at
                        FROM company_channel_configs
                        WHERE provider = %s
                          AND is_enabled = TRUE
                        ORDER BY
                          is_default DESC,
                          (channel_code = %s) DESC,
                          updated_at DESC,
                          created_at DESC
                        LIMIT 1
                        """,
                        (provider, channel_code),
                    )
                row = cur.fetchone()
                return dict(row) if row else None
    except Exception as e:
        logger.error(
            f"查询 company_channel_configs 失败 (company_id={company_id}, provider={provider}, channel_code={channel_code}): {e}"
        )
        return None


def upsert_company_channel_config(
    *,
    company_id: str,
    provider: str,
    channel_code: str = "default",
    name: str = "",
    client_id: str = "",
    client_secret: str = "",
    robot_code: str = "",
    extra: dict | None = None,
    is_default: bool = False,
    is_enabled: bool = True,
) -> dict | None:
    """创建或更新公司 channel 配置。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO company_channel_configs (
                        company_id, provider, channel_code, name,
                        client_id, client_secret, robot_code, extra,
                        is_default, is_enabled
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                    ON CONFLICT (company_id, provider, channel_code)
                    DO UPDATE SET
                        name = EXCLUDED.name,
                        client_id = EXCLUDED.client_id,
                        client_secret = EXCLUDED.client_secret,
                        robot_code = EXCLUDED.robot_code,
                        extra = EXCLUDED.extra,
                        is_default = EXCLUDED.is_default,
                        is_enabled = EXCLUDED.is_enabled,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id, company_id, provider, channel_code, name,
                              client_id, client_secret, robot_code, extra,
                              is_default, is_enabled, created_at, updated_at
                    """,
                    (
                        company_id,
                        provider,
                        channel_code,
                        name,
                        client_id,
                        client_secret,
                        robot_code,
                        psycopg2.extras.Json(extra or {}),
                        is_default,
                        is_enabled,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return dict(row) if row else None
    except Exception as e:
        logger.error(
            f"写入 company_channel_configs 失败 (company_id={company_id}, provider={provider}, channel_code={channel_code}): {e}"
        )
        return None

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


# ══════════════════════════════════════════════════════════════════════════════
# 数据连接（平台应用/店铺连接/授权/同步源/授权会话）
# ══════════════════════════════════════════════════════════════════════════════

def upsert_platform_app(
    *,
    company_id: str,
    platform_code: str,
    app_key: str,
    app_secret: str,
    app_name: str = "",
    app_type: str = "isv",
    auth_base_url: str = "",
    token_url: str = "",
    refresh_url: str = "",
    scopes_config: list | None = None,
    extra: dict | None = None,
    status: str = "active",
    include_secrets: bool = False,
) -> dict | None:
    """创建或更新平台应用配置。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO platform_apps (
                        company_id, platform_code, app_name, app_key, app_secret,
                        app_type, auth_base_url, token_url, refresh_url,
                        scopes_config, extra, status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
                    ON CONFLICT (company_id, platform_code, app_key)
                    DO UPDATE SET
                        app_name = EXCLUDED.app_name,
                        app_secret = EXCLUDED.app_secret,
                        app_type = EXCLUDED.app_type,
                        auth_base_url = EXCLUDED.auth_base_url,
                        token_url = EXCLUDED.token_url,
                        refresh_url = EXCLUDED.refresh_url,
                        scopes_config = EXCLUDED.scopes_config,
                        extra = EXCLUDED.extra,
                        status = EXCLUDED.status,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id, company_id, platform_code, app_name, app_key, app_secret,
                              app_type, auth_base_url, token_url, refresh_url,
                              scopes_config, extra, status, created_at, updated_at
                    """,
                    (
                        company_id,
                        platform_code,
                        app_name,
                        app_key,
                        seal_secret(app_secret),
                        app_type,
                        auth_base_url,
                        token_url,
                        refresh_url,
                        psycopg2.extras.Json(scopes_config or []),
                        psycopg2.extras.Json(extra or {}),
                        status,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                if not row:
                    return None
                result = _normalize_record(dict(row))
                if include_secrets:
                    result["app_secret"] = open_secret(result.get("app_secret") or "")
                else:
                    result["app_secret"] = ""
                return result
    except Exception as e:
        logger.error(
            f"写入 platform_apps 失败 (company_id={company_id}, platform_code={platform_code}): {e}"
        )
        return None


def get_platform_app(
    *,
    company_id: str,
    platform_code: str,
    app_key: str | None = None,
    include_secrets: bool = False,
) -> dict | None:
    """查询平台应用配置。未传 app_key 时按更新时间倒序取最新一条。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if app_key:
                    cur.execute(
                        """
                        SELECT id, company_id, platform_code, app_name, app_key, app_secret,
                               app_type, auth_base_url, token_url, refresh_url,
                               scopes_config, extra, status, created_at, updated_at
                        FROM platform_apps
                        WHERE company_id = %s
                          AND platform_code = %s
                          AND app_key = %s
                        LIMIT 1
                        """,
                        (company_id, platform_code, app_key),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, company_id, platform_code, app_name, app_key, app_secret,
                               app_type, auth_base_url, token_url, refresh_url,
                               scopes_config, extra, status, created_at, updated_at
                        FROM platform_apps
                        WHERE company_id = %s
                          AND platform_code = %s
                          AND status <> 'deleted'
                        ORDER BY updated_at DESC, created_at DESC
                        LIMIT 1
                        """,
                        (company_id, platform_code),
                    )
                row = cur.fetchone()
                if not row:
                    return None
                result = _normalize_record(dict(row))
                if include_secrets:
                    result["app_secret"] = open_secret(result.get("app_secret") or "")
                else:
                    result["app_secret"] = ""
                return result
    except Exception as e:
        logger.error(
            f"查询 platform_apps 失败 (company_id={company_id}, platform_code={platform_code}, app_key={app_key}): {e}"
        )
        return None


def list_platform_apps(company_id: str, include_secrets: bool = False) -> list[dict]:
    """列出某公司全部平台应用配置。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, platform_code, app_name, app_key, app_secret,
                           app_type, auth_base_url, token_url, refresh_url,
                           scopes_config, extra, status, created_at, updated_at
                    FROM platform_apps
                    WHERE company_id = %s
                    ORDER BY platform_code ASC, updated_at DESC
                    """,
                    (company_id,),
                )
                rows = cur.fetchall()
                result = []
                for row in rows:
                    item = _normalize_record(dict(row))
                    if include_secrets:
                        item["app_secret"] = open_secret(item.get("app_secret") or "")
                    else:
                        item["app_secret"] = ""
                    result.append(item)
                return result
    except Exception as e:
        logger.error(f"查询 platform_apps 列表失败 (company_id={company_id}): {e}")
        return []


def upsert_shop_connection(
    *,
    company_id: str,
    platform_code: str,
    external_shop_id: str,
    external_shop_name: str = "",
    external_seller_id: str = "",
    auth_subject_name: str = "",
    shop_type: str = "standard",
    status: str = "active",
    meta: dict | None = None,
) -> dict | None:
    """创建或更新店铺连接记录。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO shop_connections (
                        company_id, platform_code, external_shop_id, external_shop_name,
                        external_seller_id, auth_subject_name, shop_type, status, meta
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (company_id, platform_code, external_shop_id)
                    DO UPDATE SET
                        external_shop_name = EXCLUDED.external_shop_name,
                        external_seller_id = EXCLUDED.external_seller_id,
                        auth_subject_name = EXCLUDED.auth_subject_name,
                        shop_type = EXCLUDED.shop_type,
                        status = EXCLUDED.status,
                        meta = EXCLUDED.meta,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id, company_id, platform_code, external_shop_id, external_shop_name,
                              external_seller_id, auth_subject_name, shop_type, status, meta,
                              created_at, updated_at
                    """,
                    (
                        company_id,
                        platform_code,
                        external_shop_id,
                        external_shop_name,
                        external_seller_id,
                        auth_subject_name,
                        shop_type,
                        status,
                        psycopg2.extras.Json(meta or {}),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"写入 shop_connections 失败 (company_id={company_id}, platform_code={platform_code}, external_shop_id={external_shop_id}): {e}"
        )
        return None


def get_shop_connection(
    *,
    company_id: str,
    platform_code: str,
    external_shop_id: str,
) -> dict | None:
    """按平台店铺编码查询店铺连接。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, platform_code, external_shop_id, external_shop_name,
                           external_seller_id, auth_subject_name, shop_type, status, meta,
                           created_at, updated_at
                    FROM shop_connections
                    WHERE company_id = %s
                      AND platform_code = %s
                      AND external_shop_id = %s
                    LIMIT 1
                    """,
                    (company_id, platform_code, external_shop_id),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"查询 shop_connections 失败 (company_id={company_id}, platform_code={platform_code}, external_shop_id={external_shop_id}): {e}"
        )
        return None


def get_shop_connection_by_id(shop_connection_id: str) -> dict | None:
    """按主键查询店铺连接。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, platform_code, external_shop_id, external_shop_name,
                           external_seller_id, auth_subject_name, shop_type, status, meta,
                           created_at, updated_at
                    FROM shop_connections
                    WHERE id = %s
                    LIMIT 1
                    """,
                    (shop_connection_id,),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"按 id 查询 shop_connections 失败 (id={shop_connection_id}): {e}")
        return None


def list_shop_connections(
    *,
    company_id: str,
    platform_code: str | None = None,
    include_deleted: bool = False,
) -> list[dict]:
    """查询公司下店铺连接列表，可按平台筛选。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if platform_code:
                    if include_deleted:
                        cur.execute(
                            """
                            SELECT id, company_id, platform_code, external_shop_id, external_shop_name,
                                   external_seller_id, auth_subject_name, shop_type, status, meta,
                                   created_at, updated_at
                            FROM shop_connections
                            WHERE company_id = %s
                              AND platform_code = %s
                            ORDER BY updated_at DESC, created_at DESC
                            """,
                            (company_id, platform_code),
                        )
                    else:
                        cur.execute(
                            """
                            SELECT id, company_id, platform_code, external_shop_id, external_shop_name,
                                   external_seller_id, auth_subject_name, shop_type, status, meta,
                                   created_at, updated_at
                            FROM shop_connections
                            WHERE company_id = %s
                              AND platform_code = %s
                              AND status <> 'deleted'
                            ORDER BY updated_at DESC, created_at DESC
                            """,
                            (company_id, platform_code),
                        )
                else:
                    if include_deleted:
                        cur.execute(
                            """
                            SELECT id, company_id, platform_code, external_shop_id, external_shop_name,
                                   external_seller_id, auth_subject_name, shop_type, status, meta,
                                   created_at, updated_at
                            FROM shop_connections
                            WHERE company_id = %s
                            ORDER BY platform_code ASC, updated_at DESC
                            """,
                            (company_id,),
                        )
                    else:
                        cur.execute(
                            """
                            SELECT id, company_id, platform_code, external_shop_id, external_shop_name,
                                   external_seller_id, auth_subject_name, shop_type, status, meta,
                                   created_at, updated_at
                            FROM shop_connections
                            WHERE company_id = %s
                              AND status <> 'deleted'
                            ORDER BY platform_code ASC, updated_at DESC
                            """,
                            (company_id,),
                        )

                rows = cur.fetchall()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(f"查询 shop_connections 列表失败 (company_id={company_id}): {e}")
        return []


def update_shop_connection_status(
    *,
    shop_connection_id: str,
    status: str,
) -> dict | None:
    """更新店铺连接状态。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE shop_connections
                    SET status = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING id, company_id, platform_code, external_shop_id, external_shop_name,
                              external_seller_id, auth_subject_name, shop_type, status, meta,
                              created_at, updated_at
                    """,
                    (status, shop_connection_id),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 shop_connections 状态失败 (id={shop_connection_id}, status={status}): {e}")
        return None


def create_shop_authorization(
    *,
    company_id: str,
    shop_connection_id: str,
    platform_app_id: str,
    access_token: str,
    refresh_token: str = "",
    auth_type: str = "oauth_code",
    token_expires_at: str | None = None,
    refresh_expires_at: str | None = None,
    scope_text: str = "",
    auth_status: str = "authorized",
    last_error: str = "",
    raw_auth_payload: dict | None = None,
    include_secrets: bool = False,
) -> dict | None:
    """创建新的店铺授权记录，并将历史 current 记录置为 false。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE shop_authorizations
                    SET is_current = false,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE shop_connection_id = %s
                      AND is_current = true
                    """,
                    (shop_connection_id,),
                )

                cur.execute(
                    """
                    INSERT INTO shop_authorizations (
                        company_id, shop_connection_id, platform_app_id, auth_type,
                        access_token, refresh_token, token_expires_at, refresh_expires_at,
                        scope_text, auth_status, is_current, auth_time, last_refresh_at,
                        last_error, raw_auth_payload
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
                        %s, %s::jsonb
                    )
                    RETURNING id, company_id, shop_connection_id, platform_app_id, auth_type,
                              access_token, refresh_token, token_expires_at, refresh_expires_at,
                              scope_text, auth_status, is_current, auth_time, last_refresh_at,
                              last_error, raw_auth_payload, created_at, updated_at
                    """,
                    (
                        company_id,
                        shop_connection_id,
                        platform_app_id,
                        auth_type,
                        seal_secret(access_token),
                        seal_secret(refresh_token),
                        token_expires_at,
                        refresh_expires_at,
                        scope_text,
                        auth_status,
                        last_error,
                        psycopg2.extras.Json(raw_auth_payload or {}),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                if not row:
                    return None
                result = _normalize_record(dict(row))
                if include_secrets:
                    result["access_token"] = open_secret(result.get("access_token") or "")
                    result["refresh_token"] = open_secret(result.get("refresh_token") or "")
                else:
                    result["access_token"] = ""
                    result["refresh_token"] = ""
                return result
    except Exception as e:
        logger.error(
            f"创建 shop_authorizations 失败 (company_id={company_id}, shop_connection_id={shop_connection_id}): {e}"
        )
        return None


def get_current_shop_authorization(
    *,
    shop_connection_id: str,
    include_secrets: bool = False,
) -> dict | None:
    """查询店铺当前有效授权记录。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, shop_connection_id, platform_app_id, auth_type,
                           access_token, refresh_token, token_expires_at, refresh_expires_at,
                           scope_text, auth_status, is_current, auth_time, last_refresh_at,
                           last_error, raw_auth_payload, created_at, updated_at
                    FROM shop_authorizations
                    WHERE shop_connection_id = %s
                      AND is_current = true
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (shop_connection_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                result = _normalize_record(dict(row))
                if include_secrets:
                    result["access_token"] = open_secret(result.get("access_token") or "")
                    result["refresh_token"] = open_secret(result.get("refresh_token") or "")
                else:
                    result["access_token"] = ""
                    result["refresh_token"] = ""
                return result
    except Exception as e:
        logger.error(f"查询当前 shop_authorizations 失败 (shop_connection_id={shop_connection_id}): {e}")
        return None


def update_shop_authorization_tokens(
    *,
    authorization_id: str,
    access_token: str,
    refresh_token: str = "",
    token_expires_at: str | None = None,
    refresh_expires_at: str | None = None,
    scope_text: str | None = None,
    auth_status: str = "authorized",
    raw_auth_payload: dict | None = None,
) -> dict | None:
    """刷新授权 token。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE shop_authorizations
                    SET access_token = %s,
                        refresh_token = %s,
                        token_expires_at = %s,
                        refresh_expires_at = %s,
                        scope_text = COALESCE(%s, scope_text),
                        auth_status = %s,
                        last_refresh_at = CURRENT_TIMESTAMP,
                        raw_auth_payload = CASE
                            WHEN %s::jsonb = '{}'::jsonb THEN raw_auth_payload
                            ELSE %s::jsonb
                        END,
                        last_error = '',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING id, company_id, shop_connection_id, platform_app_id, auth_type,
                              access_token, refresh_token, token_expires_at, refresh_expires_at,
                              scope_text, auth_status, is_current, auth_time, last_refresh_at,
                              last_error, raw_auth_payload, created_at, updated_at
                    """,
                    (
                        seal_secret(access_token),
                        seal_secret(refresh_token),
                        token_expires_at,
                        refresh_expires_at,
                        scope_text,
                        auth_status,
                        psycopg2.extras.Json(raw_auth_payload or {}),
                        psycopg2.extras.Json(raw_auth_payload or {}),
                        authorization_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                if not row:
                    return None
                result = _normalize_record(dict(row), decrypt_fields=["access_token", "refresh_token"])
                return result
    except Exception as e:
        logger.error(f"更新 shop_authorizations token 失败 (id={authorization_id}): {e}")
        return None


def update_shop_authorization_status(
    *,
    authorization_id: str,
    auth_status: str,
    last_error: str = "",
    is_current: bool | None = None,
) -> dict | None:
    """更新授权状态。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if is_current is None:
                    cur.execute(
                        """
                        UPDATE shop_authorizations
                        SET auth_status = %s,
                            last_error = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                        RETURNING id, company_id, shop_connection_id, platform_app_id, auth_type,
                                  access_token, refresh_token, token_expires_at, refresh_expires_at,
                                  scope_text, auth_status, is_current, auth_time, last_refresh_at,
                                  last_error, raw_auth_payload, created_at, updated_at
                        """,
                        (auth_status, last_error, authorization_id),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE shop_authorizations
                        SET auth_status = %s,
                            last_error = %s,
                            is_current = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                        RETURNING id, company_id, shop_connection_id, platform_app_id, auth_type,
                                  access_token, refresh_token, token_expires_at, refresh_expires_at,
                                  scope_text, auth_status, is_current, auth_time, last_refresh_at,
                                  last_error, raw_auth_payload, created_at, updated_at
                        """,
                        (auth_status, last_error, is_current, authorization_id),
                    )

                row = cur.fetchone()
                conn.commit()
                if not row:
                    return None
                result = _normalize_record(dict(row))
                result["access_token"] = ""
                result["refresh_token"] = ""
                return result
    except Exception as e:
        logger.error(f"更新 shop_authorizations 状态失败 (id={authorization_id}): {e}")
        return None


def upsert_sync_source(
    *,
    company_id: str,
    shop_connection_id: str,
    source_type: str,
    enabled: bool = True,
    sync_strategy: str = "full_then_incremental",
    last_sync_cursor: str = "",
    last_sync_at: str | None = None,
    last_success_at: str | None = None,
    last_status: str = "idle",
    last_error: str = "",
    extra: dict | None = None,
) -> dict | None:
    """创建或更新同步源配置。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO sync_sources (
                        company_id, shop_connection_id, source_type, enabled,
                        sync_strategy, last_sync_cursor, last_sync_at, last_success_at,
                        last_status, last_error, extra
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (shop_connection_id, source_type)
                    DO UPDATE SET
                        enabled = EXCLUDED.enabled,
                        sync_strategy = EXCLUDED.sync_strategy,
                        last_sync_cursor = EXCLUDED.last_sync_cursor,
                        last_sync_at = EXCLUDED.last_sync_at,
                        last_success_at = EXCLUDED.last_success_at,
                        last_status = EXCLUDED.last_status,
                        last_error = EXCLUDED.last_error,
                        extra = EXCLUDED.extra,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id, company_id, shop_connection_id, source_type, enabled,
                              sync_strategy, last_sync_cursor, last_sync_at, last_success_at,
                              last_status, last_error, extra, created_at, updated_at
                    """,
                    (
                        company_id,
                        shop_connection_id,
                        source_type,
                        enabled,
                        sync_strategy,
                        last_sync_cursor,
                        last_sync_at,
                        last_success_at,
                        last_status,
                        last_error,
                        psycopg2.extras.Json(extra or {}),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"写入 sync_sources 失败 (company_id={company_id}, shop_connection_id={shop_connection_id}, source_type={source_type}): {e}"
        )
        return None


def list_sync_sources(
    *,
    company_id: str,
    shop_connection_id: str | None = None,
) -> list[dict]:
    """列出同步源配置。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if shop_connection_id:
                    cur.execute(
                        """
                        SELECT id, company_id, shop_connection_id, source_type, enabled,
                               sync_strategy, last_sync_cursor, last_sync_at, last_success_at,
                               last_status, last_error, extra, created_at, updated_at
                        FROM sync_sources
                        WHERE company_id = %s
                          AND shop_connection_id = %s
                        ORDER BY source_type ASC
                        """,
                        (company_id, shop_connection_id),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, company_id, shop_connection_id, source_type, enabled,
                               sync_strategy, last_sync_cursor, last_sync_at, last_success_at,
                               last_status, last_error, extra, created_at, updated_at
                        FROM sync_sources
                        WHERE company_id = %s
                        ORDER BY shop_connection_id ASC, source_type ASC
                        """,
                        (company_id,),
                    )
                rows = cur.fetchall()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(
            f"查询 sync_sources 失败 (company_id={company_id}, shop_connection_id={shop_connection_id}): {e}"
        )
        return []


def create_auth_session(
    *,
    company_id: str,
    platform_code: str,
    state_token: str,
    expires_at: str,
    operator_user_id: str | None = None,
    shop_connection_id: str | None = None,
    return_path: str = "",
    redirect_uri: str = "",
) -> dict | None:
    """创建授权会话。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO auth_sessions (
                        company_id, platform_code, operator_user_id, shop_connection_id,
                        state_token, return_path, redirect_uri, status, expires_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending', %s)
                    RETURNING id, company_id, platform_code, operator_user_id, shop_connection_id,
                              state_token, return_path, redirect_uri, status, expires_at,
                              callback_code, callback_error, callback_payload,
                              created_at, updated_at, completed_at
                    """,
                    (
                        company_id,
                        platform_code,
                        operator_user_id,
                        shop_connection_id,
                        state_token,
                        return_path,
                        redirect_uri,
                        expires_at,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"创建 auth_sessions 失败 (company_id={company_id}, platform_code={platform_code}, state={state_token}): {e}"
        )
        return None


def get_auth_session_by_state(state_token: str) -> dict | None:
    """按 state token 查询授权会话。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, platform_code, operator_user_id, shop_connection_id,
                           state_token, return_path, redirect_uri, status, expires_at,
                           callback_code, callback_error, callback_payload,
                           created_at, updated_at, completed_at
                    FROM auth_sessions
                    WHERE state_token = %s
                    LIMIT 1
                    """,
                    (state_token,),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"查询 auth_sessions 失败 (state_token={state_token}): {e}")
        return None


def update_auth_session_callback(
    *,
    session_id: str,
    status: str,
    callback_code: str = "",
    callback_error: str = "",
    callback_payload: dict | None = None,
) -> dict | None:
    """更新授权回调结果。status 通常为 authorized/failed/expired/cancelled。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE auth_sessions
                    SET status = %s,
                        callback_code = %s,
                        callback_error = %s,
                        callback_payload = %s::jsonb,
                        completed_at = CASE
                            WHEN %s IN ('authorized', 'failed', 'expired', 'cancelled')
                            THEN CURRENT_TIMESTAMP
                            ELSE completed_at
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING id, company_id, platform_code, operator_user_id, shop_connection_id,
                              state_token, return_path, redirect_uri, status, expires_at,
                              callback_code, callback_error, callback_payload,
                              created_at, updated_at, completed_at
                    """,
                    (
                        status,
                        callback_code,
                        callback_error,
                        psycopg2.extras.Json(callback_payload or {}),
                        status,
                        session_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 auth_sessions 回调结果失败 (id={session_id}, status={status}): {e}")
        return None


def list_auth_sessions(
    *,
    company_id: str,
    platform_code: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """查询授权会话列表。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT id, company_id, platform_code, operator_user_id, shop_connection_id,
                           state_token, return_path, redirect_uri, status, expires_at,
                           callback_code, callback_error, callback_payload,
                           created_at, updated_at, completed_at
                    FROM auth_sessions
                    WHERE company_id = %s
                """
                params: list = [company_id]
                if platform_code:
                    sql += " AND platform_code = %s"
                    params.append(platform_code)
                if status:
                    sql += " AND status = %s"
                    params.append(status)
                sql += " ORDER BY created_at DESC LIMIT %s"
                params.append(limit)
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(
            f"查询 auth_sessions 列表失败 (company_id={company_id}, platform_code={platform_code}, status={status}): {e}"
        )
        return []


# ══════════════════════════════════════════════════════════════════════════════
# 通用数据连接模型（data_sources / sync_jobs / dataset_snapshots）
# ══════════════════════════════════════════════════════════════════════════════


def create_data_source(
    *,
    company_id: str,
    source_kind: str,
    domain_type: str,
    provider_code: str,
    source_code: str,
    name: str,
    execution_mode: str = "deterministic",
    description: str = "",
    status: str = "active",
    capabilities: list[str] | None = None,
    created_by: str | None = None,
    updated_by: str | None = None,
) -> dict | None:
    """创建数据源。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO data_sources (
                        company_id, source_kind, domain_type, execution_mode,
                        provider_code, source_code, name, description, status,
                        capabilities, created_by, updated_by
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                    RETURNING id, company_id, source_kind, domain_type, execution_mode,
                              provider_code, source_code, name, description, status,
                              capabilities, last_test_status, last_test_at, last_test_error,
                              created_by, updated_by, created_at, updated_at
                    """,
                    (
                        company_id,
                        source_kind,
                        domain_type,
                        execution_mode,
                        provider_code,
                        source_code,
                        name,
                        description,
                        status,
                        psycopg2.extras.Json(capabilities or []),
                        created_by,
                        updated_by,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"创建 data_sources 失败 (company_id={company_id}, source_code={source_code}): {e}")
        return None


def update_data_source(
    *,
    data_source_id: str,
    company_id: str,
    name: str | None = None,
    description: str | None = None,
    status: str | None = None,
    capabilities: list[str] | None = None,
    updated_by: str | None = None,
    last_test_status: str | None = None,
    last_test_error: str | None = None,
    touch_last_test_at: bool = False,
) -> dict | None:
    """更新数据源基础信息。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE data_sources
                    SET name = COALESCE(%s, name),
                        description = COALESCE(%s, description),
                        status = COALESCE(%s, status),
                        capabilities = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN capabilities
                            ELSE %s::jsonb
                        END,
                        updated_by = COALESCE(%s, updated_by),
                        last_test_status = COALESCE(%s, last_test_status),
                        last_test_error = COALESCE(%s, last_test_error),
                        last_test_at = CASE
                            WHEN %s THEN CURRENT_TIMESTAMP
                            ELSE last_test_at
                        END
                    WHERE id = %s
                      AND company_id = %s
                    RETURNING id, company_id, source_kind, domain_type, execution_mode,
                              provider_code, source_code, name, description, status,
                              capabilities, last_test_status, last_test_at, last_test_error,
                              created_by, updated_by, created_at, updated_at
                    """,
                    (
                        name,
                        description,
                        status,
                        psycopg2.extras.Json(capabilities) if capabilities is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(capabilities) if capabilities is not None else psycopg2.extras.Json(None),
                        updated_by,
                        last_test_status,
                        last_test_error,
                        touch_last_test_at,
                        data_source_id,
                        company_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 data_sources 失败 (id={data_source_id}, company_id={company_id}): {e}")
        return None


def get_data_source_by_id(data_source_id: str, company_id: str | None = None) -> dict | None:
    """按 id 查询数据源。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if company_id:
                    cur.execute(
                        """
                        SELECT id, company_id, source_kind, domain_type, execution_mode,
                               provider_code, source_code, name, description, status,
                               capabilities, last_test_status, last_test_at, last_test_error,
                               created_by, updated_by, created_at, updated_at
                        FROM data_sources
                        WHERE id = %s AND company_id = %s
                        LIMIT 1
                        """,
                        (data_source_id, company_id),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, company_id, source_kind, domain_type, execution_mode,
                               provider_code, source_code, name, description, status,
                               capabilities, last_test_status, last_test_at, last_test_error,
                               created_by, updated_by, created_at, updated_at
                        FROM data_sources
                        WHERE id = %s
                        LIMIT 1
                        """,
                        (data_source_id,),
                    )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"查询 data_sources 失败 (id={data_source_id}, company_id={company_id}): {e}")
        return None


def get_data_source_by_code(company_id: str, source_code: str) -> dict | None:
    """按 source_code 查询数据源。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, source_kind, domain_type, execution_mode,
                           provider_code, source_code, name, description, status,
                           capabilities, last_test_status, last_test_at, last_test_error,
                           created_by, updated_by, created_at, updated_at
                    FROM data_sources
                    WHERE company_id = %s
                      AND source_code = %s
                    LIMIT 1
                    """,
                    (company_id, source_code),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"按 source_code 查询 data_sources 失败 (company_id={company_id}, source_code={source_code}): {e}")
        return None


def list_data_sources(
    *,
    company_id: str,
    source_kind: str | None = None,
    domain_type: str | None = None,
    status: str | None = None,
) -> list[dict]:
    """列出数据源。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT id, company_id, source_kind, domain_type, execution_mode,
                           provider_code, source_code, name, description, status,
                           capabilities, last_test_status, last_test_at, last_test_error,
                           created_by, updated_by, created_at, updated_at
                    FROM data_sources
                    WHERE company_id = %s
                """
                params: list[Any] = [company_id]
                if source_kind:
                    sql += " AND source_kind = %s"
                    params.append(source_kind)
                if domain_type:
                    sql += " AND domain_type = %s"
                    params.append(domain_type)
                if status:
                    sql += " AND status = %s"
                    params.append(status)
                sql += " ORDER BY updated_at DESC, created_at DESC"
                cur.execute(sql, tuple(params))
                return [_normalize_record(dict(row)) for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"查询 data_sources 列表失败 (company_id={company_id}): {e}")
        return []


def create_data_source_credential(
    *,
    company_id: str,
    data_source_id: str,
    credential_payload: dict[str, Any],
    credential_type: str = "primary",
    credential_mask: dict[str, Any] | None = None,
    status: str = "active",
    created_by: str | None = None,
) -> dict | None:
    """创建新的数据源凭证，并将历史 current 记录置为 false。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE data_source_credentials
                    SET is_current = false,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE data_source_id = %s
                      AND credential_type = %s
                      AND is_current = true
                    """,
                    (data_source_id, credential_type),
                )
                cur.execute(
                    """
                    INSERT INTO data_source_credentials (
                        company_id, data_source_id, credential_type, encrypted_payload,
                        credential_mask, version, is_current, status, last_rotated_at, created_by
                    )
                    VALUES (
                        %s, %s, %s, %s, %s::jsonb,
                        COALESCE(
                            (SELECT MAX(version) + 1
                             FROM data_source_credentials
                             WHERE data_source_id = %s AND credential_type = %s),
                            1
                        ),
                        true, %s, CURRENT_TIMESTAMP, %s
                    )
                    RETURNING id, company_id, data_source_id, credential_type, credential_mask,
                              version, is_current, status, last_rotated_at, created_by,
                              created_at, updated_at
                    """,
                    (
                        company_id,
                        data_source_id,
                        credential_type,
                        _seal_json_payload(credential_payload),
                        psycopg2.extras.Json(credential_mask or {}),
                        data_source_id,
                        credential_type,
                        status,
                        created_by,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"创建 data_source_credentials 失败 (source_id={data_source_id}, type={credential_type}): {e}")
        return None


def get_current_data_source_credential(
    *,
    company_id: str,
    data_source_id: str,
    credential_type: str = "primary",
    include_secret: bool = False,
) -> dict | None:
    """查询当前生效凭证。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, data_source_id, credential_type, encrypted_payload,
                           credential_mask, version, is_current, status, last_rotated_at,
                           created_by, created_at, updated_at
                    FROM data_source_credentials
                    WHERE company_id = %s
                      AND data_source_id = %s
                      AND credential_type = %s
                      AND is_current = true
                    LIMIT 1
                    """,
                    (company_id, data_source_id, credential_type),
                )
                row = cur.fetchone()
                if not row:
                    return None
                result = _normalize_record(dict(row))
                if include_secret:
                    result["credential_payload"] = _open_json_payload(result.get("encrypted_payload") or "")
                result["encrypted_payload"] = ""
                return result
    except Exception as e:
        logger.error(f"查询 data_source_credentials 失败 (source_id={data_source_id}, type={credential_type}): {e}")
        return None


def upsert_data_source_config(
    *,
    company_id: str,
    data_source_id: str,
    config_type: str,
    config: dict[str, Any],
    created_by: str | None = None,
) -> dict | None:
    """写入数据源当前配置版本。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE data_source_configs
                    SET is_current = false,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE data_source_id = %s
                      AND config_type = %s
                      AND is_current = true
                    """,
                    (data_source_id, config_type),
                )
                cur.execute(
                    """
                    INSERT INTO data_source_configs (
                        company_id, data_source_id, config_type, version, is_current, config, created_by
                    )
                    VALUES (
                        %s, %s, %s,
                        COALESCE(
                            (SELECT MAX(version) + 1
                             FROM data_source_configs
                             WHERE data_source_id = %s AND config_type = %s),
                            1
                        ),
                        true, %s::jsonb, %s
                    )
                    RETURNING id, company_id, data_source_id, config_type, version,
                              is_current, config, created_by, created_at, updated_at
                    """,
                    (
                        company_id,
                        data_source_id,
                        config_type,
                        data_source_id,
                        config_type,
                        psycopg2.extras.Json(config or {}),
                        created_by,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"写入 data_source_configs 失败 (source_id={data_source_id}, type={config_type}): {e}")
        return None


def get_current_data_source_config(
    *,
    company_id: str,
    data_source_id: str,
    config_type: str,
) -> dict | None:
    """读取当前配置。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, data_source_id, config_type, version,
                           is_current, config, created_by, created_at, updated_at
                    FROM data_source_configs
                    WHERE company_id = %s
                      AND data_source_id = %s
                      AND config_type = %s
                      AND is_current = true
                    LIMIT 1
                    """,
                    (company_id, data_source_id, config_type),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"查询 data_source_configs 失败 (source_id={data_source_id}, type={config_type}): {e}")
        return None


def list_current_data_source_configs(
    *,
    company_id: str,
    data_source_id: str,
) -> list[dict]:
    """列出当前所有配置分组。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, data_source_id, config_type, version,
                           is_current, config, created_by, created_at, updated_at
                    FROM data_source_configs
                    WHERE company_id = %s
                      AND data_source_id = %s
                      AND is_current = true
                    ORDER BY config_type ASC
                    """,
                    (company_id, data_source_id),
                )
                return [_normalize_record(dict(row)) for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"查询 data_source_configs 列表失败 (source_id={data_source_id}): {e}")
        return []


def create_sync_job(
    *,
    company_id: str,
    data_source_id: str,
    idempotency_key: str,
    job_type: str = "sync",
    trigger_type: str = "manual",
    resource_scope: dict[str, Any] | None = None,
    requested_window_start: str | None = None,
    requested_window_end: str | None = None,
    requested_cursor: str = "",
    requested_by: str | None = None,
    run_context: dict[str, Any] | None = None,
) -> dict | None:
    """创建同步任务；如果幂等键已存在则直接返回已有任务。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO sync_jobs (
                        company_id, data_source_id, job_type, trigger_type, status,
                        idempotency_key, resource_scope, requested_window_start,
                        requested_window_end, requested_cursor, requested_by, run_context
                    ) VALUES (%s, %s, %s, %s, 'pending', %s, %s::jsonb, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (company_id, idempotency_key)
                    DO UPDATE SET updated_at = CURRENT_TIMESTAMP
                    RETURNING id, company_id, data_source_id, job_type, trigger_type, status,
                              idempotency_key, resource_scope, requested_window_start,
                              requested_window_end, requested_cursor, active_attempt_no,
                              requested_by, run_context, error_summary, started_at, finished_at,
                              created_at, updated_at
                    """,
                    (
                        company_id,
                        data_source_id,
                        job_type,
                        trigger_type,
                        idempotency_key,
                        psycopg2.extras.Json(resource_scope or {}),
                        requested_window_start,
                        requested_window_end,
                        requested_cursor,
                        requested_by,
                        psycopg2.extras.Json(run_context or {}),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"创建 sync_jobs 失败 (source_id={data_source_id}, key={idempotency_key}): {e}")
        return None


def get_sync_job(
    *,
    sync_job_id: str,
    company_id: str | None = None,
) -> dict | None:
    """按 id 查询同步任务。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if company_id:
                    cur.execute(
                        """
                        SELECT id, company_id, data_source_id, job_type, trigger_type, status,
                               idempotency_key, resource_scope, requested_window_start,
                               requested_window_end, requested_cursor, active_attempt_no,
                               requested_by, run_context, error_summary, started_at, finished_at,
                               created_at, updated_at
                        FROM sync_jobs
                        WHERE id = %s AND company_id = %s
                        LIMIT 1
                        """,
                        (sync_job_id, company_id),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, company_id, data_source_id, job_type, trigger_type, status,
                               idempotency_key, resource_scope, requested_window_start,
                               requested_window_end, requested_cursor, active_attempt_no,
                               requested_by, run_context, error_summary, started_at, finished_at,
                               created_at, updated_at
                        FROM sync_jobs
                        WHERE id = %s
                        LIMIT 1
                        """,
                        (sync_job_id,),
                    )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"查询 sync_jobs 失败 (id={sync_job_id}, company_id={company_id}): {e}")
        return None


def list_sync_jobs(
    *,
    company_id: str,
    data_source_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """列出同步任务。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT id, company_id, data_source_id, job_type, trigger_type, status,
                           idempotency_key, resource_scope, requested_window_start,
                           requested_window_end, requested_cursor, active_attempt_no,
                           requested_by, run_context, error_summary, started_at, finished_at,
                           created_at, updated_at
                    FROM sync_jobs
                    WHERE company_id = %s
                """
                params: list[Any] = [company_id]
                if data_source_id:
                    sql += " AND data_source_id = %s"
                    params.append(data_source_id)
                if status:
                    sql += " AND status = %s"
                    params.append(status)
                sql += " ORDER BY created_at DESC LIMIT %s"
                params.append(limit)
                cur.execute(sql, tuple(params))
                return [_normalize_record(dict(row)) for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"查询 sync_jobs 列表失败 (company_id={company_id}, source_id={data_source_id}): {e}")
        return []


def update_sync_job_status(
    *,
    sync_job_id: str,
    status: str,
    error_summary: str | None = None,
    active_attempt_no: int | None = None,
    mark_started: bool = False,
    mark_finished: bool = False,
) -> dict | None:
    """更新同步任务状态。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE sync_jobs
                    SET status = %s,
                        error_summary = COALESCE(%s, error_summary),
                        active_attempt_no = COALESCE(%s, active_attempt_no),
                        started_at = CASE WHEN %s THEN COALESCE(started_at, CURRENT_TIMESTAMP) ELSE started_at END,
                        finished_at = CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE finished_at END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING id, company_id, data_source_id, job_type, trigger_type, status,
                              idempotency_key, resource_scope, requested_window_start,
                              requested_window_end, requested_cursor, active_attempt_no,
                              requested_by, run_context, error_summary, started_at, finished_at,
                              created_at, updated_at
                    """,
                    (
                        status,
                        error_summary,
                        active_attempt_no,
                        mark_started,
                        mark_finished,
                        sync_job_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 sync_jobs 状态失败 (id={sync_job_id}, status={status}): {e}")
        return None


def create_sync_job_attempt(
    *,
    company_id: str,
    sync_job_id: str,
    attempt_no: int,
    request_payload: dict[str, Any] | None = None,
) -> dict | None:
    """创建同步尝试。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO sync_job_attempts (
                        company_id, sync_job_id, attempt_no, status, request_payload
                    ) VALUES (%s, %s, %s, 'pending', %s::jsonb)
                    RETURNING id, company_id, sync_job_id, attempt_no, status,
                              request_payload, runtime_summary, error_detail,
                              started_at, finished_at, created_at, updated_at
                    """,
                    (
                        company_id,
                        sync_job_id,
                        attempt_no,
                        psycopg2.extras.Json(request_payload or {}),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"创建 sync_job_attempts 失败 (job_id={sync_job_id}, attempt={attempt_no}): {e}")
        return None


def list_sync_job_attempts(sync_job_id: str) -> list[dict]:
    """列出同步任务的尝试记录。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, sync_job_id, attempt_no, status,
                           request_payload, runtime_summary, error_detail,
                           started_at, finished_at, created_at, updated_at
                    FROM sync_job_attempts
                    WHERE sync_job_id = %s
                    ORDER BY attempt_no DESC
                    """,
                    (sync_job_id,),
                )
                return [_normalize_record(dict(row)) for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"查询 sync_job_attempts 失败 (job_id={sync_job_id}): {e}")
        return []


def update_sync_job_attempt_status(
    *,
    sync_attempt_id: str,
    status: str,
    runtime_summary: dict[str, Any] | None = None,
    error_detail: str | None = None,
    mark_started: bool = False,
    mark_finished: bool = False,
) -> dict | None:
    """更新同步尝试状态。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE sync_job_attempts
                    SET status = %s,
                        runtime_summary = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN runtime_summary
                            ELSE %s::jsonb
                        END,
                        error_detail = COALESCE(%s, error_detail),
                        started_at = CASE WHEN %s THEN COALESCE(started_at, CURRENT_TIMESTAMP) ELSE started_at END,
                        finished_at = CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE finished_at END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING id, company_id, sync_job_id, attempt_no, status,
                              request_payload, runtime_summary, error_detail,
                              started_at, finished_at, created_at, updated_at
                    """,
                    (
                        status,
                        psycopg2.extras.Json(runtime_summary) if runtime_summary is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(runtime_summary) if runtime_summary is not None else psycopg2.extras.Json(None),
                        error_detail,
                        mark_started,
                        mark_finished,
                        sync_attempt_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 sync_job_attempts 状态失败 (id={sync_attempt_id}, status={status}): {e}")
        return None


def upsert_sync_checkpoint(
    *,
    company_id: str,
    data_source_id: str,
    resource_type: str = "default",
    checkpoint_key: str = "default",
    cursor_value: str = "",
    watermark_at: str | None = None,
    last_successful_job_id: str | None = None,
    last_published_snapshot_id: str | None = None,
    status: str = "success",
    last_error: str = "",
) -> dict | None:
    """写入同步 checkpoint；只建议在成功发布 snapshot 后推进。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO sync_checkpoints (
                        company_id, data_source_id, resource_type, checkpoint_key,
                        cursor_value, watermark_at, last_successful_job_id,
                        last_published_snapshot_id, status, last_error
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (data_source_id, resource_type, checkpoint_key)
                    DO UPDATE SET
                        cursor_value = EXCLUDED.cursor_value,
                        watermark_at = EXCLUDED.watermark_at,
                        last_successful_job_id = EXCLUDED.last_successful_job_id,
                        last_published_snapshot_id = EXCLUDED.last_published_snapshot_id,
                        status = EXCLUDED.status,
                        last_error = EXCLUDED.last_error,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id, company_id, data_source_id, resource_type, checkpoint_key,
                              cursor_value, watermark_at, last_successful_job_id,
                              last_published_snapshot_id, status, last_error,
                              created_at, updated_at
                    """,
                    (
                        company_id,
                        data_source_id,
                        resource_type,
                        checkpoint_key,
                        cursor_value,
                        watermark_at,
                        last_successful_job_id,
                        last_published_snapshot_id,
                        status,
                        last_error,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"写入 sync_checkpoints 失败 (source_id={data_source_id}, resource={resource_type}): {e}")
        return None


def get_sync_checkpoint(
    *,
    data_source_id: str,
    resource_type: str = "default",
    checkpoint_key: str = "default",
) -> dict | None:
    """读取 checkpoint。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, data_source_id, resource_type, checkpoint_key,
                           cursor_value, watermark_at, last_successful_job_id,
                           last_published_snapshot_id, status, last_error,
                           created_at, updated_at
                    FROM sync_checkpoints
                    WHERE data_source_id = %s
                      AND resource_type = %s
                      AND checkpoint_key = %s
                    LIMIT 1
                    """,
                    (data_source_id, resource_type, checkpoint_key),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"查询 sync_checkpoints 失败 (source_id={data_source_id}, resource={resource_type}): {e}")
        return None


def create_raw_ingestion_batch(
    *,
    company_id: str,
    data_source_id: str,
    sync_job_id: str,
    sync_attempt_id: str,
    resource_type: str = "default",
    window_start: str | None = None,
    window_end: str | None = None,
    cursor_before: str = "",
    cursor_after: str = "",
    batch_hash: str = "",
    record_count: int = 0,
    status: str = "ingested",
    metadata: dict[str, Any] | None = None,
) -> dict | None:
    """创建原始入湖批次。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO raw_ingestion_batches (
                        company_id, data_source_id, sync_job_id, sync_attempt_id, resource_type,
                        window_start, window_end, cursor_before, cursor_after,
                        batch_hash, record_count, status, metadata
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    RETURNING id, company_id, data_source_id, sync_job_id, sync_attempt_id,
                              resource_type, window_start, window_end, cursor_before,
                              cursor_after, batch_hash, record_count, status, metadata,
                              created_at, updated_at
                    """,
                    (
                        company_id,
                        data_source_id,
                        sync_job_id,
                        sync_attempt_id,
                        resource_type,
                        window_start,
                        window_end,
                        cursor_before,
                        cursor_after,
                        batch_hash,
                        record_count,
                        status,
                        psycopg2.extras.Json(metadata or {}),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"创建 raw_ingestion_batches 失败 (source_id={data_source_id}, job_id={sync_job_id}): {e}")
        return None


def insert_raw_ingestion_records(
    *,
    company_id: str,
    data_source_id: str,
    raw_batch_id: str,
    records: list[dict[str, Any]],
) -> int:
    """批量写入原始记录；同一 batch 内按 record_hash 去重。"""
    if not records:
        return 0
    conn_manager = get_conn()
    try:
        values: list[tuple[Any, ...]] = []
        for item in records:
            values.append(
                (
                    company_id,
                    data_source_id,
                    raw_batch_id,
                    str(item.get("source_record_key") or ""),
                    str(item.get("business_key") or ""),
                    str(item.get("record_hash") or ""),
                    psycopg2.extras.Json(item.get("payload") or {}),
                    item.get("source_event_at"),
                    bool(item.get("is_deleted") or False),
                )
            )
        with conn_manager as conn:
            with conn.cursor() as cur:
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO raw_ingestion_records (
                        company_id, data_source_id, raw_batch_id,
                        source_record_key, business_key, record_hash,
                        payload, source_event_at, is_deleted
                    ) VALUES %s
                    ON CONFLICT (raw_batch_id, record_hash) DO NOTHING
                    """,
                    values,
                    page_size=200,
                )
                inserted = cur.rowcount
                conn.commit()
                return inserted if inserted is not None and inserted >= 0 else 0
    except Exception as e:
        logger.error(f"写入 raw_ingestion_records 失败 (batch_id={raw_batch_id}): {e}")
        return 0


def create_dataset_snapshot(
    *,
    company_id: str,
    data_source_id: str,
    sync_job_id: str,
    sync_attempt_id: str,
    dataset_code: str,
    resource_type: str = "default",
    snapshot_stage: str = "candidate",
    validation_status: str = "pending",
    record_count: int = 0,
    checksum: str = "",
    previous_snapshot_id: str | None = None,
    window_start: str | None = None,
    window_end: str | None = None,
    snapshot_metadata: dict[str, Any] | None = None,
) -> dict | None:
    """创建数据集快照，默认先生成 candidate。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO dataset_snapshots (
                        company_id, data_source_id, sync_job_id, sync_attempt_id,
                        dataset_code, resource_type, snapshot_stage, is_active,
                        validation_status, record_count, checksum, previous_snapshot_id,
                        window_start, window_end, snapshot_metadata
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s, false,
                        %s, %s, %s, %s,
                        %s, %s, %s::jsonb
                    )
                    RETURNING id, company_id, data_source_id, sync_job_id, sync_attempt_id,
                              dataset_code, resource_type, snapshot_stage, is_active,
                              validation_status, record_count, checksum, previous_snapshot_id,
                              superseded_by_snapshot_id, window_start, window_end,
                              snapshot_metadata, published_at, created_at, updated_at
                    """,
                    (
                        company_id,
                        data_source_id,
                        sync_job_id,
                        sync_attempt_id,
                        dataset_code,
                        resource_type,
                        snapshot_stage,
                        validation_status,
                        record_count,
                        checksum,
                        previous_snapshot_id,
                        window_start,
                        window_end,
                        psycopg2.extras.Json(snapshot_metadata or {}),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"创建 dataset_snapshots 失败 (source_id={data_source_id}, dataset={dataset_code}): {e}")
        return None


def publish_dataset_snapshot(
    *,
    snapshot_id: str,
    company_id: str,
) -> dict | None:
    """发布快照：先退役当前 active published，再将新 snapshot 标记为 active published。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, data_source_id, dataset_code, resource_type
                    FROM dataset_snapshots
                    WHERE id = %s AND company_id = %s
                    LIMIT 1
                    """,
                    (snapshot_id, company_id),
                )
                target = cur.fetchone()
                if not target:
                    conn.rollback()
                    return None

                cur.execute(
                    """
                    UPDATE dataset_snapshots
                    SET is_active = false,
                        snapshot_stage = 'superseded',
                        superseded_by_snapshot_id = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE company_id = %s
                      AND data_source_id = %s
                      AND dataset_code = %s
                      AND resource_type = %s
                      AND is_active = true
                      AND id <> %s
                    """,
                    (
                        snapshot_id,
                        company_id,
                        target["data_source_id"],
                        target["dataset_code"],
                        target["resource_type"],
                        snapshot_id,
                    ),
                )

                cur.execute(
                    """
                    UPDATE dataset_snapshots
                    SET snapshot_stage = 'published',
                        is_active = true,
                        validation_status = CASE
                            WHEN validation_status = 'pending' THEN 'passed'
                            ELSE validation_status
                        END,
                        published_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING id, company_id, data_source_id, sync_job_id, sync_attempt_id,
                              dataset_code, resource_type, snapshot_stage, is_active,
                              validation_status, record_count, checksum, previous_snapshot_id,
                              superseded_by_snapshot_id, window_start, window_end,
                              snapshot_metadata, published_at, created_at, updated_at
                    """,
                    (snapshot_id,),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"发布 dataset_snapshots 失败 (id={snapshot_id}, company_id={company_id}): {e}")
        return None


def get_published_dataset_snapshot(
    *,
    company_id: str,
    data_source_id: str,
    dataset_code: str,
    resource_type: str = "default",
) -> dict | None:
    """获取当前已发布的健康快照。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, data_source_id, sync_job_id, sync_attempt_id,
                           dataset_code, resource_type, snapshot_stage, is_active,
                           validation_status, record_count, checksum, previous_snapshot_id,
                           superseded_by_snapshot_id, window_start, window_end,
                           snapshot_metadata, published_at, created_at, updated_at
                    FROM dataset_snapshots
                    WHERE company_id = %s
                      AND data_source_id = %s
                      AND dataset_code = %s
                      AND resource_type = %s
                      AND is_active = true
                      AND snapshot_stage = 'published'
                    LIMIT 1
                    """,
                    (company_id, data_source_id, dataset_code, resource_type),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"查询 published dataset_snapshots 失败 (source_id={data_source_id}, dataset={dataset_code}): {e}")
        return None


def list_dataset_snapshots(
    *,
    company_id: str,
    data_source_id: str,
    dataset_code: str | None = None,
    resource_type: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """列出快照。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT id, company_id, data_source_id, sync_job_id, sync_attempt_id,
                           dataset_code, resource_type, snapshot_stage, is_active,
                           validation_status, record_count, checksum, previous_snapshot_id,
                           superseded_by_snapshot_id, window_start, window_end,
                           snapshot_metadata, published_at, created_at, updated_at
                    FROM dataset_snapshots
                    WHERE company_id = %s
                      AND data_source_id = %s
                """
                params: list[Any] = [company_id, data_source_id]
                if dataset_code:
                    sql += " AND dataset_code = %s"
                    params.append(dataset_code)
                if resource_type:
                    sql += " AND resource_type = %s"
                    params.append(resource_type)
                sql += " ORDER BY created_at DESC LIMIT %s"
                params.append(limit)
                cur.execute(sql, tuple(params))
                return [_normalize_record(dict(row)) for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"查询 dataset_snapshots 列表失败 (source_id={data_source_id}, dataset={dataset_code}): {e}")
        return []


def insert_dataset_snapshot_items(
    *,
    company_id: str,
    snapshot_id: str,
    items: list[dict[str, Any]],
) -> int:
    """批量写入标准化后的快照数据。"""
    if not items:
        return 0
    conn_manager = get_conn()
    try:
        values: list[tuple[Any, ...]] = []
        for item in items:
            values.append(
                (
                    company_id,
                    snapshot_id,
                    str(item.get("source_record_key") or ""),
                    str(item.get("business_key") or ""),
                    str(item.get("item_hash") or ""),
                    psycopg2.extras.Json(item.get("record_data") or {}),
                )
            )
        with conn_manager as conn:
            with conn.cursor() as cur:
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO dataset_snapshot_items (
                        company_id, snapshot_id, source_record_key, business_key, item_hash, record_data
                    ) VALUES %s
                    ON CONFLICT (snapshot_id, item_hash) DO NOTHING
                    """,
                    values,
                    page_size=200,
                )
                inserted = cur.rowcount
                conn.commit()
                return inserted if inserted is not None and inserted >= 0 else 0
    except Exception as e:
        logger.error(f"写入 dataset_snapshot_items 失败 (snapshot_id={snapshot_id}): {e}")
        return 0


def upsert_dataset_binding(
    *,
    company_id: str,
    data_source_id: str,
    dataset_code: str,
    consumer_type: str,
    consumer_key: str,
    role_code: str = "source",
    selection_mode: str = "latest_published",
    binding_config: dict[str, Any] | None = None,
    status: str = "active",
) -> dict | None:
    """写入数据集绑定关系。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO dataset_bindings (
                        company_id, data_source_id, dataset_code, consumer_type,
                        consumer_key, role_code, selection_mode, binding_config, status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                    ON CONFLICT (company_id, consumer_type, consumer_key, role_code)
                    DO UPDATE SET
                        data_source_id = EXCLUDED.data_source_id,
                        dataset_code = EXCLUDED.dataset_code,
                        selection_mode = EXCLUDED.selection_mode,
                        binding_config = EXCLUDED.binding_config,
                        status = EXCLUDED.status,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id, company_id, data_source_id, dataset_code, consumer_type,
                              consumer_key, role_code, selection_mode, binding_config,
                              status, created_at, updated_at
                    """,
                    (
                        company_id,
                        data_source_id,
                        dataset_code,
                        consumer_type,
                        consumer_key,
                        role_code,
                        selection_mode,
                        psycopg2.extras.Json(binding_config or {}),
                        status,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"写入 dataset_bindings 失败 (consumer={consumer_type}:{consumer_key}, role={role_code}): {e}")
        return None


def list_dataset_bindings(
    *,
    company_id: str,
    consumer_type: str | None = None,
    consumer_key: str | None = None,
) -> list[dict]:
    """列出数据集绑定。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT id, company_id, data_source_id, dataset_code, consumer_type,
                           consumer_key, role_code, selection_mode, binding_config,
                           status, created_at, updated_at
                    FROM dataset_bindings
                    WHERE company_id = %s
                """
                params: list[Any] = [company_id]
                if consumer_type:
                    sql += " AND consumer_type = %s"
                    params.append(consumer_type)
                if consumer_key:
                    sql += " AND consumer_key = %s"
                    params.append(consumer_key)
                sql += " ORDER BY updated_at DESC"
                cur.execute(sql, tuple(params))
                return [_normalize_record(dict(row)) for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"查询 dataset_bindings 失败 (company_id={company_id}): {e}")
        return []


def create_data_source_event(
    *,
    company_id: str,
    event_type: str,
    data_source_id: str | None = None,
    sync_job_id: str | None = None,
    sync_attempt_id: str | None = None,
    event_level: str = "info",
    event_message: str = "",
    event_payload: dict[str, Any] | None = None,
) -> dict | None:
    """写入数据连接审计事件。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO data_source_events (
                        company_id, data_source_id, sync_job_id, sync_attempt_id,
                        event_type, event_level, event_message, event_payload
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    RETURNING id, company_id, data_source_id, sync_job_id, sync_attempt_id,
                              event_type, event_level, event_message, event_payload, created_at
                    """,
                    (
                        company_id,
                        data_source_id,
                        sync_job_id,
                        sync_attempt_id,
                        event_type,
                        event_level,
                        event_message,
                        psycopg2.extras.Json(event_payload or {}),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"写入 data_source_events 失败 (event_type={event_type}, source_id={data_source_id}): {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# 通用数据连接模型（data_sources / sync_jobs / dataset_snapshots）
# ══════════════════════════════════════════════════════════════════════════════


def upsert_unified_data_source(
    *,
    company_id: str,
    code: str,
    name: str,
    source_kind: str,
    domain_type: str,
    provider_code: str,
    execution_mode: str = "deterministic",
    description: str = "",
    status: str = "active",
    is_enabled: bool = True,
    health_status: str | None = None,
    last_checked_at: str | None = None,
    last_error_message: str | None = None,
    meta: dict | None = None,
) -> dict | None:
    """创建或更新数据源。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO data_sources (
                        company_id, code, name, source_kind, domain_type, provider_code,
                        execution_mode, description, status, is_enabled,
                        health_status, last_checked_at, last_error_message, meta
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        COALESCE(%s, 'unknown'), %s, COALESCE(%s, ''), %s::jsonb
                    )
                    ON CONFLICT (company_id, code)
                    DO UPDATE SET
                        name = EXCLUDED.name,
                        source_kind = EXCLUDED.source_kind,
                        domain_type = EXCLUDED.domain_type,
                        provider_code = EXCLUDED.provider_code,
                        execution_mode = EXCLUDED.execution_mode,
                        description = EXCLUDED.description,
                        status = EXCLUDED.status,
                        is_enabled = EXCLUDED.is_enabled,
                        health_status = COALESCE(EXCLUDED.health_status, data_sources.health_status),
                        last_checked_at = COALESCE(EXCLUDED.last_checked_at, data_sources.last_checked_at),
                        last_error_message = CASE
                            WHEN EXCLUDED.last_error_message IS NULL
                                THEN data_sources.last_error_message
                            ELSE EXCLUDED.last_error_message
                        END,
                        meta = EXCLUDED.meta,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id, company_id, code, name, source_kind, domain_type, provider_code,
                              execution_mode, description, status, is_enabled,
                              health_status, last_checked_at, last_error_message, meta,
                              created_at, updated_at
                    """,
                    (
                        company_id,
                        code,
                        name,
                        source_kind,
                        domain_type,
                        provider_code,
                        execution_mode,
                        description,
                        status,
                        is_enabled,
                        health_status,
                        last_checked_at,
                        last_error_message,
                        psycopg2.extras.Json(meta or {}),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"写入 data_sources 失败 (company_id={company_id}, code={code}): {e}")
        return None


def get_unified_data_source_by_id(*, company_id: str, data_source_id: str) -> dict | None:
    """按 id 查询数据源。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, code, name, source_kind, domain_type, provider_code,
                           execution_mode, description, status, is_enabled,
                           health_status, last_checked_at, last_error_message, meta,
                           created_at, updated_at
                    FROM data_sources
                    WHERE company_id = %s
                      AND id = %s
                    LIMIT 1
                    """,
                    (company_id, data_source_id),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"查询 data_sources 失败 (company_id={company_id}, id={data_source_id}): {e}")
        return None


def list_unified_data_sources(
    *,
    company_id: str,
    source_kind: str | None = None,
    domain_type: str | None = None,
    status: str | None = None,
    include_deleted: bool = False,
) -> list[dict]:
    """查询数据源列表。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT id, company_id, code, name, source_kind, domain_type, provider_code,
                           execution_mode, description, status, is_enabled,
                           health_status, last_checked_at, last_error_message, meta,
                           created_at, updated_at
                    FROM data_sources
                    WHERE company_id = %s
                """
                params: list[Any] = [company_id]
                if source_kind:
                    sql += " AND source_kind = %s"
                    params.append(source_kind)
                if domain_type:
                    sql += " AND domain_type = %s"
                    params.append(domain_type)
                if status:
                    sql += " AND status = %s"
                    params.append(status)
                elif not include_deleted:
                    sql += " AND status <> 'deleted'"
                sql += " ORDER BY updated_at DESC, created_at DESC"
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(
            f"查询 data_sources 列表失败 (company_id={company_id}, source_kind={source_kind}, domain_type={domain_type}, status={status}): {e}"
        )
        return []


def update_unified_data_source_status(
    *,
    data_source_id: str,
    status: str,
    is_enabled: bool | None = None,
) -> dict | None:
    """更新数据源状态。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if is_enabled is None:
                    cur.execute(
                        """
                        UPDATE data_sources
                        SET status = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                        RETURNING id, company_id, code, name, source_kind, domain_type, provider_code,
                                  execution_mode, description, status, is_enabled,
                                  health_status, last_checked_at, last_error_message, meta,
                                  created_at, updated_at
                        """,
                        (status, data_source_id),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE data_sources
                        SET status = %s,
                            is_enabled = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                        RETURNING id, company_id, code, name, source_kind, domain_type, provider_code,
                                  execution_mode, description, status, is_enabled,
                                  health_status, last_checked_at, last_error_message, meta,
                                  created_at, updated_at
                        """,
                        (status, is_enabled, data_source_id),
                    )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 data_sources 状态失败 (id={data_source_id}, status={status}): {e}")
        return None


def update_unified_data_source_health(
    *,
    data_source_id: str,
    health_status: str,
    last_checked_at: str | None = None,
    last_error_message: str = "",
) -> dict | None:
    """更新数据源健康状态。"""
    conn_manager = get_conn()
    checked_at = last_checked_at or datetime.now(timezone.utc).isoformat()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE data_sources
                    SET health_status = %s,
                        last_checked_at = %s,
                        last_error_message = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING id, company_id, code, name, source_kind, domain_type, provider_code,
                              execution_mode, description, status, is_enabled,
                              health_status, last_checked_at, last_error_message, meta,
                              created_at, updated_at
                    """,
                    (health_status, checked_at, last_error_message, data_source_id),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 data_sources 健康状态失败 (id={data_source_id}, health_status={health_status}): {e}")
        return None


def upsert_unified_data_source_dataset(
    *,
    company_id: str,
    data_source_id: str,
    dataset_code: str,
    dataset_name: str,
    resource_key: str = "default",
    dataset_kind: str = "table",
    origin_type: str = "manual",
    extract_config: dict | None = None,
    schema_summary: dict | None = None,
    sync_strategy: dict | None = None,
    status: str = "active",
    is_enabled: bool = True,
    health_status: str = "unknown",
    last_checked_at: str | None = None,
    last_sync_at: str | None = None,
    last_error_message: str = "",
    meta: dict | None = None,
) -> dict | None:
    """创建或更新数据源下的数据集目录项。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO data_source_datasets (
                        company_id, data_source_id, dataset_code, dataset_name,
                        resource_key, dataset_kind, origin_type,
                        extract_config, schema_summary, sync_strategy,
                        status, is_enabled, health_status,
                        last_checked_at, last_sync_at, last_error_message, meta
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s::jsonb, %s::jsonb, %s::jsonb,
                        %s, %s, %s,
                        %s, %s, %s, %s::jsonb
                    )
                    ON CONFLICT (company_id, data_source_id, dataset_code)
                    DO UPDATE SET
                        dataset_name = EXCLUDED.dataset_name,
                        resource_key = EXCLUDED.resource_key,
                        dataset_kind = EXCLUDED.dataset_kind,
                        origin_type = EXCLUDED.origin_type,
                        extract_config = EXCLUDED.extract_config,
                        schema_summary = EXCLUDED.schema_summary,
                        sync_strategy = EXCLUDED.sync_strategy,
                        status = EXCLUDED.status,
                        is_enabled = EXCLUDED.is_enabled,
                        health_status = EXCLUDED.health_status,
                        last_checked_at = EXCLUDED.last_checked_at,
                        last_sync_at = EXCLUDED.last_sync_at,
                        last_error_message = EXCLUDED.last_error_message,
                        meta = EXCLUDED.meta,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id, company_id, data_source_id, dataset_code, dataset_name,
                              resource_key, dataset_kind, origin_type,
                              extract_config, schema_summary, sync_strategy,
                              status, is_enabled, health_status,
                              last_checked_at, last_sync_at, last_error_message, meta,
                              created_at, updated_at
                    """,
                    (
                        company_id,
                        data_source_id,
                        dataset_code,
                        dataset_name,
                        resource_key,
                        dataset_kind,
                        origin_type,
                        psycopg2.extras.Json(extract_config or {}),
                        psycopg2.extras.Json(schema_summary or {}),
                        psycopg2.extras.Json(sync_strategy or {}),
                        status,
                        is_enabled,
                        health_status,
                        last_checked_at,
                        last_sync_at,
                        last_error_message,
                        psycopg2.extras.Json(meta or {}),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"写入 data_source_datasets 失败 (company_id={company_id}, data_source_id={data_source_id}, dataset_code={dataset_code}): {e}"
        )
        return None


def get_unified_data_source_dataset_by_id(
    *,
    company_id: str,
    dataset_id: str,
) -> dict | None:
    """按 id 查询数据集目录项。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, data_source_id, dataset_code, dataset_name,
                           resource_key, dataset_kind, origin_type,
                           extract_config, schema_summary, sync_strategy,
                           status, is_enabled, health_status,
                           last_checked_at, last_sync_at, last_error_message, meta,
                           created_at, updated_at
                    FROM data_source_datasets
                    WHERE company_id = %s
                      AND id = %s
                    LIMIT 1
                    """,
                    (company_id, dataset_id),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"查询 data_source_datasets 失败 (company_id={company_id}, id={dataset_id}): {e}")
        return None


def get_unified_data_source_dataset_by_source_resource(
    *,
    company_id: str,
    data_source_id: str,
    resource_key: str = "default",
    status: str | None = None,
) -> dict | None:
    """按 source + resource_key 查询数据集目录项（最新一条）。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT id, company_id, data_source_id, dataset_code, dataset_name,
                           resource_key, dataset_kind, origin_type,
                           extract_config, schema_summary, sync_strategy,
                           status, is_enabled, health_status,
                           last_checked_at, last_sync_at, last_error_message, meta,
                           created_at, updated_at
                    FROM data_source_datasets
                    WHERE company_id = %s
                      AND data_source_id = %s
                      AND resource_key = %s
                """
                params: list[Any] = [company_id, data_source_id, resource_key]
                if status:
                    sql += " AND status = %s"
                    params.append(status)
                sql += " ORDER BY updated_at DESC, created_at DESC LIMIT 1"
                cur.execute(sql, tuple(params))
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"查询 data_source_datasets 失败 (company_id={company_id}, data_source_id={data_source_id}, resource_key={resource_key}, status={status}): {e}"
        )
        return None


def list_unified_data_source_datasets(
    *,
    company_id: str,
    data_source_id: str | None = None,
    status: str | None = None,
    include_deleted: bool = False,
    limit: int = 500,
) -> list[dict]:
    """查询数据源下的数据集目录列表。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT id, company_id, data_source_id, dataset_code, dataset_name,
                           resource_key, dataset_kind, origin_type,
                           extract_config, schema_summary, sync_strategy,
                           status, is_enabled, health_status,
                           last_checked_at, last_sync_at, last_error_message, meta,
                           created_at, updated_at
                    FROM data_source_datasets
                    WHERE company_id = %s
                """
                params: list[Any] = [company_id]
                if data_source_id:
                    sql += " AND data_source_id = %s"
                    params.append(data_source_id)
                if status:
                    sql += " AND status = %s"
                    params.append(status)
                elif not include_deleted:
                    sql += " AND status <> 'deleted'"
                sql += " ORDER BY updated_at DESC, created_at DESC LIMIT %s"
                params.append(max(1, min(limit, 2000)))
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(
            f"查询 data_source_datasets 列表失败 (company_id={company_id}, data_source_id={data_source_id}, status={status}): {e}"
        )
        return []


def update_unified_data_source_dataset_status(
    *,
    dataset_id: str,
    status: str,
    is_enabled: bool | None = None,
) -> dict | None:
    """更新数据集目录状态。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if is_enabled is None:
                    cur.execute(
                        """
                        UPDATE data_source_datasets
                        SET status = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                        RETURNING id, company_id, data_source_id, dataset_code, dataset_name,
                                  resource_key, dataset_kind, origin_type,
                                  extract_config, schema_summary, sync_strategy,
                                  status, is_enabled, health_status,
                                  last_checked_at, last_sync_at, last_error_message, meta,
                                  created_at, updated_at
                        """,
                        (status, dataset_id),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE data_source_datasets
                        SET status = %s,
                            is_enabled = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                        RETURNING id, company_id, data_source_id, dataset_code, dataset_name,
                                  resource_key, dataset_kind, origin_type,
                                  extract_config, schema_summary, sync_strategy,
                                  status, is_enabled, health_status,
                                  last_checked_at, last_sync_at, last_error_message, meta,
                                  created_at, updated_at
                        """,
                        (status, is_enabled, dataset_id),
                    )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 data_source_datasets 状态失败 (id={dataset_id}, status={status}): {e}")
        return None


def update_unified_data_source_dataset_health(
    *,
    dataset_id: str,
    health_status: str,
    last_checked_at: str | None = None,
    last_sync_at: str | None = None,
    last_error_message: str = "",
) -> dict | None:
    """更新数据集目录健康状态。"""
    conn_manager = get_conn()
    checked_at = last_checked_at or datetime.now(timezone.utc).isoformat()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE data_source_datasets
                    SET health_status = %s,
                        last_checked_at = %s,
                        last_sync_at = COALESCE(%s, last_sync_at),
                        last_error_message = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING id, company_id, data_source_id, dataset_code, dataset_name,
                              resource_key, dataset_kind, origin_type,
                              extract_config, schema_summary, sync_strategy,
                              status, is_enabled, health_status,
                              last_checked_at, last_sync_at, last_error_message, meta,
                              created_at, updated_at
                    """,
                    (health_status, checked_at, last_sync_at, last_error_message, dataset_id),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"更新 data_source_datasets 健康状态失败 (id={dataset_id}, health_status={health_status}): {e}"
        )
        return None


def list_unified_rule_binding_requirements(
    *,
    company_id: str,
    binding_scope: str,
    binding_code: str,
    status: str | None = "active",
) -> list[dict]:
    """查询规则绑定及其 source/dataset 健康上下文（preflight helper）。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT b.id, b.company_id, b.binding_scope, b.binding_code, b.binding_name,
                           b.data_source_id, b.resource_key, b.role_code, b.is_required, b.priority,
                           b.filter_config, b.mapping_config, b.status AS binding_status,
                           b.created_at AS binding_created_at, b.updated_at AS binding_updated_at,
                           s.name AS source_name, s.source_kind, s.provider_code,
                           s.status AS source_status, s.is_enabled AS source_enabled,
                           s.health_status AS source_health_status, s.last_checked_at AS source_last_checked_at,
                           s.last_error_message AS source_last_error_message,
                           d.id AS dataset_id, d.dataset_code, d.dataset_name, d.dataset_kind, d.origin_type,
                           d.status AS dataset_status, d.is_enabled AS dataset_enabled,
                           d.health_status AS dataset_health_status, d.last_checked_at AS dataset_last_checked_at,
                           d.last_sync_at AS dataset_last_sync_at, d.last_error_message AS dataset_last_error_message
                    FROM dataset_bindings b
                    LEFT JOIN data_sources s
                      ON s.id = b.data_source_id
                    LEFT JOIN LATERAL (
                        SELECT id, dataset_code, dataset_name, dataset_kind, origin_type,
                               status, is_enabled, health_status, last_checked_at, last_sync_at, last_error_message
                        FROM data_source_datasets d0
                        WHERE d0.data_source_id = b.data_source_id
                          AND d0.resource_key = b.resource_key
                          AND d0.status <> 'deleted'
                        ORDER BY d0.updated_at DESC, d0.created_at DESC
                        LIMIT 1
                    ) d ON true
                    WHERE b.company_id = %s
                      AND b.binding_scope = %s
                      AND b.binding_code = %s
                """
                params: list[Any] = [company_id, binding_scope, binding_code]
                if status:
                    sql += " AND b.status = %s"
                    params.append(status)
                sql += " ORDER BY b.priority ASC, b.updated_at DESC"
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(
            f"查询规则绑定 preflight 上下文失败 (company_id={company_id}, binding_scope={binding_scope}, binding_code={binding_code}, status={status}): {e}"
        )
        return []


def evaluate_unified_rule_binding_preflight(
    *,
    company_id: str,
    binding_scope: str,
    binding_code: str,
    stale_after_minutes: int = 24 * 60,
) -> dict[str, Any]:
    """评估规则绑定可用性（preflight helper）。"""
    bindings = list_unified_rule_binding_requirements(
        company_id=company_id,
        binding_scope=binding_scope,
        binding_code=binding_code,
        status="active",
    )
    issues: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for item in bindings:
        role_code = str(item.get("role_code") or "")
        source_id = str(item.get("data_source_id") or "")
        resource_key = str(item.get("resource_key") or "default")
        is_required = bool(item.get("is_required", True))

        source_status = str(item.get("source_status") or "")
        source_enabled = bool(item.get("source_enabled", False))
        source_health_status = str(item.get("source_health_status") or "unknown")
        source_name = str(item.get("source_name") or source_id or "未知数据源")

        dataset_id = str(item.get("dataset_id") or "")
        dataset_name = str(item.get("dataset_name") or item.get("dataset_code") or resource_key)
        dataset_status = str(item.get("dataset_status") or "")
        dataset_enabled = bool(item.get("dataset_enabled", False))
        dataset_health_status = str(item.get("dataset_health_status") or "unknown")

        def _append_issue(code: str, level: str, message: str) -> None:
            issues.append(
                {
                    "code": code,
                    "level": level,
                    "message": message,
                    "binding_scope": binding_scope,
                    "binding_code": binding_code,
                    "role_code": role_code,
                    "is_required": is_required,
                    "data_source_id": source_id,
                    "resource_key": resource_key,
                    "dataset_id": dataset_id,
                }
            )

        if not source_id:
            _append_issue("source_missing", "error", f"角色 {role_code} 未绑定数据源")
            continue

        if source_status != "active" or not source_enabled:
            _append_issue("source_disabled", "error", f"{source_name} 未启用或状态非 active")
            continue

        if source_health_status in {"error", "auth_expired", "disabled"}:
            _append_issue("source_unhealthy", "error", f"{source_name} 当前健康状态为 {source_health_status}")
            continue

        if not dataset_id:
            _append_issue("dataset_missing", "error", f"{source_name} 的资源 {resource_key} 未配置数据集目录")
            continue

        if dataset_status != "active" or not dataset_enabled:
            _append_issue("dataset_disabled", "error", f"数据集 {dataset_name} 未启用或状态非 active")
            continue

        if dataset_health_status in {"error", "auth_expired", "disabled"}:
            _append_issue("dataset_unhealthy", "error", f"数据集 {dataset_name} 当前健康状态为 {dataset_health_status}")
            continue

        last_sync_at = item.get("dataset_last_sync_at")
        if isinstance(last_sync_at, str) and last_sync_at:
            try:
                last_sync_dt = datetime.fromisoformat(last_sync_at.replace("Z", "+00:00"))
                stale_threshold = now - timedelta(minutes=max(1, stale_after_minutes))
                if last_sync_dt.tzinfo is None:
                    last_sync_dt = last_sync_dt.replace(tzinfo=timezone.utc)
                if last_sync_dt < stale_threshold:
                    _append_issue(
                        "dataset_stale",
                        "warn",
                        f"数据集 {dataset_name} 最近同步时间 {last_sync_at}，已超过 {stale_after_minutes} 分钟",
                    )
            except Exception:
                _append_issue("dataset_sync_time_invalid", "warn", f"数据集 {dataset_name} 最近同步时间格式无效")

    blocking_issues = [item for item in issues if item.get("level") == "error"]
    return {
        "ready": len(blocking_issues) == 0,
        "issue_count": len(issues),
        "blocking_issue_count": len(blocking_issues),
        "issues": issues,
        "requirements": bindings,
    }


def upsert_unified_data_source_credentials(
    *,
    company_id: str,
    data_source_id: str,
    credential_type: str = "default",
    credential_payload: dict | None = None,
    extra: dict | None = None,
) -> dict | None:
    """创建或更新数据源凭证（密封存储）。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO data_source_credentials (
                        company_id, data_source_id, credential_type,
                        secret_payload, secret_version, secret_updated_at, extra
                    ) VALUES (
                        %s, %s, %s,
                        %s, 1, CURRENT_TIMESTAMP, %s::jsonb
                    )
                    ON CONFLICT (data_source_id, credential_type)
                    DO UPDATE SET
                        secret_payload = EXCLUDED.secret_payload,
                        secret_version = data_source_credentials.secret_version + 1,
                        secret_updated_at = CURRENT_TIMESTAMP,
                        extra = EXCLUDED.extra,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id, company_id, data_source_id, credential_type,
                              secret_payload, secret_version, secret_updated_at, extra,
                              created_at, updated_at
                    """,
                    (
                        company_id,
                        data_source_id,
                        credential_type,
                        _seal_json_payload(credential_payload),
                        psycopg2.extras.Json(extra or {}),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                if not row:
                    return None
                result = _normalize_record(dict(row))
                result["credential_payload"] = {}
                return result
    except Exception as e:
        logger.error(
            f"写入 data_source_credentials 失败 (company_id={company_id}, data_source_id={data_source_id}, credential_type={credential_type}): {e}"
        )
        return None


def get_unified_data_source_credentials(
    *,
    data_source_id: str,
    credential_type: str = "default",
    include_secret: bool = False,
) -> dict | None:
    """查询数据源凭证。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, data_source_id, credential_type,
                           secret_payload, secret_version, secret_updated_at, extra,
                           created_at, updated_at
                    FROM data_source_credentials
                    WHERE data_source_id = %s
                      AND credential_type = %s
                    LIMIT 1
                    """,
                    (data_source_id, credential_type),
                )
                row = cur.fetchone()
                if not row:
                    return None
                result = _normalize_record(dict(row))
                if include_secret:
                    result["credential_payload"] = _open_json_payload(str(result.get("secret_payload") or ""))
                else:
                    result["credential_payload"] = {}
                result["secret_payload"] = ""
                return result
    except Exception as e:
        logger.error(
            f"查询 data_source_credentials 失败 (data_source_id={data_source_id}, credential_type={credential_type}): {e}"
        )
        return None


def upsert_unified_data_source_config(
    *,
    company_id: str,
    data_source_id: str,
    config_type: str,
    config: dict | None = None,
    is_active: bool = True,
) -> dict | None:
    """写入数据源配置；当 is_active=true 时将同类型旧配置置为非激活。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if is_active:
                    cur.execute(
                        """
                        UPDATE data_source_configs
                        SET is_active = false,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE data_source_id = %s
                          AND config_type = %s
                          AND is_active = true
                        """,
                        (data_source_id, config_type),
                    )
                cur.execute(
                    """
                    INSERT INTO data_source_configs (
                        company_id, data_source_id, config_type, config, version, is_active
                    ) VALUES (
                        %s, %s, %s, %s::jsonb,
                        COALESCE((
                            SELECT MAX(version) + 1
                            FROM data_source_configs
                            WHERE data_source_id = %s
                              AND config_type = %s
                        ), 1),
                        %s
                    )
                    RETURNING id, company_id, data_source_id, config_type, config, version, is_active,
                              created_at, updated_at
                    """,
                    (
                        company_id,
                        data_source_id,
                        config_type,
                        psycopg2.extras.Json(config or {}),
                        data_source_id,
                        config_type,
                        is_active,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"写入 data_source_configs 失败 (company_id={company_id}, data_source_id={data_source_id}, config_type={config_type}): {e}"
        )
        return None


def get_unified_data_source_config(
    *,
    data_source_id: str,
    config_type: str,
    active_only: bool = True,
) -> dict | None:
    """查询数据源配置。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if active_only:
                    cur.execute(
                        """
                        SELECT id, company_id, data_source_id, config_type, config, version, is_active,
                               created_at, updated_at
                        FROM data_source_configs
                        WHERE data_source_id = %s
                          AND config_type = %s
                          AND is_active = true
                        ORDER BY version DESC
                        LIMIT 1
                        """,
                        (data_source_id, config_type),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, company_id, data_source_id, config_type, config, version, is_active,
                               created_at, updated_at
                        FROM data_source_configs
                        WHERE data_source_id = %s
                          AND config_type = %s
                        ORDER BY version DESC
                        LIMIT 1
                        """,
                        (data_source_id, config_type),
                    )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"查询 data_source_configs 失败 (data_source_id={data_source_id}, config_type={config_type}, active_only={active_only}): {e}"
        )
        return None


def create_unified_sync_job(
    *,
    company_id: str,
    data_source_id: str,
    trigger_mode: str = "manual",
    resource_key: str = "default",
    idempotency_key: str | None = None,
    window_start: str | None = None,
    window_end: str | None = None,
    request_payload: dict | None = None,
    checkpoint_before: dict | None = None,
) -> dict | None:
    """创建同步任务；同数据源下幂等键冲突时复用原任务。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO sync_jobs (
                        company_id, data_source_id, trigger_mode, resource_key, idempotency_key,
                        window_start, window_end, request_payload, checkpoint_before
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s::jsonb, %s::jsonb
                    )
                    ON CONFLICT (company_id, data_source_id, idempotency_key)
                    WHERE idempotency_key IS NOT NULL
                    DO UPDATE SET updated_at = CURRENT_TIMESTAMP
                    RETURNING id, company_id, data_source_id, trigger_mode, resource_key,
                              window_start, window_end, idempotency_key, job_status,
                              request_payload, checkpoint_before, checkpoint_after,
                              active_snapshot_id, published_snapshot_id, current_attempt,
                              error_message, started_at, completed_at, created_at, updated_at
                    """,
                    (
                        company_id,
                        data_source_id,
                        trigger_mode,
                        resource_key,
                        idempotency_key,
                        window_start,
                        window_end,
                        psycopg2.extras.Json(request_payload or {}),
                        psycopg2.extras.Json(checkpoint_before or {}),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"创建 sync_jobs 失败 (company_id={company_id}, data_source_id={data_source_id}, idempotency_key={idempotency_key}): {e}"
        )
        return None


def get_unified_sync_job_by_id(sync_job_id: str) -> dict | None:
    """按 id 查询同步任务。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, data_source_id, trigger_mode, resource_key,
                           window_start, window_end, idempotency_key, job_status,
                           request_payload, checkpoint_before, checkpoint_after,
                           active_snapshot_id, published_snapshot_id, current_attempt,
                           error_message, started_at, completed_at, created_at, updated_at
                    FROM sync_jobs
                    WHERE id = %s
                    LIMIT 1
                    """,
                    (sync_job_id,),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"查询 sync_jobs 失败 (id={sync_job_id}): {e}")
        return None


def find_unified_sync_job_by_idempotency_key(
    *,
    company_id: str,
    data_source_id: str,
    idempotency_key: str,
) -> dict | None:
    """按幂等键查询同步任务。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, data_source_id, trigger_mode, resource_key,
                           window_start, window_end, idempotency_key, job_status,
                           request_payload, checkpoint_before, checkpoint_after,
                           active_snapshot_id, published_snapshot_id, current_attempt,
                           error_message, started_at, completed_at, created_at, updated_at
                    FROM sync_jobs
                    WHERE company_id = %s
                      AND data_source_id = %s
                      AND idempotency_key = %s
                    LIMIT 1
                    """,
                    (company_id, data_source_id, idempotency_key),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"查询 sync_jobs 幂等键失败 (company_id={company_id}, data_source_id={data_source_id}, idempotency_key={idempotency_key}): {e}"
        )
        return None


def list_unified_sync_jobs(
    *,
    company_id: str,
    data_source_id: str | None = None,
    job_status: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """查询同步任务列表。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT id, company_id, data_source_id, trigger_mode, resource_key,
                           window_start, window_end, idempotency_key, job_status,
                           request_payload, checkpoint_before, checkpoint_after,
                           active_snapshot_id, published_snapshot_id, current_attempt,
                           error_message, started_at, completed_at, created_at, updated_at
                    FROM sync_jobs
                    WHERE company_id = %s
                """
                params: list[Any] = [company_id]
                if data_source_id:
                    sql += " AND data_source_id = %s"
                    params.append(data_source_id)
                if job_status:
                    sql += " AND job_status = %s"
                    params.append(job_status)
                sql += " ORDER BY created_at DESC LIMIT %s"
                params.append(limit)
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(
            f"查询 sync_jobs 列表失败 (company_id={company_id}, data_source_id={data_source_id}, job_status={job_status}): {e}"
        )
        return []


def create_unified_sync_job_attempt(
    *,
    company_id: str,
    sync_job_id: str,
    attempt_no: int,
    checkpoint_before: dict | None = None,
) -> dict | None:
    """创建同步任务尝试记录。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO sync_job_attempts (
                        company_id, sync_job_id, attempt_no, attempt_status, checkpoint_before
                    ) VALUES (
                        %s, %s, %s, 'running', %s::jsonb
                    )
                    RETURNING id, company_id, sync_job_id, attempt_no, attempt_status,
                              started_at, finished_at, error_message, metrics,
                              checkpoint_before, checkpoint_after, created_at, updated_at
                    """,
                    (
                        company_id,
                        sync_job_id,
                        attempt_no,
                        psycopg2.extras.Json(checkpoint_before or {}),
                    ),
                )
                row = cur.fetchone()
                cur.execute(
                    """
                    UPDATE sync_jobs
                    SET current_attempt = %s,
                        job_status = 'running',
                        started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """,
                    (attempt_no, sync_job_id),
                )
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"创建 sync_job_attempts 失败 (sync_job_id={sync_job_id}, attempt_no={attempt_no}): {e}")
        return None


def update_unified_sync_job_attempt(
    *,
    attempt_id: str,
    attempt_status: str,
    error_message: str = "",
    metrics: dict | None = None,
    checkpoint_after: dict | None = None,
    finish_attempt: bool = True,
) -> dict | None:
    """更新同步任务尝试结果。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE sync_job_attempts
                    SET attempt_status = %s,
                        error_message = %s,
                        metrics = %s::jsonb,
                        checkpoint_after = %s::jsonb,
                        finished_at = CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE finished_at END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING id, company_id, sync_job_id, attempt_no, attempt_status,
                              started_at, finished_at, error_message, metrics,
                              checkpoint_before, checkpoint_after, created_at, updated_at
                    """,
                    (
                        attempt_status,
                        error_message,
                        psycopg2.extras.Json(metrics or {}),
                        psycopg2.extras.Json(checkpoint_after or {}),
                        finish_attempt,
                        attempt_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 sync_job_attempts 失败 (attempt_id={attempt_id}, status={attempt_status}): {e}")
        return None


def update_unified_sync_job_status(
    *,
    sync_job_id: str,
    job_status: str,
    error_message: str = "",
    checkpoint_after: dict | None = None,
    active_snapshot_id: str | None = None,
    published_snapshot_id: str | None = None,
    finish_job: bool = False,
) -> dict | None:
    """更新同步任务状态。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE sync_jobs
                    SET job_status = %s,
                        error_message = %s,
                        checkpoint_after = CASE
                            WHEN %s::jsonb = '{}'::jsonb THEN checkpoint_after
                            ELSE %s::jsonb
                        END,
                        active_snapshot_id = COALESCE(%s, active_snapshot_id),
                        published_snapshot_id = COALESCE(%s, published_snapshot_id),
                        completed_at = CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE completed_at END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING id, company_id, data_source_id, trigger_mode, resource_key,
                              window_start, window_end, idempotency_key, job_status,
                              request_payload, checkpoint_before, checkpoint_after,
                              active_snapshot_id, published_snapshot_id, current_attempt,
                              error_message, started_at, completed_at, created_at, updated_at
                    """,
                    (
                        job_status,
                        error_message,
                        psycopg2.extras.Json(checkpoint_after or {}),
                        psycopg2.extras.Json(checkpoint_after or {}),
                        active_snapshot_id,
                        published_snapshot_id,
                        finish_job,
                        sync_job_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 sync_jobs 状态失败 (sync_job_id={sync_job_id}, status={job_status}): {e}")
        return None


def upsert_unified_sync_checkpoint(
    *,
    company_id: str,
    data_source_id: str,
    resource_key: str = "default",
    checkpoint_value: dict | None = None,
    updated_by_job_id: str | None = None,
) -> dict | None:
    """写入同步 checkpoint。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO sync_checkpoints (
                        company_id, data_source_id, resource_key, checkpoint_value, checkpoint_version, updated_by_job_id
                    ) VALUES (
                        %s, %s, %s, %s::jsonb, 1, %s
                    )
                    ON CONFLICT (data_source_id, resource_key)
                    DO UPDATE SET
                        checkpoint_value = EXCLUDED.checkpoint_value,
                        checkpoint_version = sync_checkpoints.checkpoint_version + 1,
                        updated_by_job_id = EXCLUDED.updated_by_job_id,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id, company_id, data_source_id, resource_key, checkpoint_value,
                              checkpoint_version, updated_by_job_id, created_at, updated_at
                    """,
                    (
                        company_id,
                        data_source_id,
                        resource_key,
                        psycopg2.extras.Json(checkpoint_value or {}),
                        updated_by_job_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"写入 sync_checkpoints 失败 (company_id={company_id}, data_source_id={data_source_id}, resource_key={resource_key}): {e}"
        )
        return None


def get_unified_sync_checkpoint(*, data_source_id: str, resource_key: str = "default") -> dict | None:
    """查询同步 checkpoint。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, data_source_id, resource_key, checkpoint_value,
                           checkpoint_version, updated_by_job_id, created_at, updated_at
                    FROM sync_checkpoints
                    WHERE data_source_id = %s
                      AND resource_key = %s
                    LIMIT 1
                    """,
                    (data_source_id, resource_key),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"查询 sync_checkpoints 失败 (data_source_id={data_source_id}, resource_key={resource_key}): {e}")
        return None


def create_unified_raw_ingestion_batch(
    *,
    company_id: str,
    data_source_id: str,
    sync_job_id: str,
    sync_job_attempt_id: str | None = None,
    resource_key: str = "default",
    meta: dict | None = None,
) -> dict | None:
    """创建原始数据批次。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO raw_ingestion_batches (
                        company_id, data_source_id, sync_job_id, sync_job_attempt_id,
                        resource_key, batch_status, meta
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, 'staging', %s::jsonb
                    )
                    RETURNING id, company_id, data_source_id, sync_job_id, sync_job_attempt_id,
                              resource_key, batch_status, record_count, data_hash, meta,
                              created_at, updated_at
                    """,
                    (
                        company_id,
                        data_source_id,
                        sync_job_id,
                        sync_job_attempt_id,
                        resource_key,
                        psycopg2.extras.Json(meta or {}),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"创建 raw_ingestion_batches 失败 (data_source_id={data_source_id}, sync_job_id={sync_job_id}): {e}"
        )
        return None


def append_unified_raw_ingestion_records(
    *,
    company_id: str,
    data_source_id: str,
    batch_id: str,
    records: list[dict],
) -> int:
    """向原始层追加记录（append-only）。"""
    if not records:
        return 0

    conn_manager = get_conn()
    inserted = 0
    try:
        with conn_manager as conn:
            with conn.cursor() as cur:
                for record in records:
                    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
                    cur.execute(
                        """
                        INSERT INTO raw_ingestion_records (
                            company_id, data_source_id, batch_id,
                            source_record_key, source_event_time, payload, payload_hash
                        ) VALUES (
                            %s, %s, %s,
                            %s, %s, %s::jsonb, %s
                        )
                        """,
                        (
                            company_id,
                            data_source_id,
                            batch_id,
                            str(record.get("source_record_key") or ""),
                            record.get("source_event_time"),
                            psycopg2.extras.Json(payload),
                            str(record.get("payload_hash") or ""),
                        ),
                    )
                    inserted += 1

                cur.execute(
                    """
                    UPDATE raw_ingestion_batches
                    SET record_count = record_count + %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """,
                    (inserted, batch_id),
                )
            conn.commit()
            return inserted
    except Exception as e:
        logger.error(
            f"写入 raw_ingestion_records 失败 (data_source_id={data_source_id}, batch_id={batch_id}, records={len(records)}): {e}"
        )
        return 0


def update_unified_raw_ingestion_batch_status(
    *,
    batch_id: str,
    batch_status: str,
    data_hash: str = "",
    meta: dict | None = None,
) -> dict | None:
    """更新原始批次状态。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE raw_ingestion_batches
                    SET batch_status = %s,
                        data_hash = CASE WHEN %s = '' THEN data_hash ELSE %s END,
                        meta = CASE
                            WHEN %s::jsonb = '{}'::jsonb THEN meta
                            ELSE %s::jsonb
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING id, company_id, data_source_id, sync_job_id, sync_job_attempt_id,
                              resource_key, batch_status, record_count, data_hash, meta,
                              created_at, updated_at
                    """,
                    (
                        batch_status,
                        data_hash,
                        data_hash,
                        psycopg2.extras.Json(meta or {}),
                        psycopg2.extras.Json(meta or {}),
                        batch_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 raw_ingestion_batches 状态失败 (batch_id={batch_id}, status={batch_status}): {e}")
        return None


def create_unified_dataset_snapshot(
    *,
    company_id: str,
    data_source_id: str,
    resource_key: str = "default",
    sync_job_id: str | None = None,
    sync_job_attempt_id: str | None = None,
    snapshot_name: str = "",
    snapshot_status: str = "candidate",
    record_count: int = 0,
    data_hash: str = "",
    schema_hash: str = "",
    window_start: str | None = None,
    window_end: str | None = None,
    meta: dict | None = None,
) -> dict | None:
    """创建数据快照（默认 candidate）。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO dataset_snapshots (
                        company_id, data_source_id, sync_job_id, sync_job_attempt_id,
                        resource_key, snapshot_name, snapshot_version, snapshot_status,
                        is_published, record_count, data_hash, schema_hash,
                        window_start, window_end, meta
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, %s,
                        COALESCE((
                            SELECT MAX(snapshot_version) + 1
                            FROM dataset_snapshots
                            WHERE data_source_id = %s
                              AND resource_key = %s
                        ), 1),
                        %s, false, %s, %s, %s,
                        %s, %s, %s::jsonb
                    )
                    RETURNING id, company_id, data_source_id, sync_job_id, sync_job_attempt_id,
                              resource_key, snapshot_name, snapshot_version, snapshot_status,
                              is_published, published_at, published_by_job_id,
                              record_count, data_hash, schema_hash, window_start, window_end,
                              meta, created_at, updated_at
                    """,
                    (
                        company_id,
                        data_source_id,
                        sync_job_id,
                        sync_job_attempt_id,
                        resource_key,
                        snapshot_name,
                        data_source_id,
                        resource_key,
                        snapshot_status,
                        record_count,
                        data_hash,
                        schema_hash,
                        window_start,
                        window_end,
                        psycopg2.extras.Json(meta or {}),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"创建 dataset_snapshots 失败 (company_id={company_id}, data_source_id={data_source_id}, resource_key={resource_key}): {e}"
        )
        return None


def append_unified_dataset_snapshot_items(
    *,
    company_id: str,
    data_source_id: str,
    snapshot_id: str,
    items: list[dict],
) -> int:
    """向快照追加数据项。"""
    if not items:
        return 0
    conn_manager = get_conn()
    inserted = 0
    try:
        with conn_manager as conn:
            with conn.cursor() as cur:
                for item in items:
                    payload = item.get("item_payload") if isinstance(item.get("item_payload"), dict) else {}
                    cur.execute(
                        """
                        INSERT INTO dataset_snapshot_items (
                            company_id, data_source_id, snapshot_id,
                            item_key, item_payload, item_hash
                        ) VALUES (
                            %s, %s, %s,
                            %s, %s::jsonb, %s
                        )
                        ON CONFLICT (snapshot_id, item_hash, item_key)
                        DO NOTHING
                        """,
                        (
                            company_id,
                            data_source_id,
                            snapshot_id,
                            str(item.get("item_key") or ""),
                            psycopg2.extras.Json(payload),
                            str(item.get("item_hash") or ""),
                        ),
                    )
                    inserted += 1 if cur.rowcount > 0 else 0

                cur.execute(
                    """
                    UPDATE dataset_snapshots
                    SET record_count = record_count + %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """,
                    (inserted, snapshot_id),
                )
            conn.commit()
            return inserted
    except Exception as e:
        logger.error(
            f"写入 dataset_snapshot_items 失败 (data_source_id={data_source_id}, snapshot_id={snapshot_id}, items={len(items)}): {e}"
        )
        return 0


def mark_unified_dataset_snapshot_published(
    *,
    snapshot_id: str,
    published_by_job_id: str | None = None,
) -> dict | None:
    """发布快照：同资源下旧 published 标记为 superseded，新快照标记为 published。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, data_source_id, resource_key
                    FROM dataset_snapshots
                    WHERE id = %s
                    LIMIT 1
                    """,
                    (snapshot_id,),
                )
                target = cur.fetchone()
                if not target:
                    return None

                data_source_id = target["data_source_id"]
                resource_key = target["resource_key"]

                cur.execute(
                    """
                    UPDATE dataset_snapshots
                    SET is_published = false,
                        snapshot_status = CASE
                            WHEN snapshot_status = 'published' THEN 'superseded'
                            ELSE snapshot_status
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE data_source_id = %s
                      AND resource_key = %s
                      AND id <> %s
                      AND is_published = true
                    """,
                    (data_source_id, resource_key, snapshot_id),
                )

                cur.execute(
                    """
                    UPDATE dataset_snapshots
                    SET is_published = true,
                        snapshot_status = 'published',
                        published_at = CURRENT_TIMESTAMP,
                        published_by_job_id = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING id, company_id, data_source_id, sync_job_id, sync_job_attempt_id,
                              resource_key, snapshot_name, snapshot_version, snapshot_status,
                              is_published, published_at, published_by_job_id,
                              record_count, data_hash, schema_hash, window_start, window_end,
                              meta, created_at, updated_at
                    """,
                    (published_by_job_id, snapshot_id),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"发布 dataset_snapshots 失败 (snapshot_id={snapshot_id}): {e}")
        return None


def get_unified_published_dataset_snapshot(
    *,
    data_source_id: str,
    resource_key: str = "default",
) -> dict | None:
    """查询已发布快照。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, data_source_id, sync_job_id, sync_job_attempt_id,
                           resource_key, snapshot_name, snapshot_version, snapshot_status,
                           is_published, published_at, published_by_job_id,
                           record_count, data_hash, schema_hash, window_start, window_end,
                           meta, created_at, updated_at
                    FROM dataset_snapshots
                    WHERE data_source_id = %s
                      AND resource_key = %s
                      AND is_published = true
                    ORDER BY published_at DESC NULLS LAST, updated_at DESC
                    LIMIT 1
                    """,
                    (data_source_id, resource_key),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"查询已发布 dataset_snapshots 失败 (data_source_id={data_source_id}, resource_key={resource_key}): {e}"
        )
        return None


def get_unified_dataset_snapshot_by_id(*, snapshot_id: str) -> dict | None:
    """按 snapshot_id 查询快照。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, data_source_id, sync_job_id, sync_job_attempt_id,
                           resource_key, snapshot_name, snapshot_version, snapshot_status,
                           is_published, published_at, published_by_job_id,
                           record_count, data_hash, schema_hash, window_start, window_end,
                           meta, created_at, updated_at
                    FROM dataset_snapshots
                    WHERE id = %s
                    LIMIT 1
                    """,
                    (snapshot_id,),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"查询 dataset_snapshots 失败 (id={snapshot_id}): {e}")
        return None


def list_unified_dataset_snapshot_items(
    *,
    snapshot_id: str,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict]:
    """按 snapshot_id 查询快照行。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT id, snapshot_id, data_source_id, item_key, item_payload, item_hash, created_at
                    FROM dataset_snapshot_items
                    WHERE snapshot_id = %s
                    ORDER BY id ASC
                """
                params: list[Any] = [snapshot_id]
                if offset > 0:
                    sql += " OFFSET %s"
                    params.append(offset)
                if limit is not None and limit > 0:
                    sql += " LIMIT %s"
                    params.append(limit)
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(f"查询 dataset_snapshot_items 失败 (snapshot_id={snapshot_id}, limit={limit}, offset={offset}): {e}")
        return []


def list_unified_dataset_snapshots(
    *,
    company_id: str,
    data_source_id: str | None = None,
    resource_key: str | None = None,
    snapshot_status: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """查询快照列表。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT id, company_id, data_source_id, sync_job_id, sync_job_attempt_id,
                           resource_key, snapshot_name, snapshot_version, snapshot_status,
                           is_published, published_at, published_by_job_id,
                           record_count, data_hash, schema_hash, window_start, window_end,
                           meta, created_at, updated_at
                    FROM dataset_snapshots
                    WHERE company_id = %s
                """
                params: list[Any] = [company_id]
                if data_source_id:
                    sql += " AND data_source_id = %s"
                    params.append(data_source_id)
                if resource_key:
                    sql += " AND resource_key = %s"
                    params.append(resource_key)
                if snapshot_status:
                    sql += " AND snapshot_status = %s"
                    params.append(snapshot_status)
                sql += " ORDER BY created_at DESC LIMIT %s"
                params.append(limit)
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(
            f"查询 dataset_snapshots 列表失败 (company_id={company_id}, data_source_id={data_source_id}, resource_key={resource_key}, snapshot_status={snapshot_status}): {e}"
        )
        return []


def upsert_unified_dataset_binding(
    *,
    company_id: str,
    binding_scope: str,
    binding_code: str,
    data_source_id: str,
    resource_key: str = "default",
    role_code: str = "source",
    binding_name: str = "",
    is_required: bool = True,
    priority: int = 100,
    filter_config: dict | None = None,
    mapping_config: dict | None = None,
    status: str = "active",
) -> dict | None:
    """写入数据集绑定关系。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO dataset_bindings (
                        company_id, binding_scope, binding_code, binding_name,
                        data_source_id, resource_key, role_code, is_required, priority,
                        filter_config, mapping_config, status
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s::jsonb, %s::jsonb, %s
                    )
                    ON CONFLICT (company_id, binding_scope, binding_code, role_code, data_source_id, resource_key)
                    DO UPDATE SET
                        binding_name = EXCLUDED.binding_name,
                        is_required = EXCLUDED.is_required,
                        priority = EXCLUDED.priority,
                        filter_config = EXCLUDED.filter_config,
                        mapping_config = EXCLUDED.mapping_config,
                        status = EXCLUDED.status,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id, company_id, binding_scope, binding_code, binding_name,
                              data_source_id, resource_key, role_code, is_required, priority,
                              filter_config, mapping_config, status, created_at, updated_at
                    """,
                    (
                        company_id,
                        binding_scope,
                        binding_code,
                        binding_name,
                        data_source_id,
                        resource_key,
                        role_code,
                        is_required,
                        priority,
                        psycopg2.extras.Json(filter_config or {}),
                        psycopg2.extras.Json(mapping_config or {}),
                        status,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"写入 dataset_bindings 失败 (company_id={company_id}, binding_scope={binding_scope}, binding_code={binding_code}, data_source_id={data_source_id}): {e}"
        )
        return None


def list_unified_dataset_bindings(
    *,
    company_id: str,
    binding_scope: str | None = None,
    binding_code: str | None = None,
    status: str | None = "active",
) -> list[dict]:
    """查询数据集绑定关系。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT id, company_id, binding_scope, binding_code, binding_name,
                           data_source_id, resource_key, role_code, is_required, priority,
                           filter_config, mapping_config, status, created_at, updated_at
                    FROM dataset_bindings
                    WHERE company_id = %s
                """
                params: list[Any] = [company_id]
                if binding_scope:
                    sql += " AND binding_scope = %s"
                    params.append(binding_scope)
                if binding_code:
                    sql += " AND binding_code = %s"
                    params.append(binding_code)
                if status:
                    sql += " AND status = %s"
                    params.append(status)
                sql += " ORDER BY priority ASC, updated_at DESC"
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(
            f"查询 dataset_bindings 列表失败 (company_id={company_id}, binding_scope={binding_scope}, binding_code={binding_code}, status={status}): {e}"
        )
        return []


def create_unified_data_source_event(
    *,
    company_id: str,
    data_source_id: str,
    event_type: str,
    event_level: str = "info",
    event_message: str = "",
    event_payload: dict | None = None,
    sync_job_id: str | None = None,
) -> dict | None:
    """写入数据源事件。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO data_source_events (
                        company_id, data_source_id, sync_job_id,
                        event_type, event_level, event_message, event_payload
                    ) VALUES (
                        %s, %s, %s,
                        %s, %s, %s, %s::jsonb
                    )
                    RETURNING id, company_id, data_source_id, sync_job_id,
                              event_type, event_level, event_message, event_payload, created_at
                    """,
                    (
                        company_id,
                        data_source_id,
                        sync_job_id,
                        event_type,
                        event_level,
                        event_message,
                        psycopg2.extras.Json(event_payload or {}),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"写入 data_source_events 失败 (company_id={company_id}, data_source_id={data_source_id}, event_type={event_type}): {e}"
        )
        return None


def list_unified_data_source_events(
    *,
    company_id: str,
    data_source_id: str | None = None,
    sync_job_id: str | None = None,
    event_level: str | None = None,
    limit: int = 200,
) -> list[dict]:
    """查询数据源事件。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT id, company_id, data_source_id, sync_job_id,
                           event_type, event_level, event_message, event_payload, created_at
                    FROM data_source_events
                    WHERE company_id = %s
                """
                params: list[Any] = [company_id]
                if data_source_id:
                    sql += " AND data_source_id = %s"
                    params.append(data_source_id)
                if sync_job_id:
                    sql += " AND sync_job_id = %s"
                    params.append(sync_job_id)
                if event_level:
                    sql += " AND event_level = %s"
                    params.append(event_level)
                sql += " ORDER BY created_at DESC LIMIT %s"
                params.append(limit)
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(
            f"查询 data_source_events 列表失败 (company_id={company_id}, data_source_id={data_source_id}, sync_job_id={sync_job_id}, event_level={event_level}): {e}"
        )
        return []


# ══════════════════════════════════════════════════════════════════════════════
# 自动对账任务与异常闭环（recon_auto_tasks / recon_auto_runs / recon_exception_tasks）
# ══════════════════════════════════════════════════════════════════════════════

def create_recon_auto_task(
    *,
    company_id: str,
    task_name: str,
    rule_code: str,
    rule_id: str = "",
    is_enabled: bool = True,
    schedule_type: str = "daily",
    schedule_expr: str = "",
    biz_date_offset: str = "T-1",
    max_wait_until: str = "",
    retry_policy_json: dict | None = None,
    input_mode: str = "bound_source",
    bound_data_source_ids: list[str] | None = None,
    completeness_policy_json: dict | None = None,
    auto_create_exceptions: bool = True,
    auto_remind: bool = False,
    channel_config_id: str | None = None,
    reminder_policy_json: dict | None = None,
    owner_mapping_json: dict | None = None,
    task_meta_json: dict | None = None,
) -> dict | None:
    """创建自动运行任务配置。"""
    import uuid as _uuid

    conn_manager = get_conn()
    try:
        task_code = f"task_{_uuid.uuid4().hex[:10]}"
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO recon_auto_tasks (
                        company_id, task_code, task_name, rule_code, rule_id, is_enabled,
                        schedule_type, schedule_expr, biz_date_offset, max_wait_until,
                        retry_policy_json, input_mode, bound_data_source_ids, completeness_policy_json,
                        auto_create_exceptions, auto_remind, channel_config_id,
                        reminder_policy_json, owner_mapping_json, task_meta_json
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s::jsonb, %s, %s::jsonb, %s::jsonb,
                        %s, %s, %s,
                        %s::jsonb, %s::jsonb, %s::jsonb
                    )
                    RETURNING id, company_id, task_code, task_name, rule_code, rule_id, is_enabled,
                              schedule_type, schedule_expr, biz_date_offset, max_wait_until,
                              retry_policy_json, input_mode, bound_data_source_ids, completeness_policy_json,
                              auto_create_exceptions, auto_remind, channel_config_id,
                              reminder_policy_json, owner_mapping_json, task_meta_json,
                              created_at, updated_at
                    """,
                    (
                        company_id,
                        task_code,
                        task_name,
                        rule_code,
                        rule_id,
                        is_enabled,
                        schedule_type,
                        schedule_expr,
                        biz_date_offset,
                        max_wait_until,
                        psycopg2.extras.Json(retry_policy_json or {}),
                        input_mode,
                        psycopg2.extras.Json(bound_data_source_ids or []),
                        psycopg2.extras.Json(completeness_policy_json or {}),
                        auto_create_exceptions,
                        auto_remind,
                        channel_config_id,
                        psycopg2.extras.Json(reminder_policy_json or {}),
                        psycopg2.extras.Json(owner_mapping_json or {}),
                        psycopg2.extras.Json(task_meta_json or {}),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"创建 recon_auto_tasks 失败 (company_id={company_id}, rule_code={rule_code}): {e}")
        return None


def update_recon_auto_task(
    *,
    company_id: str,
    auto_task_id: str,
    task_name: str | None = None,
    rule_code: str | None = None,
    rule_id: str | None = None,
    is_enabled: bool | None = None,
    schedule_type: str | None = None,
    schedule_expr: str | None = None,
    biz_date_offset: str | None = None,
    max_wait_until: str | None = None,
    retry_policy_json: dict | None = None,
    input_mode: str | None = None,
    bound_data_source_ids: list[str] | None = None,
    completeness_policy_json: dict | None = None,
    auto_create_exceptions: bool | None = None,
    auto_remind: bool | None = None,
    channel_config_id: str | None = None,
    reminder_policy_json: dict | None = None,
    owner_mapping_json: dict | None = None,
    task_meta_json: dict | None = None,
) -> dict | None:
    """更新自动运行任务配置。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE recon_auto_tasks
                    SET task_name = COALESCE(%s, task_name),
                        rule_code = COALESCE(%s, rule_code),
                        rule_id = COALESCE(%s, rule_id),
                        is_enabled = COALESCE(%s, is_enabled),
                        schedule_type = COALESCE(%s, schedule_type),
                        schedule_expr = COALESCE(%s, schedule_expr),
                        biz_date_offset = COALESCE(%s, biz_date_offset),
                        max_wait_until = COALESCE(%s, max_wait_until),
                        retry_policy_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN retry_policy_json
                            ELSE %s::jsonb
                        END,
                        input_mode = COALESCE(%s, input_mode),
                        bound_data_source_ids = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN bound_data_source_ids
                            ELSE %s::jsonb
                        END,
                        completeness_policy_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN completeness_policy_json
                            ELSE %s::jsonb
                        END,
                        auto_create_exceptions = COALESCE(%s, auto_create_exceptions),
                        auto_remind = COALESCE(%s, auto_remind),
                        channel_config_id = COALESCE(%s, channel_config_id),
                        reminder_policy_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN reminder_policy_json
                            ELSE %s::jsonb
                        END,
                        owner_mapping_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN owner_mapping_json
                            ELSE %s::jsonb
                        END,
                        task_meta_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN task_meta_json
                            ELSE %s::jsonb
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                      AND company_id = %s
                    RETURNING id, company_id, task_code, task_name, rule_code, rule_id, is_enabled,
                              schedule_type, schedule_expr, biz_date_offset, max_wait_until,
                              retry_policy_json, input_mode, bound_data_source_ids, completeness_policy_json,
                              auto_create_exceptions, auto_remind, channel_config_id,
                              reminder_policy_json, owner_mapping_json, task_meta_json,
                              created_at, updated_at
                    """,
                    (
                        task_name,
                        rule_code,
                        rule_id,
                        is_enabled,
                        schedule_type,
                        schedule_expr,
                        biz_date_offset,
                        max_wait_until,
                        psycopg2.extras.Json(retry_policy_json) if retry_policy_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(retry_policy_json) if retry_policy_json is not None else psycopg2.extras.Json(None),
                        input_mode,
                        psycopg2.extras.Json(bound_data_source_ids) if bound_data_source_ids is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(bound_data_source_ids) if bound_data_source_ids is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(completeness_policy_json) if completeness_policy_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(completeness_policy_json) if completeness_policy_json is not None else psycopg2.extras.Json(None),
                        auto_create_exceptions,
                        auto_remind,
                        channel_config_id,
                        psycopg2.extras.Json(reminder_policy_json) if reminder_policy_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(reminder_policy_json) if reminder_policy_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(owner_mapping_json) if owner_mapping_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(owner_mapping_json) if owner_mapping_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(task_meta_json) if task_meta_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(task_meta_json) if task_meta_json is not None else psycopg2.extras.Json(None),
                        auto_task_id,
                        company_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 recon_auto_tasks 失败 (company_id={company_id}, id={auto_task_id}): {e}")
        return None


def get_recon_auto_task(*, company_id: str, auto_task_id: str) -> dict | None:
    """查询单个自动运行任务配置。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, task_code, task_name, rule_code, is_enabled,
                           rule_id,
                           schedule_type, schedule_expr, biz_date_offset, max_wait_until,
                           retry_policy_json, input_mode, bound_data_source_ids, completeness_policy_json,
                           auto_create_exceptions, auto_remind, channel_config_id,
                           reminder_policy_json, owner_mapping_json, task_meta_json,
                           created_at, updated_at
                    FROM recon_auto_tasks
                    WHERE company_id = %s
                      AND id = %s
                    LIMIT 1
                    """,
                    (company_id, auto_task_id),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"查询 recon_auto_tasks 失败 (company_id={company_id}, id={auto_task_id}): {e}")
        return None


def list_recon_auto_tasks(
    *,
    company_id: str,
    include_disabled: bool = True,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """查询自动运行任务配置列表。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT id, company_id, task_code, task_name, rule_code, rule_id, is_enabled,
                           schedule_type, schedule_expr, biz_date_offset, max_wait_until,
                           retry_policy_json, input_mode, bound_data_source_ids, completeness_policy_json,
                           auto_create_exceptions, auto_remind, channel_config_id,
                           reminder_policy_json, owner_mapping_json, task_meta_json,
                           created_at, updated_at
                    FROM recon_auto_tasks
                    WHERE company_id = %s
                """
                params: list[Any] = [company_id]
                if not include_disabled:
                    sql += " AND is_enabled = true"
                sql += " ORDER BY updated_at DESC LIMIT %s OFFSET %s"
                params.extend([limit, offset])
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(f"查询 recon_auto_tasks 列表失败 (company_id={company_id}): {e}")
        return []


def disable_recon_auto_task(*, company_id: str, auto_task_id: str) -> dict | None:
    """停用自动运行任务配置（逻辑删除）。"""
    return update_recon_auto_task(company_id=company_id, auto_task_id=auto_task_id, is_enabled=False)


def create_recon_auto_run(
    *,
    company_id: str,
    auto_task_id: str,
    biz_date: str,
    trigger_mode: str = "cron",
    run_status: str = "scheduled",
    readiness_status: str = "waiting_data",
    closure_status: str = "open",
    run_no: int | None = None,
    task_snapshot_json: dict | None = None,
    source_snapshot_json: dict | None = None,
    recon_result_summary_json: dict | None = None,
    anomaly_count: int = 0,
    error_message: str = "",
) -> dict | None:
    """创建自动运行批次记录（run）。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if run_no is None:
                    cur.execute(
                        """
                        SELECT COALESCE(MAX(run_no), 0) + 1 AS next_run_no
                        FROM recon_auto_runs
                        WHERE auto_task_id = %s
                          AND biz_date = %s
                        """,
                        (auto_task_id, biz_date),
                    )
                    row = cur.fetchone()
                    run_no = int((row or {}).get("next_run_no") or 1)

                cur.execute(
                    """
                    INSERT INTO recon_auto_runs (
                        company_id, auto_task_id, biz_date, run_status, readiness_status, closure_status,
                        trigger_mode, run_no, task_snapshot_json, source_snapshot_json,
                        recon_result_summary_json, anomaly_count, error_message
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s::jsonb, %s::jsonb,
                        %s::jsonb, %s, %s
                    )
                    RETURNING id, company_id, auto_task_id, biz_date, run_status, readiness_status, closure_status,
                              trigger_mode, run_no, task_snapshot_json, source_snapshot_json,
                              recon_result_summary_json, anomaly_count, started_at, finished_at, error_message,
                              created_at, updated_at
                    """,
                    (
                        company_id,
                        auto_task_id,
                        biz_date,
                        run_status,
                        readiness_status,
                        closure_status,
                        trigger_mode,
                        run_no,
                        psycopg2.extras.Json(task_snapshot_json or {}),
                        psycopg2.extras.Json(source_snapshot_json or {}),
                        psycopg2.extras.Json(recon_result_summary_json or {}),
                        anomaly_count,
                        error_message,
                    ),
                )
                created = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(created)) if created else None
    except Exception as e:
        logger.error(f"创建 recon_auto_runs 失败 (company_id={company_id}, auto_task_id={auto_task_id}, biz_date={biz_date}): {e}")
        return None


def get_recon_auto_run(*, company_id: str, auto_run_id: str) -> dict | None:
    """查询单个运行批次记录。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT r.id, r.company_id, r.auto_task_id, r.biz_date,
                           r.run_status, r.readiness_status, r.closure_status,
                           r.trigger_mode, r.run_no, r.task_snapshot_json, r.source_snapshot_json,
                           r.recon_result_summary_json, r.anomaly_count, r.started_at, r.finished_at,
                           r.error_message, r.created_at, r.updated_at,
                           t.task_name, t.rule_code
                    FROM recon_auto_runs r
                    JOIN recon_auto_tasks t ON t.id = r.auto_task_id
                    WHERE r.company_id = %s
                      AND r.id = %s
                    LIMIT 1
                    """,
                    (company_id, auto_run_id),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"查询 recon_auto_runs 失败 (company_id={company_id}, id={auto_run_id}): {e}")
        return None


def list_recon_auto_runs(
    *,
    company_id: str,
    auto_task_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """查询运行批次记录列表。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT r.id, r.company_id, r.auto_task_id, r.biz_date,
                           r.run_status, r.readiness_status, r.closure_status,
                           r.trigger_mode, r.run_no, r.task_snapshot_json, r.source_snapshot_json,
                           r.recon_result_summary_json, r.anomaly_count, r.started_at, r.finished_at,
                           r.error_message, r.created_at, r.updated_at,
                           t.task_name, t.rule_code
                    FROM recon_auto_runs r
                    JOIN recon_auto_tasks t ON t.id = r.auto_task_id
                    WHERE r.company_id = %s
                """
                params: list[Any] = [company_id]
                if auto_task_id:
                    sql += " AND r.auto_task_id = %s"
                    params.append(auto_task_id)
                sql += " ORDER BY r.created_at DESC LIMIT %s OFFSET %s"
                params.extend([limit, offset])
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(f"查询 recon_auto_runs 列表失败 (company_id={company_id}, auto_task_id={auto_task_id}): {e}")
        return []


def update_recon_auto_run_status(
    *,
    company_id: str,
    auto_run_id: str,
    run_status: str | None = None,
    readiness_status: str | None = None,
    closure_status: str | None = None,
    recon_result_summary_json: dict | None = None,
    anomaly_count: int | None = None,
    error_message: str | None = None,
    started_at_now: bool = False,
    finished_at_now: bool = False,
) -> dict | None:
    """更新运行批次状态。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE recon_auto_runs
                    SET run_status = COALESCE(%s, run_status),
                        readiness_status = COALESCE(%s, readiness_status),
                        closure_status = COALESCE(%s, closure_status),
                        recon_result_summary_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN recon_result_summary_json
                            ELSE %s::jsonb
                        END,
                        anomaly_count = COALESCE(%s, anomaly_count),
                        error_message = COALESCE(%s, error_message),
                        started_at = CASE WHEN %s THEN COALESCE(started_at, CURRENT_TIMESTAMP) ELSE started_at END,
                        finished_at = CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE finished_at END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                      AND company_id = %s
                    RETURNING id, company_id, auto_task_id, biz_date, run_status, readiness_status, closure_status,
                              trigger_mode, run_no, task_snapshot_json, source_snapshot_json,
                              recon_result_summary_json, anomaly_count, started_at, finished_at, error_message,
                              created_at, updated_at
                    """,
                    (
                        run_status,
                        readiness_status,
                        closure_status,
                        psycopg2.extras.Json(recon_result_summary_json) if recon_result_summary_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(recon_result_summary_json) if recon_result_summary_json is not None else psycopg2.extras.Json(None),
                        anomaly_count,
                        error_message,
                        started_at_now,
                        finished_at_now,
                        auto_run_id,
                        company_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 recon_auto_runs 失败 (company_id={company_id}, id={auto_run_id}): {e}")
        return None


def create_recon_run_job(
    *,
    company_id: str,
    auto_run_id: str,
    job_type: str,
    job_status: str = "queued",
    attempt_no: int = 1,
    idempotency_key: str = "",
    input_json: dict | None = None,
    output_json: dict | None = None,
    error_message: str = "",
) -> dict | None:
    """创建 run 下的短动作执行记录。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO recon_run_jobs (
                        company_id, auto_run_id, job_type, job_status, attempt_no,
                        idempotency_key, input_json, output_json, error_message
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s::jsonb, %s::jsonb, %s
                    )
                    RETURNING id, company_id, auto_run_id, job_type, job_status, attempt_no,
                              idempotency_key, started_at, finished_at, input_json, output_json,
                              error_message, created_at, updated_at
                    """,
                    (
                        company_id,
                        auto_run_id,
                        job_type,
                        job_status,
                        attempt_no,
                        idempotency_key,
                        psycopg2.extras.Json(input_json or {}),
                        psycopg2.extras.Json(output_json or {}),
                        error_message,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"创建 recon_run_jobs 失败 (company_id={company_id}, auto_run_id={auto_run_id}, job_type={job_type}): {e}")
        return None


def update_recon_run_job(
    *,
    company_id: str,
    run_job_id: str,
    job_status: str | None = None,
    output_json: dict | None = None,
    error_message: str | None = None,
    started_at_now: bool = False,
    finished_at_now: bool = False,
) -> dict | None:
    """更新 run_job 状态。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE recon_run_jobs
                    SET job_status = COALESCE(%s, job_status),
                        output_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN output_json
                            ELSE %s::jsonb
                        END,
                        error_message = COALESCE(%s, error_message),
                        started_at = CASE WHEN %s THEN COALESCE(started_at, CURRENT_TIMESTAMP) ELSE started_at END,
                        finished_at = CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE finished_at END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                      AND company_id = %s
                    RETURNING id, company_id, auto_run_id, job_type, job_status, attempt_no,
                              idempotency_key, started_at, finished_at, input_json, output_json,
                              error_message, created_at, updated_at
                    """,
                    (
                        job_status,
                        psycopg2.extras.Json(output_json) if output_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(output_json) if output_json is not None else psycopg2.extras.Json(None),
                        error_message,
                        started_at_now,
                        finished_at_now,
                        run_job_id,
                        company_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 recon_run_jobs 失败 (company_id={company_id}, id={run_job_id}): {e}")
        return None


def create_recon_exception_task(
    *,
    company_id: str,
    auto_task_id: str,
    auto_run_id: str,
    anomaly_key: str,
    anomaly_type: str,
    summary: str,
    detail_json: dict | None = None,
    owner_name: str = "",
    owner_identifier: str = "",
    owner_contact_json: dict | None = None,
    reminder_status: str = "pending",
    processing_status: str = "pending",
    fix_status: str = "pending",
    latest_feedback: str = "",
    feedback_json: dict | None = None,
    verify_required: bool = False,
    verify_run_id: str | None = None,
    is_closed: bool = False,
) -> dict | None:
    """创建或幂等更新异常任务。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO recon_exception_tasks (
                        company_id, auto_task_id, auto_run_id, anomaly_key, anomaly_type,
                        summary, detail_json, owner_name, owner_identifier, owner_contact_json,
                        reminder_status, processing_status, fix_status, latest_feedback,
                        feedback_json, verify_required, verify_run_id, is_closed
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s::jsonb, %s, %s, %s::jsonb,
                        %s, %s, %s, %s,
                        %s::jsonb, %s, %s, %s
                    )
                    ON CONFLICT (auto_run_id, anomaly_key)
                    DO UPDATE SET
                        anomaly_type = EXCLUDED.anomaly_type,
                        summary = EXCLUDED.summary,
                        detail_json = EXCLUDED.detail_json,
                        owner_name = CASE
                            WHEN EXCLUDED.owner_name <> '' THEN EXCLUDED.owner_name
                            ELSE recon_exception_tasks.owner_name
                        END,
                        owner_identifier = CASE
                            WHEN EXCLUDED.owner_identifier <> '' THEN EXCLUDED.owner_identifier
                            ELSE recon_exception_tasks.owner_identifier
                        END,
                        owner_contact_json = CASE
                            WHEN EXCLUDED.owner_contact_json <> '{}'::jsonb THEN EXCLUDED.owner_contact_json
                            ELSE recon_exception_tasks.owner_contact_json
                        END,
                        reminder_status = EXCLUDED.reminder_status,
                        processing_status = EXCLUDED.processing_status,
                        fix_status = EXCLUDED.fix_status,
                        latest_feedback = CASE
                            WHEN EXCLUDED.latest_feedback <> '' THEN EXCLUDED.latest_feedback
                            ELSE recon_exception_tasks.latest_feedback
                        END,
                        feedback_json = CASE
                            WHEN EXCLUDED.feedback_json <> '{}'::jsonb THEN EXCLUDED.feedback_json
                            ELSE recon_exception_tasks.feedback_json
                        END,
                        verify_required = EXCLUDED.verify_required,
                        verify_run_id = COALESCE(EXCLUDED.verify_run_id, recon_exception_tasks.verify_run_id),
                        is_closed = EXCLUDED.is_closed,
                        closed_at = CASE
                            WHEN EXCLUDED.is_closed THEN COALESCE(recon_exception_tasks.closed_at, CURRENT_TIMESTAMP)
                            ELSE NULL
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id, company_id, auto_task_id, auto_run_id, anomaly_key, anomaly_type,
                              summary, detail_json, owner_name, owner_identifier, owner_contact_json,
                              reminder_status, processing_status, fix_status, latest_feedback,
                              feedback_json, verify_required, verify_run_id, last_verified_at,
                              is_closed, closed_at, created_at, updated_at
                    """,
                    (
                        company_id,
                        auto_task_id,
                        auto_run_id,
                        anomaly_key,
                        anomaly_type,
                        summary,
                        psycopg2.extras.Json(detail_json or {}),
                        owner_name,
                        owner_identifier,
                        psycopg2.extras.Json(owner_contact_json or {}),
                        reminder_status,
                        processing_status,
                        fix_status,
                        latest_feedback,
                        psycopg2.extras.Json(feedback_json or {}),
                        verify_required,
                        verify_run_id,
                        is_closed,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"创建 recon_exception_tasks 失败 (company_id={company_id}, auto_run_id={auto_run_id}, anomaly_key={anomaly_key}): {e}"
        )
        return None


def get_recon_exception_task(*, company_id: str, exception_id: str) -> dict | None:
    """查询单个异常任务。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, auto_task_id, auto_run_id, anomaly_key, anomaly_type,
                           summary, detail_json, owner_name, owner_identifier, owner_contact_json,
                           reminder_status, processing_status, fix_status, latest_feedback,
                           feedback_json, verify_required, verify_run_id, last_verified_at,
                           is_closed, closed_at, created_at, updated_at
                    FROM recon_exception_tasks
                    WHERE company_id = %s
                      AND id = %s
                    LIMIT 1
                    """,
                    (company_id, exception_id),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"查询 recon_exception_tasks 失败 (company_id={company_id}, id={exception_id}): {e}")
        return None


def list_recon_exception_tasks(
    *,
    company_id: str,
    auto_run_id: str,
    limit: int = 500,
    offset: int = 0,
) -> list[dict]:
    """按运行批次查询异常任务列表。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, auto_task_id, auto_run_id, anomaly_key, anomaly_type,
                           summary, detail_json, owner_name, owner_identifier, owner_contact_json,
                           reminder_status, processing_status, fix_status, latest_feedback,
                           feedback_json, verify_required, verify_run_id, last_verified_at,
                           is_closed, closed_at, created_at, updated_at
                    FROM recon_exception_tasks
                    WHERE company_id = %s
                      AND auto_run_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (company_id, auto_run_id, limit, offset),
                )
                rows = cur.fetchall()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(f"查询 recon_exception_tasks 失败 (company_id={company_id}, auto_run_id={auto_run_id}): {e}")
        return []


def update_recon_exception_task(
    *,
    company_id: str,
    exception_id: str,
    owner_name: str | None = None,
    owner_identifier: str | None = None,
    owner_contact_json: dict | None = None,
    reminder_status: str | None = None,
    processing_status: str | None = None,
    fix_status: str | None = None,
    latest_feedback: str | None = None,
    feedback_json: dict | None = None,
    verify_required: bool | None = None,
    verify_run_id: str | None = None,
    is_closed: bool | None = None,
) -> dict | None:
    """更新异常任务状态。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE recon_exception_tasks
                    SET owner_name = COALESCE(%s, owner_name),
                        owner_identifier = COALESCE(%s, owner_identifier),
                        owner_contact_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN owner_contact_json
                            ELSE %s::jsonb
                        END,
                        reminder_status = COALESCE(%s, reminder_status),
                        processing_status = COALESCE(%s, processing_status),
                        fix_status = COALESCE(%s, fix_status),
                        latest_feedback = COALESCE(%s, latest_feedback),
                        feedback_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN feedback_json
                            ELSE %s::jsonb
                        END,
                        verify_required = COALESCE(%s, verify_required),
                        verify_run_id = COALESCE(%s, verify_run_id),
                        last_verified_at = CASE WHEN %s IS NOT NULL THEN CURRENT_TIMESTAMP ELSE last_verified_at END,
                        is_closed = COALESCE(%s, is_closed),
                        closed_at = CASE
                            WHEN COALESCE(%s, false) THEN COALESCE(closed_at, CURRENT_TIMESTAMP)
                            ELSE NULL
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                      AND company_id = %s
                    RETURNING id, company_id, auto_task_id, auto_run_id, anomaly_key, anomaly_type,
                              summary, detail_json, owner_name, owner_identifier, owner_contact_json,
                              reminder_status, processing_status, fix_status, latest_feedback,
                              feedback_json, verify_required, verify_run_id, last_verified_at,
                              is_closed, closed_at, created_at, updated_at
                    """,
                    (
                        owner_name,
                        owner_identifier,
                        psycopg2.extras.Json(owner_contact_json) if owner_contact_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(owner_contact_json) if owner_contact_json is not None else psycopg2.extras.Json(None),
                        reminder_status,
                        processing_status,
                        fix_status,
                        latest_feedback,
                        psycopg2.extras.Json(feedback_json) if feedback_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(feedback_json) if feedback_json is not None else psycopg2.extras.Json(None),
                        verify_required,
                        verify_run_id,
                        verify_run_id,
                        is_closed,
                        is_closed,
                        exception_id,
                        company_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 recon_exception_tasks 失败 (company_id={company_id}, id={exception_id}): {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# 执行模型（execution_schemes / execution_run_plans / execution_runs / execution_run_exceptions）
# ══════════════════════════════════════════════════════════════════════════════

def _generate_execution_code(prefix: str) -> str:
    import uuid as _uuid

    return f"{prefix}_{_uuid.uuid4().hex[:12]}"


def create_execution_scheme(
    *,
    company_id: str,
    scheme_name: str,
    scheme_code: str = "",
    scheme_type: str = "recon",
    description: str = "",
    file_rule_code: str = "",
    proc_rule_code: str = "",
    recon_rule_code: str = "",
    scheme_meta_json: dict | None = None,
    is_enabled: bool = True,
    created_by: str | None = None,
) -> dict | None:
    """创建执行方案。"""
    conn_manager = get_conn()
    try:
        resolved_scheme_code = str(scheme_code or "").strip() or _generate_execution_code("scheme")
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO execution_schemes (
                        company_id, scheme_code, scheme_name, scheme_type, description,
                        file_rule_code, proc_rule_code, recon_rule_code, scheme_meta_json,
                        is_enabled, created_by
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s::jsonb,
                        %s, %s
                    )
                    RETURNING id, company_id, scheme_code, scheme_name, scheme_type, description,
                              file_rule_code, proc_rule_code, recon_rule_code, scheme_meta_json,
                              is_enabled, created_by, created_at, updated_at
                    """,
                    (
                        company_id,
                        resolved_scheme_code,
                        scheme_name,
                        scheme_type,
                        description,
                        file_rule_code,
                        proc_rule_code,
                        recon_rule_code,
                        psycopg2.extras.Json(scheme_meta_json or {}),
                        is_enabled,
                        created_by,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"创建 execution_schemes 失败 (company_id={company_id}, scheme_name={scheme_name}): {e}")
        return None


def update_execution_scheme(
    *,
    company_id: str,
    scheme_id: str,
    scheme_name: str | None = None,
    scheme_type: str | None = None,
    description: str | None = None,
    file_rule_code: str | None = None,
    proc_rule_code: str | None = None,
    recon_rule_code: str | None = None,
    scheme_meta_json: dict | None = None,
    is_enabled: bool | None = None,
) -> dict | None:
    """更新执行方案。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE execution_schemes
                    SET scheme_name = COALESCE(%s, scheme_name),
                        scheme_type = COALESCE(%s, scheme_type),
                        description = COALESCE(%s, description),
                        file_rule_code = COALESCE(%s, file_rule_code),
                        proc_rule_code = COALESCE(%s, proc_rule_code),
                        recon_rule_code = COALESCE(%s, recon_rule_code),
                        scheme_meta_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN scheme_meta_json
                            ELSE %s::jsonb
                        END,
                        is_enabled = COALESCE(%s, is_enabled),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                      AND company_id = %s
                    RETURNING id, company_id, scheme_code, scheme_name, scheme_type, description,
                              file_rule_code, proc_rule_code, recon_rule_code, scheme_meta_json,
                              is_enabled, created_by, created_at, updated_at
                    """,
                    (
                        scheme_name,
                        scheme_type,
                        description,
                        file_rule_code,
                        proc_rule_code,
                        recon_rule_code,
                        psycopg2.extras.Json(scheme_meta_json) if scheme_meta_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(scheme_meta_json) if scheme_meta_json is not None else psycopg2.extras.Json(None),
                        is_enabled,
                        scheme_id,
                        company_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 execution_schemes 失败 (company_id={company_id}, scheme_id={scheme_id}): {e}")
        return None


def disable_execution_scheme(*, company_id: str, scheme_id: str) -> dict | None:
    """停用执行方案。"""
    return update_execution_scheme(company_id=company_id, scheme_id=scheme_id, is_enabled=False)


def get_execution_scheme(*, company_id: str, scheme_id: str | None = None, scheme_code: str | None = None) -> dict | None:
    """查询单个执行方案（按 id 或 scheme_code）。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if scheme_id:
                    cur.execute(
                        """
                        SELECT id, company_id, scheme_code, scheme_name, scheme_type, description,
                               file_rule_code, proc_rule_code, recon_rule_code, scheme_meta_json,
                               is_enabled, created_by, created_at, updated_at
                        FROM execution_schemes
                        WHERE company_id = %s
                          AND id = %s
                        LIMIT 1
                        """,
                        (company_id, scheme_id),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, company_id, scheme_code, scheme_name, scheme_type, description,
                               file_rule_code, proc_rule_code, recon_rule_code, scheme_meta_json,
                               is_enabled, created_by, created_at, updated_at
                        FROM execution_schemes
                        WHERE company_id = %s
                          AND scheme_code = %s
                        LIMIT 1
                        """,
                        (company_id, str(scheme_code or "").strip()),
                    )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"查询 execution_schemes 失败 (company_id={company_id}, scheme_id={scheme_id}, scheme_code={scheme_code}): {e}"
        )
        return None


def list_execution_schemes(
    *,
    company_id: str,
    include_disabled: bool = True,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """查询执行方案列表。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT id, company_id, scheme_code, scheme_name, scheme_type, description,
                           file_rule_code, proc_rule_code, recon_rule_code, scheme_meta_json,
                           is_enabled, created_by, created_at, updated_at
                    FROM execution_schemes
                    WHERE company_id = %s
                """
                params: list[Any] = [company_id]
                if not include_disabled:
                    sql += " AND is_enabled = true"
                sql += " ORDER BY updated_at DESC LIMIT %s OFFSET %s"
                params.extend([limit, offset])
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(f"查询 execution_schemes 列表失败 (company_id={company_id}): {e}")
        return []


def create_execution_run_plan(
    *,
    company_id: str,
    plan_name: str,
    scheme_code: str,
    plan_code: str = "",
    schedule_type: str = "daily",
    schedule_expr: str = "",
    biz_date_offset: str = "previous_day",
    input_bindings_json: list[dict] | None = None,
    channel_config_id: str | None = None,
    owner_mapping_json: dict | None = None,
    plan_meta_json: dict | None = None,
    is_enabled: bool = True,
    created_by: str | None = None,
) -> dict | None:
    """创建执行运行计划。"""
    conn_manager = get_conn()
    try:
        resolved_plan_code = str(plan_code or "").strip() or _generate_execution_code("plan")
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO execution_run_plans (
                        company_id, plan_code, plan_name, scheme_code,
                        schedule_type, schedule_expr, biz_date_offset,
                        input_bindings_json, channel_config_id,
                        owner_mapping_json, plan_meta_json,
                        is_enabled, created_by
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s::jsonb, %s,
                        %s::jsonb, %s::jsonb,
                        %s, %s
                    )
                    RETURNING id, company_id, plan_code, plan_name, scheme_code,
                              schedule_type, schedule_expr, biz_date_offset,
                              input_bindings_json, channel_config_id,
                              owner_mapping_json, plan_meta_json,
                              is_enabled, created_by, created_at, updated_at
                    """,
                    (
                        company_id,
                        resolved_plan_code,
                        plan_name,
                        scheme_code,
                        schedule_type,
                        schedule_expr,
                        biz_date_offset,
                        psycopg2.extras.Json(input_bindings_json or []),
                        channel_config_id,
                        psycopg2.extras.Json(owner_mapping_json or {}),
                        psycopg2.extras.Json(plan_meta_json or {}),
                        is_enabled,
                        created_by,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"创建 execution_run_plans 失败 (company_id={company_id}, plan_name={plan_name}): {e}")
        return None


def update_execution_run_plan(
    *,
    company_id: str,
    plan_id: str,
    plan_name: str | None = None,
    scheme_code: str | None = None,
    schedule_type: str | None = None,
    schedule_expr: str | None = None,
    biz_date_offset: str | None = None,
    input_bindings_json: list[dict] | None = None,
    channel_config_id: str | None = None,
    owner_mapping_json: dict | None = None,
    plan_meta_json: dict | None = None,
    is_enabled: bool | None = None,
) -> dict | None:
    """更新执行运行计划。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE execution_run_plans
                    SET plan_name = COALESCE(%s, plan_name),
                        scheme_code = COALESCE(%s, scheme_code),
                        schedule_type = COALESCE(%s, schedule_type),
                        schedule_expr = COALESCE(%s, schedule_expr),
                        biz_date_offset = COALESCE(%s, biz_date_offset),
                        input_bindings_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN input_bindings_json
                            ELSE %s::jsonb
                        END,
                        channel_config_id = COALESCE(%s, channel_config_id),
                        owner_mapping_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN owner_mapping_json
                            ELSE %s::jsonb
                        END,
                        plan_meta_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN plan_meta_json
                            ELSE %s::jsonb
                        END,
                        is_enabled = COALESCE(%s, is_enabled),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                      AND company_id = %s
                    RETURNING id, company_id, plan_code, plan_name, scheme_code,
                              schedule_type, schedule_expr, biz_date_offset,
                              input_bindings_json, channel_config_id,
                              owner_mapping_json, plan_meta_json,
                              is_enabled, created_by, created_at, updated_at
                    """,
                    (
                        plan_name,
                        scheme_code,
                        schedule_type,
                        schedule_expr,
                        biz_date_offset,
                        psycopg2.extras.Json(input_bindings_json) if input_bindings_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(input_bindings_json) if input_bindings_json is not None else psycopg2.extras.Json(None),
                        channel_config_id,
                        psycopg2.extras.Json(owner_mapping_json) if owner_mapping_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(owner_mapping_json) if owner_mapping_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(plan_meta_json) if plan_meta_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(plan_meta_json) if plan_meta_json is not None else psycopg2.extras.Json(None),
                        is_enabled,
                        plan_id,
                        company_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 execution_run_plans 失败 (company_id={company_id}, plan_id={plan_id}): {e}")
        return None


def disable_execution_run_plan(*, company_id: str, plan_id: str) -> dict | None:
    """停用执行运行计划。"""
    return update_execution_run_plan(company_id=company_id, plan_id=plan_id, is_enabled=False)


def delete_execution_run_plan(*, company_id: str, plan_id: str) -> dict | None:
    """删除执行运行计划。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    DELETE FROM execution_run_plans
                    WHERE company_id = %s
                      AND id = %s
                    RETURNING id, company_id, plan_code, plan_name, scheme_code,
                              schedule_type, schedule_expr, biz_date_offset,
                              input_bindings_json, channel_config_id,
                              owner_mapping_json, plan_meta_json,
                              is_enabled, created_by, created_at, updated_at
                    """,
                    (company_id, plan_id),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"删除 execution_run_plans 失败 (company_id={company_id}, plan_id={plan_id}): {e}")
        return None


def get_execution_run_plan(*, company_id: str, plan_id: str | None = None, plan_code: str | None = None) -> dict | None:
    """查询单个执行运行计划（按 id 或 plan_code）。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if plan_id:
                    cur.execute(
                        """
                        SELECT id, company_id, plan_code, plan_name, scheme_code,
                               schedule_type, schedule_expr, biz_date_offset,
                               input_bindings_json, channel_config_id,
                               owner_mapping_json, plan_meta_json,
                               is_enabled, created_by, created_at, updated_at
                        FROM execution_run_plans
                        WHERE company_id = %s
                          AND id = %s
                        LIMIT 1
                        """,
                        (company_id, plan_id),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, company_id, plan_code, plan_name, scheme_code,
                               schedule_type, schedule_expr, biz_date_offset,
                               input_bindings_json, channel_config_id,
                               owner_mapping_json, plan_meta_json,
                               is_enabled, created_by, created_at, updated_at
                        FROM execution_run_plans
                        WHERE company_id = %s
                          AND plan_code = %s
                        LIMIT 1
                        """,
                        (company_id, str(plan_code or "").strip()),
                    )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"查询 execution_run_plans 失败 (company_id={company_id}, plan_id={plan_id}, plan_code={plan_code}): {e}"
        )
        return None


def list_execution_run_plans(
    *,
    company_id: str,
    scheme_code: str | None = None,
    include_disabled: bool = True,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """查询执行运行计划列表。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT id, company_id, plan_code, plan_name, scheme_code,
                           schedule_type, schedule_expr, biz_date_offset,
                           input_bindings_json, channel_config_id,
                           owner_mapping_json, plan_meta_json,
                           is_enabled, created_by, created_at, updated_at
                    FROM execution_run_plans
                    WHERE company_id = %s
                """
                params: list[Any] = [company_id]
                if scheme_code:
                    sql += " AND scheme_code = %s"
                    params.append(scheme_code)
                if not include_disabled:
                    sql += " AND is_enabled = true"
                sql += " ORDER BY updated_at DESC LIMIT %s OFFSET %s"
                params.extend([limit, offset])
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(f"查询 execution_run_plans 列表失败 (company_id={company_id}, scheme_code={scheme_code}): {e}")
        return []


def create_execution_run(
    *,
    company_id: str,
    scheme_code: str,
    run_code: str = "",
    plan_code: str | None = None,
    scheme_type: str = "recon",
    trigger_type: str = "chat",
    entry_mode: str = "file",
    execution_status: str = "running",
    failed_stage: str = "",
    failed_reason: str = "",
    run_context_json: dict | None = None,
    source_snapshot_json: dict | None = None,
    subtasks_json: list[dict] | None = None,
    proc_result_json: dict | None = None,
    recon_result_summary_json: dict | None = None,
    artifacts_json: dict | None = None,
    anomaly_count: int = 0,
    started_at_now: bool = True,
    finished_at_now: bool = False,
) -> dict | None:
    """创建执行记录。"""
    conn_manager = get_conn()
    try:
        resolved_run_code = str(run_code or "").strip() or _generate_execution_code("run")
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO execution_runs (
                        company_id, run_code, scheme_code, plan_code, scheme_type,
                        trigger_type, entry_mode, execution_status,
                        failed_stage, failed_reason,
                        run_context_json, source_snapshot_json, subtasks_json,
                        proc_result_json, recon_result_summary_json, artifacts_json,
                        anomaly_count, started_at, finished_at
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s,
                        %s::jsonb, %s::jsonb, %s::jsonb,
                        %s::jsonb, %s::jsonb, %s::jsonb,
                        %s,
                        CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE NULL END,
                        CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE NULL END
                    )
                    RETURNING id, company_id, run_code, scheme_code, plan_code, scheme_type,
                              trigger_type, entry_mode, execution_status,
                              failed_stage, failed_reason,
                              run_context_json, source_snapshot_json, subtasks_json,
                              proc_result_json, recon_result_summary_json, artifacts_json,
                              anomaly_count, started_at, finished_at, created_at, updated_at
                    """,
                    (
                        company_id,
                        resolved_run_code,
                        scheme_code,
                        plan_code,
                        scheme_type,
                        trigger_type,
                        entry_mode,
                        execution_status,
                        failed_stage,
                        failed_reason,
                        psycopg2.extras.Json(run_context_json or {}),
                        psycopg2.extras.Json(source_snapshot_json or {}),
                        psycopg2.extras.Json(subtasks_json or []),
                        psycopg2.extras.Json(proc_result_json or {}),
                        psycopg2.extras.Json(recon_result_summary_json or {}),
                        psycopg2.extras.Json(artifacts_json or {}),
                        max(0, int(anomaly_count)),
                        started_at_now,
                        finished_at_now,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"创建 execution_runs 失败 (company_id={company_id}, scheme_code={scheme_code}): {e}")
        return None


def update_execution_run(
    *,
    company_id: str,
    run_id: str,
    execution_status: str | None = None,
    failed_stage: str | None = None,
    failed_reason: str | None = None,
    run_context_json: dict | None = None,
    source_snapshot_json: dict | None = None,
    subtasks_json: list[dict] | None = None,
    proc_result_json: dict | None = None,
    recon_result_summary_json: dict | None = None,
    artifacts_json: dict | None = None,
    anomaly_count: int | None = None,
    started_at_now: bool = False,
    finished_at_now: bool = False,
) -> dict | None:
    """更新执行记录。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE execution_runs
                    SET execution_status = COALESCE(%s, execution_status),
                        failed_stage = COALESCE(%s, failed_stage),
                        failed_reason = COALESCE(%s, failed_reason),
                        run_context_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN run_context_json
                            ELSE %s::jsonb
                        END,
                        source_snapshot_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN source_snapshot_json
                            ELSE %s::jsonb
                        END,
                        subtasks_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN subtasks_json
                            ELSE %s::jsonb
                        END,
                        proc_result_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN proc_result_json
                            ELSE %s::jsonb
                        END,
                        recon_result_summary_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN recon_result_summary_json
                            ELSE %s::jsonb
                        END,
                        artifacts_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN artifacts_json
                            ELSE %s::jsonb
                        END,
                        anomaly_count = COALESCE(%s, anomaly_count),
                        started_at = CASE WHEN %s THEN COALESCE(started_at, CURRENT_TIMESTAMP) ELSE started_at END,
                        finished_at = CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE finished_at END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                      AND company_id = %s
                    RETURNING id, company_id, run_code, scheme_code, plan_code, scheme_type,
                              trigger_type, entry_mode, execution_status,
                              failed_stage, failed_reason,
                              run_context_json, source_snapshot_json, subtasks_json,
                              proc_result_json, recon_result_summary_json, artifacts_json,
                              anomaly_count, started_at, finished_at, created_at, updated_at
                    """,
                    (
                        execution_status,
                        failed_stage,
                        failed_reason,
                        psycopg2.extras.Json(run_context_json) if run_context_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(run_context_json) if run_context_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(source_snapshot_json) if source_snapshot_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(source_snapshot_json) if source_snapshot_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(subtasks_json) if subtasks_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(subtasks_json) if subtasks_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(proc_result_json) if proc_result_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(proc_result_json) if proc_result_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(recon_result_summary_json) if recon_result_summary_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(recon_result_summary_json) if recon_result_summary_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(artifacts_json) if artifacts_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(artifacts_json) if artifacts_json is not None else psycopg2.extras.Json(None),
                        anomaly_count,
                        started_at_now,
                        finished_at_now,
                        run_id,
                        company_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 execution_runs 失败 (company_id={company_id}, run_id={run_id}): {e}")
        return None


def get_execution_run(*, company_id: str, run_id: str | None = None, run_code: str | None = None) -> dict | None:
    """查询单个执行记录（按 id 或 run_code）。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if run_id:
                    cur.execute(
                        """
                        SELECT id, company_id, run_code, scheme_code, plan_code, scheme_type,
                               trigger_type, entry_mode, execution_status,
                               failed_stage, failed_reason,
                               run_context_json, source_snapshot_json, subtasks_json,
                               proc_result_json, recon_result_summary_json, artifacts_json,
                               anomaly_count, started_at, finished_at, created_at, updated_at
                        FROM execution_runs
                        WHERE company_id = %s
                          AND id = %s
                        LIMIT 1
                        """,
                        (company_id, run_id),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, company_id, run_code, scheme_code, plan_code, scheme_type,
                               trigger_type, entry_mode, execution_status,
                               failed_stage, failed_reason,
                               run_context_json, source_snapshot_json, subtasks_json,
                               proc_result_json, recon_result_summary_json, artifacts_json,
                               anomaly_count, started_at, finished_at, created_at, updated_at
                        FROM execution_runs
                        WHERE company_id = %s
                          AND run_code = %s
                        LIMIT 1
                        """,
                        (company_id, str(run_code or "").strip()),
                    )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"查询 execution_runs 失败 (company_id={company_id}, run_id={run_id}, run_code={run_code}): {e}")
        return None


def list_execution_runs(
    *,
    company_id: str,
    scheme_code: str | None = None,
    plan_code: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """查询执行记录列表。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT id, company_id, run_code, scheme_code, plan_code, scheme_type,
                           trigger_type, entry_mode, execution_status,
                           failed_stage, failed_reason,
                           run_context_json, source_snapshot_json, subtasks_json,
                           proc_result_json, recon_result_summary_json, artifacts_json,
                           anomaly_count, started_at, finished_at, created_at, updated_at
                    FROM execution_runs
                    WHERE company_id = %s
                """
                params: list[Any] = [company_id]
                if scheme_code:
                    sql += " AND scheme_code = %s"
                    params.append(scheme_code)
                if plan_code:
                    sql += " AND plan_code = %s"
                    params.append(plan_code)
                sql += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
                params.extend([limit, offset])
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(
            f"查询 execution_runs 列表失败 (company_id={company_id}, scheme_code={scheme_code}, plan_code={plan_code}): {e}"
        )
        return []


def create_execution_run_exception(
    *,
    company_id: str,
    run_id: str,
    scheme_code: str,
    anomaly_key: str,
    anomaly_type: str,
    summary: str,
    detail_json: dict | None = None,
    owner_name: str = "",
    owner_identifier: str = "",
    owner_contact_json: dict | None = None,
    reminder_status: str = "pending",
    processing_status: str = "pending",
    fix_status: str = "pending",
    latest_feedback: str = "",
    feedback_json: dict | None = None,
    is_closed: bool = False,
) -> dict | None:
    """创建或幂等更新执行异常。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO execution_run_exceptions (
                        company_id, run_id, scheme_code, anomaly_key, anomaly_type,
                        summary, detail_json,
                        owner_name, owner_identifier, owner_contact_json,
                        reminder_status, processing_status, fix_status,
                        latest_feedback, feedback_json, is_closed
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s::jsonb,
                        %s, %s, %s::jsonb,
                        %s, %s, %s,
                        %s, %s::jsonb, %s
                    )
                    ON CONFLICT (run_id, anomaly_key)
                    DO UPDATE SET
                        anomaly_type = EXCLUDED.anomaly_type,
                        summary = EXCLUDED.summary,
                        detail_json = EXCLUDED.detail_json,
                        owner_name = CASE
                            WHEN EXCLUDED.owner_name <> '' THEN EXCLUDED.owner_name
                            ELSE execution_run_exceptions.owner_name
                        END,
                        owner_identifier = CASE
                            WHEN EXCLUDED.owner_identifier <> '' THEN EXCLUDED.owner_identifier
                            ELSE execution_run_exceptions.owner_identifier
                        END,
                        owner_contact_json = CASE
                            WHEN EXCLUDED.owner_contact_json <> '{}'::jsonb THEN EXCLUDED.owner_contact_json
                            ELSE execution_run_exceptions.owner_contact_json
                        END,
                        reminder_status = EXCLUDED.reminder_status,
                        processing_status = EXCLUDED.processing_status,
                        fix_status = EXCLUDED.fix_status,
                        latest_feedback = CASE
                            WHEN EXCLUDED.latest_feedback <> '' THEN EXCLUDED.latest_feedback
                            ELSE execution_run_exceptions.latest_feedback
                        END,
                        feedback_json = CASE
                            WHEN EXCLUDED.feedback_json <> '{}'::jsonb THEN EXCLUDED.feedback_json
                            ELSE execution_run_exceptions.feedback_json
                        END,
                        is_closed = EXCLUDED.is_closed,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id, company_id, run_id, scheme_code, anomaly_key, anomaly_type,
                              summary, detail_json,
                              owner_name, owner_identifier, owner_contact_json,
                              reminder_status, processing_status, fix_status,
                              latest_feedback, feedback_json, is_closed, created_at, updated_at
                    """,
                    (
                        company_id,
                        run_id,
                        scheme_code,
                        anomaly_key,
                        anomaly_type,
                        summary,
                        psycopg2.extras.Json(detail_json or {}),
                        owner_name,
                        owner_identifier,
                        psycopg2.extras.Json(owner_contact_json or {}),
                        reminder_status,
                        processing_status,
                        fix_status,
                        latest_feedback,
                        psycopg2.extras.Json(feedback_json or {}),
                        is_closed,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"创建 execution_run_exceptions 失败 (company_id={company_id}, run_id={run_id}, anomaly_key={anomaly_key}): {e}"
        )
        return None


def get_execution_run_exception(*, company_id: str, exception_id: str) -> dict | None:
    """查询单个执行异常。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, run_id, scheme_code, anomaly_key, anomaly_type,
                           summary, detail_json,
                           owner_name, owner_identifier, owner_contact_json,
                           reminder_status, processing_status, fix_status,
                           latest_feedback, feedback_json, is_closed, created_at, updated_at
                    FROM execution_run_exceptions
                    WHERE company_id = %s
                      AND id = %s
                    LIMIT 1
                    """,
                    (company_id, exception_id),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"查询 execution_run_exceptions 失败 (company_id={company_id}, exception_id={exception_id}): {e}")
        return None


def list_execution_run_exceptions(
    *,
    company_id: str,
    run_id: str,
    limit: int = 500,
    offset: int = 0,
) -> list[dict]:
    """按执行记录查询异常列表。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, run_id, scheme_code, anomaly_key, anomaly_type,
                           summary, detail_json,
                           owner_name, owner_identifier, owner_contact_json,
                           reminder_status, processing_status, fix_status,
                           latest_feedback, feedback_json, is_closed, created_at, updated_at
                    FROM execution_run_exceptions
                    WHERE company_id = %s
                      AND run_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (company_id, run_id, limit, offset),
                )
                rows = cur.fetchall()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(f"查询 execution_run_exceptions 列表失败 (company_id={company_id}, run_id={run_id}): {e}")
        return []


def update_execution_run_exception(
    *,
    company_id: str,
    exception_id: str,
    owner_name: str | None = None,
    owner_identifier: str | None = None,
    owner_contact_json: dict | None = None,
    reminder_status: str | None = None,
    processing_status: str | None = None,
    fix_status: str | None = None,
    latest_feedback: str | None = None,
    feedback_json: dict | None = None,
    is_closed: bool | None = None,
) -> dict | None:
    """更新执行异常状态。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE execution_run_exceptions
                    SET owner_name = COALESCE(%s, owner_name),
                        owner_identifier = COALESCE(%s, owner_identifier),
                        owner_contact_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN owner_contact_json
                            ELSE %s::jsonb
                        END,
                        reminder_status = COALESCE(%s, reminder_status),
                        processing_status = COALESCE(%s, processing_status),
                        fix_status = COALESCE(%s, fix_status),
                        latest_feedback = COALESCE(%s, latest_feedback),
                        feedback_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN feedback_json
                            ELSE %s::jsonb
                        END,
                        is_closed = COALESCE(%s, is_closed),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                      AND company_id = %s
                    RETURNING id, company_id, run_id, scheme_code, anomaly_key, anomaly_type,
                              summary, detail_json,
                              owner_name, owner_identifier, owner_contact_json,
                              reminder_status, processing_status, fix_status,
                              latest_feedback, feedback_json, is_closed, created_at, updated_at
                    """,
                    (
                        owner_name,
                        owner_identifier,
                        psycopg2.extras.Json(owner_contact_json) if owner_contact_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(owner_contact_json) if owner_contact_json is not None else psycopg2.extras.Json(None),
                        reminder_status,
                        processing_status,
                        fix_status,
                        latest_feedback,
                        psycopg2.extras.Json(feedback_json) if feedback_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(feedback_json) if feedback_json is not None else psycopg2.extras.Json(None),
                        is_closed,
                        exception_id,
                        company_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"更新 execution_run_exceptions 失败 (company_id={company_id}, exception_id={exception_id}): {e}"
        )
        return None
