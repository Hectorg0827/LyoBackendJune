"""
Gamification service implementation.
Handles XP tracking, achievements, streaks, levels, and leaderboards.
"""

from datetime import datetime, timedelta, date
from typing import List, Optional, Dict, Any, Tuple
from collections import defaultdict

from sqlalchemy import select, func, and_, or_, desc, asc, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from lyo_app.gamification.models import (
    UserXP, Achievement, UserAchievement, Streak, UserLevel, 
    LeaderboardEntry, Badge, UserBadge,
    XPActionType, AchievementType, StreakType
)
from lyo_app.gamification.schemas import (
    XPRecordCreate, AchievementCreate, AchievementUpdate,
    UserAchievementCreate, UserAchievementUpdate,
    StreakUpdate, BadgeCreate, BadgeUpdate,
    UserBadgeCreate, UserBadgeUpdate
)


class GamificationService:
    """Service class for gamification features - XP, achievements, streaks, levels."""

    # XP Configuration
    XP_VALUES = {
        XPActionType.LESSON_COMPLETED: 20,
        XPActionType.COURSE_COMPLETED: 100,
        XPActionType.POST_CREATED: 10,
        XPActionType.COMMENT_CREATED: 5,
        XPActionType.DAILY_LOGIN: 5,
        XPActionType.STREAK_MILESTONE: 25,
        XPActionType.STUDY_GROUP_JOINED: 15,
        XPActionType.EVENT_ATTENDED: 30,
        XPActionType.PROFILE_COMPLETED: 50,
        XPActionType.FIRST_ACHIEVEMENT: 20,
    }

    # Level Configuration
    BASE_XP_PER_LEVEL = 100
    LEVEL_MULTIPLIER = 1.2

    # XP Operations
    async def award_xp(
        self, 
        db: AsyncSession, 
        user_id: int, 
        action_type: XPActionType,
        context_type: Optional[str] = None,
        context_id: Optional[int] = None,
        context_data: Optional[Dict[str, Any]] = None,
        custom_xp: Optional[int] = None
    ) -> UserXP:
        """
        Award XP to a user for an action.
        
        Args:
            db: Database session
            user_id: User ID
            action_type: Type of action that earned XP
            context_type: Optional context type
            context_id: Optional context entity ID
            context_data: Optional additional context data
            custom_xp: Custom XP amount (overrides default)
            
        Returns:
            Created XP record
        """
        xp_amount = custom_xp or self.XP_VALUES.get(action_type, 0)
        
        # Check for daily XP limits to prevent abuse
        if action_type in [XPActionType.POST_CREATED, XPActionType.COMMENT_CREATED]:
            daily_xp = await self._get_daily_xp_for_action(db, user_id, action_type)
            max_daily_xp = 100  # Limit per action type per day
            if daily_xp + xp_amount > max_daily_xp:
                xp_amount = max(0, max_daily_xp - daily_xp)
        
        if xp_amount <= 0:
            raise ValueError("No XP to award or daily limit reached")
        
        # Create XP record
        xp_record = UserXP(
            user_id=user_id,
            action_type=action_type,
            xp_earned=xp_amount,
            context_type=context_type,
            context_id=context_id,
            context_data=context_data
        )
        db.add(xp_record)
        
        # Update user level
        await self._update_user_level(db, user_id, xp_amount)
        
        # Check for achievements
        await self._check_achievements(db, user_id, action_type, context_data)
        
        # Update streaks if applicable
        if action_type in [XPActionType.LESSON_COMPLETED, XPActionType.DAILY_LOGIN]:
            await self._update_streak(db, user_id, self._action_to_streak_type(action_type))
        
        await db.commit()
        return xp_record

    async def get_user_xp_summary(self, db: AsyncSession, user_id: int) -> Dict[str, Any]:
        """Get comprehensive XP summary for a user."""
        now = datetime.utcnow()
        today = now.date()
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)
        
        # Total XP
        total_xp_result = await db.execute(
            select(func.sum(UserXP.xp_earned))
            .where(UserXP.user_id == user_id)
        )
        total_xp = total_xp_result.scalar() or 0
        
        # XP by time period
        xp_today_result = await db.execute(
            select(func.sum(UserXP.xp_earned))
            .where(
                and_(
                    UserXP.user_id == user_id,
                    func.date(UserXP.earned_at) == today
                )
            )
        )
        xp_today = xp_today_result.scalar() or 0
        
        xp_week_result = await db.execute(
            select(func.sum(UserXP.xp_earned))
            .where(
                and_(
                    UserXP.user_id == user_id,
                    func.date(UserXP.earned_at) >= week_start
                )
            )
        )
        xp_this_week = xp_week_result.scalar() or 0
        
        xp_month_result = await db.execute(
            select(func.sum(UserXP.xp_earned))
            .where(
                and_(
                    UserXP.user_id == user_id,
                    func.date(UserXP.earned_at) >= month_start
                )
            )
        )
        xp_this_month = xp_month_result.scalar() or 0
        
        # XP by action type
        xp_by_action_result = await db.execute(
            select(UserXP.action_type, func.sum(UserXP.xp_earned))
            .where(UserXP.user_id == user_id)
            .group_by(UserXP.action_type)
        )
        xp_by_action = {row[0]: row[1] for row in xp_by_action_result}
        
        # Recent XP records
        recent_xp_result = await db.execute(
            select(UserXP)
            .where(UserXP.user_id == user_id)
            .order_by(desc(UserXP.earned_at))
            .limit(10)
        )
        recent_records = recent_xp_result.scalars().all()
        
        return {
            "total_xp": total_xp,
            "xp_today": xp_today,
            "xp_this_week": xp_this_week,
            "xp_this_month": xp_this_month,
            "xp_by_action": xp_by_action,
            "recent_records": recent_records
        }

    # Achievement Operations
    async def create_achievement(
        self, db: AsyncSession, achievement_data: AchievementCreate
    ) -> Achievement:
        """Create a new achievement."""
        # Validate criteria format
        if not self._validate_achievement_criteria(achievement_data.criteria):
            raise ValueError("Invalid achievement criteria format")
        
        achievement = Achievement(
            name=achievement_data.name,
            description=achievement_data.description,
            icon_url=achievement_data.icon_url,
            type=achievement_data.type,
            rarity=achievement_data.rarity,
            xp_reward=achievement_data.xp_reward,
            criteria=achievement_data.criteria
        )
        db.add(achievement)
        await db.commit()
        await db.refresh(achievement)
        return achievement

    async def get_achievements(
        self, 
        db: AsyncSession, 
        skip: int = 0, 
        limit: int = 50,
        achievement_type: Optional[AchievementType] = None,
        user_id: Optional[int] = None
    ) -> List[Achievement]:
        """Get achievements with optional filtering."""
        query = select(Achievement).where(Achievement.is_active == True)
        
        if achievement_type:
            query = query.where(Achievement.type == achievement_type)
        
        query = query.order_by(Achievement.rarity, Achievement.name).offset(skip).limit(limit)
        
        result = await db.execute(query)
        achievements = result.scalars().all()
        
        # If user_id provided, add progress information
        if user_id and achievements:
            achievement_ids = [a.id for a in achievements]
            user_achievements_result = await db.execute(
                select(UserAchievement)
                .where(
                    and_(
                        UserAchievement.user_id == user_id,
                        UserAchievement.achievement_id.in_(achievement_ids)
                    )
                )
            )
            user_achievements = {ua.achievement_id: ua for ua in user_achievements_result.scalars()}
            
            # Add progress to achievements
            for achievement in achievements:
                if achievement.id in user_achievements:
                    achievement.user_progress = user_achievements[achievement.id].progress_data
                    achievement.is_completed = user_achievements[achievement.id].is_completed
        
        return achievements

    async def check_and_award_achievements(
        self, db: AsyncSession, user_id: int, action_type: XPActionType, context_data: Optional[Dict] = None
    ) -> List[UserAchievement]:
        """Check and award achievements based on user actions."""
        return await self._check_achievements(db, user_id, action_type, context_data)

    # Streak Operations
    async def update_streak(
        self, db: AsyncSession, user_id: int, streak_type: StreakType
    ) -> Streak:
        """Update a user's streak."""
        return await self._update_streak(db, user_id, streak_type)

    async def get_user_streaks(self, db: AsyncSession, user_id: int) -> List[Streak]:
        """Get all streaks for a user."""
        result = await db.execute(
            select(Streak)
            .where(Streak.user_id == user_id)
            .order_by(desc(Streak.current_count))
        )
        return result.scalars().all()

    # Level Operations
    async def get_user_level(self, db: AsyncSession, user_id: int) -> UserLevel:
        """Get or create user level."""
        result = await db.execute(
            select(UserLevel).where(UserLevel.user_id == user_id)
        )
        user_level = result.scalar_one_or_none()
        
        if not user_level:
            user_level = UserLevel(user_id=user_id)
            db.add(user_level)
            await db.commit()
            await db.refresh(user_level)
        
        return user_level

    # Leaderboard Operations
    async def get_leaderboard(
        self, 
        db: AsyncSession, 
        leaderboard_type: str = "xp",
        scope: str = "global",
        scope_id: Optional[int] = None,
        period: str = "all_time",
        limit: int = 50
    ) -> List[LeaderboardEntry]:
        """Get leaderboard entries."""
        # First, update leaderboard for this request
        await self._update_leaderboard(db, leaderboard_type, scope, scope_id, period)
        
        query = select(LeaderboardEntry).where(
            and_(
                LeaderboardEntry.leaderboard_type == leaderboard_type,
                LeaderboardEntry.scope == scope,
                LeaderboardEntry.period == period
            )
        )
        
        if scope_id:
            query = query.where(LeaderboardEntry.scope_id == scope_id)
        
        query = query.order_by(asc(LeaderboardEntry.rank)).limit(limit)
        
        result = await db.execute(query)
        return result.scalars().all()

    # Badge Operations
    async def create_badge(self, db: AsyncSession, badge_data: BadgeCreate) -> Badge:
        """Create a new badge."""
        badge = Badge(
            name=badge_data.name,
            description=badge_data.description,
            icon_url=badge_data.icon_url,
            color=badge_data.color,
            category=badge_data.category,
            is_limited_time=badge_data.is_limited_time,
            valid_from=badge_data.valid_from,
            valid_until=badge_data.valid_until,
            requirements=badge_data.requirements
        )
        db.add(badge)
        await db.commit()
        await db.refresh(badge)
        return badge

    async def award_badge(self, db: AsyncSession, user_id: int, badge_id: int) -> UserBadge:
        """Award a badge to a user."""
        # Check if user already has this badge
        existing = await db.execute(
            select(UserBadge).where(
                and_(UserBadge.user_id == user_id, UserBadge.badge_id == badge_id)
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("User already has this badge")
        
        user_badge = UserBadge(user_id=user_id, badge_id=badge_id)
        db.add(user_badge)
        await db.commit()
        await db.refresh(user_badge)
        return user_badge

    async def get_user_badges(self, db: AsyncSession, user_id: int) -> List[UserBadge]:
        """Get all badges for a user."""
        result = await db.execute(
            select(UserBadge)
            .options(selectinload(UserBadge.badge))
            .where(UserBadge.user_id == user_id)
            .order_by(desc(UserBadge.earned_at))
        )
        return result.scalars().all()

    # Statistics and Analytics
    async def get_user_stats(self, db: AsyncSession, user_id: int) -> Dict[str, Any]:
        """Get comprehensive user gamification statistics."""
        # Get user level
        user_level = await self.get_user_level(db, user_id)
        
        # Get achievements count
        achievements_result = await db.execute(
            select(func.count(UserAchievement.id))
            .where(
                and_(
                    UserAchievement.user_id == user_id,
                    UserAchievement.is_completed == True
                )
            )
        )
        achievements_completed = achievements_result.scalar() or 0
        
        # Get badges count
        badges_result = await db.execute(
            select(func.count(UserBadge.id))
            .where(UserBadge.user_id == user_id)
        )
        badges_earned = badges_result.scalar() or 0
        
        # Get streak information
        streaks = await self.get_user_streaks(db, user_id)
        current_streak = max((s.current_count for s in streaks if s.is_active), default=0)
        longest_streak = max((s.longest_count for s in streaks), default=0)
        
        # Get recent achievements
        recent_achievements_result = await db.execute(
            select(UserAchievement)
            .options(selectinload(UserAchievement.achievement))
            .where(
                and_(
                    UserAchievement.user_id == user_id,
                    UserAchievement.is_completed == True
                )
            )
            .order_by(desc(UserAchievement.completed_at))
            .limit(5)
        )
        recent_achievements = recent_achievements_result.scalars().all()
        
        # Get XP summary
        xp_summary = await self.get_user_xp_summary(db, user_id)
        
        return {
            "total_xp": user_level.total_xp,
            "current_level": user_level.current_level,
            "achievements_completed": achievements_completed,
            "badges_earned": badges_earned,
            "longest_streak": longest_streak,
            "current_streak": current_streak,
            "recent_achievements": recent_achievements,
            "recent_xp_gains": xp_summary["recent_records"]
        }

    # Private Helper Methods
    async def _get_daily_xp_for_action(
        self, db: AsyncSession, user_id: int, action_type: XPActionType
    ) -> int:
        """Get XP earned today for a specific action type."""
        today = datetime.utcnow().date()
        result = await db.execute(
            select(func.sum(UserXP.xp_earned))
            .where(
                and_(
                    UserXP.user_id == user_id,
                    UserXP.action_type == action_type,
                    func.date(UserXP.earned_at) == today
                )
            )
        )
        return result.scalar() or 0

    async def _update_user_level(self, db: AsyncSession, user_id: int, xp_gained: int) -> UserLevel:
        """Update user level based on XP gained."""
        user_level = await self.get_user_level(db, user_id)
        
        user_level.total_xp += xp_gained
        levels_gained = 0
        
        while user_level.total_xp >= self._xp_for_level(user_level.current_level + 1):
            user_level.current_level += 1
            levels_gained += 1
            user_level.last_level_up = datetime.utcnow()
            
            # Award XP for level up
            if levels_gained == 1:  # First level up of the session
                await self.award_xp(
                    db, user_id, XPActionType.STREAK_MILESTONE, 
                    context_data={"level": user_level.current_level}
                )
        
        user_level.xp_to_next_level = self._xp_for_level(user_level.current_level + 1) - user_level.total_xp
        user_level.levels_gained_today += levels_gained
        user_level.updated_at = datetime.utcnow()
        
        await db.commit()
        return user_level

    def _xp_for_level(self, level: int) -> int:
        """Calculate total XP required for a given level."""
        if level <= 1:
            return 0
        return int(self.BASE_XP_PER_LEVEL * (self.LEVEL_MULTIPLIER ** (level - 2)))

    async def _check_achievements(
        self, db: AsyncSession, user_id: int, action_type: XPActionType, context_data: Optional[Dict] = None
    ) -> List[UserAchievement]:
        """Check and award achievements for user actions."""
        # This is a simplified achievement checking system
        # In a real implementation, you'd have more sophisticated criteria evaluation
        
        awarded_achievements = []
        
        # Get all active achievements that could be triggered by this action
        result = await db.execute(
            select(Achievement)
            .where(Achievement.is_active == True)
        )
        achievements = result.scalars().all()
        
        for achievement in achievements:
            # Check if user already has this achievement
            existing = await db.execute(
                select(UserAchievement).where(
                    and_(
                        UserAchievement.user_id == user_id,
                        UserAchievement.achievement_id == achievement.id
                    )
                )
            )
            user_achievement = existing.scalar_one_or_none()
            
            if user_achievement and user_achievement.is_completed:
                continue  # Already completed
            
            # Evaluate achievement criteria
            is_completed = await self._evaluate_achievement_criteria(
                db, user_id, achievement.criteria, action_type, context_data
            )
            
            if is_completed:
                if not user_achievement:
                    user_achievement = UserAchievement(
                        user_id=user_id,
                        achievement_id=achievement.id,
                        is_completed=True,
                        completed_at=datetime.utcnow()
                    )
                    db.add(user_achievement)
                else:
                    user_achievement.is_completed = True
                    user_achievement.completed_at = datetime.utcnow()
                
                # Award XP for achievement
                if achievement.xp_reward > 0:
                    await self.award_xp(
                        db, user_id, XPActionType.FIRST_ACHIEVEMENT,
                        custom_xp=achievement.xp_reward,
                        context_data={"achievement_id": achievement.id}
                    )
                
                awarded_achievements.append(user_achievement)
        
        await db.commit()
        return awarded_achievements

    async def _evaluate_achievement_criteria(
        self, db: AsyncSession, user_id: int, criteria: Dict[str, Any], 
        action_type: XPActionType, context_data: Optional[Dict] = None
    ) -> bool:
        """Evaluate if achievement criteria are met."""
        # Simplified criteria evaluation
        # Real implementation would be more sophisticated
        
        criteria_type = criteria.get("type")
        
        if criteria_type == "lesson_count":
            required_count = criteria.get("count", 0)
            # Count completed lessons
            result = await db.execute(
                select(func.count(UserXP.id))
                .where(
                    and_(
                        UserXP.user_id == user_id,
                        UserXP.action_type == XPActionType.LESSON_COMPLETED
                    )
                )
            )
            actual_count = result.scalar() or 0
            return actual_count >= required_count
        
        elif criteria_type == "total_xp":
            required_xp = criteria.get("xp", 0)
            user_level = await self.get_user_level(db, user_id)
            return user_level.total_xp >= required_xp
        
        elif criteria_type == "streak_days":
            required_days = criteria.get("days", 0)
            streak_type = StreakType(criteria.get("streak_type", "daily_login"))
            
            result = await db.execute(
                select(Streak)
                .where(
                    and_(
                        Streak.user_id == user_id,
                        Streak.streak_type == streak_type
                    )
                )
            )
            streak = result.scalar_one_or_none()
            return streak and streak.current_count >= required_days
        
        return False

    async def _update_streak(self, db: AsyncSession, user_id: int, streak_type: StreakType) -> Streak:
        """Update user streak."""
        result = await db.execute(
            select(Streak).where(
                and_(Streak.user_id == user_id, Streak.streak_type == streak_type)
            )
        )
        streak = result.scalar_one_or_none()
        
        if not streak:
            streak = Streak(
                user_id=user_id,
                streak_type=streak_type,
                current_count=1,
                longest_count=1,
                last_activity_date=datetime.utcnow(),
                is_active=True
            )
            db.add(streak)
        else:
            now = datetime.utcnow()
            last_activity = streak.last_activity_date
            
            if last_activity:
                days_diff = (now.date() - last_activity.date()).days
                
                if days_diff == 1:  # Consecutive day
                    streak.current_count += 1
                    streak.longest_count = max(streak.longest_count, streak.current_count)
                elif days_diff > 1:  # Streak broken
                    streak.current_count = 1
                # Same day - no change to count
            else:
                streak.current_count = 1
            
            streak.last_activity_date = now
            streak.updated_at = now
            streak.is_active = True
        
        await db.commit()
        return streak

    async def _update_leaderboard(
        self, db: AsyncSession, leaderboard_type: str, scope: str, 
        scope_id: Optional[int], period: str
    ) -> None:
        """Update leaderboard entries."""
        # This is a simplified leaderboard update
        # Real implementation would be more efficient with batch operations
        
        if leaderboard_type == "xp":
            # Calculate XP scores based on period
            if period == "all_time":
                scores_query = select(
                    UserXP.user_id,
                    func.sum(UserXP.xp_earned).label("score")
                ).group_by(UserXP.user_id)
            else:
                # Add time filtering for other periods
                scores_query = select(
                    UserXP.user_id,
                    func.sum(UserXP.xp_earned).label("score")
                ).group_by(UserXP.user_id)
            
            result = await db.execute(scores_query)
            scores = [(user_id, score) for user_id, score in result]
            scores.sort(key=lambda x: x[1], reverse=True)
            
            # Update leaderboard entries
            for rank, (user_id, score) in enumerate(scores, 1):
                # Check if entry exists
                existing_result = await db.execute(
                    select(LeaderboardEntry).where(
                        and_(
                            LeaderboardEntry.user_id == user_id,
                            LeaderboardEntry.leaderboard_type == leaderboard_type,
                            LeaderboardEntry.scope == scope,
                            LeaderboardEntry.period == period
                        )
                    )
                )
                entry = existing_result.scalar_one_or_none()
                
                if entry:
                    entry.score = score
                    entry.rank = rank
                    entry.updated_at = datetime.utcnow()
                else:
                    entry = LeaderboardEntry(
                        user_id=user_id,
                        leaderboard_type=leaderboard_type,
                        scope=scope,
                        scope_id=scope_id,
                        score=score,
                        rank=rank,
                        period=period
                    )
                    db.add(entry)
        
        await db.commit()

    def _action_to_streak_type(self, action_type: XPActionType) -> StreakType:
        """Convert XP action type to streak type."""
        mapping = {
            XPActionType.LESSON_COMPLETED: StreakType.LESSON_COMPLETION,
            XPActionType.DAILY_LOGIN: StreakType.DAILY_LOGIN,
        }
        return mapping.get(action_type, StreakType.DAILY_LOGIN)

    def _validate_achievement_criteria(self, criteria: Dict[str, Any]) -> bool:
        """Validate achievement criteria format."""
        if not isinstance(criteria, dict):
            return False
        
        criteria_type = criteria.get("type")
        valid_types = ["lesson_count", "total_xp", "streak_days", "course_count", "social_actions"]
        
        return criteria_type in valid_types
