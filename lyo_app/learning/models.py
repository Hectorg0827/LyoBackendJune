"""
Learning module models for courses, lessons, and user progress.
Defines the database schema for educational content management.
"""

from datetime import datetime
from typing import Optional, List
from enum import Enum

from sqlalchemy import Boolean, DateTime, String, Text, Integer, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lyo_app.core.database import Base
from lyo_app.tenants.mixins import TenantMixin


class DifficultyLevel(str, Enum):
    """Difficulty levels for courses and lessons."""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class ContentType(str, Enum):
    """Types of lesson content."""
    VIDEO = "video"
    TEXT = "text"
    INTERACTIVE = "interactive"
    QUIZ = "quiz"
    ASSIGNMENT = "assignment"


class Course(TenantMixin, Base):
    """Course model for educational content."""
    
    __tablename__ = "courses"
    
    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    # Course information
    title: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    short_description: Mapped[Optional[str]] = mapped_column(String(500))
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(500))
    
    # Course metadata
    difficulty_level: Mapped[DifficultyLevel] = mapped_column(
        SQLEnum(DifficultyLevel), nullable=False
    )
    estimated_duration_hours: Mapped[Optional[int]] = mapped_column(Integer)
    category: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    tags: Mapped[Optional[str]] = mapped_column(Text)  # JSON array as string
    
    # Course status
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Instructor (foreign key to User)
    instructor_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    
    # Relationships
    lessons: Mapped[List["Lesson"]] = relationship(
        "Lesson", back_populates="course", cascade="all, delete-orphan"
    )
    enrollments: Mapped[List["CourseEnrollment"]] = relationship(
        "CourseEnrollment", back_populates="course", cascade="all, delete-orphan"
    )
    study_groups = relationship("lyo_app.community.models.StudyGroup", back_populates="course", lazy="select")
    instructor: Mapped["User"] = relationship("lyo_app.auth.models.User")
    
    def __repr__(self) -> str:
        return f"<Course(id={self.id}, title='{self.title}', instructor_id={self.instructor_id})>"


class Lesson(TenantMixin, Base):
    """Lesson model for individual learning units."""
    
    __tablename__ = "lessons"
    
    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    # Lesson information
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    content: Mapped[Optional[str]] = mapped_column(Text)  # Main lesson content
    content_type: Mapped[ContentType] = mapped_column(
        SQLEnum(ContentType), nullable=False
    )
    
    # Lesson structure
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id"), nullable=False, index=True
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)  # Order within course
    
    # Lesson metadata
    duration_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    video_url: Mapped[Optional[str]] = mapped_column(String(500))
    resources_url: Mapped[Optional[str]] = mapped_column(String(500))
    
    # Lesson status
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_preview: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    
    # Relationships
    course: Mapped["Course"] = relationship("Course", back_populates="lessons")
    completions: Mapped[List["LessonCompletion"]] = relationship(
        "LessonCompletion", back_populates="lesson", cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<Lesson(id={self.id}, title='{self.title}', course_id={self.course_id})>"


class CourseEnrollment(TenantMixin, Base):
    """Model for tracking user course enrollments."""
    
    __tablename__ = "course_enrollments"
    
    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    # Foreign keys
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id"), nullable=False, index=True
    )
    
    # Enrollment data
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    progress_percentage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Relationships
    course: Mapped["Course"] = relationship("Course", back_populates="enrollments")
    user: Mapped["User"] = relationship("lyo_app.auth.models.User", back_populates="course_enrollments")
    
    def __repr__(self) -> str:
        return f"<CourseEnrollment(user_id={self.user_id}, course_id={self.course_id})>"


class LessonCompletion(TenantMixin, Base):
    """Model for tracking individual lesson completions."""
    
    __tablename__ = "lesson_completions"
    
    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    # Foreign keys
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    lesson_id: Mapped[int] = mapped_column(
        ForeignKey("lessons.id"), nullable=False, index=True
    )
    
    # Completion data
    completed_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    time_spent_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Relationships
    lesson: Mapped["Lesson"] = relationship("Lesson", back_populates="completions")
    user: Mapped["User"] = relationship("lyo_app.auth.models.User", back_populates="lesson_completions")
    
    def __repr__(self) -> str:
        return f"<LessonCompletion(user_id={self.user_id}, lesson_id={self.lesson_id})>"
