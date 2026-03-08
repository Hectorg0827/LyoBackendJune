"""
Database models for the Persistent Relationship System (Pillar 4).
Tracks the evolving relationship between Lyo and each member.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List

from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, JSON, Float, Text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from lyo_app.core.database import Base
from lyo_app.tenants.mixins import TenantMixin


class MilestoneType(str, Enum):
    """Types of milestones in the learner's journey."""
    FIRST_LESSON = "first_lesson"
    FIRST_GOAL_SET = "first_goal_set"
    FIRST_GOAL_ACHIEVED = "first_goal_achieved"
    STREAK_7 = "streak_7"
    STREAK_30 = "streak_30"
    STREAK_100 = "streak_100"
    SKILL_MASTERED = "skill_mastered"
    COURSE_COMPLETED = "course_completed"
    REFLECTION_COUNT_10 = "reflection_count_10"
    PROOF_GENERATED = "proof_generated"
    COMMUNITY_FIRST_POST = "community_first_post"
    BREAKTHROUGH_MOMENT = "breakthrough_moment"
    CUSTOM = "custom"


class Milestone(TenantMixin, Base):
    """Records significant moments in the learner's journey."""
    __tablename__ = "milestones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    milestone_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)
    celebrated: Mapped[bool] = mapped_column(Boolean, default=False)
    achieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PersonalityProfile(TenantMixin, Base):
    """
    Lyo's adapted communication personality for each member.
    Evolves based on interaction patterns and preferences.
    """
    __tablename__ = "personality_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False, unique=True)

    # Communication style (0.0-1.0 scales)
    formality: Mapped[float] = mapped_column(Float, default=0.5)  # casual ⟷ formal
    humor_level: Mapped[float] = mapped_column(Float, default=0.4)  # serious ⟷ playful
    encouragement_intensity: Mapped[float] = mapped_column(Float, default=0.7)  # reserved ⟷ enthusiastic
    detail_level: Mapped[float] = mapped_column(Float, default=0.5)  # concise ⟷ thorough
    challenge_level: Mapped[float] = mapped_column(Float, default=0.5)  # supportive ⟷ challenging

    # Preferred metaphor domains (e.g. ["sports", "cooking", "music"])
    metaphor_domains: Mapped[Optional[List]] = mapped_column(JSON, default=list)

    # Detected preferences
    prefers_visual: Mapped[bool] = mapped_column(Boolean, default=False)
    prefers_examples_first: Mapped[bool] = mapped_column(Boolean, default=True)
    prefers_socratic: Mapped[bool] = mapped_column(Boolean, default=False)

    # Adaptation history
    adaptation_log: Mapped[Optional[List]] = mapped_column(JSON, default=list)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RelationshipMemory(TenantMixin, Base):
    """
    Long-term episodic memory for the learner-Lyo relationship.
    Stores key moments, inside jokes, emotional landmarks, etc.
    """
    __tablename__ = "relationship_memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # Categories: "breakthrough", "struggle_overcome", "emotional_support",
    #             "inside_joke", "preference_learned", "habit_formed"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[float] = mapped_column(Float, default=0.5)  # 0-1
    source: Mapped[str] = mapped_column(String(50), default="system")  # system, reflection, chat
    metadata_json: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
