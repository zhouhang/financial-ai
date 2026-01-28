"""
Finance MCP API Server
提供 RESTful API 和 MCP 服务的统一服务器
"""
import sys
from pathlib import Path
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn
import logging

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

# 导入数据库和配置
from api.database import init_db
from api.config import settings

# 导入路由
from api.routers import auth_router, schemas_router, files_router

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan events
    """
    # Startup: Initialize database
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialized successfully")

    yield

    # Shutdown
    logger.info("Shutting down API server...")


# Create FastAPI app
app = FastAPI(
    title="Finance MCP API",
    description="Backend API for Finance MCP - Authentication, Schema Management, and File Operations",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router, prefix=settings.API_PREFIX)
app.include_router(schemas_router, prefix=settings.API_PREFIX)
app.include_router(files_router, prefix=settings.API_PREFIX)


@app.get("/")
def root():
    """
    Root endpoint
    """
    return {
        "message": "Finance MCP API",
        "version": "1.0.0",
        "docs": "/docs",
        "services": {
            "api": "RESTful API for authentication, schemas, and files",
            "mcp": "Model Context Protocol server (port 3335)"
        }
    }


@app.get("/health")
def health_check():
    """
    Health check endpoint
    """
    return {
        "status": "healthy",
        "service": "finance-mcp-api",
        "version": "1.0.0"
    }


if __name__ == "__main__":
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
