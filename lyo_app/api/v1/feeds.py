"""
Production feeds API routes.
Personalized content feeds and recommendations.
"""

import logging
from typing import List, Dict, Any, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from lyo_app.core.database import get_db
from lyo_app.models.production import User, FeedItem, Course
from lyo_app.auth.production import require_user
from lyo_app.tasks.feed_curation import curate_personalized_feed

logger = logging.getLogger(__name__)

router = APIRouter()


# Response models
class FeedItemResponse(BaseModel):
    id: str
    title: str
    description: str = None
    content_type: str
    content_id: str = None
    metadata: Dict[str, Any] = None
    score: float
    created_at: str
    
    model_config = {
        "from_attributes": True
    }


class FeedResponse(BaseModel):
    items: List[FeedItemResponse]
    total_count: int
    has_more: bool


class FeedPreferencesRequest(BaseModel):
    subjects: List[str] = []
    difficulty_levels: List[str] = []
    content_types: List[str] = []
    learning_styles: List[str] = []


class FeedPreferencesResponse(BaseModel):
    subjects: List[str] = []
    difficulty_levels: List[str] = []
    content_types: List[str] = []
    learning_styles: List[str] = []
    updated_at: str


@router.get("/", response_model=FeedResponse)
async def get_personalized_feed(
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=50),
    content_type: Optional[str] = Query(None),
    refresh: bool = Query(False)
):
    """
    Get personalized feed for the user.
    """
    try:
        # If refresh requested, trigger feed curation
        if refresh:
            curate_personalized_feed.delay(str(current_user.id))
        
        # Build query
        query = select(FeedItem).where(FeedItem.user_id == current_user.id)
        
        # Filter by content type if provided
        if content_type:
            query = query.where(FeedItem.content_type == content_type)
        
        # Get total count
        count_query = select(func.count(FeedItem.id)).where(
            FeedItem.user_id == current_user.id
        )
        if content_type:
            count_query = count_query.where(FeedItem.content_type == content_type)
            
        count_result = await db.execute(count_query)
        total_count = count_result.scalar()
        
        # Get feed items
        query = query.offset(skip).limit(limit).order_by(
            FeedItem.score.desc(),
            FeedItem.created_at.desc()
        )
        
        result = await db.execute(query)
        feed_items = result.scalars().all()
        
        # Convert to response format
        items = []
        for item in feed_items:
            items.append(FeedItemResponse(
                id=str(item.id),
                title=item.title,
                description=item.description,
                content_type=item.content_type,
                content_id=str(item.content_id) if item.content_id else None,
                metadata=item.metadata,
                score=item.score,
                created_at=item.created_at.isoformat()
            ))
        
        has_more = (skip + len(items)) < total_count
        
        return FeedResponse(
            items=items,
            total_count=total_count,
            has_more=has_more
        )
        
    except Exception as e:
        logger.error(f"Feed retrieval error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get feed")


@router.post("/refresh")
async def refresh_feed(
    current_user: User = Depends(require_user)
):
    """
    Trigger manual feed refresh for the user.
    """
    try:
        # Start feed curation task
        task = curate_personalized_feed.delay(str(current_user.id))
        
        logger.info(f"Feed refresh triggered for user: {current_user.email}")
        
        return {
            "message": "Feed refresh started",
            "task_id": task.id
        }
        
    except Exception as e:
        logger.error(f"Feed refresh error: {e}")
        raise HTTPException(status_code=500, detail="Feed refresh failed")


@router.get("/recommendations", response_model=List[FeedItemResponse])
async def get_course_recommendations(
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(5, ge=1, le=20)
):
    """
    Get course recommendations based on user preferences and activity.
    """
    try:
        # Get recent popular courses
        query = select(Course).options(
            selectinload(Course.lessons)
        ).order_by(Course.created_at.desc()).limit(limit * 2)
        
        result = await db.execute(query)
        courses = result.scalars().all()
        
        # Convert to feed items
        recommendations = []
        for course in courses[:limit]:
            recommendations.append(FeedItemResponse(
                id=f"course_{course.id}",
                title=course.title,
                description=course.description,
                content_type="course_recommendation",
                content_id=str(course.id),
                metadata={
                    "subject": course.subject,
                    "difficulty": course.difficulty_level,
                    "duration_hours": course.estimated_duration_hours,
                    "lessons_count": len(course.lessons) if course.lessons else 0
                },
                score=0.8,  # Default recommendation score
                created_at=course.created_at.isoformat()
            ))
        
        return recommendations
        
    except Exception as e:
        logger.error(f"Course recommendations error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get recommendations")


@router.post("/mark-read/{item_id}")
async def mark_feed_item_read(
    item_id: UUID,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Mark a feed item as read.
    """
    try:
        query = select(FeedItem).where(
            FeedItem.id == item_id,
            FeedItem.user_id == current_user.id
        )
        
        result = await db.execute(query)
        feed_item = result.scalar_one_or_none()
        
        if not feed_item:
            raise HTTPException(status_code=404, detail="Feed item not found")
        
        # Update metadata to mark as read
        if not feed_item.metadata:
            feed_item.metadata = {}
        feed_item.metadata["read"] = True
        feed_item.metadata["read_at"] = "now"
        
        await db.commit()
        
        return {"message": "Feed item marked as read"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Mark read error: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to mark as read")


@router.delete("/clear")
async def clear_feed(
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
    content_type: Optional[str] = Query(None)
):
    """
    Clear feed items for the user.
    """
    try:
        query = select(FeedItem).where(FeedItem.user_id == current_user.id)
        
        if content_type:
            query = query.where(FeedItem.content_type == content_type)
        
        result = await db.execute(query)
        feed_items = result.scalars().all()
        
        for item in feed_items:
            await db.delete(item)
        
        await db.commit()
        
        count = len(feed_items)
        logger.info(f"Cleared {count} feed items for user: {current_user.email}")
        
        return {
            "message": f"Cleared {count} feed items",
            "count": count
        }
        
    except Exception as e:
        logger.error(f"Clear feed error: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to clear feed")
