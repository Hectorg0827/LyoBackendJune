"""Invitations to Community events: shareable links, direct invites, guests.

A private event is visible only to its host, the people who RSVP'd, members
of a linked study group, and its guests. Hosts add guests two ways:

* an invite link (``/community/invite/<token>``) anyone signed in can accept,
  optionally limited by uses and expiry, and revocable at any time; or
* a direct invite to one Lyo member, which also notifies them.

The token is the secret in the link: 256 random bits from ``secrets``. Links
are only ever listed to the event's host.
"""

from __future__ import annotations

import logging
import os
import secrets
from datetime import timedelta
from typing import Optional

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from lyo_app.auth.models import User
from lyo_app.community.models import (
    AttendanceStatus,
    CommunityEvent,
    CommunityEventGuest,
    CommunityEventInvite,
    EventAttendance,
    EventStatus,
)
from lyo_app.community.schemas import (
    AttendanceMode,
    EventGuestRead,
    EventInviteCreate,
    EventInviteRead,
    EventInvitesResponse,
    EventVisibility,
    InvitePreview,
    RSVPStatus,
    UserPreview,
)
from lyo_app.community.service import CommunityConflict, CommunityRateLimited
from lyo_app.community.timeutil import to_naive_utc, utc_now

logger = logging.getLogger(__name__)

ACTIVE_LINKS_PER_EVENT = 20
DIRECT_INVITES_PER_DAY = 200
GUESTS_PER_EVENT = 2000


class InviteNotFound(Exception):
    """No such event, link, or guest (or the caller may not know it exists)."""


class NotEventHost(Exception):
    """Only the event's host may manage its invitations."""


def web_base_url() -> str:
    return os.getenv("COMMUNITY_WEB_URL", "https://lyoai.app").rstrip("/")


def invite_url(token: str) -> str:
    return f"{web_base_url()}/community/invite/{token}"


def _display_name(user: Optional[User]) -> str:
    if user is None:
        return "Lyo learner"
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    return full_name or user.username or "Lyo learner"


def _preview(user: Optional[User]) -> Optional[UserPreview]:
    if user is None:
        return None
    return UserPreview(id=user.id, name=_display_name(user), avatar=user.avatar_url)


def _link_state(invite: CommunityEventInvite, now) -> str:
    if invite.revoked_at is not None:
        return "revoked"
    if invite.expires_at is not None and to_naive_utc(invite.expires_at) <= now:
        return "expired"
    if invite.max_uses is not None and (invite.use_count or 0) >= invite.max_uses:
        return "used_up"
    return "valid"


def _event_state(event: CommunityEvent, now) -> Optional[str]:
    status = getattr(event.status, "value", event.status)
    if status == EventStatus.CANCELLED.value:
        return "cancelled"
    if event.end_time is not None and to_naive_utc(event.end_time) < now:
        return "ended"
    return None


def _invite_read(invite: CommunityEventInvite, now) -> EventInviteRead:
    return EventInviteRead(
        id=invite.id,
        token=invite.token,
        url=invite_url(invite.token),
        created_at=invite.created_at,
        expires_at=invite.expires_at,
        max_uses=invite.max_uses,
        use_count=invite.use_count or 0,
        active=_link_state(invite, now) == "valid",
    )


