"""
Pydantic schemas for community module endpoints.
Defines request/response models for study groups and community events.

Write schemas (``*Create`` / ``*Update``) validate and sanitize what a client
may store. Read schemas deliberately do *not* inherit those rules: rows written
before a rule existed (a zero capacity, a two-person group limit that later
became three, a long legacy description) must still be readable, or one old
row turns every list that contains it into a 500.
"""

from datetime import datetime, timedelta
from typing import Optional, List, Literal, Union
from uuid import UUID
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

from lyo_app.community.models import (
    StudyGroupStatus, StudyGroupPrivacy, MembershipRole,
    EventType, EventStatus, AttendanceStatus, BookingStatus
)
from lyo_app.community.content_safety import (
    ensure_not_link_spam,
    plain_text,
    safe_web_url,
)
from lyo_app.community.timeutil import StoredUTCDateTime, UTCDateTime, utc_now

_MAX_EVENT_DURATION = timedelta(days=31)


def _positive_or_none(value):
    """Legacy zero/negative capacities mean "no limit" on read."""
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if number >= 1 else None


def _coordinate_or_none(value, bound: float):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if -bound <= number <= bound else None


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
    location: Optional[str] = Field(None, max_length=300, description="Physical meeting location")
    is_online: bool = Field(default=False, description="Whether this group meets online")
    meeting_url: Optional[str] = Field(None, max_length=500, description="Online meeting URL")
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    image_url: Optional[str] = Field(None, max_length=500)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        cleaned = plain_text(value)
        if not cleaned:
            raise ValueError("A group name is required")
        return cleaned

    @field_validator("description")
    @classmethod
    def _clean_description(cls, value: Optional[str]) -> Optional[str]:
        cleaned = plain_text(value, multiline=True)
        ensure_not_link_spam(cleaned)
        return cleaned

    @field_validator("location")
    @classmethod
    def _clean_location(cls, value: Optional[str]) -> Optional[str]:
        return plain_text(value)

    @field_validator("meeting_url", "image_url")
    @classmethod
    def _clean_url(cls, value: Optional[str]) -> Optional[str]:
        return safe_web_url(value)


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
    location: Optional[str] = Field(None, max_length=300)
    is_online: Optional[bool] = None
    meeting_url: Optional[str] = Field(None, max_length=500)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    image_url: Optional[str] = Field(None, max_length=500)

    @field_validator("name", "location")
    @classmethod
    def _clean_line(cls, value: Optional[str]) -> Optional[str]:
        return plain_text(value)

    @field_validator("description")
    @classmethod
    def _clean_description(cls, value: Optional[str]) -> Optional[str]:
        cleaned = plain_text(value, multiline=True)
        ensure_not_link_spam(cleaned)
        return cleaned

    @field_validator("meeting_url", "image_url")
    @classmethod
    def _clean_url(cls, value: Optional[str]) -> Optional[str]:
        return safe_web_url(value)


