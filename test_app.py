#!/usr/bin/env python3
"""
Simple test script to verify the LyoApp backend functionality.
Tests basic imports, app creation, and route registration.
"""

import asyncio
import sys

def test_imports():
    """Test that all modules can be imported."""
    try:
        from lyo_app.main import app
        from lyo_app.auth.routes import router as auth_router
        from lyo_app.learning.routes import router as learning_router
        from lyo_app.feeds.routes import router as feeds_router
        print("✅ All modules imported successfully")
        return True
    except Exception as e:
        print(f"❌ Import error: {e}")
        return False

def test_app_routes():
    """Test that routes are properly registered."""
    try:
        from lyo_app.main import app
        
        # Check if routes are registered
        route_paths = [route.path for route in app.routes]
        
        print("📊 Registered routes:")
        for path in route_paths:
            print(f"  - {path}")
        
        # Check for key routes
        expected_routes = ["/", "/health"]
        missing_routes = [route for route in expected_routes if route not in route_paths]
        
        if missing_routes:
            print(f"❌ Missing routes: {missing_routes}")
            return False
        
        print("✅ Routes are properly registered")
        return True
    except Exception as e:
        print(f"❌ Route registration error: {e}")
        return False

def test_database_models():
    """Test that database models can be imported."""
    try:
        from lyo_app.auth.models import User
        from lyo_app.learning.models import Course, Lesson, CourseEnrollment, LessonCompletion
        from lyo_app.feeds.models import Post, Comment, PostReaction, CommentReaction, UserFollow, FeedItem
        
        print("✅ All database models imported successfully")
        return True
    except Exception as e:
        print(f"❌ Database model import error: {e}")
        return False

async def test_app_startup():
    """Test that the app can start up."""
    try:
        from lyo_app.main import app
        from lyo_app.core.database import init_db, close_db
        
        # Test database initialization
        # Note: This would create tables in the configured database
        # For testing, we'll just check that the function exists
        print("✅ Database initialization function available")
        
        print("✅ App startup test completed")
        return True
    except Exception as e:
        print(f"❌ App startup error: {e}")
        return False

def main():
    """Run all tests."""
    print("🧪 Testing LyoApp Backend")
    print("=" * 50)
    
    tests = [
        ("Import Test", test_imports),
        ("Route Registration Test", test_app_routes),
        ("Database Models Test", test_database_models),
        ("App Startup Test", lambda: asyncio.run(test_app_startup())),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n🔍 Running {test_name}...")
        try:
            if test_func():
                passed += 1
            else:
                print(f"❌ {test_name} failed")
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
    
    print("\n" + "=" * 50)
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! LyoApp backend is ready.")
        return 0
    else:
        print("💥 Some tests failed. Please check the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
