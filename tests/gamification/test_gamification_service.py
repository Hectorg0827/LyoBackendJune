"""
Tests for the gamification service.
"""

import pytest
from datetime import datetime, timedelta
from typing import List

from lyo_app.gamification.service import GamificationService
from lyo_app.gamification.models import (
    UserXP, Achievement, UserAchievement, Streak, UserLevel, 
    LeaderboardEntry, Badge, UserBadge,
    AchievementType, XPSourceType, LeaderboardType, BadgeType
)
from lyo_app.gamification.schemas import (
    UserXPCreate, AchievementCreate, StreakCreate, 
    LeaderboardEntryCreate, BadgeCreate
)


@pytest.fixture
def gamification_service(async_session):
    """Create a gamification service instance."""
    return GamificationService(async_session)


@pytest.fixture
async def sample_user_id() -> str:
    """Sample user ID for testing."""
    return "test-user-123"


@pytest.fixture
async def sample_achievement(async_session) -> Achievement:
    """Create a sample achievement for testing."""
    achievement = Achievement(
        id="test-achievement-1",
        name="First Steps",
        description="Complete your first lesson",
        type=AchievementType.LEARNING,
        points_required=10,
        icon="🎯",
        is_active=True
    )
    async_session.add(achievement)
    await async_session.commit()
    await async_session.refresh(achievement)
    return achievement


@pytest.fixture
async def sample_badge(async_session) -> Badge:
    """Create a sample badge for testing."""
    badge = Badge(
        id="test-badge-1",
        name="Learner",
        description="Active learner badge",
        type=BadgeType.MILESTONE,
        criteria="Complete 5 lessons",
        icon="📚",
        color="#4CAF50",
        is_active=True
    )
    async_session.add(badge)
    await async_session.commit()
    await async_session.refresh(badge)
    return badge


class TestUserXPService:
    """Test XP-related service methods."""
    
    async def test_add_xp_new_user(self, gamification_service: GamificationService, sample_user_id: str):
        """Test adding XP for a new user."""
        xp_data = UserXPCreate(
            user_id=sample_user_id,
            points=50,
            source=XPSourceType.LESSON_COMPLETION,
            source_id="lesson-123"
        )
        
        user_xp = await gamification_service.add_xp(xp_data)
        
        assert user_xp.user_id == sample_user_id
        assert user_xp.points == 50
        assert user_xp.source == XPSourceType.LESSON_COMPLETION
        assert user_xp.source_id == "lesson-123"
    
    async def test_add_xp_existing_user(self, gamification_service: GamificationService, sample_user_id: str):
        """Test adding XP for an existing user."""
        # Add initial XP
        xp_data1 = UserXPCreate(
            user_id=sample_user_id,
            points=30,
            source=XPSourceType.LESSON_COMPLETION,
            source_id="lesson-1"
        )
        await gamification_service.add_xp(xp_data1)
        
        # Add more XP
        xp_data2 = UserXPCreate(
            user_id=sample_user_id,
            points=20,
            source=XPSourceType.QUIZ_COMPLETION,
            source_id="quiz-1"
        )
        user_xp = await gamification_service.add_xp(xp_data2)
        
        assert user_xp.points == 20
        
        # Check total XP
        total_xp = await gamification_service.get_user_total_xp(sample_user_id)
        assert total_xp == 50
    
    async def test_get_user_xp_history(self, gamification_service: GamificationService, sample_user_id: str):
        """Test getting user XP history."""
        # Add multiple XP entries
        for i in range(3):
            xp_data = UserXPCreate(
                user_id=sample_user_id,
                points=10 * (i + 1),
                source=XPSourceType.LESSON_COMPLETION,
                source_id=f"lesson-{i+1}"
            )
            await gamification_service.add_xp(xp_data)
        
        history = await gamification_service.get_user_xp_history(sample_user_id, limit=10)
        
        assert len(history) == 3
        # Should be in descending order by created_at
        assert history[0].points == 30
        assert history[1].points == 20
        assert history[2].points == 10


