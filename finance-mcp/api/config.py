"""
Configuration settings for the Finance MCP API
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "mysql+pymysql://aiuser:123456@127.0.0.1:3306/finance-ai?charset=utf8mb4"

    # Security
    SECRET_KEY: str = "your-secret-key-change-in-production-09a8f7d6e5c4b3a2"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    # File Storage
    UPLOAD_DIR: str = "./uploads"
    SCHEMA_BASE_DIR: str = "."
    MAX_FILE_SIZE: int = 100 * 1024 * 1024  # 100MB
    ALLOWED_EXTENSIONS: set = {".xlsx", ".xls", ".csv"}

    # API
    API_PREFIX: str = "/api"
    CORS_ORIGINS: list = ["http://localhost:5173", "http://localhost:3000"]

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
