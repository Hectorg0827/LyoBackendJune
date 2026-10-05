"""Wire contract for the Lyo Coach orchestration layer."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


GoalType = Literal["test", "assignment", "mastery", "course", "recovery", "certification"]
GoalStatus = Literal["active", "paused", "completed", "archived"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GoalSkillInput(StrictModel):
    concept_id: Optional[str] = Field(default=None, max_length=80)
    name: str = Field(min_length=1, max_length=240)
    weight: float = Field(default=1.0, gt=0.0, le=1000.0)
    required_rung: str = Field(default="transfer", max_length=32)
    priority: int = Field(default=5, ge=1, le=10)


class LearningGoalCreate(StrictModel):
    goal_type: GoalType
    title: str = Field(min_length=1, max_length=240)
    subject: Optional[str] = Field(default=None, max_length=120)
    deadline: Optional[datetime] = None
    desired_outcome: Dict[str, Any] = Field(default_factory=dict)
    constraints: Dict[str, Any] = Field(default_factory=dict)
    skills: List[GoalSkillInput] = Field(default_factory=list, max_length=200)

    @field_validator("skills")
    @classmethod
    def unique_skill_names(cls, value: List[GoalSkillInput]) -> List[GoalSkillInput]:
        seen = set()
        for skill in value:
            key = (skill.concept_id or skill.name).strip().lower()
            if key in seen:
                raise ValueError("skills must be unique within a goal")
            seen.add(key)
        return value


class LearningGoalPatch(StrictModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=240)
    subject: Optional[str] = Field(default=None, max_length=120)
    deadline: Optional[datetime] = None
    status: Optional[GoalStatus] = None
    desired_outcome: Optional[Dict[str, Any]] = None
    constraints: Optional[Dict[str, Any]] = None

    @field_validator("title", "status", "desired_outcome", "constraints")
    @classmethod
    def non_nullable_fields_cannot_be_explicit_null(cls, value: Any) -> Any:
        # Omission remains valid because validators are not run for defaults;
        # explicit JSON null must not reach NOT NULL database columns.
        if value is None:
            raise ValueError("field may be omitted but cannot be null")
        return value


class GoalSkillRead(StrictModel):
    id: str
    concept_id: str
    display_name: str
    weight: float
    required_rung: str
    priority: int

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class LearningGoalRead(StrictModel):
    id: str
    goal_type: str
    title: str
    subject: Optional[str] = None
    status: str
    deadline: Optional[datetime] = None
    desired_outcome: Dict[str, Any] = Field(default_factory=dict)
    constraints: Dict[str, Any] = Field(default_factory=dict)
    source_surface: Optional[str] = None
    source_ref_type: Optional[str] = None
    source_ref_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    skills: List[GoalSkillRead] = Field(default_factory=list)


class GoalSkillState(StrictModel):
    skill_id: str
    concept_id: str
    display_name: str
    weight: float
    required_rung: str
    evidence_state: str = "NOT_SEEN"
    strongest_rung: Optional[str] = None
    next_rung: Optional[str] = None
    misconception: Optional[str] = None
    last_seen: Optional[str] = None
    evidence_progress: float = Field(default=0.0, ge=0.0, le=1.0)
    priority_score: float = Field(default=0.0, ge=0.0)
    overdue_review: bool = False


class ReadinessRead(StrictModel):
    # Internal ordinal index.  It is intentionally not labelled a probability
    # or expected exam grade until production outcomes calibrate it.
    readiness_index: float = Field(ge=0.0, le=1.0)
    readiness_level: Literal["not_ready", "getting_there", "ready"]
    calibrated: bool = False
    assessed_skills: int = Field(ge=0)
    total_skills: int = Field(ge=0)
    critical_gaps: int = Field(ge=0)


class MissionItem(StrictModel):
    goal_id: str
    goal_title: str
    skill_id: str
    concept_id: str
    title: str
    action: str
    target_evidence_type: Optional[str] = None
    recommended_surface: Literal["chat", "classroom", "quiz", "review"]
    estimated_minutes: int = Field(ge=1, le=60)
    priority_score: float = Field(ge=0.0)
    reason: str


class GoalCoachView(StrictModel):
    goal: LearningGoalRead
    readiness: ReadinessRead
    skills: List[GoalSkillState]
    mission: List[MissionItem]
    total_minutes: int = Field(ge=0)
    coach_note: str
    source_event_id: Optional[int] = None
    generated_at: datetime


class TodayCoachView(StrictModel):
    primary_goal_id: Optional[str] = None
    active_goals: List[LearningGoalRead] = Field(default_factory=list)
    readiness: Dict[str, ReadinessRead] = Field(default_factory=dict)
    mission: List[MissionItem] = Field(default_factory=list)
    total_minutes: int = Field(ge=0)
    coach_note: str
    generated_at: datetime
