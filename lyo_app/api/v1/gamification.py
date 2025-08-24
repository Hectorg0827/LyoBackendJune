"""
Production gamification API routes.
Achievement tracking, badges, and progress systems.
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
from lyo_app.models.production import User, Badge, UserProfile
from lyo_app.auth.production import require_user
from lyo_app.tasks.gamification import check_achievements

logger = logging.getLogger(__name__)

router = APIRouter()


# Response models
class BadgeResponse(BaseModel):
    id: str
    name: str
    description: str
    icon: str = None
    category: str
    requirements: Dict[str, Any] = None
    earned_at: str = None
    
    class Config:
        from_attributes = True


class ProfileStatsResponse(BaseModel):
    total_courses_completed: int = 0
    total_lessons_completed: int = 0
    total_study_time_hours: float = 0.0
    current_streak_days: int = 0
    longest_streak_days: int = 0
    badges_earned: int = 0
    level: int = 1
    experience_points: int = 0


class LeaderboardEntry(BaseModel):
    rank: int
    user_id: str
    username: str = None
    full_name: str = None
    score: int
    badges_count: int


class AchievementResponse(BaseModel):
    id: str
    name: str
    description: str
    category: str
    progress: float = 0.0
    completed: bool = False
    requirements: Dict[str, Any] = None
    reward: Dict[str, Any] = None


@router.get("/profile", response_model=ProfileStatsResponse)
async def get_user_profile_stats(
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get user's gamification profile and stats.
    """
    try:
        # Get user profile with badges
        query = select(UserProfile).options(
            selectinload(UserProfile.badges)
        ).where(UserProfile.user_id == current_user.id)
        
        result = await db.execute(query)
        profile = result.scalar_one_or_none()
        
        if not profile:
            # Create default profile
            profile = UserProfile(
                user_id=current_user.id,
                learning_preferences={"created": "auto"}
            )
            db.add(profile)
            await db.commit()
            await db.refresh(profile)
        
        # Calculate stats
        stats = ProfileStatsResponse(
            total_courses_completed=profile.total_courses_completed,
            total_lessons_completed=profile.total_lessons_completed,
            total_study_time_hours=profile.total_study_time_hours,
            current_streak_days=profile.current_streak_days,
            longest_streak_days=profile.longest_streak_days,
            badges_earned=len(profile.badges) if profile.badges else 0,
            level=profile.level,
            experience_points=profile.experience_points
        )
        
        return stats
        
    except Exception as e:
        logger.error(f"Profile stats error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get profile stats")


@router.get("/badges", response_model=List[BadgeResponse])
async def get_user_badges(
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
    earned_only: bool = Query(False)
):
    """
    Get user's badges (earned and available).
    """
    try:
        if earned_only:
            # Get only earned badges
            query = select(Badge).join(
                Badge.users
            ).where(Badge.users.any(id=current_user.id))
        else:
            # Get all badges
            query = select(Badge)
        
        query = query.order_by(Badge.category, Badge.name)
        
        result = await db.execute(query)
        badges = result.scalars().all()
        
        # Get user's earned badges
        earned_query = select(Badge).join(
            Badge.users
        ).where(Badge.users.any(id=current_user.id))
        
        earned_result = await db.execute(earned_query)
        earned_badges = {str(badge.id): badge for badge in earned_result.scalars().all()}
        
        # Format response
        badge_responses = []
        for badge in badges:
            badge_id = str(badge.id)
            earned_badge = earned_badges.get(badge_id)
            
            badge_responses.append(BadgeResponse(
                id=badge_id,
                name=badge.name,
                description=badge.description,
                icon=badge.icon,
                category=badge.category,
                requirements=badge.requirements,
                earned_at=earned_badge.created_at.isoformat() if earned_badge else None
            ))
        
        return badge_responses
        
    except Exception as e:
        logger.error(f"Badges retrieval error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get badges")


