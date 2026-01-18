"""
任务管理器 - 管理异步数据整理任务
"""
import asyncio
import uuid
import logging
from typing import Dict, Optional
from datetime import datetime
import json

from .models import ProcessingResult
from .processing_engine import ProcessingEngine
from .schema_loader import SchemaLoader

logger = logging.getLogger(__name__)


class TaskManager:
    """任务管理器"""
    
    def __init__(self):
        self.tasks: Dict[str, Dict] = {}
        self.lock = asyncio.Lock()
    
    async def create_task(
        self,
        reconciliation_type: str,
        files: list,
        schema_path: str,
        output_dir: str,
        report_dir: str = None,
        callback_url: Optional[str] = None
    ) -> str:
        """
        创建数据整理任务
        
        Args:
            reconciliation_type: 数据整理类型（用于显示）
            files: 文件路径列表
            schema_path: Schema 文件路径
            output_dir: 输出目录
            report_dir: 报告目录
            callback_url: 回调 URL
        
        Returns:
            task_id
        """
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        
        async with self.lock:
            self.tasks[task_id] = {
                "task_id": task_id,
                "status": "pending",
                "created_at": datetime.now().isoformat(),
                "reconciliation_type": reconciliation_type,
                "files": files,
                "schema_path": schema_path,
                "output_dir": output_dir,
                "report_dir": report_dir,
                "callback_url": callback_url,
                "result": None,
                "error": None
            }
        
        # 异步执行任务
        asyncio.create_task(self._execute_task(task_id))
        
        logger.info(f"任务已创建: {task_id}, 类型: {reconciliation_type}")
        return task_id
    
    async def _execute_task(self, task_id: str):
        """执行任务"""
        async with self.lock:
            if task_id not in self.tasks:
                return
            self.tasks[task_id]["status"] = "processing"
        
        try:
            # 加载 schema
            task_info = self.tasks[task_id]
            schema = SchemaLoader.load_from_file(task_info["schema_path"])
            
            # 创建处理引擎
            engine = ProcessingEngine(schema)
            
            # 执行处理（在后台线程中执行，避免阻塞）
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                engine.process,
                task_info["files"],
                task_info["output_dir"],
                task_info.get("report_dir")
            )
            
            # 更新任务状态
            async with self.lock:
                self.tasks[task_id]["status"] = "completed"
                self.tasks[task_id]["result"] = result
            
            logger.info(f"任务完成: {task_id}")
            
            # 回调（如果有）
            if task_info.get("callback_url"):
                await self._send_callback(task_info["callback_url"], result.to_dict())
        
        except Exception as e:
            logger.error(f"任务执行失败: {task_id}, 错误: {str(e)}", exc_info=True)
            async with self.lock:
                self.tasks[task_id]["status"] = "failed"
                self.tasks[task_id]["error"] = str(e)
    
    async def get_task_status(self, task_id: str) -> Dict:
        """获取任务状态"""
        async with self.lock:
            if task_id not in self.tasks:
                return {"error": f"任务不存在: {task_id}"}
            
            task = self.tasks[task_id]
            return {
                "task_id": task_id,
                "status": task["status"]
            }
    
    async def get_task_result(self, task_id: str) -> Dict:
        """获取任务结果"""
        async with self.lock:
            if task_id not in self.tasks:
                return {"error": f"任务不存在: {task_id}"}
            
            task = self.tasks[task_id]
            
            if task["status"] == "pending" or task["status"] == "processing":
                return {
                    "task_id": task_id,
                    "status": task["status"]
                }
            
            elif task["status"] == "completed":
                result: ProcessingResult = task["result"]
                return result.to_dict() if result else {"error": "结果为空"}
            
            else:  # failed
                return {
                    "task_id": task_id,
                    "status": "failed",
                    "error": task.get("error", "Unknown error")
                }
    
    async def list_tasks(self) -> list:
        """列出所有任务"""
        async with self.lock:
            return [
                {
                    "task_id": task_id,
                    "status": task["status"],
                    "created_at": task["created_at"],
                    "reconciliation_type": task.get("reconciliation_type", "")
                }
                for task_id, task in self.tasks.items()
            ]
    
    async def _send_callback(self, callback_url: str, result: Dict):
        """发送回调"""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    callback_url,
                    json=result,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        logger.info(f"回调成功: {callback_url}")
                    else:
                        logger.warning(f"回调失败: {callback_url}, 状态码: {response.status}")
        except Exception as e:
            logger.error(f"回调失败: {callback_url}, 错误: {str(e)}")
