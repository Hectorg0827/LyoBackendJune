"""
Pydantic schemas for learning module endpoints.
Defines request/response models for courses, lessons, and enrollments.
"""

from datetime import datetime
from typing import Optional, List
from enum import Enum

from pydantic import BaseModel, Field, ConfigDict

from lyo_app.learning.models import DifficultyLevel, ContentType


class CourseBase(BaseModel):
    """Base course schema with common fields."""
    
    title: str = Field(..., min_length=1, max_length=200, description="Course title")
    description: Optional[str] = Field(None, description="Detailed course description")
    short_description: Optional[str] = Field(
        None, max_length=500, description="Brief course description"
    )
    thumbnail_url: Optional[str] = Field(None, description="Course thumbnail image URL")
    difficulty_level: DifficultyLevel = Field(..., description="Course difficulty level")
    estimated_duration_hours: Optional[int] = Field(
        None, ge=1, le=1000, description="Estimated completion time in hours"
    )
    category: Optional[str] = Field(None, max_length=100, description="Course category")
    tags: Optional[List[str]] = Field(None, description="Course tags for categorization")


class CourseCreate(CourseBase):
    """Schema for creating a new course."""
    
    instructor_id: int = Field(..., description="ID of the instructor creating the course")


class CourseUpdate(BaseModel):
    """Schema for updating course information."""
    
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    short_description: Optional[str] = Field(None, max_length=500)
    thumbnail_url: Optional[str] = None
    difficulty_level: Optional[DifficultyLevel] = None
    estimated_duration_hours: Optional[int] = Field(None, ge=1, le=1000)
    category: Optional[str] = Field(None, max_length=100)
    tags: Optional[List[str]] = None
    is_published: Optional[bool] = None
    is_featured: Optional[bool] = None

class ProofRead(BaseModel):
    """Schema for reading a Proof of Learning."""
    id: int
    course_id: Optional[str]
    title: str
    issued_at: datetime
    proof_hash: str
    skills_validated: List[str]
    verification_url: Optional[str]
    
    model_config = ConfigDict(from_attributes=True)


class CourseRead(CourseBase):
    """Schema for reading course data."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: int = Field(..., description="Course ID")
    instructor_id: int = Field(..., description="Instructor user ID")
    is_published: bool = Field(..., description="Whether the course is published")
    is_featured: bool = Field(..., description="Whether the course is featured")
    created_at: datetime = Field(..., description="Course creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    lesson_count: Optional[int] = Field(None, description="Number of lessons in course")
    enrollment_count: Optional[int] = Field(None, description="Number of enrolled students")


class LessonBase(BaseModel):
    """Base lesson schema with common fields."""
    
    title: str = Field(..., min_length=1, max_length=200, description="Lesson title")
    description: Optional[str] = Field(None, description="Lesson description")
    content: Optional[str] = Field(None, description="Main lesson content")
    content_type: ContentType = Field(..., description="Type of lesson content")
    duration_minutes: Optional[int] = Field(
        None, ge=1, le=600, description="Lesson duration in minutes"
    )
    video_url: Optional[str] = Field(None, description="Video content URL")
    resources_url: Optional[str] = Field(None, description="Additional resources URL")
    order_index: int = Field(..., ge=1, description="Order within the course")


class LessonCreate(LessonBase):
    """Schema for creating a new lesson."""
    
    course_id: int = Field(..., description="ID of the course this lesson belongs to")


class LessonUpdate(BaseModel):
    """Schema for updating lesson information."""
    
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    content: Optional[str] = None
    content_type: Optional[ContentType] = None
    duration_minutes: Optional[int] = Field(None, ge=1, le=600)
    video_url: Optional[str] = None
    resources_url: Optional[str] = None
    order_index: Optional[int] = Field(None, ge=1)
    is_published: Optional[bool] = None
    is_preview: Optional[bool] = None


class LessonRead(LessonBase):
    """Schema for reading lesson data."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: int = Field(..., description="Lesson ID")
    course_id: int = Field(..., description="Course ID")
    is_published: bool = Field(..., description="Whether the lesson is published")
    is_preview: bool = Field(..., description="Whether the lesson is available as preview")
    created_at: datetime = Field(..., description="Lesson creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class CourseEnrollmentCreate(BaseModel):
    """Schema for enrolling in a course."""
    
    course_id: int = Field(..., description="ID of the course to enroll in")


class CourseEnrollmentRead(BaseModel):
    """Schema for reading enrollment data."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: int = Field(..., description="Enrollment ID")
    user_id: int = Field(..., description="Enrolled user ID")
    course_id: int = Field(..., description="Course ID")
    enrolled_at: datetime = Field(..., description="Enrollment timestamp")
    completed_at: Optional[datetime] = Field(None, description="Completion timestamp")
    progress_percentage: int = Field(..., description="Course completion percentage")
    is_active: bool = Field(..., description="Whether enrollment is active")


class LessonCompletionCreate(BaseModel):
    """Schema for marking a lesson as completed."""
    
    lesson_id: int = Field(..., description="ID of the completed lesson")
    time_spent_minutes: Optional[int] = Field(
        None, ge=1, description="Time spent on the lesson in minutes"
    )


class LessonCompletionRead(BaseModel):
    """Schema for reading lesson completion data."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: int = Field(..., description="Completion ID")
    user_id: int = Field(..., description="User ID")
    lesson_id: int = Field(..., description="Lesson ID")
    completed_at: datetime = Field(..., description="Completion timestamp")
    time_spent_minutes: Optional[int] = Field(
        None, description="Time spent on lesson in minutes"
    )


class CourseListResponse(BaseModel):
    """Schema for paginated course list responses."""
    
    courses: List[CourseRead] = Field(..., description="List of courses")
    total: int = Field(..., description="Total number of courses")
    page: int = Field(..., description="Current page number")
    per_page: int = Field(..., description="Items per page")
    has_next: bool = Field(..., description="Whether there are more pages")


class UserProgressResponse(BaseModel):
    """Schema for user progress in a course."""
    
    course_id: int = Field(..., description="Course ID")
    enrollment: CourseEnrollmentRead = Field(..., description="Enrollment details")
    completed_lessons: List[LessonCompletionRead] = Field(
        ..., description="List of completed lessons"
    )
    next_lesson: Optional[LessonRead] = Field(
        None, description="Next lesson to complete"
    )
