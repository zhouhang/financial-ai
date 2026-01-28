"""
File upload and preview router
"""
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
from typing import List
from api.models.user import User
from api.schemas.file import FileUploadListResponse, FileUploadResponse, FilePreviewResponse
from api.services.file_service import FileService
from api.routers.auth import get_current_user

router = APIRouter(prefix="/files", tags=["Files"])


@router.post("/upload", response_model=FileUploadListResponse)
async def upload_files(
    files: List[UploadFile] = File(..., description="Files to upload"),
    current_user: User = Depends(get_current_user)
):
    """
    Upload multiple files
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    uploaded_files = FileService.upload_multiple_files(files)

    return FileUploadListResponse(
        uploaded_files=[FileUploadResponse(**f) for f in uploaded_files]
    )


@router.get("/preview", response_model=FilePreviewResponse)
def preview_file(
    file_path: str = Query(..., description="File path to preview"),
    max_rows: int = Query(100, ge=1, le=1000, description="Maximum rows to preview"),
    current_user: User = Depends(get_current_user)
):
    """
    Get Excel file preview data
    """
    preview_data = FileService.get_file_preview(file_path, max_rows)
    return FilePreviewResponse(**preview_data)
