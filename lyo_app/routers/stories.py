"""
Stories Router - Ephemeral content (Stories) management
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from lyo_app.auth.jwt_auth import get_current_user
from lyo_app.auth.models import User

router = APIRouter(prefix="/stories", tags=["Stories"])


class StoryCreate(BaseModel):
    """Create a new story."""
    caption: Optional[str] = None
    media_type: str = "image"  # image, video
    duration_hours: int = 24


class StoryResponse(BaseModel):
    """Story response model."""
    id: str
    user_id: int
    media_url: str
    caption: Optional[str]
    created_at: datetime
    expires_at: datetime
    view_count: int


@router.get("/feed")
async def get_stories_feed(
    current_user: User = Depends(get_current_user)
):
    """Get stories from followed users."""
    return {"stories": [], "users_with_stories": []}


@router.get("/me")
async def get_my_stories(
    current_user: User = Depends(get_current_user)
):
    """Get current user's active stories."""
    return {"stories": []}


@router.post("/create")
async def create_story(
    file: UploadFile = File(...),
    caption: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Create a new story."""
    return {
        "status": "created",
        "message": "Story created successfully",
        "expires_in_hours": 24
    }


@router.get("/{story_id}")
async def get_story(
    story_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get a specific story by ID."""
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Story not found or expired"
    )


@router.delete("/{story_id}")
async def delete_story(
    story_id: str,
    current_user: User = Depends(get_current_user)
):
    """Delete a story."""
    return {"status": "deleted", "story_id": story_id}


@router.post("/{story_id}/view")
async def mark_story_viewed(
    story_id: str,
    current_user: User = Depends(get_current_user)
):
    """Mark a story as viewed."""
    return {"status": "viewed", "story_id": story_id}


@router.get("/{story_id}/viewers")
async def get_story_viewers(
    story_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get list of users who viewed a story."""
    return {"viewers": [], "total": 0}
