from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

ActionType = Literal[
    "login",
    "login_if_needed",
    "navigate",
    "click",
    "fill",
    "set_date",
    "set_range_calendar_day",
    "wait_for",
    "wait_ms",
    "extract_text",
    "extract_summary",
    "stop_if_summary_zero",
    "select_checkboxes",
    "download",
    "download_history_file",
    "download_qianniu_export_report",
    "parse_table",
    "paginate_capture_json",
    "assert",
]
ColumnType = Literal["string", "date", "decimal", "integer", "boolean"]
FailureReason = Literal["PAGE_CHANGED", "AUTH_EXPIRED", "RISK_VERIFICATION", "DATA_MISMATCH"]


class PlaybookTarget(BaseModel):
    platform: str
    business_object: str
    timezone: str


class PlaybookParamsSchemaProperty(BaseModel):
    type: Literal["date", "string", "integer", "number", "boolean"]
    format: str | None = None


class PlaybookParamsSchema(BaseModel):
    required: list[str] = Field(default_factory=list)
    properties: dict[str, PlaybookParamsSchemaProperty] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_biz_date(self) -> "PlaybookParamsSchema":
        if "biz_date" not in self.required:
            raise ValueError("params_schema must require biz_date")
        biz_date = self.properties.get("biz_date")
        if biz_date is None:
            raise ValueError("params_schema must define biz_date")
        if biz_date.type != "date" or biz_date.format != "YYYY-MM-DD":
            raise ValueError("params_schema.biz_date must be a YYYY-MM-DD date")
        return self


class PlaybookStep(BaseModel):
    id: str
    action: ActionType
    url: str | None = None
    selector: str | None = None
    value: str | None = None
    value_from: str | None = None
    timeout_ms: int | None = None
    mapping: dict[str, str] | None = None
    source: str | None = None
    format: Literal["csv", "xlsx"] | None = None
    skip_rows: int | None = None
    archive: Literal["zip"] | None = None
    drop_row_prefix: str | None = None
    header_selector: str | None = None
    day_cell_selector: str | None = None
    out_of_month_marker: str | None = None
    prev_month_selector: str | None = None
    next_month_selector: str | None = None
    confirm_selector: str | None = None
    capture_url_contains: str | None = None
    results_path: str | None = None
    total_path: str | None = None
    field_map: dict[str, str] | None = None
    next_selector: str | None = None
    trigger_selector: str | None = None
    max_pages: int | None = None
    page_wait_ms: int | None = None
    download_timeout_ms: int | None = None
    history_row_selector: str | None = None
    history_row_selectors: list[str] | None = None
    history_open_selector: str | None = None
    history_open_selectors: list[str] | None = None
    history_close_selector: str | None = None
    history_close_selectors: list[str] | None = None
    history_open_timeout_ms: int | None = None
    history_refresh_close_timeout_ms: int | None = None
    history_refresh_interval_ms: int | None = None
    history_completed_status_text: str | None = None
    history_download_selector: str | None = None
    duration_ms: int | None = None
    refresh_interval_ms: int | None = None
    allowed_labels: list[str] | None = None
    checked_labels: list[str] | None = None
    label_selector: str | None = None
    exact: bool | None = None
    record_time_as: str | None = None
    requested_after_from: str | None = None
    report_type: str | None = None
    download_button_text: str | None = None
    refresh_selector: str | None = None
    request_time_tolerance_seconds: int | None = None
    username_selector: str | None = None
    password_selector: str | None = None
    submit_selector: str | None = None
    username_value: str | None = None
    password_value: str | None = None
    username_value_from: str | None = None
    password_value_from: str | None = None
    post_login_wait_selector: str | None = None
    summary_field: str | None = None
    record_as: str | None = None

    @model_validator(mode="after")
    def validate_action_contract(self) -> "PlaybookStep":
        if not self.id.strip():
            raise ValueError("step.id cannot be empty")
        if self.action == "navigate" and not str(self.url or "").startswith(("http://", "https://")):
            raise ValueError("navigate requires an absolute URL")
        if self.action in {"login", "login_if_needed"}:
            if (
                not str(self.username_selector or "").strip()
                or not str(self.password_selector or "").strip()
                or not str(self.submit_selector or "").strip()
            ):
                raise ValueError(f"{self.action} requires username/password/submit selectors")
            if not (
                str(self.username_value or "").strip()
                or str(self.username_value_from or "").strip()
            ):
                raise ValueError(f"{self.action} requires username_value or username_value_from")
            if not (
                str(self.password_value or "").strip()
                or str(self.password_value_from or "").strip()
            ):
                raise ValueError(f"{self.action} requires password_value or password_value_from")
        if self.action in {
            "click",
            "fill",
            "set_date",
            "set_range_calendar_day",
            "wait_for",
            "extract_text",
            "download",
            "download_history_file",
            "download_qianniu_export_report",
        }:
            if not str(self.selector or "").strip():
                raise ValueError(f"{self.action} requires selector")
        if self.action == "wait_ms" and (self.duration_ms is None or self.duration_ms <= 0):
            raise ValueError("wait_ms requires positive duration_ms")
        if self.action == "select_checkboxes":
            labels = self.checked_labels if self.checked_labels is not None else self.allowed_labels
            if not str(self.selector or "").strip():
                raise ValueError("select_checkboxes requires selector")
            if not labels:
                raise ValueError("select_checkboxes requires checked_labels or allowed_labels")
        if self.action == "set_date":
            has_biz_date_value = "{{params.biz_date}}" in str(self.value or "")
            if self.value_from != "params.biz_date" and not has_biz_date_value:
                raise ValueError("set_date must use value_from=params.biz_date or value with {{params.biz_date}}")
        if self.action == "set_range_calendar_day":
            has_biz_date_value = "{{params.biz_date}}" in str(self.value or "")
            if self.value_from != "params.biz_date" and not has_biz_date_value:
                raise ValueError(
                    "set_range_calendar_day must use value_from=params.biz_date or value with {{params.biz_date}}"
                )
        if self.action == "download_history_file" and self.value_from != "params.biz_date":
            raise ValueError("download_history_file must use value_from=params.biz_date")
        if self.action == "download_qianniu_export_report":
            if not str(self.requested_after_from or "").strip():
                raise ValueError("download_qianniu_export_report requires requested_after_from")
            if not str(self.download_button_text or "").strip():
                raise ValueError("download_qianniu_export_report requires download_button_text")
        if self.action == "extract_summary" and not self.mapping:
            raise ValueError("extract_summary requires mapping")
        if self.action == "parse_table":
            if self.source != "last_download" or self.format not in {"csv", "xlsx"}:
                raise ValueError("parse_table requires source=last_download and format csv/xlsx")
        return self


