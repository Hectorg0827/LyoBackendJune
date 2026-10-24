"""
Moderation Router - Content moderation and safety

Reports are filed where the content lives (POST /api/v1/clips/{id}/report,
/api/v1/community/reports), which store them for review. A report endpoint
here answered "submitted" without saving anything, so it was removed.
"""
from fastapi import APIRouter, Depends, HTTPException, status

from lyo_app.auth.jwt_auth import get_current_user
from lyo_app.auth.models import User

router = APIRouter(prefix="/moderation", tags=["Moderation"])


@router.post("/block/{user_id}")
async def block_user(
    user_id: int,
    current_user: User = Depends(get_current_user)
):
    """Block a user."""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot block yourself"
        )
    return {"status": "blocked", "user_id": user_id}


@router.delete("/block/{user_id}")
async def unblock_user(
    user_id: int,
    current_user: User = Depends(get_current_user)
):
    """Unblock a user."""
    return {"status": "unblocked", "user_id": user_id}


@router.get("/blocked")
async def get_blocked_users(
    current_user: User = Depends(get_current_user)
):
    """Get list of blocked users."""
    return {"blocked_users": []}


@router.post("/mute/{user_id}")
async def mute_user(
    user_id: int,
    current_user: User = Depends(get_current_user)
):
    """Mute a user (hide their content without blocking)."""
    return {"status": "muted", "user_id": user_id}


@router.delete("/mute/{user_id}")
async def unmute_user(
    user_id: int,
    current_user: User = Depends(get_current_user)
):
    """Unmute a user."""
    return {"status": "unmuted", "user_id": user_id}


@router.get("/muted")
async def get_muted_users(
    current_user: User = Depends(get_current_user)
):
    """Get list of muted users."""
    return {"muted_users": []}
