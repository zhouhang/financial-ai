"""
Routers package initialization
"""
from routers.auth import router as auth_router
from routers.schemas import router as schemas_router
from routers.files import router as files_router
from routers.dify import router as dify_router

__all__ = ["auth_router", "schemas_router", "files_router", "dify_router"]
