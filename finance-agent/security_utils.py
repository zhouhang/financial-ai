"""
安全工具模块 - 提供输入验证和安全功能
"""
import re
from pathlib import Path
from typing import Optional


def validate_task_id(task_id: str) -> bool:
    """
    验证 task_id 格式，防止路径遍历攻击

    Args:
        task_id: 任务ID

    Returns:
        是否有效
    """
    if not task_id:
        return False

    # 只允许字母、数字、下划线、连字符
    # 典型的 task_id 格式：proc_20260110_135748_9b37a0 或 recon_20260110_135748_9b37a0
    pattern = r'^[a-zA-Z0-9_-]+$'

    # 长度限制（防止过长的输入）
    if len(task_id) > 100:
        return False

    # 不允许包含路径分隔符
    if '/' in task_id or '\\' in task_id or '..' in task_id:
        return False

    return bool(re.match(pattern, task_id))


def validate_filename(filename: str) -> bool:
    """
    验证文件名格式，防止路径遍历攻击

    Args:
        filename: 文件名

    Returns:
        是否有效
    """
    if not filename:
        return False

    # 长度限制
    if len(filename) > 255:
        return False

    # 不允许包含路径分隔符
    if '/' in filename or '\\' in filename or '..' in filename:
        return False

    # 不允许包含特殊字符
    dangerous_chars = ['<', '>', ':', '"', '|', '?', '*', '\0']
    if any(char in filename for char in dangerous_chars):
        return False

    return True


def sanitize_path(base_dir: Path, relative_path: str) -> Optional[Path]:
    """
    安全地拼接路径，防止路径遍历攻击

    Args:
        base_dir: 基础目录
        relative_path: 相对路径

    Returns:
        安全的绝对路径，如果不安全则返回 None
    """
    try:
        # 解析为绝对路径
        base_dir = base_dir.resolve()
        full_path = (base_dir / relative_path).resolve()

        # 检查是否在 base_dir 内
        if not str(full_path).startswith(str(base_dir)):
            return None

        return full_path
    except (ValueError, OSError):
        return None


def validate_url(url: str) -> bool:
    """
    验证 URL 格式（用于回调 URL 等）

    Args:
        url: URL 字符串

    Returns:
        是否有效
    """
    if not url:
        return False

    # 只允许 http 和 https 协议
    if not url.startswith(('http://', 'https://')):
        return False

    # 长度限制
    if len(url) > 2048:
        return False

    # 基本的 URL 格式验证
    url_pattern = r'^https?://[^\s/$.?#].[^\s]*$'
    return bool(re.match(url_pattern, url))
