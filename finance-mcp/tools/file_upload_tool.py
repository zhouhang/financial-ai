"""
公共上传 MCP 工具定义
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp import Tool

logger = logging.getLogger(__name__)

FINANCE_MCP_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = FINANCE_MCP_DIR / "uploads"
ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}

UPLOAD_DIR.mkdir(exist_ok=True)


def create_file_upload_tools() -> list[Tool]:
    """创建公共上传 MCP 工具。"""
    return [
        Tool(
            name="file_upload",
            description="上传文件并保存到服务器，支持多个文件上传。返回上传文件路径列表。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {
                        "type": "string",
                        "description": "JWT token，用于校验用户身份",
                    },
                    "files": {
                        "type": "array",
                        "description": "文件数组，每个元素包含 filename, content(base64)",
                        "items": {
                            "type": "object",
                            "properties": {
                                "filename": {"type": "string", "description": "文件名"},
                                "content": {"type": "string", "description": "文件内容（base64 编码）"},
                            },
                            "required": ["filename", "content"],
                        },
                    },
                },
                "required": ["auth_token", "files"],
            },
        ),
    ]


async def handle_file_upload_tool_call(
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """处理上传工具调用。"""
    if tool_name == "file_upload":
        return await _file_upload(arguments)
    return {"error": f"未知的工具: {tool_name}"}


async def _file_upload(args: dict[str, Any]) -> dict[str, Any]:
    """接收文件并保存（支持多文件，content 为 base64 编码）。"""
    try:
        import base64

        import chardet

        from auth.jwt_utils import get_user_from_token
        from security_utils import sanitize_path, validate_filename

        auth_token = args.get("auth_token", "")
        if not auth_token:
            return {"success": False, "error": "缺少 auth_token 参数"}

        user_info = get_user_from_token(auth_token)
        if not user_info:
            return {"success": False, "error": "无效的 auth_token"}

        files = args.get("files", [])
        if not files:
            return {"success": False, "error": "files 参数不能为空"}

        uploaded_files: list[dict[str, str]] = []
        errors: list[dict[str, Any]] = []

        now = datetime.now()
        date_dir = UPLOAD_DIR / str(now.year) / str(now.month) / str(now.day)
        date_dir.mkdir(parents=True, exist_ok=True)

        for idx, file_obj in enumerate(files):
            try:
                filename = file_obj.get("filename")
                content_b64 = file_obj.get("content")

                if not filename:
                    errors.append({"index": idx, "error": "缺少 filename 字段"})
                    continue
                if not content_b64:
                    errors.append({"index": idx, "filename": filename, "error": "缺少 content 字段"})
                    continue
                if not validate_filename(filename):
                    errors.append(
                        {"index": idx, "filename": filename, "error": "非法文件名，可能存在安全风险"}
                    )
                    continue

                file_ext = Path(filename).suffix.lower()
                if file_ext not in ALLOWED_EXTENSIONS:
                    errors.append(
                        {"index": idx, "filename": filename, "error": f"不支持的文件类型: {file_ext}"}
                    )
                    continue

                try:
                    file_content = base64.b64decode(content_b64)
                except Exception as exc:
                    errors.append(
                        {"index": idx, "filename": filename, "error": f"base64 解码失败: {exc}"}
                    )
                    continue

                max_file_size = int(os.getenv("MAX_FILE_SIZE", str(100 * 1024 * 1024)))
                if len(file_content) > max_file_size:
                    errors.append(
                        {
                            "index": idx,
                            "filename": filename,
                            "error": f"文件大小超过限制 ({max_file_size} bytes)",
                        }
                    )
                    continue

                timestamp = datetime.now().strftime("%H%M%S")
                safe_filename = Path(filename).name
                name_parts = safe_filename.rsplit(".", 1)
                if len(name_parts) == 2:
                    safe_filename = f"{name_parts[0]}_{timestamp}.{name_parts[1]}"
                else:
                    safe_filename = f"{safe_filename}_{timestamp}"

                file_path = sanitize_path(date_dir, safe_filename)
                if file_path is None:
                    errors.append(
                        {"index": idx, "filename": filename, "error": "非法文件路径，可能存在安全风险"}
                    )
                    continue

                if file_ext in [".csv", ".txt", ".tsv"]:
                    try:
                        detected = chardet.detect(file_content)
                        encoding = detected.get("encoding", "utf-8")
                        confidence = detected.get("confidence", 0)

                        if not encoding or confidence < 0.7:
                            for try_encoding in ["utf-8", "gbk", "gb2312", "gb18030", "latin1"]:
                                try:
                                    file_content.decode(try_encoding)
                                    encoding = try_encoding
                                    break
                                except (UnicodeDecodeError, LookupError):
                                    continue

                        if encoding:
                            try:
                                text_content = file_content.decode(encoding)
                                file_content = text_content.encode("utf-8-sig")
                            except (UnicodeDecodeError, LookupError) as exc:
                                logger.error(f"[编码转换] 解码失败 {filename}: {exc}")
                    except Exception as exc:
                        logger.error(f"[编码转换] 转换异常 {filename}: {exc}")

                with open(file_path, "wb") as file_handle:
                    file_handle.write(file_content)

                relative_path = file_path.relative_to(UPLOAD_DIR.parent)
                file_path_str = f"/{relative_path.as_posix()}"
                uploaded_files.append(
                    {
                        "original_filename": filename,
                        "file_path": file_path_str,
                    }
                )
            except Exception as exc:
                errors.append(
                    {
                        "index": idx,
                        "filename": file_obj.get("filename", "unknown"),
                        "error": f"处理失败: {exc}",
                    }
                )

        if not uploaded_files:
            return {
                "success": False,
                "uploaded_count": 0,
                "uploaded_files": [],
                "errors": errors,
            }

        result: dict[str, Any] = {
            "success": True,
            "uploaded_count": len(uploaded_files),
            "uploaded_files": uploaded_files,
        }
        if errors:
            result["errors"] = errors
            result["error_count"] = len(errors)
        return result
    except Exception as exc:
        logger.error(f"文件上传失败: {exc}", exc_info=True)
        return {"success": False, "error": f"文件上传失败: {exc}"}