class StudyGroupRead(BaseModel):
    """Schema for reading study group data (tolerant of legacy rows)."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Study group ID")
    name: str
    description: Optional[str] = None
    privacy: StudyGroupPrivacy = StudyGroupPrivacy.PUBLIC
    max_members: Optional[int] = None
    requires_approval: bool = False
    course_id: Optional[int] = None
    location: Optional[str] = None
    is_online: bool = False
    meeting_url: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    image_url: Optional[str] = None
    status: StudyGroupStatus = Field(..., description="Group status")
    creator_id: int = Field(..., description="Creator user ID")
    created_at: UTCDateTime = Field(..., description="Creation timestamp")
    updated_at: UTCDateTime = Field(..., description="Last update timestamp")

    # Computed fields
    member_count: Optional[int] = Field(None, description="Number of members")
    is_member: Optional[bool] = Field(None, description="Whether current user is a member")
    user_role: Optional[MembershipRole] = Field(None, description="Current user's role in group")
    host: Optional[UserPreview] = None

    @field_validator("max_members", mode="before")
    @classmethod
    def _legacy_capacity(cls, value):
        return _positive_or_none(value)

    @field_validator("latitude", mode="before")
    @classmethod
    def _legacy_latitude(cls, value):
        return _coordinate_or_none(value, 90)

    @field_validator("longitude", mode="before")
    @classmethod
    def _legacy_longitude(cls, value):
        return _coordinate_or_none(value, 180)

    @field_validator("is_online", "requires_approval", mode="before")
    @classmethod
    def _legacy_flag(cls, value):
        return bool(value)


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
    joined_at: UTCDateTime = Field(..., description="Join timestamp")
    approved_at: Optional[UTCDateTime] = Field(None, description="Approval timestamp")
    approved_by_id: Optional[int] = Field(None, description="Approver user ID")


# Community Event Schemas
class EventVisibility(str, Enum):
    """Who can discover an event."""
    PUBLIC = "public"        # on the map and in search for every signed-in learner
    UNLISTED = "unlisted"    # reachable by link, never on the map
    PRIVATE = "private"      # organizer, people who RSVP'd, and linked group members


class PriceType(str, Enum):
    FREE = "free"
    PAID = "paid"


class AttendanceMode(str, Enum):
    IN_PERSON = "in_person"
    ONLINE = "online"
    HYBRID = "hybrid"


class EventLifecycle(str, Enum):
    """Where an event is in time, computed on every read."""
    UPCOMING = "upcoming"
    TODAY = "today"          # starts later today in the viewer's timezone
    LIVE = "live"            # happening right now
    PAST = "past"
    CANCELLED = "cancelled"


class RSVPStatus(str, Enum):
    GOING = "going"
    INTERESTED = "interested"


class _EventWriteValidation(BaseModel):
    """Sanitization shared by event create and update payloads."""

    @field_validator(
        "title", "location", "organizer_name", "venue_name", "address",
        check_fields=False,
    )
    @classmethod
    def _clean_line(cls, value: Optional[str]) -> Optional[str]:
        return plain_text(value)

    @field_validator("description", check_fields=False)
    @classmethod
    def _clean_description(cls, value: Optional[str]) -> Optional[str]:
        cleaned = plain_text(value, multiline=True)
        ensure_not_link_spam(cleaned)
        return cleaned

    @field_validator("meeting_url", "website_url", "image_url", check_fields=False)
    @classmethod
    def _clean_url(cls, value: Optional[str]) -> Optional[str]:
        return safe_web_url(value)

    @field_validator("timezone", check_fields=False)
    @classmethod
    def _clean_timezone(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        candidate = value.strip() or "UTC"
        try:
            ZoneInfo(candidate)
        except (ZoneInfoNotFoundError, ValueError, KeyError):
            return "UTC"
        return candidate

    @field_validator("currency", check_fields=False)
    @classmethod
    def _clean_currency(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip().upper()
        if not cleaned.isalpha() or len(cleaned) != 3:
            raise ValueError("Currency must be a three-letter code such as USD")
        return cleaned


class CommunityEventBase(_EventWriteValidation):
    """Base community event schema with common fields."""

    title: str = Field(..., min_length=1, max_length=200, description="Event title")
    description: Optional[str] = Field(None, max_length=4000, description="Event description")
    event_type: EventType = Field(default=EventType.STUDY_SESSION, description="Type of event")
    location: Optional[str] = Field(None, max_length=300, description="Event location")
    is_online: bool = Field(default=False, description="Whether the event is online")
    meeting_url: Optional[str] = Field(None, max_length=500, description="Virtual meeting URL")
    max_attendees: Optional[int] = Field(None, ge=1, le=10000, description="Maximum attendees")
    start_time: StoredUTCDateTime = Field(..., description="Event start time")
    end_time: StoredUTCDateTime = Field(..., description="Event end time")
    timezone: str = Field(default="UTC", max_length=50, description="Event timezone")
    study_group_id: Optional[int] = Field(None, description="Associated study group ID")
    course_id: Optional[int] = Field(None, description="Associated course ID")
    lesson_id: Optional[int] = Field(None, description="Associated lesson ID")
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    room_id: Optional[str] = Field(None, max_length=100)
    image_url: Optional[str] = Field(None, max_length=500)
    visibility: EventVisibility = Field(default=EventVisibility.PUBLIC)
    price_type: PriceType = Field(default=PriceType.FREE)
    price_amount: Optional[float] = Field(None, ge=0, le=100000)
    currency: Optional[str] = Field(None, max_length=3)
    website_url: Optional[str] = Field(None, max_length=500)
    organizer_name: Optional[str] = Field(None, max_length=200)
    venue_name: Optional[str] = Field(None, max_length=200)
    address: Optional[str] = Field(None, max_length=500)
    attendance_mode: Optional[AttendanceMode] = None


class CommunityEventCreate(CommunityEventBase):
    """Schema for creating a new community event."""

    # Clients generate one id per "Create" form; a retried or double-tapped
    # submit with the same id returns the original event instead of a copy.
    client_request_id: Optional[str] = Field(
        None, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$"
    )

    @model_validator(mode="after")
    def _coherent_event(self) -> "CommunityEventCreate":
        if not self.title:
            raise ValueError("An event title is required")
        if self.end_time <= self.start_time:
            raise ValueError("The event must end after it starts")
        if self.end_time - self.start_time > _MAX_EVENT_DURATION:
            raise ValueError("Events can last at most 31 days")
        if self.end_time <= utc_now():
            raise ValueError("This event has already ended")
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("A map location needs both latitude and longitude")
        if self.attendance_mode is None:
            if self.is_online and self.latitude is not None:
                self.attendance_mode = AttendanceMode.HYBRID
            elif self.is_online:
                self.attendance_mode = AttendanceMode.ONLINE
            else:
                self.attendance_mode = AttendanceMode.IN_PERSON
        if self.attendance_mode in {AttendanceMode.ONLINE, AttendanceMode.HYBRID}:
            self.is_online = True
        # An in-person event without a place is accepted for older clients;
        # it simply has no map pin. Current apps require an address or pin.
        if self.attendance_mode == AttendanceMode.ONLINE:
            # An online-only event never pretends to have a physical pin.
            self.latitude = None
            self.longitude = None
        if self.price_type == PriceType.FREE:
            self.price_amount = None
        elif self.price_amount is not None and not self.currency:
            self.currency = "USD"
        return self


class CommunityEventUpdate(_EventWriteValidation):
    """Schema for updating community event information."""

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=4000)
    event_type: Optional[EventType] = None
    location: Optional[str] = Field(None, max_length=300)
    is_online: Optional[bool] = None
    meeting_url: Optional[str] = Field(None, max_length=500)
    max_attendees: Optional[int] = Field(None, ge=1, le=10000)
    start_time: Optional[StoredUTCDateTime] = None
    end_time: Optional[StoredUTCDateTime] = None
    timezone: Optional[str] = Field(None, max_length=50)
    status: Optional[EventStatus] = None
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    room_id: Optional[str] = Field(None, max_length=100)
    image_url: Optional[str] = Field(None, max_length=500)
    visibility: Optional[EventVisibility] = None
    price_type: Optional[PriceType] = None
    price_amount: Optional[float] = Field(None, ge=0, le=100000)
    currency: Optional[str] = Field(None, max_length=3)
    website_url: Optional[str] = Field(None, max_length=500)
    organizer_name: Optional[str] = Field(None, max_length=200)
    venue_name: Optional[str] = Field(None, max_length=200)
    address: Optional[str] = Field(None, max_length=500)
    attendance_mode: Optional[AttendanceMode] = None


class CommunityEventRead(BaseModel):
    """Schema for reading community event data (tolerant of legacy rows)."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Event ID")
    title: str
    description: Optional[str] = None
    event_type: EventType = EventType.OTHER
    location: Optional[str] = None
    is_online: bool = False
    meeting_url: Optional[str] = None
    max_attendees: Optional[int] = None
    start_time: UTCDateTime
    end_time: UTCDateTime
    timezone: str = "UTC"
    study_group_id: Optional[int] = None
    course_id: Optional[int] = None
    lesson_id: Optional[int] = None
    status: EventStatus = Field(..., description="Event status")
    organizer_id: int = Field(..., description="Organizer user ID")
    latitude: Optional[float] = Field(None, description="Event latitude")
    longitude: Optional[float] = Field(None, description="Event longitude")
    room_id: Optional[str] = Field(None, description="Specific room or area ID")
    image_url: Optional[str] = Field(None, description="Event image URL")
    visibility: EventVisibility = EventVisibility.PUBLIC
    price_type: PriceType = PriceType.FREE
    price_amount: Optional[float] = None
    currency: Optional[str] = None
    website_url: Optional[str] = None
    organizer_name: Optional[str] = None
    venue_name: Optional[str] = None
    address: Optional[str] = None
    attendance_mode: Optional[AttendanceMode] = None
    created_at: UTCDateTime = Field(..., description="Creation timestamp")
    updated_at: UTCDateTime = Field(..., description="Last update timestamp")

    # Computed fields
    attendee_count: Optional[int] = Field(None, description="Number of attendees")
    user_attendance_status: Optional[AttendanceStatus] = Field(None, description="Current user's attendance status")
    is_full: Optional[bool] = Field(None, description="Whether event is at capacity")
    organizer_profile: Optional[UserPreview] = None

    @field_validator("max_attendees", mode="before")
    @classmethod
    def _legacy_capacity(cls, value):
        return _positive_or_none(value)

    @field_validator("latitude", mode="before")
    @classmethod
    def _legacy_latitude(cls, value):
        return _coordinate_or_none(value, 90)

    @field_validator("longitude", mode="before")
    @classmethod
    def _legacy_longitude(cls, value):
        return _coordinate_or_none(value, 180)

    @field_validator("timezone", mode="before")
    @classmethod
    def _legacy_timezone(cls, value):
        return value or "UTC"

    @field_validator("is_online", mode="before")
    @classmethod
    def _legacy_online(cls, value):
        return bool(value)

    @field_validator("visibility", mode="before")
    @classmethod
    def _legacy_visibility(cls, value):
        return value or EventVisibility.PUBLIC

    @field_validator("price_type", mode="before")
    @classmethod
    def _legacy_price_type(cls, value):
        return value or PriceType.FREE

    @field_validator("attendance_mode", mode="before")
    @classmethod
    def _legacy_mode(cls, value):
        return value or None


