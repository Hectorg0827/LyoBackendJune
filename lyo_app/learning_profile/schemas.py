"""Pydantic schemas for the LearningProfile API."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class LearningProfileRead(BaseModel):
    """Public view of the user's learning profile."""

    user_id: int
    known_subjects: List[str] = Field(default_factory=list)
    struggle_topics: List[str] = Field(default_factory=list)

    last_classroom_topic: Optional[str] = None
    last_classroom_session_id: Optional[str] = None
    last_classroom_at: Optional[datetime] = None

    total_classroom_sessions: int = 0

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LearningProfileUpdate(BaseModel):
    """Partial-update payload. Any provided list REPLACES the existing one;
    set the field to None / omit it to leave the existing value untouched."""

    known_subjects: Optional[List[str]] = None
    struggle_topics: Optional[List[str]] = None
    last_classroom_topic: Optional[str] = None
    last_classroom_session_id: Optional[str] = None
    record_classroom_session: bool = False
