"""
MCP 工具定义
"""
import json
import uuid
from pathlib import Path
from typing import Dict, Any, List
from mcp import Tool
from .task_manager import TaskManager
from .config import UPLOAD_DIR, ALLOWED_EXTENSIONS, SCHEMA_DIR, RECONCILIATION_SCHEMAS_FILE
from .schema_loader import SchemaLoader


# 全局任务管理器
task_manager = TaskManager()


def create_tools() -> List[Tool]:
    """创建所有 MCP 工具"""
    return [
        Tool(
            name="reconciliation_start",
            description="开始对账任务。根据对账类型自动获取配置，系统会异步执行对账并返回任务 ID。",
            inputSchema={
                "type": "object",
                "properties": {
                    "reconciliation_type": {
                        "type": "string",
                        "description": "对账类型中文名称，例如：直销对账"
                    },
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要对账的文件路径列表"
                    }
                },
                "required": ["reconciliation_type", "files"]
            }
        ),
        Tool(
            name="reconciliation_status",
            description="查询对账任务状态",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "任务 ID"
                    }
                },
                "required": ["task_id"]
            }
        ),
        Tool(
            name="reconciliation_result",
            description="获取对账结果",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "任务 ID"
                    }
                },
                "required": ["task_id"]
            }
        ),
        Tool(
            name="reconciliation_list_tasks",
            description="列出所有对账任务",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="file_upload",
            description="从 Dify 下载文件并保存到服务器，支持多个文件上传。返回上传文件的路径列表。",
            inputSchema={
                "type": "object",
                "properties": {
                    "files": {
                        "type": "array",
                        "description": "文件数组，每个元素包含 filename, size, related_id, mime_type",
                        "items": {
                            "type": "object",
                            "properties": {
                                "filename": {
                                    "type": "string",
                                    "description": "文件名"
                                },
                                "size": {
                                    "type": "number",
                                    "description": "文件大小（字节）"
                                },
                                "related_id": {
                                    "type": "string",
                                    "description": "Dify 文件 ID"
                                },
                                "mime_type": {
                                    "type": "string",
                                    "description": "MIME 类型"
                                }
                            },
                            "required": ["filename", "related_id"]
                        }
                    }
                },
                "required": ["files"]
            }
        ),
        Tool(
            name="get_reconciliation",
            description="根据对账类型获取对账配置和回调地址",
            inputSchema={
                "type": "object",
                "properties": {
                    "reconciliation_type": {
                        "type": "string",
                        "description": "对账类型中文名称，例如：直销对账"
                    }
                },
                "required": ["reconciliation_type"]
            }
        )
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
    
    else:
        return {"error": f"未知的工具: {tool_name}"}


