"""
File upload and processing service
"""
from pathlib import Path
from datetime import datetime
from fastapi import UploadFile, HTTPException, status
from typing import List
from api.config import settings
from api.utils.excel import parse_excel_file, get_sheet_names
import shutil


class FileService:
    @staticmethod
    def save_uploaded_file(file: UploadFile) -> dict:
        """
        Save uploaded file to disk

        Returns:
            Dictionary with file metadata
        """
        # Validate file extension
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File type {file_ext} not allowed. Allowed types: {settings.ALLOWED_EXTENSIONS}"
            )

        # Create date-based directory structure
        now = datetime.now()
        upload_dir = Path(settings.UPLOAD_DIR) / str(now.year) / str(now.month) / str(now.day)
        upload_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique filename if file already exists
        file_path = upload_dir / file.filename
        counter = 1
        while file_path.exists():
            stem = Path(file.filename).stem
            file_path = upload_dir / f"{stem}_{counter}{file_ext}"
            counter += 1

        # Save file
        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to save file: {str(e)}"
            )

        # Get file size
        file_size = file_path.stat().st_size

        # Check file size
        if file_size > settings.MAX_FILE_SIZE:
            file_path.unlink()  # Delete file
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File size exceeds maximum allowed size of {settings.MAX_FILE_SIZE / (1024*1024)}MB"
            )

        # Get sheet names for Excel files
        sheets = []
        if file_ext in [".xlsx", ".xls"]:
            try:
                sheets = get_sheet_names(str(file_path))
            except Exception as e:
                print(f"Warning: Could not read sheet names: {e}")

        # Return relative path from UPLOAD_DIR
        relative_path = str(file_path.relative_to(Path(settings.UPLOAD_DIR).parent))

        return {
            "filename": file.filename,
            "path": f"/{relative_path}",
            "size": file_size,
            "sheets": sheets
        }

    @staticmethod
    def upload_multiple_files(files: List[UploadFile]) -> List[dict]:
        """
        Upload multiple files

        Returns:
            List of file metadata dictionaries
        """
        uploaded_files = []

        for file in files:
            try:
                file_info = FileService.save_uploaded_file(file)
                uploaded_files.append(file_info)
            except HTTPException as e:
                # Continue with other files even if one fails
                print(f"Failed to upload {file.filename}: {e.detail}")
                continue

        return uploaded_files

    @staticmethod
    def get_file_preview(file_path: str, max_rows: int = 100) -> dict:
        """
        Get preview data for Excel file

        Args:
            file_path: Relative path to file
            max_rows: Maximum number of rows to preview

        Returns:
            Dictionary with preview data
        """
        # Convert relative path to absolute path
        if file_path.startswith('/'):
            file_path = file_path[1:]

        abs_path = Path(settings.UPLOAD_DIR).parent / file_path

        if not abs_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found"
            )

        # Check file extension
        file_ext = abs_path.suffix.lower()
        if file_ext not in [".xlsx", ".xls"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only Excel files (.xlsx, .xls) can be previewed"
            )

        try:
            preview_data = parse_excel_file(str(abs_path), max_rows=max_rows)
            return preview_data
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to parse Excel file: {str(e)}"
            )
