from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lyo_app.core.database import Base
from lyo_app.tenants.mixins import TenantMixin

class FileAsset(TenantMixin, Base):
    """
    Model to track file assets stored in the shared bucket.
    Enforces tenant ownership and tracks storage usage for billing.
    """
    __tablename__ = "file_assets"
    
    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    # Ownership (TenantMixin provides organization_id)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    
    # File details
    file_path: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)  # S3 Key: org_X/...
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[Optional[str]] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Access Control
    is_private: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship("lyo_app.auth.models.User", backref="file_assets")
    
    def __repr__(self) -> str:
        return f"<FileAsset(id={self.id}, org={self.organization_id}, path='{self.file_path}')>"
