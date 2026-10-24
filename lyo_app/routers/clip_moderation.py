"""Moderators' review of Discover clips.

Learners report clips (POST /api/v1/clips/{id}/report), and three different
reporters hide one until a moderator decides. Here a moderator lists the
reported clips, every clip, or the removed ones, and decides:

- keep: the pending reports are dismissed and the clip is served again;
- remove: the clip leaves Discover for everyone but its owner, its pending
  reports are resolved, and its video and poster move out of public storage,
  so their URLs stop working;
- restore: a removed clip's media moves back and it is served again.

A moderator is a superuser, or a learner whose email is listed in the API's
DISCOVER_MODERATOR_EMAILS setting (comma-separated). List only emails of
accounts that already exist: emails are unique, so nobody else can then
sign up with one and inherit the role.
"""
import logging
import os
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import String, cast, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.concurrency import run_in_threadpool

from lyo_app.auth.jwt_auth import get_current_user
from lyo_app.auth.models import User
from lyo_app.community.models import ContentReport, ReportStatus, ReportTargetType
from lyo_app.core.database import get_async_session
from lyo_app.models.clips import Clip, MODERATION_ACTIVE, MODERATION_HIDDEN, MODERATION_REMOVED
from lyo_app.routers import user_media
from lyo_app.routers.clip_media_storage import set_media_removed
from lyo_app.routers.clips import _clip_author_display_name, _search_clips, _unshared_media

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/moderation", tags=["Moderation"])

# Which states each decision applies to.
DECIDABLE = {
    "keep": {MODERATION_ACTIVE, MODERATION_HIDDEN},
    "remove": {MODERATION_ACTIVE, MODERATION_HIDDEN},
    "restore": {MODERATION_REMOVED},
}
NOTES_SHOWN = 5


def is_moderator(user) -> bool:
    if getattr(user, "is_superuser", False):
        return True
    email = (getattr(user, "email", None) or "").strip().lower()
    listed = {e.strip().lower() for e in os.getenv("DISCOVER_MODERATOR_EMAILS", "").split(",") if e.strip()}
    return bool(email) and email in listed


async def require_moderator(current_user: User = Depends(get_current_user)) -> User:
    if not is_moderator(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only moderators can do this")
    return current_user


class ClipDecision(BaseModel):
    action: Literal["keep", "remove", "restore"]
    note: Optional[str] = Field(None, max_length=500)


@router.get("/me")
async def moderation_me(current_user: User = Depends(get_current_user)):
    """Whether the signed-in learner may use the moderator page."""
    return {"moderator": is_moderator(current_user)}


def _clip_key():
    return cast(Clip.id, String)


async def _report_summaries(db: AsyncSession, clip_ids: list) -> dict:
    """Per clip: pending and total reports, pending reasons, latest notes."""
    if not clip_ids:
        return {}
    rows = (await db.execute(
        select(ContentReport.target_id, ContentReport.reason, ContentReport.status,
               ContentReport.description, ContentReport.created_at)
        .where(ContentReport.target_type == ReportTargetType.CLIP,
               ContentReport.target_id.in_([str(i) for i in clip_ids]))
        .order_by(desc(ContentReport.created_at))
    )).all()
    summaries = {}
    for row in rows:
        summary = summaries.setdefault(int(row.target_id), {"pending": 0, "total": 0, "reasons": {}, "notes": []})
        summary["total"] += 1
        if row.status != ReportStatus.PENDING:
            continue
        summary["pending"] += 1
        reason = getattr(row.reason, "value", row.reason)
        summary["reasons"][reason] = summary["reasons"].get(reason, 0) + 1
        if row.description and len(summary["notes"]) < NOTES_SHOWN:
            summary["notes"].append({"text": row.description, "reason": reason,
                                     "createdAt": row.created_at.isoformat() if row.created_at else None})
    return summaries


async def _moderator_names(db: AsyncSession, clips) -> dict:
    ids = {clip.moderated_by_id for clip in clips if clip.moderated_by_id}
    if not ids:
        return {}
    users = (await db.execute(select(User).where(User.id.in_(ids)))).scalars().all()
    return {user.id: _clip_author_display_name(user) for user in users}


def _item(clip: Clip, reports: dict, names: dict) -> dict:
    data = clip.to_dict()
    if clip.user is not None:
        data["authorName"] = _clip_author_display_name(clip.user)
    data["reports"] = reports.get(clip.id, {"pending": 0, "total": 0, "reasons": {}, "notes": []})
    data["moderatedAt"] = clip.moderated_at.isoformat() if clip.moderated_at else None
    data["moderatedBy"] = names.get(clip.moderated_by_id)
    data["moderationNote"] = clip.moderation_note
    return data


@router.get("/clips")
async def list_clips_for_moderation(
    view: Literal["reported", "all", "removed"] = "reported",
    q: Optional[str] = Query(None, max_length=120),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_async_session),
    moderator: User = Depends(require_moderator),
):
    """Reported clips (most reporters first), every clip, or removed clips."""
    pending = (
        select(ContentReport.target_id.label("clip_key"),
               func.count(func.distinct(ContentReport.reporter_id)).label("reporters"),
               func.max(ContentReport.created_at).label("latest"))
        .where(ContentReport.target_type == ReportTargetType.CLIP, ContentReport.status == ReportStatus.PENDING)
        .group_by(ContentReport.target_id)
        .subquery()
    )

    def scoped(query):
        if view == "reported":
            query = query.join(pending, pending.c.clip_key == _clip_key())
        query = query.where(Clip.moderation_status == MODERATION_REMOVED if view == "removed"
                            else Clip.moderation_status != MODERATION_REMOVED)
        search = _search_clips(q)
        return query.where(search) if search is not None else query

    total = await db.scalar(select(func.count()).select_from(scoped(select(Clip.id)).subquery()))
    order = {
        "reported": (desc(pending.c.reporters), desc(pending.c.latest), desc(Clip.id)),
        "removed": (desc(Clip.moderated_at), desc(Clip.id)),
        "all": (desc(Clip.created_at), desc(Clip.id)),
    }[view]
    clips = (await db.execute(
        scoped(select(Clip).options(selectinload(Clip.user)))
        .order_by(*order).offset((page - 1) * per_page).limit(per_page)
    )).scalars().all()
    reports = await _report_summaries(db, [clip.id for clip in clips])
    names = await _moderator_names(db, clips)
    return {"clips": [_item(clip, reports, names) for clip in clips],
            "total": total or 0, "page": page, "perPage": per_page}


