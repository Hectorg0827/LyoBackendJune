"""Enhanced database models for LyoBackend v2."""

import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey, 
    JSON, Index, UniqueConstraint, Float, Enum as SQLEnum
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum


Base = declarative_base()


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


class User(Base):
    """Enhanced user model with authentication and profile data."""
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(100), unique=True, index=True, nullable=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    
    # Profile & preferences
    avatar_url = Column(String(500), nullable=True)
    bio = Column(Text, nullable=True)
    locale = Column(String(10), default="en", nullable=False)
    timezone = Column(String(50), default="UTC", nullable=False)
    
    # Account status
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    email_verified_at = Column(DateTime(timezone=True), nullable=True)
    
    # Authentication tracking
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    login_attempts = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    
    # Relationships
    courses = relationship("Course", back_populates="owner", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="user", cascade="all, delete-orphan")
    push_devices = relationship("PushDevice", back_populates="user", cascade="all, delete-orphan")
    gamification_profile = relationship("GamificationProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User {self.email}>"


class Course(Base):
    """Course model with normalized content structure."""
    __tablename__ = "courses"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Course metadata
    title = Column(String(500), nullable=False)
    topic = Column(String(200), nullable=False, index=True)
    summary = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    
    # Generation parameters (preserved for reproducibility)
    interests = Column(JSONB, nullable=True)  # List of interest keywords
    difficulty_level = Column(String(20), nullable=True)  # beginner/intermediate/advanced
    target_duration_hours = Column(Float, nullable=True)
    
    # Status tracking
    status = Column(SQLEnum(CourseStatus), default=CourseStatus.DRAFT, nullable=False, index=True)
    generation_metadata = Column(JSONB, nullable=True)  # Model version, prompts, etc.
    
    # SEO & Discovery
    tags = Column(JSONB, nullable=True)  # List of tags
    thumbnail_url = Column(String(500), nullable=True)
    estimated_duration_hours = Column(Float, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    owner = relationship("User", back_populates="courses")
    lessons = relationship("Lesson", back_populates="course", cascade="all, delete-orphan")
    content_items = relationship("ContentItem", back_populates="course", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("ix_courses_owner_created", "owner_user_id", "created_at"),
        Index("ix_courses_topic_status", "topic", "status"),
    )
    
    def __repr__(self):
        return f"<Course {self.title}>"


class Lesson(Base):
    """Individual lessons within a course."""
    __tablename__ = "lessons"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id"), nullable=False)
    
    title = Column(String(500), nullable=False)
    summary = Column(Text, nullable=True)
    order = Column(Integer, nullable=False)  # Sequence within course
    
    # Learning objectives
    objectives = Column(JSONB, nullable=True)  # List of learning objectives
    prerequisites = Column(JSONB, nullable=True)  # List of prerequisite concepts
    
    # Estimated timing
    estimated_duration_minutes = Column(Integer, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    
    # Relationships
    course = relationship("Course", back_populates="lessons")
    content_items = relationship("ContentItem", back_populates="lesson")
    
    __table_args__ = (
        Index("ix_lessons_course_order", "course_id", "order"),
        UniqueConstraint("course_id", "order", name="uq_lesson_course_order"),
    )
    
    def __repr__(self):
        return f"<Lesson {self.title}>"


class ContentItem(Base):
    """Normalized content items with unified schema for one-screen UI."""
    __tablename__ = "content_items"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id"), nullable=False)
    lesson_id = Column(UUID(as_uuid=True), ForeignKey("lessons.id"), nullable=True)  # Optional lesson grouping
    
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
    tags = Column(JSONB, nullable=True)  # List of tags
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
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Idempotency & deduplication
    idempotency_key = Column(String(100), unique=True, index=True, nullable=False)
    
    # Task metadata
    task_type = Column(String(50), nullable=False, index=True)  # "course_generation", etc.
    task_params = Column(JSONB, nullable=True)  # Original parameters
    
    # Progress tracking
    state = Column(SQLEnum(TaskState), default=TaskState.QUEUED, nullable=False, index=True)
    progress_pct = Column(Integer, default=0, nullable=False)
    message = Column(String(500), nullable=True)  # Current status message
    
    # Results
    result_course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id"), nullable=True)
    result_data = Column(JSONB, nullable=True)  # Additional result metadata
    error_details = Column(JSONB, nullable=True)  # Error information
    
    # For course generation specifically
    provisional_course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id"), nullable=True)
    
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
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
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
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False)
    
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
    badges = Column(JSONB, default=list, nullable=False)
    achievements = Column(JSONB, default=list, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="gamification_profile")
    
    def __repr__(self):
        return f"<GamificationProfile user={self.user_id} level={self.level}>"


class FeedItem(Base):
    """Feed items for community/discovery feed."""
    __tablename__ = "feed_items"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Content
    item_type = Column(String(50), nullable=False, index=True)  # "course_shared", "achievement", etc.
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=True)
    
    # References
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id"), nullable=True)
    
    # Metadata
    item_metadata = Column("metadata", JSONB, nullable=True)
    
    # Engagement
    likes_count = Column(Integer, default=0, nullable=False)
    comments_count = Column(Integer, default=0, nullable=False)
    
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
