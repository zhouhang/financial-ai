"""
MCP 工具定义
"""
import json
import uuid
from pathlib import Path
from typing import Dict, Any, List
from mcp import Tool
from .task_manager import TaskManager
from .config import UPLOAD_DIR, ALLOWED_EXTENSIONS
from .schema_loader import SchemaLoader


# 全局任务管理器
task_manager = TaskManager()


def create_tools() -> List[Tool]:
    """创建所有 MCP 工具"""
    return [
        Tool(
            name="reconciliation_start",
            description="开始对账任务。上传文件并提供 schema 配置，系统会异步执行对账并返回任务 ID。",
            inputSchema={
                "type": "object",
                "properties": {
                    "schema": {
                        "type": "object",
                        "description": "对账配置 schema，包含数据源、字段映射、验证规则等"
                    },
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要对账的文件路径列表"
                    },
                    "callback_url": {
                        "type": "string",
                        "description": "对账完成后的回调地址（可选）"
                    }
                },
                "required": ["schema", "files"]
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
            description="上传文件到服务器，返回文件路径",
            inputSchema={
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "文件名"
                    },
                    "content": {
                        "type": "string",
                        "description": "文件内容（base64 编码）"
                    }
                },
                "required": ["filename", "content"]
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
    
    else:
        return {"error": f"未知的工具: {tool_name}"}


async def _reconciliation_start(args: Dict) -> Dict:
    """开始对账任务"""
    try:
        schema = args.get("schema")
        files = args.get("files", [])
        callback_url = args.get("callback_url")
        
        # 验证 schema
        SchemaLoader.validate_schema(schema)
        
        # 验证文件
        for file_path in files:
            if not Path(file_path).exists():
                return {"error": f"文件不存在: {file_path}"}
        
        # 创建任务
        task_id = await task_manager.create_task(schema, files, callback_url)
        
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
    """上传文件"""
    try:
        import base64
        
        filename = args.get("filename")
        content_b64 = args.get("content")
        
        # 验证文件扩展名
        file_ext = Path(filename).suffix.lower()
        if file_ext not in ALLOWED_EXTENSIONS:
            return {"error": f"不支持的文件类型: {file_ext}"}
        
        # 生成唯一文件名
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        file_path = UPLOAD_DIR / unique_filename
        
        # 解码并保存
        content = base64.b64decode(content_b64)
        with open(file_path, 'wb') as f:
            f.write(content)
        
        return {
            "success": True,
            "file_path": str(file_path),
            "filename": unique_filename
        }
    
    except Exception as e:
        return {"error": f"文件上传失败: {str(e)}"}

