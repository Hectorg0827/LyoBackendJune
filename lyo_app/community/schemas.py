"""
Pydantic schemas for community module endpoints.
Defines request/response models for study groups and community events.
"""

from datetime import datetime
from typing import Optional, List, Literal, Union
from uuid import UUID
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict

from lyo_app.community.models import (
    StudyGroupStatus, StudyGroupPrivacy, MembershipRole,
    EventType, EventStatus, AttendanceStatus, BookingStatus
)


class UserPreview(BaseModel):
    """Lite user profile for community views."""
    
    id: int
    name: str
    avatar: Optional[str] = None


# Study Group Schemas
class StudyGroupBase(BaseModel):
    """Base study group schema with common fields."""
    
    name: str = Field(..., min_length=1, max_length=200, description="Study group name")
    description: Optional[str] = Field(None, max_length=2000, description="Group description")
    privacy: StudyGroupPrivacy = Field(default=StudyGroupPrivacy.PUBLIC, description="Group privacy level")
    max_members: Optional[int] = Field(None, ge=2, le=1000, description="Maximum number of members")
    requires_approval: bool = Field(default=False, description="Whether membership requires approval")
    course_id: Optional[int] = Field(None, description="Associated course ID")


class StudyGroupCreate(StudyGroupBase):
    """Schema for creating a new study group."""
    pass


class StudyGroupUpdate(BaseModel):
    """Schema for updating study group information."""
    
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    privacy: Optional[StudyGroupPrivacy] = None
    max_members: Optional[int] = Field(None, ge=2, le=1000)
    requires_approval: Optional[bool] = None
    status: Optional[StudyGroupStatus] = None


class StudyGroupRead(StudyGroupBase):
    """Schema for reading study group data."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: int = Field(..., description="Study group ID")
    status: StudyGroupStatus = Field(..., description="Group status")
    creator_id: int = Field(..., description="Creator user ID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    
    # Computed fields
    member_count: Optional[int] = Field(None, description="Number of members")
    is_member: Optional[bool] = Field(None, description="Whether current user is a member")
    user_role: Optional[MembershipRole] = Field(None, description="Current user's role in group")
    host: Optional[UserPreview] = None


# Group Membership Schemas
class GroupMembershipCreate(BaseModel):
    """Schema for joining a study group."""
    
    study_group_id: int = Field(..., description="Study group ID to join")


class GroupMembershipUpdate(BaseModel):
    """Schema for updating membership (admin only)."""
    
    role: Optional[MembershipRole] = Field(None, description="New role for member")
    is_approved: Optional[bool] = Field(None, description="Approval status")


class GroupMembershipRead(BaseModel):
    """Schema for reading membership data."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: int = Field(..., description="Membership ID")
    user_id: int = Field(..., description="User ID")
    study_group_id: int = Field(..., description="Study group ID")
    role: MembershipRole = Field(..., description="Member role")
    is_approved: bool = Field(..., description="Whether membership is approved")
    joined_at: datetime = Field(..., description="Join timestamp")
    approved_at: Optional[datetime] = Field(None, description="Approval timestamp")
    approved_by_id: Optional[int] = Field(None, description="Approver user ID")


# Community Event Schemas
class CommunityEventBase(BaseModel):
    """Base community event schema with common fields."""
    
    title: str = Field(..., min_length=1, max_length=200, description="Event title")
    description: Optional[str] = Field(None, max_length=2000, description="Event description")
    event_type: EventType = Field(default=EventType.STUDY_SESSION, description="Type of event")
    location: Optional[str] = Field(None, max_length=300, description="Event location")
    meeting_url: Optional[str] = Field(None, max_length=500, description="Virtual meeting URL")
    max_attendees: Optional[int] = Field(None, ge=1, le=10000, description="Maximum attendees")
    start_time: datetime = Field(..., description="Event start time")
    end_time: datetime = Field(..., description="Event end time")
    timezone: str = Field(default="UTC", max_length=50, description="Event timezone")
    study_group_id: Optional[int] = Field(None, description="Associated study group ID")
    course_id: Optional[int] = Field(None, description="Associated course ID")
    lesson_id: Optional[int] = Field(None, description="Associated lesson ID")
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    room_id: Optional[str] = None
    image_url: Optional[str] = None


