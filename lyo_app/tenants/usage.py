"""
Usage logging for SaaS billing and analytics.
Tracks API calls and AI token usage per organization.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Integer, ForeignKey, Float
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.core.database import Base

logger = logging.getLogger(__name__)


class UsageLog(Base):
    """
    Tracks individual API usage events for billing purposes.
    
    This is a write-heavy table optimized for fast inserts.
    Monthly aggregations are computed for billing.
    """
    
    __tablename__ = "usage_logs"
    
    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    # Foreign key to organization
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Request details
    endpoint: Mapped[str] = mapped_column(String(200), nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    
    # Resource usage
    tokens_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    
    # Response metadata
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Request source (for debugging)
    api_key_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("api_keys.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    
    # Timestamp (indexed for date range queries)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )

    def __repr__(self) -> str:
        return f"<UsageLog(id={self.id}, org={self.organization_id}, endpoint='{self.endpoint}')>"


async def log_api_usage(
    db: AsyncSession,
    organization_id: int,
    endpoint: str,
    method: str,
    status_code: int,
    latency_ms: int = 0,
    tokens_used: int = 0,
    cost_usd: float = 0.0,
    api_key_id: Optional[int] = None,
    user_id: Optional[int] = None
) -> None:
    """
    Log API usage for billing purposes.
    
    This is designed as a fire-and-forget operation that won't
    block the main request. Errors are logged but not raised.
    """
    try:
        usage = UsageLog(
            organization_id=organization_id,
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            latency_ms=latency_ms,
            tokens_used=tokens_used,
            cost_usd=cost_usd,
            api_key_id=api_key_id,
            user_id=user_id
        )
        db.add(usage)
        await db.commit()
    except Exception as e:
        logger.warning(f"Failed to log API usage: {e}")
        await db.rollback()


async def log_usage_async(
    organization_id: int,
    endpoint: str,
    method: str,
    status_code: int,
    latency_ms: int = 0,
    tokens_used: int = 0,
    **kwargs
) -> None:
    """
    Fire-and-forget usage logging.
    
    Creates its own database session for background logging.
    Safe to call with asyncio.create_task().
    """
    try:
        from lyo_app.core.database import AsyncSessionLocal
        
        async with AsyncSessionLocal() as db:
            await log_api_usage(
                db=db,
                organization_id=organization_id,
                endpoint=endpoint,
                method=method,
                status_code=status_code,
                latency_ms=latency_ms,
                tokens_used=tokens_used,
                **kwargs
            )
    except Exception as e:
        logger.warning(f"Background usage logging failed: {e}")
