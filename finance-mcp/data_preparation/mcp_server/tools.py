"""
Data Preparation MCP 工具定义
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any
from mcp import Tool

from .task_manager import TaskManager
from .config import (
    OUTPUT_DIR, SCHEMA_DIR, CONFIG_DIR, REPORT_DIR,
    DATA_PREPARATION_SCHEMAS_FILE, DEFAULT_HOST, DEFAULT_PORT
)
from .schema_loader import load_json_with_comments

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 全局任务管理器
task_manager = TaskManager()


def create_tools() -> list[Tool]:
    """创建 MCP 工具列表"""
    return [
        Tool(
            name="data_preparation_start",
            description="开始数据整理任务",
            inputSchema={
                "type": "object",
                "properties": {
                    "data_preparation_type": {
                        "type": "string",
                        "description": "数据整理类型（中文名称，如：审计数据整理）"
                    },
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "文件路径列表"
                    }
                },
                "required": ["data_preparation_type", "files"]
            }
        ),
        Tool(
            name="data_preparation_result",
            description="获取数据整理结果",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "任务ID"
                    }
                },
                "required": ["task_id"]
            }
        ),
        Tool(
            name="data_preparation_status",
            description="查询数据整理任务状态",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "任务ID"
                    }
                },
                "required": ["task_id"]
            }
        ),
        Tool(
            name="data_preparation_list_tasks",
            description="列出所有数据整理任务",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        )
    ]


async def handle_tool_call(name: str, arguments: dict) -> Dict[str, Any]:
    """处理工具调用"""
    if name == "data_preparation_start":
        return await _data_preparation_start(arguments)
    elif name == "data_preparation_result":
        return await _data_preparation_result(arguments)
    elif name == "data_preparation_status":
        return await _data_preparation_status(arguments)
    elif name == "data_preparation_list_tasks":
        return await _data_preparation_list_tasks(arguments)
    else:
        return {"error": f"未知的工具: {name}"}


async def _data_preparation_start(args: Dict) -> Dict:
    """开始数据整理任务"""
    try:
        data_preparation_type = args.get("data_preparation_type")
        files = args.get("files", [])
        
        if not data_preparation_type:
            return {"error": "缺少参数: data_preparation_type"}
        
        if not files:
            return {"error": "缺少参数: files"}
        
        # 加载数据整理类型配置
        if not DATA_PREPARATION_SCHEMAS_FILE.exists():
            return {"error": f"配置文件不存在: {DATA_PREPARATION_SCHEMAS_FILE}"}
        
        schemas_config = load_json_with_comments(DATA_PREPARATION_SCHEMAS_FILE)
        
        # 查找匹配的类型
        type_config = None
        for type_info in schemas_config.get("types", []):
            if type_info.get("name_cn") == data_preparation_type:
                type_config = type_info
                break
        
        if not type_config:
            return {"error": f"未找到数据整理类型: {data_preparation_type}"}
        
        # 获取 schema 路径
        schema_path = type_config.get("schema_path", "")
        
        # SCHEMA_DIR 已经指向 data_preparation/schemas
        # schema_path 格式: audit_schema.json (只包含文件名)
        if schema_path.startswith("/"):
            schema_path = schema_path[1:]  # 移除开头的 /
        if schema_path.startswith("schemas/"):
            # 如果包含 schemas/ 前缀，去掉它
            schema_path = schema_path.replace("schemas/", "", 1)
        
        full_schema_path = SCHEMA_DIR / schema_path
        
        if not full_schema_path.exists():
            return {"error": f"Schema 文件不存在: {full_schema_path}"}
        
        # 转换文件路径为绝对路径
        absolute_files = []
        for file_path in files:
            if file_path.startswith("/uploads/"):
                # 相对路径，转换为绝对路径
                rel_path = file_path[1:]  # 移除开头的 /
                abs_path = SCHEMA_DIR.parent.parent / rel_path
                absolute_files.append(str(abs_path))
            else:
                absolute_files.append(file_path)
        
        # 创建任务
        task_id = await task_manager.create_task(
            reconciliation_type=data_preparation_type,
            files=absolute_files,
            schema_path=str(full_schema_path),
            output_dir=str(OUTPUT_DIR),
            report_dir=str(REPORT_DIR),
            callback_url=type_config.get("callback_url")
        )
        
        return {
            "task_id": task_id,
            "status": "pending",
            "message": f"{data_preparation_type}任务已创建，正在处理中"
        }
    
    except Exception as e:
        logger.error(f"创建任务失败: {str(e)}", exc_info=True)
        return {"error": f"创建任务失败: {str(e)}"}


async def _data_preparation_result(args: Dict) -> Dict:
    """获取数据整理结果"""
    try:
        task_id = args.get("task_id")
        
        if not task_id:
            return {"error": "缺少参数: task_id"}
        
        result = await task_manager.get_task_result(task_id)
        
        # 如果任务完成，添加下载链接
        if result.get("status") == "success" and "actions" in result:
            # 生成下载/预览/报告 URL
            base_url = f"http://{DEFAULT_HOST}:{DEFAULT_PORT}"
            
            for action in result["actions"]:
                if action["action"] == "download_file":
                    # 从输出文件路径生成下载 URL
                    # TODO: 实现文件下载服务
                    action["url"] = f"{base_url}/download/{task_id}"
                elif action["action"] == "view_preview":
                    action["url"] = f"{base_url}/preview/{task_id}"
                elif action["action"] == "get_detailed_report":
                    action["url"] = f"{base_url}/report/{task_id}"
        
        return result
    
    except Exception as e:
        logger.error(f"获取结果失败: {str(e)}", exc_info=True)
        return {"error": f"获取结果失败: {str(e)}"}


async def _data_preparation_status(args: Dict) -> Dict:
    """查询任务状态"""
    try:
        task_id = args.get("task_id")
        
        if not task_id:
            return {"error": "缺少参数: task_id"}
        
        return await task_manager.get_task_status(task_id)
    
    except Exception as e:
        logger.error(f"查询状态失败: {str(e)}", exc_info=True)
        return {"error": f"查询状态失败: {str(e)}"}


async def _data_preparation_list_tasks(args: Dict) -> Dict:
    """列出所有任务"""
    try:
        tasks = await task_manager.list_tasks()
        return {"tasks": tasks}
    
    except Exception as e:
        logger.error(f"列出任务失败: {str(e)}", exc_info=True)
        return {"error": f"列出任务失败: {str(e)}"}
