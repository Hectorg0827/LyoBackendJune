"""
Search Router - cross-entity search over users, study groups, community
events, and community posts. One endpoint, grouped results, so every
client renders the same search experience.
"""
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.auth.jwt_auth import get_current_user
from lyo_app.auth.models import User
from lyo_app.community.models import CommunityEvent, CommunityPost, StudyGroup, StudyGroupPrivacy
from lyo_app.core.database import get_db

router = APIRouter(prefix="/search", tags=["Search"])


class SearchType(str, Enum):
    """Types of searchable content."""
    ALL = "all"
    USERS = "users"
    GROUPS = "groups"
    EVENTS = "events"
    POSTS = "posts"


def _display_name(user: User) -> str:
    full = f"{user.first_name or ''} {user.last_name or ''}".strip()
    return full or user.username or f"User {user.id}"


@router.get("")
async def search(
    q: str = Query(..., min_length=1, max_length=200, description="Search query"),
    type: SearchType = Query(default=SearchType.ALL, description="Filter by content type"),
    limit: int = Query(default=10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search users, study groups, community events, and posts."""
    pattern = f"%{q.strip()}%"
    users, groups, events, posts = [], [], [], []

    if type in (SearchType.ALL, SearchType.USERS):
        result = await db.execute(
            select(User)
            .where(
                or_(
                    User.username.ilike(pattern),
                    User.first_name.ilike(pattern),
                    User.last_name.ilike(pattern),
                )
            )
            .order_by(User.username)
            .limit(limit)
        )
        users = [
            {
                "id": u.id,
                "username": u.username,
                "name": _display_name(u),
                "avatar_url": u.avatar_url,
            }
            for u in result.scalars().all()
        ]

    if type in (SearchType.ALL, SearchType.GROUPS):
        result = await db.execute(
            select(StudyGroup)
            .where(
                StudyGroup.privacy == StudyGroupPrivacy.PUBLIC,
                or_(StudyGroup.name.ilike(pattern), StudyGroup.description.ilike(pattern)),
            )
            .order_by(StudyGroup.name)
            .limit(limit)
        )
        groups = [
            {
                "id": g.id,
                "name": g.name,
                "description": g.description,
                "privacy": g.privacy.value if g.privacy else "public",
            }
            for g in result.scalars().all()
        ]

    if type in (SearchType.ALL, SearchType.EVENTS):
        result = await db.execute(
            select(CommunityEvent)
            .where(or_(CommunityEvent.title.ilike(pattern), CommunityEvent.description.ilike(pattern)))
            .order_by(CommunityEvent.start_time)
            .limit(limit)
        )
        events = [
            {
                "id": e.id,
                "title": e.title,
                "event_type": e.event_type.value if e.event_type else "other",
                "start_time": e.start_time.isoformat() if e.start_time else None,
                "end_time": e.end_time.isoformat() if e.end_time else None,
                "location": e.location,
                "is_online": bool(e.is_online),
                "latitude": e.latitude,
                "longitude": e.longitude,
            }
            for e in result.scalars().all()
        ]

    if type in (SearchType.ALL, SearchType.POSTS):
        result = await db.execute(
            select(CommunityPost)
            .where(
                CommunityPost.is_deleted == False,  # noqa: E712
                CommunityPost.content.ilike(pattern),
            )
            .order_by(CommunityPost.created_at.desc())
            .limit(limit)
        )
        posts = [
            {
                "id": str(p.id),
                "content": (p.content[:200] + "…") if len(p.content or "") > 200 else p.content,
                "author_name": p.author_name,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in result.scalars().all()
        ]

    return {
        "query": q,
        "users": users,
        "groups": groups,
        "events": events,
        "posts": posts,
        "total": len(users) + len(groups) + len(events) + len(posts),
    }


@router.get("/suggestions")
async def get_search_suggestions(
    q: str = Query(..., min_length=1, max_length=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Autocomplete: usernames and group names matching the prefix."""
    pattern = f"{q.strip()}%"
    names = await db.execute(select(User.username).where(User.username.ilike(pattern)).limit(5))
    groups = await db.execute(select(StudyGroup.name).where(StudyGroup.name.ilike(pattern)).limit(5))
    return {"suggestions": [*[n for (n,) in names.all()], *[g for (g,) in groups.all()]]}
