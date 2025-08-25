"""User management API endpoints."""

from typing import List, Optional, Dict, Any
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, Field

from lyo_app.core.database import get_db_session
from lyo_app.auth.jwt_auth import require_active_user
from lyo_app.models.enhanced import User, Course, Task, GamificationProfile
from lyo_app.schemas import UserResponse
from lyo_app.core.problems import NotFoundProblem

router = APIRouter()


class UserProfileUpdate(BaseModel):
    """Request model for updating user profile."""
    email: Optional[str] = Field(None, description="New email address")
    full_name: Optional[str] = Field(None, description="Updated full name")
    profile_data: Optional[Dict[str, Any]] = Field(None, description="Additional profile data")


class UserStatsResponse(BaseModel):
    """Response model for user statistics."""
    courses_completed: int
    tasks_completed: int
    total_study_time_minutes: int
    current_streak_days: int
    total_points: int
    level: int
    achievements_count: int
    join_date: datetime


class UserActivityResponse(BaseModel):
    """Response model for user activity."""
    recent_courses: List[Dict[str, Any]]
    recent_tasks: List[Dict[str, Any]]
    learning_streak: Dict[str, Any]
    weekly_activity: List[Dict[str, Any]]


@router.get("/me", response_model=UserResponse, summary="Get current user profile")
async def get_current_user_profile(
    current_user: User = Depends(require_active_user)
) -> UserResponse:
    """Get the current user's profile information."""
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        full_name=current_user.full_name,
        is_active=current_user.is_active,
        is_verified=current_user.is_verified,
        created_at=current_user.created_at,
        last_login_at=current_user.last_login_at,
        profile_data=current_user.profile_data
    )


@router.put("/me", response_model=UserResponse, summary="Update current user profile")
async def update_current_user_profile(
    profile_update: UserProfileUpdate,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session)
) -> UserResponse:
    """Update the current user's profile information."""
    # Update fields if provided
    if profile_update.email is not None:
        current_user.email = profile_update.email
    
    if profile_update.full_name is not None:
        current_user.full_name = profile_update.full_name
    
    if profile_update.profile_data is not None:
        # Merge with existing profile data
        existing_data = current_user.profile_data or {}
        existing_data.update(profile_update.profile_data)
        current_user.profile_data = existing_data
    
    await db.commit()
    await db.refresh(current_user)
    
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        full_name=current_user.full_name,
        is_active=current_user.is_active,
        is_verified=current_user.is_verified,
        created_at=current_user.created_at,
        last_login_at=current_user.last_login_at,
        profile_data=current_user.profile_data
    )


@router.get("/me/stats", response_model=UserStatsResponse, summary="Get user statistics")
async def get_user_stats(
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session)
) -> UserStatsResponse:
    """Get comprehensive statistics for the current user."""
    
    # Count completed courses
    courses_result = await db.execute(
        select(func.count(Course.id)).where(
            Course.user_id == current_user.id,
            Course.completion_status == "completed"
        )
    )
    courses_completed = courses_result.scalar() or 0
    
    # Count completed tasks
    tasks_result = await db.execute(
        select(func.count(Task.id)).where(
            Task.user_id == current_user.id,
            Task.completion_status == "completed"
        )
    )
    tasks_completed = tasks_result.scalar() or 0
    
    # Get gamification profile
    gamification_result = await db.execute(
        select(GamificationProfile).where(GamificationProfile.user_id == current_user.id)
    )
    gamification = gamification_result.scalar_one_or_none()
    
    if not gamification:
        # Create default gamification profile
        gamification = GamificationProfile(
            user_id=current_user.id,
            total_points=0,
            level=1,
            achievements=[],
            streak_days=0
        )
        db.add(gamification)
        await db.commit()
    
    return UserStatsResponse(
        courses_completed=courses_completed,
        tasks_completed=tasks_completed,
        total_study_time_minutes=0,  # Would be calculated from actual study sessions
        current_streak_days=gamification.streak_days,
        total_points=gamification.total_points,
        level=gamification.level,
        achievements_count=len(gamification.achievements),
        join_date=current_user.created_at
    )


@router.get("/me/activity", response_model=UserActivityResponse, summary="Get user activity")
async def get_user_activity(
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session),
    days: int = Query(30, description="Number of days of activity to retrieve")
) -> UserActivityResponse:
    """Get recent activity and learning patterns for the current user."""
    
    # Get recent courses
    recent_courses_result = await db.execute(
        select(Course).where(Course.user_id == current_user.id)
        .order_by(Course.updated_at.desc())
        .limit(5)
    )
    recent_courses = recent_courses_result.scalars().all()
    
    # Get recent tasks
    recent_tasks_result = await db.execute(
        select(Task).where(Task.user_id == current_user.id)
        .order_by(Task.updated_at.desc())
        .limit(10)
    )
    recent_tasks = recent_tasks_result.scalars().all()
    
    # Get gamification data for streak info
    gamification_result = await db.execute(
        select(GamificationProfile).where(GamificationProfile.user_id == current_user.id)
    )
    gamification = gamification_result.scalar_one_or_none()
    
    return UserActivityResponse(
        recent_courses=[
            {
                "id": str(course.id),
                "title": course.title,
                "status": course.completion_status,
                "updated_at": course.updated_at.isoformat(),
                "progress": course.progress_percentage
            }
            for course in recent_courses
        ],
        recent_tasks=[
            {
                "id": str(task.id),
                "title": task.title,
                "status": task.completion_status,
                "updated_at": task.updated_at.isoformat(),
                "course_id": str(task.course_id) if task.course_id else None
            }
            for task in recent_tasks
        ],
        learning_streak={
            "current_streak": gamification.streak_days if gamification else 0,
            "longest_streak": gamification.metadata.get("longest_streak", 0) if gamification and gamification.metadata else 0,
            "last_activity": current_user.last_login_at.isoformat() if current_user.last_login_at else None
        },
        weekly_activity=[
            # Placeholder for weekly activity data
            # In production, this would query actual activity logs
            {
                "date": (datetime.utcnow().date()).isoformat(),
                "activities": 0,
                "study_time_minutes": 0
            }
        ]
    )


@router.delete("/me", summary="Delete current user account")
async def delete_current_user(
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Delete the current user account and all associated data.
    
    ⚠️ **WARNING**: This action is irreversible and will delete:
    - User profile and authentication data
    - All courses and learning progress
    - Tasks and completions
    - Gamification data and achievements
    - Push notification devices
    - Community posts and interactions
    
    Consider deactivating the account instead if temporary suspension is desired.
    """
    # In production, this would:
    # 1. Send confirmation email
    # 2. Add grace period before actual deletion
    # 3. Anonymize data instead of hard delete (GDPR compliance)
    # 4. Log the deletion for audit purposes
    
    user_id = current_user.id
    
    # Mark user as inactive first (safer approach)
    current_user.is_active = False
    await db.commit()
    
    # In production, you might queue a background job for full data deletion
    # after a grace period, rather than immediate deletion
    
    return {
        "message": "Account deactivation initiated",
        "user_id": str(user_id),
        "note": "Account has been deactivated. Contact support if this was done in error."
    }


@router.post("/me/deactivate", summary="Deactivate current user account")
async def deactivate_current_user(
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Deactivate the current user account.
    
    This preserves all user data but prevents login until the account is reactivated.
    """
    current_user.is_active = False
    await db.commit()
    
    return {
        "message": "Account deactivated successfully",
        "user_id": str(current_user.id),
        "note": "Account can be reactivated by contacting support"
    }
