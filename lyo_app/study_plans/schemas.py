"""Pydantic schemas for the StudyPlan API."""
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


PlanStatus = Literal["active", "completed", "abandoned"]


class StudyPlanCreate(BaseModel):
    """Payload for creating a new plan from chat."""

    subject: str = Field(..., min_length=1, max_length=100)
    topics: List[str] = Field(default_factory=list, max_items=20)
    deadline: Optional[str] = Field(default=None, max_length=80)
    daily_breakdown: List[str] = Field(default_factory=list, max_items=14)
    source_conversation_id: Optional[str] = Field(default=None, max_length=100)


class StudyPlanUpdate(BaseModel):
    """Partial update. Any nil field is left unchanged on the server."""

    subject: Optional[str] = Field(default=None, max_length=100)
    topics: Optional[List[str]] = Field(default=None, max_items=20)
    deadline: Optional[str] = Field(default=None, max_length=80)
    daily_breakdown: Optional[List[str]] = Field(default=None, max_items=14)
    status: Optional[PlanStatus] = None


class StudyPlanRead(BaseModel):
    """Public view of a plan."""

    id: int
    user_id: int
    subject: str
    topics: List[str]
    deadline: Optional[str]
    daily_breakdown: List[str]
    status: PlanStatus
    source_conversation_id: Optional[str]

    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}
