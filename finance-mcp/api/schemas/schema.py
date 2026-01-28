"""
Pydantic schemas for user schemas (data processing configurations)
"""
from pydantic import BaseModel, Field, HttpUrl
from datetime import datetime
from typing import Optional, Dict, Any
from api.models.schema import WorkType, SchemaStatus


class SchemaBase(BaseModel):
    name_cn: str = Field(..., min_length=1, max_length=100, description="中文名称")
    work_type: WorkType = Field(..., description="工作类型")
    callback_url: Optional[str] = Field(None, max_length=500, description="回调URL")
    description: Optional[str] = Field(None, description="描述")


class SchemaCreate(SchemaBase):
    pass


class SchemaUpdate(BaseModel):
    name_cn: Optional[str] = Field(None, min_length=1, max_length=100, description="中文名称")
    schema_content: Optional[Dict[str, Any]] = Field(None, description="Schema JSON内容")
    status: Optional[SchemaStatus] = Field(None, description="状态")
    callback_url: Optional[str] = Field(None, max_length=500, description="回调URL")
    description: Optional[str] = Field(None, description="描述")


class SchemaResponse(SchemaBase):
    id: int
    user_id: int
    type_key: str
    schema_path: str
    config_path: str
    version: str
    status: SchemaStatus
    is_public: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SchemaDetailResponse(SchemaResponse):
    schema_content: Optional[Dict[str, Any]] = Field(None, description="Schema JSON内容")


class SchemaListResponse(BaseModel):
    total: int
    schemas: list[SchemaResponse]


class SchemaStepCreate(BaseModel):
    step_name: str = Field(..., description="步骤名称")
    step_type: str = Field(..., description="步骤类型")
    data_source: Dict[str, Any] = Field(..., description="数据源配置")
    template_action: Optional[Dict[str, Any]] = Field(None, description="模板操作")


class SchemaValidateRequest(BaseModel):
    test_files: list[str] = Field(..., description="测试文件路径列表")


class SchemaValidateResponse(BaseModel):
    valid: bool
    test_result: Optional[Dict[str, Any]] = None
    errors: list[str] = []


# New schemas for canvas functionality
class TypeKeyRequest(BaseModel):
    name_cn: str = Field(..., min_length=1, max_length=100, description="中文名称")


class TypeKeyResponse(BaseModel):
    type_key: str


class NameExistsResponse(BaseModel):
    exists: bool


class SchemaContentValidateRequest(BaseModel):
    schema_content: Dict[str, Any] = Field(..., description="Schema配置内容")


class SchemaContentValidateResponse(BaseModel):
    valid: bool
    errors: list[str] = []
    warnings: list[str] = []


class SchemaTestRequest(BaseModel):
    schema_content: Dict[str, Any] = Field(..., description="Schema配置内容")
    file_paths: list[str] = Field(..., description="测试文件路径列表")


class SchemaTestResponse(BaseModel):
    success: bool
    output_preview: list[list[Any]] = []
    errors: list[str] = []
    execution_time: float
