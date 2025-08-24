"""
Pydantic schemas for community module endpoints.
Defines request/response models for study groups and community events.
"""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field, ConfigDict

from lyo_app.community.models import (
    StudyGroupStatus, StudyGroupPrivacy, MembershipRole,
    EventType, EventStatus, AttendanceStatus
)


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
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    
    # Computed fields
    attendee_count: Optional[int] = Field(None, description="Number of attendees")
    user_attendance_status: Optional[AttendanceStatus] = Field(None, description="Current user's attendance status")
    is_full: Optional[bool] = Field(None, description="Whether event is at capacity")


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
    """Schema for reading attendance data."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: int = Field(..., description="Attendance ID")
    user_id: int = Field(..., description="User ID")
    event_id: int = Field(..., description="Event ID")
    status: AttendanceStatus = Field(..., description="Attendance status")
    rating: Optional[int] = Field(None, description="Event rating")
    feedback: Optional[str] = Field(None, description="Event feedback")
    registered_at: datetime = Field(..., description="Registration timestamp")
    attended_at: Optional[datetime] = Field(None, description="Attendance timestamp")
    feedback_at: Optional[datetime] = Field(None, description="Feedback timestamp")


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
