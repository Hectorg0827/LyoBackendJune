"""Gamification API endpoints for achievements, points, and leaderboards."""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from enum import Enum

from fastapi import APIRouter, Depends, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, and_
from pydantic import BaseModel, Field

from lyo_app.core.database import get_db_session
from lyo_app.auth.jwt_auth import require_active_user
from lyo_app.models.enhanced import User, GamificationProfile, Course, Task
from lyo_app.core.problems import NotFoundProblem, ValidationProblem

router = APIRouter()


class AchievementType(str, Enum):
    """Types of achievements."""
    COURSE_COMPLETION = "course_completion"
    STREAK_MILESTONE = "streak_milestone"
    POINTS_MILESTONE = "points_milestone"
    COMMUNITY_ENGAGEMENT = "community_engagement"
    LEARNING_CONSISTENCY = "learning_consistency"
    SKILL_MASTERY = "skill_mastery"


class AchievementResponse(BaseModel):
    """Response model for achievements."""
    id: str
    title: str
    description: str
    achievement_type: str
    icon_url: Optional[str]
    points_reward: int
    unlocked_at: Optional[datetime]
    progress_current: int
    progress_target: int
    is_unlocked: bool
    rarity: str  # common, rare, epic, legendary


class GamificationProfileResponse(BaseModel):
    """Response model for gamification profile."""
    user_id: str
    level: int
    total_points: int
    current_streak: int
    longest_streak: int
    achievements_unlocked: int
    achievements_total: int
    level_progress_current: int
    level_progress_target: int
    rank_position: Optional[int]
    badges: List[Dict[str, Any]]


class LeaderboardEntry(BaseModel):
    """Response model for leaderboard entries."""
    user_id: str
    username: str
    avatar_url: Optional[str]
    points: int
    level: int
    rank: int
    achievements_count: int


class LeaderboardResponse(BaseModel):
    """Response model for leaderboards."""
    leaderboard_type: str
    timeframe: str
    entries: List[LeaderboardEntry]
    current_user_rank: Optional[int]
    total_participants: int


