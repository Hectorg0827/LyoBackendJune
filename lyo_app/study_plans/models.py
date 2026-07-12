"""SQLAlchemy models for the "I Have a Test" prep system."""
import uuid
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, JSON, ForeignKey, Numeric, Date
)
from lyo_app.core.database import Base


def generate_uuid():
    return str(uuid.uuid4())


class TestProfile(Base):
    """Stores the intake configuration and user info for a specific test."""
    __tablename__ = "test_profiles"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Core test info
    subject = Column(String(100), nullable=False)
    test_date = Column(Date, nullable=False)
    test_format = Column(String(50))  # multiple_choice, essay, oral, mixed
    
    # Content scope
    topics = Column(JSON, default=list, nullable=False)  # list of dicts: {name, weight, confidence}
    materials = Column(JSON, default=list, nullable=False)  # list of dicts: {type, url, name}
    
    # User context
    baseline_confidence = Column(Integer, default=5)
    daily_minutes_available = Column(Integer, default=45)
    study_days_per_week = Column(Integer, default=5)
    stress_level = Column(Integer, default=5)
    
    # Intake metadata
    intake_complete = Column(Boolean, default=False, nullable=False)
    intake_transcript = Column(JSON, default=list, nullable=False)  # chat log history


class StudyPlan(Base):
    """The generated roadmap containing milestones and referencing the test profile."""
    __tablename__ = "study_plans"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    test_profile_id = Column(String(36), ForeignKey("test_profiles.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    status = Column(String(20), default="active", nullable=False, index=True)  # active, paused, completed, archived
    version = Column(Integer, default=1, nullable=False)
    
    total_sessions = Column(Integer, default=0)
    weekly_milestones = Column(JSON, default=list, nullable=False)  # [{week, focus, goals}]
    
    generated_by_agent = Column(String(50))
    generation_notes = Column(String(500))


class StudySession(Base):
    """Individual study session blocks scheduled for specific topics/types."""
    # Not "study_sessions": lyo_app/ai_study/models.py already owns that
    # table on the shared Base, and the duplicate definition made importing
    # both modules in one process raise InvalidRequestError.
    __tablename__ = "study_plan_sessions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    study_plan_id = Column(String(36), ForeignKey("study_plans.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    scheduled_at = Column(DateTime, nullable=False, index=True)
    duration_minutes = Column(Integer, nullable=False)
    
    topic = Column(String(200), nullable=False)
    session_type = Column(String(50), nullable=False)  # learn, practice, review, mock_test
    module_id = Column(String(36))  # link to course module
    
    status = Column(String(20), default="scheduled", nullable=False, index=True)  # scheduled, in_progress, completed, skipped
    completed_at = Column(DateTime)
    performance_score = Column(Numeric(3, 2))  # 0.00 to 1.00
    
    user_notes = Column(String(500))
    agent_notes = Column(String(500))


class SessionReminder(Base):
    """Session reminder notification jobs."""
    __tablename__ = "session_reminders"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(36), ForeignKey("study_plan_sessions.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    fire_at = Column(DateTime, nullable=False, index=True)
    reminder_type = Column(String(50), nullable=False)  # night_before, thirty_min, checkin_after
    
    status = Column(String(20), default="pending", nullable=False, index=True)  # pending, sent, failed, cancelled
    sent_at = Column(DateTime)
    payload = Column(JSON, default=dict, nullable=False)


class PlanEvent(Base):
    """Audit log tracking every adaptation, skipped session, or re-planning."""
    __tablename__ = "plan_events"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    study_plan_id = Column(String(36), ForeignKey("study_plans.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    event_type = Column(String(50), nullable=False)  # created, session_completed, session_skipped, replanned, adapted
    reasoning = Column(String(500))
    payload = Column(JSON, default=dict, nullable=False)
