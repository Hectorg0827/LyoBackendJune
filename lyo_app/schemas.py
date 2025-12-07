"""Pydantic models for API contracts and request/response schemas."""

from datetime import datetime
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field, EmailStr, validator, HttpUrl
from pydantic import BaseModel, Field, EmailStr, HttpUrl, field_validator
from enum import Enum
import uuid


class TaskState(str, Enum):
    """Task execution states for API responses."""
    QUEUED = "QUEUED"
    RUNNING = "RUNNING" 
    DONE = "DONE"
    ERROR = "ERROR"


class ContentType(str, Enum):
    """Content types for normalized content schema."""
    VIDEO = "video"
    ARTICLE = "article"
    EBOOK = "ebook"
    PDF = "pdf"
    PODCAST = "podcast"
    COURSE = "course"


class CourseStatus(str, Enum):
    """Course status for API responses."""
    DRAFT = "DRAFT"
    GENERATING = "GENERATING"
    PARTIAL = "PARTIAL"
    READY = "READY"
    ERROR = "ERROR"


class PushPlatform(str, Enum):
    """Push notification platforms."""
    IOS = "ios"
    ANDROID = "android"


# Authentication Models

class LoginRequest(BaseModel):
    """User login request."""
    email: EmailStr
    password: str = Field(..., min_length=8)


class LoginResponse(BaseModel):
    """User login response with JWT tokens."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    user: "UserProfile"


class RefreshRequest(BaseModel):
    """Token refresh request."""
    refresh_token: str


class RefreshResponse(BaseModel):
    """Token refresh response."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class RegisterRequest(BaseModel):
    """User registration request."""
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=1, max_length=255)
    username: Optional[str] = Field(None, min_length=3, max_length=100)


class UserProfile(BaseModel):
    """User profile information."""
    id: str
    email: EmailStr
    username: Optional[str]
    full_name: str
    avatar_url: Optional[HttpUrl]
    bio: Optional[str]
    is_active: bool
    is_verified: bool
    created_at: datetime
    
    model_config = {
        "from_attributes": True
    }


# Course Generation Models

class CourseGenerationRequest(BaseModel):
    """Request to generate a new course."""
    topic: str = Field(..., min_length=3, max_length=200)
    interests: List[str] = Field(default_factory=list, max_items=10)
    difficulty_level: Optional[str] = Field("beginner", regex="^(beginner|intermediate|advanced)$")
    target_duration_hours: Optional[float] = Field(None, gt=0, le=100)
    locale: Optional[str] = Field("en", min_length=2, max_length=10)


class CourseGenerationResponse(BaseModel):
    """Response for course generation kickoff."""
    task_id: str
    provisional_course_id: str
    estimated_completion_minutes: Optional[int] = 15


# Task Progress Models

class TaskProgress(BaseModel):
    """Task progress information."""
    task_id: str
    state: TaskState
    progress_pct: int = Field(..., ge=0, le=100)
    message: Optional[str]
    result_id: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_details: Optional[Dict[str, Any]] = None


class WebSocketTaskEvent(BaseModel):
    """WebSocket event for task progress."""
    task_id: str
    state: TaskState
    progress_pct: int = Field(..., ge=0, le=100)
    message: Optional[str]
    result_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# Content Models

class LessonSummary(BaseModel):
    """Lesson summary for course responses."""
    id: str
    title: str
    order: int
    summary: Optional[str]
    estimated_duration_minutes: Optional[int]
    
    model_config = {
        "from_attributes": True
    }


class ContentItemResponse(BaseModel):
    """Normalized content item for API responses."""
    id: str
    type: ContentType
    title: str
    source: Optional[str]
    source_url: Optional[HttpUrl]
    thumbnail_url: Optional[HttpUrl]
    
    # Type-specific fields
    duration_sec: Optional[int] = Field(None, ge=0)
    pages: Optional[int] = Field(None, ge=0)
    word_count: Optional[int] = Field(None, ge=0)
    
    summary: Optional[str]
    attribution: Optional[str]
    tags: List[str] = Field(default_factory=list)
    difficulty_level: Optional[str]
    language: str = "en"
    
    # Quality indicators
    quality_score: Optional[float] = Field(None, ge=0, le=1)
    is_free: bool = True
    requires_subscription: bool = False
    
    model_config = {
        "from_attributes": True
    }


