"""
Proc 模块 RESTful API 服务器

提供前端调用的 HTTP 接口，用于获取数字员工列表和规则列表。

启动方式:
    python proc_api_server.py

接口列表:
    GET  /api/proc/employees          - 获取数字员工列表
    GET  /api/proc/rules/{emp_code}   - 获取指定数字员工的规则列表
    GET  /health                      - 健康检查
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "finance-mcp"))

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from mcp_proc_tools import get_digital_employees, get_rules_by_employee

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 创建 FastAPI 应用
app = FastAPI(
    title="Proc API Server",
    description="数字员工和规则管理 RESTful API",
    version="1.0.0"
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════════════════════════════════════
# 数据模型
# ══════════════════════════════════════════════════════════════════════════════

class Employee(BaseModel):
    """数字员工模型"""
    id: int
    code: str
    name: str
    desc_text: str | None
    type: str
    memo: str | None


class Rule(BaseModel):
    """规则模型"""
    id: int
    code: str
    name: str
    desc_text: str | None
    type: str
    parent_code: str | None
    memo: str | None


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


class ErrorResponse(BaseModel):
    """错误响应"""
    success: bool = False
    error: str


# ══════════════════════════════════════════════════════════════════════════════
# API 路由
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "service": "proc-api-server",
        "version": "1.0.0"
    }


@app.get("/api/proc/employees", response_model=EmployeesResponse)
async def list_employees(auth_token: str = ""):
    """
    获取数字员工列表
    
    Args:
        auth_token: JWT token（可选，通过 query 参数传递）
        
    Returns:
        数字员工列表
    """
    logger.info("API: 获取数字员工列表")
    
    result = get_digital_employees(auth_token)
    
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


@app.get("/api/proc/rules/{employee_code}", response_model=RulesResponse)
async def list_rules(employee_code: str, auth_token: str = ""):
    """
    获取指定数字员工的规则列表
    
    Args:
        employee_code: 数字员工的 code
        auth_token: JWT token（可选，通过 query 参数传递）
        
    Returns:
        规则列表
    """
    logger.info(f"API: 获取数字员工 {employee_code} 的规则列表")
    
    if not employee_code:
        raise HTTPException(
            status_code=400,
            detail="employee_code 不能为空"
        )
    
    result = get_rules_by_employee(employee_code, auth_token)
    
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


# ══════════════════════════════════════════════════════════════════════════════
# 启动入口
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Proc API Server")
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="服务器主机地址 (默认: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8101,
        help="服务器端口 (默认: 8101)"
    )
    
    args = parser.parse_args()
    
    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║          Proc API Server 启动中...                               ║
╚══════════════════════════════════════════════════════════════════╝

🌐 服务端点:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  • 健康检查:        http://{args.host}:{args.port}/health
  • 数字员工列表:    http://{args.host}:{args.port}/api/proc/employees
  • 规则列表:        http://{args.host}:{args.port}/api/proc/rules/{{employee_code}}

📖 API 文档:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  • Swagger UI:      http://{args.host}:{args.port}/docs
  • ReDoc:           http://{args.host}:{args.port}/redoc

服务器正在运行...
""")
    
    uvicorn.run(app, host=args.host, port=args.port)