class CommunityEventCreate(CommunityEventBase):
    """Schema for creating a new community event."""
    pass


class CommunityEventUpdate(BaseModel):
    """Schema for updating community event information."""
    
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    event_type: Optional[EventType] = None
    location: Optional[str] = Field(None, max_length=300)
    meeting_url: Optional[str] = Field(None, max_length=500)
    max_attendees: Optional[int] = Field(None, ge=1, le=10000)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    timezone: Optional[str] = Field(None, max_length=50)
    status: Optional[EventStatus] = None


class CommunityEventRead(CommunityEventBase):
    """Schema for reading community event data."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: int = Field(..., description="Event ID")
    status: EventStatus = Field(..., description="Event status")
    organizer_id: int = Field(..., description="Organizer user ID")
    latitude: Optional[float] = Field(None, description="Event latitude")
    longitude: Optional[float] = Field(None, description="Event longitude")
    room_id: Optional[str] = Field(None, description="Specific room or area ID")
    image_url: Optional[str] = Field(None, description="Event image URL")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    
    # Computed fields
    attendee_count: Optional[int] = Field(None, description="Number of attendees")
    user_attendance_status: Optional[AttendanceStatus] = Field(None, description="Current user's attendance status")
    is_full: Optional[bool] = Field(None, description="Whether event is at capacity")
    organizer_profile: Optional[UserPreview] = None


# Event Attendance Schemas
class EventAttendanceCreate(BaseModel):
    """Schema for registering for an event."""
    
    event_id: int = Field(..., description="Event ID to register for")
    status: AttendanceStatus = Field(default=AttendanceStatus.GOING, description="Attendance status")


class EventAttendanceUpdate(BaseModel):
    """Schema for updating event attendance."""
    
    status: Optional[AttendanceStatus] = Field(None, description="New attendance status")
    rating: Optional[int] = Field(None, ge=1, le=5, description="Event rating (1-5)")
    feedback: Optional[str] = Field(None, max_length=1000, description="Event feedback")


class EventAttendanceRead(BaseModel):
    """Schema for reading event attendance data."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: int = Field(..., description="Attendance ID")
    status: AttendanceStatus = Field(..., description="Attendance status")
    user_id: int = Field(..., description="User ID")
    event_id: int = Field(..., description="Event ID")
    registered_at: datetime = Field(..., description="Registration timestamp")


# --- Phase 3: Campus Map Schemas ---

class CommunityQuestionCreate(BaseModel):
    text: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_name: Optional[str] = None

class CommunityQuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    text: str
    latitude: Optional[float]
    longitude: Optional[float]
    location_name: Optional[str]
    is_resolved: bool
    created_at: datetime
    user_id: int

class CommunityAnswerCreate(BaseModel):
    text: str

class CommunityAnswerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    text: str
    created_at: datetime
    user_id: int
    question_id: UUID

# Beacon Schemas

class BeaconType(str, Enum):
    EVENT = "event"
    USER_ACTIVITY = "user_activity"
    QUESTION = "question"

class EventBeacon(BaseModel):
    type: Literal["event"] = "event"
    id: int
    title: str
    latitude: float
    longitude: float
    location_name: Optional[str]
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    relevance_score: Optional[float] = None

class UserActivityBeacon(BaseModel):
    type: Literal["user_activity"] = "user_activity"
    user_id: int
    display_name: str
    latitude: Optional[float]
    longitude: Optional[float]
    recent_topics: List[str] = []
    level: Optional[int] = None
    xp: Optional[int] = None

class QuestionBeacon(BaseModel):
    type: Literal["question"] = "question"
    id: UUID
    text: str
    latitude: float
    longitude: float
    location_name: Optional[str]
    is_resolved: bool

class MarketplaceBeacon(BaseModel):
    type: Literal["marketplace"] = "marketplace"
    id: int
    title: str
    latitude: float
    longitude: float
    price: float
    currency: str

BeaconBase = Union[EventBeacon, UserActivityBeacon, QuestionBeacon, MarketplaceBeacon]


# Marketplace Schemas

class MarketplaceItemBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    price: float = Field(default=0.0, ge=0.0)
    currency: str = Field(default="USD", max_length=10)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_name: Optional[str] = None
    image_urls: Optional[List[str]] = None

