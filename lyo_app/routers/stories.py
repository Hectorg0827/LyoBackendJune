"""
Stories Router - Instagram-style ephemeral content (Stories) management
24-hour auto-expiring stories with slides, views tracking, and seen status
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, and_, or_
from sqlalchemy.orm import selectinload
import uuid
import logging

from lyo_app.auth.jwt_auth import get_current_user
from lyo_app.auth.models import User
from lyo_app.core.database import get_db
from lyo_app.models.social import Story as StoryModel, StoryView

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stories", tags=["Stories"])


# ============================================================================
# SCHEMAS
# ============================================================================

class StorySlideCreate(BaseModel):
    """Slide within a story."""
    type: str = "image"  # image, video, text
    media_url: Optional[str] = None
    text: Optional[str] = None
    duration: int = 5  # seconds


class StoryCreate(BaseModel):
    """Create a new story request."""
    media_url: str
    media_type: str = "image"  # image, video, text
    caption: Optional[str] = None
    is_live: bool = False
    linked_course_id: Optional[str] = None
    linked_group_id: Optional[str] = None
    tags: List[str] = []


class StorySlideResponse(BaseModel):
    """Story slide response."""
    id: str
    type: str
    media_url: Optional[str]
    text: Optional[str]
    duration: int

    class Config:
        from_attributes = True


class StoryResponse(BaseModel):
    """Full story response model."""
    id: str
    user_id: str
    user_name: str
    user_avatar: Optional[str]
    slides: List[StorySlideResponse]
    is_live: bool
    created_at: datetime
    expires_at: datetime
    is_seen: bool = False
    view_count: int
    linked_course_id: Optional[str] = None
    linked_group_id: Optional[str] = None
    linked_reel_id: Optional[str] = None
    tags: List[str] = []

    class Config:
        from_attributes = True


class StoriesResponse(BaseModel):
    """Response for stories feed."""
    stories: List[StoryResponse]
    my_story: Optional[StoryResponse] = None


class StoryViewerResponse(BaseModel):
    """User who viewed a story."""
    user_id: str
    user_name: str
    user_avatar: Optional[str]
    viewed_at: datetime


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def story_model_to_response(story: StoryModel, current_user_id: int, db: AsyncSession) -> StoryResponse:
    """Convert SQLAlchemy model to response schema."""
    # Check if current user has seen this story
    stmt = select(StoryView).filter(
        StoryView.story_id == story.id,
        StoryView.viewer_id == current_user_id
    )
    result = await db.execute(stmt)
    is_seen = result.scalars().first() is not None
    
    # Parse metadata for slides
    metadata = story.story_metadata or {}
    slides_data = metadata.get("slides", [])
    
    # If no slides in metadata, create one from main media
    if not slides_data and story.media_url:
        slides_data = [{
            "id": f"slide_{story.id}_1",
            "type": story.content_type or "image",
            "media_url": story.media_url,
            "text": story.text_content,
            "duration": 5
        }]
    
    slides = [
        StorySlideResponse(
            id=s.get("id", str(uuid.uuid4())),
            type=s.get("type", "image"),
            media_url=s.get("media_url"),
            text=s.get("text"),
            duration=s.get("duration", 5)
        )
        for s in slides_data
    ]
    
    return StoryResponse(
        id=str(story.id),
        user_id=str(story.user_id),
        user_name=story.user.username if story.user else "Unknown",
        user_avatar=story.user.avatar_url if story.user else None,
        slides=slides,
        is_live=metadata.get("is_live", False),
        created_at=story.created_at,
        expires_at=story.expires_at,
        is_seen=is_seen,
        view_count=story.view_count or 0,
        linked_course_id=metadata.get("linked_course_id"),
        linked_group_id=metadata.get("linked_group_id"),
        linked_reel_id=metadata.get("linked_reel_id"),
        tags=metadata.get("tags", [])
    )


async def cleanup_expired_stories():
    """Background task to delete expired stories."""
    from lyo_app.core.database import get_db_session
    db = await get_db_session()
    try:
        now = datetime.utcnow()
        stmt = select(StoryModel).filter(
            StoryModel.expires_at < now,
            StoryModel.is_highlight == False
        )
        result = await db.execute(stmt)
        expired = result.scalars().all()
        
        
        for story in expired:
            db.delete(story)
        
        await db.commit()
        if expired:
            logger.info(f"🗑️ Cleaned up {len(expired)} expired stories")
    except Exception as e:
        logger.error(f"❌ Failed to cleanup expired stories: {e}")
        await db.rollback()
    finally:
        await db.close()


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("", response_model=StoriesResponse)
@router.get("/", response_model=StoriesResponse)
async def get_stories_feed(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = None
):
    """
    Get all active stories (not expired).
    Returns stories from all users, grouped by user.
    Also includes the current user's story separately as 'my_story'.
    """
    # Trigger cleanup in background
    if background_tasks:
        background_tasks.add_task(cleanup_expired_stories)
    
    now = datetime.utcnow()
    
    # Get all non-expired stories
    stmt = select(StoryModel).options(
        selectinload(StoryModel.user)
    ).filter(
        StoryModel.expires_at > now
    ).order_by(StoryModel.created_at.desc())
    
    result = await db.execute(stmt)
    stories = result.scalars().all()
    
    # Separate current user's story
    my_story = None
    other_stories = []
    
    for story in stories:
        response = await story_model_to_response(story, current_user.id, db)
        if story.user_id == current_user.id:
            my_story = response
        else:
            other_stories.append(response)
    
    return StoriesResponse(
        stories=other_stories,
        my_story=my_story
    )


@router.get("/me", response_model=List[StoryResponse])
async def get_my_stories(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current user's active stories."""
    now = datetime.utcnow()
    
    stmt = select(StoryModel).options(
        selectinload(StoryModel.user)
    ).filter(
        StoryModel.user_id == current_user.id,
        StoryModel.expires_at > now
    ).order_by(StoryModel.created_at.desc())
    
    result = await db.execute(stmt)
    stories = result.scalars().all()
    
    return [await story_model_to_response(s, current_user.id, db) for s in stories]


