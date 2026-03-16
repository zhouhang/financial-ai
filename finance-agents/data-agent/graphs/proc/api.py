"""proc RESTful API 路由

提供数字员工和规则管理的 HTTP 接口：
- GET /proc/list_digital_employees    - 获取数字员工列表
- GET /proc/list_rules_by_employee    - 获取指定数字员工的规则列表
- GET /proc/get_file_validation_rule  - 根据 rule_code 获取文件校验规则
- GET /proc/get_proc_rule             - 根据 rule_code 获取整理规则
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# 创建路由
router = APIRouter(prefix="/proc", tags=["proc"])


# ══════════════════════════════════════════════════════════════════════════════
# 数据模型
# ══════════════════════════════════════════════════════════════════════════════

class Employee(BaseModel):
    """数字员工模型"""
    id: int
    code: str
    name: str
    desc_text: Optional[str] = None
    type: str
    memo: Optional[str] = None
    file_rule_code: Optional[str] = None


class Rule(BaseModel):
    """规则模型"""
    id: int
    code: str
    name: str
    desc_text: Optional[str] = None
    type: str
    parent_code: Optional[str] = None
    memo: Optional[str] = None
    file_rule_code: Optional[str] = None


class EmployeesResponse(BaseModel):
    """数字员工列表响应"""
    success: bool
    count: int
    employees: list[Employee]
    message: str


class RulesResponse(BaseModel):
    """规则列表响应"""
    success: bool
    count: int
    employee_code: str
    rules: list[Rule]
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

@router.get("/list_digital_employees", response_model=EmployeesResponse)
async def list_digital_employees(
    authorization: Optional[str] = Header(None),
):
    """获取数字员工列表
    
    Args:
        authorization: JWT token（可选，通过 Header 传递）
        
    Returns:
        数字员工列表
    """
    logger.info("API: 获取数字员工列表")
    
    # 提取 token
    auth_token = ""
    if authorization:
        auth_token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    
    try:
        # 导入 MCP 客户端函数
        from tools.mcp_client import list_digital_employees as mcp_list_digital_employees
        
        result = await mcp_list_digital_employees(auth_token)
        
        if not result.get("success"):
            logger.error(f"获取数字员工列表失败: {result.get('error')}")
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "获取数字员工列表失败")
            )
        
        return EmployeesResponse(
            success=True,
            count=result.get("count", 0),
            employees=result.get("employees", []),
            message=result.get("message", "")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取数字员工列表异常: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list_rules_by_employee", response_model=RulesResponse)
async def list_rules_by_employee(
    employee_code: str = Query(..., description="数字员工的 code"),
    authorization: Optional[str] = Header(None),
):
    """获取指定数字员工的规则列表
    
    Args:
        employee_code: 数字员工的 code（通过 query 参数传递）
        authorization: JWT token（可选，通过 Header 传递）
        
    Returns:
        规则列表
    """
    logger.info(f"API: 获取数字员工 {employee_code} 的规则列表")
    
    if not employee_code:
        raise HTTPException(status_code=400, detail="employee_code 不能为空")
    
    # 提取 token
    auth_token = ""
    if authorization:
        auth_token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    
    try:
        # 导入 MCP 客户端函数
        from tools.mcp_client import list_rules_by_employee as mcp_list_rules_by_employee
        
        result = await mcp_list_rules_by_employee(employee_code, auth_token)
        
        if not result.get("success"):
            logger.error(f"获取规则列表失败: {result.get('error')}")
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "获取规则列表失败")
            )
        
        return RulesResponse(
            success=True,
            count=result.get("count", 0),
            employee_code=employee_code,
            rules=result.get("rules", []),
            message=result.get("message", "")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取规则列表异常: {e}")
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
        # 导入 MCP 客户端函数（get_file_validation_rule 和 get_proc_rule 功能相同，均调用 get_rule_from_bus）
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