class PlaybookColumn(BaseModel):
    name: str
    type: ColumnType
    required: bool = True
    semantic_name: str = ""


class PlaybookOutput(BaseModel):
    record_type: Literal["browser_collection_records"]
    item_key_fields: list[str]
    columns: list[PlaybookColumn]

    @model_validator(mode="after")
    def validate_item_key_fields(self) -> "PlaybookOutput":
        column_names = {column.name for column in self.columns}
        missing = [field for field in self.item_key_fields if field not in column_names]
        if missing:
            raise ValueError(f"item_key_fields missing from output.columns: {missing}")
        return self


class PlaybookQualityGate(BaseModel):
    date_field: str
    amount_field: str
    summary_step_id: str
    row_count_field: str = "row_count"
    amount_total_field: str = "amount_total"
    row_count_equals_summary: bool = True
    amount_sum_equals_summary: bool = True
    amount_precision: int = 2
    zero_tolerance: bool = True


class AccountingPolicy(BaseModel):
    date_basis: str
    amount_sign: Literal["source_signed"] = "source_signed"
    included_business_types: list[str]


class FailureMapping(BaseModel):
    selector_missing: FailureReason = "PAGE_CHANGED"
    auth_redirect: FailureReason = "AUTH_EXPIRED"
    risk_verification: FailureReason = "RISK_VERIFICATION"
    quality_mismatch: FailureReason = "DATA_MISMATCH"


class PlaybookAuthCheck(BaseModel):
    logged_in_selector: str = ""
    timeout_ms: int = 5000

    @model_validator(mode="after")
    def validate_auth_check(self) -> "PlaybookAuthCheck":
        if self.timeout_ms <= 0:
            raise ValueError("auth_check.timeout_ms must be positive")
        return self


class PlaybookOverlay(BaseModel):
    id: str
    markers: list[str]
    close_selectors: list[str]

    @model_validator(mode="after")
    def validate_overlay(self) -> "PlaybookOverlay":
        if not self.id.strip():
            raise ValueError("overlays.id cannot be empty")
        self.markers = [selector.strip() for selector in self.markers if selector.strip()]
        self.close_selectors = [
            selector.strip()
            for selector in self.close_selectors
            if selector.strip()
        ]
        if not self.markers:
            raise ValueError("overlays.markers cannot be empty")
        if not self.close_selectors:
            raise ValueError("overlays.close_selectors cannot be empty")
        return self


class PlaybookBody(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    playbook_id: str
    title: str
    target: PlaybookTarget
    params_schema: PlaybookParamsSchema
    steps: list[PlaybookStep]
    output: PlaybookOutput
    quality_gate: PlaybookQualityGate
    accounting_policy: AccountingPolicy
    failure_mapping: FailureMapping
    auth_check: PlaybookAuthCheck = Field(default_factory=PlaybookAuthCheck)
    overlays: list[PlaybookOverlay] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_cross_references(self) -> "PlaybookBody":
        step_ids = [step.id for step in self.steps]
        if not step_ids:
            raise ValueError("steps cannot be empty")
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("steps.id must be unique")
        if self.quality_gate.summary_step_id not in set(step_ids):
            raise ValueError("quality_gate.summary_step_id must reference a step.id")
        column_names = {column.name for column in self.output.columns}
        for field_name in [self.quality_gate.date_field, self.quality_gate.amount_field]:
            if field_name not in column_names:
                raise ValueError(f"quality_gate field missing from output.columns: {field_name}")
        return self


class RunPlaybookMessage(BaseModel):
    job_id: str
    shop_id: str
    playbook_id: str
    playbook_version: str
    playbook_body: PlaybookBody
    params: dict[str, Any]
    runtime_profile_ref: str
    egress_group: str = ""
    credential_ref: str = ""
    timeout_ms: int = 900_000

    @model_validator(mode="after")
    def validate_params(self) -> "RunPlaybookMessage":
        biz_date = str(self.params.get("biz_date") or "")
        if len(biz_date) != 10 or biz_date[4] != "-" or biz_date[7] != "-":
            raise ValueError("params.biz_date must use YYYY-MM-DD")
        return self


class BrowserRecord(BaseModel):
    item_key: str
    item_key_values: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any]


class CaptureFile(BaseModel):
    storage_path: str
    encoding: str = ""
    checksum: str = ""
    row_count: int = 0


class TaskResult(BaseModel):
    job_id: str
    status: Literal["success", "failed"]
    fail_reason: str = ""
    records: list[BrowserRecord] = Field(default_factory=list)
    capture_files: list[CaptureFile] = Field(default_factory=list)
    quality_summary: dict[str, Any] = Field(default_factory=dict)
    error_info: dict[str, Any] = Field(default_factory=dict)
