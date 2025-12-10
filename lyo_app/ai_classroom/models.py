"""
AI Classroom Models - Graph-Based Learning Engine

This module defines the core data models for Lyo's "Interactive Cinema + Adaptive Tutor" system.

Architecture:
- Course: The top-level container (like a Netflix Series)
- LearningNode: Individual content units (Scenes, Interactions, Remediation)
- LearningEdge: Connections between nodes with conditions (pass/fail branching)
- MasteryState: Per-user, per-objective learning progress
- Concept: Subject matter taxonomy
- Misconception: Common errors mapped to concepts
- ReviewSchedule: Spaced repetition tracking

This is not a linear "list of lessons" - it's a directed graph that adapts.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
import uuid

from sqlalchemy import (
    Column, String, Text, Integer, Boolean, DateTime, JSON,
    ForeignKey, Index, Float, Enum as SQLEnum, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID, ARRAY
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func

from lyo_app.core.database import Base


# =============================================================================
# ENUMS
# =============================================================================

class NodeType(str, Enum):
    """Types of learning nodes in the graph"""
    NARRATIVE = "narrative"          # Story-based content (the "cinema" part)
    INTERACTION = "interaction"      # Knowledge checks (quiz, drag-drop, etc.)
    REMEDIATION = "remediation"      # Generated when user fails
    SUMMARY = "summary"              # Recap nodes
    REVIEW = "review"                # Spaced repetition nodes
    HOOK = "hook"                    # Attention-grabbing intro
    TRANSITION = "transition"        # Bridge between concepts


class EdgeCondition(str, Enum):
    """Conditions for traversing edges"""
    ALWAYS = "always"                # Default path
    PASS = "pass"                    # User answered correctly
    FAIL = "fail"                    # User answered incorrectly
    MASTERY_LOW = "mastery_low"      # Mastery score < threshold
    MASTERY_HIGH = "mastery_high"    # Mastery score >= threshold
    OPTIONAL = "optional"            # User can skip


class InteractionType(str, Enum):
    """Types of interactive elements"""
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    SLIDER = "slider"
    DRAG_MATCH = "drag_match"
    SHORT_ANSWER = "short_answer"
    PREDICTION = "prediction"        # "What do you think happens next?"


class AssetTier(str, Enum):
    """Cost tiers for visual assets"""
    HERO = "hero"          # DALL-E 3 - expensive, key moments only
    STOCK = "stock"        # Vector search existing images - free
    ABSTRACT = "abstract"  # CSS gradients/patterns - free


class SkillType(str, Enum):
    """Types of skills being assessed"""
    DEFINITION = "definition"
    APPLICATION = "application"
    CALCULATION = "calculation"
    INFERENCE = "inference"
    RECALL = "recall"


# =============================================================================
# COURSE MODEL (The Series)
# =============================================================================

class GraphCourse(Base):
    """
    A GraphCourse is like a Netflix Series.
    Contains metadata and points to the entry node of the learning graph.
    
    Note: Named GraphCourse to avoid conflict with the existing Course model
    in lyo_app/learning/models.py which uses integer IDs.
    """
    __tablename__ = "graph_courses"
    
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    
    # Basic Info
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    subject: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    grade_band: Mapped[str] = mapped_column(String(50), nullable=True)  # e.g., "6-8", "9-12"
    
    # Visual Theme
    visual_theme: Mapped[str] = mapped_column(String(50), default="modern")  # cyberpunk, nature, minimalist
    audio_mood: Mapped[str] = mapped_column(String(50), default="calm")
    
    # Graph Entry Point
    entry_node_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    
    # Metadata
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=30)
    difficulty: Mapped[str] = mapped_column(String(50), default="intermediate")
    learning_objectives: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)
    prerequisites: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)
    
    # Generation Context
    source_intent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Original user request
    source_conversation_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    
    # Publishing
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    is_template: Mapped[bool] = mapped_column(Boolean, default=False)  # Gold standard courses
    created_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    
    # Relationships
    nodes = relationship("LearningNode", back_populates="course", cascade="all, delete-orphan")
    edges = relationship("LearningEdge", back_populates="course", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('ix_graph_courses_subject_grade', 'subject', 'grade_band'),
    )


# =============================================================================
# LEARNING NODE MODEL (The Scenes)
# =============================================================================

class LearningNode(Base):
    """
    A single unit of learning content.
    Can be a narrative scene, an interaction, remediation, or review.
    """
    __tablename__ = "learning_nodes"
    
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    course_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("graph_courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Node Type
    node_type: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # Content Payload (The "Script")
    content: Mapped[Dict] = mapped_column(JSON, nullable=False, default=dict)
    # Structure varies by node_type:
    # NARRATIVE: { "narration": str, "visual_prompt": str, "keywords": [], "audio_mood": str }
    # INTERACTION: { "prompt": str, "options": [], "correct_feedback": str, "wrong_feedback": str }
    # REMEDIATION: { "analogy": str, "narration": str, "visual_prompt": str }
    
    # Learning Objective Link
    objective_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    concept_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("concepts.id"), nullable=True
    )
    
    # Prerequisites (node IDs that must be completed first)
    prerequisites: Mapped[Optional[List]] = mapped_column(JSON, nullable=True, default=list)
    
    # Timing
    estimated_seconds: Mapped[int] = mapped_column(Integer, default=15)
    
    # Asset Management
    asset_tier: Mapped[str] = mapped_column(String(20), default=AssetTier.ABSTRACT.value)
    generated_asset_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    generated_audio_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # For Interactions
    interaction_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    skill_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    misconception_tags: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)
    
    # Remediation Config
    remediation_budget: Mapped[int] = mapped_column(Integer, default=2)  # Max retries
    fallback_node_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)  # Gold standard fallback
    
    # Ordering (for linear fallback)
    sequence_order: Mapped[int] = mapped_column(Integer, default=0)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    
    # Relationships
    course = relationship("GraphCourse", back_populates="nodes")
    concept = relationship("Concept", back_populates="nodes")
    outgoing_edges = relationship(
        "LearningEdge", 
        foreign_keys="LearningEdge.from_node_id",
        back_populates="from_node"
    )
    incoming_edges = relationship(
        "LearningEdge",
        foreign_keys="LearningEdge.to_node_id", 
        back_populates="to_node"
    )
    
    __table_args__ = (
        Index('ix_learning_nodes_course_sequence', 'course_id', 'sequence_order'),
    )


# =============================================================================
# LEARNING EDGE MODEL (The Branches)
# =============================================================================

class LearningEdge(Base):
    """
    Directed edge between two learning nodes.
    Defines the conditions for traversal (pass/fail branching).
    """
    __tablename__ = "learning_edges"
    
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    course_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("graph_courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Connection
    from_node_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("learning_nodes.id", ondelete="CASCADE"), nullable=False
    )
    to_node_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("learning_nodes.id", ondelete="CASCADE"), nullable=False
    )
    
    # Condition for traversal
    condition: Mapped[str] = mapped_column(String(50), default=EdgeCondition.ALWAYS.value)
    
    # For mastery-based routing
    mastery_threshold: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Weight for adaptive routing (higher = more likely to be chosen)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    
    # Relationships
    course = relationship("GraphCourse", back_populates="edges")
    from_node = relationship("LearningNode", foreign_keys=[from_node_id], back_populates="outgoing_edges")
    to_node = relationship("LearningNode", foreign_keys=[to_node_id], back_populates="incoming_edges")
    
    __table_args__ = (
        Index('ix_learning_edges_from', 'from_node_id'),
        Index('ix_learning_edges_to', 'to_node_id'),
        UniqueConstraint('from_node_id', 'to_node_id', 'condition', name='uq_edge_connection'),
    )


# =============================================================================
# CONCEPT TAXONOMY
# =============================================================================

class Concept(Base):
    """
    A concept in the subject matter taxonomy.
    Used to map content to learning objectives.
    """
    __tablename__ = "concepts"
    
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    
    # Identity
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Taxonomy
    subject: Mapped[str] = mapped_column(String(100), nullable=False)  # Index via composite
    grade_band: Mapped[str] = mapped_column(String(50), nullable=True)
    parent_concept_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("concepts.id"), nullable=True
    )
    
    # Importance for prioritization
    priority: Mapped[int] = mapped_column(Integer, default=5)  # 1-10
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    
    # Relationships
    nodes = relationship("LearningNode", back_populates="concept")
    misconceptions = relationship("Misconception", back_populates="concept")
    
    __table_args__ = (
        Index('ix_concepts_subject', 'subject', 'grade_band'),
        UniqueConstraint('name', 'subject', name='uq_concept_name_subject'),
    )


# =============================================================================
# MISCONCEPTION MODEL
# =============================================================================

class Misconception(Base):
    """
    Common misconceptions for a concept.
    Used to generate targeted remediation.
    """
    __tablename__ = "misconceptions"
    
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    concept_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Identity
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Examples of wrong beliefs
    example_wrong_beliefs: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)
    
    # Remediation hints
    remediation_strategy: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    suggested_analogy: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Frequency tracking
    occurrence_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Relationships
    concept = relationship("Concept", back_populates="misconceptions")


# =============================================================================
# MASTERY STATE MODEL (Per-User Learning Progress)
# =============================================================================

class MasteryState(Base):
    """
    Tracks a user's mastery of a specific concept/objective.
    This is the "brain" that makes the system adaptive.
    """
    __tablename__ = "mastery_states"
    
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    
    # What are we tracking?
    concept_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("concepts.id"), nullable=True
    )
    objective_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    
    # Mastery Metrics
    mastery_score: Mapped[float] = mapped_column(Float, default=0.0)  # 0.0 to 1.0
    confidence: Mapped[float] = mapped_column(Float, default=0.5)     # How sure are we?
    
    # History
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    incorrect_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Error Tracking
    error_pattern: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    misconception_tags: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)
    
    # Timing
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_correct: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Trend (is the user improving?)
    trend: Mapped[str] = mapped_column(String(20), default="stable")  # improving, declining, stable
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    
    __table_args__ = (
        Index('ix_mastery_user_concept', 'user_id', 'concept_id'),
        Index('ix_mastery_user_objective', 'user_id', 'objective_id'),
        UniqueConstraint('user_id', 'concept_id', name='uq_user_concept_mastery'),
    )


# =============================================================================
# REVIEW SCHEDULE (Spaced Repetition)
# =============================================================================

class ReviewSchedule(Base):
    """
    Spaced repetition scheduler.
    Tracks when content should be reviewed for optimal retention.
    """
    __tablename__ = "review_schedules"
    
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    
    # What to review
    node_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("learning_nodes.id", ondelete="CASCADE"), nullable=True
    )
    concept_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("concepts.id"), nullable=True
    )
    
    # SM-2 Algorithm Fields
    easiness_factor: Mapped[float] = mapped_column(Float, default=2.5)  # EF
    interval_days: Mapped[int] = mapped_column(Integer, default=1)       # Current interval
    repetition_number: Mapped[int] = mapped_column(Integer, default=0)   # n
    
    # Scheduling
    next_review_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    last_reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Performance
    last_quality: Mapped[int] = mapped_column(Integer, default=3)  # 0-5 quality rating
    streak: Mapped[int] = mapped_column(Integer, default=0)
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    
    __table_args__ = (
        Index('ix_review_user_next', 'user_id', 'next_review_at'),
        Index('ix_review_active', 'user_id', 'is_active'),
    )


# =============================================================================
# INTERACTION ATTEMPT (User Response Tracking)
# =============================================================================

class InteractionAttempt(Base):
    """
    Records each user attempt at an interaction.
    Used for analytics and adaptive routing.
    """
    __tablename__ = "interaction_attempts"
    
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    node_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("learning_nodes.id", ondelete="CASCADE"), nullable=False
    )
    
    # Response
    user_answer: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    
    # Timing
    time_taken_seconds: Mapped[float] = mapped_column(Float, nullable=True)
    
    # Context
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)  # Which try was this?
    remediation_shown: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Detected issues
    detected_misconception_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("misconceptions.id"), nullable=True
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    
    __table_args__ = (
        Index('ix_attempts_user_node', 'user_id', 'node_id'),
        Index('ix_attempts_created', 'created_at'),
    )


# =============================================================================
# COURSE PROGRESS (User's Position in Course)
# =============================================================================

class CourseProgress(Base):
    """
    Tracks a user's progress through a course graph.
    """
    __tablename__ = "course_progress"
    
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    course_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("graph_courses.id", ondelete="CASCADE"), nullable=False
    )
    
    # Current Position
    current_node_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    
    # Completed Nodes
    completed_node_ids: Mapped[List] = mapped_column(JSON, default=list)
    
    # Stats
    total_time_seconds: Mapped[int] = mapped_column(Integer, default=0)
    interactions_completed: Mapped[int] = mapped_column(Integer, default=0)
    interactions_passed: Mapped[int] = mapped_column(Integer, default=0)
    remediations_triggered: Mapped[int] = mapped_column(Integer, default=0)
    
    # Status
    status: Mapped[str] = mapped_column(String(50), default="in_progress")  # in_progress, completed, paused
    completion_percentage: Mapped[float] = mapped_column(Float, default=0.0)
    
    # Timestamps
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    __table_args__ = (
        Index('ix_progress_user_course', 'user_id', 'course_id'),
        UniqueConstraint('user_id', 'course_id', name='uq_user_course_progress'),
    )


# =============================================================================
# CELEBRATION CONFIG (Success Animations)
# =============================================================================

class CelebrationConfig(Base):
    """
    Configuration for success celebrations.
    Stores the avatar, animation type, and triggers.
    """
    __tablename__ = "celebration_configs"
    
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    
    # Trigger
    trigger_type: Mapped[str] = mapped_column(String(50), nullable=False)  # interaction_pass, module_complete, streak
    min_streak: Mapped[int] = mapped_column(Integer, default=1)
    
    # Display
    avatar_url: Mapped[str] = mapped_column(String(500), nullable=False)
    animation_type: Mapped[str] = mapped_column(String(50), default="confetti")  # confetti, fireworks, stars
    sound_effect: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    message_template: Mapped[str] = mapped_column(String(500), default="Great job! 🎉")
    
    # A/B Testing
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)


# =============================================================================
# AD PLACEMENT CONFIG (Monetization)
# =============================================================================

class AdPlacementConfig(Base):
    """
    Configuration for ad placements during latency windows.
    """
    __tablename__ = "ad_placement_configs"
    
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    
    # Placement
    placement_type: Mapped[str] = mapped_column(String(50), nullable=False)  # loading, between_modules, remediation_wait
    
    # Conditions
    min_latency_ms: Mapped[int] = mapped_column(Integer, default=2000)  # Only show if latency > 2s
    max_frequency_per_session: Mapped[int] = mapped_column(Integer, default=3)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=300)  # 5 min between ads
    
    # Ad Config
    ad_unit_id: Mapped[str] = mapped_column(String(200), nullable=False)  # Google AdMob unit ID
    ad_format: Mapped[str] = mapped_column(String(50), default="interstitial")  # interstitial, rewarded, banner
    
    # Targeting
    target_subjects: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)  # null = all
    exclude_premium: Mapped[bool] = mapped_column(Boolean, default=True)  # No ads for premium users
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
