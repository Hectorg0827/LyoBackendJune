"""Enhanced database models for LyoBackend v2."""

import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey, 
    JSON, Index, UniqueConstraint, Float, Enum as SQLEnum
)
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, Uuid, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum


from lyo_app.core.database import Base


class TaskState(str, enum.Enum):
    """Task execution states mapping from Celery states."""
    QUEUED = "QUEUED"      # Celery: PENDING
    RUNNING = "RUNNING"    # Celery: STARTED/PROGRESS  
    DONE = "DONE"          # Celery: SUCCESS
    ERROR = "ERROR"        # Celery: FAILURE


class ContentType(str, enum.Enum):
    """Content types for normalized content schema."""
    VIDEO = "video"
    ARTICLE = "article"
    EBOOK = "ebook"
    PDF = "pdf"
    PODCAST = "podcast"
    COURSE = "course"


class CourseStatus(str, enum.Enum):
    """Course generation/curation status."""
    DRAFT = "DRAFT"
    GENERATING = "GENERATING"
    PARTIAL = "PARTIAL" 
    READY = "READY"
    ERROR = "ERROR"


class PushPlatform(str, enum.Enum):
    """Push notification platforms."""
    IOS = "ios"
    ANDROID = "android"


# Note: User model moved to lyo_app.auth.models to avoid redundancy
from lyo_app.auth.models import User
# Note: Course and Lesson moved to lyo_app.learning.models to avoid redundancy
from lyo_app.learning.models import Course, Lesson


class ContentItem(Base):
    """Normalized content items with unified schema for one-screen UI."""
    __tablename__ = "content_items"
    
    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    lesson_id = Column(Integer, ForeignKey("lessons.id"), nullable=True)  # Optional lesson grouping
    
    # Content identification
    type = Column(SQLEnum(ContentType), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    
    # Source information
    source = Column(String(200), nullable=True)  # "YouTube", "Khan Academy", etc.
    source_url = Column(String(1000), nullable=True)
    external_id = Column(String(200), nullable=True)  # YouTube video ID, etc.
    
    # Unified metadata (type-specific fields)
    thumbnail_url = Column(String(500), nullable=True)
    duration_sec = Column(Integer, nullable=True)  # For videos/podcasts
    pages = Column(Integer, nullable=True)  # For PDFs/ebooks  
    word_count = Column(Integer, nullable=True)  # For articles
    file_size_bytes = Column(Integer, nullable=True)  # For downloadable content
    
    # Content description
    summary = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    attribution = Column(String(500), nullable=True)  # Author/creator
    
    # Categorization & discovery
    tags = Column(JSON, nullable=True)  # List of tags
    difficulty_level = Column(String(20), nullable=True)
    language = Column(String(10), default="en", nullable=False)
    
    # Quality & curation
    quality_score = Column(Float, nullable=True)  # AI-generated quality assessment
    curation_notes = Column(Text, nullable=True)  # Human/AI curation notes
    
    # Access & licensing
    is_free = Column(Boolean, default=True, nullable=False)
    requires_subscription = Column(Boolean, default=False, nullable=False)
    license_type = Column(String(100), nullable=True)  # CC, proprietary, etc.
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)  # Original content publish date
    
    # Relationships
    course = relationship("Course", back_populates="content_items")
    lesson = relationship("Lesson", back_populates="content_items")
    
    __table_args__ = (
        Index("ix_content_course_type", "course_id", "type"),
        Index("ix_content_lesson", "lesson_id"),
        Index("ix_content_source", "source", "external_id"),
    )
    
    def __repr__(self):
        return f"<ContentItem {self.title} ({self.type})>"


class Task(Base):
    """Async task tracking with WebSocket progress support."""
    __tablename__ = "tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Idempotency & deduplication
    idempotency_key = Column(String(100), unique=True, index=True, nullable=False)
    
    # Task metadata
    task_type = Column(String(50), nullable=False, index=True)  # "course_generation", etc.
    task_params = Column(JSON, nullable=True)  # Original parameters
    
    # Progress tracking
    state = Column(SQLEnum(TaskState), default=TaskState.QUEUED, nullable=False, index=True)
    progress_pct = Column(Integer, default=0, nullable=False)
    message = Column(String(500), nullable=True)  # Current status message
    
    # Results
    result_course_id = Column(Integer, ForeignKey("courses.id"), nullable=True)
    result_data = Column(JSON, nullable=True)  # Additional result metadata
    error_details = Column(JSON, nullable=True)  # Error information
    
    # For course generation specifically
    provisional_course_id = Column(Integer, ForeignKey("courses.id"), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="tasks")
    result_course = relationship("Course", foreign_keys=[result_course_id])
    provisional_course = relationship("Course", foreign_keys=[provisional_course_id])
    
    __table_args__ = (
        Index("ix_tasks_user_created", "user_id", "created_at"),
        Index("ix_tasks_state_type", "state", "task_type"),
    )
    
    def __repr__(self):
        return f"<Task {self.task_type} ({self.state})>"


class PushDevice(Base):
    """Push notification device registration."""
    __tablename__ = "push_devices"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    device_token = Column(String(200), nullable=False, index=True)
    platform = Column(SQLEnum(PushPlatform), nullable=False)
    
    # Device metadata
    locale = Column(String(10), nullable=True)
    app_version = Column(String(20), nullable=True)
    device_model = Column(String(100), nullable=True)
    os_version = Column(String(20), nullable=True)
    
    # Status tracking
    is_active = Column(Boolean, default=True, nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="push_devices")
    
    __table_args__ = (
        Index("ix_push_user_platform", "user_id", "platform"),
        UniqueConstraint("user_id", "device_token", name="uq_user_device_token"),
    )
    
    def __repr__(self):
        return f"<PushDevice {self.platform} for user {self.user_id}>"


class GamificationProfile(Base):
    """User gamification profile with XP, streaks, and badges."""
    __tablename__ = "gamification_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    
    # Experience points
    total_xp = Column(Integer, default=0, nullable=False)
    level = Column(Integer, default=1, nullable=False)
    xp_to_next_level = Column(Integer, default=100, nullable=False)
    
    # Streaks
    current_streak_days = Column(Integer, default=0, nullable=False)
    longest_streak_days = Column(Integer, default=0, nullable=False)
    last_activity_date = Column(DateTime(timezone=True), nullable=True)
    
    # Statistics
    courses_completed = Column(Integer, default=0, nullable=False)
    lessons_completed = Column(Integer, default=0, nullable=False)
    total_study_minutes = Column(Integer, default=0, nullable=False)
    
    # Badges and achievements (JSON array of badge IDs)
    badges = Column(JSON, default=list, nullable=False)
    achievements = Column(JSON, default=list, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="gamification_profile")
    
    def __repr__(self):
        return f"<GamificationProfile user={self.user_id} level={self.level}>"


class DiscoveryFeedItem(Base):
    """Feed items for community/discovery feed (AI generated)."""
    __tablename__ = "discovery_feed_items"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Content
    item_type = Column(String(50), nullable=False, index=True)  # "course_shared", "achievement", etc.
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=True)
    
    # References
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=True)
    
    # Metadata
    item_metadata = Column("metadata", JSON, nullable=True)
    image_url = Column(String(500), nullable=True)
    
    # Engagement
    like_count = Column(Integer, default=0)
    comment_count = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    
    # Relationships
    user = relationship("User")
    course = relationship("Course")
    
    __table_args__ = (
        Index("ix_feed_created", "created_at"),
        Index("ix_feed_type_created", "item_type", "created_at"),
    )
