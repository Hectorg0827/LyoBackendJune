"""Durable, user-owned navigation continuity between Lyo learning surfaces.

These tables do NOT contain grades or mastery. The evidence ledger remains
authoritative; each destination must separately authorize its course/exam.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint
from lyo_app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class LearningJourney(Base):
    __tablename__ = "learning_journeys"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    goal_id = Column(String(36), ForeignKey("learning_goals.id", ondelete="CASCADE"), nullable=False, index=True)
    start_request_id = Column(String(80), nullable=False)
    origin_surface = Column(String(24), nullable=False)
    origin_ref = Column(String(160), nullable=True)
    active_surface = Column(String(24), nullable=False)
    active_ref = Column(String(160), nullable=True)
    initial_context_json = Column(JSON, nullable=False, default=dict)
    context_json = Column(JSON, nullable=False, default=dict)
    status = Column(String(20), nullable=False, default="active")
    revision = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "start_request_id", name="uq_learning_journey_start"),
        Index("ix_learning_journeys_user_goal", "user_id", "goal_id"),
    )


class JourneyHandoff(Base):
    __tablename__ = "journey_handoffs"

    id = Column(String(36), primary_key=True, default=_uuid)
    journey_id = Column(String(36), ForeignKey("learning_journeys.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    request_id = Column(String(80), nullable=False)
    revision = Column(Integer, nullable=False)
    from_surface = Column(String(24), nullable=False)
    from_ref = Column(String(160), nullable=True)
    to_surface = Column(String(24), nullable=False)
    to_ref = Column(String(160), nullable=True)
    # The input and resulting context are recorded to distinguish retries
    # from reused idempotency keys with different requested actions.
    requested_context = Column(JSON, nullable=False, default=dict)
    context_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("journey_id", "request_id", name="uq_journey_handoff_request"),
        UniqueConstraint("journey_id", "revision", name="uq_journey_handoff_revision"),
    )
