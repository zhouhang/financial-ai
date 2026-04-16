"""
安全工具模块 - 提供输入验证和安全功能
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional


FINANCE_MCP_DIR = Path(__file__).resolve().parent
UPLOAD_ROOT = FINANCE_MCP_DIR / "uploads"
PROC_OUTPUT_ROOT = FINANCE_MCP_DIR / "proc" / "output"
RECON_OUTPUT_ROOT = FINANCE_MCP_DIR / "recon" / "output"


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


def resolve_path_under_roots(file_path: str, allowed_roots: Iterable[Path]) -> Path:
    """将文件引用解析为受控绝对路径，并限制在允许目录内。"""
    if not file_path:
        raise ValueError("文件路径不能为空")

    allowed_root_list = [root.resolve() for root in allowed_roots]
    path_str = str(file_path).strip()

    if path_str.startswith("/uploads/") or path_str.startswith("uploads/"):
        candidate = (FINANCE_MCP_DIR / path_str.lstrip("/")).resolve()
    else:
        candidate = Path(path_str).expanduser().resolve()

    for root in allowed_root_list:
        try:
            candidate.relative_to(root)
            return candidate
        except ValueError:
            continue

    raise ValueError(f"文件路径不在允许目录内: {file_path}")


def resolve_upload_file_path(file_path: str) -> Path:
    """解析上传目录中的文件路径。"""
    return resolve_path_under_roots(file_path, [UPLOAD_ROOT])


def resolve_recon_input_file_path(file_path: str) -> Path:
    """解析对账输入文件路径。

    recon 既可能直接读取上传文件，也可能读取 proc 产出的中间结果。
    """
    return resolve_path_under_roots(file_path, [UPLOAD_ROOT, PROC_OUTPUT_ROOT])


def get_output_metadata_path(file_path: str | Path) -> Path:
    """获取输出文件 sidecar 元数据路径。"""
    target = Path(file_path)
    return target.with_name(f"{target.name}.meta.json")


def write_output_metadata(file_path: str | Path, metadata: dict[str, Any]) -> Path:
    """为输出文件写入 sidecar 元数据。"""
    target = Path(file_path)
    meta_path = get_output_metadata_path(target)
    payload = dict(metadata)
    payload.setdefault("file_name", target.name)
    payload.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    meta_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return meta_path


def read_output_metadata(file_path: str | Path) -> Optional[dict[str, Any]]:
    """读取输出文件 sidecar 元数据。"""
    meta_path = get_output_metadata_path(file_path)
    if not meta_path.exists() or not meta_path.is_file():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
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
