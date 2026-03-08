"""
Pydantic schemas for the Relationship System API.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict


# ── Milestones ──────────────────────────────────────────────

class MilestoneRead(BaseModel):
    id: int
    user_id: int
    milestone_type: str
    title: str
    description: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None
    celebrated: bool
    achieved_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MilestonesResponse(BaseModel):
    milestones: List[MilestoneRead]
    total: int


# ── Personality ─────────────────────────────────────────────

class PersonalityProfileRead(BaseModel):
    formality: float
    humor_level: float
    encouragement_intensity: float
    detail_level: float
    challenge_level: float
    metaphor_domains: List[str]
    prefers_visual: bool
    prefers_examples_first: bool
    prefers_socratic: bool

    model_config = ConfigDict(from_attributes=True)


# ── Relationship Memory ────────────────────────────────────

class RelationshipMemoryRead(BaseModel):
    id: int
    category: str
    content: str
    importance: float
    source: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Journey Summary ────────────────────────────────────────

class JourneySummaryResponse(BaseModel):
    days_since_joined: int
    total_milestones: int
    recent_milestones: List[MilestoneRead]
    total_memories: int
    personality_snapshot: Optional[PersonalityProfileRead] = None
    streak_days: int
    goals_achieved: int


# ── Weekly Review ──────────────────────────────────────────

class WeeklyReviewResponse(BaseModel):
    period_start: str
    period_end: str
    lessons_completed: int
    events_logged: int
    reflections_submitted: int
    goals_progressed: int
    new_milestones: List[MilestoneRead]
    momentum_trend: str  # "rising", "stable", "declining"
    highlight: Optional[str] = None
