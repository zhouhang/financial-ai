"""
异步任务管理器
"""
import asyncio
import uuid
import httpx
import logging
from typing import Dict, Optional, List
from datetime import datetime
from .models import ReconciliationTask, TaskStatus, ReconciliationResult
from .reconciliation_engine import ReconciliationEngine
from .config import TASK_TIMEOUT

logger = logging.getLogger(__name__)


class TaskManager:
    """任务管理器"""
    
    def __init__(self):
        self.tasks: Dict[str, ReconciliationTask] = {}
        self._lock = asyncio.Lock()
    
    async def create_task(self, schema: Dict, files: List[str], callback_url: Optional[str] = None) -> str:
        """
        创建新任务
        
        Args:
            schema: 对账 schema
            files: 文件路径列表
            callback_url: 回调地址
        
        Returns:
            任务 ID
        """
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        
        task = ReconciliationTask(
            task_id=task_id,
            schema=schema,
            files=files,
            callback_url=callback_url,
            status=TaskStatus.PENDING
        )
        
        async with self._lock:
            self.tasks[task_id] = task
        
        # 异步执行任务
        asyncio.create_task(self._execute_task(task_id))
        
        return task_id
    
    async def get_task(self, task_id: str) -> Optional[ReconciliationTask]:
        """获取任务信息"""
        async with self._lock:
            return self.tasks.get(task_id)
    
    async def list_tasks(self) -> List[ReconciliationTask]:
        """列出所有任务"""
        async with self._lock:
            return list(self.tasks.values())
    
    async def _execute_task(self, task_id: str):
        """执行任务"""
        async with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                return
            task.status = TaskStatus.PROCESSING
            task.updated_at = datetime.now()
        
        try:
            # 执行对账（在线程池中执行，避免阻塞事件循环）
            loop = asyncio.get_event_loop()
            result_dict = await asyncio.wait_for(
                loop.run_in_executor(None, self._run_reconciliation, task),
                timeout=TASK_TIMEOUT
            )
            
            # 构建结果（result_dict 中的 summary、issues、metadata 已经是字典格式）
            from .models import ReconciliationSummary, ReconciliationIssue, ReconciliationMetadata
            
            summary = ReconciliationSummary(**result_dict["summary"])
            issues = [ReconciliationIssue(**issue) for issue in result_dict["issues"]]
            metadata = ReconciliationMetadata(**result_dict["metadata"])
            
            result = ReconciliationResult(
                task_id=task_id,
                status=TaskStatus.COMPLETED,
                summary=summary,
                issues=issues,
                metadata=metadata
            )
            
            async with self._lock:
                task.status = TaskStatus.COMPLETED
                task.result = result
                task.updated_at = datetime.now()
            
            # 回调
            if task.callback_url:
                await self._send_callback(task.callback_url, result.to_dict())
        
        except asyncio.TimeoutError:
            async with self._lock:
                task.status = TaskStatus.FAILED
                task.result = ReconciliationResult(
                    task_id=task_id,
                    status=TaskStatus.FAILED,
                    summary=None,
                    error="任务超时"
                )
                task.updated_at = datetime.now()
        
        except Exception as e:
            async with self._lock:
                task.status = TaskStatus.FAILED
                task.result = ReconciliationResult(
                    task_id=task_id,
                    status=TaskStatus.FAILED,
                    summary=None,
                    error=str(e)
                )
                task.updated_at = datetime.now()
            
            # 回调错误
            if task.callback_url:
                error_result = {
                    "task_id": task_id,
                    "status": "failed",
                    "error": str(e)
                }
                await self._send_callback(task.callback_url, error_result)
    
    def _run_reconciliation(self, task: ReconciliationTask) -> Dict:
        """运行对账（同步方法，在执行器中运行）"""
        engine = ReconciliationEngine(task.schema)
        return engine.reconcile(task.files)
    
    async def _send_callback(self, callback_url: str, data: Dict):
        """发送回调"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(callback_url, json=data)
                logger.info(f"回调成功: {callback_url}, 状态码: {response.status_code}")
        except Exception as e:
            logger.error(f"回调失败: {callback_url}, 错误: {str(e)}")

