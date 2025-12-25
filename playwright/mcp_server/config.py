"""
配置常量
"""

# 服务器配置
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 3334

# 截图保存目录
SCREENSHOT_DIR = ".playwright-mcp"

# Playwright 路径修复（确保从 site-packages 导入）
import os
import sys

_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_script_dir))
_site_packages = os.path.join(_project_root, '.venv', 'lib', 'python3.12', 'site-packages')

if os.path.exists(_site_packages) and _site_packages not in sys.path:
    sys.path.insert(0, _site_packages)

