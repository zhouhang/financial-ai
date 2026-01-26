"""
Schema management router
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from database import get_db
from models.user import User
from models.schema import WorkType, SchemaStatus
from schemas.schema import (
    SchemaCreate, SchemaUpdate, SchemaResponse, SchemaDetailResponse,
    SchemaListResponse, TypeKeyRequest, TypeKeyResponse, NameExistsResponse,
    SchemaContentValidateRequest, SchemaContentValidateResponse,
    SchemaTestRequest, SchemaTestResponse
)
from services.schema_service import SchemaService
from routers.auth import get_current_user
from typing import Optional

router = APIRouter(prefix="/schemas", tags=["Schemas"])


@router.post("", response_model=SchemaResponse, status_code=201)
def create_schema(
    schema_data: SchemaCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new schema
    """
    schema = SchemaService.create_schema(db, current_user, schema_data)
    return SchemaResponse.model_validate(schema)


@router.get("", response_model=SchemaListResponse)
def list_schemas(
    work_type: Optional[WorkType] = Query(None, description="Filter by work type"),
    status: Optional[SchemaStatus] = Query(None, description="Filter by status"),
    skip: int = Query(0, ge=0, description="Skip records"),
    limit: int = Query(100, ge=1, le=1000, description="Limit records"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List user's schemas
    """
    schemas, total = SchemaService.get_user_schemas(
        db, current_user, work_type, status, skip, limit
    )

    return SchemaListResponse(
        total=total,
        schemas=[SchemaResponse.model_validate(s) for s in schemas]
    )


@router.get("/{schema_id}", response_model=SchemaDetailResponse)
def get_schema(
    schema_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get schema details including content
    """
    schema = SchemaService.get_schema_by_id(db, current_user, schema_id)
    schema_content = SchemaService.get_schema_content(schema)

    response = SchemaDetailResponse.model_validate(schema)
    response.schema_content = schema_content

    return response


@router.put("/{schema_id}", response_model=SchemaResponse)
def update_schema(
    schema_id: int,
    update_data: SchemaUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update schema
    """
    schema = SchemaService.update_schema(db, current_user, schema_id, update_data)
    return SchemaResponse.model_validate(schema)


@router.delete("/{schema_id}")
def delete_schema(
    schema_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete schema
    """
    SchemaService.delete_schema(db, current_user, schema_id)
    return {"message": "Schema deleted successfully"}


@router.post("/generate-type-key", response_model=TypeKeyResponse)
def generate_type_key(
    request: TypeKeyRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Generate type_key from Chinese name using pinyin
    """
    type_key = SchemaService.generate_type_key_from_chinese(request.name_cn)
    return TypeKeyResponse(type_key=type_key)


@router.get("/check-name-exists", response_model=NameExistsResponse)
def check_name_exists(
    name_cn: str = Query(..., description="Chinese name to check"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Check if name_cn already exists for the current user
    """
    exists = SchemaService.check_name_exists(db, current_user.id, name_cn)
    return NameExistsResponse(exists=exists)


@router.post("/validate-content", response_model=SchemaContentValidateResponse)
def validate_schema_content(
    request: SchemaContentValidateRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Validate schema configuration structure and rules
    """
    result = SchemaService.validate_schema_content(request.schema_content)
    return result


@router.post("/test", response_model=SchemaTestResponse)
async def test_schema(
    request: SchemaTestRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Test schema execution with uploaded files
    """
    result = await SchemaService.test_schema_execution(
        request.schema_content,
        request.file_paths
    )
    return result
