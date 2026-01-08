"""
数据模型定义
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class IssueType(str, Enum):
    """问题类型"""
    AMOUNT_MISMATCH = "amount_mismatch"
    DATE_MISMATCH = "date_mismatch"
    MISSING_IN_FINANCE = "missing_in_finance"
    MISSING_IN_BUSINESS = "missing_in_business"
    CUSTOM = "custom"
    SKIPPED = "skipped"


@dataclass
class ReconciliationIssue:
    """对账问题"""
    order_id: str
    issue_type: str
    business_value: Optional[Any] = None
    finance_value: Optional[Any] = None
    detail: str = ""
    
    def to_dict(self) -> Dict:
        return {
            "order_id": self.order_id,
            "issue_type": self.issue_type,
            "business_value": str(self.business_value) if self.business_value is not None else None,
            "finance_value": str(self.finance_value) if self.finance_value is not None else None,
            "detail": self.detail
        }


@dataclass
class ReconciliationSummary:
    """对账摘要"""
    total_business_records: int = 0
    total_finance_records: int = 0
    matched_records: int = 0
    unmatched_records: int = 0
    # 新增：业务文件名（多个文件以逗号拼接）
    business_file: str = ""
    # 新增：财务文件名（多个文件以逗号拼接）
    finance_file: str = ""
    
    def to_dict(self) -> Dict:
        return {
            "total_business_records": self.total_business_records,
            "total_finance_records": self.total_finance_records,
            "matched_records": self.matched_records,
            "unmatched_records": self.unmatched_records,
            "business_file": self.business_file,
            "finance_file": self.finance_file,
        }


@dataclass
class ReconciliationMetadata:
    """对账元数据"""
    business_file_count: int = 0
    finance_file_count: int = 0
    rule_version: str = "1.0"
    processed_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict:
        return {
            "business_file_count": self.business_file_count,
            "finance_file_count": self.finance_file_count,
            "rule_version": self.rule_version,
            "processed_at": self.processed_at
        }


@dataclass
class ReconciliationResult:
    """对账结果"""
    task_id: str
    status: TaskStatus
    summary: ReconciliationSummary
    issues: List[ReconciliationIssue] = field(default_factory=list)
    metadata: ReconciliationMetadata = field(default_factory=ReconciliationMetadata)
    error: Optional[str] = None
    
    def to_dict(self) -> Dict:
        result = {
            "task_id": self.task_id,
            "status": self.status.value,
            "summary": self.summary.to_dict(),
            "issues": [issue.to_dict() for issue in self.issues],
            "metadata": self.metadata.to_dict()
        }
        if self.error:
            result["error"] = self.error
        return result


@dataclass
class ReconciliationTask:
    """对账任务"""
    task_id: str
    schema: Dict
    files: List[str]
    callback_url: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[ReconciliationResult] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

