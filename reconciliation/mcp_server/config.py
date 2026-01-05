"""
配置常量
"""
import os
from pathlib import Path

# 基础目录
BASE_DIR = Path(__file__).parent.parent.absolute()
UPLOAD_DIR = BASE_DIR / "uploads"
RESULT_DIR = BASE_DIR / "results"
SCHEMA_DIR = BASE_DIR / "schemas"

# 确保目录存在
UPLOAD_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)
SCHEMA_DIR.mkdir(exist_ok=True)

# 服务器配置
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 3335

# 任务配置
TASK_TIMEOUT = 3600  # 1 小时
MAX_CONCURRENT_TASKS = 5

# 文件配置
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}

