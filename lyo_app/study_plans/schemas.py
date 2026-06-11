"""Pydantic schemas for the Test Prep & Study Plans API."""
from datetime import datetime, date
from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field

# Common status literals
PlanStatus = Literal["active", "paused", "completed", "archived", "abandoned"]
SessionStatus = Literal["scheduled", "in_progress", "completed", "skipped"]
ReminderStatus = Literal["pending", "sent", "failed", "cancelled"]

# ═══════════════════════════════════════════════════════════════════════════════════
# 📝 INTAKE SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════════

class IntakeMessage(BaseModel):
    """Message sent from client during intake conversation."""
    test_profile_id: Optional[str] = None
    user_message: str

class IntakeResponse(BaseModel):
    """Response returned to client containing chat reply and smart block UI elements."""
    test_profile_id: str
    message_to_user: str
    smart_blocks: List[Dict[str, Any]] = []
    intake_complete: bool

# ═══════════════════════════════════════════════════════════════════════════════════
# 📋 TEST PROFILE SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════════

class TestProfileCreate(BaseModel):
    subject: str = Field(..., min_length=1, max_length=100)
    test_date: date
    test_format: Optional[str] = None
    topics: List[Dict[str, Any]] = Field(default_factory=list)
    materials: List[Dict[str, Any]] = Field(default_factory=list)
    baseline_confidence: int = Field(5, ge=1, le=10)
    daily_minutes_available: int = Field(45, ge=5, le=480)
    study_days_per_week: int = Field(5, ge=1, le=7)
    stress_level: int = Field(5, ge=1, le=10)

class TestProfileRead(BaseModel):
    id: str
    user_id: int
    created_at: datetime
    subject: str
    test_date: date
    test_format: Optional[str]
    topics: List[Dict[str, Any]]
    materials: List[Dict[str, Any]]
    baseline_confidence: int
    daily_minutes_available: int
    study_days_per_week: int
    stress_level: int
    intake_complete: bool
    intake_transcript: List[Dict[str, Any]]

    class Config:
        from_attributes = True

# ═══════════════════════════════════════════════════════════════════════════════════
# 📅 STUDY PLAN SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════════

class StudyPlanCreate(BaseModel):
    test_profile_id: str
    status: PlanStatus = "active"

class StudyPlanRead(BaseModel):
    id: str
    test_profile_id: str
    user_id: int
    created_at: datetime
    updated_at: datetime
    status: PlanStatus
    version: int
    total_sessions: int
    weekly_milestones: List[Dict[str, Any]]
    generated_by_agent: Optional[str]
    generation_notes: Optional[str]

    class Config:
        from_attributes = True

class StudyPlanUpdate(BaseModel):
    status: Optional[PlanStatus] = None
    version: Optional[int] = None
    weekly_milestones: Optional[List[Dict[str, Any]]] = None

# ═══════════════════════════════════════════════════════════════════════════════════
# 📚 STUDY SESSION SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════════

class StudySessionCreate(BaseModel):
    study_plan_id: str
    scheduled_at: datetime
    duration_minutes: int
    topic: str
    session_type: str
    module_id: Optional[str] = None

class StudySessionRead(BaseModel):
    id: str
    study_plan_id: str
    user_id: int
    scheduled_at: datetime
    duration_minutes: int
    topic: str
    session_type: str
    module_id: Optional[str]
    status: SessionStatus
    completed_at: Optional[datetime]
    performance_score: Optional[float]
    user_notes: Optional[str]
    agent_notes: Optional[str]

    class Config:
        from_attributes = True

class StudySessionUpdate(BaseModel):
    status: Optional[SessionStatus] = None
    completed_at: Optional[datetime] = None
    performance_score: Optional[float] = None
    user_notes: Optional[str] = None
    agent_notes: Optional[str] = None

# ═══════════════════════════════════════════════════════════════════════════════════
# 🔔 REMINDER SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════════

class SessionReminderRead(BaseModel):
    id: str
    session_id: str
    user_id: int
    fire_at: datetime
    reminder_type: str
    status: ReminderStatus
    sent_at: Optional[datetime]
    payload: Dict[str, Any]

    class Config:
        from_attributes = True

# ═══════════════════════════════════════════════════════════════════════════════════
# 📈 PROGRESS / DASHBOARD SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════════

class PlanEventRead(BaseModel):
    id: str
    study_plan_id: str
    user_id: int
    created_at: datetime
    event_type: str
    reasoning: Optional[str]
    payload: Dict[str, Any]

    class Config:
        from_attributes = True

class ProgressDashboardStats(BaseModel):
    mastery_by_topic: Dict[str, float]
    sessions_completed: int
    sessions_total: int
    recent_events: List[PlanEventRead]
