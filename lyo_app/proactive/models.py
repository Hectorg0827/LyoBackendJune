"""
Database models for Proactive Intervention System
"""

from datetime import datetime, time
from typing import Optional, Dict, Any, List
from enum import Enum

from sqlalchemy import Column, String, Integer, Boolean, DateTime, JSON, Text, Time, ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from lyo_app.core.database import Base
from lyo_app.tenants.mixins import TenantMixin


class InterventionType(str, Enum):
    """Types of proactive interventions"""
    # Time-based
    MORNING_RITUAL = "morning_ritual"
    EVENING_REFLECTION = "evening_reflection"
    PRE_STUDY_CHECKIN = "pre_study_checkin"

    # Event-based
    STREAK_PRESERVATION = "streak_preservation"
    MILESTONE_CELEBRATION = "milestone_celebration"
    COMPLETION_PUSH = "completion_push"

    # Behavioral
    PLATEAU_INTERVENTION = "plateau_intervention"
    RETENTION_REFRESH = "retention_refresh"
    DIFFICULTY_ADJUSTMENT = "difficulty_adjustment"

    # Emotional
    EMOTIONAL_SUPPORT = "emotional_support"
    BURNOUT_PREVENTION = "burnout_prevention"
    MOMENTUM_BOOST = "momentum_boost"

    # Deadline-related
    PRE_DEADLINE = "pre_deadline"
    EXAM_PREP = "exam_prep"


class InterventionLog(TenantMixin, Base):
    """
    Logs all proactive interventions sent to users.
    Used for analytics and respecting notification fatigue.
    """

    __tablename__ = "intervention_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)

    # Intervention details
    intervention_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-10, higher = more urgent
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)

    # Delivery
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # User response
    user_response: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # 'engaged', 'dismissed', 'ignored', 'snoozed'
    response_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Context (for debugging and analysis)
    context: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UserNotificationPreferences(TenantMixin, Base):
    """
    User preferences for proactive notifications.
    Respects user's time and prevents notification fatigue.
    """

    __tablename__ = "user_notification_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)

    # Do Not Disturb
    dnd_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # Quiet hours
    quiet_hours_start: Mapped[Optional[time]] = mapped_column(
        Time, nullable=True
    )  # e.g., 22:00
    quiet_hours_end: Mapped[Optional[time]] = mapped_column(
        Time, nullable=True
    )  # e.g., 08:00

    # Daily limits
    max_notifications_per_day: Mapped[int] = mapped_column(Integer, default=5)

    # Intervention type preferences (array of enabled types)
    enabled_intervention_types: Mapped[Optional[List]] = mapped_column(
        ARRAY(String), nullable=True
    )
    disabled_intervention_types: Mapped[Optional[List]] = mapped_column(
        ARRAY(String), nullable=True
    )

    # Study time preferences (when user usually studies)
    preferred_study_times: Mapped[Optional[Dict]] = mapped_column(
        JSON, nullable=True
    )  # {day_of_week: [time_ranges]}

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )


class Intervention:
    """
    In-memory representation of a potential intervention.
    Not a database model - created by intervention engine, then logged if delivered.
    """

    def __init__(
        self,
        intervention_type: InterventionType,
        priority: int,
        title: str,
        message: str,
        action: str,
        timing: str = "immediate",
        context: Optional[Dict[str, Any]] = None
    ):
        self.intervention_type = intervention_type
        self.priority = priority
        self.title = title
        self.message = message
        self.action = action
        self.timing = timing  # 'immediate', 'scheduled', 'delayed'
        self.context = context or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intervention_type": self.intervention_type,
            "priority": self.priority,
            "title": self.title,
            "message": self.message,
            "action": self.action,
            "timing": self.timing,
            "context": self.context
        }


class UserState:
    """
    In-memory user state for intervention evaluation.
    Aggregates data from multiple sources for quick decision-making.
    """

    def __init__(self, user_id: int):
        self.user_id = user_id

        # Session data
        self.last_activity_hours: float = 0
        self.studied_today: bool = False
        self.session_count_week: int = 0

        # Streak data
        self.current_streak: int = 0
        self.longest_streak: int = 0

        # Performance data
        self.recent_accuracy: float = 0.0
        self.recent_sentiment: float = 0.0

        # Learning data
        self.primary_subject: Optional[str] = None
        self.current_course_progress: float = 0.0

        # Timing patterns
        self.usual_study_start_time: Optional[time] = None
