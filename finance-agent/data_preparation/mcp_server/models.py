"""
数据整理模块数据模型
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime


@dataclass
class ProcessingStep:
    """处理步骤记录"""
    step_name: str
    step_type: str  # extraction, transformation, validation, output
    status: str  # pending, processing, completed, failed
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_seconds: Optional[float] = None
    records_processed: int = 0
    error_message: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "step_name": self.step_name,
            "step_type": self.step_type,
            "status": self.status,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": self.duration_seconds,
            "records_processed": self.records_processed,
            "error_message": self.error_message,
            "details": self.details
        }


@dataclass
class DataSource:
    """数据源信息"""
    source_id: str
    name: str
    type: str  # excel, pdf, image, csv
    file_path: str
    records_extracted: int = 0
    extraction_time: Optional[float] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "source_id": source_id,
            "name": self.name,
            "type": self.type,
            "file_path": self.file_path,
            "records_extracted": self.records_extracted,
            "extraction_time": self.extraction_time,
            "error": self.error
        }


@dataclass
class ProcessingMetadata:
    """处理元数据"""
    project_name: str
    rule_version: str
    processed_by: str = "data-preparation-mcp-v1.0.0"
    execution_time_seconds: float = 0.0
    total_records_processed: int = 0
    total_errors: int = 0
    
    def to_dict(self) -> Dict:
        return {
            "project_name": self.project_name,
            "rule_version": self.rule_version,
            "processed_by": self.processed_by,
            "execution_time_seconds": self.execution_time_seconds,
            "total_records_processed": self.total_records_processed,
            "total_errors": self.total_errors
        }


@dataclass
class ProcessingResult:
    """数据整理结果"""
    task_id: str
    status: str  # success, failed, processing
    output_file: Optional[str] = None
    output_url: Optional[str] = None
    preview_url: Optional[str] = None
    report_url: Optional[str] = None
    metadata: Optional[ProcessingMetadata] = None
    steps: List[ProcessingStep] = field(default_factory=list)
    error: Optional[str] = None
    
    def to_dict(self) -> Dict:
        result = {
            "task_id": self.task_id,
            "status": self.status
        }
        
        if self.status == "success":
            result["actions"] = []
            if self.output_url:
                result["actions"].append({
                    "action": "download_file",
                    "url": self.output_url,
                    "method": "GET",
                    "expires_at": None  # TODO: 添加过期时间
                })
            if self.preview_url:
                result["actions"].append({
                    "action": "view_preview",
                    "url": self.preview_url,
                    "method": "GET"
                })
            if self.report_url:
                result["actions"].append({
                    "action": "get_detailed_report",
                    "url": self.report_url,
                    "method": "GET"
                })
            
            if self.metadata:
                result["metadata"] = self.metadata.to_dict()
        
        elif self.status == "failed" and self.error:
            result["error"] = self.error
        
        return result