class CourseResponse(BaseModel):
    """Complete course response with normalized structure."""
    id: str
    title: str
    topic: str
    summary: Optional[str]
    description: Optional[str]
    status: CourseStatus
    
    # Generation metadata
    interests: List[str] = Field(default_factory=list)
    difficulty_level: Optional[str]
    estimated_duration_hours: Optional[float]
    
    # SEO & Discovery
    tags: List[str] = Field(default_factory=list)
    thumbnail_url: Optional[HttpUrl]
    
    # Timestamps
    created_at: datetime
    updated_at: Optional[datetime]
    published_at: Optional[datetime]
    
    # Owner
    owner_user_id: str
    
    # Related content
    lessons: List[LessonSummary] = Field(default_factory=list)
    items: List[ContentItemResponse] = Field(default_factory=list)
    
    model_config = {
        "from_attributes": True
    }


# Feed Models

class FeedItemResponse(BaseModel):
    """Feed item for community/discovery."""
    id: str
    user_id: str
    item_type: str
    title: str
    content: Optional[str]
    course_id: Optional[str]
    likes_count: int = 0
    comments_count: int = 0
    created_at: datetime
    
    # User info (joined)
    user_full_name: Optional[str]
    user_avatar_url: Optional[HttpUrl]
    
    # Course info (if applicable)
    course_title: Optional[str]
    course_thumbnail_url: Optional[HttpUrl]
    
    model_config = {
        "from_attributes": True
    }


class FeedResponse(BaseModel):
    """Paginated feed response."""
    items: List[FeedItemResponse]
    next_cursor: Optional[str]
    has_more: bool


# Gamification Models

class BadgeInfo(BaseModel):
    """Badge information."""
    id: str
    name: str
    description: str
    icon_url: HttpUrl
    earned_at: Optional[datetime]


class GamificationProfileResponse(BaseModel):
    """Gamification profile response."""
    user_id: str
    total_xp: int
    level: int
    xp_to_next_level: int
    current_streak_days: int
    longest_streak_days: int
    courses_completed: int
    lessons_completed: int
    total_study_minutes: int
    badges: List[BadgeInfo] = Field(default_factory=list)
    
    model_config = {
        "from_attributes": True
    }


# Push Notification Models

class PushDeviceRequest(BaseModel):
    """Push device registration request."""
    device_token: str = Field(..., min_length=10)
    platform: PushPlatform
    locale: Optional[str] = Field("en", min_length=2, max_length=10)
    app_version: Optional[str] = Field(None, max_length=20)
    device_model: Optional[str] = Field(None, max_length=100)
    os_version: Optional[str] = Field(None, max_length=20)


class PushDeviceResponse(BaseModel):
    """Push device registration response."""
    id: str
    device_token: str
    platform: PushPlatform
    is_active: bool
    created_at: datetime
    
    model_config = {
        "from_attributes": True
    }


# Pagination Models

class PaginationParams(BaseModel):
    """Common pagination parameters."""
    cursor: Optional[str] = None
    limit: int = Field(20, ge=1, le=50)


class PaginatedResponse(BaseModel):
    """Generic paginated response."""
    items: List[Any]
    next_cursor: Optional[str]
    has_more: bool
    total_count: Optional[int] = None


# Error Response Models (RFC 9457)

class ProblemDetails(BaseModel):
    """RFC 9457 Problem Details response."""
    type: str
    title: str
    status: int
    detail: str
    instance: str
    # Additional extension fields are dynamically added


# Health Check Models

class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "healthy"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    version: str
    uptime_seconds: float


class ModelHealthResponse(BaseModel):
    """Model health check response."""
    status: str
    model_name: str
    model_version: Optional[str]
    checksum_verified: bool
    last_loaded_at: Optional[datetime]


# WebSocket Models

class WSConnectionRequest(BaseModel):
    """WebSocket connection request parameters."""
    task_id: str
    
    @field_validator('task_id')
    def validate_task_id(cls, v):
        try:
            uuid.UUID(v)
        except ValueError:
            raise ValueError('task_id must be a valid UUID')
        return v


# Search & Discovery Models

class SearchRequest(BaseModel):
    """Content search request."""
    query: str = Field(..., min_length=1, max_length=200)
    content_types: List[ContentType] = Field(default_factory=list)
    difficulty_level: Optional[str] = Field(None, regex="^(beginner|intermediate|advanced)$")
    language: Optional[str] = Field("en", min_length=2, max_length=10)
    limit: int = Field(20, ge=1, le=50)
    offset: int = Field(0, ge=0)


class SearchResponse(BaseModel):
    """Content search response."""
    results: List[ContentItemResponse]
    total_count: int
    query: str
    took_ms: float


# Configuration for forward references
CourseResponse.model_rebuild()
LoginResponse.model_rebuild()
