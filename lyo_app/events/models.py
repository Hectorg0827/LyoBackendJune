"""
Database models for the LearningEvent Log.
Enables event-driven tracking of the user's self-evolution.
"""

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Column, DateTime, Integer, String, ForeignKey,
    Enum as SQLEnum, Float, JSON
)

from lyo_app.core.database import Base


class EventType(str, Enum):
    """Types of learning events that can trigger state updates."""
    QUIZ_ANSWER = "quiz_answer"
    LESSON_COMPLETION = "lesson_completion"
    AI_SESSION = "ai_session"
    REFLECTION = "reflection"
    PROJECT = "project"
    VOICE_INTERACTION = "voice_interaction"
    # Evidence demonstrated inside the live classroom — a transfer prompt
    # answered, an explanation accepted, a review retrieved. Distinct from
    # QUIZ_ANSWER so a recap can tell a classroom demonstration from a chat
    # check without inspecting metadata.
    CLASSROOM_DEMONSTRATION = "classroom_demonstration"


class LearningEvent(Base):
    """
    Immutable log of user events that drive compounding growth.
    """
    
    __tablename__ = "learning_events"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    event_type = Column(SQLEnum(EventType), nullable=False, index=True)
    
    # Store JSON array of skill IDs associated with this event
    skill_ids_json = Column(JSON, nullable=True)
    
    # E.g., { "time_spent_seconds": 120, "difficulty_rating": 4 }
    metadata_json = Column(JSON, nullable=True)
    
    # E.g., quiz score, confidence level, XP earned directly from this event
    measurable_outcome = Column(Float, nullable=True)
    
    # ── Evidence ─────────────────────────────────────────────────────────
    #
    # What this event proves about one concept, in the vocabulary of
    # `lyo_app/events/evidence.py`. Every column is nullable: events predating
    # this (and the reflection/voice events that carry no graded evidence)
    # stay valid and simply contribute no rung.
    #
    # `skill_ids_json` above is unchanged and still drives the DKT update.
    # `concept_id` is the single concept this evidence is *about*, which is
    # what the classroom's mastery lookup keys on.

    # 80 to match slugify_skill's own cap. At String(64) an unusually long
    # topic slug would fail the insert, and the check endpoint swallows that
    # error — so the learner's answer would never reach the evidence stream at
    # all. Truncating instead risks two distinct topics colliding onto one
    # concept, which silently merges two learners' records.
    concept_id = Column(String(80), nullable=True, index=True)

    #: A rung of the ladder — exposure | recognition | explanation |
    #: application | transfer | retention. Stored normalized, so the wire's
    #: "retrieval" is written here as "retention".
    evidence_type = Column(String(32), nullable=True)

    #: 0..1, already damped by whatever help the learner needed.
    evidence_confidence = Column(Float, nullable=True)

    #: How much support was used. Kept alongside the damped confidence so the
    #: damping can be re-derived or re-tuned later without losing the input.
    hints_used = Column(Integer, nullable=False, default=0)

    #: The specific error, when the grader identified one. Survives a later
    #: correct retry so remediation can still target it.
    misconception = Column(String(500), nullable=True)

    #: chat | classroom | test_prep | course — which surface produced this.
    source_surface = Column(String(32), nullable=True, index=True)

    # Background processing status
    processed_for_mastery = Column(Integer, nullable=False, default=0) # 0=Pending, 1=Processed, -1=Error
    
    # Metadata
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