@router.get("/achievements", response_model=List[AchievementResponse])
async def get_achievements(
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get user's achievements and progress.
    """
    try:
        # Get user profile
        query = select(UserProfile).where(UserProfile.user_id == current_user.id)
        result = await db.execute(query)
        profile = result.scalar_one_or_none()
        
        if not profile:
            # Create default profile
            profile = UserProfile(
                user_id=current_user.id,
                learning_preferences={"created": "auto"}
            )
            db.add(profile)
            await db.commit()
            await db.refresh(profile)
        
        # Define achievements
        achievements = [
            {
                "id": "first_course",
                "name": "First Steps",
                "description": "Complete your first course",
                "category": "learning",
                "target": 1,
                "current": profile.total_courses_completed,
                "reward": {"xp": 100, "badge": "Beginner"}
            },
            {
                "id": "streak_7",
                "name": "Week Warrior",
                "description": "Maintain a 7-day learning streak",
                "category": "consistency",
                "target": 7,
                "current": profile.current_streak_days,
                "reward": {"xp": 200, "badge": "Consistent"}
            },
            {
                "id": "lessons_50",
                "name": "Lesson Master",
                "description": "Complete 50 lessons",
                "category": "learning",
                "target": 50,
                "current": profile.total_lessons_completed,
                "reward": {"xp": 500, "badge": "Scholar"}
            },
            {
                "id": "study_time_20",
                "name": "Time Keeper",
                "description": "Study for 20 hours total",
                "category": "dedication",
                "target": 20,
                "current": profile.total_study_time_hours,
                "reward": {"xp": 300, "badge": "Dedicated"}
            }
        ]
        
        # Format achievements
        achievement_responses = []
        for ach in achievements:
            progress = min(ach["current"] / ach["target"], 1.0) if ach["target"] > 0 else 0.0
            completed = progress >= 1.0
            
            achievement_responses.append(AchievementResponse(
                id=ach["id"],
                name=ach["name"],
                description=ach["description"],
                category=ach["category"],
                progress=progress,
                completed=completed,
                requirements={"target": ach["target"], "current": ach["current"]},
                reward=ach["reward"]
            ))
        
        return achievement_responses
        
    except Exception as e:
        logger.error(f"Achievements error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get achievements")


@router.get("/leaderboard", response_model=List[LeaderboardEntry])
async def get_leaderboard(
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(10, ge=1, le=50),
    timeframe: str = Query("all_time", pattern="^(daily|weekly|monthly|all_time)$")
):
    """
    Get leaderboard rankings.
    """
    try:
        # Get top users by experience points
        query = select(
            UserProfile.user_id,
            UserProfile.experience_points,
            User.username,
            User.full_name
        ).join(
            User, UserProfile.user_id == User.id
        ).order_by(
            UserProfile.experience_points.desc()
        ).limit(limit)
        
        result = await db.execute(query)
        leaderboard_data = result.all()
        
        # Get badge counts for each user
        badge_counts = {}
        for row in leaderboard_data:
            user_id = row.user_id
            badge_query = select(func.count(Badge.id)).join(
                Badge.users
            ).where(Badge.users.any(id=user_id))
            
            badge_result = await db.execute(badge_query)
            badge_counts[str(user_id)] = badge_result.scalar() or 0
        
        # Format leaderboard
        leaderboard = []
        for rank, row in enumerate(leaderboard_data, 1):
            leaderboard.append(LeaderboardEntry(
                rank=rank,
                user_id=str(row.user_id),
                username=row.username,
                full_name=row.full_name,
                score=row.experience_points,
                badges_count=badge_counts.get(str(row.user_id), 0)
            ))
        
        return leaderboard
        
    except Exception as e:
        logger.error(f"Leaderboard error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get leaderboard")


@router.post("/check-achievements")
async def trigger_achievement_check(
    current_user: User = Depends(require_user)
):
    """
    Manually trigger achievement check for the user.
    """
    try:
        # Start achievement check task
        task = check_achievements.delay(str(current_user.id))
        
        logger.info(f"Achievement check triggered for user: {current_user.email}")
        
        return {
            "message": "Achievement check started",
            "task_id": task.id
        }
        
    except Exception as e:
        logger.error(f"Achievement check error: {e}")
        raise HTTPException(status_code=500, detail="Achievement check failed")


@router.post("/update-progress")
async def update_learning_progress(
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
    action: str = Query(..., pattern="^(course_completed|lesson_completed|study_session)$"),
    value: int = Query(1, ge=0)
):
    """
    Update learning progress for gamification.
    """
    try:
        # Get or create user profile
        query = select(UserProfile).where(UserProfile.user_id == current_user.id)
        result = await db.execute(query)
        profile = result.scalar_one_or_none()
        
        if not profile:
            profile = UserProfile(
                user_id=current_user.id,
                learning_preferences={"created": "auto"}
            )
            db.add(profile)
        
        # Update based on action
        if action == "course_completed":
            profile.total_courses_completed += value
            profile.experience_points += 100 * value
            
        elif action == "lesson_completed":
            profile.total_lessons_completed += value
            profile.experience_points += 25 * value
            
        elif action == "study_session":
            profile.total_study_time_hours += value / 60.0  # value is in minutes
            profile.experience_points += max(1, value // 10)  # 1 XP per 10 minutes
            
            # Update streak logic could go here
            profile.current_streak_days = max(profile.current_streak_days, 1)
        
        # Update level based on experience
        new_level = max(1, profile.experience_points // 500)  # 500 XP per level
        if new_level > profile.level:
            profile.level = new_level
            logger.info(f"User {current_user.email} leveled up to {new_level}")
        
        await db.commit()
        
        # Trigger achievement check
        check_achievements.delay(str(current_user.id))
        
        return {
            "message": "Progress updated successfully",
            "experience_points": profile.experience_points,
            "level": profile.level
        }
        
    except Exception as e:
        logger.error(f"Progress update error: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update progress")
