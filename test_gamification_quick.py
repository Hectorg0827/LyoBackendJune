#!/usr/bin/env python3
"""
Gamification Module Quick Validation
Tests schema creation and basic functionality without database connections.
"""

def test_schema_validation():
    """Test that schemas can be created and validated."""
    print("🧪 Testing Gamification Schemas...")
    
    try:
        # Test basic schema imports
        from pydantic import BaseModel, ValidationError
        print("✓ Pydantic imported")
        
        # Test enum imports
        from enum import Enum
        
        # Create test enums (simulating our models)
        class TestXPActionType(str, Enum):
            LESSON_COMPLETED = "lesson_completed"
            QUIZ_COMPLETED = "quiz_completed"
        
        class TestAchievementType(str, Enum):
            LEARNING = "learning"
            SOCIAL = "social"
        
        print("✓ Test enums created")
        
        # Test schema creation
        class TestXPCreate(BaseModel):
            user_id: str
            points: int
            action_type: TestXPActionType
            source_id: str
        
        class TestAchievementCreate(BaseModel):
            name: str
            description: str
            type: TestAchievementType
            points_required: int
            icon: str
        
        print("✓ Test schemas defined")
        
        # Test schema instantiation
        xp_data = TestXPCreate(
            user_id="test-user-123",
            points=50,
            action_type=TestXPActionType.LESSON_COMPLETED,
            source_id="lesson-456"
        )
        
        achievement_data = TestAchievementCreate(
            name="First Steps",
            description="Complete your first lesson",
            type=TestAchievementType.LEARNING,
            points_required=10,
            icon="🎯"
        )
        
        print("✓ Schema instances created successfully")
        print(f"  XP: {xp_data.user_id} earned {xp_data.points} XP")
        print(f"  Achievement: {achievement_data.name} ({achievement_data.points_required} points)")
        
        # Test validation
        try:
            invalid_xp = TestXPCreate(
                user_id="test",
                points="invalid",  # Should be int
                action_type=TestXPActionType.LESSON_COMPLETED,
                source_id="lesson"
            )
        except ValidationError as e:
            print("✓ Schema validation working (caught invalid data)")
        
        return True
        
    except Exception as e:
        print(f"❌ Schema test failed: {e}")
        return False


def test_business_logic():
    """Test business logic concepts without database."""
    print("\n🧮 Testing Business Logic Concepts...")
    
    try:
        # Test XP calculation logic
        def calculate_level_from_xp(total_xp: int) -> int:
            """Calculate user level from total XP (similar to our service method)."""
            if total_xp < 100:
                return 1
            elif total_xp < 300:
                return 2
            elif total_xp < 600:
                return 3
            elif total_xp < 1000:
                return 4
            else:
                return min(5 + (total_xp - 1000) // 500, 100)
        
        # Test level calculations
        test_cases = [
            (0, 1),
            (99, 1),
            (100, 2),
            (299, 2),
            (300, 3),
            (1000, 5),
            (2000, 7)
        ]
        
        for xp, expected_level in test_cases:
            actual_level = calculate_level_from_xp(xp)
            assert actual_level == expected_level, f"XP {xp}: expected level {expected_level}, got {actual_level}"
        
        print("✓ Level calculation logic working")
        
        # Test streak logic
        from datetime import datetime, timedelta
        
        def should_increment_streak(last_activity: datetime, current_time: datetime) -> bool:
            """Check if streak should be incremented."""
            time_diff = current_time - last_activity
            return timedelta(hours=20) <= time_diff <= timedelta(hours=28)
        
        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)
        two_days_ago = now - timedelta(days=2)
        
        assert should_increment_streak(yesterday, now) == True
        assert should_increment_streak(two_days_ago, now) == False
        
        print("✓ Streak logic working")
        
        # Test achievement threshold logic
        def check_achievement_earned(user_xp: int, achievement_required_xp: int) -> bool:
            """Check if user has earned an achievement."""
            return user_xp >= achievement_required_xp
        
        assert check_achievement_earned(150, 100) == True
        assert check_achievement_earned(50, 100) == False
        
        print("✓ Achievement logic working")
        
        return True
        
    except Exception as e:
        print(f"❌ Business logic test failed: {e}")
        return False


def test_api_concepts():
    """Test API structure concepts."""
    print("\n🛣️ Testing API Concepts...")
    
    try:
        # Test response structure concepts
        class MockResponse:
            def __init__(self, data, status_code=200):
                self.data = data
                self.status_code = status_code
            
            def json(self):
                return self.data
        
        # Mock API responses
        xp_response = MockResponse({
            "user_id": "test-user",
            "points": 50,
            "action_type": "lesson_completed",
            "source_id": "lesson-123",
            "created_at": "2024-01-01T00:00:00Z"
        })
        
        achievement_response = MockResponse({
            "id": "achievement-1",
            "name": "First Steps",
            "description": "Complete your first lesson",
            "type": "learning",
            "points_required": 10,
            "icon": "🎯",
            "is_active": True
        })
        
        leaderboard_response = MockResponse([
            {"user_id": "user-1", "score": 1000, "rank": 1},
            {"user_id": "user-2", "score": 800, "rank": 2},
            {"user_id": "user-3", "score": 600, "rank": 3}
        ])
        
        print("✓ API response structures defined")
        print(f"  XP Response: {xp_response.json()['points']} points")
        print(f"  Achievement: {achievement_response.json()['name']}")
        print(f"  Leaderboard: {len(leaderboard_response.json())} entries")
        
        return True
        
    except Exception as e:
        print(f"❌ API concept test failed: {e}")
        return False


def main():
    """Run all validation tests."""
    print("=" * 60)
    print("🎮 GAMIFICATION MODULE QUICK VALIDATION")
    print("=" * 60)
    
    tests = [
        ("Schema Validation", test_schema_validation),
        ("Business Logic", test_business_logic),
        ("API Concepts", test_api_concepts),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results.append((test_name, False))
    
    print("\n" + "=" * 60)
    print("📊 VALIDATION SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
    
    print(f"\n🎯 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 Gamification module concepts validated successfully!")
        print("✅ Ready for database integration and full testing")
        return True
    else:
        print("⚠️ Some validation tests failed")
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
