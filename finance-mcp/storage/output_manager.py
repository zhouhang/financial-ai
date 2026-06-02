from __future__ import annotations

import mimetypes
import os
from datetime import datetime
from logging import Logger
from pathlib import Path
from urllib.parse import quote

from storage import repository
from storage.client import storage_from_env
from storage.config import StorageSettings


def _today_parts() -> tuple[str, str, str]:
    now = datetime.now()
    return now.strftime("%Y"), now.strftime("%m"), now.strftime("%d")


def _logical_output_path(output_path: str | Path, *, module: str, rule_code: str) -> str:
    filename = Path(output_path).name
    if module == "recon":
        return f"/output/recon/{filename}"
    if module == "proc":
        clean_rule_code = str(rule_code or "").strip().strip("/")
        return f"/output/proc/{clean_rule_code}/{filename}"
    raise ValueError(f"unsupported output module: {module}")


def _local_root_for_module(module: str) -> Path:
    if module == "recon":
        from recon.mcp_server.recon_tool import RECON_OUTPUT_DIR

        return Path(RECON_OUTPUT_DIR)
    if module == "proc":
        from proc.config.config import OUTPUT_DIR

        return Path(OUTPUT_DIR)
    raise ValueError(f"unsupported output module: {module}")


def _join_storage_key(*parts: str) -> str:
    segments: list[str] = []
    for part in parts:
        for segment in str(part or "").strip().strip("/").split("/"):
            if segment:
                segments.append(segment)
    return "/".join(segments)


def persist_generated_output(
    output_path: str | Path,
    *,
    module: str,
    owner_user_id: str | None,
    company_id: str | None,
    rule_code: str,
    run_id: str = "",
) -> str:
    """Persist generated output to OSS when enabled and return its logical path."""
    clean_module = str(module or "").strip()
    local_path = Path(output_path)
    logical_path = _logical_output_path(local_path, module=clean_module, rule_code=rule_code)

    if os.getenv("STORAGE_BACKEND", "local").strip().lower() != "oss":
        return logical_path

    settings = StorageSettings.from_env()
    filename = local_path.name
    year, month, day = _today_parts()
    output_kind = "recon-output" if clean_module == "recon" else "proc-output"
    clean_company_id = str(company_id or "").strip().strip("/") or "unknown-company"
    clean_run_id = str(run_id or "").strip().strip("/") or "manual"
    key = _join_storage_key(
        settings.oss_prefix,
        output_kind,
        clean_company_id,
        year,
        month,
        day,
        clean_run_id,
        filename,
    )
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    client = storage_from_env(local_root=_local_root_for_module(clean_module))
    ref = client.put_file(
        local_path,
        key=key,
        original_filename=filename,
        content_type=content_type,
    )
    repository.save_storage_object_metadata(
        owner_user_id=owner_user_id,
        company_id=company_id,
        module=clean_module,
        logical_path=logical_path,
        ref=ref,
        metadata={"rule_code": rule_code, "run_id": run_id},
    )
    return logical_path


def persist_generated_output_safely(
    output_path: str | Path,
    *,
    module: str,
    owner_user_id: str | None,
    company_id: str | None,
    rule_code: str,
    run_id: str = "",
    logger: Logger | None = None,
) -> str:
    """Persist generated output without failing the completed local run."""
    try:
        return persist_generated_output(
            output_path,
            module=module,
            owner_user_id=owner_user_id,
            company_id=company_id,
            rule_code=rule_code,
            run_id=run_id,
        )
    except Exception as exc:
        if logger:
            logger.error(
                "生成文件持久化到对象存储失败，回退本地下载: module=%s path=%s error=%s",
                module,
                output_path,
                exc,
                exc_info=True,
            )
        return ""


def build_output_download_url(base_url: str, logical_path: str, auth_token: str) -> str:
    """Build an output download URL with each path segment RFC3986-encoded."""
    clean_logical_path = str(logical_path or "").strip()
    if not clean_logical_path.startswith("/output/"):
        raise ValueError(f"invalid output logical path: {logical_path}")
    encoded_path = "/".join(
        quote(segment, safe="")
        for segment in clean_logical_path.removeprefix("/output/").split("/")
        if segment
    )
    return f"{str(base_url).rstrip('/')}/output/{encoded_path}?auth_token={quote(str(auth_token or ''), safe='')}"
