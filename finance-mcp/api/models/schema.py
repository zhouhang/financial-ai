"""
UserSchema database model
"""
from sqlalchemy import Column, Integer, String, DateTime, Enum, Boolean, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from api.database import Base
import enum


class WorkType(str, enum.Enum):
    DATA_PREPARATION = "data_preparation"
    RECONCILIATION = "reconciliation"


class SchemaStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"


class UserSchema(Base):
    __tablename__ = "user_schemas"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name_cn = Column(String(100), nullable=False, comment="中文名称")
    type_key = Column(String(50), nullable=False, index=True, comment="类型键（英文标识）")
    work_type = Column(Enum(WorkType), nullable=False, comment="工作类型")
    schema_path = Column(String(500), nullable=False, comment="Schema JSON文件路径")
    config_path = Column(String(500), nullable=False, comment="配置文件路径")
    version = Column(String(20), default="1.0", comment="Schema版本")
    status = Column(Enum(SchemaStatus), default=SchemaStatus.DRAFT, comment="状态")
    is_public = Column(Boolean, default=False, comment="是否公开")
    callback_url = Column(String(500), nullable=True, comment="回调URL")
    description = Column(Text, nullable=True, comment="描述")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationship
    user = relationship("User", back_populates="schemas")

    def __repr__(self):
        return f"<UserSchema(id={self.id}, name_cn='{self.name_cn}', type_key='{self.type_key}', work_type='{self.work_type}')>"
