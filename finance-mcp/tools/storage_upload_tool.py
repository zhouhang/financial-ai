"""OSS/local upload presign and confirm MCP tools."""
from __future__ import annotations

import logging
import mimetypes
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp import Tool

from auth.jwt_utils import get_user_from_token
from security_utils import validate_filename
from storage import repository
from storage.client import OssStorageClient
from storage.config import StorageSettings
from storage.refs import StorageObjectRef

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".xlsm", ".xlsb"}


def create_storage_upload_tools() -> list[Tool]:
    """创建存储上传 MCP 工具。"""
    return [
        Tool(
            name="file_upload_presign",
            description="为文件上传创建预签名信息；OSS 后端返回直传 PUT 信息，本地后端回退到 file_upload。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string", "description": "JWT token，用于校验用户身份"},
                    "filename": {"type": "string", "description": "原始文件名"},
                    "size_bytes": {"type": "integer", "description": "文件大小（字节）"},
                    "size": {"type": "integer", "description": "文件大小（字节），兼容前端字段"},
                    "content_type": {"type": "string", "description": "文件 MIME 类型，可选"},
                },
                "required": ["auth_token", "filename"],
            },
        ),
        Tool(
            name="file_upload_confirm",
            description="确认 OSS 直传文件已存在，并登记上传文件元数据。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string", "description": "JWT token，用于校验用户身份"},
                    "storage_key": {"type": "string", "description": "OSS 对象 key"},
                    "filename": {"type": "string", "description": "原始文件名"},
                    "size_bytes": {"type": "integer", "description": "文件大小（字节）"},
                    "size": {"type": "integer", "description": "文件大小（字节），兼容前端字段"},
                    "content_type": {"type": "string", "description": "文件 MIME 类型，可选"},
                    "checksum": {"type": "string", "description": "文件校验和，可选"},
                },
                "required": ["auth_token", "storage_key", "filename"],
            },
        ),
    ]


def create_tools() -> list[Tool]:
    """兼容 tools 模块常用命名。"""
    return create_storage_upload_tools()


