"""
Personalization database models for hyper-personalized tutoring
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON, Boolean, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from lyo_app.core.database import Base

class MasteryLevel(enum.Enum):
    NOVICE = "novice"
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"

class AffectState(enum.Enum):
    FRUSTRATED = "frustrated"
    CONFUSED = "confused"
    BORED = "bored"
    ENGAGED = "engaged"
    FLOW = "flow"

class LearnerState(Base):
    """Core learner state tracking"""
    __tablename__ = "learner_states"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, index=True)
    
    # Cognitive state
    overall_mastery = Column(Float, default=0.0)  # 0-1 scale
    learning_velocity = Column(Float, default=0.5)  # Rate of learning
    forgetting_rate = Column(Float, default=0.1)  # Forgetting curve parameter
    optimal_difficulty = Column(Float, default=0.5)  # Sweet spot difficulty
    
    # Affective state
    current_affect = Column(SQLEnum(AffectState), default=AffectState.ENGAGED)
    affect_confidence = Column(Float, default=0.0)
    valence = Column(Float, default=0.0)  # -1 to 1 (negative to positive)
    arousal = Column(Float, default=0.5)  # 0 to 1 (calm to excited)
    
    # Session state
    fatigue_level = Column(Float, default=0.0)
    focus_level = Column(Float, default=0.7)
    session_start = Column(DateTime, nullable=True)
    last_break = Column(DateTime, nullable=True)
    
    # Preferences
    reading_level = Column(Integer, default=8)  # Grade level
    preferred_pace = Column(String, default="moderate")  # slow/moderate/fast
    prefers_visual = Column(Boolean, default=True)
    prefers_audio = Column(Boolean, default=False)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships commented out due to missing FK between LearnerState and related tables
    # mastery_records = relationship("LearnerMastery", back_populates="learner", cascade="all, delete-orphan")
    # affect_samples = relationship("AffectSample", back_populates="learner", cascade="all, delete-orphan")
    # repetition_schedules = relationship("SpacedRepetitionSchedule", back_populates="learner", cascade="all, delete-orphan")

class LearnerMastery(Base):
    """Per-skill mastery tracking with uncertainty"""
    __tablename__ = "learner_mastery"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    skill_id = Column(String, index=True)  # e.g., "linear_equations", "photosynthesis"
    
    # Deep Knowledge Tracing parameters
    mastery_level = Column(Float, default=0.0)  # 0-1 probability of mastery
    uncertainty = Column(Float, default=0.5)  # Confidence in mastery estimate
    
    # Performance tracking
    attempts = Column(Integer, default=0)
    successes = Column(Integer, default=0)
    hints_used = Column(Integer, default=0)
    avg_time_to_solve = Column(Float, nullable=True)
    
    # Misconception tracking
    misconceptions = Column(JSON, default=list)  # List of identified misconceptions
    error_patterns = Column(JSON, default=dict)  # Common error types and frequencies
    
    # Learning trajectory
    last_seen = Column(DateTime, default=datetime.utcnow)
    first_attempt = Column(DateTime, default=datetime.utcnow)
    mastery_achieved = Column(DateTime, nullable=True)
    
    # Relationships
    # learner = relationship("LearnerState", back_populates="mastery_records")

class AffectSample(Base):
    """Aggregated affect samples (privacy-preserving)"""
    __tablename__ = "affect_samples"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    
    # Aggregated signals (never raw data)
    valence = Column(Float)  # -1 to 1
    arousal = Column(Float)  # 0 to 1
    confidence = Column(Float)  # 0 to 1
    
    # Context
    lesson_id = Column(Integer, nullable=True)
    skill_id = Column(String, nullable=True)
    activity_type = Column(String)  # reading/problem_solving/watching
    
    # Source (for transparency)
    source = Column(JSON)  # ["typing_rhythm", "heart_rate"]
    
    # Privacy
    timestamp = Column(DateTime, default=datetime.utcnow)
    aggregation_window = Column(Integer, default=60)  # Seconds
    
    # Relationships
    # learner = relationship("LearnerState", back_populates="affect_samples")

class SpacedRepetitionSchedule(Base):
    """Spaced repetition scheduling for optimal retention"""
    __tablename__ = "spaced_repetition_schedules"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    skill_id = Column(String, index=True)
    item_id = Column(String, index=True)  # Question/concept ID
    
    # Scheduling parameters
    interval = Column(Integer, default=1)  # Days until next review
    easiness_factor = Column(Float, default=2.5)  # Difficulty modifier
    repetitions = Column(Integer, default=0)
    
    # Performance
    last_review = Column(DateTime, nullable=True)
    next_review = Column(DateTime, nullable=True)
    last_grade = Column(Integer, nullable=True)  # 0-5 scale
    
    # Relationships
    # learner = relationship("LearnerState", back_populates="repetition_schedules")
