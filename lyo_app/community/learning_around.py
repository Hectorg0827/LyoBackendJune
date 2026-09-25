"""Canonical map-first Community discovery and account state.

This module deliberately sits behind one authenticated API contract. Native
map SDKs may differ by platform, but the nodes, memberships, attendance,
saves, and connections always come from the same user-owned backend rows.
"""

from __future__ import annotations

import logging
import math
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Iterable, Optional, Set, TypeVar

import httpx
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from lyo_app.auth.models import User
from lyo_app.community.models import (
    AttendanceStatus,
    CommunityEvent,
    CommunitySavedNode,
    EventAttendance,
    EventStatus,
    EventType,
    GroupMembership,
    PrivateLesson,
    StudyGroup,
    StudyGroupPrivacy,
    StudyGroupStatus,
)
from lyo_app.community.query_intent import TopicQuery, parse_topic
from lyo_app.community.schemas import (
    AttendanceMode,
    CommunityEventRead,
    CommunityMeResponse,
    EventLifecycle,
    EventVisibility,
    LearningNode,
    LearningNodeCategory,
    LearningNodeDetail,
    LearningNodeKind,
    NearbyLearningResponse,
    RSVPStatus,
    StudyGroupRead,
    UserPreview,
)
from lyo_app.community.timeutil import (
    day_window,
    resolve_zone,
    to_naive_utc,
    utc_now,
    week_window,
)
from lyo_app.feeds.models import UserFollow

logger = logging.getLogger(__name__)
ReadResult = TypeVar("ReadResult")

ACTIVE_ATTENDANCE = (AttendanceStatus.GOING, AttendanceStatus.MAYBE, AttendanceStatus.ATTENDED)
GOING_ATTENDANCE = (AttendanceStatus.GOING, AttendanceStatus.ATTENDED)
MAX_SAVED_NODES_PER_USER = 500
# Overpass cost grows with area; wider map views still list Lyo nodes but
# only look up public institutions within this radius of the center.
MAX_PLACE_RADIUS_KM = 25.0
WHEN_FILTERS = {"today", "week"}

_PLACE_RELEVANCE = {
    "library": "Free study space, books, and public learning programs.",
    "museum": "Exhibits and programs for hands-on learning.",
    "planetarium": "Astronomy shows and science learning.",
    "university": "Campus with courses, lectures, and public events.",
    "college": "Campus with courses, lectures, and public events.",
    "language_school": "Language classes and conversation practice.",
    "music_school": "Music lessons, theory, and ensembles.",
    "prep_school": "Tutoring and test preparation.",
    "training": "Career and vocational training.",
    "community_centre": "Community classes, workshops, and study space.",
}


def _clean_text(value: Any, max_length: int) -> Optional[str]:
    """Return provider/legacy text that is safe for the public map contract."""
    if value is None:
        return None
    text = str(value).strip()
    return text[:max_length] or None


def _clean_coordinates(
    latitude: Any,
    longitude: Any,
) -> tuple[Optional[float], Optional[float]]:
    """Treat corrupt or partial coordinates as unavailable, not a map outage."""
    try:
        point_latitude = float(latitude)
        point_longitude = float(longitude)
    except (TypeError, ValueError, OverflowError):
        return None, None
    if (
        not math.isfinite(point_latitude)
        or not math.isfinite(point_longitude)
        or not -90 <= point_latitude <= 90
        or not -180 <= point_longitude <= 180
    ):
        return None, None
    return point_latitude, point_longitude


def _positive_capacity(value: Any) -> Optional[int]:
    """Normalize pre-contract zero/negative capacities to unlimited."""
    try:
        capacity = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return capacity if capacity >= 1 else None


def _start_sort_value(value: Optional[datetime]) -> float:
    """Sort aware and naive legacy datetimes without comparing them directly."""
    if value is None:
        return float("inf")
    try:
        normalized = value
        if value.tzinfo is None or value.utcoffset() is None:
            normalized = value.replace(tzinfo=timezone.utc)
        return normalized.timestamp()
    except (AttributeError, OSError, OverflowError, ValueError):
        return float("inf")


def _enum_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    return getattr(value, "value", value)


def _display_name(user: Optional[User]) -> str:
    if user is None:
        return ""
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    return full_name or user.username or "Lyo learner"


def _preview(user: Optional[User]) -> Optional[UserPreview]:
    if user is None:
        return None
    return UserPreview(id=user.id, name=_display_name(user), avatar=user.avatar_url)


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lng / 2) ** 2
    )
    # Floating point rounding can push an antipodal distance just outside
    # [0, 1], which otherwise raises while building the whole map response.
    value = min(1.0, max(0.0, value))
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def _bounds(lat: float, lng: float, radius_km: float) -> tuple[float, float, float, float]:
    lat_delta = radius_km / 111.0
    longitude_scale = max(math.cos(math.radians(lat)), 0.15)
    lng_delta = radius_km / (111.0 * longitude_scale)
    return lat - lat_delta, lat + lat_delta, lng - lng_delta, lng + lng_delta


def _event_category(event_type: EventType) -> LearningNodeCategory:
    if event_type == EventType.WORKSHOP:
        return LearningNodeCategory.WORKSHOP
    if event_type in {
        EventType.CLASS,
        EventType.SEMINAR,
        EventType.LECTURE,
        EventType.OFFICE_HOURS,
    }:
        return LearningNodeCategory.CLASS
    return LearningNodeCategory.EVENT


def event_lifecycle(event: CommunityEvent, now: datetime, zone) -> EventLifecycle:
    """Where an event sits in time for this viewer (naive-UTC ``now``)."""
    status = getattr(event, "status", None)
    if status == EventStatus.CANCELLED:
        return EventLifecycle.CANCELLED
    start = to_naive_utc(event.start_time)
    end = to_naive_utc(event.end_time)
    if end is not None and end <= now:
        return EventLifecycle.PAST
    if status == EventStatus.COMPLETED:
        return EventLifecycle.PAST
    if start is not None and start <= now:
        return EventLifecycle.LIVE
    _, day_end = day_window(zone, now)
    if start is not None and start < day_end:
        return EventLifecycle.TODAY
    return EventLifecycle.UPCOMING


def _rsvp_from_attendance(status: Optional[AttendanceStatus]) -> Optional[RSVPStatus]:
    if status in GOING_ATTENDANCE:
        return RSVPStatus.GOING
    if status == AttendanceStatus.MAYBE:
        return RSVPStatus.INTERESTED
    return None


