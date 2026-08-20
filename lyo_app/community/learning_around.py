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
from datetime import datetime
from typing import Optional, Set

import httpx
from sqlalchemy import and_, or_, select
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
from lyo_app.community.schemas import (
    CommunityEventRead,
    CommunityMeResponse,
    LearningNode,
    LearningNodeCategory,
    LearningNodeKind,
    NearbyLearningResponse,
    StudyGroupRead,
    UserPreview,
)
from lyo_app.feeds.models import UserFollow

logger = logging.getLogger(__name__)


def _display_name(user: Optional[User]) -> str:
    if user is None:
        return ""
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    return full_name or user.username


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


class LearningAroundService:
    """Builds the shared Learning Around Me view and My Community state."""

    _poi_cache: dict[tuple[float, float, float], tuple[float, list[LearningNode]]] = {}
    _poi_cache_ttl_seconds = 300

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
    ) -> NearbyLearningResponse:
        categories = categories or set(LearningNodeCategory)
        search = query_text.strip().lower() if query_text else None
        south, north, west, east = _bounds(latitude, longitude, radius_km)

        saved_keys = await self._saved_keys(db, user_id)
        joined_group_ids = await self._joined_group_ids(db, user_id)
        attending_event_ids = await self._attending_event_ids(db, user_id)

        items: list[LearningNode] = []

        event_categories = {
            LearningNodeCategory.EVENT,
            LearningNodeCategory.WORKSHOP,
            LearningNodeCategory.CLASS,
        }
        if categories.intersection(event_categories):
            event_location = and_(
                CommunityEvent.latitude.between(south, north),
                CommunityEvent.longitude.between(west, east),
            )
            if include_online:
                event_location = or_(event_location, CommunityEvent.is_online.is_(True))
            result = await db.execute(
                select(CommunityEvent)
                .options(
                    selectinload(CommunityEvent.organizer),
                    selectinload(CommunityEvent.attendances),
                )
                .where(
                    CommunityEvent.status.in_([EventStatus.SCHEDULED, EventStatus.ONGOING]),
                    CommunityEvent.end_time >= datetime.utcnow(),
                    event_location,
                )
                .order_by(CommunityEvent.start_time)
                .limit(max(limit * 2, 100))
            )
            for event in result.scalars().all():
                category = _event_category(event.event_type)
                if category not in categories:
                    continue
                node = self._event_node(
                    event,
                    latitude,
                    longitude,
                    saved_keys,
                    attending_event_ids,
                )
                if self._within_scope(node, radius_km, include_online, search):
                    items.append(node)

        if LearningNodeCategory.STUDY_GROUP in categories:
            group_location = and_(
                StudyGroup.latitude.between(south, north),
                StudyGroup.longitude.between(west, east),
            )
            if include_online:
                group_location = or_(group_location, StudyGroup.is_online.is_(True))
            result = await db.execute(
                select(StudyGroup)
                .options(
                    selectinload(StudyGroup.creator),
                    selectinload(StudyGroup.memberships),
                )
                .where(
                    StudyGroup.status == StudyGroupStatus.ACTIVE,
                    or_(
                        StudyGroup.privacy == StudyGroupPrivacy.PUBLIC,
                        StudyGroup.id.in_(joined_group_ids or [-1]),
                    ),
                    group_location,
                )
                .order_by(StudyGroup.updated_at.desc())
                .limit(max(limit * 2, 100))
            )
            for group in result.scalars().all():
                member_count = sum(1 for membership in group.memberships if membership.is_approved)
                node = self._group_node(
                    group,
                    latitude,
                    longitude,
                    saved_keys,
                    joined_group_ids,
                    member_count,
                )
                if self._within_scope(node, radius_km, include_online, search):
                    items.append(node)

        if LearningNodeCategory.TUTOR in categories:
            lesson_location = and_(
                PrivateLesson.latitude.between(south, north),
                PrivateLesson.longitude.between(west, east),
            )
            if include_online:
                lesson_location = or_(lesson_location, PrivateLesson.is_online.is_(True))
            result = await db.execute(
                select(PrivateLesson)
                .options(selectinload(PrivateLesson.instructor))
                .where(PrivateLesson.is_active.is_(True), lesson_location)
                .order_by(PrivateLesson.updated_at.desc())
                .limit(max(limit * 2, 100))
            )
            for lesson in result.scalars().all():
                node = self._lesson_node(
                    lesson,
                    latitude,
                    longitude,
                    saved_keys,
                )
                if self._within_scope(node, radius_km, include_online, search):
                    items.append(node)

        institution_categories = {
            LearningNodeCategory.LIBRARY,
            LearningNodeCategory.MUSEUM,
            LearningNodeCategory.EDUCATIONAL_CENTER,
        }
        if include_institutions and categories.intersection(institution_categories):
            places = await self._fetch_osm_places(latitude, longitude, radius_km)
            for node in places:
                if node.category not in categories:
                    continue
                node.is_saved = node.key in saved_keys
                if self._within_scope(node, radius_km, False, search):
                    items.append(node)

        items.sort(
            key=lambda item: (
                item.distance_km is None,
                item.distance_km if item.distance_km is not None else float("inf"),
                item.starts_at or datetime.max,
                item.title.lower(),
            )
        )
        return NearbyLearningResponse(
            items=items[:limit],
            center_latitude=latitude,
            center_longitude=longitude,
            radius_km=radius_km,
            fetched_at=datetime.utcnow(),
        )

    async def get_my_community(self, db: AsyncSession, user_id: int) -> CommunityMeResponse:
        joined_result = await db.execute(
            select(StudyGroup)
            .join(GroupMembership, GroupMembership.study_group_id == StudyGroup.id)
            .where(
                GroupMembership.user_id == user_id,
                GroupMembership.is_approved.is_(True),
            )
            .order_by(StudyGroup.updated_at.desc())
        )
        groups = list(joined_result.scalars().all())

        attending_ids = await self._attending_event_ids(db, user_id)
        event_result = await db.execute(
            select(CommunityEvent)
            .where(
                or_(
                    CommunityEvent.organizer_id == user_id,
                    CommunityEvent.id.in_(attending_ids or [-1]),
                ),
                CommunityEvent.end_time >= datetime.utcnow(),
            )
            .order_by(CommunityEvent.start_time)
        )
        events = list(event_result.scalars().all())

        follow_result = await db.execute(
            select(User)
            .join(UserFollow, UserFollow.following_id == User.id)
            .where(UserFollow.follower_id == user_id)
            .order_by(User.first_name, User.last_name, User.username)
        )
        following = [preview for user in follow_result.scalars().all() if (preview := _preview(user))]

        return CommunityMeResponse(
            joined_groups=[StudyGroupRead.model_validate(group) for group in groups],
            attending_events=[CommunityEventRead.model_validate(event) for event in events],
            saved_nodes=await self.get_saved_nodes(db, user_id),
            following=following,
            updated_at=datetime.utcnow(),
        )

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

        result = await db.execute(
            select(CommunitySavedNode).where(
                CommunitySavedNode.user_id == user_id,
                CommunitySavedNode.node_kind == kind.value,
                CommunitySavedNode.node_id == node_id,
            )
        )
        saved = result.scalar_one_or_none()
        snapshot.is_saved = True
        # Never turn a private meeting link into a durable client-provided
        # snapshot. Authorized members receive links from canonical rows.
        stored_snapshot = snapshot.model_copy(update={"meeting_url": None})
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
        return snapshot

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

    async def get_saved_nodes(self, db: AsyncSession, user_id: int) -> list[LearningNode]:
        joined_ids = await self._joined_group_ids(db, user_id)
        attending_ids = await self._attending_event_ids(db, user_id)
        result = await db.execute(
            select(CommunitySavedNode)
            .where(CommunitySavedNode.user_id == user_id)
            .order_by(CommunitySavedNode.updated_at.desc())
        )
        nodes: list[LearningNode] = []
        for saved in result.scalars().all():
            try:
                node = LearningNode.model_validate(saved.snapshot)
                node.is_saved = True
                node.is_joined = (
                    node.kind == LearningNodeKind.STUDY_GROUP
                    and node.id.isdigit()
                    and int(node.id) in joined_ids
                )
                node.is_attending = (
                    node.kind == LearningNodeKind.EVENT
                    and node.id.isdigit()
                    and int(node.id) in attending_ids
                )
                node.meeting_url = None
                nodes.append(node)
            except Exception as exc:  # A bad legacy snapshot must not break all account state.
                logger.warning("Skipping invalid saved Community node %s: %s", saved.id, exc)
        return nodes

    @staticmethod
    def _within_scope(
        node: LearningNode,
        radius_km: float,
        include_online: bool,
        search: Optional[str],
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
            searchable = " ".join(
                value for value in [node.title, node.description, node.location_name] if value
            ).lower()
            if search not in searchable:
                return False
        return True

    @staticmethod
    def _distance(
        latitude: float,
        longitude: float,
        node_latitude: Optional[float],
        node_longitude: Optional[float],
    ) -> Optional[float]:
        if node_latitude is None or node_longitude is None:
            return None
        return round(_haversine_km(latitude, longitude, node_latitude, node_longitude), 2)

    def _event_node(
        self,
        event: CommunityEvent,
        latitude: float,
        longitude: float,
        saved_keys: Set[str],
        attending_ids: Set[int],
    ) -> LearningNode:
        node_id = str(event.id)
        key = f"{LearningNodeKind.EVENT.value}:{node_id}"
        return LearningNode(
            key=key,
            kind=LearningNodeKind.EVENT,
            category=_event_category(event.event_type),
            id=node_id,
            title=event.title,
            description=event.description,
            latitude=event.latitude,
            longitude=event.longitude,
            distance_km=self._distance(latitude, longitude, event.latitude, event.longitude),
            location_name=event.location,
            is_online=event.is_online,
            meeting_url=event.meeting_url if event.id in attending_ids else None,
            starts_at=event.start_time,
            ends_at=event.end_time,
            timezone=event.timezone,
            host=_preview(event.organizer),
            attendee_count=(
                sum(
                    1
                    for attendance in event.attendances
                    if attendance.status
                    in {
                        AttendanceStatus.GOING,
                        AttendanceStatus.MAYBE,
                        AttendanceStatus.ATTENDED,
                    }
                )
                if "attendances" in event.__dict__
                else None
            ),
            capacity=event.max_attendees,
            is_attending=event.id in attending_ids,
            is_saved=key in saved_keys,
            course_id=event.course_id,
            lesson_id=event.lesson_id,
            study_group_id=event.study_group_id,
            image_url=event.image_url,
        )

    def _group_node(
        self,
        group: StudyGroup,
        latitude: float,
        longitude: float,
        saved_keys: Set[str],
        joined_ids: Set[int],
        member_count: int,
    ) -> LearningNode:
        node_id = str(group.id)
        key = f"{LearningNodeKind.STUDY_GROUP.value}:{node_id}"
        return LearningNode(
            key=key,
            kind=LearningNodeKind.STUDY_GROUP,
            category=LearningNodeCategory.STUDY_GROUP,
            id=node_id,
            title=group.name,
            description=group.description,
            latitude=group.latitude,
            longitude=group.longitude,
            distance_km=self._distance(latitude, longitude, group.latitude, group.longitude),
            location_name=group.location,
            is_online=group.is_online,
            meeting_url=group.meeting_url if group.id in joined_ids else None,
            host=_preview(group.creator),
            member_count=member_count,
            capacity=group.max_members,
            is_joined=group.id in joined_ids,
            is_saved=key in saved_keys,
            course_id=group.course_id,
            study_group_id=group.id,
            image_url=group.image_url,
        )

    def _lesson_node(
        self,
        lesson: PrivateLesson,
        latitude: float,
        longitude: float,
        saved_keys: Set[str],
    ) -> LearningNode:
        node_id = str(lesson.id)
        key = f"{LearningNodeKind.PRIVATE_LESSON.value}:{node_id}"
        price = f"{lesson.currency} {lesson.price_per_hour:g}/hour"
        description = " · ".join(value for value in [lesson.subject, price, lesson.description] if value)
        return LearningNode(
            key=key,
            kind=LearningNodeKind.PRIVATE_LESSON,
            category=LearningNodeCategory.TUTOR,
            id=node_id,
            title=lesson.title,
            description=description,
            latitude=lesson.latitude,
            longitude=lesson.longitude,
            distance_km=self._distance(latitude, longitude, lesson.latitude, lesson.longitude),
            location_name=lesson.location,
            is_online=lesson.is_online,
            # The public map advertises the lesson; the private meeting link is
            # released through the booking flow, never through discovery.
            meeting_url=None,
            host=_preview(lesson.instructor),
            is_saved=key in saved_keys,
            image_url=lesson.image_url,
        )

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
        result = await db.execute(
            select(EventAttendance.event_id).where(
                EventAttendance.user_id == user_id,
                EventAttendance.status.in_(
                    [AttendanceStatus.GOING, AttendanceStatus.MAYBE, AttendanceStatus.ATTENDED]
                ),
            )
        )
        return set(result.scalars().all())

    async def _fetch_osm_places(
        self,
        latitude: float,
        longitude: float,
        radius_km: float,
    ) -> list[LearningNode]:
        cache_key = (round(latitude, 3), round(longitude, 3), round(radius_km, 1))
        cached = self._poi_cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < self._poi_cache_ttl_seconds:
            return [node.model_copy(deep=True) for node in cached[1]]

        endpoint = os.getenv("COMMUNITY_OVERPASS_URL", "https://overpass-api.de/api/interpreter")
        if not endpoint:
            return []

        south, north, west, east = _bounds(latitude, longitude, radius_km)
        bbox = f"{south:.6f},{west:.6f},{north:.6f},{east:.6f}"
        overpass_query = f"""
        [out:json][timeout:8];
        (
          nwr[\"amenity\"~\"^(library|college|university|school|language_school|music_school)$\"]({bbox});
          nwr[\"tourism\"=\"museum\"]({bbox});
          nwr[\"amenity\"=\"community_centre\"][\"community_centre\"~\"education|language|culture\"]({bbox});
        );
        out center tags;
        """
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                response = await client.post(
                    endpoint,
                    data={"data": overpass_query},
                    headers={"User-Agent": "LyoLearningAround/1.0 (https://lyoai.app)"},
                )
                response.raise_for_status()
                elements = response.json().get("elements", [])
        except Exception as exc:  # Nearby Lyo nodes remain available on provider failure.
            logger.warning("Educational place lookup failed: %s", exc)
            return []

        nodes: list[LearningNode] = []
        for element in elements:
            tags = element.get("tags") or {}
            center = element.get("center") or {}
            point_lat = element["lat"] if "lat" in element else center.get("lat")
            point_lng = element["lon"] if "lon" in element else center.get("lon")
            if point_lat is None or point_lng is None:
                continue
            category = self._place_category(tags)
            name = tags.get("name") or tags.get("operator")
            if category is None or not name:
                continue
            node_id = f"osm:{element.get('type', 'node')}:{element.get('id')}"
            address = self._place_address(tags)
            description = tags.get("description") or tags.get("operator")
            nodes.append(
                LearningNode(
                    key=f"{LearningNodeKind.INSTITUTION.value}:{node_id}",
                    kind=LearningNodeKind.INSTITUTION,
                    category=category,
                    id=node_id,
                    title=name,
                    description=description,
                    latitude=float(point_lat),
                    longitude=float(point_lng),
                    distance_km=round(
                        _haversine_km(latitude, longitude, float(point_lat), float(point_lng)),
                        2,
                    ),
                    location_name=address,
                    source="openstreetmap",
                    source_url=(
                        f"https://www.openstreetmap.org/{element.get('type', 'node')}/"
                        f"{element.get('id')}"
                    ),
                )
            )

        # Overpass may return the same feature through overlapping tag clauses.
        deduplicated = list({node.key: node for node in nodes}.values())
        deduplicated.sort(key=lambda node: node.distance_km or float("inf"))
        deduplicated = deduplicated[:100]
        self._poi_cache[cache_key] = (time.monotonic(), deduplicated)
        return [node.model_copy(deep=True) for node in deduplicated]

    @staticmethod
    def _place_category(tags: dict) -> Optional[LearningNodeCategory]:
        if tags.get("tourism") == "museum":
            return LearningNodeCategory.MUSEUM
        if tags.get("amenity") == "library":
            return LearningNodeCategory.LIBRARY
        if tags.get("amenity") in {
            "college",
            "university",
            "school",
            "language_school",
            "music_school",
            "community_centre",
        }:
            return LearningNodeCategory.EDUCATIONAL_CENTER
        return None

    @staticmethod
    def _place_address(tags: dict) -> Optional[str]:
        street = " ".join(
            value for value in [tags.get("addr:housenumber"), tags.get("addr:street")] if value
        )
        locality = tags.get("addr:city") or tags.get("addr:town") or tags.get("addr:suburb")
        values = [value for value in [street, locality] if value]
        return ", ".join(values) or None


learning_around_service = LearningAroundService()