@router.post("", response_model=StoryResponse)
@router.post("/", response_model=StoryResponse)
async def create_story(
    request: StoryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new story that expires in 24 hours.
    """
    try:
        # Create story metadata
        metadata = {
            "slides": [{
                "id": f"slide_{uuid.uuid4().hex[:8]}",
                "type": request.media_type,
                "media_url": request.media_url,
                "text": request.caption,
                "duration": 5
            }],
            "is_live": request.is_live,
            "linked_course_id": request.linked_course_id,
            "linked_group_id": request.linked_group_id,
            "tags": request.tags
        }
        
        # Create the story
        story = StoryModel(
            user_id=current_user.id,
            content_type=request.media_type,
            media_url=request.media_url,
            text_content=request.caption,
            story_metadata=metadata,
            expires_at=datetime.utcnow() + timedelta(hours=24),
            is_highlight=False,
            view_count=0
        )
        
        db.add(story)
        await db.commit()
        await db.refresh(story)
        
        logger.info(f"✅ Story created by user {current_user.id}, expires at {story.expires_at}")
        
        return await story_model_to_response(story, current_user.id, db)
        
    except Exception as e:
        await db.rollback()
        logger.error(f"❌ Failed to create story: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create story: {str(e)}"
        )


@router.get("/{story_id}", response_model=StoryResponse)
async def get_story(
    story_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific story by ID."""
    stmt = select(StoryModel).options(
        selectinload(StoryModel.user)
    ).filter(
        StoryModel.id == int(story_id),
        StoryModel.expires_at > datetime.utcnow()
    )
    result = await db.execute(stmt)
    story = result.scalars().first()
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found or expired"
        )
    
    return await story_model_to_response(story, current_user.id, db)


@router.delete("/{story_id}")
async def delete_story(
    story_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a story (only owner can delete)."""
    stmt = select(StoryModel).filter(StoryModel.id == int(story_id))
    result = await db.execute(stmt)
    story = result.scalars().first()
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    if story.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own stories"
        )
    
    db.delete(story)
    await db.commit()
    
    logger.info(f"🗑️ Story {story_id} deleted by user {current_user.id}")
    
    return {"status": "deleted", "story_id": story_id}


@router.post("/{story_id}/seen")
@router.post("/{story_id}/view")
async def mark_story_viewed(
    story_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Mark a story as viewed by the current user."""
    stmt = select(StoryModel).filter(StoryModel.id == int(story_id))
    result = await db.execute(stmt)
    story = result.scalars().first()
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    # Check if already viewed
    stmt = select(StoryView).filter(
        StoryView.story_id == story.id,
        StoryView.viewer_id == current_user.id
    )
    result = await db.execute(stmt)
    existing_view = result.scalars().first()
    
    if not existing_view:
        # Create view record
        view = StoryView(
            story_id=story.id,
            viewer_id=current_user.id
        )
        db.add(view)
        
        # Increment view count
        story.view_count = (story.view_count or 0) + 1
        
        await db.commit()
    
    return {"status": "viewed", "story_id": story_id}


@router.get("/{story_id}/viewers", response_model=List[StoryViewerResponse])
async def get_story_viewers(
    story_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get list of users who viewed a story (only owner can see)."""
    stmt = select(StoryModel).filter(StoryModel.id == int(story_id))
    result = await db.execute(stmt)
    story = result.scalars().first()
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    if story.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view viewers of your own stories"
        )
    
    stmt = select(StoryView).filter(StoryView.story_id == story.id)
    result = await db.execute(stmt)
    views = result.scalars().all()
    
    return [
        StoryViewerResponse(
            user_id=str(v.viewer.id) if v.viewer else "Unknown",
            user_name=v.viewer.username if v.viewer else "Unknown",
            user_avatar=v.viewer.avatar_url if v.viewer else None,
            viewed_at=v.viewed_at
        )
        for v in views
    ]