class _AccountState:
    """The signed-in learner's relationship to Lyo-owned nodes."""

    def __init__(
        self,
        user_id: int,
        saved_keys: Set[str],
        joined_group_ids: Set[int],
        attendance: dict[int, AttendanceStatus],
    ) -> None:
        self.user_id = user_id
        self.saved_keys = saved_keys
        self.joined_group_ids = joined_group_ids
        self.attendance = attendance

    @property
    def attending_event_ids(self) -> Set[int]:
        return {
            event_id
            for event_id, status in self.attendance.items()
            if status in ACTIVE_ATTENDANCE
        }


class LearningAroundService:
    """Builds the shared Learning Around Me view and My Community state."""

    _poi_cache: dict[tuple[float, float, float], tuple[float, list[LearningNode]]] = {}
    _poi_cache_ttl_seconds = 300
    # Recently seen places by key, so a detail request for a marker the
    # learner just tapped never needs a second provider round-trip.
    _place_index: dict[str, tuple[float, LearningNode]] = {}
    _place_index_limit = 4000

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    async def get_nearby(
        self,
        db: AsyncSession,
        *,
        user_id: int,
        latitude: float,
        longitude: float,
        radius_km: float,
        categories: Optional[Set[LearningNodeCategory]] = None,
        query_text: Optional[str] = None,
        include_online: bool = True,
        include_institutions: bool = True,
        limit: int = 100,
        when: Optional[str] = None,
        free_only: bool = False,
        place_types: Optional[Set[str]] = None,
        tz: Optional[str] = None,
    ) -> NearbyLearningResponse:
        explicit_categories = set(categories or ())
        categories = explicit_categories or set(LearningNodeCategory)
        topic = parse_topic(query_text)
        when = when if when in WHEN_FILTERS else None
        zone = resolve_zone(tz)
        now = utc_now()
        degraded: list[str] = []

        account = await self._account_state(db, user_id)
        items: list[LearningNode] = []

        def keep(node: LearningNode, dated: bool) -> bool:
            # Time filters narrow dated opportunities; undated ones (a group,
            # a library) stay only when the learner explicitly asked for them.
            if when and not dated and node.category not in explicit_categories:
                return False
            if free_only and node.is_free is not True:
                return False
            return self._within_scope(node, radius_km, include_online, topic)

        event_categories = {
            LearningNodeCategory.EVENT,
            LearningNodeCategory.WORKSHOP,
            LearningNodeCategory.CLASS,
        }
        if categories.intersection(event_categories):
            statement = self._event_query(
                account,
                latitude=latitude,
                longitude=longitude,
                radius_km=radius_km,
                include_online=include_online,
                now=now,
                when=when,
                zone=zone,
                free_only=free_only,
                limit=max(limit * 2, 100),
            )
            events = await self._read_or_default(
                db, "events", lambda: self._scalar_rows(db, statement), None
            )
            if events is None:
                degraded.append("events")
                events = []
            counts = await self._read_or_default(
                db,
                "event counts",
                lambda: self._attendance_counts(db, [event.id for event in events]),
                {},
            )
            for event in events:
                try:
                    if _event_category(event.event_type) not in categories:
                        continue
                    node = self._event_node(
                        event, latitude, longitude, account, counts, now, zone
                    )
                    if keep(node, dated=True):
                        items.append(node)
                except Exception as exc:
                    logger.warning(
                        "Skipping invalid Community event %s: %s",
                        getattr(event, "id", "unknown"),
                        exc,
                    )

        if LearningNodeCategory.STUDY_GROUP in categories:
            statement = self._group_query(
                account,
                latitude=latitude,
                longitude=longitude,
                radius_km=radius_km,
                include_online=include_online,
                limit=max(limit * 2, 100),
            )
            groups = await self._read_or_default(
                db, "study groups", lambda: self._scalar_rows(db, statement), None
            )
            if groups is None:
                degraded.append("study_groups")
                groups = []
            for group in groups:
                try:
                    node = self._group_node(group, latitude, longitude, account)
                    if keep(node, dated=False):
                        items.append(node)
                except Exception as exc:
                    logger.warning(
                        "Skipping invalid Community study group %s: %s",
                        getattr(group, "id", "unknown"),
                        exc,
                    )

        if LearningNodeCategory.TUTOR in categories:
            south, north, west, east = _bounds(latitude, longitude, radius_km)
            lesson_location = and_(
                PrivateLesson.latitude.between(south, north),
                PrivateLesson.longitude.between(west, east),
            )
            if include_online:
                lesson_location = or_(lesson_location, PrivateLesson.is_online.is_(True))
            lesson_statement = (
                select(PrivateLesson)
                .options(selectinload(PrivateLesson.instructor))
                .where(PrivateLesson.is_active.is_(True), lesson_location)
                .order_by(PrivateLesson.updated_at.desc())
                .limit(max(limit * 2, 100))
            )
            lessons = await self._read_or_default(
                db, "private lessons", lambda: self._scalar_rows(db, lesson_statement), None
            )
            if lessons is None:
                degraded.append("tutors")
                lessons = []
            for lesson in lessons:
                try:
                    node = self._lesson_node(lesson, latitude, longitude, account)
                    if keep(node, dated=False):
                        items.append(node)
                except Exception as exc:
                    logger.warning(
                        "Skipping invalid Community private lesson %s: %s",
                        getattr(lesson, "id", "unknown"),
                        exc,
                    )

        institution_categories = {
            LearningNodeCategory.LIBRARY,
            LearningNodeCategory.MUSEUM,
            LearningNodeCategory.EDUCATIONAL_CENTER,
        }
        if include_institutions and categories.intersection(institution_categories):
            places, places_ok = await self._fetch_osm_places(
                latitude, longitude, min(radius_km, MAX_PLACE_RADIUS_KM)
            )
            if not places_ok:
                degraded.append("places")
            for node in places:
                if node.category not in categories:
                    continue
                if (
                    place_types
                    and node.category == LearningNodeCategory.EDUCATIONAL_CENTER
                    and node.place_type not in place_types
                ):
                    continue
                node.is_saved = node.key in account.saved_keys
                if keep(node, dated=False):
                    items.append(node)

        if topic.is_empty:
            items.sort(key=self._distance_sort_key)
        else:
            # A topic search ranks exact-title matches first, then distance.
            items.sort(key=lambda node: (not self._title_matches(node, topic), *self._distance_sort_key(node)))
        return NearbyLearningResponse(
            items=items[:limit],
            center_latitude=latitude,
            center_longitude=longitude,
            radius_km=radius_km,
            fetched_at=datetime.utcnow(),
            degraded_sources=degraded,
        )

    def _event_query(
        self,
        account: _AccountState,
        *,
        latitude: float,
        longitude: float,
        radius_km: float,
        include_online: bool,
        now: datetime,
        when: Optional[str],
        zone,
        free_only: bool,
        limit: int,
    ):
        south, north, west, east = _bounds(latitude, longitude, radius_km)
        location = and_(
            CommunityEvent.latitude.between(south, north),
            CommunityEvent.longitude.between(west, east),
        )
        if include_online:
            location = or_(location, CommunityEvent.is_online.is_(True))
        conditions = [
            CommunityEvent.status.in_([EventStatus.SCHEDULED, EventStatus.ONGOING]),
            CommunityEvent.end_time >= now,
            location,
            self._event_visible_condition(account),
            or_(
                CommunityEvent.moderation_status == "active",
                CommunityEvent.organizer_id == account.user_id,
            ),
        ]
        # Discovery never shows unlisted events, even to their organizer's
        # contacts; the organizer still sees their own on the map.
        conditions.append(
            or_(
                CommunityEvent.visibility != EventVisibility.UNLISTED.value,
                CommunityEvent.organizer_id == account.user_id,
                CommunityEvent.id.in_(account.attending_event_ids or [-1]),
            )
        )
        if when == "today":
            _, day_end = day_window(zone, now)
            conditions.append(CommunityEvent.start_time < day_end)
        elif when == "week":
            _, week_end = week_window(zone, now)
            conditions.append(CommunityEvent.start_time < week_end)
        if free_only:
            conditions.append(CommunityEvent.price_type == "free")
        return (
            select(CommunityEvent)
            .options(selectinload(CommunityEvent.organizer))
            .where(*conditions)
            .order_by(CommunityEvent.start_time)
            .limit(limit)
        )

    @staticmethod
    def _event_visible_condition(account: _AccountState):
        """Who may see an event at all (map, search, and detail)."""
        return or_(
            CommunityEvent.visibility.in_(
                [EventVisibility.PUBLIC.value, EventVisibility.UNLISTED.value]
            ),
            CommunityEvent.visibility.is_(None),
            CommunityEvent.organizer_id == account.user_id,
            CommunityEvent.id.in_(account.attending_event_ids or [-1]),
            and_(
                CommunityEvent.study_group_id.isnot(None),
                CommunityEvent.study_group_id.in_(account.joined_group_ids or [-1]),
            ),
        )

    def _group_query(
        self,
        account: _AccountState,
        *,
        latitude: float,
        longitude: float,
        radius_km: float,
        include_online: bool,
        limit: int,
    ):
        south, north, west, east = _bounds(latitude, longitude, radius_km)
        location = and_(
            StudyGroup.latitude.between(south, north),
            StudyGroup.longitude.between(west, east),
        )
        if include_online:
            location = or_(location, StudyGroup.is_online.is_(True))
        return (
            select(StudyGroup)
            .options(
                selectinload(StudyGroup.creator),
                selectinload(StudyGroup.memberships),
            )
            .where(
                StudyGroup.status == StudyGroupStatus.ACTIVE,
                or_(
                    StudyGroup.privacy == StudyGroupPrivacy.PUBLIC,
                    StudyGroup.id.in_(account.joined_group_ids or [-1]),
                ),
                location,
            )
            .order_by(StudyGroup.updated_at.desc())
            .limit(limit)
        )

    @staticmethod
    def _distance_sort_key(item: LearningNode) -> tuple:
        return (
            item.distance_km is None,
            item.distance_km if item.distance_km is not None else float("inf"),
            _start_sort_value(item.starts_at),
            item.title.lower(),
        )

    @staticmethod
    def _title_matches(node: LearningNode, topic: TopicQuery) -> bool:
        return bool(topic.terms) and topic.matches(node.category, node.title)

    # ------------------------------------------------------------------
    # Detail
    # ------------------------------------------------------------------

    async def get_node_detail(
        self,
        db: AsyncSession,
        *,
        user_id: int,
        kind: LearningNodeKind,
        node_id: str,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        tz: Optional[str] = None,
        include_related: bool = True,
    ) -> Optional[LearningNodeDetail]:
        account = await self._account_state(db, user_id)
        zone = resolve_zone(tz)
        now = utc_now()
        origin_lat, origin_lng = _clean_coordinates(latitude, longitude)
        node: Optional[LearningNode] = None
        event_read: Optional[CommunityEventRead] = None
        can_edit = False

        if kind == LearningNodeKind.EVENT:
            if not node_id.isdigit():
                return None
            event = await self.visible_event(db, account, int(node_id))
            if event is None:
                return None
            counts = await self._attendance_counts(db, [event.id])
            node = self._event_node(event, origin_lat, origin_lng, account, counts, now, zone)
            can_edit = event.organizer_id == user_id
            event_read = self._event_read(event, counts, account)
        elif kind == LearningNodeKind.STUDY_GROUP:
            if not node_id.isdigit():
                return None
            result = await db.execute(
                select(StudyGroup)
                .options(selectinload(StudyGroup.creator), selectinload(StudyGroup.memberships))
                .where(StudyGroup.id == int(node_id))
            )
            group = result.scalar_one_or_none()
            if group is None or (
                group.privacy != StudyGroupPrivacy.PUBLIC
                and group.id not in account.joined_group_ids
                and group.creator_id != user_id
            ):
                return None
            node = self._group_node(group, origin_lat, origin_lng, account)
            can_edit = group.creator_id == user_id
        elif kind == LearningNodeKind.PRIVATE_LESSON:
            if not node_id.isdigit():
                return None
            result = await db.execute(
                select(PrivateLesson)
                .options(selectinload(PrivateLesson.instructor))
                .where(PrivateLesson.id == int(node_id))
            )
            lesson = result.scalar_one_or_none()
            if lesson is None or (not lesson.is_active and lesson.instructor_id != user_id):
                return None
            node = self._lesson_node(lesson, origin_lat, origin_lng, account)
            can_edit = lesson.instructor_id == user_id
        else:
            node = await self._institution_node(db, user_id, node_id)
            if node is None:
                return None
            node.is_saved = node.key in account.saved_keys
            if origin_lat is not None and node.latitude is not None and node.longitude is not None:
                node.distance_km = round(
                    _haversine_km(origin_lat, origin_lng, node.latitude, node.longitude), 2
                )

        related: list[LearningNode] = []
        anchor_lat = node.latitude if node.latitude is not None else origin_lat
        anchor_lng = node.longitude if node.longitude is not None else origin_lng
        if include_related and anchor_lat is not None and anchor_lng is not None:
            try:
                nearby = await self.get_nearby(
                    db,
                    user_id=user_id,
                    latitude=anchor_lat,
                    longitude=anchor_lng,
                    radius_km=5.0,
                    include_online=False,
                    include_institutions=True,
                    limit=24,
                    tz=tz,
                )
                related = [item for item in nearby.items if item.key != node.key][:6]
                # Distances elsewhere mean "from you"; keep that meaning here
                # rather than "from this event" (which would read "Here").
                for item in related:
                    item.distance_km = self._distance(
                        origin_lat, origin_lng, item.latitude, item.longitude
                    )
            except Exception as exc:  # Related items are a bonus, never a failure.
                logger.warning("Related Community items unavailable for %s: %s", node.key, exc)
        return LearningNodeDetail(node=node, related=related, can_edit=can_edit, event=event_read)

    async def visible_event(
        self, db: AsyncSession, account: "_AccountState | int", event_id: int
    ) -> Optional[CommunityEvent]:
        """Load an event the viewer is allowed to open (any lifecycle)."""
        if isinstance(account, int):
            account = await self._account_state(db, account)
        result = await db.execute(
            select(CommunityEvent)
            .options(selectinload(CommunityEvent.organizer))
            .where(
                CommunityEvent.id == event_id,
                self._event_visible_condition(account),
                or_(
                    CommunityEvent.moderation_status != "removed",
                    CommunityEvent.organizer_id == account.user_id,
                ),
                or_(
                    CommunityEvent.moderation_status != "hidden",
                    CommunityEvent.organizer_id == account.user_id,
                    CommunityEvent.id.in_(account.attending_event_ids or [-1]),
                ),
            )
        )
        return result.scalar_one_or_none()

    async def event_node_for_user(
        self,
        db: AsyncSession,
        *,
        user_id: int,
        event_id: int,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        tz: Optional[str] = None,
    ) -> Optional[LearningNode]:
        account = await self._account_state(db, user_id)
        event = await self.visible_event(db, account, event_id)
        if event is None:
            return None
        counts = await self._attendance_counts(db, [event.id])
        origin_lat, origin_lng = _clean_coordinates(latitude, longitude)
        return self._event_node(
            event, origin_lat, origin_lng, account, counts, utc_now(), resolve_zone(tz)
        )

    # ------------------------------------------------------------------
    # Account state
    # ------------------------------------------------------------------

    async def get_my_community(
        self,
        db: AsyncSession,
        user_id: int,
        *,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        tz: Optional[str] = None,
    ) -> CommunityMeResponse:
        """Every section is isolated: one unreadable row never blanks the rest."""
        account = await self._account_state(db, user_id)
        zone = resolve_zone(tz)
        now = utc_now()
        origin_lat, origin_lng = _clean_coordinates(latitude, longitude)

        groups = await self._read_or_default(
            db, "joined groups", lambda: self._joined_groups(db, user_id), []
        )
        joined_groups = self._validated(groups, StudyGroupRead.model_validate, "study group")

        account_events = await self._read_or_default(
            db,
            "account events",
            lambda: self._account_events(db, account, now),
            [],
        )
        counts = await self._read_or_default(
            db,
            "account event counts",
            lambda: self._attendance_counts(db, [event.id for event in account_events]),
            {},
        )
        attending_events = self._validated(
            [
                event
                for event in account_events
                if event.end_time is None or to_naive_utc(event.end_time) >= now
            ],
            lambda event: self._event_read(event, counts, account),
            "event",
        )

        hosting: list[LearningNode] = []
        going: list[LearningNode] = []
        interested: list[LearningNode] = []
        for event in account_events:
            try:
                node = self._event_node(event, origin_lat, origin_lng, account, counts, now, zone)
            except Exception as exc:
                logger.warning("Skipping unreadable account event %s: %s", getattr(event, "id", "?"), exc)
                continue
            if event.organizer_id == user_id:
                hosting.append(node)
            elif node.lifecycle not in {EventLifecycle.PAST, EventLifecycle.CANCELLED}:
                if node.rsvp_status == RSVPStatus.GOING:
                    going.append(node)
                elif node.rsvp_status == RSVPStatus.INTERESTED:
                    interested.append(node)

        following = await self._read_or_default(
            db, "following", lambda: self._following(db, user_id), []
        )
        saved_nodes = await self._read_or_default(
            db,
            "saved nodes",
            lambda: self.get_saved_nodes(
                db, user_id, account=account, latitude=origin_lat, longitude=origin_lng, tz=tz
            ),
            [],
        )
        return CommunityMeResponse(
            joined_groups=joined_groups,
            attending_events=attending_events,
            saved_nodes=saved_nodes,
            following=following,
            updated_at=datetime.utcnow(),
            hosting=hosting,
            going=going,
            interested=interested,
        )

    @staticmethod
    def _validated(rows: Iterable[Any], validate: Callable[[Any], Any], label: str) -> list:
        items = []
        for row in rows:
            try:
                items.append(validate(row))
            except Exception as exc:
                logger.warning("Skipping unreadable Community %s %s: %s", label, getattr(row, "id", "?"), exc)
        return items

    async def _joined_groups(self, db: AsyncSession, user_id: int) -> list[StudyGroup]:
        result = await db.execute(
            select(StudyGroup)
            .join(GroupMembership, GroupMembership.study_group_id == StudyGroup.id)
            .where(
                GroupMembership.user_id == user_id,
                GroupMembership.is_approved.is_(True),
            )
            .order_by(StudyGroup.updated_at.desc())
        )
        return list(result.scalars().all())

    async def _account_events(
        self, db: AsyncSession, account: _AccountState, now: datetime
    ) -> list[CommunityEvent]:
        # Hosted events stay visible for 30 days after they end so the host
        # can still find, review, or delete them from any device.
        history_floor = now - timedelta(days=30)
        result = await db.execute(
            select(CommunityEvent)
            .options(selectinload(CommunityEvent.organizer))
            .where(
                or_(
                    and_(
                        CommunityEvent.organizer_id == account.user_id,
                        CommunityEvent.end_time >= history_floor,
                    ),
                    and_(
                        CommunityEvent.id.in_(account.attending_event_ids or [-1]),
                        CommunityEvent.end_time >= now,
                        CommunityEvent.moderation_status != "removed",
                    ),
                )
            )
            .order_by(CommunityEvent.start_time)
            .limit(200)
        )
        return list(result.scalars().all())

    async def _following(self, db: AsyncSession, user_id: int) -> list[UserPreview]:
        follow_result = await db.execute(
            select(User)
            .join(UserFollow, UserFollow.following_id == User.id)
            .where(UserFollow.follower_id == user_id)
            .order_by(User.first_name, User.last_name, User.username)
        )
        return [preview for user in follow_result.scalars().all() if (preview := _preview(user))]

    def _event_read(
        self,
        event: CommunityEvent,
        counts: dict[int, dict[str, int]],
        account: _AccountState,
    ) -> CommunityEventRead:
        read = CommunityEventRead.model_validate(event)
        event_counts = counts.get(event.id, {})
        attendee_count = event_counts.get("going", 0) + event_counts.get("interested", 0)
        capacity = _positive_capacity(event.max_attendees)
        read.attendee_count = attendee_count
        read.user_attendance_status = account.attendance.get(event.id)
        read.is_full = bool(capacity and event_counts.get("going", 0) >= capacity)
        read.organizer_profile = _preview(event.__dict__.get("organizer"))
        if not (event.organizer_id == account.user_id or event.id in account.attending_event_ids):
            read.meeting_url = None
        return read

    # ------------------------------------------------------------------
    # Saved nodes
    # ------------------------------------------------------------------

    async def save_node(
        self,
        db: AsyncSession,
        *,
        user_id: int,
        kind: LearningNodeKind,
        node_id: str,
        snapshot: LearningNode,
    ) -> LearningNode:
        if snapshot.kind != kind or snapshot.id != node_id:
            raise ValueError("Saved node identity does not match its snapshot")

        # Lyo-owned nodes are saved from the canonical row, never from what a
        # client claims about them; a place is saved as the client saw it.
        canonical: Optional[LearningNode] = None
        if kind != LearningNodeKind.INSTITUTION:
            detail = await self.get_node_detail(
                db, user_id=user_id, kind=kind, node_id=node_id, include_related=False
            )
            if detail is None:
                raise LookupError("This item is no longer available")
            canonical = detail.node
        node = canonical or snapshot

        result = await db.execute(
            select(CommunitySavedNode).where(
                CommunitySavedNode.user_id == user_id,
                CommunitySavedNode.node_kind == kind.value,
                CommunitySavedNode.node_id == node_id,
            )
        )
        saved = result.scalar_one_or_none()
        if saved is None:
            count = await db.scalar(
                select(func.count(CommunitySavedNode.id)).where(
                    CommunitySavedNode.user_id == user_id
                )
            )
            if (count or 0) >= MAX_SAVED_NODES_PER_USER:
                raise ValueError(
                    f"You can save up to {MAX_SAVED_NODES_PER_USER} places and events"
                )
        node.is_saved = True
        # Never turn a private meeting link into a durable snapshot.
        # Authorized members receive links from canonical rows.
        stored_snapshot = node.model_copy(
            update={"meeting_url": None, "distance_km": None, "is_owner": False}
        )
        payload = stored_snapshot.model_dump(mode="json")
        if saved:
            saved.snapshot = payload
            saved.updated_at = datetime.utcnow()
        else:
            saved = CommunitySavedNode(
                user_id=user_id,
                node_kind=kind.value,
                node_id=node_id,
                snapshot=payload,
            )
            db.add(saved)
        await db.commit()
        return node

    async def unsave_node(
        self,
        db: AsyncSession,
        *,
        user_id: int,
        kind: LearningNodeKind,
        node_id: str,
    ) -> bool:
        result = await db.execute(
            select(CommunitySavedNode).where(
                CommunitySavedNode.user_id == user_id,
                CommunitySavedNode.node_kind == kind.value,
                CommunitySavedNode.node_id == node_id,
            )
        )
        saved = result.scalar_one_or_none()
        if saved is None:
            return False
        await db.delete(saved)
        await db.commit()
        return True

    async def get_saved_nodes(
        self,
        db: AsyncSession,
        user_id: int,
        *,
        account: Optional[_AccountState] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        tz: Optional[str] = None,
    ) -> list[LearningNode]:
        """Saved items, refreshed from live rows so every device agrees."""
        account = account or await self._account_state(db, user_id)
        zone = resolve_zone(tz)
        now = utc_now()
        result = await db.execute(
            select(CommunitySavedNode)
            .where(CommunitySavedNode.user_id == user_id)
            .order_by(CommunitySavedNode.updated_at.desc())
        )
        saved_rows = list(result.scalars().all())

        event_ids = [int(row.node_id) for row in saved_rows if row.node_kind == LearningNodeKind.EVENT.value and str(row.node_id).isdigit()]
        live_events: dict[int, CommunityEvent] = {}
        if event_ids:
            event_result = await db.execute(
                select(CommunityEvent)
                .options(selectinload(CommunityEvent.organizer))
                .where(CommunityEvent.id.in_(event_ids), self._event_visible_condition(account))
            )
            live_events = {event.id: event for event in event_result.scalars().all()}
        counts = await self._attendance_counts(db, list(live_events)) if live_events else {}

        nodes: list[LearningNode] = []
        for saved in saved_rows:
            try:
                node: Optional[LearningNode] = None
                if saved.node_kind == LearningNodeKind.EVENT.value and str(saved.node_id).isdigit():
                    event = live_events.get(int(saved.node_id))
                    if event is None:
                        continue  # deleted or no longer visible
                    node = self._event_node(event, latitude, longitude, account, counts, now, zone)
                if node is None:
                    node = LearningNode.model_validate(saved.snapshot)
                    node.is_joined = (
                        node.kind == LearningNodeKind.STUDY_GROUP
                        and node.id.isdigit()
                        and int(node.id) in account.joined_group_ids
                    )
                    node.meeting_url = None
                    node.is_owner = False
                    if latitude is not None and node.latitude is not None and node.longitude is not None:
                        node.distance_km = round(
                            _haversine_km(latitude, longitude, node.latitude, node.longitude), 2
                        )
                    else:
                        node.distance_km = None
                node.is_saved = True
                nodes.append(node)
            except Exception as exc:  # A bad legacy snapshot must not break all account state.
                logger.warning("Skipping invalid saved Community node %s: %s", saved.id, exc)
        return nodes

    # ------------------------------------------------------------------
    # Node builders
    # ------------------------------------------------------------------

    @staticmethod
    def _within_scope(
        node: LearningNode,
        radius_km: float,
        include_online: bool,
        search: "Optional[TopicQuery | str]",
    ) -> bool:
        if (
            node.distance_km is not None
            and node.distance_km > radius_km
            and not (include_online and node.is_online)
        ):
            return False
        if node.distance_km is None and not (include_online and node.is_online):
            return False
        if search:
            topic = parse_topic(search) if isinstance(search, str) else search
            if topic.is_empty:
                return True
            searchable = " ".join(
                value
                for value in [
                    node.title,
                    node.description,
                    node.location_name,
                    node.venue_name,
                    node.organizer_name,
                    node.place_type.replace("_", " ") if node.place_type else None,
                ]
                if value
            )
            if not topic.matches(node.category, searchable):
                return False
        return True

    @staticmethod
    def _distance(
        latitude: Optional[float],
        longitude: Optional[float],
        node_latitude: Optional[float],
        node_longitude: Optional[float],
    ) -> Optional[float]:
        if None in (latitude, longitude, node_latitude, node_longitude):
            return None
        return round(_haversine_km(latitude, longitude, node_latitude, node_longitude), 2)

    @staticmethod
    async def _scalar_rows(db: AsyncSession, statement: Any) -> list[Any]:
        result = await db.execute(statement)
        return list(result.scalars().all())

    @staticmethod
    async def _read_or_default(
        db: AsyncSession,
        source: str,
        operation: Callable[[], Awaitable[ReadResult]],
        default: ReadResult,
    ) -> ReadResult:
        try:
            return await operation()
        except Exception as exc:
            logger.error(
                "Community %s read failed; returning partial data: %s",
                source,
                exc,
                exc_info=True,
            )
            try:
                await db.rollback()
            except Exception as rollback_exc:
                logger.error(
                    "Could not recover Community read transaction: %s",
                    rollback_exc,
                )
            return default

    def _event_node(
        self,
        event: CommunityEvent,
        latitude: Optional[float],
        longitude: Optional[float],
        account: _AccountState,
        counts: dict[int, dict[str, int]],
        now: datetime,
        zone,
    ) -> LearningNode:
        node_id = str(event.id)
        key = f"{LearningNodeKind.EVENT.value}:{node_id}"
        node_latitude, node_longitude = _clean_coordinates(
            event.latitude,
            event.longitude,
        )
        is_owner = getattr(event, "organizer_id", None) == account.user_id
        attendance = account.attendance.get(event.id)
        rsvp = _rsvp_from_attendance(attendance)
        event_counts = counts.get(event.id, {})
        going = event_counts.get("going", 0)
        interested = event_counts.get("interested", 0)
        capacity = _positive_capacity(event.max_attendees)
        price_type = _enum_value(getattr(event, "price_type", None)) or "free"
        venue = _clean_text(getattr(event, "venue_name", None), 200)
        address = _clean_text(getattr(event, "address", None), 500)
        location_name = _clean_text(event.location, 500) or (
            ", ".join(part for part in (venue, address) if part) or None
        )
        mode = _enum_value(getattr(event, "attendance_mode", None))
        return LearningNode(
            key=key,
            kind=LearningNodeKind.EVENT,
            category=_event_category(event.event_type),
            id=node_id,
            title=_clean_text(event.title, 300),
            description=_clean_text(event.description, 4000),
            latitude=node_latitude,
            longitude=node_longitude,
            distance_km=self._distance(latitude, longitude, node_latitude, node_longitude),
            location_name=location_name,
            is_online=bool(event.is_online),
            meeting_url=(
                _clean_text(event.meeting_url, 1000)
                if is_owner or event.id in account.attending_event_ids
                else None
            ),
            starts_at=event.start_time,
            ends_at=event.end_time,
            timezone=_clean_text(event.timezone, 50),
            host=_preview(event.__dict__.get("organizer")),
            attendee_count=going + interested,
            capacity=capacity,
            is_attending=attendance in ACTIVE_ATTENDANCE,
            is_saved=key in account.saved_keys,
            course_id=event.course_id,
            lesson_id=event.lesson_id,
            study_group_id=event.study_group_id,
            image_url=_clean_text(event.image_url, 1000),
            lifecycle=event_lifecycle(event, now, zone),
            rsvp_status=rsvp,
            going_count=going,
            interested_count=interested,
            is_free=price_type != "paid",
            price_amount=getattr(event, "price_amount", None) if price_type == "paid" else None,
            currency=_clean_text(getattr(event, "currency", None), 10) if price_type == "paid" else None,
            organizer_name=_clean_text(getattr(event, "organizer_name", None), 200),
            venue_name=venue,
            address=address,
            attendance_mode=mode if mode in {m.value for m in AttendanceMode} else None,
            visibility=_enum_value(getattr(event, "visibility", None)) or EventVisibility.PUBLIC.value,
            website_url=_clean_text(getattr(event, "website_url", None), 1000),
            is_owner=is_owner,
            is_full=bool(capacity and going >= capacity),
        )

    def _group_node(
        self,
        group: StudyGroup,
        latitude: Optional[float],
        longitude: Optional[float],
        account: _AccountState,
    ) -> LearningNode:
        node_id = str(group.id)
        key = f"{LearningNodeKind.STUDY_GROUP.value}:{node_id}"
        node_latitude, node_longitude = _clean_coordinates(
            group.latitude,
            group.longitude,
        )
        member_count = (
            sum(1 for membership in group.memberships if membership.is_approved)
            if "memberships" in group.__dict__
            else None
        )
        capacity = _positive_capacity(group.max_members)
        is_member = group.id in account.joined_group_ids
        is_owner = group.creator_id == account.user_id
        return LearningNode(
            key=key,
            kind=LearningNodeKind.STUDY_GROUP,
            category=LearningNodeCategory.STUDY_GROUP,
            id=node_id,
            title=_clean_text(group.name, 300),
            description=_clean_text(group.description, 4000),
            latitude=node_latitude,
            longitude=node_longitude,
            distance_km=self._distance(latitude, longitude, node_latitude, node_longitude),
            location_name=_clean_text(group.location, 500),
            is_online=bool(group.is_online),
            meeting_url=(
                _clean_text(group.meeting_url, 1000) if is_member or is_owner else None
            ),
            host=_preview(group.__dict__.get("creator")),
            member_count=member_count,
            capacity=capacity,
            is_joined=is_member,
            is_saved=key in account.saved_keys,
            course_id=group.course_id,
            study_group_id=group.id,
            image_url=_clean_text(group.image_url, 1000),
            is_free=True,
            attendance_mode=(
                AttendanceMode.HYBRID.value
                if group.is_online and node_latitude is not None
                else AttendanceMode.ONLINE.value
                if group.is_online
                else AttendanceMode.IN_PERSON.value
            ),
            is_owner=is_owner,
            is_full=bool(capacity and member_count is not None and member_count >= capacity),
            relevance="Learn alongside peers who share your goals.",
        )

    def _lesson_node(
        self,
        lesson: PrivateLesson,
        latitude: Optional[float],
        longitude: Optional[float],
        account: _AccountState,
    ) -> LearningNode:
        node_id = str(lesson.id)
        key = f"{LearningNodeKind.PRIVATE_LESSON.value}:{node_id}"
        node_latitude, node_longitude = _clean_coordinates(
            lesson.latitude,
            lesson.longitude,
        )
        price = None
        if lesson.price_per_hour is not None:
            try:
                amount = f"{lesson.price_per_hour:g}"
            except (TypeError, ValueError):
                amount = str(lesson.price_per_hour)
            currency = _clean_text(lesson.currency, 20)
            price = f"{currency} {amount}/hour" if currency else f"{amount}/hour"
        description = " · ".join(
            str(value)
            for value in [lesson.subject, price, lesson.description]
            if value
        )
        try:
            hourly = float(lesson.price_per_hour or 0)
        except (TypeError, ValueError):
            hourly = 0.0
        return LearningNode(
            key=key,
            kind=LearningNodeKind.PRIVATE_LESSON,
            category=LearningNodeCategory.TUTOR,
            id=node_id,
            title=_clean_text(lesson.title, 300),
            description=_clean_text(description, 4000),
            latitude=node_latitude,
            longitude=node_longitude,
            distance_km=self._distance(latitude, longitude, node_latitude, node_longitude),
            location_name=_clean_text(lesson.location, 500),
            is_online=bool(lesson.is_online),
            # The public map advertises the lesson; the private meeting link is
            # released through the booking flow, never through discovery.
            meeting_url=None,
            host=_preview(lesson.__dict__.get("instructor")),
            is_saved=key in account.saved_keys,
            image_url=_clean_text(lesson.image_url, 1000),
            is_free=hourly <= 0,
            price_amount=hourly if hourly > 0 else None,
            currency=_clean_text(lesson.currency, 10) if hourly > 0 else None,
            place_type="tutoring",
            is_owner=lesson.instructor_id == account.user_id,
            relevance="One-to-one help from a tutor on Lyo.",
        )

    # ------------------------------------------------------------------
    # Account-state reads
    # ------------------------------------------------------------------

    async def _account_state(self, db: AsyncSession, user_id: int) -> _AccountState:
        # Account state and map sources are intentionally failure-isolated. A
        # drifted legacy table or one temporarily unavailable source must not
        # turn every other source (including public institutions) into a 500.
        saved_keys = await self._read_or_default(
            db, "saved nodes", lambda: self._saved_keys(db, user_id), set()
        )
        joined_group_ids = await self._read_or_default(
            db, "group memberships", lambda: self._joined_group_ids(db, user_id), set()
        )
        attendance = await self._read_or_default(
            db, "event attendance", lambda: self._attendance_statuses(db, user_id), {}
        )
        return _AccountState(user_id, saved_keys, joined_group_ids, attendance)

    async def _saved_keys(self, db: AsyncSession, user_id: int) -> Set[str]:
        result = await db.execute(
            select(CommunitySavedNode.node_kind, CommunitySavedNode.node_id).where(
                CommunitySavedNode.user_id == user_id
            )
        )
        return {f"{kind}:{node_id}" for kind, node_id in result.all()}

    async def _joined_group_ids(self, db: AsyncSession, user_id: int) -> Set[int]:
        result = await db.execute(
            select(GroupMembership.study_group_id).where(
                GroupMembership.user_id == user_id,
                GroupMembership.is_approved.is_(True),
            )
        )
        return set(result.scalars().all())

    async def _attending_event_ids(self, db: AsyncSession, user_id: int) -> Set[int]:
        statuses = await self._attendance_statuses(db, user_id)
        return {event_id for event_id, status in statuses.items() if status in ACTIVE_ATTENDANCE}

    async def _attendance_statuses(
        self, db: AsyncSession, user_id: int
    ) -> dict[int, AttendanceStatus]:
        result = await db.execute(
            select(EventAttendance.event_id, EventAttendance.status).where(
                EventAttendance.user_id == user_id,
            )
        )
        return {event_id: status for event_id, status in result.all()}

    async def _attendance_counts(
        self, db: AsyncSession, event_ids: list[int]
    ) -> dict[int, dict[str, int]]:
        """Going/interested totals for many events in one grouped query."""
        if not event_ids:
            return {}
        result = await db.execute(
            select(EventAttendance.event_id, EventAttendance.status, func.count())
            .where(
                EventAttendance.event_id.in_(event_ids),
                EventAttendance.status.in_(list(ACTIVE_ATTENDANCE)),
            )
            .group_by(EventAttendance.event_id, EventAttendance.status)
        )
        counts: dict[int, dict[str, int]] = {}
        for event_id, status, total in result.all():
            bucket = counts.setdefault(event_id, {"going": 0, "interested": 0})
            if status == AttendanceStatus.MAYBE:
                bucket["interested"] += int(total)
            else:
                bucket["going"] += int(total)
        return counts

    # ------------------------------------------------------------------
    # Public educational places (OpenStreetMap)
    # ------------------------------------------------------------------

    async def _fetch_osm_places(
        self,
        latitude: float,
        longitude: float,
        radius_km: float,
    ) -> tuple[list[LearningNode], bool]:
        """Return (places, provider_ok). A failed lookup is never an error."""
        cache_key = (round(latitude, 3), round(longitude, 3), round(radius_km, 1))
        cached = self._poi_cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < self._poi_cache_ttl_seconds:
            return [node.model_copy(deep=True) for node in cached[1]], True

        endpoint = os.getenv("COMMUNITY_OVERPASS_URL", "https://overpass-api.de/api/interpreter")
        if not endpoint:
            return [], True

        south, north, west, east = _bounds(latitude, longitude, radius_km)
        bbox = f"{south:.6f},{west:.6f},{north:.6f},{east:.6f}"
        overpass_query = f"""
        [out:json][timeout:8];
        (
          nwr[\"amenity\"~\"^(library|college|university|language_school|music_school|prep_school|training|planetarium)$\"]({bbox});
          nwr[\"tourism\"=\"museum\"]({bbox});
          nwr[\"amenity\"=\"community_centre\"][\"community_centre\"~\"education|language|culture|youth\"]({bbox});
        );
        out center tags;
        """
        elements = await self._overpass(endpoint, overpass_query)
        if elements is None:
            stale = self._poi_cache.get(cache_key)
            if stale:  # Serve the last good answer rather than an empty map.
                return [node.model_copy(deep=True) for node in stale[1]], False
            return [], False

        nodes = self._places_from_elements(elements, latitude, longitude)
        # Overpass may return the same feature through overlapping tag clauses.
        deduplicated = list({node.key: node for node in nodes}.values())
        deduplicated.sort(key=lambda node: node.distance_km or float("inf"))
        deduplicated = deduplicated[:120]
        self._poi_cache[cache_key] = (time.monotonic(), deduplicated)
        self._remember_places(deduplicated)
        return [node.model_copy(deep=True) for node in deduplicated], True

    async def _overpass(self, endpoint: str, query: str) -> Optional[list]:
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                response = await client.post(
                    endpoint,
                    data={"data": query},
                    headers={"User-Agent": "LyoLearningAround/1.0 (https://lyoai.app)"},
                )
                response.raise_for_status()
                payload = response.json()
                elements = payload.get("elements", []) if isinstance(payload, dict) else []
                return elements if isinstance(elements, list) else []
        except Exception as exc:  # Nearby Lyo nodes remain available on provider failure.
            logger.warning("Educational place lookup failed: %s", exc)
            return None

    def _places_from_elements(
        self, elements: list, latitude: Optional[float], longitude: Optional[float]
    ) -> list[LearningNode]:
        nodes: list[LearningNode] = []
        for element in elements:
            try:
                node = self._place_node(element, latitude, longitude)
                if node is not None:
                    nodes.append(node)
            except Exception as exc:
                logger.warning(
                    "Skipping invalid educational place %s: %s",
                    element.get("id", "unknown") if isinstance(element, dict) else "unknown",
                    exc,
                )
        return nodes

    def _place_node(
        self, element: Any, latitude: Optional[float], longitude: Optional[float]
    ) -> Optional[LearningNode]:
        if not isinstance(element, dict):
            return None
        tags = element.get("tags") or {}
        center = element.get("center") or {}
        if not isinstance(tags, dict) or not isinstance(center, dict):
            return None
        point_lat = element["lat"] if "lat" in element else center.get("lat")
        point_lng = element["lon"] if "lon" in element else center.get("lon")
        point_lat, point_lng = _clean_coordinates(point_lat, point_lng)
        if point_lat is None or point_lng is None:
            return None
        category = self._place_category(tags)
        name = _clean_text(tags.get("name") or tags.get("operator"), 300)
        if category is None or not name:
            return None
        element_type = _clean_text(element.get("type"), 20) or "node"
        element_id = _clean_text(element.get("id"), 220)
        if not element_id:
            return None
        node_id = f"osm:{element_type}:{element_id}"
        place_type = self._place_type(tags)
        description = _clean_text(tags.get("description"), 4000)
        website = _clean_text(tags.get("website") or tags.get("contact:website") or tags.get("url"), 1000)
        if website and not website.lower().startswith(("http://", "https://")):
            website = f"https://{website}"
        return LearningNode(
            key=f"{LearningNodeKind.INSTITUTION.value}:{node_id}",
            kind=LearningNodeKind.INSTITUTION,
            category=category,
            id=node_id,
            title=name,
            description=description,
            latitude=point_lat,
            longitude=point_lng,
            distance_km=self._distance(latitude, longitude, point_lat, point_lng),
            location_name=self._place_address(tags),
            address=self._place_address(tags),
            source="openstreetmap",
            source_url=f"https://www.openstreetmap.org/{element_type}/{element_id}",
            organizer_name=_clean_text(tags.get("operator"), 200),
            website_url=website,
            phone=_clean_text(tags.get("phone") or tags.get("contact:phone"), 60),
            email=_clean_text(tags.get("email") or tags.get("contact:email"), 200),
            opening_hours=_clean_text(tags.get("opening_hours"), 500),
            place_type=place_type,
            relevance=_PLACE_RELEVANCE.get(place_type or ""),
            is_free=self._place_is_free(tags, category),
        )

    def _remember_places(self, nodes: list[LearningNode]) -> None:
        now = time.monotonic()
        for node in nodes:
            self._place_index[node.key] = (now, node.model_copy(deep=True))
        overflow = len(self._place_index) - self._place_index_limit
        if overflow > 0:
            for key, _ in sorted(self._place_index.items(), key=lambda item: item[1][0])[:overflow]:
                self._place_index.pop(key, None)

    async def _institution_node(
        self, db: AsyncSession, user_id: int, node_id: str
    ) -> Optional[LearningNode]:
        key = f"{LearningNodeKind.INSTITUTION.value}:{node_id}"
        remembered = self._place_index.get(key)
        if remembered:
            return remembered[1].model_copy(deep=True)
        parts = node_id.split(":")
        if len(parts) == 3 and parts[0] == "osm" and parts[1] in {"node", "way", "relation"} and parts[2].isdigit():
            endpoint = os.getenv("COMMUNITY_OVERPASS_URL", "https://overpass-api.de/api/interpreter")
            if endpoint:
                elements = await self._overpass(
                    endpoint, f"[out:json][timeout:8];{parts[1]}({parts[2]});out center tags;"
                )
                for node in self._places_from_elements(elements or [], None, None):
                    if node.key == key:
                        self._remember_places([node])
                        return node
        # Fall back to the learner's own saved copy of the place.
        result = await db.execute(
            select(CommunitySavedNode).where(
                CommunitySavedNode.user_id == user_id,
                CommunitySavedNode.node_kind == LearningNodeKind.INSTITUTION.value,
                CommunitySavedNode.node_id == node_id,
            )
        )
        saved = result.scalar_one_or_none()
        if saved is not None:
            try:
                return LearningNode.model_validate(saved.snapshot)
            except Exception:
                return None
        return None

    @staticmethod
    def _place_type(tags: dict) -> Optional[str]:
        if tags.get("tourism") == "museum":
            return "museum"
        amenity = tags.get("amenity")
        return str(amenity) if amenity else None

    @staticmethod
    def _place_category(tags: dict) -> Optional[LearningNodeCategory]:
        if tags.get("tourism") == "museum" or tags.get("amenity") == "planetarium":
            return LearningNodeCategory.MUSEUM
        if tags.get("amenity") == "library":
            return LearningNodeCategory.LIBRARY
        if tags.get("amenity") in {
            "college",
            "university",
            "language_school",
            "music_school",
            "prep_school",
            "training",
            "community_centre",
        }:
            return LearningNodeCategory.EDUCATIONAL_CENTER
        return None

    @staticmethod
    def _place_is_free(tags: dict, category: LearningNodeCategory) -> Optional[bool]:
        fee = str(tags.get("fee") or "").strip().lower()
        if fee in {"no", "free", "donation"}:
            return True
        if fee == "yes":
            return False
        if category == LearningNodeCategory.LIBRARY:
            return True
        return None

    @staticmethod
    def _place_address(tags: dict) -> Optional[str]:
        street = " ".join(
            str(value)
            for value in [tags.get("addr:housenumber"), tags.get("addr:street")]
            if value
        )
        locality = tags.get("addr:city") or tags.get("addr:town") or tags.get("addr:suburb")
        values = [str(value) for value in [street, locality] if value]
        return _clean_text(", ".join(values), 500)


learning_around_service = LearningAroundService()
