"""代理状态和数据模式的 Pydantic / TypedDict 模型。"""

from __future__ import annotations

import operator
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal, Optional, Sequence

from langchain_core.messages import AnyMessage
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


# ---------------------------------------------------------------------------
# 枚举
# ---------------------------------------------------------------------------

class UserIntent(str, Enum):
    USE_EXISTING_RULE = "use_existing_rule"
    CREATE_NEW_RULE = "create_new_rule"
    EDIT_RULE = "edit_rule"  # 调整/编辑已有规则
    RESUME_WORKFLOW = "resume_workflow"  # 继续当前 workflow
    LOGIN = "login"
    REGISTER = "register"
    # 管理员相关
    ADMIN_LOGIN = "admin_login"
    ADMIN_VIEW = "admin_view"
    CREATE_COMPANY = "create_company"
    CREATE_DEPARTMENT = "create_department"
    ADMIN_LOGOUT = "admin_logout"
    UNKNOWN = "unknown"
    PROC = "proc"              # 数据整理
    RECON = "recon"            # 对账执行


class ReconciliationPhase(str, Enum):
    IDLE = "idle"
    FILE_ANALYSIS = "file_analysis"
    FIELD_MAPPING = "field_mapping"
    RULE_RECOMMENDATION = "rule_recommendation"
    RULE_CONFIG = "rule_config"
    VALIDATION_PREVIEW = "validation_preview"
    RESULT_EVALUATION = "result_evaluation"  # 对账结果评估
    # 编辑规则流程
    EDIT_FIELD_MAPPING = "edit_field_mapping"
    EDIT_RULE_CONFIG = "edit_rule_config"
    EDIT_VALIDATION_PREVIEW = "edit_validation_preview"
    EDIT_SAVE = "edit_save"
    TASK_EXECUTION = "task_execution"
    COMPLETED = "completed"


class ProcAgentPhase(str, Enum):
    """数据整理子图（proc_agent）的阶段枚举。"""
    IDLE = "idle"
    GETTING_RULE = "getting_rule"          # 正在读取规则
    RULE_NOT_FOUND = "rule_not_found"      # 规则不存在
    CHECKING_FILES = "checking_files"      # 正在校验文件
    FILE_CHECK_FAILED = "file_check_failed" # 文件校验失败
    EXECUTING = "executing"                # 正在执行整理
    SHOWING_RESULT = "showing_result"      # 展示结果
    COMPLETED = "completed"                # 已完成


class ReconAgentPhase(str, Enum):
    """对账执行子图（recon_agent）的阶段枚举。"""
    IDLE = "idle"
    GETTING_RULE = "getting_rule"          # 正在读取规则
    RULE_NOT_FOUND = "rule_not_found"      # 规则不存在
    CHECKING_FILES = "checking_files"      # 正在校验文件
    FILE_CHECK_FAILED = "file_check_failed" # 文件校验失败
    EXECUTING = "executing"                # 正在执行对账
    EXEC_FAILED = "exec_failed"            # 对账执行失败
    SHOWING_RESULT = "showing_result"      # 展示结果
    COMPLETED = "completed"                # 已完成


class TaskExecutionStep(str, Enum):
    NOT_STARTED = "not_started"
    STARTING = "starting"
    POLLING = "polling"
    SHOWING_RESULT = "showing_result"
    DONE = "done"


# ---------------------------------------------------------------------------
# Pydantic 模型 – 规则/模式相关
# ---------------------------------------------------------------------------

class FieldMapping(BaseModel):
    """单个字段-角色映射：原始列名 -> 标准角色。"""
    role: str = Field(description="标准角色名称，例如 order_id, amount")
    original_field: str = Field(description="文件中的原始列名")
    source: Literal["business", "finance"] = Field(description="哪个数据源")


class FieldTransform(BaseModel):
    field: str
    operation: str
    value: Optional[Any] = None
    decimals: Optional[int] = None
    expression: Optional[str] = None
    condition: Optional[str] = None
    description: str = ""


class RowFilter(BaseModel):
    condition: str
    description: str = ""


class Aggregation(BaseModel):
    group_by: str | list[str]
    agg_fields: dict[str, str]
    description: str = ""


class GlobalTransform(BaseModel):
    operation: str
    subset: Optional[list[str]] = None
    keep: Optional[str] = None
    description: str = ""


