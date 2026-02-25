"""
MCP 工具定义
"""
import json
import uuid
import os
import logging
from pathlib import Path
from typing import Dict, Any, List
from mcp import Tool
from .task_manager import TaskManager
from .config import UPLOAD_DIR, ALLOWED_EXTENSIONS, SCHEMA_DIR, RECONCILIATION_SCHEMAS_FILE, BASE_DIR, FINANCE_MCP_DIR
from .schema_loader import SchemaLoader
import re

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(FINANCE_MCP_DIR / 'reconciliation_mcp.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# 全局任务管理器
task_manager = TaskManager()


def load_json_with_comments(file_path: Path) -> Dict:
    """加载 JSON 文件（支持 JSON5 格式的注释）"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 移除多行注释 (/* ... */) - 先处理多行注释
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    
    # 移除单行注释 (// ...) - 但保留字符串中的 //
    lines = []
    in_string = False
    escape_next = False
    
    for line in content.split('\n'):
        new_line = []
        i = 0
        while i < len(line):
            char = line[i]
            
            if escape_next:
                new_line.append(char)
                escape_next = False
                i += 1
                continue
            
            if char == '\\':
                escape_next = True
                new_line.append(char)
                i += 1
                continue
            
            if char == '"':
                in_string = not in_string
                new_line.append(char)
                i += 1
                continue
            
            # 如果不在字符串中，遇到 // 则移除后面的内容
            if not in_string and char == '/' and i + 1 < len(line) and line[i + 1] == '/':
                break  # 移除该行剩余部分
            
            new_line.append(char)
            i += 1
        
        lines.append(''.join(new_line))
    
    content = '\n'.join(lines)
    
    return json.loads(content)


def create_tools() -> List[Tool]:
    """创建所有 MCP 工具"""
    return [
        Tool(
            name="reconciliation_start",
            description="开始对账任务。支持从 PostgreSQL 查询规则，或直接传入 rule_template（新建规则流程先对账再保存）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {
                        "type": "string",
                        "description": "JWT token，用于校验用户身份和规则权限"
                    },
                    "guest_token": {
                        "type": "string",
                        "description": "游客 token（与 auth_token 二选一）"
                    },
                    "rule_id": {
                        "type": "string",
                        "description": "规则 ID（与 rule_name、rule_template 三选一）"
                    },
                    "rule_name": {
                        "type": "string",
                        "description": "规则名称（与 rule_id、rule_template 三选一）"
                    },
                    "rule_template": {
                        "type": "object",
                        "description": "规则模板 JSON（新建规则流程直接传入，无需先保存）"
                    },
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要对账的文件路径列表"
                    }
                },
                "required": ["files"]
            }
        ),
        Tool(
            name="reconciliation_status",
            description="查询对账任务状态",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {
                        "type": "string",
                        "description": "JWT token，用于校验用户身份"
                    },
                    "task_id": {
                        "type": "string",
                        "description": "任务 ID"
                    }
                },
                "required": ["auth_token", "task_id"]
            }
        ),
        Tool(
            name="reconciliation_result",
            description="获取对账结果",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {
                        "type": "string",
                        "description": "JWT token，用于校验用户身份"
                    },
                    "task_id": {
                        "type": "string",
                        "description": "任务 ID"
                    }
                },
                "required": ["auth_token", "task_id"]
            }
        ),
        Tool(
            name="reconciliation_list_tasks",
            description="列出当前用户的所有对账任务",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {
                        "type": "string",
                        "description": "JWT token，用于校验用户身份"
                    }
                },
                "required": ["auth_token"]
            }
        ),
        Tool(
            name="file_upload",
            description="上传文件并保存到服务器，支持多个文件上传。返回上传文件的路径列表。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {
                        "type": "string",
                        "description": "JWT token，用于校验用户身份"
                    },
                    "files": {
                        "type": "array",
                        "description": "文件数组，每个元素包含 filename, content (base64编码)",
                        "items": {
                            "type": "object",
                            "properties": {
                                "filename": {
                                    "type": "string",
                                    "description": "文件名"
                                },
                                "content": {
                                    "type": "string",
                                    "description": "文件内容（base64编码）"
                                }
                            },
                            "required": ["filename", "content"]
                        }
                    }
                },
                "required": ["auth_token", "files"]
            }
        ),
        Tool(
            name="get_reconciliation",
            description="根据对账类型获取对账配置和回调地址",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {
                        "type": "string",
                        "description": "JWT token，用于校验用户身份"
                    },
                    "reconciliation_type": {
                        "type": "string",
                        "description": "对账类型中文名称，例如：直销对账"
                    }
                },
                "required": ["auth_token", "reconciliation_type"]
            }
        ),
        Tool(
            name="analyze_files",
            description="分析已上传的文件，返回文件的列信息、行数、样本数据和文件类型（business/finance）。需要先通过 file_upload 上传文件。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {
                        "type": "string",
                        "description": "JWT token，用于校验用户身份"
                    },
                    "file_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要分析的文件路径列表（由 file_upload 返回的路径）"
                    },
                    "original_filenames": {
                        "type": "object",
                        "description": "文件路径到原始文件名的映射（可选，用于纯数字文件名）",
                        "additionalProperties": {"type": "string"}
                    }
                },
                "required": ["auth_token", "file_paths"]
            }
        ),
        Tool(
            name="read_excel_sheets",
            description="读取Excel文件的所有sheet信息，返回每个sheet的名称、列名和样本数据。用于处理多sheet的Excel文件。",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Excel文件路径"
                    },
                    "sample_rows": {
                        "type": "integer",
                        "description": "每个sheet读取的样本行数（默认5行）",
                        "default": 5
                    }
                },
                "required": ["file_path"]
            }
        ),
        Tool(
            name="detect_file_complexity",
            description="检测上传文件的复杂度，判断是否需要智能分析处理（多sheet、非标准格式、多文件配对等）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "files": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "file_path": {"type": "string"},
                                "original_filename": {"type": "string"}
                            }
                        },
                        "description": "要检测的文件列表"
                    }
                },
                "required": ["files"]
            }
        ),
        # 注意：list/save/update/delete_reconciliation_rule 已移至 auth/tools.py
        # 由 auth 模块统一处理（带权限控制）
    ]


async def handle_tool_call(tool_name: str, arguments: Dict[str, Any]) -> Any:
    """处理工具调用"""
    
    if tool_name == "reconciliation_start":
        return await _reconciliation_start(arguments)
    
    elif tool_name == "reconciliation_status":
        return await _reconciliation_status(arguments)
    
    elif tool_name == "reconciliation_result":
        return await _reconciliation_result(arguments)
    
    elif tool_name == "reconciliation_list_tasks":
        return await _reconciliation_list_tasks(arguments)
    
    elif tool_name == "file_upload":
        return await _file_upload(arguments)
    
    elif tool_name == "get_reconciliation":
        return await _get_reconciliation(arguments)
    
    elif tool_name == "analyze_files":
        return await _analyze_files(arguments)

    elif tool_name == "read_excel_sheets":
        return await _read_excel_sheets(arguments)

    elif tool_name == "detect_file_complexity":
        return await _detect_file_complexity(arguments)

    else:
        return {"error": f"未知的工具: {tool_name}"}


async def _reconciliation_start(args: Dict) -> Dict:
    """开始对账任务 - 从 PostgreSQL 读取规则和 schema"""
    try:
        from auth.jwt_utils import get_user_from_token
        from auth import db as auth_db
        
        # 1. 验证 token 和获取用户信息 - 支持 auth_token 或 guest_token
        auth_token = args.get("auth_token", "")
        guest_token = args.get("guest_token", "")
        
        user_info = None
        if auth_token:
            user_info = get_user_from_token(auth_token)
            if not user_info:
                return {"error": "token 无效或已过期"}
        elif guest_token:
            # 验证游客token
            try:
                token_info = auth_db.verify_guest_token(guest_token)
            except Exception as e:
                logger.error(f"验证游客token失败: {e}")
                return {"error": f"验证游客token失败: {e}"}
            
            if not token_info:
                return {"error": "无效的游客token"}
            if not token_info.get("valid", False):
                return {"error": token_info.get("error", "游客token已过期")}
            
            # 检查使用次数
            if token_info.get("usage_count", 0) >= token_info.get("max_usage", 3):
                return {"error": "游客使用次数已达上限，请登录后继续使用", "code": "GUEST_LIMIT_REACHED"}
        else:
            return {"error": "缺少 auth_token 或 guest_token 参数"}
        
        # 2. 获取规则：rule_template（直接传入）或 rule_id/rule_name（从 DB 查询）
        rule_id = args.get("rule_id")
        rule_name = args.get("rule_name")
        rule_template_arg = args.get("rule_template")
        files = args.get("files", [])
        
        if not rule_id and not rule_name and not rule_template_arg:
            return {"error": "缺少 rule_id、rule_name 或 rule_template 参数"}
        
        if not files:
            return {"error": "缺少 files 参数"}
        
        schema = None
        rule = None  # rule_template 路径下不查 DB，rule 为空
        if rule_template_arg:
            # 直接使用传入的 rule_template（新建规则流程：先对账再保存）
            if isinstance(rule_template_arg, str):
                try:
                    schema = json.loads(rule_template_arg)
                except json.JSONDecodeError as e:
                    return {"error": f"rule_template 格式错误: {str(e)}"}
            else:
                schema = rule_template_arg
            logger.info("使用直接传入的 rule_template 执行对账（新建规则流程）")
        else:
            # 3. 从 PostgreSQL 查询规则
            rule = None
            if rule_id:
                rule = auth_db.get_rule_by_id(rule_id)
            else:
                rule = auth_db.get_rule_by_name(rule_name)
            
            if not rule:
                return {"error": f"规则不存在: {rule_id or rule_name}"}
            
            # 4. 验证用户是否有权限使用此规则
            rule_visibility = rule.get("visibility", "private")
            rule_created_by = rule.get("created_by")
            rule_company_id = rule.get("company_id")
            rule_department_id = rule.get("department_id")
            
            if not user_info:
                if rule_visibility in ["company", "department", "public"]:
                    logger.info(f"游客模式：允许使用规则 {rule.get('name')}")
                elif rule_created_by:
                    logger.info(f"游客模式：允许使用创建者的规则 {rule.get('name')}")
            else:
                user_id = user_info.get("user_id")
                user_company_id = user_info.get("company_id")
                user_department_id = user_info.get("department_id")
                user_role = user_info.get("role")
                has_access = False
                if str(rule_created_by) == user_id:
                    has_access = True
                elif rule_visibility == "company" and str(rule_company_id) == str(user_company_id):
                    has_access = True
                elif rule_visibility == "department" and str(rule_department_id) == str(user_department_id):
                    has_access = True
                elif user_role == "admin":
                    has_access = True
                if not has_access:
                    return {"error": f"无权使用该规则: {rule.get('name')}"}
            
            rule_template = rule.get("rule_template")
            if not rule_template:
                return {"error": f"规则缺少 rule_template: {rule.get('name')}"}
            if isinstance(rule_template, str):
                try:
                    schema = json.loads(rule_template)
                except json.JSONDecodeError as e:
                    return {"error": f"规则 rule_template 格式错误: {str(e)}"}
            else:
                schema = rule_template
        
        # 6. 验证 schema
        try:
            SchemaLoader.validate_schema(schema)
        except Exception as e:
            return {"error": f"规则 schema 验证失败: {str(e)}"}
        
        # 7. 验证文件并转换为绝对路径
        absolute_files = []
        for file_path in files:
            # 将相对路径转换为绝对路径
            if file_path.startswith('/uploads/'):
                # 去掉开头的 / 并与 FINANCE_MCP_DIR 拼接（因为 uploads 在 finance-mcp 目录下）
                abs_path = FINANCE_MCP_DIR / file_path.lstrip('/')
            elif file_path.startswith('uploads/'):
                # 相对路径，直接与 FINANCE_MCP_DIR 拼接
                abs_path = FINANCE_MCP_DIR / file_path
            elif str(file_path).startswith(str(UPLOAD_DIR)):
                # 如果已经是 UPLOAD_DIR 的绝对路径
                abs_path = Path(file_path)
            else:
                # 假设是绝对路径或其他格式
                abs_path = Path(file_path)
                # 如果不是绝对路径，尝试相对 UPLOAD_DIR
                if not abs_path.is_absolute():
                    abs_path = UPLOAD_DIR / file_path
            
            if not abs_path.exists():
                return {"error": f"文件不存在: {file_path} (解析路径: {abs_path})"}
            
            absolute_files.append(str(abs_path))
        
        # 8. 获取 callback_url（可选，从规则中获取或从参数中获取）
        callback_url_arg = args.get("callback_url", "")
        rule_id_for_callback = rule.get("id") if rule else None
        rule_name_for_msg = rule.get("name") if rule else (rule_name or schema.get("description", "新规则"))
        callback_url = callback_url_arg or (rule.get("callback_url", "") if rule else "")
        
        # 9. 创建任务（使用绝对路径和schema）
        task_id = await task_manager.create_task(schema, absolute_files, callback_url if callback_url else None)
        
        # 记录日志（区分游客和登录用户）
        if user_info:
            logger.info(f"规则对账任务已创建: rule={rule_name_for_msg} (id={rule_id or rule_name}), task_id={task_id}, user={user_info.get('username', 'unknown')}")
        else:
            logger.info(f"游客模式 - 规则对账任务已创建: rule={rule_name_for_msg} (id={rule_id or rule_name}), task_id={task_id}")
        
        return {
            "task_id": task_id,
            "status": "pending",
            "rule_id": rule_id_for_callback or rule_id,
            "rule_name": rule_name_for_msg,
            "message": f"对账任务已创建，使用规则 '{rule_name_for_msg}'，正在处理中"
        }
    
    except Exception as e:
        logger.error(f"reconciliation_start 执行失败: {str(e)}", exc_info=True)
        return {"error": f"创建任务失败: {str(e)}"}


async def _reconciliation_status(args: Dict) -> Dict:
    """查询任务状态"""
    task_id = args.get("task_id")
    
    task = await task_manager.get_task(task_id)
    if not task:
        return {"error": f"任务不存在: {task_id}"}
    
    result = {
        "task_id": task.task_id,
        "status": task.status.value,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat()
    }
    # 任务失败时返回错误信息，便于前端展示
    if task.status.value in ("failed", "error") and task.result and getattr(task.result, "error", None):
        result["error"] = task.result.error
    return result


async def _reconciliation_result(args: Dict) -> Dict:
    """获取对账结果"""
    task_id = args.get("task_id")
    
    task = await task_manager.get_task(task_id)
    if not task:
        return {"error": f"任务不存在: {task_id}"}
    
    if task.status != "completed" and task.status.value != "completed":
        return {
            "task_id": task.task_id,
            "status": task.status.value,
            "message": "任务尚未完成"
        }
    
    if task.result:
        return task.result.to_dict()
    else:
        return {"error": "结果不可用"}


async def _reconciliation_list_tasks(args: Dict) -> Dict:
    """列出所有任务"""
    tasks = await task_manager.list_tasks()
    
    return {
        "tasks": [
            {
                "task_id": task.task_id,
                "status": task.status.value,
                "created_at": task.created_at.isoformat(),
                "updated_at": task.updated_at.isoformat()
            }
            for task in tasks
        ]
    }


async def _file_upload(args: Dict) -> Dict:
    """接收文件并保存（支持多文件，content 为 base64 编码）"""
    try:
        import base64
        from datetime import datetime
        import chardet
        from security_utils import validate_filename, sanitize_path

        files = args.get("files", [])
        if not files:
            return {"error": "files 参数不能为空"}

        uploaded_files = []
        errors = []

        # 创建按日期分类的上传目录
        now = datetime.now()
        date_dir = UPLOAD_DIR / str(now.year) / str(now.month) / str(now.day)
        date_dir.mkdir(parents=True, exist_ok=True)

        for idx, file_obj in enumerate(files):
            try:
                # 提取文件信息
                filename = file_obj.get("filename")
                content_b64 = file_obj.get("content")

                # 验证必填字段
                if not filename:
                    errors.append({
                        "index": idx,
                        "error": "缺少 filename 字段"
                    })
                    continue

                if not content_b64:
                    errors.append({
                        "index": idx,
                        "filename": filename,
                        "error": "缺少 content 字段"
                    })
                    continue

                # Validate filename to prevent path traversal attacks
                if not validate_filename(filename):
                    errors.append({
                        "index": idx,
                        "filename": filename,
                        "error": "非法文件名，可能存在安全风险"
                    })
                    continue

                # 验证文件扩展名
                file_ext = Path(filename).suffix.lower()
                if file_ext not in ALLOWED_EXTENSIONS:
                    errors.append({
                        "index": idx,
                        "filename": filename,
                        "error": f"不支持的文件类型: {file_ext}"
                    })
                    continue

                # 解码 base64
                try:
                    file_content = base64.b64decode(content_b64)
                except Exception as e:
                    errors.append({
                        "index": idx,
                        "filename": filename,
                        "error": f"base64 解码失败: {str(e)}"
                    })
                    continue

                # Check file size limit
                max_file_size = int(os.getenv("MAX_FILE_SIZE", str(100 * 1024 * 1024)))  # 100MB default
                if len(file_content) > max_file_size:
                    errors.append({
                        "index": idx,
                        "filename": filename,
                        "error": f"文件大小超过限制 ({max_file_size} bytes)"
                    })
                    continue

                # 保存文件到日期目录
                # 始终添加时间戳，确保文件名唯一
                timestamp = datetime.now().strftime("%H%M%S")
                safe_filename = Path(filename).name  # 只取文件名，去除路径
                name_parts = safe_filename.rsplit('.', 1)
                if len(name_parts) == 2:
                    safe_filename = f"{name_parts[0]}_{timestamp}.{name_parts[1]}"
                else:
                    safe_filename = f"{safe_filename}_{timestamp}"
                
                # Sanitize the file path to prevent directory traversal
                file_path = sanitize_path(date_dir, safe_filename)
                if file_path is None:
                    errors.append({
                        "index": idx,
                        "filename": filename,
                        "error": "非法文件路径，可能存在安全风险"
                    })
                    continue

                # 对文本文件（CSV、TXT）进行编码转换，确保保存为 UTF-8
                text_extensions = ['.csv', '.txt', '.tsv']
                if file_ext in text_extensions:
                    try:
                        logger.info(f"[编码转换] 开始处理文件: {filename}")
                        logger.info(f"[编码转换] 文件扩展名: {file_ext}")
                        logger.info(f"[编码转换] 原始文件大小: {len(file_content)} 字节")

                        # 检测原始编码
                        detected = chardet.detect(file_content)
                        encoding = detected.get('encoding', 'utf-8')
                        confidence = detected.get('confidence', 0)

                        logger.info(f"[编码转换] 检测到编码: {encoding}, 置信度: {confidence:.2%}")

                        # 如果检测不出编码或置信度低，尝试常见编码
                        if not encoding or confidence < 0.7:
                            logger.info(f"[编码转换] 置信度低，尝试常见编码...")
                            for try_encoding in ['utf-8', 'gbk', 'gb2312', 'gb18030', 'latin1']:
                                try:
                                    file_content.decode(try_encoding)
                                    encoding = try_encoding
                                    logger.info(f"[编码转换] 使用编码: {encoding}")
                                    break
                                except (UnicodeDecodeError, LookupError):
                                    continue

                        # 解码后重新编码为 UTF-8 保存
                        if encoding:
                            try:
                                text_content = file_content.decode(encoding)
                                file_content = text_content.encode('utf-8-sig')  # 使用 UTF-8 with BOM
                                logger.info(f"[编码转换] ✅ 成功转换: {encoding} → UTF-8-sig")
                                logger.info(f"[编码转换] 转换后大小: {len(file_content)} 字节")
                            except (UnicodeDecodeError, LookupError) as e:
                                # 如果解码失败，保持原样
                                logger.error(f"[编码转换] ❌ 解码失败: {str(e)}")
                        else:
                            logger.warning(f"[编码转换] ⚠️ 未检测到编码，保持原样")
                    except Exception as e:
                        # 编码转换失败，保持原样
                        logger.error(f"[编码转换] ❌ 转换异常 ({filename}): {str(e)}")

                # 保存文件
                with open(file_path, 'wb') as f:
                    f.write(file_content)

                # 构建相对路径（相对于 UPLOAD_DIR）
                relative_path = file_path.relative_to(UPLOAD_DIR.parent)

                # 添加到成功列表
                uploaded_files.append({
                    "original_filename": filename,
                    "file_path": f"/{relative_path.as_posix()}"
                })

            except Exception as e:
                errors.append({
                    "index": idx,
                    "filename": file_obj.get("filename", "unknown"),
                    "error": f"处理失败: {str(e)}"
                })

        # 返回结果
        if not uploaded_files:
            return {
                "success": False,
                "uploaded_count": 0,
                "uploaded_files": [],
                "errors": errors
            }

        result = {
            "success": True,
            "uploaded_count": len(uploaded_files),
            "uploaded_files": uploaded_files
        }

        if errors:
            result["errors"] = errors
            result["error_count"] = len(errors)

        return result

    except Exception as e:
        return {"error": f"文件上传失败: {str(e)}"}


def _guess_file_extension(content: bytes) -> str:
    """根据文件内容推断文件扩展名"""
    # 检查文件头（魔术数字）
    if len(content) < 4:
        return ".csv"  # 默认为 CSV
    
    # Excel (xlsx) - PK\x03\x04
    if content[:4] == b'PK\x03\x04':
        # 进一步检查是否是 xlsx
        if b'xl/' in content[:2000] or b'[Content_Types].xml' in content[:2000]:
            return ".xlsx"
        return ".xlsx"  # 默认为 xlsx
    
    # Excel (xls) - D0CF11E0A1B11AE1
    if len(content) >= 8 and content[:8] == b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1':
        return ".xls"
    
    # CSV - 尝试检测是否是文本（检查更多内容）
    try:
        # 尝试解码前 5000 字节
        test_content = content[:5000]
        decoded = test_content.decode('utf-8')
        # 检查是否包含常见的 CSV 特征
        if ',' in decoded or '\t' in decoded or '\n' in decoded:
            return ".csv"
        return ".txt"
    except:
        try:
            test_content = content[:5000]
            decoded = test_content.decode('gbk')
            if ',' in decoded or '\t' in decoded or '\n' in decoded:
                return ".csv"
            return ".txt"
        except:
            pass
    
    # 默认返回 CSV（因为对账系统主要处理 CSV/Excel）
    return ".csv"



async def _get_reconciliation(args: Dict) -> Dict:
    """根据对账类型获取对账配置"""
    try:
        reconciliation_type = args.get("reconciliation_type")
        
        if not reconciliation_type:
            return {
                "schema": {},
                "callback_url": "",
                "error": "缺少 reconciliation_type 参数"
            }
        
        # 读取配置文件
        if not RECONCILIATION_SCHEMAS_FILE.exists():
            return {
                "schema": {},
                "callback_url": "",
                "error": f"配置文件不存在: {RECONCILIATION_SCHEMAS_FILE}"
            }
        
        config = load_json_with_comments(RECONCILIATION_SCHEMAS_FILE)
        
        # 查找匹配的类型
        types = config.get("types", [])
        matched_type = None
        
        for type_config in types:
            if type_config.get("name_cn") == reconciliation_type:
                matched_type = type_config
                break
        
        if not matched_type:
            # 没有匹配到，返回空结构
            return {
                "schema": {},
                "callback_url": ""
            }
        
        # 获取 schema_path 和 callback_url
        schema_path_config = matched_type.get("schema_path")
        callback_url = matched_type.get("callback_url", "")
        type_key = matched_type.get("type_key")
        
        if not schema_path_config:
            return {
                "schema": {},
                "callback_url": callback_url,
                "error": f"配置缺少 schema_path: {reconciliation_type}"
            }
        
        # 读取 schema 文件
        # schema_path 格式: /schemas/direct_sales_schema.json 或 schemas/direct_sales_schema.json
        if schema_path_config.startswith('/'):
            # 绝对路径，去掉开头的 / 并与 BASE_DIR 拼接
            schema_path = BASE_DIR / schema_path_config.lstrip('/')
        elif schema_path_config.startswith('schemas/'):
            # 相对路径，与 BASE_DIR 拼接
            schema_path = BASE_DIR / schema_path_config
        else:
            # 只有文件名，与 SCHEMA_DIR 拼接
            schema_path = SCHEMA_DIR / schema_path_config
        
        if not schema_path.exists():
            return {
                "schema": {},
                "callback_url": callback_url,
                "error": f"Schema 文件不存在: {schema_path}"
            }
        
        schema = load_json_with_comments(schema_path)
        
        # 返回新的结构：schema 和 callback_url 分离
        return {
            "schema": schema,
            "callback_url": callback_url
        }
    
    except Exception as e:
        return {
            "schema": {},
            "callback_url": "",
            "error": f"获取对账配置失败: {str(e)}"
        }


async def _analyze_files(args: Dict) -> Dict:
    """分析已上传的文件，返回文件列信息、行数、样本数据和文件类型判断"""
    try:
        import pandas as pd
        import chardet
        import json
        import os
        from langchain_openai import ChatOpenAI
        
        file_paths = args.get("file_paths", [])
        if not file_paths:
            return {"error": "file_paths 参数不能为空"}
        
        # 获取原始文件名映射（如果提供）
        original_filenames_map = args.get("original_filenames", {})
        
        analyses = []
        
        # 第一步：读取每个文件的基本信息
        for file_path in file_paths:
            # 转换为绝对路径
            if file_path.startswith("/"):
                full_path = FINANCE_MCP_DIR / file_path.lstrip("/")
            else:
                full_path = FINANCE_MCP_DIR / file_path
            
            # 调试日志：记录文件路径信息
            logger.info(f"analyze_files - 处理文件: file_path={file_path}, full_path={full_path}, full_path.name={full_path.name}")
            
            # 验证文件是否存在
            if not full_path.exists():
                analyses.append({
                    "filename": Path(file_path).name,
                    "file_path": file_path,
                    "error": f"文件不存在: {file_path}"
                })
                continue
            
            # 验证文件扩展名
            file_ext = full_path.suffix.lower()
            if file_ext not in ALLOWED_EXTENSIONS:
                analyses.append({
                    "filename": full_path.name,
                    "file_path": file_path,
                    "error": f"不支持的文件类型: {file_ext}"
                })
                continue
            
            # 读取文件
            try:
                if file_ext == ".csv":
                    # CSV 文件，检测编码
                    raw = full_path.read_bytes()
                    det = chardet.detect(raw[:10000])
                    enc = det.get("encoding") or "utf-8"
                    df = pd.read_csv(full_path, encoding=enc, index_col=False)
                else:
                    # Excel 文件
                    df = pd.read_excel(full_path, index_col=False)
                
                # 提取样本数据
                sample = df.head(5).fillna("").to_dict(orient="records")
                safe_sample = []
                for row in sample:
                    safe_sample.append({k: str(v) for k, v in row.items()})
                
                # 从文件路径中提取原始文件名（去掉时间戳后缀）
                # 支持多种时间戳格式：
                # - filename_163045.csv → filename.csv (HHMMSS)
                # - 1767597466118.csv → 纯数字文件名，从 original_filenames_map 获取或使用文件扩展名模式
                # - filename_20260105152012277_0.csv → filename.csv (带日期时间戳)
                original_name = full_path.name
                import re
                
                # 首先检查是否提供了原始文件名映射
                if file_path in original_filenames_map:
                    original_name = original_filenames_map[file_path]
                    logger.info(f"使用提供的原始文件名: {original_name}")
                else:
                    # 尝试匹配各种时间戳格式
                    # 1. _HHMMSS 格式（6位数字）
                    match = re.match(r'(.+)_(\d{6})(\.\w+)$', original_name)
                    if match:
                        original_name = match.group(1) + match.group(3)
                    else:
                        # 2. 纯数字文件名（可能是时间戳，如 1767597466118.csv）
                        # 对于纯数字文件名，无法提取原始文件名，使用文件扩展名模式
                        if re.match(r'^\d+\.\w+$', original_name):
                            # 纯数字文件名，使用文件扩展名模式（如 *.csv）
                            file_ext = full_path.suffix
                            original_name = f"*{file_ext}"  # 使用通配符模式
                            logger.warning(f"纯数字文件名 {full_path.name}，使用扩展名模式: {original_name}")
                        else:
                            # 3. 带日期时间戳的格式：filename_YYYYMMDDHHMMSSmmm_0.ext
                            match = re.match(r'(.+?)_(\d{17})_\d+(\.\w+)$', original_name)
                            if match:
                                original_name = match.group(1) + match.group(3)
                            else:
                                # 4. 其他格式，尝试提取基础文件名（去掉最后的数字后缀）
                                # 例如：filename_12345.csv → filename.csv
                                match = re.match(r'(.+?)_\d+(\.\w+)$', original_name)
                                if match:
                                    original_name = match.group(1) + match.group(2)
                
                analysis_result = {
                    "filename": full_path.name,  # 系统文件名（带时间戳）
                    "original_filename": original_name,  # 原始文件名（不带时间戳）
                    "file_path": file_path,
                    "columns": list(df.columns),
                    "row_count": len(df),
                    "sample_data": safe_sample,
                    "guessed_source": None  # 稍后由 LLM 填充
                }
                # 调试日志：记录 analyze_files 返回的数据
                logger.info(f"analyze_files - 返回数据: filename={analysis_result['filename']}, original_filename={analysis_result['original_filename']}, file_path={file_path}")
                analyses.append(analysis_result)
                
            except Exception as e:
                analyses.append({
                    "filename": full_path.name,
                    "file_path": file_path,
                    "error": f"文件读取失败: {str(e)}"
                })
        
        # 第二步：使用 LLM 判断文件类型
        valid_analyses = [a for a in analyses if "error" not in a]
        if valid_analyses:
            try:
                # 构建 prompt
                files_desc = []
                for i, a in enumerate(valid_analyses):
                    cols_str = ", ".join(a.get("columns", [])[:20])
                    sample_str = ""
                    for row in a.get("sample_data", [])[:2]:
                        sample_str += "    " + str(row) + "\n"
                    files_desc.append(
                        f"文件{i+1}: {a['filename']}\n"
                        f"  列名: {cols_str}\n"
                        f"  行数: {a.get('row_count', 0)}\n"
                        f"  示例数据:\n{sample_str}"
                    )
                
                prompt = (
                    "你是一个财务数据分析专家。以下是用户上传的文件信息，"
                    "请判断每个文件属于哪种数据源类型。\n\n"
                    "类型说明：\n"
                    "- business: 业务数据（如订单流水、销售记录、交易明细等，通常包含订单号、商品、销售额等字段）\n"
                    "- finance: 财务数据（如财务账单、对账单、银行流水、发票等，通常包含财务科目、借贷金额等字段）\n\n"
                    "📖 分析策略提示：\n"
                    "- 优先根据列名判断（如：订单号、商品名→business；科目、借贷方向→finance）\n"
                    "- 参考样本数据特征（业务数据通常有SKU/商品信息，财务数据有会计科目/凭证号）\n"
                    "- 文件名也可作为辅助判断依据\n"
                    "- 如果同时包含业务和财务特征，优先判断为主要特征更明显的类型\n\n"
                    + "\n".join(files_desc)
                    + "\n\n请严格按以下 JSON 格式回复，不要添加其他内容：\n"
                    '{"results": [{"filename": "文件名", "source": "business 或 finance", "reason": "简短理由"}]}'
                )
                
                # 调用 LLM（使用环境变量配置）
                llm_provider = os.getenv("LLM_PROVIDER", "deepseek").lower()
                
                if llm_provider == "deepseek":
                    api_key = os.getenv("DEEPSEEK_API_KEY", "")
                    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
                    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
                elif llm_provider == "qwen":
                    api_key = os.getenv("QWEN_API_KEY", "")
                    base_url = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
                    model = os.getenv("QWEN_MODEL", "qwen-plus")
                else:  # openai
                    api_key = os.getenv("OPENAI_API_KEY", "")
                    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
                    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
                
                if not api_key:
                    logger.warning(f"LLM API Key 未配置 ({llm_provider})，跳过文件类型判断")
                    return {
                        "success": True,
                        "analyses": analyses
                    }
                
                llm = ChatOpenAI(
                    temperature=0.1,
                    model=model,
                    api_key=api_key,
                    base_url=base_url
                )
                resp = llm.invoke(prompt)
                content = resp.content.strip()
                
                # 提取 JSON
                if "```" in content:
                    import re
                    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
                    if m:
                        content = m.group(1)
                
                parsed = json.loads(content)
                results = parsed.get("results", [])
                
                # 将结果写回 analyses
                result_map = {r["filename"]: {"source": r["source"], "reason": r.get("reason", "")} for r in results}
                for a in valid_analyses:
                    if a["filename"] in result_map:
                        a["guessed_source"] = result_map[a["filename"]]["source"]
                        a["source_reason"] = result_map[a["filename"]]["reason"]
                        # 设置置信度（基于LLM识别的确定性，这里统一设为0.85）
                        a["confidence"] = 0.85
            
            except Exception as e:
                logger.warning(f"LLM 文件类型判断失败: {e}")
                # 不影响主流程，只是 guessed_source 为 None
        
        return {
            "success": True,
            "analyses": analyses
        }
    
    except Exception as e:
        logger.error(f"文件分析失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"文件分析失败: {str(e)}"
        }

# ══════════════════════════════════════════════════════════════════════════════
# 智能文件分析工具
# ══════════════════════════════════════════════════════════════════════════════

async def _read_excel_sheets(args: Dict) -> Dict:
    """读取Excel文件的所有sheet信息"""
    try:
        import pandas as pd
        from pathlib import Path

        file_path = args.get("file_path", "")
        sample_rows = args.get("sample_rows", 5)

        if not file_path:
            return {"error": "缺少file_path参数"}

        # 转换为绝对路径
        if file_path.startswith("/"):
            full_path = FINANCE_MCP_DIR / file_path.lstrip("/")
        else:
            full_path = FINANCE_MCP_DIR / file_path

        if not full_path.exists():
            return {"error": f"文件不存在: {file_path}"}

        # 检查是否是Excel文件
        file_ext = full_path.suffix.lower()
        if file_ext not in [".xlsx", ".xls"]:
            return {"error": f"不是Excel文件: {file_ext}"}

        # 读取所有sheet
        excel_file = pd.ExcelFile(full_path)
        sheets_info = []

        for sheet_name in excel_file.sheet_names:
            try:
                df = pd.read_excel(full_path, sheet_name=sheet_name, nrows=sample_rows)

                # 提取样本数据，确保所有值都转换为字符串（避免大整数序列化问题）
                sample = df.head(sample_rows).fillna("").to_dict(orient="records")
                safe_sample = []
                for row in sample:
                    safe_sample.append({k: str(v) for k, v in row.items()})

                # 提取信息
                sheet_info = {
                    "sheet_name": sheet_name,
                    "columns": [str(col) for col in df.columns],  # 确保列名也是字符串
                    "row_count": int(len(df)),  # 确保是标准int
                    "sample_data": safe_sample
                }
                sheets_info.append(sheet_info)
            except Exception as e:
                sheets_info.append({
                    "sheet_name": sheet_name,
                    "error": f"读取失败: {str(e)}"
                })

        return {
            "success": True,
            "file_path": file_path,
            "sheet_count": len(excel_file.sheet_names),
            "sheets": sheets_info
        }

    except Exception as e:
        logger.error(f"读取Excel sheets失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"读取失败: {str(e)}"
        }


async def _detect_file_complexity(args: Dict) -> Dict:
    """检测文件复杂度"""
    try:
        import pandas as pd
        from pathlib import Path

        files = args.get("files", [])
        if not files:
            return {"error": "缺少files参数"}

        complexity_info = {
            "file_count": len(files),
            "multi_sheet": False,
            "multi_sheet_files": [],
            "non_standard": False,
            "non_standard_files": [],
            "complexity_level": "simple"  # simple, medium, complex
        }

        # 检查每个文件
        for file in files:
            file_path = file.get("file_path", "")
            if not file_path:
                continue

            # 转换为绝对路径
            if file_path.startswith("/"):
                full_path = FINANCE_MCP_DIR / file_path.lstrip("/")
            else:
                full_path = FINANCE_MCP_DIR / file_path

            if not full_path.exists():
                continue

            file_ext = full_path.suffix.lower()

            # 检查是否是多sheet的Excel
            if file_ext in [".xlsx", ".xls"]:
                try:
                    excel_file = pd.ExcelFile(full_path)
                    if len(excel_file.sheet_names) > 1:
                        complexity_info["multi_sheet"] = True
                        complexity_info["multi_sheet_files"].append({
                            "file_path": file_path,
                            "sheet_count": len(excel_file.sheet_names),
                            "sheet_names": excel_file.sheet_names
                        })

                    # 检查第一个sheet是否有非标准格式迹象
                    df = pd.read_excel(full_path, sheet_name=0, nrows=10)

                    # 检测非标准格式的简单启发式规则
                    # 1. 前几行全空
                    # 2. 列名包含大量Unnamed
                    # 3. 第一行不是列名（包含数字数据）

                    unnamed_count = sum(1 for col in df.columns if str(col).startswith("Unnamed"))
                    if unnamed_count > len(df.columns) * 0.3:  # 超过30%的列是Unnamed
                        complexity_info["non_standard"] = True
                        complexity_info["non_standard_files"].append({
                            "file_path": file_path,
                            "reason": "检测到大量未命名列，可能有合并单元格"
                        })

                    # 检查前3行是否有大量空值
                    if len(df) >= 3:
                        null_ratio = df.iloc[:3].isnull().sum().sum() / (3 * len(df.columns))
                        if null_ratio > 0.5:  # 超过50%为空
                            complexity_info["non_standard"] = True
                            if file_path not in [f["file_path"] for f in complexity_info["non_standard_files"]]:
                                complexity_info["non_standard_files"].append({
                                    "file_path": file_path,
                                    "reason": "检测到前几行大量空值，可能有注释行"
                                })

                except Exception as e:
                    logger.warning(f"检测文件复杂度时出错: {file_path}, {e}")

        # 判断复杂度等级
        if len(files) > 2:
            complexity_info["complexity_level"] = "complex"
        elif complexity_info["multi_sheet"] or complexity_info["non_standard"]:
            complexity_info["complexity_level"] = "medium"
        else:
            complexity_info["complexity_level"] = "simple"

        return {
            "success": True,
            **complexity_info
        }

    except Exception as e:
        logger.error(f"检测文件复杂度失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"检测失败: {str(e)}"
        }


# 注意：数据库操作工具（list/save/update/delete_reconciliation_rule）
# 已移至 auth/tools.py，由认证模块统一管理