class TestAchievementService:
    """Test achievement-related service methods."""
    
    async def test_create_achievement(self, gamification_service: GamificationService):
        """Test creating an achievement."""
        achievement_data = AchievementCreate(
            name="Test Achievement",
            description="A test achievement",
            type=AchievementType.LEARNING,
            points_required=100,
            icon="🏆"
        )
        
        achievement = await gamification_service.create_achievement(achievement_data)
        
        assert achievement.name == "Test Achievement"
        assert achievement.type == AchievementType.LEARNING
        assert achievement.points_required == 100
        assert achievement.is_active is True
    
    async def test_award_achievement(
        self, 
        gamification_service: GamificationService, 
        sample_user_id: str, 
        sample_achievement: Achievement
    ):
        """Test awarding an achievement to a user."""
        user_achievement = await gamification_service.award_achievement(
            sample_user_id, 
            sample_achievement.id
        )
        
        assert user_achievement.user_id == sample_user_id
        assert user_achievement.achievement_id == sample_achievement.id
        assert user_achievement.awarded_at is not None
    
    async def test_check_and_award_achievements(
        self, 
        gamification_service: GamificationService, 
        sample_user_id: str,
        sample_achievement: Achievement
    ):
        """Test checking and awarding achievements based on XP."""
        # Add XP that meets achievement requirements
        xp_data = UserXPCreate(
            user_id=sample_user_id,
            points=15,  # More than the 10 required
            source=XPSourceType.LESSON_COMPLETION,
            source_id="lesson-1"
        )
        await gamification_service.add_xp(xp_data)
        
        # Check and award achievements
        awarded = await gamification_service.check_and_award_achievements(sample_user_id)
        
        assert len(awarded) == 1
        assert awarded[0].achievement_id == sample_achievement.id
    
    async def test_get_user_achievements(
        self, 
        gamification_service: GamificationService, 
        sample_user_id: str,
        sample_achievement: Achievement
    ):
        """Test getting user achievements."""
        # Award achievement
        await gamification_service.award_achievement(sample_user_id, sample_achievement.id)
        
        achievements = await gamification_service.get_user_achievements(sample_user_id)
        
        assert len(achievements) == 1
        assert achievements[0].achievement.name == sample_achievement.name


class TestStreakService:
    """Test streak-related service methods."""
    
    async def test_update_streak_new_user(self, gamification_service: GamificationService, sample_user_id: str):
        """Test updating streak for a new user."""
        streak_data = StreakCreate(
            user_id=sample_user_id,
            streak_type="daily_login"
        )
        
        streak = await gamification_service.update_streak(streak_data)
        
        assert streak.user_id == sample_user_id
        assert streak.streak_type == "daily_login"
        assert streak.current_count == 1
        assert streak.max_count == 1
        assert streak.last_activity_date.date() == datetime.utcnow().date()
    
    async def test_update_streak_consecutive_days(self, gamification_service: GamificationService, sample_user_id: str):
        """Test updating streak for consecutive days."""
        # Day 1
        streak_data = StreakCreate(
            user_id=sample_user_id,
            streak_type="daily_login"
        )
        streak1 = await gamification_service.update_streak(streak_data)
        assert streak1.current_count == 1
        
        # Simulate day 2 (manually update last_activity_date to yesterday)
        streak1.last_activity_date = datetime.utcnow() - timedelta(days=1)
        await gamification_service.session.commit()
        
        # Update streak for "today"
        streak2 = await gamification_service.update_streak(streak_data)
        assert streak2.current_count == 2
        assert streak2.max_count == 2
    
    async def test_get_user_streaks(self, gamification_service: GamificationService, sample_user_id: str):
        """Test getting user streaks."""
        # Create multiple streaks
        streak_types = ["daily_login", "lesson_completion", "quiz_completion"]
        for streak_type in streak_types:
            streak_data = StreakCreate(
                user_id=sample_user_id,
                streak_type=streak_type
            )
            await gamification_service.update_streak(streak_data)
        
        streaks = await gamification_service.get_user_streaks(sample_user_id)
        
        assert len(streaks) == 3
        streak_types_result = [s.streak_type for s in streaks]
        assert all(st in streak_types_result for st in streak_types)


class TestLevelService:
    """Test level-related service methods."""
    
    async def test_calculate_level_from_xp(self, gamification_service: GamificationService):
        """Test calculating user level from XP."""
        # Test different XP amounts
        test_cases = [
            (0, 1),      # 0 XP = Level 1
            (99, 1),     # 99 XP = Level 1
            (100, 2),    # 100 XP = Level 2
            (299, 2),    # 299 XP = Level 2
            (300, 3),    # 300 XP = Level 3
            (1000, 6),   # 1000 XP = Level 6
        ]
        
        for xp, expected_level in test_cases:
            level = await gamification_service.calculate_level_from_xp(xp)
            assert level == expected_level, f"XP {xp} should be level {expected_level}, got {level}"
    
    async def test_update_user_level(self, gamification_service: GamificationService, sample_user_id: str):
        """Test updating user level."""
        # Add XP to reach level 2
        xp_data = UserXPCreate(
            user_id=sample_user_id,
            points=150,
            source=XPSourceType.LESSON_COMPLETION,
            source_id="lesson-1"
        )
        await gamification_service.add_xp(xp_data)
        
        # Update user level
        user_level = await gamification_service.update_user_level(sample_user_id)
        
        assert user_level.user_id == sample_user_id
        assert user_level.current_level == 2
        assert user_level.total_xp == 150
    
    async def test_get_user_level(self, gamification_service: GamificationService, sample_user_id: str):
        """Test getting user level."""
        # Add XP and update level
        xp_data = UserXPCreate(
            user_id=sample_user_id,
            points=250,
            source=XPSourceType.LESSON_COMPLETION,
            source_id="lesson-1"
        )
        await gamification_service.add_xp(xp_data)
        await gamification_service.update_user_level(sample_user_id)
        
        user_level = await gamification_service.get_user_level(sample_user_id)
        
        assert user_level is not None
        assert user_level.current_level == 3
        assert user_level.total_xp == 250


