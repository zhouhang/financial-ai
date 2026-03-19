"""proc RESTful API 路由。

提供任务与规则管理的 HTTP 接口：
- GET /proc/list_user_tasks          - 获取当前用户可用任务
- GET /proc/get_file_validation_rule - 根据 rule_code 获取文件校验规则
- GET /proc/get_proc_rule            - 根据 rule_code 获取整理规则
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# 创建路由
router = APIRouter(prefix="/proc", tags=["proc"])


# ══════════════════════════════════════════════════════════════════════════════
# 数据模型
# ══════════════════════════════════════════════════════════════════════════════

class UserTaskRule(BaseModel):
    """任务下的规则模型。"""
    id: int
    user_id: Optional[str] = None
    task_id: Optional[int] = None
    rule_code: str
    name: str
    rule_type: str
    remark: Optional[str] = None
    task_code: str
    task_name: str
    task_type: str
    file_rule_code: Optional[str] = None


class UserTask(BaseModel):
    """用户任务模型。"""
    id: int
    user_id: Optional[str] = None
    task_code: str
    task_name: str
    description: Optional[str] = None
    task_type: str
    rules: list[UserTaskRule] = Field(default_factory=list)


class UserTasksResponse(BaseModel):
    """任务列表响应。"""
    success: bool
    count: int
    tasks: list[UserTask]
    message: str


class RuleDetailResponse(BaseModel):
    """规则详情响应（文件校验/整理规则）"""
    success: bool
    rule_code: str
    data: Optional[dict] = None
    message: str


# ══════════════════════════════════════════════════════════════════════════════
# API 路由
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/list_user_tasks", response_model=UserTasksResponse)
async def list_user_tasks(
    authorization: Optional[str] = Header(None),
):
    """获取当前用户可用任务。"""
    logger.info("API: 获取任务列表")
    
    # 提取 token
    auth_token = ""
    if authorization:
        auth_token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    
    try:
        from tools.mcp_client import list_user_tasks as mcp_list_user_tasks

        result = await mcp_list_user_tasks(auth_token)
        
        if not result.get("success"):
            logger.error(f"获取任务列表失败: {result.get('error')}")
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "获取任务列表失败")
            )
        
        return UserTasksResponse(
            success=True,
            count=result.get("count", 0),
            tasks=result.get("tasks", []),
            message=result.get("message", "")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取任务列表异常: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get_file_validation_rule", response_model=RuleDetailResponse)
async def get_file_validation_rule(
    rule_code: str = Query(..., description="规则编码 (rule_code)"),
    authorization: Optional[str] = Header(None),
):
    """根据 rule_code 获取文件校验规则 JSON
    
    Args:
        rule_code: 规则编码（通过 query 参数传递）
        authorization: JWT token（可选，通过 Header 传递）
        
    Returns:
        文件校验规则 JSON
    """
    logger.info(f"API: 获取文件校验规则 rule_code={rule_code}")
    
    if not rule_code:
        raise HTTPException(status_code=400, detail="rule_code 不能为空")
    
    # 提取 token
    auth_token = ""
    if authorization:
        auth_token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    
    try:
        # 导入 MCP 客户端函数
        from tools.mcp_client import get_file_validation_rule as mcp_get_file_validation_rule
        
        result = await mcp_get_file_validation_rule(rule_code, auth_token)
        
        if not result.get("success"):
            logger.warning(f"获取文件校验规则失败: {result.get('error')}")
            return RuleDetailResponse(
                success=False,
                rule_code=rule_code,
                data=None,
                message=result.get("error", "未找到规则")
            )
        
        return RuleDetailResponse(
            success=True,
            rule_code=rule_code,
            data=result.get("data"),
            message=result.get("message", "成功获取文件校验规则")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文件校验规则异常: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get_proc_rule", response_model=RuleDetailResponse)
async def get_proc_rule(
    rule_code: str = Query(..., description="规则编码 (rule_code)"),
    authorization: Optional[str] = Header(None),
):
    """根据 rule_code 获取整理规则 JSON
    
    Args:
        rule_code: 规则编码（通过 query 参数传递）
        authorization: JWT token（可选，通过 Header 传递）
        
    Returns:
        整理规则 JSON
    """
    logger.info(f"API: 获取整理规则 rule_code={rule_code}")
    
    if not rule_code:
        raise HTTPException(status_code=400, detail="rule_code 不能为空")
    
    # 提取 token
    auth_token = ""
    if authorization:
        auth_token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    
    try:
        # 导入 MCP 客户端函数（get_file_validation_rule 和 get_proc_rule 功能相同，均调用 get_rule）
        from tools.mcp_client import get_file_validation_rule
        
        result = await get_file_validation_rule(rule_code, auth_token)
        
        if not result.get("success"):
            logger.warning(f"获取整理规则失败: {result.get('error')}")
            return RuleDetailResponse(
                success=False,
                rule_code=rule_code,
                data=None,
                message=result.get("error", "未找到规则")
            )
        
        return RuleDetailResponse(
            success=True,
            rule_code=rule_code,
            data=result.get("data"),
            message=result.get("message", "成功获取整理规则")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取整理规则异常: {e}")
        raise HTTPException(status_code=500, detail=str(e))
