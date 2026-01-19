"""
Clips Router - CRUD operations for educational video clips.
Provides endpoints for creating, viewing, and managing user clips.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from lyo_app.auth.jwt_auth import get_current_user
from lyo_app.auth.models import User
from lyo_app.core.database import get_async_session
from lyo_app.models.clips import Clip, ClipLike, ClipView

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/clips", tags=["Clips"])


# ============================================================================
# Pydantic Models
# ============================================================================

class ClipMetadata(BaseModel):
    """Metadata for AI course generation."""
    subject: Optional[str] = None
    topic: Optional[str] = None
    level: str = "beginner"
    keyPoints: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    enableCourseGeneration: bool = True


class ClipCreate(BaseModel):
    """Request model for creating a clip."""
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    videoUrl: str = Field(..., description="URL of uploaded video")
    thumbnailUrl: Optional[str] = None
    durationSeconds: float = 0
    subject: Optional[str] = None
    topic: Optional[str] = None
    level: str = "beginner"
    keyPoints: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    isPublic: bool = True
    enableCourseGeneration: bool = True


class ClipUpdate(BaseModel):
    """Request model for updating clip metadata."""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    subject: Optional[str] = None
    topic: Optional[str] = None
    level: Optional[str] = None
    keyPoints: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    isPublic: Optional[bool] = None


class ClipResponse(BaseModel):
    """Response model for a single clip."""
    success: bool
    clip: Optional[dict] = None
    message: Optional[str] = None
    error: Optional[str] = None


class ClipsListResponse(BaseModel):
    """Response model for list of clips."""
    success: bool
    clips: List[dict]
    total: int
    page: int
    perPage: int


class GenerateCourseRequest(BaseModel):
    """Request to generate a course from a clip."""
    clipId: str
    courseTitle: Optional[str] = None
    targetLevel: Optional[str] = None
    additionalContext: Optional[str] = None


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("", response_model=ClipResponse)
async def create_clip(
    request: ClipCreate,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
):
    """Create a new clip."""
    try:
        clip = Clip(
            user_id=current_user.id,
            title=request.title,
            description=request.description,
            video_url=request.videoUrl,
            thumbnail_url=request.thumbnailUrl,
            duration_seconds=request.durationSeconds,
            subject=request.subject,
            topic=request.topic,
            level=request.level,
            key_points=request.keyPoints,
            tags=request.tags,
            is_public=request.isPublic,
            enable_course_generation=request.enableCourseGeneration
        )
        
        db.add(clip)
        await db.commit()
        await db.refresh(clip)
        
        logger.info(f"Clip created: {clip.id} by user {current_user.id}")
        
        return ClipResponse(
            success=True,
            clip=clip.to_dict(),
            message="Clip created successfully"
        )
        
    except Exception as e:
        logger.error(f"Error creating clip: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("", response_model=ClipsListResponse)
async def get_my_clips(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
):
    """Get clips created by the current user."""
    try:
        offset = (page - 1) * per_page
        
        # Count total
        count_query = select(func.count()).select_from(Clip).where(
            Clip.user_id == current_user.id
        )
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0
        
        # Get clips
        query = (
            select(Clip)
            .where(Clip.user_id == current_user.id)
            .order_by(desc(Clip.created_at))
            .offset(offset)
            .limit(per_page)
        )
        result = await db.execute(query)
        clips = result.scalars().all()
        
        return ClipsListResponse(
            success=True,
            clips=[clip.to_dict() for clip in clips],
            total=total,
            page=page,
            perPage=per_page
        )
        
    except Exception as e:
        logger.error(f"Error fetching clips: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/discover", response_model=ClipsListResponse)
async def get_discover_clips(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    subject: Optional[str] = None,
    level: Optional[str] = None,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
):
    """Get public clips for Discover feed."""
    try:
        offset = (page - 1) * per_page
        
        # Build query for public clips
        conditions = [Clip.is_public == True]
        
        if subject:
            conditions.append(Clip.subject == subject)
        if level:
            conditions.append(Clip.level == level)
        
        # Count total
        count_query = select(func.count()).select_from(Clip).where(*conditions)
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0
        
        # Get clips ordered by engagement
        query = (
            select(Clip)
            .where(*conditions)
            .order_by(desc(Clip.view_count + Clip.like_count * 2))
            .offset(offset)
            .limit(per_page)
        )
        result = await db.execute(query)
        clips = result.scalars().all()
        
        # Check if current user liked each clip
        clip_dicts = []
        for clip in clips:
            clip_dict = clip.to_dict()
            
            # Check if user liked this clip
            like_query = select(ClipLike).where(
                ClipLike.clip_id == clip.id,
                ClipLike.user_id == current_user.id
            )
            like_result = await db.execute(like_query)
            clip_dict["isLiked"] = like_result.scalar() is not None
            
            clip_dicts.append(clip_dict)
        
        return ClipsListResponse(
            success=True,
            clips=clip_dicts,
            total=total,
            page=page,
            perPage=per_page
        )
        
    except Exception as e:
        logger.error(f"Error fetching discover clips: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/{clip_id}", response_model=ClipResponse)
async def get_clip(
    clip_id: int,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
):
    """Get a specific clip by ID."""
    try:
        query = select(Clip).where(Clip.id == clip_id)
        result = await db.execute(query)
        clip = result.scalar_one_or_none()
        
        if not clip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Clip not found"
            )
        
        # Check access (owner or public)
        if not clip.is_public and clip.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        clip_dict = clip.to_dict()
        
        # Check if user liked this clip
        like_query = select(ClipLike).where(
            ClipLike.clip_id == clip.id,
            ClipLike.user_id == current_user.id
        )
        like_result = await db.execute(like_query)
        clip_dict["isLiked"] = like_result.scalar() is not None
        
        return ClipResponse(
            success=True,
            clip=clip_dict
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching clip {clip_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.put("/{clip_id}", response_model=ClipResponse)
async def update_clip(
    clip_id: int,
    request: ClipUpdate,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
):
    """Update clip metadata."""
    try:
        query = select(Clip).where(Clip.id == clip_id)
        result = await db.execute(query)
        clip = result.scalar_one_or_none()
        
        if not clip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Clip not found"
            )
        
        if clip.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only update your own clips"
            )
        
        # Update fields
        update_data = request.dict(exclude_unset=True)
        
        if "title" in update_data:
            clip.title = update_data["title"]
        if "description" in update_data:
            clip.description = update_data["description"]
        if "subject" in update_data:
            clip.subject = update_data["subject"]
        if "topic" in update_data:
            clip.topic = update_data["topic"]
        if "level" in update_data:
            clip.level = update_data["level"]
        if "keyPoints" in update_data:
            clip.key_points = update_data["keyPoints"]
        if "tags" in update_data:
            clip.tags = update_data["tags"]
        if "isPublic" in update_data:
            clip.is_public = update_data["isPublic"]
        
        await db.commit()
        await db.refresh(clip)
        
        return ClipResponse(
            success=True,
            clip=clip.to_dict(),
            message="Clip updated successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating clip {clip_id}: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.delete("/{clip_id}")
async def delete_clip(
    clip_id: int,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
):
    """Delete a clip."""
    try:
        query = select(Clip).where(Clip.id == clip_id)
        result = await db.execute(query)
        clip = result.scalar_one_or_none()
        
        if not clip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Clip not found"
            )
        
        if clip.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only delete your own clips"
            )
        
        await db.delete(clip)
        await db.commit()
        
        logger.info(f"Clip deleted: {clip_id} by user {current_user.id}")
        
        return {"success": True, "message": "Clip deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting clip {clip_id}: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/{clip_id}/like")
async def toggle_clip_like(
    clip_id: int,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
):
    """Toggle like status for a clip."""
    try:
        # Check clip exists
        clip_query = select(Clip).where(Clip.id == clip_id)
        clip_result = await db.execute(clip_query)
        clip = clip_result.scalar_one_or_none()
        
        if not clip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Clip not found"
            )
        
        # Check if already liked
        like_query = select(ClipLike).where(
            ClipLike.clip_id == clip_id,
            ClipLike.user_id == current_user.id
        )
        like_result = await db.execute(like_query)
        existing_like = like_result.scalar_one_or_none()
        
        if existing_like:
            # Unlike
            await db.delete(existing_like)
            clip.like_count = max(0, clip.like_count - 1)
            is_liked = False
        else:
            # Like
            new_like = ClipLike(clip_id=clip_id, user_id=current_user.id)
            db.add(new_like)
            clip.like_count += 1
            is_liked = True
        
        await db.commit()
        
        return {
            "isLiked": is_liked,
            "likeCount": clip.like_count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error toggling like for clip {clip_id}: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/{clip_id}/view")
async def record_clip_view(
    clip_id: int,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
):
    """Record a view for a clip."""
    try:
        # Check clip exists
        clip_query = select(Clip).where(Clip.id == clip_id)
        clip_result = await db.execute(clip_query)
        clip = clip_result.scalar_one_or_none()
        
        if not clip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Clip not found"
            )
        
        # Record view
        view = ClipView(clip_id=clip_id, user_id=current_user.id)
        db.add(view)
        
        # Increment view count
        clip.view_count += 1
        
        await db.commit()
        
        return {"success": True, "viewCount": clip.view_count}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recording view for clip {clip_id}: {e}")
        await db.rollback()
        return {"success": False}  # Non-critical, don't raise


@router.post("/{clip_id}/generate-course")
async def generate_course_from_clip(
    clip_id: int,
    request: GenerateCourseRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
):
    """Generate a course from a clip using AI."""
    try:
        # Get clip
        clip_query = select(Clip).where(Clip.id == clip_id)
        clip_result = await db.execute(clip_query)
        clip = clip_result.scalar_one_or_none()
        
        if not clip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Clip not found"
            )
        
        if not clip.enable_course_generation:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Course generation is disabled for this clip"
            )
        
        # Build course generation context
        course_title = request.courseTitle or f"Learn: {clip.title}"
        context = {
            "clip_title": clip.title,
            "clip_description": clip.description,
            "subject": clip.subject,
            "topic": clip.topic,
            "level": request.targetLevel or clip.level,
            "key_points": clip.key_points or [],
            "transcript": clip.transcript,
            "additional_context": request.additionalContext
        }
        
        # TODO: Call CourseGenerationService to create course
        # For now, return a placeholder
        logger.info(f"Course generation requested for clip {clip_id}")
        
        return {
            "success": True,
            "courseId": f"course-from-clip-{clip_id}",
            "message": f"Course generation initiated for '{course_title}'"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating course from clip {clip_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
