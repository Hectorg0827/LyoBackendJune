"""SQLAlchemy model for the StudyPlan table (Stage B2)."""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column, DateTime, ForeignKey, Integer, JSON, String,
)

from lyo_app.core.database import Base


class StudyPlan(Base):
    """A user-owned study plan. One user can have multiple plans (one per
    test / project / goal). Soft-deleted via `status`, never hard-deleted by
    the user-facing endpoints (so we keep history for analytics).
    """
    __tablename__ = "study_plans"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id"), index=True, nullable=False
    )

    # What the plan is about
    subject = Column(String(100), nullable=False)
    topics = Column(JSON, default=list, nullable=False)  # list[str]

    # Free-form deadline phrase ("next Tuesday", "by end of week").
    # We don't parse this server-side — the AI handles temporal reasoning.
    deadline = Column(String(80))

    # Human-readable per-day plan items: ["Today: cells", "Tuesday: photosynthesis", ...]
    daily_breakdown = Column(JSON, default=list, nullable=False)

    # active | completed | abandoned
    status = Column(String(20), default="active", nullable=False, index=True)

    # Pointer back to the originating chat conversation (optional).
    source_conversation_id: Optional[str] = Column(String(100))

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    completed_at: Optional[datetime] = Column(DateTime)
