"""
Pydantic schemas for file operations
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Any


class FileUploadResponse(BaseModel):
    filename: str
    path: str
    size: int
    sheets: List[str]


class FileUploadListResponse(BaseModel):
    uploaded_files: List[FileUploadResponse]


class FilePreviewSheet(BaseModel):
    name: str
    headers: List[str]
    rows: List[List[str]]
    total_rows: int
    total_columns: int


class FilePreviewResponse(BaseModel):
    filename: str
    sheets: List[FilePreviewSheet]