class TestLeaderboardService:
    """Test leaderboard-related service methods."""
    
    async def test_update_leaderboard_entry(self, gamification_service: GamificationService):
        """Test updating leaderboard entry."""
        entry_data = LeaderboardEntryCreate(
            user_id="user-1",
            leaderboard_type=LeaderboardType.XP_WEEKLY,
            score=100,
            period_start=datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0),
            period_end=datetime.utcnow().replace(hour=23, minute=59, second=59, microsecond=999999)
        )
        
        entry = await gamification_service.update_leaderboard_entry(entry_data)
        
        assert entry.user_id == "user-1"
        assert entry.leaderboard_type == LeaderboardType.XP_WEEKLY
        assert entry.score == 100
        assert entry.rank == 1  # First entry should be rank 1
    
    async def test_get_leaderboard(self, gamification_service: GamificationService):
        """Test getting leaderboard."""
        # Create multiple entries
        users_scores = [("user-1", 100), ("user-2", 200), ("user-3", 150)]
        period_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        period_end = datetime.utcnow().replace(hour=23, minute=59, second=59, microsecond=999999)
        
        for user_id, score in users_scores:
            entry_data = LeaderboardEntryCreate(
                user_id=user_id,
                leaderboard_type=LeaderboardType.XP_WEEKLY,
                score=score,
                period_start=period_start,
                period_end=period_end
            )
            await gamification_service.update_leaderboard_entry(entry_data)
        
        leaderboard = await gamification_service.get_leaderboard(
            LeaderboardType.XP_WEEKLY,
            period_start=period_start,
            period_end=period_end,
            limit=10
        )
        
        assert len(leaderboard) == 3
        # Should be ordered by score desc
        assert leaderboard[0].score == 200  # user-2
        assert leaderboard[1].score == 150  # user-3
        assert leaderboard[2].score == 100  # user-1


class TestBadgeService:
    """Test badge-related service methods."""
    
    async def test_create_badge(self, gamification_service: GamificationService):
        """Test creating a badge."""
        badge_data = BadgeCreate(
            name="Test Badge",
            description="A test badge",
            type=BadgeType.ACHIEVEMENT,
            criteria="Complete 10 lessons",
            icon="🎖️",
            color="#FF5722"
        )
        
        badge = await gamification_service.create_badge(badge_data)
        
        assert badge.name == "Test Badge"
        assert badge.type == BadgeType.ACHIEVEMENT
        assert badge.color == "#FF5722"
        assert badge.is_active is True
    
    async def test_award_badge(
        self, 
        gamification_service: GamificationService, 
        sample_user_id: str,
        sample_badge: Badge
    ):
        """Test awarding a badge to a user."""
        user_badge = await gamification_service.award_badge(sample_user_id, sample_badge.id)
        
        assert user_badge.user_id == sample_user_id
        assert user_badge.badge_id == sample_badge.id
        assert user_badge.awarded_at is not None
    
    async def test_get_user_badges(
        self, 
        gamification_service: GamificationService, 
        sample_user_id: str,
        sample_badge: Badge
    ):
        """Test getting user badges."""
        # Award badge
        await gamification_service.award_badge(sample_user_id, sample_badge.id)
        
        badges = await gamification_service.get_user_badges(sample_user_id)
        
        assert len(badges) == 1
        assert badges[0].badge.name == sample_badge.name


class TestStatsService:
    """Test statistics-related service methods."""
    
    async def test_get_user_stats(self, gamification_service: GamificationService, sample_user_id: str):
        """Test getting comprehensive user stats."""
        # Add some XP
        xp_data = UserXPCreate(
            user_id=sample_user_id,
            points=150,
            source=XPSourceType.LESSON_COMPLETION,
            source_id="lesson-1"
        )
        await gamification_service.add_xp(xp_data)
        
        # Update level
        await gamification_service.update_user_level(sample_user_id)
        
        # Create a streak
        streak_data = StreakCreate(
            user_id=sample_user_id,
            streak_type="daily_login"
        )
        await gamification_service.update_streak(streak_data)
        
        stats = await gamification_service.get_user_stats(sample_user_id)
        
        assert stats["total_xp"] == 150
        assert stats["current_level"] == 2
        assert stats["total_achievements"] == 0
        assert stats["total_badges"] == 0
        assert stats["max_streak"] == 1
        assert stats["current_streaks"] == 1
    
    async def test_get_global_stats(self, gamification_service: GamificationService):
        """Test getting global stats."""
        # Add some test data
        users = ["user-1", "user-2", "user-3"]
        for i, user_id in enumerate(users):
            xp_data = UserXPCreate(
                user_id=user_id,
                points=100 * (i + 1),
                source=XPSourceType.LESSON_COMPLETION,
                source_id=f"lesson-{i+1}"
            )
            await gamification_service.add_xp(xp_data)
        
        stats = await gamification_service.get_global_stats()
        
        assert stats["total_users"] == 3
        assert stats["total_xp_awarded"] == 600  # 100 + 200 + 300
        assert stats["total_achievements_awarded"] == 0
        assert stats["total_badges_awarded"] == 0
        assert stats["active_streaks"] == 0