# Map-first Community contract shared by iOS, Android, and web.
class LearningNodeKind(str, Enum):
    EVENT = "event"
    STUDY_GROUP = "study_group"
    PRIVATE_LESSON = "private_lesson"
    INSTITUTION = "institution"


class LearningNodeCategory(str, Enum):
    EVENT = "event"
    WORKSHOP = "workshop"
    CLASS = "class"
    STUDY_GROUP = "study_group"
    TUTOR = "tutor"
    LIBRARY = "library"
    MUSEUM = "museum"
    EDUCATIONAL_CENTER = "educational_center"


class LearningNode(BaseModel):
    """One educational opportunity on the Learning Around Me map.

    Every field added after the first contract is optional with a default, so
    older app builds keep decoding the same payload.
    """

    key: str = Field(..., min_length=3, max_length=320)
    kind: LearningNodeKind
    category: LearningNodeCategory
    id: str = Field(..., min_length=1, max_length=255)
    title: str = Field(..., min_length=1, max_length=300)
    description: Optional[str] = Field(None, max_length=4000)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    distance_km: Optional[float] = Field(None, ge=0)
    location_name: Optional[str] = Field(None, max_length=500)
    is_online: bool = False
    meeting_url: Optional[str] = Field(None, max_length=1000)
    starts_at: Optional[UTCDateTime] = None
    ends_at: Optional[UTCDateTime] = None
    timezone: Optional[str] = Field(None, max_length=50)
    host: Optional[UserPreview] = None
    member_count: Optional[int] = Field(None, ge=0)
    attendee_count: Optional[int] = Field(None, ge=0)
    capacity: Optional[int] = Field(None, ge=1)
    is_joined: bool = False
    is_attending: bool = False
    is_saved: bool = False
    course_id: Optional[int] = None
    lesson_id: Optional[int] = None
    study_group_id: Optional[int] = None
    image_url: Optional[str] = Field(None, max_length=1000)
    source: str = Field(default="lyo", max_length=50)
    source_url: Optional[str] = Field(None, max_length=1000)
    # --- Contract 4: lifecycle, RSVP, pricing, and place details ----------
    lifecycle: Optional[EventLifecycle] = None
    rsvp_status: Optional[RSVPStatus] = None
    going_count: Optional[int] = Field(None, ge=0)
    interested_count: Optional[int] = Field(None, ge=0)
    is_free: Optional[bool] = None
    price_amount: Optional[float] = Field(None, ge=0)
    currency: Optional[str] = Field(None, max_length=10)
    organizer_name: Optional[str] = Field(None, max_length=200)
    venue_name: Optional[str] = Field(None, max_length=200)
    address: Optional[str] = Field(None, max_length=500)
    attendance_mode: Optional[AttendanceMode] = None
    visibility: Optional[EventVisibility] = None
    website_url: Optional[str] = Field(None, max_length=1000)
    phone: Optional[str] = Field(None, max_length=60)
    email: Optional[str] = Field(None, max_length=200)
    opening_hours: Optional[str] = Field(None, max_length=500)
    place_type: Optional[str] = Field(None, max_length=60)
    relevance: Optional[str] = Field(None, max_length=300)
    is_owner: bool = False
    is_full: Optional[bool] = None
    # The viewer is on this event's guest list (invited by link or by name).
    is_invited: bool = False


