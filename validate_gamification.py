#!/usr/bin/env python3
"""
Quick validation script for the gamification module.
Tests basic functionality without requiring a database connection.
"""

import asyncio
import sys
import os

# Add the project root to the Python path
sys.path.append(os.path.dirname(__file__))

from lyo_app.gamification.schemas import (
    UserXPCreate, AchievementCreate, StreakCreate, 
    LeaderboardEntryCreate, BadgeCreate
)
from lyo_app.gamification.models import (
    AchievementType, XPSourceType, LeaderboardType, BadgeType
)


def test_schemas():
    """Test that all schemas can be instantiated correctly."""
    print("Testing Gamification Schemas...")
    
    # Test UserXPCreate
    xp_data = UserXPCreate(
        user_id="test-user",
        points=50,
        source=XPSourceType.LESSON_COMPLETION,
        source_id="lesson-123"
    )
    print(f"✓ UserXPCreate: {xp_data.user_id} earned {xp_data.points} XP")
    
    # Test AchievementCreate
    achievement_data = AchievementCreate(
        name="First Steps",
        description="Complete your first lesson",
        type=AchievementType.LEARNING,
        points_required=10,
        icon="🎯"
    )
    print(f"✓ AchievementCreate: {achievement_data.name}")
    
    # Test StreakCreate
    streak_data = StreakCreate(
        user_id="test-user",
        streak_type="daily_login"
    )
    print(f"✓ StreakCreate: {streak_data.streak_type}")
    
    # Test LeaderboardEntryCreate
    from datetime import datetime
    leaderboard_data = LeaderboardEntryCreate(
        user_id="test-user",
        leaderboard_type=LeaderboardType.XP_WEEKLY,
        score=100,
        period_start=datetime.utcnow(),
        period_end=datetime.utcnow()
    )
    print(f"✓ LeaderboardEntryCreate: {leaderboard_data.leaderboard_type}")
    
    # Test BadgeCreate
    badge_data = BadgeCreate(
        name="Learner",
        description="Active learner badge",
        type=BadgeType.MILESTONE,
        criteria="Complete 5 lessons",
        icon="📚",
        color="#4CAF50"
    )
    print(f"✓ BadgeCreate: {badge_data.name}")
    
    print("All schemas created successfully! ✓")


def test_imports():
    """Test that all modules can be imported."""
    print("Testing Gamification Module Imports...")
    
    try:
        from lyo_app.gamification import GamificationService
        print("✓ GamificationService imported")
        
        from lyo_app.gamification.models import (
            UserXP, Achievement, UserAchievement, Streak, UserLevel,
            LeaderboardEntry, Badge, UserBadge
        )
        print("✓ All models imported")
        
        from lyo_app.gamification.routes import router
        print("✓ Router imported")
        
        print("All imports successful! ✓")
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    
    return True


def test_app_integration():
    """Test that the app can be created with gamification module."""
    print("Testing App Integration...")
    
    try:
        from lyo_app.main import create_app
        app = create_app()
        print("✓ App created successfully with gamification module")
        
        # Check that gamification routes are included
        routes = [route.path for route in app.routes]
        gamification_routes = [r for r in routes if "/gamification" in r]
        
        if gamification_routes:
            print(f"✓ Found {len(gamification_routes)} gamification routes")
            print("   Sample routes:")
            for route in gamification_routes[:5]:  # Show first 5
                print(f"   - {route}")
        else:
            print("❌ No gamification routes found")
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ App integration error: {e}")
        return False


def main():
    """Run all validation tests."""
    print("=" * 60)
    print("GAMIFICATION MODULE VALIDATION")
    print("=" * 60)
    
    tests = [
        ("Schema Creation", test_schemas),
        ("Module Imports", test_imports),
        ("App Integration", test_app_integration),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n{test_name}:")
        print("-" * 40)
        try:
            result = test_func()
            if result is not False:
                results.append((test_name, True, None))
                print(f"✓ {test_name} passed")
            else:
                results.append((test_name, False, "Test returned False"))
        except Exception as e:
            results.append((test_name, False, str(e)))
            print(f"❌ {test_name} failed: {e}")
    
    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, success, _ in results if success)
    total = len(results)
    
    for test_name, success, error in results:
        status = "✓ PASS" if success else "❌ FAIL"
        print(f"{status:10} {test_name}")
        if error:
            print(f"           Error: {error}")
    
    print(f"\nResults: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All gamification module tests passed!")
        print("✅ Ready for database migration and full testing")
        return True
    else:
        print("⚠️  Some tests failed. Please review the errors above.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
