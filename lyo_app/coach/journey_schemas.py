"""Versioned, typed surface-navigation contracts; no scoring or teaching policy."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Surface = Literal["chat", "classroom", "test_prep", "coach"]
JourneyStatus = Literal["active", "paused", "completed"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class JourneyContext(StrictModel):
    chat_session_id: Optional[str] = Field(default=None, max_length=160)
    test_profile_id: Optional[str] = Field(default=None, max_length=160)
    course_id: Optional[str] = Field(default=None, max_length=160)
    lesson_id: Optional[str] = Field(default=None, max_length=160)
    concept_id: Optional[str] = Field(default=None, max_length=160)
    question_id: Optional[str] = Field(default=None, max_length=160)


class JourneyStart(StrictModel):
    request_id: str = Field(min_length=8, max_length=80)
    goal_id: str = Field(min_length=1, max_length=36)
    origin_surface: Surface
    origin_ref: Optional[str] = Field(default=None, max_length=160)
    context: JourneyContext = Field(default_factory=JourneyContext)


class JourneyHandoffRequest(StrictModel):
    request_id: str = Field(min_length=8, max_length=80)
    expected_revision: int = Field(ge=0)
    target_surface: Surface
    target_ref: Optional[str] = Field(default=None, max_length=160)
    context: JourneyContext = Field(default_factory=JourneyContext)


class JourneyRead(StrictModel):
    id: str
    goal_id: str
    origin_surface: Surface
    origin_ref: Optional[str] = None
    active_surface: Surface
    active_ref: Optional[str] = None
    status: JourneyStatus
    revision: int
    context: JourneyContext
    updated_at: datetime


class JourneyHandoffRead(StrictModel):
    id: str
    revision: int
    from_surface: Surface
    from_ref: Optional[str] = None
    to_surface: Surface
    to_ref: Optional[str] = None
    context: JourneyContext
    created_at: datetime
