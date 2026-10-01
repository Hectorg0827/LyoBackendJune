"""Typed state shared by every Lyo teaching surface."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TeachingSurface(str, Enum):
    CHAT = "chat"
    CLASSROOM = "classroom"
    COURSE = "course"
    TEST_PREP = "test_prep"


class TeachingAction(str, Enum):
    """A deliberately small action vocabulary.

    The policy chooses one of these before a language model writes prose. That
    keeps pedagogy inspectable and testable instead of hiding the control flow
    inside prompts.
    """

    ANSWER = "answer"
    DIAGNOSE = "diagnose"
    EXPLAIN = "explain"
    DEMONSTRATE = "demonstrate"
    GUIDE = "guide"
    CHECK_RECALL = "check_recall"
    CHECK_APPLICATION = "check_application"
    CHECK_TRANSFER = "check_transfer"
    REMEDIATE = "remediate"
    REVIEW = "review"
    ADVANCE = "advance"
    PAUSE = "pause"


class LearnerSnapshot(StrictModel):
    concept_id: Optional[str] = None
    mastery_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    evidence_state: str = "NOT_SEEN"
    strongest_rung: Optional[str] = None
    next_rung: Optional[str] = None
    misconception: Optional[str] = None
    attempts: int = Field(default=0, ge=0)
    hints_used: int = Field(default=0, ge=0)
    uncertainty: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    last_seen: Optional[str] = None


class SessionSnapshot(StrictModel):
    surface: TeachingSurface
    turn_count: int = Field(default=0, ge=0)
    consecutive_explanations: int = Field(default=0, ge=0)
    consecutive_checks: int = Field(default=0, ge=0)
    last_action: Optional[TeachingAction] = None
    learner_requested_direct_answer: bool = False
    learner_requested_visual: bool = False
    learner_expressed_confusion: bool = False
    learner_wants_to_stop: bool = False


class TeachingContext(StrictModel):
    intent: str
    user_text: str = ""
    learner: LearnerSnapshot
    session: SessionSnapshot
    has_active_course: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TeachingDecision(StrictModel):
    action: TeachingAction
    reason_code: str
    interaction_required: bool = False
    max_exposition_words: int = Field(default=120, ge=20, le=300)
    preferred_instrument: Optional[str] = None
    target_evidence_type: Optional[str] = None
    model_tier: str = "teaching"
    directives: List[str] = Field(default_factory=list)
    policy_version: str
