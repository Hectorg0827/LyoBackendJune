"""
Database models for the Lyo backend application.
Includes all models required by the specification.
"""

import uuid
from datetime import datetime, date
from typing import Optional, List
from enum import Enum

from sqlalchemy import (
    Column, String, Text, Integer, Boolean, DateTime, Date, 
    UUID, ForeignKey, UniqueConstraint, Index, DECIMAL, JSON
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, Mapped
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.sql import func

Base = declarative_base()


class TaskState(str, Enum):
    """Task execution states."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


class CourseStatus(str, Enum):
    """Course status values."""
    DRAFT = "draft"
    GENERATING = "generating"
    COMPLETED = "completed"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class ContentType(str, Enum):
    """Content item types."""
    LESSON = "lesson"
    VIDEO = "video"
    QUIZ = "quiz"
    TEXT = "text"
    INTERACTIVE = "interactive"
    ASSESSMENT = "assessment"


class FeedItemType(str, Enum):
    """Feed item types."""
    COURSE_COMPLETION = "course_completion"
    ACHIEVEMENT = "achievement"
    COMMUNITY_POST = "community_post"
    MILESTONE = "milestone"
    RECOMMENDATION = "recommendation"


class Platform(str, Enum):
    """Device platforms."""
    IOS = "ios"
    ANDROID = "android"
    WEB = "web"


class User(Base):
    """User model with authentication and profile info."""
    __tablename__ = "users"
    
    id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=True, index=True)
    full_name = Column(String(255), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    avatar_url = Column(String(500), nullable=True)
    bio = Column(Text, nullable=True)
    timezone = Column(String(50), nullable=True)
    locale = Column(String(10), default="en", nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    last_login = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    tasks: Mapped[List["Task"]] = relationship("Task", back_populates="user", cascade="all, delete-orphan")
    courses: Mapped[List["Course"]] = relationship("Course", back_populates="user", cascade="all, delete-orphan")
    push_devices: Mapped[List["PushDevice"]] = relationship("PushDevice", back_populates="user", cascade="all, delete-orphan")
    feed_items: Mapped[List["FeedItem"]] = relationship("FeedItem", back_populates="user", cascade="all, delete-orphan")
    user_profile: Mapped[Optional["UserProfile"]] = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    user_badges: Mapped[List["UserBadge"]] = relationship("UserBadge", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(id={self.id}, email={self.email})>"


class Task(Base):
    """Async task tracking with idempotency support."""
    __tablename__ = "tasks"
    
    id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PostgresUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    idempotency_key = Column(String(255), unique=True, nullable=True, index=True)
    
    # Task execution
    state = Column(String(20), default=TaskState.PENDING, nullable=False, index=True)
    progress_pct = Column(Integer, default=0, nullable=False)
    message = Column(Text, nullable=True)
    
    # Course generation specific
    provisional_course_id = Column(PostgresUUID(as_uuid=True), nullable=True)
    result_course_id = Column(PostgresUUID(as_uuid=True), ForeignKey("courses.id", ondelete="SET NULL"), nullable=True)
    
    # Task metadata
    task_type = Column(String(50), default="course_generation", nullable=False)
    payload = Column(JSON, nullable=True)  # Original request payload
    error_details = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="tasks")
    result_course: Mapped[Optional["Course"]] = relationship("Course", foreign_keys=[result_course_id])
    
    # Indexes for performance
    __table_args__ = (
        Index("idx_tasks_user_state", "user_id", "state"),
        Index("idx_tasks_idempotency", "idempotency_key"),
        Index("idx_tasks_created", "created_at"),
    )
    
    def __repr__(self):
        return f"<Task(id={self.id}, state={self.state}, progress={self.progress_pct}%)>"


class Course(Base):
    """Generated courses with lessons and items."""
    __tablename__ = "courses"
    
    id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PostgresUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Course content
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(50), default=CourseStatus.DRAFT, nullable=False, index=True)
    
    # Course metadata
    topic = Column(String(200), nullable=True, index=True)
    interests = Column(JSON, nullable=True)  # Array of interests
    level = Column(String(50), nullable=True)  # beginner, intermediate, advanced
    locale = Column(String(10), default="en", nullable=False)
    estimated_duration = Column(Integer, nullable=True)  # minutes
    
    # AI generation context
    generation_prompt = Column(Text, nullable=True)
    generation_metadata = Column(JSON, nullable=True)
    
    # Progress tracking
    total_items = Column(Integer, default=0, nullable=False)
    completed_items = Column(Integer, default=0, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="courses")
    lessons: Mapped[List["Lesson"]] = relationship("Lesson", back_populates="course", cascade="all, delete-orphan", order_by="Lesson.order_index")
    items: Mapped[List["CourseItem"]] = relationship("CourseItem", back_populates="course", cascade="all, delete-orphan", order_by="CourseItem.order_index")
    study_groups = relationship("lyo_app.community.models.StudyGroup", back_populates="course", lazy="select")
    
    # Indexes for performance
    __table_args__ = (
        Index("idx_courses_user_status", "user_id", "status"),
        Index("idx_courses_topic", "topic"),
        Index("idx_courses_created", "created_at"),
    )
    
    def __repr__(self):
        return f"<Course(id={self.id}, title={self.title}, status={self.status})>"


class Lesson(Base):
    """Course lessons for organization."""
    __tablename__ = "lessons"
    
    id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id = Column(PostgresUUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Lesson content
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    order_index = Column(Integer, nullable=False)
    
    # Learning objectives
    objectives = Column(JSON, nullable=True)  # Array of learning objectives
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    course: Mapped["Course"] = relationship("Course", back_populates="lessons")
    items: Mapped[List["CourseItem"]] = relationship("CourseItem", back_populates="lesson", cascade="all, delete-orphan", order_by="CourseItem.order_index")
    
    # Unique constraint for ordering within course
    __table_args__ = (
        UniqueConstraint("course_id", "order_index", name="uq_lesson_order"),
        Index("idx_lessons_course_order", "course_id", "order_index"),
    )
    
    def __repr__(self):
        return f"<Lesson(id={self.id}, title={self.title}, order={self.order_index})>"


class CourseItem(Base):
    """Individual course content items (videos, text, quizzes, etc.)."""
    __tablename__ = "course_items"
    
    id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id = Column(PostgresUUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    lesson_id = Column(PostgresUUID(as_uuid=True), ForeignKey("lessons.id", ondelete="CASCADE"), nullable=True, index=True)
    
    # Content
    type = Column(String(50), nullable=False, index=True)  # ContentType enum
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=True)  # Main content body
    
    # External resources
    source = Column(String(100), nullable=True)  # youtube, wikipedia, generated, etc.
    source_url = Column(Text, nullable=True)
    thumbnail_url = Column(String(500), nullable=True)
    
    # Content metadata
    duration = Column(Integer, nullable=True)  # seconds for videos, estimated reading time for text
    difficulty_level = Column(String(20), nullable=True)
    tags = Column(JSON, nullable=True)  # Array of tags
    
    # Organization
    order_index = Column(Integer, nullable=False)
    
    # Interaction tracking
    view_count = Column(Integer, default=0, nullable=False)
    completion_rate = Column(DECIMAL(5, 4), nullable=True)  # 0.0000 to 1.0000
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    course: Mapped["Course"] = relationship("Course", back_populates="items")
    lesson: Mapped[Optional["Lesson"]] = relationship("Lesson", back_populates="items")
    
    # Unique constraint for ordering within course
    __table_args__ = (
        UniqueConstraint("course_id", "order_index", name="uq_courseitem_order"),
        Index("idx_courseitems_course_order", "course_id", "order_index"),
        Index("idx_courseitems_lesson_order", "lesson_id", "order_index"),
        Index("idx_courseitems_type", "type"),
    )
    
    def __repr__(self):
        return f"<CourseItem(id={self.id}, type={self.type}, title={self.title})>"


class UserProfile(Base):
    """User gamification profile."""
    __tablename__ = "user_profiles"
    
    user_id = Column(PostgresUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    
    # Gamification stats
    xp = Column(Integer, default=0, nullable=False)
    level = Column(Integer, default=1, nullable=False)
    current_streak = Column(Integer, default=0, nullable=False)
    longest_streak = Column(Integer, default=0, nullable=False)
    last_activity_date = Column(Date, nullable=True)
    
    # Learning progress
    courses_completed = Column(Integer, default=0, nullable=False)
    lessons_completed = Column(Integer, default=0, nullable=False)
    total_study_time = Column(Integer, default=0, nullable=False)  # minutes
    
    # Preferences
    daily_goal = Column(Integer, default=30, nullable=False)  # minutes
    notification_preferences = Column(JSON, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="user_profile")
    
    def __repr__(self):
        return f"<UserProfile(user_id={self.user_id}, xp={self.xp}, level={self.level})>"


class Badge(Base):
    """Achievement badges."""
    __tablename__ = "badges"
    
    id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    icon_url = Column(String(500), nullable=True)
    
    # Badge criteria and rewards
    criteria = Column(JSON, nullable=True)  # Conditions for earning
    xp_reward = Column(Integer, default=0, nullable=False)
    rarity = Column(String(20), default="common", nullable=False)  # common, rare, epic, legendary
    
    # Metadata
    is_active = Column(Boolean, default=True, nullable=False)
    category = Column(String(50), nullable=True, index=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    user_badges: Mapped[List["UserBadge"]] = relationship("UserBadge", back_populates="badge", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Badge(id={self.id}, name={self.name}, rarity={self.rarity})>"


class UserBadge(Base):
    """Many-to-many relationship for user badges."""
    __tablename__ = "user_badges"
    
    user_id = Column(PostgresUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    badge_id = Column(PostgresUUID(as_uuid=True), ForeignKey("badges.id", ondelete="CASCADE"), primary_key=True)
    
    # Achievement tracking
    earned_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    progress_data = Column(JSON, nullable=True)  # Track progress toward badge
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="user_badges")
    badge: Mapped["Badge"] = relationship("Badge", back_populates="user_badges")
    
    def __repr__(self):
        return f"<UserBadge(user_id={self.user_id}, badge_id={self.badge_id})>"


class PushDevice(Base):
    """Push notification device registration."""
    __tablename__ = "push_devices"
    
    id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PostgresUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Device info
    device_token = Column(String(255), unique=True, nullable=False, index=True)
    platform = Column(String(20), nullable=False, index=True)  # Platform enum
    device_name = Column(String(100), nullable=True)
    app_version = Column(String(20), nullable=True)
    
    # Status
    active = Column(Boolean, default=True, nullable=False)
    
    # Timestamps
    registered_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_used = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="push_devices")
    
    # Indexes for performance
    __table_args__ = (
        Index("idx_push_devices_user_active", "user_id", "active"),
        Index("idx_push_devices_platform", "platform"),
    )
    
    def __repr__(self):
        return f"<PushDevice(id={self.id}, platform={self.platform}, active={self.active})>"


class FeedItem(Base):
    """Social feed items for community features."""
    __tablename__ = "feed_items"
    
    id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PostgresUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)  # Can be system-generated
    
    # Content
    type = Column(String(50), nullable=False, index=True)  # FeedItemType enum
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=True)
    
    # Rich content
    item_metadata = Column(JSON, nullable=True)  # Type-specific data (renamed from metadata)
    image_url = Column(String(500), nullable=True)
    link_url = Column(String(500), nullable=True)
    
    # Engagement
    like_count = Column(Integer, default=0, nullable=False)
    comment_count = Column(Integer, default=0, nullable=False)
    share_count = Column(Integer, default=0, nullable=False)
    
    # Visibility and ranking
    is_public = Column(Boolean, default=True, nullable=False)
    is_featured = Column(Boolean, default=False, nullable=False)
    priority_score = Column(DECIMAL(10, 6), default=0, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    user: Mapped[Optional["User"]] = relationship("User", back_populates="feed_items")
    
    # Indexes for performance (critical for feed queries)
    __table_args__ = (
        Index("idx_feed_items_type_created", "type", "created_at"),
        Index("idx_feed_items_public_priority", "is_public", "priority_score"),
        Index("idx_feed_items_user_created", "user_id", "created_at"),
        Index("idx_feed_items_featured_created", "is_featured", "created_at"),
    )
    
    def __repr__(self):
        return f"<FeedItem(id={self.id}, type={self.type}, title={self.title})>"


# Add some helpful utility functions for common operations
class ModelMixin:
    """Common methods for all models."""
    
    def to_dict(self):
        """Convert model to dictionary."""
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
    
    def update_from_dict(self, data: dict):
        """Update model from dictionary."""
        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)


# Apply mixin to all models
for cls in [User, Task, Course, Lesson, CourseItem, UserProfile, Badge, UserBadge, PushDevice, FeedItem]:
    cls.__bases__ = (ModelMixin,) + cls.__bases__