class MarketplaceItemCreate(MarketplaceItemBase):
    pass

class MarketplaceItemUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    is_active: Optional[bool] = None
    is_sold: Optional[bool] = None

class MarketplaceItemRead(MarketplaceItemBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    seller_id: int
    seller_avatar: Optional[str] = None
    is_active: bool
    is_sold: bool
    created_at: datetime
    updated_at: datetime


# Response Schemas
class StudyGroupListResponse(BaseModel):
    """Schema for paginated study group responses."""
    
    groups: List[StudyGroupRead] = Field(..., description="List of study groups")
    total: int = Field(..., description="Total number of groups")
    page: int = Field(..., description="Current page number")
    per_page: int = Field(..., description="Items per page")
    has_next: bool = Field(..., description="Whether there are more pages")


class CommunityEventListResponse(BaseModel):
    """Schema for paginated community event responses."""
    
    events: List[CommunityEventRead] = Field(..., description="List of events")
    total: int = Field(..., description="Total number of events")
    page: int = Field(..., description="Current page number")
    per_page: int = Field(..., description="Items per page")
    has_next: bool = Field(..., description="Whether there are more pages")


class GroupMemberListResponse(BaseModel):
    """Schema for study group member list responses."""
    
    members: List[GroupMembershipRead] = Field(..., description="List of group members")
    total: int = Field(..., description="Total number of members")
    pending_requests: int = Field(..., description="Number of pending membership requests")


class EventAttendeeListResponse(BaseModel):
    """Schema for event attendee list responses."""
    
    attendees: List[EventAttendanceRead] = Field(..., description="List of event attendees")
    total: int = Field(..., description="Total number of attendees")
    by_status: dict = Field(..., description="Attendee count by status")


class CommunityStatsResponse(BaseModel):
    """Schema for community statistics."""
    
    total_groups: int = Field(..., description="Total number of study groups")
    active_groups: int = Field(..., description="Number of active study groups")
    total_events: int = Field(..., description="Total number of events")
    upcoming_events: int = Field(..., description="Number of upcoming events")
    total_memberships: int = Field(..., description="Total group memberships")
    user_groups_count: int = Field(..., description="Number of groups user belongs to")
    user_events_count: int = Field(..., description="Number of events user is attending")


class StudyGroupWithDetailsRead(StudyGroupRead):
    """Extended study group schema with members and events."""
    
    members: List[GroupMembershipRead] = Field(..., description="Group members")
    recent_events: List[CommunityEventRead] = Field(..., description="Recent events")
    upcoming_events: List[CommunityEventRead] = Field(..., description="Upcoming events")


class CommunityEventWithDetailsRead(CommunityEventRead):
    """Extended event schema with attendees and group info."""
    
    attendees: List[EventAttendanceRead] = Field(..., description="Event attendees")
    study_group: Optional[StudyGroupRead] = Field(None, description="Associated study group")


# =============================================================================
# BOOKING & REVIEW SCHEMAS
# =============================================================================


class PrivateLessonCreate(BaseModel):
    """Schema for creating a private lesson."""
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    subject: str = Field(..., min_length=1, max_length=100)
    price_per_hour: float = Field(default=0.0, ge=0.0)
    currency: str = Field(default="USD", max_length=10)
    duration_minutes: int = Field(default=60, ge=15, le=480)
    location: Optional[str] = Field(None, max_length=500)
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class PrivateLessonRead(BaseModel):
    """Schema for reading a private lesson — matches iOS APIPrivateLesson."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: Optional[str] = None
    subject: str
    price_per_hour: float
    currency: str
    duration_minutes: int
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_active: bool
    instructor_id: int
    instructor_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class BookingSlotRead(BaseModel):
    """Matches iOS APIBookingSlot (snake_case for .convertFromSnakeCase decoder)."""
    id: str
    start_time: datetime
    end_time: datetime
    is_available: bool


class BookingCreate(BaseModel):
    """Matches iOS APIBookingRequest."""
    lesson_id: int
    slot_id: str  # Encoded as "{lessonId}-{YYYYMMDD}-{HHMM}" — parsed server-side
    notes: Optional[str] = None


class BookingRead(BaseModel):
    """Matches iOS APIBookingResponse."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    lesson_id: int
    lesson_title: Optional[str] = None
    student_id: int
    status: BookingStatus
    slot_start: datetime
    slot_end: datetime
    notes: Optional[str] = None
    created_at: datetime


class ReviewCreate(BaseModel):
    """Matches iOS APIReviewRequest."""
    target_type: str = Field(..., pattern="^(lesson|institution)$")
    target_id: str
    rating: int = Field(..., ge=1, le=5)
    text: Optional[str] = Field(None, max_length=2000)


class ReviewRead(BaseModel):
    """Matches iOS APIReview."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    author_id: int
    author_name: Optional[str] = None
    author_avatar: Optional[str] = None
    target_type: str
    target_id: str
    rating: int
    text: Optional[str] = None
    created_at: datetime


class ReviewStatsRead(BaseModel):
    """Matches iOS APIReviewStats."""
    average_rating: float
    review_count: int
    rating_distribution: dict  # {"1": count, "2": count, ...}


# =============================================================================
# SOCIAL FEED SCHEMAS (Posts, Comments, Likes, Reports, Blocks)
# =============================================================================

from lyo_app.community.models import PostType, PostVisibility, ReportTargetType, ReportReason


class PostCreate(BaseModel):
    """Schema for creating a new post."""
    content: str = Field(..., min_length=1, max_length=5000, description="Post content")
    media_urls: Optional[List[str]] = Field(None, max_items=10, description="Media URLs")
    tags: Optional[List[str]] = Field(None, max_items=20, description="Tags")
    post_type: PostType = Field(default=PostType.TEXT, description="Post type")
    linked_course_id: Optional[int] = Field(None, description="Linked course ID")
    linked_group_id: Optional[int] = Field(None, description="Linked study group ID")
    visibility: PostVisibility = Field(default=PostVisibility.PUBLIC, description="Visibility")


class PostUpdate(BaseModel):
    """Schema for updating a post."""
    content: Optional[str] = Field(None, min_length=1, max_length=5000)
    tags: Optional[List[str]] = Field(None, max_items=20)
    visibility: Optional[PostVisibility] = None


class PostRead(BaseModel):
    """Schema for reading a post."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    author_id: int
    author_name: str
    author_avatar: Optional[str] = None
    author_level: int = 1
    content: str
    media_urls: List[str] = []
    tags: List[str] = []
    like_count: int
    comment_count: int
    has_liked: bool = False  # Populated per-request
    has_bookmarked: bool = False  # Populated per-request
    post_type: PostType
    linked_course_id: Optional[int] = None
    linked_group_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    is_edited: bool
    is_pinned: bool
    visibility: PostVisibility


class CommentCreate(BaseModel):
    """Schema for creating a comment."""
    content: str = Field(..., min_length=1, max_length=2000, description="Comment content")
    parent_id: Optional[UUID] = Field(None, description="Parent comment ID for replies")


class CommentRead(BaseModel):
    """Schema for reading a comment."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    post_id: UUID
    author_id: int
    author_name: str
    author_avatar: Optional[str] = None
    content: str
    like_count: int
    has_liked: bool = False
    parent_id: Optional[UUID] = None
    reply_count: int
    created_at: datetime
    is_edited: bool


class ReportCreate(BaseModel):
    """Schema for creating a report."""
    target_type: ReportTargetType
    target_id: str
    reason: ReportReason
    description: Optional[str] = Field(None, max_length=1000)


class ReportRead(BaseModel):
    """Schema for report response."""
    id: UUID
    status: str
    message: str = "Report submitted successfully"


class BlockUserCreate(BaseModel):
    """Schema for blocking a user."""
    user_id: int
    reason: Optional[str] = Field(None, max_length=500)


class BlockedUserRead(BaseModel):
    """Schema for reading blocked user."""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    user_id: int
    user_name: str
    user_avatar: Optional[str] = None
    blocked_at: datetime


class PaginatedPostsResponse(BaseModel):
    """Paginated posts response."""
    items: List[PostRead]
    page: int
    limit: int
    total_count: int
    total_pages: int


class PaginatedCommentsResponse(BaseModel):
    """Paginated comments response."""
    items: List[CommentRead]
    page: int
    limit: int
    total_count: int
    total_pages: int

