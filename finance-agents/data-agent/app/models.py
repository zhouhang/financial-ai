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
    UNKNOWN = "unknown"


class ReconciliationPhase(str, Enum):
    IDLE = "idle"
    FILE_ANALYSIS = "file_analysis"
    FIELD_MAPPING = "field_mapping"
    RULE_CONFIG = "rule_config"
    VALIDATION_PREVIEW = "validation_preview"
    SAVE_RULE = "save_rule"
    TASK_EXECUTION = "task_execution"
    COMPLETED = "completed"


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
# 对账规则类型条目（存储在 reconciliation_schemas.json 中）
# ---------------------------------------------------------------------------

class ReconciliationTypeEntry(BaseModel):
    name_cn: str
    type_key: str
    schema_path: str
    callback_url: str = ""


# ---------------------------------------------------------------------------
# 代理状态 – 用作 LangGraph 状态
# ---------------------------------------------------------------------------

class AgentState(TypedDict, total=False):
    """在主图和子图之间共享的顶级状态。"""

    # 对话
    messages: Annotated[Sequence[AnyMessage], operator.add]

    # 会话
    thread_id: str

    # 意图检测（第1层）
    user_intent: str  # UserIntent 值
    selected_rule_name: Optional[str]

    # 上传的文件
    uploaded_files: list[str]

    # 文件分析（第2层 – 步骤1）
    file_analyses: list[dict[str, Any]]

    # 字段映射（第2层 – 步骤2，HITL）
    suggested_mappings: dict[str, Any]
    confirmed_mappings: Optional[dict[str, Any]]

    # 规则配置（第2层 – 步骤3，HITL）
    rule_config_questions: list[dict[str, Any]]
    rule_config_answers: Optional[dict[str, Any]]

    # 生成的模式（第2层 – 步骤4）
    generated_schema: Optional[dict[str, Any]]

    # 预览（第2层 – 步骤4，HITL）
    preview_result: Optional[dict[str, Any]]

    # 保存的规则名称（第2层 – 步骤5）
    saved_rule_name: Optional[str]

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
