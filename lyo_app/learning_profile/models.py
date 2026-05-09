"""SQLAlchemy model for the per-user learning profile (Stage B1)."""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Column, DateTime, ForeignKey, Integer, JSON, String,
)

from lyo_app.core.database import Base


class LearningProfile(Base):
    """One-to-one with users.id. Auto-created on first read.

    Slots are intentionally simple at this stage — list of strings + a few
    last-session pointers. The richer "mastery state" already lives in
    `personalization.models.MasteryState`; this table is the lightweight
    chat-context summary, not a duplicate of mastery tracking.
    """
    __tablename__ = "learning_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id"), unique=True, index=True, nullable=False
    )

    # Free-form lowercase string lists. We don't try to normalize subject /
    # topic names server-side — the AI handles synonyms in prompts.
    known_subjects = Column(JSON, default=list, nullable=False)
    struggle_topics = Column(JSON, default=list, nullable=False)

    # Last classroom session — feeds "continue where you left off" greetings
    last_classroom_topic: Optional[str] = Column(String(200))
    last_classroom_session_id: Optional[str] = Column(String(100))
    last_classroom_at: Optional[datetime] = Column(DateTime)

    # Bookkeeping
    total_classroom_sessions = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
