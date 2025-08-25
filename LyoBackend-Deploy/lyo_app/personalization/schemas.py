"""
Pydantic schemas for personalization API
"""

from pydantic import BaseModel, Field, validator
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum

class ActionType(str, Enum):
    PRACTICE_QUESTION = "practice_question"
    HINT = "hint"
    EXPLANATION = "explanation"
    WORKED_EXAMPLE = "worked_example"
    BREAK = "break"
    REVIEW = "review"
    CHALLENGE = "challenge"

class AffectSignals(BaseModel):
    """Affect signals from on-device processing"""
    valence: float = Field(..., ge=-1, le=1)
    arousal: float = Field(..., ge=0, le=1)
    confidence: float = Field(..., ge=0, le=1)
    source: List[str] = Field(default_factory=list)

class SessionState(BaseModel):
    """Current session state"""
    fatigue: float = Field(0.0, ge=0, le=1)
    focus: float = Field(0.7, ge=0, le=1)
    duration_minutes: Optional[int] = None
    last_break_minutes_ago: Optional[int] = None

class LearningContext(BaseModel):
    """Current learning context"""
    lesson_id: Optional[str] = None
    skill: Optional[str] = None
    topic: Optional[str] = None
    difficulty: Optional[str] = None

class PersonalizationStateUpdate(BaseModel):
    """Update learner state with signals"""
    learner_id: str
    affect: Optional[AffectSignals] = None
    session: Optional[SessionState] = None
    context: Optional[LearningContext] = None

class KnowledgeTraceRequest(BaseModel):
    """Track knowledge from assessment result"""
    learner_id: str
    skill_id: str
    item_id: str
    correct: bool
    time_taken_seconds: float
    hints_used: int = 0
    attempt_number: int = 1

class NextActionRequest(BaseModel):
    """Request next best action"""
    learner_id: str
    lesson_id: Optional[str] = None
    current_skill: Optional[str] = None
    available_actions: List[ActionType] = Field(
        default_factory=lambda: list(ActionType)
    )

class NextActionResponse(BaseModel):
    """Next best action recommendation"""
    action: ActionType
    difficulty: str
    reason: List[str]
    spaced_repetition_due: bool = False
    content: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class MasteryProfile(BaseModel):
    """Learner's mastery profile"""
    learner_id: str
    skills: Dict[str, float]  # skill_id -> mastery level
    strengths: List[str]
    weaknesses: List[str]
    recommended_focus: List[str]
    learning_velocity: float
    optimal_difficulty: float