class NearbyLearningResponse(BaseModel):
    items: List[LearningNode]
    center_latitude: float
    center_longitude: float
    radius_km: float
    fetched_at: UTCDateTime
    # Sources that failed for this request (e.g. "places"); the rest of the
    # map is still valid, and clients can say "some places could not load".
    degraded_sources: List[str] = Field(default_factory=list)


class LearningNodeSaveRequest(BaseModel):
    snapshot: LearningNode


class CommunityMeResponse(BaseModel):
    """Canonical account-owned Community state used on every platform."""

    joined_groups: List[StudyGroupRead]
    attending_events: List[CommunityEventRead]
    saved_nodes: List[LearningNode]
    following: List[UserPreview]
    updated_at: UTCDateTime
    # Contract 4: the same account state as map nodes, split by intent.
    hosting: List[LearningNode] = Field(default_factory=list)
    going: List[LearningNode] = Field(default_factory=list)
    interested: List[LearningNode] = Field(default_factory=list)
    # Upcoming events the learner was invited to and has not answered yet.
    invited: List[LearningNode] = Field(default_factory=list)


class LearningNodeDetail(BaseModel):
    """Everything the full detail screen needs in one request."""

    node: LearningNode
    related: List[LearningNode] = Field(default_factory=list)
    can_edit: bool = False
    event: Optional[CommunityEventRead] = None


