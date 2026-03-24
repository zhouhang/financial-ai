"""proc 模块配置。"""
from __future__ import annotations

import os
from pathlib import Path

# ── 输出目录 ──────────────────────────────────────────────────────────────────
# 默认指向 finance-mcp/proc/output/，可通过环境变量 PROC_OUTPUT_DIR 覆盖。
OUTPUT_DIR: str = os.getenv(
    "PROC_OUTPUT_DIR",
    str(Path(__file__).resolve().parents[1] / "output"),
)