class InviteService:
    async def _hosted_event(self, db: AsyncSession, event_id: int, host_id: int) -> CommunityEvent:
        event = await db.get(CommunityEvent, event_id)
        if event is None or getattr(event, "moderation_status", "active") == "removed":
            raise InviteNotFound("Event not found")
        if event.organizer_id != host_id:
            raise NotEventHost("Only the host can manage invitations for this event.")
        return event

    async def _invite_by_token(self, db: AsyncSession, token: str) -> CommunityEventInvite:
        if not token or len(token) > 64:
            raise InviteNotFound("This invite link isn't valid.")
        result = await db.execute(
            select(CommunityEventInvite).where(CommunityEventInvite.token == token)
        )
        invite = result.scalar_one_or_none()
        if invite is None:
            raise InviteNotFound("This invite link isn't valid.")
        return invite

    # -- Host: links -------------------------------------------------------

    async def create_link(
        self, db: AsyncSession, *, event_id: int, host_id: int, options: EventInviteCreate
    ) -> EventInviteRead:
        event = await self._hosted_event(db, event_id, host_id)
        now = utc_now()
        if _event_state(event, now) is not None:
            raise CommunityConflict("This event has ended or was cancelled, so it can't take new guests.")
        links = await db.execute(
            select(CommunityEventInvite).where(CommunityEventInvite.event_id == event_id)
        )
        active = [link for link in links.scalars().all() if _link_state(link, now) == "valid"]
        if len(active) >= ACTIVE_LINKS_PER_EVENT:
            raise CommunityConflict(
                "This event already has a lot of active invite links. Turn one off before making another."
            )
        expires_at = None
        if options.expires_in_days:
            expires_at = now + timedelta(days=options.expires_in_days)
            event_end = to_naive_utc(event.end_time) if event.end_time is not None else None
            if event_end is not None and expires_at > event_end:
                expires_at = event_end
        invite = CommunityEventInvite(
            event_id=event_id,
            token=secrets.token_urlsafe(32),
            created_by_id=host_id,
            max_uses=options.max_uses,
            use_count=0,
            expires_at=expires_at,
            created_at=now,
        )
        db.add(invite)
        await db.commit()
        await db.refresh(invite)
        return _invite_read(invite, now)

    async def list_invitations(
        self, db: AsyncSession, *, event_id: int, host_id: int
    ) -> EventInvitesResponse:
        await self._hosted_event(db, event_id, host_id)
        now = utc_now()
        links = await db.execute(
            select(CommunityEventInvite)
            .where(CommunityEventInvite.event_id == event_id)
            .order_by(CommunityEventInvite.created_at.desc())
        )
        guests = await db.execute(
            select(CommunityEventGuest)
            .options(selectinload(CommunityEventGuest.user))
            .where(CommunityEventGuest.event_id == event_id)
            .order_by(CommunityEventGuest.created_at.desc())
        )
        guest_rows = [row for row in guests.scalars().all() if row.user is not None]
        statuses: dict[int, str] = {}
        if guest_rows:
            attendance = await db.execute(
                select(EventAttendance.user_id, EventAttendance.status).where(
                    EventAttendance.event_id == event_id,
                    EventAttendance.user_id.in_([row.user_id for row in guest_rows]),
                )
            )
            for user_id, status in attendance.all():
                value = getattr(status, "value", status)
                if value in {AttendanceStatus.GOING.value, AttendanceStatus.ATTENDED.value}:
                    statuses[user_id] = RSVPStatus.GOING.value
                elif value == AttendanceStatus.MAYBE.value:
                    statuses[user_id] = RSVPStatus.INTERESTED.value
        return EventInvitesResponse(
            links=[_invite_read(link, now) for link in links.scalars().all()],
            guests=[
                EventGuestRead(
                    user=_preview(row.user),
                    source="direct" if row.source == "direct" else "link",
                    invited_at=row.created_at,
                    rsvp_status=statuses.get(row.user_id),
                )
                for row in guest_rows
            ],
        )

    async def revoke_link(
        self, db: AsyncSession, *, event_id: int, host_id: int, invite_id: int
    ) -> None:
        await self._hosted_event(db, event_id, host_id)
        invite = await db.get(CommunityEventInvite, invite_id)
        if invite is None or invite.event_id != event_id:
            raise InviteNotFound("Invite link not found")
        if invite.revoked_at is None:
            invite.revoked_at = utc_now()
            await db.commit()

    # -- Host: guests ------------------------------------------------------

    async def invite_member(
        self, db: AsyncSession, *, event_id: int, host_id: int, user_id: int
    ) -> tuple[EventGuestRead, bool]:
        """Add one Lyo member to the guest list. Returns (guest, newly_added)."""
        event = await self._hosted_event(db, event_id, host_id)
        now = utc_now()
        if user_id == host_id:
            raise CommunityConflict("You're the host, so you're already in.")
        if _event_state(event, now) is not None:
            raise CommunityConflict("This event has ended or was cancelled, so it can't take new guests.")
        user = await db.get(User, user_id)
        if user is None or not getattr(user, "is_active", True):
            raise InviteNotFound("We couldn't find that Lyo member.")
        existing = await db.execute(
            select(CommunityEventGuest).where(
                CommunityEventGuest.event_id == event_id,
                CommunityEventGuest.user_id == user_id,
            )
        )
        guest = existing.scalar_one_or_none()
        added = guest is None
        if added:
            recent = await db.execute(
                select(func.count(CommunityEventGuest.id)).where(
                    CommunityEventGuest.invited_by_id == host_id,
                    CommunityEventGuest.source == "direct",
                    CommunityEventGuest.created_at >= now - timedelta(days=1),
                )
            )
            if (recent.scalar() or 0) >= DIRECT_INVITES_PER_DAY:
                raise CommunityRateLimited(
                    "You've sent a lot of invitations today. Please try again tomorrow.", 3600
                )
            await self._ensure_room(db, event_id)
            guest = CommunityEventGuest(
                event_id=event_id,
                user_id=user_id,
                invited_by_id=host_id,
                source="direct",
                created_at=now,
            )
            db.add(guest)
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
                raise CommunityConflict("That person is already on the guest list.")
            await db.refresh(guest)
        return (
            EventGuestRead(
                user=_preview(user),
                source="direct" if guest.source == "direct" else "link",
                invited_at=guest.created_at,
            ),
            added,
        )

    async def remove_guest(
        self, db: AsyncSession, *, event_id: int, host_id: int, user_id: int
    ) -> None:
        """Take someone off the guest list, including their RSVP to a private event."""
        event = await self._hosted_event(db, event_id, host_id)
        result = await db.execute(
            delete(CommunityEventGuest).where(
                CommunityEventGuest.event_id == event_id,
                CommunityEventGuest.user_id == user_id,
            )
        )
        removed = (result.rowcount or 0) > 0
        if getattr(event, "visibility", "public") == EventVisibility.PRIVATE.value:
            # An RSVP would otherwise keep a private event visible to them.
            await db.execute(
                delete(EventAttendance).where(
                    EventAttendance.event_id == event_id,
                    EventAttendance.user_id == user_id,
                )
            )
        await db.commit()
        if not removed:
            raise InviteNotFound("That person isn't on the guest list.")

    async def _ensure_room(self, db: AsyncSession, event_id: int) -> None:
        count = await db.execute(
            select(func.count(CommunityEventGuest.id)).where(CommunityEventGuest.event_id == event_id)
        )
        if (count.scalar() or 0) >= GUESTS_PER_EVENT:
            raise CommunityConflict("This event's guest list is full.")

    # -- Guest: links ------------------------------------------------------

    async def preview(self, db: AsyncSession, *, token: str, user_id: int) -> InvitePreview:
        invite = await self._invite_by_token(db, token)
        result = await db.execute(
            select(CommunityEvent)
            .options(selectinload(CommunityEvent.organizer))
            .where(CommunityEvent.id == invite.event_id)
        )
        event = result.scalar_one_or_none()
        if event is None or getattr(event, "moderation_status", "active") == "removed":
            raise InviteNotFound("This invite link isn't valid.")
        now = utc_now()
        guest = await db.execute(
            select(CommunityEventGuest.id).where(
                CommunityEventGuest.event_id == event.id,
                CommunityEventGuest.user_id == user_id,
            )
        )
        state = _event_state(event, now) or _link_state(invite, now)
        mode = getattr(event, "attendance_mode", None)
        visibility = getattr(event, "visibility", None)
        return InvitePreview(
            status=state,
            already_guest=guest.scalar_one_or_none() is not None,
            is_host=event.organizer_id == user_id,
            event_id=event.id,
            title=event.title,
            starts_at=event.start_time,
            ends_at=event.end_time,
            timezone=event.timezone,
            location_name=None if mode == AttendanceMode.ONLINE.value else (event.venue_name or event.location),
            attendance_mode=mode if mode in {m.value for m in AttendanceMode} else None,
            visibility=visibility if visibility in {v.value for v in EventVisibility} else None,
            host=_preview(event.organizer),
            organizer_name=getattr(event, "organizer_name", None),
            image_url=getattr(event, "image_url", None),
        )

    async def accept(self, db: AsyncSession, *, token: str, user_id: int) -> int:
        """Put the caller on the guest list. Safe to repeat; returns the event id."""
        invite = await self._invite_by_token(db, token)
        event = await db.get(CommunityEvent, invite.event_id)
        if event is None or getattr(event, "moderation_status", "active") == "removed":
            raise InviteNotFound("This invite link isn't valid.")
        if event.organizer_id == user_id:
            return event.id
        existing = await db.execute(
            select(CommunityEventGuest.id).where(
                CommunityEventGuest.event_id == event.id,
                CommunityEventGuest.user_id == user_id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            return event.id
        now = utc_now()
        state = _event_state(event, now) or _link_state(invite, now)
        messages = {
            "revoked": "The host turned off this invite link. Ask them for a new one.",
            "expired": "This invite link has expired. Ask the host for a new one.",
            "used_up": "This invite link has been used as many times as the host allowed.",
            "ended": "This event has already ended.",
            "cancelled": "This event was cancelled by the host.",
        }
        if state != "valid":
            raise CommunityConflict(messages[state])
        await self._ensure_room(db, event.id)
        # Count the use atomically so two people accepting at once can never
        # take a single-use link past its limit.
        claimed = await db.execute(
            update(CommunityEventInvite)
            .where(
                CommunityEventInvite.id == invite.id,
                CommunityEventInvite.revoked_at.is_(None),
                or_(
                    CommunityEventInvite.max_uses.is_(None),
                    CommunityEventInvite.use_count < CommunityEventInvite.max_uses,
                ),
            )
            .values(use_count=CommunityEventInvite.use_count + 1)
            .execution_options(synchronize_session=False)
        )
        if (claimed.rowcount or 0) == 0:
            await db.rollback()
            raise CommunityConflict(messages["used_up"])
        db.add(
            CommunityEventGuest(
                event_id=event.id,
                user_id=user_id,
                invited_by_id=invite.created_by_id,
                invite_id=invite.id,
                source="link",
                created_at=now,
            )
        )
        try:
            await db.commit()
        except IntegrityError:
            # Accepted on another device at the same moment: already a guest.
            await db.rollback()
        return event.id


invite_service = InviteService()
