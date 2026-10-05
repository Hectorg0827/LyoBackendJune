"""Persistence for Lyo Coach.

Only goals and derived caches live here.  Learner truth remains in
learning_events / mastery_states / concepts; duplicating mastery in the coach
would let Chat, Classroom and Test Prep disagree again.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)

from lyo_app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class LearningGoal(Base):
    """A learner outcome that the whole product can work toward."""

    __tablename__ = "learning_goals"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # test | assignment | mastery | course | recovery | certification
    goal_type = Column(String(32), nullable=False, index=True)
    title = Column(String(240), nullable=False)
    subject = Column(String(120), nullable=True, index=True)
    status = Column(String(20), nullable=False, default="active", index=True)

    deadline = Column(DateTime, nullable=True, index=True)
    desired_outcome = Column(JSON, nullable=False, default=dict)
    constraints = Column(JSON, nullable=False, default=dict)

    # Optional adapter identity.  It lets Test Prep, a course, an assignment,
    # etc. refer to one durable goal without creating duplicates.
    source_surface = Column(String(32), nullable=True)
    source_ref_type = Column(String(40), nullable=True)
    source_ref_id = Column(String(80), nullable=True)

    metadata_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "source_ref_type",
            "source_ref_id",
            name="uq_learning_goal_source",
        ),
        Index("ix_learning_goals_user_status_deadline", "user_id", "status", "deadline"),
    )


class GoalSkill(Base):
    """One skill/concept required by a goal.

    concept_id accepts either a persistent concept UUID or a canonical slug.
    That mirrors LearningEvent.concept_id and preserves the compatibility bridge
    while classroom skills continue moving to durable graph identities.
    """

    __tablename__ = "goal_skills"

    id = Column(String(36), primary_key=True, default=_uuid)
    goal_id = Column(
        String(36),
        ForeignKey("learning_goals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    concept_id = Column(String(80), nullable=False, index=True)
    display_name = Column(String(240), nullable=False)

    weight = Column(Float, nullable=False, default=1.0)
    required_rung = Column(String(32), nullable=False, default="transfer")
    priority = Column(Integer, nullable=False, default=5)
    parent_concept_id = Column(String(80), nullable=True)
    metadata_json = Column(JSON, nullable=False, default=dict)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("goal_id", "concept_id", name="uq_goal_skill_concept"),
        Index("ix_goal_skills_user_goal", "user_id", "goal_id"),
    )


class CoachSnapshot(Base):
    """Disposable context cache generated from structured source-of-truth state."""

    __tablename__ = "coach_snapshots"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    goal_id = Column(
        String(36),
        ForeignKey("learning_goals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_event_id = Column(Integer, nullable=True)
    goal_updated_at = Column(DateTime, nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    generated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "goal_id", name="uq_coach_snapshot_user_goal"),
    )