def _move_media(media: list, removed: bool) -> None:
    """Move every file, or none: a failure part-way moves the earlier ones back."""
    root = user_media._media_root()
    moved = []
    try:
        for folder, name in media:
            if not set_media_removed(folder, name, root, removed):
                logger.warning("Clip media %s/%s is in neither public nor removed storage", folder, name)
            moved.append((folder, name))
    except Exception:
        for folder, name in moved:
            try:
                set_media_removed(folder, name, root, not removed)
            except Exception:
                logger.exception("Could not move %s/%s back after a failed moderation move", folder, name)
        raise


@router.post("/clips/{clip_id}/decision")
async def decide_on_clip(
    clip_id: int,
    decision: ClipDecision,
    db: AsyncSession = Depends(get_async_session),
    moderator: User = Depends(require_moderator),
):
    """Keep, remove or restore a clip, and close its pending reports."""
    # Locked like a report of it, so a decision and a report take turns.
    clip = (await db.execute(
        select(Clip).options(selectinload(Clip.user)).where(Clip.id == clip_id).with_for_update()
    )).scalar_one_or_none()
    if not clip:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")
    action = decision.action
    if clip.moderation_status not in DECIDABLE[action]:
        done = {"keep": "kept", "remove": "removed", "restore": "restored"}[action]
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"This video is {clip.moderation_status}, so it cannot be {done}")

    now = datetime.utcnow()
    note = (decision.note or "").strip() or None
    if action != "restore":
        await db.execute(
            update(ContentReport)
            .where(ContentReport.target_type == ReportTargetType.CLIP,
                   ContentReport.target_id == str(clip.id),
                   ContentReport.status == ReportStatus.PENDING)
            .values(status=ReportStatus.DISMISSED if action == "keep" else ReportStatus.RESOLVED,
                    reviewed_by_id=moderator.id, reviewed_at=now, resolution_note=note)
            .execution_options(synchronize_session=False)
        )
    clip.moderation_status = MODERATION_REMOVED if action == "remove" else MODERATION_ACTIVE
    clip.moderated_at, clip.moderated_by_id, clip.moderation_note = now, moderator.id, note

    media = await _unshared_media(db, clip) if action != "keep" else []
    try:
        await run_in_threadpool(_move_media, media, action == "remove")
    except Exception:
        logger.exception("Could not move the media of clip %s for %s", clip_id, action)
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Video storage is unavailable, so nothing was changed. Please try again.")
    try:
        await db.commit()
    except Exception:
        logger.exception("Could not save the %s decision on clip %s", action, clip_id)
        await db.rollback()
        try:
            await run_in_threadpool(_move_media, media, action != "remove")
        except Exception:
            logger.exception("Could not put back the media of clip %s", clip_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="The decision could not be saved. Please try again.")
    logger.info("Moderator %s chose %s for clip %s", moderator.id, action, clip_id)
    reports = await _report_summaries(db, [clip.id])
    return {"clip": _item(clip, reports, {moderator.id: _clip_author_display_name(moderator)})}