async def _reconciliation_start(args: Dict) -> Dict:
    """开始对账任务"""
    try:
        reconciliation_type = args.get("reconciliation_type")
        files = args.get("files", [])
        
        if not reconciliation_type:
            return {"error": "缺少 reconciliation_type 参数"}
        
        # 1. 读取配置文件，获取 schema 和 callback_url
        if not RECONCILIATION_SCHEMAS_FILE.exists():
            return {"error": f"配置文件不存在: {RECONCILIATION_SCHEMAS_FILE}"}
        
        with open(RECONCILIATION_SCHEMAS_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # 2. 查找匹配的对账类型
        types = config.get("types", [])
        matched_type = None
        
        for type_config in types:
            if type_config.get("name_cn") == reconciliation_type:
                matched_type = type_config
                break
        
        if not matched_type:
            available_types = [t.get("name_cn") for t in types if t.get("name_cn")]
            return {
                "error": f"未找到对账类型: {reconciliation_type}",
                "available_types": available_types
            }
        
        # 3. 获取 schema_url 和 callback_url
        schema_url = matched_type.get("schema_url")
        callback_url = matched_type.get("callback_url", "")
        
        if not schema_url:
            return {"error": f"配置缺少 schema_url: {reconciliation_type}"}
        
        # 4. 读取 schema 文件
        schema_path = SCHEMA_DIR / Path(schema_url).name
        
        if not schema_path.exists():
            return {
                "error": f"Schema 文件不存在: {schema_path}",
                "schema_url": schema_url
            }
        
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema = json.load(f)
        
        # 5. 验证 schema
        SchemaLoader.validate_schema(schema)
        
        # 6. 验证文件
        for file_path in files:
            if not Path(file_path).exists():
                return {"error": f"文件不存在: {file_path}"}
        
        # 7. 创建任务（传入 callback_url，如果为空则不会回调）
        task_id = await task_manager.create_task(schema, files, callback_url if callback_url else None)
        
        return {
            "task_id": task_id,
            "status": "pending",
            "message": "对账任务已创建，正在处理中"
        }
    
    except Exception as e:
        return {"error": f"创建任务失败: {str(e)}"}


async def _reconciliation_status(args: Dict) -> Dict:
    """查询任务状态"""
    task_id = args.get("task_id")
    
    task = await task_manager.get_task(task_id)
    if not task:
        return {"error": f"任务不存在: {task_id}"}
    
    return {
        "task_id": task.task_id,
        "status": task.status.value,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat()
    }


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
    """从 Dify 下载文件并保存（支持多文件）"""
    try:
        import httpx
        from datetime import datetime
        
        # Dify API 配置
        DIFY_BASE_URL = "http://localhost"
        DIFY_API_TOKEN = "app-pffBjBphPBhbrSwz8mxku2R3"
        
        files = args.get("files", [])
        if not files:
            return {"error": "files 参数不能为空"}
        
        uploaded_files = []
        errors = []
        
        # 创建按日期分类的上传目录
        now = datetime.now()
        date_dir = UPLOAD_DIR / str(now.year) / str(now.month) / str(now.day)
        date_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建 HTTP 客户端
        async with httpx.AsyncClient(timeout=60.0) as client:
            for idx, file_obj in enumerate(files):
                try:
                    # 提取文件信息
                    filename = file_obj.get("filename")
                    related_id = file_obj.get("related_id")
                    file_size = file_obj.get("size", 0)
                    mime_type = file_obj.get("mime_type", "application/octet-stream")
                    
                    # 验证必填字段
                    if not filename:
                        errors.append({
                            "index": idx,
                            "error": "缺少 filename 字段"
                        })
                        continue
                    
                    if not related_id:
                        errors.append({
                            "index": idx,
                            "filename": filename,
                            "error": "缺少 related_id 字段"
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
                    
                    # 构建 Dify 文件下载 URL
                    file_url = f"{DIFY_BASE_URL}/v1/files/{related_id}/preview"
                    
                    # 设置请求头
                    headers = {
                        "Authorization": f"Bearer {DIFY_API_TOKEN}"
                    }
                    
                    # 下载文件
                    try:
                        response = await client.get(file_url, headers=headers)
                        response.raise_for_status()
                        file_content = response.content
                    except httpx.HTTPStatusError as e:
                        errors.append({
                            "index": idx,
                            "filename": filename,
                            "error": f"下载文件失败: HTTP {e.response.status_code}"
                        })
                        continue
                    except httpx.RequestError as e:
                        errors.append({
                            "index": idx,
                            "filename": filename,
                            "error": f"请求失败: {str(e)}"
                        })
                        continue
                    
                    # 保存文件到日期目录
                    safe_filename = Path(filename).name  # 只取文件名，去除路径
                    file_path = date_dir / safe_filename
                    
                    # 如果文件已存在，添加时间戳
                    if file_path.exists():
                        timestamp = datetime.now().strftime("%H%M%S")
                        name_parts = safe_filename.rsplit('.', 1)
                        if len(name_parts) == 2:
                            safe_filename = f"{name_parts[0]}_{timestamp}.{name_parts[1]}"
                        else:
                            safe_filename = f"{safe_filename}_{timestamp}"
                        file_path = date_dir / safe_filename
                    
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
        
        with open(RECONCILIATION_SCHEMAS_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
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
        
        # 获取 schema_url 和 callback_url
        schema_url = matched_type.get("schema_url")
        callback_url = matched_type.get("callback_url", "")
        type_key = matched_type.get("type_key")
        
        if not schema_url:
            return {
                "schema": {},
                "callback_url": callback_url,
                "error": f"配置缺少 schema_url: {reconciliation_type}"
            }
        
        # 读取 schema 文件
        # schema_url 格式: /schemas/direct_sales_schema.json
        schema_path = SCHEMA_DIR / Path(schema_url).name
        
        if not schema_path.exists():
            return {
                "schema": {},
                "callback_url": callback_url,
                "error": f"Schema 文件不存在: {schema_path}"
            }
        
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema = json.load(f)
        
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