async def handle_tool_call(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """处理存储上传工具调用。"""
    if tool_name == "file_upload_presign":
        return await create_upload_presign(arguments)
    if tool_name == "file_upload_confirm":
        return await confirm_upload(arguments)
    return {"error": f"未知的工具: {tool_name}"}


async def handle_storage_upload_tool_call(
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """兼容统一 MCP 服务器的命名约定。"""
    return await handle_tool_call(tool_name, arguments)


async def create_upload_presign(args: dict[str, Any]) -> dict[str, Any]:
    """创建文件上传预签名信息。"""
    try:
        user_info, auth_error = _get_authenticated_user(args)
        if auth_error:
            return auth_error

        settings = StorageSettings.from_env()
        validated, validation_error = _validate_upload_request(args, settings)
        if validation_error:
            return validation_error

        filename = validated["filename"]
        size_bytes = validated["size_bytes"]
        content_type = validated["content_type"]

        if settings.backend == "local":
            return {
                "success": True,
                "direct_upload": False,
                "storage_provider": "local",
                "upload_tool": "file_upload",
                "filename": filename,
                "content_type": content_type,
                "size_bytes": size_bytes,
                "max_size_bytes": settings.oss_upload_max_size,
                "message": "当前为本地存储，请继续使用 file_upload 代理上传。",
            }

        if settings.backend != "oss":
            return {"success": False, "error": f"不支持的存储后端: {settings.backend}"}

        try:
            settings.require_oss_ready()
        except RuntimeError as exc:
            return {"success": False, "error": str(exc)}

        company_id = _get_company_id(user_info)
        if not company_id:
            return {"success": False, "error": "当前用户未绑定公司，无法创建 OSS 上传路径"}
        if not _validate_storage_path_segment(company_id):
            return {"success": False, "error": "非法 company_id，无法创建 OSS 上传路径"}

        storage_key = _build_oss_upload_key(settings, company_id, filename)
        presigned_upload = OssStorageClient(settings).create_presigned_upload(
            key=storage_key,
            content_type=content_type,
        )

        return {
            "success": True,
            "direct_upload": True,
            "storage_provider": "oss",
            "storage_bucket": settings.oss_bucket,
            "storage_key": storage_key,
            "key": presigned_upload.get("key", storage_key),
            "url": presigned_upload.get("url", ""),
            "headers": presigned_upload.get("headers", {}),
            "filename": filename,
            "content_type": content_type,
            "size_bytes": size_bytes,
            "max_size_bytes": settings.oss_upload_max_size,
            "upload": presigned_upload,
            "presigned_upload": presigned_upload,
            **(
                {"method": presigned_upload["method"]}
                if presigned_upload.get("method") is not None
                else {}
            ),
        }
    except Exception as exc:
        logger.error(f"创建上传预签名失败: {exc}", exc_info=True)
        return {"success": False, "error": f"创建上传预签名失败: {exc}"}


async def confirm_upload(args: dict[str, Any]) -> dict[str, Any]:
    """确认 OSS 直传完成并保存元数据。"""
    try:
        user_info, auth_error = _get_authenticated_user(args)
        if auth_error:
            return auth_error

        settings = StorageSettings.from_env()
        if settings.backend != "oss":
            return {"success": False, "error": "file_upload_confirm 仅支持 OSS 存储后端"}

        try:
            settings.require_oss_ready()
        except RuntimeError as exc:
            return {"success": False, "error": str(exc)}

        validated, validation_error = _validate_upload_request(args, settings)
        if validation_error:
            return validation_error

        company_id = _get_company_id(user_info)
        if not company_id:
            return {"success": False, "error": "当前用户未绑定公司，无法确认 OSS 上传"}
        if not _validate_storage_path_segment(company_id):
            return {"success": False, "error": "非法 company_id，无法确认 OSS 上传"}

        storage_key = str(args.get("storage_key") or args.get("key") or "").strip().lstrip("/")
        if not storage_key:
            return {"success": False, "error": "缺少 storage_key 参数"}
        if ".." in storage_key.split("/"):
            return {"success": False, "error": "非法 storage_key，可能存在安全风险"}

        upload_prefix = _company_upload_prefix(settings, company_id)
        if not storage_key.startswith(upload_prefix):
            return {"success": False, "error": "storage_key 不属于当前公司上传目录"}

        filename = validated["filename"]
        size_bytes = validated["size_bytes"]
        content_type = validated["content_type"]
        checksum = str(args.get("checksum") or "").strip()
        ref = StorageObjectRef(
            provider="oss",
            bucket=settings.oss_bucket,
            key=storage_key,
            original_filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
            checksum=checksum,
        )

        if not _oss_object_exists(ref, settings):
            return {"success": False, "error": "OSS 对象不存在，无法确认上传"}

        relative_key = storage_key[len(upload_prefix) :].lstrip("/")
        logical_path = f"/uploads/oss/{company_id}/{relative_key}"
        repository.save_storage_object_metadata(
            owner_user_id=_get_user_id(user_info),
            company_id=company_id,
            module="upload",
            logical_path=logical_path,
            ref=ref,
            metadata={
                "source": "file_upload_confirm",
                "storage_key": storage_key,
            },
        )

        return {
            "success": True,
            "logical_path": logical_path,
            "file_path": logical_path,
            "storage_provider": "oss",
            "storage_bucket": settings.oss_bucket,
            "storage_key": storage_key,
            "original_filename": filename,
            "content_type": content_type,
            "size_bytes": size_bytes,
        }
    except Exception as exc:
        logger.error(f"确认 OSS 上传失败: {exc}", exc_info=True)
        return {"success": False, "error": f"确认 OSS 上传失败: {exc}"}


def _get_authenticated_user(args: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    auth_token = str(args.get("auth_token") or "").strip()
    if not auth_token:
        return None, {"success": False, "error": "缺少 auth_token 参数"}

    user_info = get_user_from_token(auth_token)
    if not user_info:
        return None, {"success": False, "error": "无效的 auth_token"}
    return user_info, None


def _validate_upload_request(
    args: dict[str, Any],
    settings: StorageSettings,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    filename = str(args.get("filename") or "").strip()
    if not filename:
        return {}, {"success": False, "error": "缺少 filename 参数"}
    if not validate_filename(filename):
        return {}, {"success": False, "error": "非法文件名，可能存在安全风险"}

    safe_filename = Path(filename).name
    file_ext = Path(safe_filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        return {}, {"success": False, "error": f"不支持的文件类型: {file_ext}"}

    try:
        raw_size = _first_present_arg(args, "size_bytes", "size", "file_size", "content_length")
        size_bytes = int(raw_size)
    except (TypeError, ValueError):
        return {}, {"success": False, "error": "缺少或非法的 size/size_bytes 参数"}

    if size_bytes < 0:
        return {}, {"success": False, "error": "size_bytes 不能小于 0"}
    if size_bytes > settings.oss_upload_max_size:
        return (
            {},
            {
                "success": False,
                "error": f"文件大小超过限制 ({settings.oss_upload_max_size} bytes)",
            },
        )

    return (
        {
            "filename": safe_filename,
            "size_bytes": size_bytes,
            "content_type": _resolve_content_type(
                safe_filename,
                str(args.get("content_type") or "").strip(),
            ),
        },
        None,
    )


def _first_present_arg(args: dict[str, Any], *names: str) -> Any:
    for name in names:
        if args.get(name) is not None:
            return args.get(name)
    return None


def _resolve_content_type(filename: str, content_type: str = "") -> str:
    return content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"


def _get_user_id(user_info: dict[str, Any]) -> str:
    return str(user_info.get("user_id") or user_info.get("id") or "").strip()


def _get_company_id(user_info: dict[str, Any]) -> str:
    return str(user_info.get("company_id") or "").strip()


def _validate_storage_path_segment(value: str) -> bool:
    if not value:
        return False
    return "/" not in value and "\\" not in value and ".." not in value


def _company_upload_prefix(settings: StorageSettings, company_id: str) -> str:
    oss_prefix = settings.oss_prefix.strip("/")
    if oss_prefix:
        return f"{oss_prefix}/uploads/{company_id}/"
    return f"uploads/{company_id}/"


def _build_oss_upload_key(settings: StorageSettings, company_id: str, filename: str) -> str:
    now = datetime.now()
    return (
        f"{_company_upload_prefix(settings, company_id)}"
        f"{now:%Y/%m/%d}/{uuid.uuid4()}-{filename}"
    )


def _oss_object_exists(ref: StorageObjectRef, settings: StorageSettings) -> bool:
    """检查 OSS 对象是否存在；独立函数便于测试 monkeypatch。"""
    return OssStorageClient(settings).exists(ref)
