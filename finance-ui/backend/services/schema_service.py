"""
Schema management service
"""
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from models.schema import UserSchema, WorkType, SchemaStatus
from models.user import User
from schemas.schema import SchemaCreate, SchemaUpdate
from utils.pinyin import generate_type_key
from pathlib import Path
import json
from config import settings
from typing import Optional, List


class SchemaService:
    @staticmethod
    def create_schema(db: Session, user: User, schema_data: SchemaCreate) -> UserSchema:
        """
        Create a new schema
        """
        # Generate type_key from Chinese name
        type_key = generate_type_key(schema_data.name_cn)

        # Check uniqueness for this user
        existing = db.query(UserSchema).filter(
            UserSchema.user_id == user.id,
            UserSchema.name_cn == schema_data.name_cn
        ).first()

        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Schema with name '{schema_data.name_cn}' already exists"
            )

        # Determine paths based on work_type
        if schema_data.work_type == WorkType.DATA_PREPARATION:
            schema_dir = Path(settings.SCHEMA_BASE_DIR) / "data_preparation" / "schemas" / str(user.id)
            config_dir = Path(settings.SCHEMA_BASE_DIR) / "data_preparation" / "config" / str(user.id)
            schema_path = f"data_preparation/schemas/{user.id}/{type_key}.json"
            config_path = f"data_preparation/config/{user.id}/data_preparation_schemas.json"
        else:  # RECONCILIATION
            schema_dir = Path(settings.SCHEMA_BASE_DIR) / "reconciliation" / "schemas" / str(user.id)
            config_dir = Path(settings.SCHEMA_BASE_DIR) / "reconciliation" / "config" / str(user.id)
            schema_path = f"reconciliation/schemas/{user.id}/{type_key}.json"
            config_path = f"reconciliation/config/{user.id}/reconciliation_schemas.json"

        # Create directories if they don't exist
        schema_dir.mkdir(parents=True, exist_ok=True)
        config_dir.mkdir(parents=True, exist_ok=True)

        # Create initial schema JSON file
        initial_schema = {
            "version": "1.0",
            "schema_type": "step_based" if schema_data.work_type == WorkType.DATA_PREPARATION else "traditional",
            "metadata": {
                "project_name": schema_data.name_cn,
                "author": user.username,
                "description": schema_data.description or ""
            },
            "processing_steps": [] if schema_data.work_type == WorkType.DATA_PREPARATION else None,
            "data_sources": {} if schema_data.work_type == WorkType.RECONCILIATION else None
        }

        schema_file = schema_dir / f"{type_key}.json"
        with open(schema_file, 'w', encoding='utf-8') as f:
            json.dump(initial_schema, f, ensure_ascii=False, indent=2)

        # Update or create config file
        config_file = config_dir / config_path.split('/')[-1]
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
        else:
            config_data = {"types": []}

        # Add new schema to config
        config_data["types"].append({
            "name_cn": schema_data.name_cn,
            "type_key": type_key,
            "schema_path": f"{type_key}.json",
            "callback_url": schema_data.callback_url
        })

        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)

        # Create database record
        new_schema = UserSchema(
            user_id=user.id,
            name_cn=schema_data.name_cn,
            type_key=type_key,
            work_type=schema_data.work_type,
            schema_path=schema_path,
            config_path=config_path,
            version="1.0",
            status=SchemaStatus.DRAFT,
            callback_url=schema_data.callback_url,
            description=schema_data.description
        )

        db.add(new_schema)
        db.commit()
        db.refresh(new_schema)

        return new_schema

    @staticmethod
    def get_user_schemas(
        db: Session,
        user: User,
        work_type: Optional[WorkType] = None,
        status: Optional[SchemaStatus] = None,
        skip: int = 0,
        limit: int = 100
    ) -> tuple[List[UserSchema], int]:
        """
        Get user's schemas with optional filters
        """
        query = db.query(UserSchema).filter(UserSchema.user_id == user.id)

        if work_type:
            query = query.filter(UserSchema.work_type == work_type)

        if status:
            query = query.filter(UserSchema.status == status)

        total = query.count()
        schemas = query.order_by(UserSchema.updated_at.desc()).offset(skip).limit(limit).all()

        return schemas, total

    @staticmethod
    def get_schema_by_id(db: Session, user: User, schema_id: int) -> UserSchema:
        """
        Get schema by ID (must belong to user)
        """
        schema = db.query(UserSchema).filter(
            UserSchema.id == schema_id,
            UserSchema.user_id == user.id
        ).first()

        if not schema:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Schema not found"
            )

        return schema

    @staticmethod
    def get_schema_content(schema: UserSchema) -> dict:
        """
        Read schema JSON content from file
        """
        schema_file = Path(settings.SCHEMA_BASE_DIR) / schema.schema_path

        if not schema_file.exists():
            return {}

        with open(schema_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    @staticmethod
    def update_schema(
        db: Session,
        user: User,
        schema_id: int,
        update_data: SchemaUpdate
    ) -> UserSchema:
        """
        Update schema
        """
        schema = SchemaService.get_schema_by_id(db, user, schema_id)

        # Update database fields
        if update_data.name_cn is not None:
            # Check uniqueness
            existing = db.query(UserSchema).filter(
                UserSchema.user_id == user.id,
                UserSchema.name_cn == update_data.name_cn,
                UserSchema.id != schema_id
            ).first()

            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Schema with name '{update_data.name_cn}' already exists"
                )

            schema.name_cn = update_data.name_cn

        if update_data.status is not None:
            schema.status = update_data.status

        if update_data.callback_url is not None:
            schema.callback_url = update_data.callback_url

        if update_data.description is not None:
            schema.description = update_data.description

        # Update schema content if provided
        if update_data.schema_content is not None:
            schema_file = Path(settings.SCHEMA_BASE_DIR) / schema.schema_path

            # Increment version
            current_version = float(schema.version)
            new_version = f"{current_version + 0.1:.1f}"
            schema.version = new_version

            # Update version in schema content
            update_data.schema_content["version"] = new_version

            with open(schema_file, 'w', encoding='utf-8') as f:
                json.dump(update_data.schema_content, f, ensure_ascii=False, indent=2)

        db.commit()
        db.refresh(schema)

        return schema

    @staticmethod
    def delete_schema(db: Session, user: User, schema_id: int):
        """
        Delete schema
        """
        schema = SchemaService.get_schema_by_id(db, user, schema_id)

        # Delete schema file
        schema_file = Path(settings.SCHEMA_BASE_DIR) / schema.schema_path
        if schema_file.exists():
            schema_file.unlink()

        # Remove from config file
        config_file = Path(settings.SCHEMA_BASE_DIR) / schema.config_path
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            config_data["types"] = [
                t for t in config_data["types"]
                if t["type_key"] != schema.type_key
            ]

            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)

        # Delete database record
        db.delete(schema)
        db.commit()

    @staticmethod
    def generate_type_key_from_chinese(name_cn: str) -> str:
        """
        Generate type_key from Chinese name using pinyin
        """
        return generate_type_key(name_cn)

    @staticmethod
    def check_name_exists(db: Session, user_id: int, name_cn: str) -> bool:
        """
        Check if name_cn already exists for the user
        """
        schema = db.query(UserSchema).filter(
            UserSchema.user_id == user_id,
            UserSchema.name_cn == name_cn
        ).first()
        return schema is not None

    @staticmethod
    def validate_schema_content(schema_content: dict) -> dict:
        """
        Validate schema configuration structure and rules
        """
        errors = []
        warnings = []

        # Check required fields
        if "version" not in schema_content:
            errors.append("Missing required field: version")

        if "schema_type" not in schema_content:
            errors.append("Missing required field: schema_type")

        if "metadata" not in schema_content:
            errors.append("Missing required field: metadata")
        else:
            metadata = schema_content["metadata"]
            if "project_name" not in metadata:
                errors.append("Missing required field: metadata.project_name")

        # Validate processing steps if present
        if "processing_steps" in schema_content:
            steps = schema_content["processing_steps"]
            if not isinstance(steps, list):
                errors.append("processing_steps must be a list")
            else:
                for i, step in enumerate(steps):
                    if not isinstance(step, dict):
                        errors.append(f"Step {i} must be an object")
                        continue

                    if "step_name" not in step:
                        errors.append(f"Step {i}: missing step_name")
                    if "step_type" not in step:
                        errors.append(f"Step {i}: missing step_type")

        # Validate data sources if present
        if "data_sources" in schema_content:
            sources = schema_content["data_sources"]
            if not isinstance(sources, dict):
                errors.append("data_sources must be an object")

        from schemas.schema import SchemaContentValidateResponse
        return SchemaContentValidateResponse(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    @staticmethod
    async def test_schema_execution(schema_content: dict, file_paths: list) -> dict:
        """
        Test schema execution with uploaded files
        """
        import time
        from schemas.schema import SchemaTestResponse

        start_time = time.time()
        errors = []
        output_preview = []

        try:
            # Validate schema first
            validation = SchemaService.validate_schema_content(schema_content)
            if not validation.valid:
                errors.extend(validation.errors)
                return SchemaTestResponse(
                    success=False,
                    output_preview=[],
                    errors=errors,
                    execution_time=time.time() - start_time
                )

            # Check if files exist
            for file_path in file_paths:
                file = Path(file_path)
                if not file.exists():
                    errors.append(f"File not found: {file_path}")

            if errors:
                return SchemaTestResponse(
                    success=False,
                    output_preview=[],
                    errors=errors,
                    execution_time=time.time() - start_time
                )

            # TODO: Implement actual schema execution logic
            # For now, return a simple preview
            output_preview = [
                ["Column1", "Column2", "Column3"],
                ["Sample", "Data", "Row1"],
                ["Sample", "Data", "Row2"]
            ]

            execution_time = time.time() - start_time

            return SchemaTestResponse(
                success=True,
                output_preview=output_preview,
                errors=[],
                execution_time=execution_time
            )

        except Exception as e:
            errors.append(f"Execution error: {str(e)}")
            return SchemaTestResponse(
                success=False,
                output_preview=[],
                errors=errors,
                execution_time=time.time() - start_time
            )