class DataCleaningRules(BaseModel):
    field_transforms: list[FieldTransform] = Field(default_factory=list)
    row_filters: list[RowFilter] = Field(default_factory=list)
    aggregations: list[Aggregation] = Field(default_factory=list)
    global_transforms: list[GlobalTransform] = Field(default_factory=list)


class CustomValidation(BaseModel):
    name: str
    condition_expr: str
    issue_type: str
    detail_template: str


class DataSourceConfig(BaseModel):
    file_pattern: list[str] = Field(default_factory=list)
    field_roles: dict[str, str | list[str]] = Field(default_factory=dict)


class ReconciliationSchema(BaseModel):
    """完整的对账模式，镜像 finance-mcp 使用的 JSON 模式。"""
    version: str = "1.0"
    description: str = ""
    data_sources: dict[str, DataSourceConfig] = Field(default_factory=dict)
    key_field_role: str = "order_id"
    tolerance: dict[str, Any] = Field(default_factory=dict)
    data_cleaning_rules: dict[str, DataCleaningRules] = Field(default_factory=dict)
    custom_validations: list[CustomValidation] = Field(default_factory=list)


class RuleConfigAnswers(BaseModel):
    """从 HITL 规则配置步骤收集的答案。"""
    order_id_pattern: Optional[str] = None
    amount_tolerance: float = 0.1
    check_order_status: bool = True


class FileAnalysisResult(BaseModel):
    """分析上传文件的结果。"""
    filename: str
    columns: list[str] = Field(default_factory=list)
    row_count: int = 0
    sample_data: list[dict[str, Any]] = Field(default_factory=list)
    guessed_source: Optional[Literal["business", "finance"]] = None


class PreviewResult(BaseModel):
    matched: int = 0
    differences: int = 0
    missing_in_business: int = 0
    missing_in_finance: int = 0
    sample_issues: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 代理状态 – 用作 LangGraph 状态
# ---------------------------------------------------------------------------

class AgentState(TypedDict, total=False):
    """在主图和子图之间共享的顶级状态。"""

    # 对话
    messages: Annotated[Sequence[AnyMessage], operator.add]

    # 会话
    thread_id: str
    workflow_type: Optional[str]   # 当前工作流类型
    workflow_run_id: Optional[str]  # 当前工作流运行ID（用于文件与缓存隔离）

    # ── 认证 ──────────────────────────────────────────────────
    auth_token: Optional[str]         # JWT token
    current_user: Optional[dict]      # 当前登录用户信息
    
    # ── 管理员 ────────────────────────────────────────────────
    admin_token: Optional[str]        # 管理员 token
    admin_data: Optional[dict]        # 管理员数据（公司部门员工）

    # 意图检测（第1层）
    user_intent: str  # UserIntent 值
    selected_task_code: Optional[str]  # 选中的任务类型，如 "proc" / "recon"
    selected_rule_name: Optional[str]
    selected_rule_code: Optional[str]  # 选中的任务编码，如 "verif_recog"
    file_rule_code: Optional[str]  # 文件校验规则编码，从 rule_detail.rule 中解析

    # 上传的文件
    uploaded_files: list[str]
    
    # 历史工作流上下文字段，保留兼容
    reconciliation_ctx: Optional[dict[str, Any]]
    data_preparation_ctx: Optional[dict[str, Any]]

    # 对账分析缓存/中断控制（兼容字段，后续逐步迁移到 reconciliation_ctx）
    analysis_key: Optional[str]
    analysis_cache: Optional[dict[str, Any]]
    pending_interrupt: Optional[dict[str, Any]]

    # 当前阶段跟踪
    phase: str  # ReconciliationPhase 值

    # 任务执行（第3层）
    task_id: Optional[str]
    task_status: Optional[str]
    task_result: Optional[dict[str, Any]]
    execution_step: str  # TaskExecutionStep 值

    # 人工参与循环标志
    waiting_for_human: bool
    human_prompt: Optional[str]

    # ── proc 数据整理子图上下文 ─────────────────────────────────────────
    proc_ctx: Optional[dict[str, Any]]

    # ── recon 对账执行子图上下文 ───────────────────────────────────────────
    # 与 proc_ctx 并列，完全隔离
    recon_ctx: Optional[dict[str, Any]]
