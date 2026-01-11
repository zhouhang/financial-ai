"""
数据整理模块配置常量
"""
import os
from pathlib import Path

# 基础目录
BASE_DIR = Path(__file__).parent.parent.absolute()  # finance-agent/data_preparation/
FINANCE_AGENT_DIR = BASE_DIR.parent  # finance-agent/
UPLOAD_DIR = FINANCE_AGENT_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"
REPORT_DIR = BASE_DIR / "report"
TEMPLATES_DIR = BASE_DIR / "templates"
SCHEMA_DIR = BASE_DIR / "schemas"
CONFIG_DIR = BASE_DIR / "config"

# 确保目录存在
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
REPORT_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)
SCHEMA_DIR.mkdir(exist_ok=True)
CONFIG_DIR.mkdir(exist_ok=True)

# 配置文件路径
DATA_PREPARATION_SCHEMAS_FILE = CONFIG_DIR / "data_preparation_schemas.json"

# 服务器配置
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 3336  # 使用不同端口避免冲突

# 任务配置
TASK_TIMEOUT = 7200  # 2 小时（数据处理可能更耗时）
MAX_CONCURRENT_TASKS = 3

# 文件配置
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".pdf", ".jpg", ".jpeg", ".png"}

# 下载链接有效期（秒）
DOWNLOAD_LINK_EXPIRY = 86400  # 24小时
