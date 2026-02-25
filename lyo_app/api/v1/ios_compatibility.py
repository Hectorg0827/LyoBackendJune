"""
iOS Compatibility Endpoints

Provides aliases and stubs for endpoints the iOS app expects but that may live
under different paths in the enhanced backend.
"""

from fastapi import APIRouter, Depends, Query
from typing import Optional, Any

from lyo_app.auth.dependencies import get_current_user_or_guest

router = APIRouter(prefix="/api/v1", tags=["iOS Compatibility"])


@router.get("/feed")
async def get_feed_alias(
    skip: int = Query(0, alias="offset"),
    limit: int = Query(10),
    content_type: Optional[str] = Query(None),
    current_user: Any = Depends(get_current_user_or_guest),
):
    """
    GET /api/v1/feed — iOS compatibility alias.

    Tries to proxy to the v1 feeds module.  If that import fails (missing deps
    in production), returns an empty but well-formed response so the iOS app
    does not crash.
    """
    try:
        from lyo_app.core.database import get_db
        from lyo_app.api.v1.feeds import get_personalized_feed

        async for db in get_db():
            return await get_personalized_feed(
                current_user=current_user,
                db=db,
                skip=skip,
                limit=limit,
                content_type=content_type,
            )
    except Exception:
        pass

    # Fallback: empty but valid feed response
    return {
        "items": [],
        "total": 0,
        "limit": limit,
        "offset": skip,
        "has_more": False,
    }


@router.get("/analytics/progress")
async def get_progress_analytics(
    current_user: Any = Depends(get_current_user_or_guest),
):
    """Placeholder for analytics progress to avoid 404s in iOS app."""
    return {
        "status": "success",
        "data": {
            "overall_progress": 0.45,
            "daily_goal_minutes": 30,
            "minutes_today": 12,
            "streak_days": 5,
            "topics_mastered": 3,
            "recent_activity": [],
        },
    }
