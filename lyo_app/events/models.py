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
    
    # Background processing status
    processed_for_mastery = Column(Integer, nullable=False, default=0) # 0=Pending, 1=Processed, -1=Error
    
    # Metadata
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
