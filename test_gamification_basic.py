#!/usr/bin/env python3
"""
Simple gamification module test without database dependencies.
"""

def test_basic_imports():
    """Test basic imports work."""
    print("Testing basic imports...")
    
    try:
        # Test enum imports
        from lyo_app.gamification.models import AchievementType, XPActionType, AchievementRarity, StreakType
        print("✓ Enums imported successfully")
        
        # Test schema imports
        from lyo_app.gamification.schemas import UserXPCreate, AchievementCreate
        print("✓ Schemas imported successfully")
        
        return True
    except Exception as e:
        print(f"❌ Import failed: {e}")
        return False

def test_schema_creation():
    """Test schema creation."""
    print("Testing schema creation...")
    
    try:
        from lyo_app.gamification.schemas import UserXPCreate
        from lyo_app.gamification.models import XPActionType
        
        # Create a schema instance
        xp_data = UserXPCreate(
            user_id="test-user",
            points=50,
            action_type=XPActionType.LESSON_COMPLETED,
            source_id="lesson-123"
        )
        
        print(f"✓ UserXPCreate created: user={xp_data.user_id}, points={xp_data.points}")
        return True
    except Exception as e:
        print(f"❌ Schema creation failed: {e}")
        return False

def test_model_definitions():
    """Test that model classes are defined correctly."""
    print("Testing model definitions...")
    
    try:
        from lyo_app.gamification.models import UserXP, Achievement, Badge
        
        print(f"✓ UserXP model: {UserXP.__name__}")
        print(f"✓ Achievement model: {Achievement.__name__}")
        print(f"✓ Badge model: {Badge.__name__}")
        
        return True
    except Exception as e:
        print(f"❌ Model definition test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("=" * 50)
    print("SIMPLE GAMIFICATION MODULE TEST")
    print("=" * 50)
    
    tests = [
        test_basic_imports,
        test_schema_creation,
        test_model_definitions,
    ]
    
    passed = 0
    for test in tests:
        if test():
            passed += 1
        print()
    
    print("=" * 50)
    print(f"Results: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("🎉 All basic tests passed!")
    else:
        print("⚠️ Some tests failed.")

if __name__ == "__main__":
    main()
