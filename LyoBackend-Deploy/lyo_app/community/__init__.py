"""
Community module for LyoApp.
Handles study groups, community events, and collaborative learning features.
"""

from .models import (
    StudyGroup, GroupMembership, CommunityEvent, EventAttendance,
    StudyGroupStatus, StudyGroupPrivacy, MembershipRole,
    EventType, EventStatus, AttendanceStatus
)
from .schemas import (
    StudyGroupCreate, StudyGroupUpdate, StudyGroupRead,
    GroupMembershipCreate, GroupMembershipUpdate, GroupMembershipRead,
    CommunityEventCreate, CommunityEventUpdate, CommunityEventRead,
    EventAttendanceCreate, EventAttendanceUpdate, EventAttendanceRead
)
from .service import CommunityService
from .routes import router

__all__ = [
    # Models
    "StudyGroup", "GroupMembership", "CommunityEvent", "EventAttendance",
    "StudyGroupStatus", "StudyGroupPrivacy", "MembershipRole",
    "EventType", "EventStatus", "AttendanceStatus",
    # Schemas
    "StudyGroupCreate", "StudyGroupUpdate", "StudyGroupRead",
    "GroupMembershipCreate", "GroupMembershipUpdate", "GroupMembershipRead",
    "CommunityEventCreate", "CommunityEventUpdate", "CommunityEventRead",
    "EventAttendanceCreate", "EventAttendanceUpdate", "EventAttendanceRead",
    # Service
    "CommunityService",
    # Router
    "router"
]
