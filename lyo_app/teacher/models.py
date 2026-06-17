"""Teacher-in-the-loop models (institutional adoption play).

Two additive tables (no changes to existing tables — safe for the prod
Postgres DB):

- ``ContentReview`` — a review record for an AI-drafted course. Instructors
  approve / flag / request-changes; approval is what flips the underlying
  ``GraphCourse.is_published`` gate so students can see it.
- ``StudentAlert`` — "AI flags, teacher intervenes": at-risk signals (e.g. a
  detected learning plateau) raised for an instructor to acknowledge/resolve.
"""
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Column, DateTime, Integer, String, Text,
)
from sqlalchemy import Enum as SQLEnum

from lyo_app.core.database import Base


class ReviewStatus(str, Enum):
    PENDING = "pending"                 # awaiting instructor review
    APPROVED = "approved"               # published to students
    FLAGGED = "flagged"                 # held back, quality/accuracy concern
    CHANGES_REQUESTED = "changes_requested"  # needs revision, then re-review


class AlertStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class ContentReview(Base):
    """Instructor review of an AI-drafted course (keyed by GraphCourse.id)."""
    __tablename__ = "content_reviews"

    id = Column(Integer, primary_key=True, index=True)
    # GraphCourse.id is a UUID string; kept as a soft reference (no hard FK) so
    # this table is fully decoupled from the classroom schema.
    course_id = Column(String(36), nullable=False, index=True)
    course_title = Column(String(500), nullable=True)

    status = Column(SQLEnum(ReviewStatus), nullable=False,
                    default=ReviewStatus.PENDING, index=True)
    submitted_by = Column(Integer, nullable=False, index=True)   # author/creator
    reviewer_id = Column(Integer, nullable=True, index=True)     # instructor who acted
    notes = Column(Text, nullable=True)                          # instructor feedback

    # Snapshot of the automated QA verdict at submission time (advisory).
    qa_score = Column(Integer, nullable=True)            # 0-100
    qa_recommendation = Column(String(64), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    reviewed_at = Column(DateTime, nullable=True)


class StudentAlert(Base):
    """An at-risk signal for an instructor (AI flags -> teacher intervenes)."""
    __tablename__ = "student_alerts"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, nullable=False, index=True)
    instructor_id = Column(Integer, nullable=True, index=True)  # who claimed it

    trigger = Column(String(64), nullable=False)   # e.g. learning_plateau
    detail = Column(Text, nullable=True)           # human-readable reason
    skill_id = Column(String(255), nullable=True)
    course_id = Column(String(36), nullable=True)

    status = Column(SQLEnum(AlertStatus), nullable=False,
                    default=AlertStatus.OPEN, index=True)
    resolution_notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    resolved_at = Column(DateTime, nullable=True)
