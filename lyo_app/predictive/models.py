"""
Database models for Predictive Intelligence System
"""

from datetime import datetime, time
from typing import Optional, Dict, Any, List
from enum import Enum

from sqlalchemy import Column, String, Integer, Boolean, DateTime, JSON, Float, Text, ARRAY, Time
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from lyo_app.core.database import Base
from lyo_app.tenants.mixins import TenantMixin


class StrugglePrediction(TenantMixin, Base):
    """
    Stores predictions about user struggling with content.
    Used to intervene proactively before frustration sets in.
    """

    __tablename__ = "struggle_predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)

    # Content being predicted
    content_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'lesson', 'problem', 'quiz'

    # Prediction
    struggle_probability: Mapped[float] = mapped_column(
        Float, nullable=False
    )  # 0.0-1.0
    confidence: Mapped[float] = mapped_column(Float, nullable=False)  # 0.0-1.0

    # Features used for prediction
    prereq_mastery: Mapped[float] = mapped_column(Float, nullable=True)
    similar_performance: Mapped[float] = mapped_column(Float, nullable=True)
    content_difficulty: Mapped[float] = mapped_column(Float, nullable=True)
    days_since_review: Mapped[int] = mapped_column(Integer, nullable=True)
    cognitive_load: Mapped[float] = mapped_column(Float, nullable=True)
    sentiment_trend: Mapped[float] = mapped_column(Float, nullable=True)

    # Full feature set (for model improvement)
    prediction_features: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)

    # Actual outcome (for model training)
    actual_struggled: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    actual_outcome_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Intervention taken
    intervention_offered: Mapped[bool] = mapped_column(Boolean, default=False)
    intervention_accepted: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    # Timestamps
    predicted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class DropoutRiskScore(TenantMixin, Base):
    """
    Stores churn/dropout risk scores for users.
    Used to trigger re-engagement campaigns.
    """

    __tablename__ = "dropout_risk_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)

    # Risk score
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)  # 0.0-1.0
    risk_level: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'low', 'medium', 'high', 'critical'

    # Risk factors
    risk_factors: Mapped[List] = mapped_column(ARRAY(String), nullable=False)

    # Metrics contributing to score
    session_frequency_trend: Mapped[float] = mapped_column(Float, nullable=True)
    avg_days_between_sessions: Mapped[float] = mapped_column(Float, nullable=True)
    sentiment_trend_7d: Mapped[float] = mapped_column(Float, nullable=True)
    days_since_last_completion: Mapped[int] = mapped_column(Integer, nullable=True)
    performance_trend: Mapped[float] = mapped_column(Float, nullable=True)
    longest_streak: Mapped[int] = mapped_column(Integer, nullable=True)
    current_streak: Mapped[int] = mapped_column(Integer, nullable=True)

    # Re-engagement strategy
    reengagement_strategy: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)
    strategy_executed: Mapped[bool] = mapped_column(Boolean, default=False)
    strategy_executed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Outcome tracking
    user_returned: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    returned_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Timestamps
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )


class UserTimingProfile(TenantMixin, Base):
    """
    Stores user's optimal learning times based on historical performance.
    Used to schedule interventions and study sessions for maximum impact.
    """

    __tablename__ = "user_timing_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)

    # Peak learning times (hours when user performs best)
    peak_hours: Mapped[List] = mapped_column(
        ARRAY(Integer), nullable=True
    )  # [7, 8, 19, 20]
    optimal_study_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)

    # Day of week preferences
    best_days: Mapped[Optional[List]] = mapped_column(
        ARRAY(String), nullable=True
    )  # ['Monday', 'Wednesday']

    # Session patterns
    avg_session_duration_minutes: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    preferred_session_length: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )  # minutes

    # Performance by time
    performance_by_hour: Mapped[Optional[Dict]] = mapped_column(
        JSON, nullable=True
    )  # {7: 0.85, 8: 0.90, ...}

    # Engagement patterns
    most_active_hour: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    least_active_hour: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Streak patterns
    typical_study_days: Mapped[Optional[List]] = mapped_column(
        ARRAY(Integer), nullable=True
    )  # [1,2,3,4,5] for Mon-Fri

    # Data points used
    sessions_analyzed: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)  # 0.0-1.0

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


class LearningPlateau(TenantMixin, Base):
    """
    Detects when user is stuck on a topic for extended period.
    Used to trigger alternative learning approaches.
    """

    __tablename__ = "learning_plateaus"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)

    # Plateau details
    topic: Mapped[str] = mapped_column(String(200), nullable=False)
    skill_id: Mapped[str] = mapped_column(String(100), nullable=False)

    # Plateau metrics
    days_on_topic: Mapped[int] = mapped_column(Integer, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    mastery_level: Mapped[float] = mapped_column(Float, nullable=False)
    mastery_improvement: Mapped[float] = mapped_column(
        Float, nullable=False
    )  # Change in last week

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Intervention
    intervention_suggested: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # Alternative approach suggestion
    intervention_taken: Mapped[bool] = mapped_column(Boolean, default=False)

    # Timestamps
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )


class SkillRegression(TenantMixin, Base):
    """
    Tracks when user's mastery of a previously learned skill is declining.
    Used for spaced repetition and retention interventions.
    """

    __tablename__ = "skill_regressions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)

    # Skill details
    skill_id: Mapped[str] = mapped_column(String(100), nullable=False)
    skill_name: Mapped[str] = mapped_column(String(200), nullable=False)

    # Regression metrics
    peak_mastery: Mapped[float] = mapped_column(Float, nullable=False)
    current_mastery: Mapped[float] = mapped_column(Float, nullable=False)
    regression_amount: Mapped[float] = mapped_column(Float, nullable=False)

    # Time since last practice
    days_since_practice: Mapped[int] = mapped_column(Integer, nullable=False)
    last_practiced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Forgetting curve prediction
    predicted_mastery_in_week: Mapped[float] = mapped_column(Float, nullable=True)
    urgency: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'low', 'medium', 'high', 'critical'

    # Intervention
    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    reminder_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    user_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Timestamps
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
