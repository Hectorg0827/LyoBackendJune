"""
Affect computing models for privacy-preserving emotion and engagement tracking
"""

from sqlalchemy import Column, Integer, Float, DateTime, ForeignKey, String, Boolean, JSON
from datetime import datetime

from lyo_app.core.database import Base

class AffectiveState(Base):
    """Aggregated affective states for privacy preservation"""
    __tablename__ = "affective_states"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    
    # Emotional state indicators (aggregated over time windows)
    engagement_level = Column(Float)  # 0-1 normalized engagement
    frustration_level = Column(Float)  # 0-1 normalized frustration
    confidence_level = Column(Float)  # 0-1 self-reported confidence
    attention_level = Column(Float)  # 0-1 focus/attention metric
    
    # Learning context
    content_type = Column(String)  # reading/video/practice/quiz
    subject_area = Column(String)
    difficulty_level = Column(String)
    
    # Session context
    session_duration_minutes = Column(Float)
    time_of_day = Column(String)  # morning/afternoon/evening
    day_of_week = Column(String)
    
    # Aggregation metadata
    sample_count = Column(Integer)  # How many individual samples this represents
    confidence_interval = Column(Float)  # Statistical confidence
    
    # Privacy-preserving flags
    is_anonymized = Column(Boolean, default=True)
    aggregation_window_minutes = Column(Integer, default=30)
    
    # Timestamps
    window_start = Column(DateTime)
    window_end = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

class EmotionalPattern(Base):
    """Long-term emotional learning patterns"""
    __tablename__ = "emotional_patterns"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    
    # Pattern identification
    pattern_type = Column(String)  # peak_performance/struggle_zone/fatigue_point
    subject_area = Column(String)
    
    # Pattern characteristics
    trigger_conditions = Column(JSON)  # What causes this pattern
    typical_duration_minutes = Column(Float)
    recovery_strategies = Column(JSON)  # What helps overcome negative patterns
    
    # Performance correlation
    performance_impact = Column(Float)  # -1 to 1 correlation with learning outcomes
    accuracy_correlation = Column(Float)
    completion_rate_correlation = Column(Float)
    
    # Temporal patterns
    preferred_time_of_day = Column(String)
    optimal_session_length = Column(Float)
    break_frequency_minutes = Column(Float)
    
    # Confidence metrics
    pattern_strength = Column(Float)  # How consistent this pattern is
    sample_size = Column(Integer)
    last_observed = Column(DateTime)
    
    # Timestamps
    first_detected = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class WellbeingMetrics(Base):
    """Holistic wellbeing indicators for learner health"""
    __tablename__ = "wellbeing_metrics"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    
    # Stress indicators (aggregated and normalized)
    cognitive_load = Column(Float)  # 0-1 current mental capacity usage
    stress_level = Column(Float)  # 0-1 stress indicator
    fatigue_level = Column(Float)  # 0-1 mental fatigue
    
    # Motivation indicators
    intrinsic_motivation = Column(Float)  # 0-1 internal drive
    self_efficacy = Column(Float)  # 0-1 belief in ability to succeed
    goal_alignment = Column(Float)  # 0-1 alignment with personal goals
    
    # Social learning indicators
    peer_interaction_comfort = Column(Float)  # Comfort with collaboration
    help_seeking_tendency = Column(Float)  # Likelihood to ask for help
    mentorship_receptiveness = Column(Float)  # Openness to guidance
    
    # Learning preferences (inferred)
    preferred_challenge_level = Column(Float)  # 0-1 preferred difficulty
    preferred_pace = Column(String)  # slow/moderate/fast
    preferred_modality = Column(String)  # visual/auditory/kinesthetic/mixed
    
    # Context
    measurement_context = Column(String)  # study_session/assessment/break
    
    # Quality indicators
    data_quality_score = Column(Float)  # Confidence in measurements
    measurement_count = Column(Integer)  # Number of underlying samples
    
    # Timestamps
    measurement_date = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
