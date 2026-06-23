"""
Notifications Router - Push notification management endpoints
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from typing import Optional, List

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.auth.jwt_auth import get_current_user
from lyo_app.auth.models import User
from lyo_app.core.database import get_db, Base

router = APIRouter(prefix="/notifications", tags=["Notifications"])


# ── SQLAlchemy Model ──────────────────────────────────────────────────────────

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type = Column(String(50), nullable=False)  # like, comment, follow, achievement, mention, system, course_complete, event_reminder, group_invite
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=False)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    target_id = Column(String(100), nullable=True)
    target_type = Column(String(50), nullable=True)
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class NotificationPreferences(BaseModel):
    """User notification preferences."""
    push_enabled: bool = True
    email_enabled: bool = True
    streak_reminders: bool = True
    learning_tips: bool = True
    quiet_hours_start: Optional[int] = 22  # 10 PM
    quiet_hours_end: Optional[int] = 8     # 8 AM


class NotificationOut(BaseModel):
    id: int
    type: str
    title: str
    body: str
    actor_id: Optional[int] = None
    actor_display_name: Optional[str] = None
    actor_username: Optional[str] = None
    actor_avatar_url: Optional[str] = None
    target_id: Optional[str] = None
    target_type: Optional[str] = None
    is_read: bool
    created_at: str


# ── Notification List Endpoint ────────────────────────────────────────────────

@router.get("")
async def list_notifications(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    type: Optional[str] = Query(None, description="Filter by notification type"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List user's notifications with optional type filter, paginated."""
    # Alias for actor user join
    from sqlalchemy.orm import aliased
    ActorUser = aliased(User)

    # Build base query with actor join
    base_q = (
        select(
            Notification,
            ActorUser.first_name.label("actor_first_name"),
            ActorUser.last_name.label("actor_last_name"),
            ActorUser.username.label("actor_username"),
            ActorUser.avatar_url.label("actor_avatar_url"),
        )
        .outerjoin(ActorUser, Notification.actor_id == ActorUser.id)
        .where(Notification.user_id == current_user.id)
    )

    if type:
        base_q = base_q.where(Notification.type == type)

    # Total count
    count_q = select(func.count()).select_from(Notification).where(Notification.user_id == current_user.id)
    if type:
        count_q = count_q.where(Notification.type == type)
    total_result = await db.execute(count_q)
    total = total_result.scalar() or 0

    # Unread count (always unfiltered)
    unread_q = (
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == current_user.id, Notification.is_read == False)  # noqa: E712
    )
    unread_result = await db.execute(unread_q)
    unread_count = unread_result.scalar() or 0

    # Paginated results
    offset = (page - 1) * per_page
    data_q = base_q.order_by(desc(Notification.created_at)).offset(offset).limit(per_page)
    result = await db.execute(data_q)
    rows = result.all()

    notifications = []
    for row in rows:
        notif = row[0]  # Notification object
        actor_first = row[1] or ""
        actor_last = row[2] or ""
        actor_uname = row[3]
        actor_avatar = row[4]
        actor_display = " ".join(filter(None, [actor_first, actor_last])) or actor_uname or None

        notifications.append(NotificationOut(
            id=notif.id,
            type=notif.type,
            title=notif.title,
            body=notif.body,
            actor_id=notif.actor_id,
            actor_display_name=actor_display,
            actor_username=actor_uname,
            actor_avatar_url=actor_avatar,
            target_id=notif.target_id,
            target_type=notif.target_type,
            is_read=notif.is_read,
            created_at=notif.created_at.isoformat() if notif.created_at else "",
        ).model_dump())

    return {"notifications": notifications, "total": total, "unread_count": unread_count}


# ── Mark Single Notification Read ─────────────────────────────────────────────

@router.post("/{notification_id}/read")
async def mark_notification_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a single notification as read."""
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")

    notif.is_read = True
    await db.commit()
    return {"status": "ok", "notification_id": notification_id}


# ── Mark All Notifications Read ───────────────────────────────────────────────

@router.post("/read-all")
async def mark_all_notifications_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark all of the user's notifications as read."""
    from sqlalchemy import update

    await db.execute(
        update(Notification)
        .where(Notification.user_id == current_user.id, Notification.is_read == False)  # noqa: E712
        .values(is_read=True)
    )
    await db.commit()
    return {"status": "ok"}


# ── Unread Count ──────────────────────────────────────────────────────────────

@router.get("/unread-count")
async def get_unread_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the number of unread notifications."""
    result = await db.execute(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == current_user.id, Notification.is_read == False)  # noqa: E712
    )
    count = result.scalar() or 0
    return {"count": count}


# ── Preferences ───────────────────────────────────────────────────────────────

@router.get("/preferences")
async def get_notification_preferences(
    current_user: User = Depends(get_current_user),
):
    """Get user's notification preferences."""
    return NotificationPreferences()


@router.put("/preferences")
async def update_notification_preferences(
    preferences: NotificationPreferences,
    current_user: User = Depends(get_current_user),
):
    """Update user's notification preferences."""
    return {"status": "updated", "preferences": preferences}


# ── Legacy History Endpoint ───────────────────────────────────────────────────

@router.get("/history")
async def get_notification_history(
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get user's notification history (legacy endpoint, prefer GET /notifications)."""
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(desc(Notification.created_at))
        .limit(limit)
    )
    rows = result.scalars().all()
    return {
        "notifications": [
            {
                "id": n.id,
                "type": n.type,
                "title": n.title,
                "body": n.body,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat() if n.created_at else "",
            }
            for n in rows
        ],
        "total": len(rows),
    }


# ── Device Registration ──────────────────────────────────────────────────────

@router.post("/register-device")
async def register_device(
    device_token: str,
    platform: str,
    current_user: User = Depends(get_current_user),
):
    """Register a device for push notifications."""
    return {"status": "registered", "device_token": device_token[:10] + "..."}


@router.delete("/unregister-device")
async def unregister_device(
    device_token: str,
    current_user: User = Depends(get_current_user),
):
    """Unregister a device from push notifications."""
    return {"status": "unregistered"}
