from fastapi import APIRouter, Depends, Query
from typing import Optional, List, Dict, Any
from lyo_app.api.v1.feeds import get_personalized_feed, FeedResponse
from lyo_app.auth.dependencies import get_current_user_or_guest
from lyo_app.auth.schemas import UserRead
from lyo_app.core.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1", tags=["iOS Compatibility"])

@router.get("/feed", response_model=FeedResponse)
async def get_feed_alias(
    current_user: Any = Depends(get_current_user_or_guest),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, alias="offset"),
    limit: int = Query(10),
    content_type: Optional[str] = Query(None)
):
    """Alias for /feeds/ to support iOS app naming convention."""
    # We adapt the parameters (offset -> skip) and call the existing feed logic
    from lyo_app.api.v1.feeds import get_personalized_feed
    return await get_personalized_feed(
        current_user=current_user,
        db=db,
        skip=skip,
        limit=limit,
        content_type=content_type
    )

@router.get("/analytics/progress")
async def get_progress_analytics(
    current_user: Any = Depends(get_current_user_or_guest)
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
            "recent_activity": []
        }
    }
