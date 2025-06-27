"""
Tests for the gamification routes/API endpoints.
"""

import pytest
from datetime import datetime
from httpx import AsyncClient

from lyo_app.gamification.models import (
    Achievement, Badge, AchievementType, BadgeType, XPSourceType, LeaderboardType
)


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


class TestXPEndpoints:
    """Test XP-related API endpoints."""
    
    async def test_add_xp(self, client: AsyncClient):
        """Test adding XP via API."""
        xp_data = {
            "user_id": "test-user-123",
            "points": 50,
            "source": "lesson_completion",
            "source_id": "lesson-123"
        }
        
        response = await client.post("/api/v1/gamification/xp", json=xp_data)
        
        assert response.status_code == 201
        data = response.json()
        assert data["user_id"] == "test-user-123"
        assert data["points"] == 50
        assert data["source"] == "lesson_completion"
    
    async def test_get_user_total_xp(self, client: AsyncClient):
        """Test getting user total XP."""
        user_id = "test-user-456"
        
        # Add some XP first
        xp_data = {
            "user_id": user_id,
            "points": 75,
            "source": "quiz_completion",
            "source_id": "quiz-1"
        }
        await client.post("/api/v1/gamification/xp", json=xp_data)
        
        response = await client.get(f"/api/v1/gamification/users/{user_id}/xp/total")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total_xp"] == 75
        assert data["user_id"] == user_id
    
    async def test_get_user_xp_history(self, client: AsyncClient):
        """Test getting user XP history."""
        user_id = "test-user-789"
        
        # Add multiple XP entries
        for i in range(3):
            xp_data = {
                "user_id": user_id,
                "points": 10 * (i + 1),
                "source": "lesson_completion",
                "source_id": f"lesson-{i+1}"
            }
            await client.post("/api/v1/gamification/xp", json=xp_data)
        
        response = await client.get(f"/api/v1/gamification/users/{user_id}/xp/history")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        # Should be in descending order
        assert data[0]["points"] == 30
        assert data[1]["points"] == 20
        assert data[2]["points"] == 10


