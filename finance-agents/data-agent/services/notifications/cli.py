"""CLI execution helpers for notification adapters."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class CLIExecutionResult:
    success: bool
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    command: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)
    timed_out: bool = False


class SubprocessCLIExecutor:
    """Run local CLI commands via subprocess with JSON payload extraction."""

    def __init__(self, *, encoding: str = "utf-8"):
        self._encoding = encoding

    def run(
        self,
        args: list[str],
        timeout_seconds: float,
        *,
        env: dict[str, str] | None = None,
    ) -> CLIExecutionResult:
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        try:
            completed = subprocess.run(
                args,
                check=False,
                capture_output=True,
                text=True,
                encoding=self._encoding,
                errors="replace",
                timeout=timeout_seconds,
                env=merged_env,
            )
            stdout = (completed.stdout or "").strip()
            stderr = (completed.stderr or "").strip()
            payload = _parse_payload(stdout)
            return CLIExecutionResult(
                success=(completed.returncode == 0),
                exit_code=completed.returncode,
                stdout=stdout,
                stderr=stderr,
                command=list(args),
                payload=payload,
            )
        except FileNotFoundError as exc:
            return CLIExecutionResult(
                success=False,
                exit_code=127,
                stderr=str(exc),
                command=list(args),
            )
        except OSError as exc:
            return CLIExecutionResult(
                success=False,
                exit_code=126,
                stderr=str(exc),
                command=list(args),
            )
        except subprocess.TimeoutExpired as exc:
            stdout = _normalize_timeout_output(exc.stdout)
            stderr = _normalize_timeout_output(exc.stderr)
            return CLIExecutionResult(
                success=False,
                exit_code=124,
                stdout=stdout,
                stderr=stderr or f"Command timed out after {timeout_seconds} seconds",
                command=list(args),
                payload=_parse_payload(stdout),
                timed_out=True,
            )


def _parse_payload(stdout: str) -> dict[str, Any]:
    """Try parsing stdout as JSON payload."""
    if not stdout:
        return {}

    text = stdout.strip()
    candidates: list[str] = [text]
    for index, char in enumerate(text):
        if char in "[{":
            candidates.append(text[index:].strip())
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        if line[:1] in "[{":
            candidates.append(line)

    for item in reversed(candidates):
        try:
            parsed = json.loads(item)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list):
            return {"items": parsed}
    return {}


def _normalize_timeout_output(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    return str(value).strip()
