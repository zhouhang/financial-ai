"""
Routers package initialization
"""
from api.routers.auth import router as auth_router
from api.routers.schemas import router as schemas_router
from api.routers.files import router as files_router

__all__ = ["auth_router", "schemas_router", "files_router"]
