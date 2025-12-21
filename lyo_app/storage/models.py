"""
Storage-specific database models for tracking uploaded assets.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lyo_app.core.database import Base


class FileAsset(Base):
    """
    Tracks uploaded files for auditing, quota enforcement, and tenant isolation.
    """

    __tablename__ = "file_assets"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )

    file_path: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(50), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_private: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Relationships
    organization = relationship("lyo_app.tenants.models.Organization", lazy="select")
    user = relationship("lyo_app.auth.models.User", lazy="select")

    def __repr__(self) -> str:
        return f"<FileAsset(id={self.id}, org={self.organization_id}, path='{self.file_path}')>"
