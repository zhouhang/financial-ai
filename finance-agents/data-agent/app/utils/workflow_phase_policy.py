"""Workflow phase policy helpers for chat entry routing."""

from __future__ import annotations

import re

from app.models import ReconciliationPhase

# 目前仅注册对账工作流；后续新增 data_preparation 时在此扩展即可。
RECONCILIATION_WORKFLOW_PHASES: set[str] = {
    ReconciliationPhase.FILE_ANALYSIS.value,
    ReconciliationPhase.FIELD_MAPPING.value,
    ReconciliationPhase.RULE_RECOMMENDATION.value,
    ReconciliationPhase.RULE_CONFIG.value,
    ReconciliationPhase.VALIDATION_PREVIEW.value,
    ReconciliationPhase.SAVE_RULE.value,
    ReconciliationPhase.RESULT_EVALUATION.value,
    ReconciliationPhase.EDIT_FIELD_MAPPING.value,
    ReconciliationPhase.EDIT_RULE_CONFIG.value,
    ReconciliationPhase.EDIT_VALIDATION_PREVIEW.value,
    ReconciliationPhase.EDIT_SAVE.value,
}

FILE_UPLOAD_PATTERNS: tuple[str, ...] = (
    r"已上传\s*\d+\s*个文件",
    r"上传了\s*\d+\s*个文件",
    r"文件已上传",
    r"请处理.*文件",
)

INTENT_SWITCH_PATTERNS: tuple[str, ...] = (
    r"^\s*(取消|退出|结束|停止)\s*(对账|流程|创建规则|编辑规则)?\s*$",
    r"^\s*(去|跳转到|切换到)\s*(数据准备|对账|规则列表|我的规则)\s*$",
    r"^\s*(查看|列出)\s*(规则|规则列表|我的规则)\s*$",
    r"^\s*(删除|删掉)\s*\S+",
    r"^\s*(新建|创建)\s*(规则|对账规则)",
)

RESET_ALLOWED_PHASES: set[str] = {
    "",
    ReconciliationPhase.FILE_ANALYSIS.value,
    ReconciliationPhase.COMPLETED.value,
}


def is_workflow_phase(phase: str) -> bool:
    """Return True if phase belongs to a registered workflow."""
    return phase in RECONCILIATION_WORKFLOW_PHASES


def is_file_upload_message(user_msg: str) -> bool:
    """Best-effort check for frontend file-upload stub message."""
    lowered = (user_msg or "").lower()
    return any(re.search(pattern, lowered) for pattern in FILE_UPLOAD_PATTERNS)


def should_check_intent_switch(user_msg: str) -> bool:
    """Only check switch intent for explicit switch-like commands."""
    text = user_msg or ""
    return any(re.search(pattern, text) for pattern in INTENT_SWITCH_PATTERNS)


def can_reset_analysis_state(phase: str) -> bool:
    """Whether file-change can clear analysis/mapping state in this phase."""
    return phase in RESET_ALLOWED_PHASES

