"""
Gamification API routes for XP, achievements, streaks, levels, and leaderboards.
Provides RESTful endpoints for engagement and progress tracking features.
"""

from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.core.database import get_db
from lyo_app.auth.routes import get_current_user
from lyo_app.auth.models import User
from lyo_app.gamification.service import GamificationService
from lyo_app.gamification.schemas import (
    XPRecordCreate, XPRecordRead, XPSummaryRead,
    AchievementCreate, AchievementUpdate, AchievementRead,
    UserAchievementCreate, UserAchievementUpdate, UserAchievementRead,
    StreakRead, StreakUpdate,
    UserLevelRead, LeaderboardRead, LeaderboardEntryRead,
    BadgeCreate, BadgeUpdate, BadgeRead,
    UserBadgeCreate, UserBadgeUpdate, UserBadgeRead,
    UserStatsRead
)
from lyo_app.gamification.models import (
    XPActionType, AchievementType, StreakType
)

router = APIRouter()
gamification_service = GamificationService()


# XP Endpoints
@router.post("/xp/award", response_model=XPRecordRead, status_code=status.HTTP_201_CREATED)
async def award_xp(
    xp_data: XPRecordCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Award XP to the current user (typically called by system)."""
    try:
        xp_record = await gamification_service.award_xp(
            db=db,
            user_id=current_user.id,
            action_type=xp_data.action_type,
            context_type=xp_data.context_type,
            context_id=xp_data.context_id,
            context_data=xp_data.context_data,
            custom_xp=xp_data.xp_earned if xp_data.xp_earned > 0 else None
        )
        return xp_record
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to award XP")


@router.get("/xp/summary", response_model=XPSummaryRead)
async def get_xp_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get XP summary for the current user."""
    try:
        summary = await gamification_service.get_user_xp_summary(db, current_user.id)
        return summary
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get XP summary")


# Achievement Endpoints
@router.post("/achievements", response_model=AchievementRead, status_code=status.HTTP_201_CREATED)
async def create_achievement(
    achievement_data: AchievementCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new achievement (admin only)."""
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    
    try:
        achievement = await gamification_service.create_achievement(db, achievement_data)
        return achievement
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create achievement")


@router.get("/achievements", response_model=List[AchievementRead])
async def list_achievements(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    achievement_type: Optional[AchievementType] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List achievements with optional filtering."""
    try:
        achievements = await gamification_service.get_achievements(
            db=db,
            skip=skip,
            limit=limit,
            achievement_type=achievement_type,
            user_id=current_user.id
        )
        return achievements
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch achievements")


@router.get("/achievements/{achievement_id}", response_model=AchievementRead)
async def get_achievement(
    achievement_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific achievement."""
    try:
        achievements = await gamification_service.get_achievements(
            db=db, skip=0, limit=1, user_id=current_user.id
        )
        achievement = next((a for a in achievements if a.id == achievement_id), None)
        if not achievement:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Achievement not found")
        return achievement
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch achievement")


@router.put("/achievements/{achievement_id}", response_model=AchievementRead)
async def update_achievement(
    achievement_id: int,
    achievement_data: AchievementUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update an achievement (admin only)."""
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    
    try:
        # Implementation would go here - simplified for now
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Update not implemented yet")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update achievement")


# User Achievement Endpoints
@router.get("/my-achievements", response_model=List[UserAchievementRead])
async def get_my_achievements(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    completed_only: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current user's achievements."""
    try:
        # Implementation would fetch user achievements
        # Simplified for now
        return []
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch user achievements")


@router.post("/achievements/{achievement_id}/check", response_model=List[UserAchievementRead])
async def check_achievement_progress(
    achievement_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Check and update progress on a specific achievement."""
    try:
        awarded = await gamification_service.check_and_award_achievements(
            db=db,
            user_id=current_user.id,
            action_type=XPActionType.PROFILE_COMPLETED,  # Generic check
            context_data={"manual_check": True, "achievement_id": achievement_id}
        )
        return awarded
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to check achievement")


# Streak Endpoints
@router.get("/streaks", response_model=List[StreakRead])
async def get_my_streaks(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current user's streaks."""
    try:
        streaks = await gamification_service.get_user_streaks(db, current_user.id)
        return streaks
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch streaks")


@router.post("/streaks/{streak_type}/update", response_model=StreakRead)
async def update_streak(
    streak_type: StreakType,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a specific streak type."""
    try:
        streak = await gamification_service.update_streak(db, current_user.id, streak_type)
        return streak
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update streak")


# Level Endpoints
@router.get("/level", response_model=UserLevelRead)
async def get_my_level(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current user's level information."""
    try:
        user_level = await gamification_service.get_user_level(db, current_user.id)
        
        # Calculate computed fields
        total_xp_for_level = gamification_service._xp_for_level(user_level.current_level)
        xp_for_current_level = user_level.total_xp - total_xp_for_level
        xp_for_next_level = gamification_service._xp_for_level(user_level.current_level + 1) - total_xp_for_level
        level_progress_percentage = (xp_for_current_level / xp_for_next_level) * 100 if xp_for_next_level > 0 else 0
        
        # Add computed fields to response
        user_level.level_progress_percentage = level_progress_percentage
        user_level.xp_for_current_level = xp_for_current_level
        
        return user_level
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch user level")


# Leaderboard Endpoints
@router.get("/leaderboards/{leaderboard_type}", response_model=LeaderboardRead)
async def get_leaderboard(
    leaderboard_type: str,
    scope: str = Query("global"),
    scope_id: Optional[int] = Query(None),
    period: str = Query("all_time"),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get leaderboard for a specific type."""
    valid_types = ["xp", "achievements", "streaks"]
    if leaderboard_type not in valid_types:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid leaderboard type")
    
    valid_periods = ["daily", "weekly", "monthly", "all_time"]
    if period not in valid_periods:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid period")
    
    try:
        entries = await gamification_service.get_leaderboard(
            db=db,
            leaderboard_type=leaderboard_type,
            scope=scope,
            scope_id=scope_id,
            period=period,
            limit=limit
        )
        
        return {
            "leaderboard_type": leaderboard_type,
            "scope": scope,
            "period": period,
            "total_entries": len(entries),
            "last_updated": datetime.utcnow(),
            "entries": entries
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch leaderboard")


@router.get("/leaderboards/{leaderboard_type}/my-rank", response_model=dict)
async def get_my_leaderboard_rank(
    leaderboard_type: str,
    scope: str = Query("global"),
    scope_id: Optional[int] = Query(None),
    period: str = Query("all_time"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current user's rank in a leaderboard."""
    try:
        entries = await gamification_service.get_leaderboard(
            db=db,
            leaderboard_type=leaderboard_type,
            scope=scope,
            scope_id=scope_id,
            period=period,
            limit=1000  # Get more entries to find user's rank
        )
        
        user_entry = next((e for e in entries if e.user_id == current_user.id), None)
        
        if user_entry:
            return {
                "rank": user_entry.rank,
                "score": user_entry.score,
                "total_participants": len(entries),
                "percentile": (1 - (user_entry.rank - 1) / len(entries)) * 100 if entries else 0
            }
        else:
            return {
                "rank": None,
                "score": 0,
                "total_participants": len(entries),
                "percentile": 0
            }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch rank")


# Badge Endpoints
@router.post("/badges", response_model=BadgeRead, status_code=status.HTTP_201_CREATED)
async def create_badge(
    badge_data: BadgeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new badge (admin only)."""
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    
    try:
        badge = await gamification_service.create_badge(db, badge_data)
        return badge
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create badge")


@router.get("/my-badges", response_model=List[UserBadgeRead])
async def get_my_badges(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current user's badges."""
    try:
        badges = await gamification_service.get_user_badges(db, current_user.id)
        return badges
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch badges")


@router.post("/badges/{badge_id}/award", response_model=UserBadgeRead, status_code=status.HTTP_201_CREATED)
async def award_badge(
    badge_id: int,
    target_user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Award a badge to a user (admin only)."""
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    
    try:
        user_badge = await gamification_service.award_badge(db, target_user_id, badge_id)
        return user_badge
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to award badge")


@router.put("/my-badges/{badge_id}", response_model=UserBadgeRead)
async def update_my_badge(
    badge_id: int,
    badge_data: UserBadgeUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update user's badge settings (e.g., equip/unequip)."""
    try:
        # Implementation would update user badge settings
        # Simplified for now
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Badge update not implemented yet")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update badge")


# Statistics and Overview Endpoints
@router.get("/stats", response_model=UserStatsRead)
async def get_my_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get comprehensive gamification statistics for current user."""
    try:
        stats = await gamification_service.get_user_stats(db, current_user.id)
        return stats
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch stats")


@router.get("/overview", response_model=dict)
async def get_gamification_overview(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get gamification overview with all key metrics."""
    try:
        # Get user stats
        stats = await gamification_service.get_user_stats(db, current_user.id)
        
        # Get user level
        user_level = await gamification_service.get_user_level(db, current_user.id)
        
        # Get XP summary
        xp_summary = await gamification_service.get_user_xp_summary(db, current_user.id)
        
        # Get recent badges
        badges = await gamification_service.get_user_badges(db, current_user.id)
        recent_badges = badges[:3]  # Last 3 badges
        
        return {
            "user_level": {
                "level": user_level.current_level,
                "total_xp": user_level.total_xp,
                "xp_to_next_level": user_level.xp_to_next_level,
                "progress_percentage": (user_level.total_xp / (user_level.total_xp + user_level.xp_to_next_level)) * 100
            },
            "xp_summary": {
                "total": xp_summary["total_xp"],
                "today": xp_summary["xp_today"],
                "this_week": xp_summary["xp_this_week"]
            },
            "achievements": {
                "completed": stats["achievements_completed"],
                "recent": [{"id": ua.achievement_id, "name": ua.achievement.name if ua.achievement else "Unknown"} 
                          for ua in stats["recent_achievements"][:3]]
            },
            "streaks": {
                "current": stats["current_streak"],
                "longest": stats["longest_streak"]
            },
            "badges": {
                "total": stats["badges_earned"],
                "recent": [{"id": ub.badge_id, "name": ub.badge.name if ub.badge else "Unknown"} 
                          for ub in recent_badges]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch overview")


# System/Integration Endpoints (for internal use)
@router.post("/system/award-xp", response_model=XPRecordRead, status_code=status.HTTP_201_CREATED)
async def system_award_xp(
    user_id: int,
    action_type: XPActionType,
    context_type: Optional[str] = None,
    context_id: Optional[int] = None,
    context_data: Optional[dict] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """System endpoint for awarding XP (internal use, admin only)."""
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    
    try:
        xp_record = await gamification_service.award_xp(
            db=db,
            user_id=user_id,
            action_type=action_type,
            context_type=context_type,
            context_id=context_id,
            context_data=context_data
        )
        return xp_record
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to award XP")


@router.post("/system/check-achievements", response_model=List[UserAchievementRead])
async def system_check_achievements(
    user_id: int,
    action_type: XPActionType,
    context_data: Optional[dict] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """System endpoint for checking achievements (internal use, admin only)."""
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    
    try:
        awarded = await gamification_service.check_and_award_achievements(
            db=db,
            user_id=user_id,
            action_type=action_type,
            context_data=context_data
        )
        return awarded
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to check achievements")