class EventRSVPRequest(BaseModel):
    status: RSVPStatus


class EventReportRequest(BaseModel):
    reason: str = Field(default="other", max_length=40)
    description: Optional[str] = Field(None, max_length=1000)

    @field_validator("description")
    @classmethod
    def _clean_description(cls, value: Optional[str]) -> Optional[str]:
        return plain_text(value, multiline=True)


class EventReportResponse(BaseModel):
    status: Literal["received", "already_reported"]
    message: str


# --- Invitations ---------------------------------------------------------


class EventInviteCreate(BaseModel):
    """A new invite link. Links expire after 30 days unless the host chooses."""

    max_uses: Optional[int] = Field(None, ge=1, le=1000)
    expires_in_days: Optional[int] = Field(30, ge=1, le=90)


class EventInviteRead(BaseModel):
    id: int
    token: str
    url: str
    created_at: UTCDateTime
    expires_at: Optional[UTCDateTime] = None
    max_uses: Optional[int] = None
    use_count: int = 0
    active: bool = True


class EventGuestCreate(BaseModel):
    """Invite one Lyo member by account."""

    user_id: int = Field(..., ge=1)


class EventGuestRead(BaseModel):
    user: UserPreview
    source: Literal["link", "direct"]
    invited_at: UTCDateTime
    rsvp_status: Optional[RSVPStatus] = None


class EventInvitesResponse(BaseModel):
    """The host's view: live and past links, and everyone on the guest list."""

    links: List[EventInviteRead] = Field(default_factory=list)
    guests: List[EventGuestRead] = Field(default_factory=list)


class InvitePreview(BaseModel):
    """What someone holding an invite link sees before they accept it."""

    status: Literal["valid", "expired", "revoked", "used_up", "ended", "cancelled"]
    already_guest: bool = False
    is_host: bool = False
    event_id: int
    title: str
    starts_at: Optional[UTCDateTime] = None
    ends_at: Optional[UTCDateTime] = None
    timezone: Optional[str] = None
    location_name: Optional[str] = None
    attendance_mode: Optional[AttendanceMode] = None
    visibility: Optional[EventVisibility] = None
    host: Optional[UserPreview] = None
    organizer_name: Optional[str] = None
    image_url: Optional[str] = None


class PlaceSuggestion(BaseModel):
    name: str
    label: str
    kind: str
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    radius_km: float = Field(..., gt=0, le=100)
    is_area: bool = False


class SearchResolution(BaseModel):
    """How the map should react to what the learner typed."""

    query: str
    intent: Literal["topic", "place", "mixed"]
    topic: Optional[str] = None
    terms: List[str] = Field(default_factory=list)
    categories: List[LearningNodeCategory] = Field(default_factory=list)
    place: Optional[PlaceSuggestion] = None
    places: List[PlaceSuggestion] = Field(default_factory=list)


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
    registered_at: UTCDateTime = Field(..., description="Registration timestamp")


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
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    is_online: bool = False
    meeting_url: Optional[str] = Field(None, max_length=500)
    image_url: Optional[str] = Field(None, max_length=500)


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
    is_online: bool = False
    meeting_url: Optional[str] = None
    image_url: Optional[str] = None
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