@router.get("/profile", response_model=GamificationProfileResponse, summary="Get user gamification profile")
async def get_gamification_profile(
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session)
) -> GamificationProfileResponse:
    """Get the current user's gamification profile with stats and progress."""
    
    # Get or create gamification profile
    result = await db.execute(
        select(GamificationProfile).where(GamificationProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()
    
    if not profile:
        # Create default profile
        profile = GamificationProfile(
            user_id=current_user.id,
            total_points=0,
            level=1,
            achievements=[],
            streak_days=0,
            metadata={}
        )
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
    
    # Calculate level progress
    current_level_points = profile.level * 1000  # Simple level calculation
    next_level_points = (profile.level + 1) * 1000
    level_progress_current = max(0, profile.total_points - current_level_points)
    level_progress_target = next_level_points - current_level_points
    
    # Get total achievements count (would be from a predefined set in production)
    total_achievements = 50  # Placeholder
    
    # Get user rank (simplified calculation)
    rank_result = await db.execute(
        select(func.count(GamificationProfile.user_id)).where(
            GamificationProfile.total_points > profile.total_points
        )
    )
    rank_position = (rank_result.scalar() or 0) + 1
    
    return GamificationProfileResponse(
        user_id=str(profile.user_id),
        level=profile.level,
        total_points=profile.total_points,
        current_streak=profile.streak_days,
        longest_streak=profile.metadata.get("longest_streak", profile.streak_days) if profile.metadata else profile.streak_days,
        achievements_unlocked=len(profile.achievements),
        achievements_total=total_achievements,
        level_progress_current=level_progress_current,
        level_progress_target=level_progress_target,
        rank_position=rank_position,
        badges=profile.metadata.get("badges", []) if profile.metadata else []
    )


@router.get("/achievements", response_model=List[AchievementResponse], summary="Get user achievements")
async def get_user_achievements(
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session),
    show_locked: bool = Query(True, description="Include locked achievements")
) -> List[AchievementResponse]:
    """Get all achievements for the current user, including locked ones."""
    
    # Get user's gamification profile
    result = await db.execute(
        select(GamificationProfile).where(GamificationProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()
    
    user_achievements = profile.achievements if profile else []
    
    # Define available achievements (in production, these would be in the database)
    all_achievements = [
        {
            "id": "first_course",
            "title": "First Steps",
            "description": "Complete your first course",
            "achievement_type": AchievementType.COURSE_COMPLETION.value,
            "icon_url": "/icons/achievements/first_course.svg",
            "points_reward": 100,
            "progress_target": 1,
            "rarity": "common"
        },
        {
            "id": "course_master_5",
            "title": "Course Master",
            "description": "Complete 5 courses",
            "achievement_type": AchievementType.COURSE_COMPLETION.value,
            "icon_url": "/icons/achievements/course_master.svg",
            "points_reward": 500,
            "progress_target": 5,
            "rarity": "rare"
        },
        {
            "id": "streak_week",
            "title": "Weekly Warrior",
            "description": "Maintain a 7-day learning streak",
            "achievement_type": AchievementType.STREAK_MILESTONE.value,
            "icon_url": "/icons/achievements/streak_week.svg",
            "points_reward": 300,
            "progress_target": 7,
            "rarity": "rare"
        },
        {
            "id": "points_1000",
            "title": "Point Collector",
            "description": "Earn 1000 total points",
            "achievement_type": AchievementType.POINTS_MILESTONE.value,
            "icon_url": "/icons/achievements/points_1000.svg",
            "points_reward": 200,
            "progress_target": 1000,
            "rarity": "common"
        },
        {
            "id": "community_contributor",
            "title": "Community Helper",
            "description": "Help others by posting 10 helpful comments",
            "achievement_type": AchievementType.COMMUNITY_ENGAGEMENT.value,
            "icon_url": "/icons/achievements/community.svg",
            "points_reward": 400,
            "progress_target": 10,
            "rarity": "rare"
        }
    ]
    
    # Calculate progress for each achievement
    achievements = []
    
    # Get user stats for progress calculation
    courses_result = await db.execute(
        select(func.count(Course.id)).where(
            Course.user_id == current_user.id,
            Course.completion_status == "completed"
        )
    )
    completed_courses = courses_result.scalar() or 0
    
    for achievement in all_achievements:
        # Check if user has unlocked this achievement
        user_achievement = next(
            (ua for ua in user_achievements if ua.get("achievement_id") == achievement["id"]),
            None
        )
        
        is_unlocked = user_achievement is not None
        unlocked_at = None
        if is_unlocked and user_achievement:
            unlocked_at = datetime.fromisoformat(user_achievement["unlocked_at"])
        
        # Calculate progress
        progress_current = 0
        if achievement["achievement_type"] == AchievementType.COURSE_COMPLETION.value:
            progress_current = completed_courses
        elif achievement["achievement_type"] == AchievementType.POINTS_MILESTONE.value:
            progress_current = profile.total_points if profile else 0
        elif achievement["achievement_type"] == AchievementType.STREAK_MILESTONE.value:
            progress_current = profile.streak_days if profile else 0
        # Add more progress calculations as needed
        
        # Only show if unlocked or if showing locked achievements
        if is_unlocked or show_locked:
            achievements.append(AchievementResponse(
                id=achievement["id"],
                title=achievement["title"],
                description=achievement["description"],
                achievement_type=achievement["achievement_type"],
                icon_url=achievement["icon_url"],
                points_reward=achievement["points_reward"],
                unlocked_at=unlocked_at,
                progress_current=min(progress_current, achievement["progress_target"]),
                progress_target=achievement["progress_target"],
                is_unlocked=is_unlocked,
                rarity=achievement["rarity"]
            ))
    
    return achievements


@router.get("/leaderboard", response_model=LeaderboardResponse, summary="Get leaderboard")
async def get_leaderboard(
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session),
    leaderboard_type: str = Query("points", description="Leaderboard type: points, level, achievements"),
    timeframe: str = Query("all_time", description="Timeframe: all_time, monthly, weekly"),
    limit: int = Query(50, ge=1, le=200)
) -> LeaderboardResponse:
    """Get leaderboard rankings for various metrics."""
    
    # Build query based on leaderboard type
    if leaderboard_type == "points":
        query = select(
            GamificationProfile.user_id,
            GamificationProfile.total_points.label("score"),
            GamificationProfile.level,
            User.full_name.label("username"),
            User.profile_data
        ).join(User, GamificationProfile.user_id == User.id)
        
        query = query.order_by(desc(GamificationProfile.total_points))
        
    elif leaderboard_type == "level":
        query = select(
            GamificationProfile.user_id,
            GamificationProfile.level.label("score"),
            GamificationProfile.total_points,
            User.full_name.label("username"),
            User.profile_data
        ).join(User, GamificationProfile.user_id == User.id)
        
        query = query.order_by(desc(GamificationProfile.level), desc(GamificationProfile.total_points))
        
    else:  # achievements
        # For achievements, we'll count the number of achievements
        query = select(
            GamificationProfile.user_id,
            func.array_length(GamificationProfile.achievements, 1).label("score"),
            GamificationProfile.level,
            GamificationProfile.total_points,
            User.full_name.label("username"),
            User.profile_data
        ).join(User, GamificationProfile.user_id == User.id)
        
        query = query.order_by(desc(func.array_length(GamificationProfile.achievements, 1)))
    
    query = query.limit(limit)
    
    result = await db.execute(query)
    entries = result.fetchall()
    
    # Convert to leaderboard entries
    leaderboard_entries = []
    current_user_rank = None
    
    for rank, entry in enumerate(entries, 1):
        avatar_url = None
        if entry.profile_data:
            avatar_url = entry.profile_data.get("avatar_url")
        
        leaderboard_entry = LeaderboardEntry(
            user_id=str(entry.user_id),
            username=entry.username or "Anonymous",
            avatar_url=avatar_url,
            points=getattr(entry, 'total_points', entry.score) if leaderboard_type != 'points' else entry.score,
            level=getattr(entry, 'level', 1),
            rank=rank,
            achievements_count=entry.score if leaderboard_type == 'achievements' else 0
        )
        
        leaderboard_entries.append(leaderboard_entry)
        
        # Track current user's rank
        if entry.user_id == current_user.id:
            current_user_rank = rank
    
    return LeaderboardResponse(
        leaderboard_type=leaderboard_type,
        timeframe=timeframe,
        entries=leaderboard_entries,
        current_user_rank=current_user_rank,
        total_participants=len(entries)
    )


@router.post("/award-points", summary="Award points to user (internal)")
async def award_points(
    user_id: str,
    points: int = Field(..., ge=0, description="Points to award"),
    reason: str = Field(..., description="Reason for awarding points"),
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """
    Award points to a user (internal endpoint for system use).
    
    In production, this would require admin permissions or be called
    by internal services when users complete actions.
    """
    
    # Get or create gamification profile
    result = await db.execute(
        select(GamificationProfile).where(GamificationProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    
    if not profile:
        profile = GamificationProfile(
            user_id=user_id,
            total_points=0,
            level=1,
            achievements=[],
            streak_days=0
        )
        db.add(profile)
    
    # Award points
    old_points = profile.total_points
    profile.total_points += points
    
    # Calculate level (simple formula: level = total_points / 1000 + 1)
    new_level = min(100, profile.total_points // 1000 + 1)
    level_up = new_level > profile.level
    profile.level = new_level
    
    await db.commit()
    
    # Check for new achievements in background
    background_tasks.add_task(
        _check_and_award_achievements,
        user_id,
        db
    )
    
    return {
        "message": f"Awarded {points} points to user",
        "user_id": user_id,
        "reason": reason,
        "old_points": old_points,
        "new_points": profile.total_points,
        "level_up": level_up,
        "new_level": profile.level if level_up else None
    }


async def _check_and_award_achievements(user_id: str, db: AsyncSession):
    """Background task to check and award achievements."""
    
    # Get user's profile and stats
    result = await db.execute(
        select(GamificationProfile).where(GamificationProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    
    if not profile:
        return
    
    # Get user's completed courses count
    courses_result = await db.execute(
        select(func.count(Course.id)).where(
            Course.user_id == user_id,
            Course.completion_status == "completed"
        )
    )
    completed_courses = courses_result.scalar() or 0
    
    current_achievements = profile.achievements or []
    current_achievement_ids = [a.get("achievement_id") for a in current_achievements]
    new_achievements = []
    
    # Check for first course achievement
    if completed_courses >= 1 and "first_course" not in current_achievement_ids:
        new_achievements.append({
            "achievement_id": "first_course",
            "unlocked_at": datetime.utcnow().isoformat(),
            "points_awarded": 100
        })
        profile.total_points += 100
    
    # Check for course master achievement
    if completed_courses >= 5 and "course_master_5" not in current_achievement_ids:
        new_achievements.append({
            "achievement_id": "course_master_5",
            "unlocked_at": datetime.utcnow().isoformat(),
            "points_awarded": 500
        })
        profile.total_points += 500
    
    # Check for points milestone
    if profile.total_points >= 1000 and "points_1000" not in current_achievement_ids:
        new_achievements.append({
            "achievement_id": "points_1000",
            "unlocked_at": datetime.utcnow().isoformat(),
            "points_awarded": 200
        })
        profile.total_points += 200
    
    # Check for streak achievements
    if profile.streak_days >= 7 and "streak_week" not in current_achievement_ids:
        new_achievements.append({
            "achievement_id": "streak_week",
            "unlocked_at": datetime.utcnow().isoformat(),
            "points_awarded": 300
        })
        profile.total_points += 300
    
    # Update profile with new achievements
    if new_achievements:
        profile.achievements = current_achievements + new_achievements
        
        # Recalculate level after bonus points
        profile.level = min(100, profile.total_points // 1000 + 1)
        
        await db.commit()
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Awarded {len(new_achievements)} new achievements to user {user_id}")


@router.get("/stats", summary="Get gamification statistics")
async def get_gamification_stats(
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    """Get global gamification statistics."""
    
    # Get total users with gamification profiles
    total_users_result = await db.execute(
        select(func.count(GamificationProfile.user_id))
    )
    total_users = total_users_result.scalar() or 0
    
    # Get total points awarded across platform
    total_points_result = await db.execute(
        select(func.sum(GamificationProfile.total_points))
    )
    total_points = total_points_result.scalar() or 0
    
    # Get highest level user
    highest_level_result = await db.execute(
        select(func.max(GamificationProfile.level))
    )
    highest_level = highest_level_result.scalar() or 1
    
    # Get user's rank
    user_profile_result = await db.execute(
        select(GamificationProfile).where(GamificationProfile.user_id == current_user.id)
    )
    user_profile = user_profile_result.scalar_one_or_none()
    
    user_rank = None
    if user_profile:
        rank_result = await db.execute(
            select(func.count(GamificationProfile.user_id)).where(
                GamificationProfile.total_points > user_profile.total_points
            )
        )
        user_rank = (rank_result.scalar() or 0) + 1
    
    return {
        "total_active_learners": total_users,
        "total_points_awarded": total_points,
        "highest_level_achieved": highest_level,
        "your_global_rank": user_rank,
        "achievements_available": 50,  # Placeholder
        "average_level": total_points / total_users / 1000 + 1 if total_users > 0 else 1
    }