class TestAchievementEndpoints:
    """Test achievement-related API endpoints."""
    
    async def test_create_achievement(self, client: AsyncClient):
        """Test creating an achievement via API."""
        achievement_data = {
            "name": "Quiz Master",
            "description": "Complete 5 quizzes",
            "type": "learning",
            "points_required": 50,
            "icon": "🧠"
        }
        
        response = await client.post("/api/v1/gamification/achievements", json=achievement_data)
        
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Quiz Master"
        assert data["type"] == "learning"
        assert data["points_required"] == 50
        assert data["is_active"] is True
    
    async def test_get_achievements(self, client: AsyncClient, sample_achievement: Achievement):
        """Test getting all achievements."""
        response = await client.get("/api/v1/gamification/achievements")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        
        # Find our sample achievement
        sample_in_response = next(
            (item for item in data if item["id"] == sample_achievement.id), 
            None
        )
        assert sample_in_response is not None
        assert sample_in_response["name"] == sample_achievement.name
    
    async def test_award_achievement(self, client: AsyncClient, sample_achievement: Achievement):
        """Test awarding an achievement to a user."""
        user_id = "test-user-award"
        
        response = await client.post(
            f"/api/v1/gamification/users/{user_id}/achievements/{sample_achievement.id}/award"
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["user_id"] == user_id
        assert data["achievement_id"] == sample_achievement.id
        assert "awarded_at" in data
    
    async def test_get_user_achievements(self, client: AsyncClient, sample_achievement: Achievement):
        """Test getting user achievements."""
        user_id = "test-user-get-achievements"
        
        # Award achievement first
        await client.post(
            f"/api/v1/gamification/users/{user_id}/achievements/{sample_achievement.id}/award"
        )
        
        response = await client.get(f"/api/v1/gamification/users/{user_id}/achievements")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["achievement"]["name"] == sample_achievement.name
    
    async def test_check_achievements(self, client: AsyncClient, sample_achievement: Achievement):
        """Test checking and awarding achievements based on XP."""
        user_id = "test-user-check"
        
        # Add XP that meets achievement requirements
        xp_data = {
            "user_id": user_id,
            "points": 15,  # More than the 10 required
            "source": "lesson_completion",
            "source_id": "lesson-1"
        }
        await client.post("/api/v1/gamification/xp", json=xp_data)
        
        response = await client.post(f"/api/v1/gamification/users/{user_id}/achievements/check")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["achievement_id"] == sample_achievement.id


class TestStreakEndpoints:
    """Test streak-related API endpoints."""
    
    async def test_update_streak(self, client: AsyncClient):
        """Test updating a streak."""
        streak_data = {
            "user_id": "test-user-streak",
            "streak_type": "daily_login"
        }
        
        response = await client.post("/api/v1/gamification/streaks", json=streak_data)
        
        assert response.status_code == 201
        data = response.json()
        assert data["user_id"] == "test-user-streak"
        assert data["streak_type"] == "daily_login"
        assert data["current_count"] == 1
        assert data["max_count"] == 1
    
    async def test_get_user_streaks(self, client: AsyncClient):
        """Test getting user streaks."""
        user_id = "test-user-streaks"
        
        # Create multiple streaks
        streak_types = ["daily_login", "lesson_completion"]
        for streak_type in streak_types:
            streak_data = {
                "user_id": user_id,
                "streak_type": streak_type
            }
            await client.post("/api/v1/gamification/streaks", json=streak_data)
        
        response = await client.get(f"/api/v1/gamification/users/{user_id}/streaks")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        streak_types_result = [s["streak_type"] for s in data]
        assert "daily_login" in streak_types_result
        assert "lesson_completion" in streak_types_result


class TestLevelEndpoints:
    """Test level-related API endpoints."""
    
    async def test_get_user_level(self, client: AsyncClient):
        """Test getting user level."""
        user_id = "test-user-level"
        
        # Add XP to reach level 2
        xp_data = {
            "user_id": user_id,
            "points": 150,
            "source": "lesson_completion",
            "source_id": "lesson-1"
        }
        await client.post("/api/v1/gamification/xp", json=xp_data)
        
        # Update level
        await client.post(f"/api/v1/gamification/users/{user_id}/level/update")
        
        response = await client.get(f"/api/v1/gamification/users/{user_id}/level")
        
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == user_id
        assert data["current_level"] == 2
        assert data["total_xp"] == 150
    
    async def test_update_user_level(self, client: AsyncClient):
        """Test updating user level."""
        user_id = "test-user-level-update"
        
        # Add XP first
        xp_data = {
            "user_id": user_id,
            "points": 200,
            "source": "quiz_completion",
            "source_id": "quiz-1"
        }
        await client.post("/api/v1/gamification/xp", json=xp_data)
        
        response = await client.post(f"/api/v1/gamification/users/{user_id}/level/update")
        
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == user_id
        assert data["current_level"] == 2
        assert data["total_xp"] == 200


class TestLeaderboardEndpoints:
    """Test leaderboard-related API endpoints."""
    
    async def test_update_leaderboard_entry(self, client: AsyncClient):
        """Test updating a leaderboard entry."""
        entry_data = {
            "user_id": "user-leaderboard-1",
            "leaderboard_type": "xp_weekly",
            "score": 100,
            "period_start": datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0).isoformat(),
            "period_end": datetime.utcnow().replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()
        }
        
        response = await client.post("/api/v1/gamification/leaderboard", json=entry_data)
        
        assert response.status_code == 201
        data = response.json()
        assert data["user_id"] == "user-leaderboard-1"
        assert data["leaderboard_type"] == "xp_weekly"
        assert data["score"] == 100
    
    async def test_get_leaderboard(self, client: AsyncClient):
        """Test getting leaderboard."""
        # Create multiple entries
        users_scores = [("user-1", 100), ("user-2", 200), ("user-3", 150)]
        period_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        period_end = datetime.utcnow().replace(hour=23, minute=59, second=59, microsecond=999999)
        
        for user_id, score in users_scores:
            entry_data = {
                "user_id": user_id,
                "leaderboard_type": "xp_weekly",
                "score": score,
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat()
            }
            await client.post("/api/v1/gamification/leaderboard", json=entry_data)
        
        response = await client.get(
            "/api/v1/gamification/leaderboard/xp_weekly",
            params={
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "limit": 10
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        # Should be ordered by score desc
        assert data[0]["score"] == 200  # user-2
        assert data[1]["score"] == 150  # user-3
        assert data[2]["score"] == 100  # user-1


class TestBadgeEndpoints:
    """Test badge-related API endpoints."""
    
    async def test_create_badge(self, client: AsyncClient):
        """Test creating a badge via API."""
        badge_data = {
            "name": "Study Champion",
            "description": "Complete 20 study sessions",
            "type": "milestone",
            "criteria": "Complete 20 study sessions",
            "icon": "🏆",
            "color": "#FFD700"
        }
        
        response = await client.post("/api/v1/gamification/badges", json=badge_data)
        
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Study Champion"
        assert data["type"] == "milestone"
        assert data["color"] == "#FFD700"
        assert data["is_active"] is True
    
    async def test_get_badges(self, client: AsyncClient, sample_badge: Badge):
        """Test getting all badges."""
        response = await client.get("/api/v1/gamification/badges")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        
        # Find our sample badge
        sample_in_response = next(
            (item for item in data if item["id"] == sample_badge.id), 
            None
        )
        assert sample_in_response is not None
        assert sample_in_response["name"] == sample_badge.name
    
    async def test_award_badge(self, client: AsyncClient, sample_badge: Badge):
        """Test awarding a badge to a user."""
        user_id = "test-user-badge-award"
        
        response = await client.post(
            f"/api/v1/gamification/users/{user_id}/badges/{sample_badge.id}/award"
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["user_id"] == user_id
        assert data["badge_id"] == sample_badge.id
        assert "awarded_at" in data
    
    async def test_get_user_badges(self, client: AsyncClient, sample_badge: Badge):
        """Test getting user badges."""
        user_id = "test-user-get-badges"
        
        # Award badge first
        await client.post(
            f"/api/v1/gamification/users/{user_id}/badges/{sample_badge.id}/award"
        )
        
        response = await client.get(f"/api/v1/gamification/users/{user_id}/badges")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["badge"]["name"] == sample_badge.name


class TestStatsEndpoints:
    """Test statistics-related API endpoints."""
    
    async def test_get_user_stats(self, client: AsyncClient):
        """Test getting user stats."""
        user_id = "test-user-stats"
        
        # Add some XP
        xp_data = {
            "user_id": user_id,
            "points": 150,
            "source": "lesson_completion",
            "source_id": "lesson-1"
        }
        await client.post("/api/v1/gamification/xp", json=xp_data)
        
        # Update level
        await client.post(f"/api/v1/gamification/users/{user_id}/level/update")
        
        # Create a streak
        streak_data = {
            "user_id": user_id,
            "streak_type": "daily_login"
        }
        await client.post("/api/v1/gamification/streaks", json=streak_data)
        
        response = await client.get(f"/api/v1/gamification/users/{user_id}/stats")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total_xp"] == 150
        assert data["current_level"] == 2
        assert data["total_achievements"] == 0
        assert data["total_badges"] == 0
        assert data["max_streak"] == 1
        assert data["current_streaks"] == 1
    
    async def test_get_global_stats(self, client: AsyncClient):
        """Test getting global stats."""
        # Add some test data
        users = ["user-global-1", "user-global-2", "user-global-3"]
        for i, user_id in enumerate(users):
            xp_data = {
                "user_id": user_id,
                "points": 100 * (i + 1),
                "source": "lesson_completion",
                "source_id": f"lesson-{i+1}"
            }
            await client.post("/api/v1/gamification/xp", json=xp_data)
        
        response = await client.get("/api/v1/gamification/stats/global")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total_users"] >= 3
        assert data["total_xp_awarded"] >= 600  # At least our test data
        assert "total_achievements_awarded" in data
        assert "total_badges_awarded" in data
        assert "active_streaks" in data


class TestSystemEndpoints:
    """Test system-related API endpoints."""
    
    async def test_health_check(self, client: AsyncClient):
        """Test gamification system health check."""
        response = await client.get("/api/v1/gamification/system/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "gamification_service" in data
        assert data["gamification_service"] == "operational"
    
    async def test_system_stats(self, client: AsyncClient):
        """Test getting system statistics."""
        response = await client.get("/api/v1/gamification/system/stats")
        
        assert response.status_code == 200
        data = response.json()
        assert "total_achievements" in data
        assert "total_badges" in data
        assert "active_achievements" in data
        assert "active_badges" in data
        assert isinstance(data["total_achievements"], int)
        assert isinstance(data["total_badges"], int)
