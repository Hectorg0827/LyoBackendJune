"""
Database models for the community module.
Defines study groups, community events, and related entities.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship

from lyo_app.core.database import Base


class StudyGroupStatus(str, Enum):
    """Study group status enumeration."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class StudyGroupPrivacy(str, Enum):
    """Study group privacy level enumeration."""
    PUBLIC = "public"
    PRIVATE = "private"
    INVITE_ONLY = "invite_only"


class MembershipRole(str, Enum):
    """Group membership role enumeration."""
    OWNER = "owner"
    ADMIN = "admin"
    MODERATOR = "moderator"
    MEMBER = "member"


class EventType(str, Enum):
    """Community event type enumeration."""
    STUDY_SESSION = "study_session"
    WORKSHOP = "workshop"
    LECTURE = "lecture"
    DISCUSSION = "discussion"
    PROJECT_SHOWCASE = "project_showcase"
    NETWORKING = "networking"
    OTHER = "other"


class EventStatus(str, Enum):
    """Event status enumeration."""
    SCHEDULED = "scheduled"
    ONGOING = "ongoing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class AttendanceStatus(str, Enum):
    """Event attendance status enumeration."""
    GOING = "going"
    MAYBE = "maybe"
    NOT_GOING = "not_going"
    ATTENDED = "attended"
    NO_SHOW = "no_show"


class StudyGroup(Base):
    """
    Study group model for collaborative learning.
    Represents groups where users can study together.
    """
    
    __tablename__ = "study_groups"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=True)
    privacy = Column(SQLEnum(StudyGroupPrivacy), nullable=False, default=StudyGroupPrivacy.PUBLIC)
    status = Column(SQLEnum(StudyGroupStatus), nullable=False, default=StudyGroupStatus.ACTIVE)
    
    # Group settings
    max_members = Column(Integer, nullable=True)  # None means unlimited
    requires_approval = Column(Boolean, nullable=False, default=False)
    
    # Associations
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=True, index=True)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    creator = relationship("User", back_populates="created_study_groups")
    course = relationship("Course", back_populates="study_groups")
    memberships = relationship("GroupMembership", back_populates="study_group", cascade="all, delete-orphan")
    events = relationship("CommunityEvent", back_populates="study_group")


class GroupMembership(Base):
    """
    Study group membership model.
    Represents user participation in study groups.
    """
    
    __tablename__ = "group_memberships"
    
    id = Column(Integer, primary_key=True, index=True)
    role = Column(SQLEnum(MembershipRole), nullable=False, default=MembershipRole.MEMBER)
    is_approved = Column(Boolean, nullable=False, default=True)  # False for pending requests
    
    # Associations
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    study_group_id = Column(Integer, ForeignKey("study_groups.id"), nullable=False, index=True)
    
    # Metadata
    joined_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    approved_at = Column(DateTime, nullable=True)
    approved_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id], back_populates="group_memberships")
    study_group = relationship("StudyGroup", back_populates="memberships")
    approved_by = relationship("User", foreign_keys=[approved_by_id])
    
    # Constraints
    __table_args__ = (
        # Unique constraint to prevent duplicate memberships
        {"extend_existing": True}
    )


class CommunityEvent(Base):
    """
    Community event model for study sessions, workshops, etc.
    Represents scheduled events within study groups or the broader community.
    """
    
    __tablename__ = "community_events"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=True)
    event_type = Column(SQLEnum(EventType), nullable=False, default=EventType.STUDY_SESSION)
    status = Column(SQLEnum(EventStatus), nullable=False, default=EventStatus.SCHEDULED)
    
    # Event details
    location = Column(String(300), nullable=True)  # Physical or virtual location
    meeting_url = Column(String(500), nullable=True)  # Video call link
    max_attendees = Column(Integer, nullable=True)  # None means unlimited
    
    # Timing
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=False)
    timezone = Column(String(50), nullable=False, default="UTC")
    
    # Associations
    organizer_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    study_group_id = Column(Integer, ForeignKey("study_groups.id"), nullable=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=True, index=True)
    lesson_id = Column(Integer, ForeignKey("lessons.id"), nullable=True, index=True)
    
    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    organizer = relationship("User", back_populates="organized_events")
    study_group = relationship("StudyGroup", back_populates="events")
    course = relationship("Course", back_populates="community_events")
    lesson = relationship("Lesson", back_populates="community_events")
    attendances = relationship("EventAttendance", back_populates="event", cascade="all, delete-orphan")


class EventAttendance(Base):
    """
    Event attendance model.
    Tracks user participation in community events.
    """
    
    __tablename__ = "event_attendances"
    
    id = Column(Integer, primary_key=True, index=True)
    status = Column(SQLEnum(AttendanceStatus), nullable=False, default=AttendanceStatus.GOING)
    
    # Feedback (post-event)
    rating = Column(Integer, nullable=True)  # 1-5 scale
    feedback = Column(Text, nullable=True)
    
    # Associations
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    event_id = Column(Integer, ForeignKey("community_events.id"), nullable=False, index=True)
    
    # Metadata
    registered_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    attended_at = Column(DateTime, nullable=True)  # When user actually attended
    feedback_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="event_attendances")
    event = relationship("CommunityEvent", back_populates="attendances")
    
    # Constraints
    __table_args__ = (
        # Unique constraint to prevent duplicate registrations
        {"extend_existing": True}
    )


# Add reverse relationships to existing models (these would be added to the respective model files)
"""
Additional relationships to add to existing models:

User model additions:
    created_study_groups = relationship("StudyGroup", back_populates="creator")
    group_memberships = relationship("GroupMembership", back_populates="user", foreign_keys=[GroupMembership.user_id])
    organized_events = relationship("CommunityEvent", back_populates="organizer")
    event_attendances = relationship("EventAttendance", back_populates="user")

Course model additions:
    study_groups = relationship("StudyGroup", back_populates="course")
    community_events = relationship("CommunityEvent", back_populates="course")

Lesson model additions:
    community_events = relationship("CommunityEvent", back_populates="lesson")
"""
