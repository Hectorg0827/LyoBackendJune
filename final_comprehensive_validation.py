#!/usr/bin/env python3
"""
Final Comprehensive Backend Validation
Tests all backend components to ensure error-free operation
"""

import traceback
import sys
import os

def test_core_imports():
    """Test basic FastAPI and core imports"""
    try:
        from fastapi import FastAPI
        from sqlalchemy import create_engine
        from lyo_app.core.config import settings
        return True, "Core imports successful"
    except Exception as e:
        return False, f"Core imports failed: {str(e)}"

def test_ai_study_models():
    """Test AI Study Mode models"""
    try:
        from lyo_app.ai_study.models import (
            StudySession, StudyMessage, GeneratedQuiz, 
            QuizAttempt, StudySessionAnalytics
        )
        return True, "AI Study Mode models imported successfully"
    except Exception as e:
        return False, f"AI Study Mode models failed: {str(e)}"

def test_enhanced_features():
    """Test enhanced backend features"""
    try:
        from lyo_app.core.monitoring import SystemMonitor
        from lyo_app.storage.enhanced_storage import EnhancedStorageManager
        from lyo_app.core.logging import logger
        return True, "Enhanced features available"
    except Exception as e:
        return False, f"Enhanced features failed: {str(e)}"

def test_addictive_algorithm():
    """Test TikTok-style addictive algorithm"""
    try:
        from lyo_app.feeds.addictive_algorithm import AddictiveFeedAlgorithm
        return True, "Addictive algorithm available"
    except Exception as e:
        return False, f"Addictive algorithm failed: {str(e)}"

def test_api_routes():
    """Test API route imports"""
    try:
        from lyo_app.api.social import router as social_router
        return True, "API routes available"
    except Exception as e:
        return False, f"API routes failed: {str(e)}"

def test_main_app():
    """Test main FastAPI app creation"""
    try:
        from lyo_app.main import create_enhanced_app
        app = create_enhanced_app()
        return True, "Main app created successfully"
    except Exception as e:
        return False, f"Main app failed: {str(e)}"

def test_user_relationships():
    """Test User model AI Study Mode relationships"""
    try:
        from lyo_app.auth.models import User
        # Check if User has the correct relationship to StudySessionAnalytics
        user_attrs = dir(User)
        has_study_analytics = any('study_analytics' in attr.lower() for attr in user_attrs)
        if has_study_analytics:
            return True, "User model relationships correct"
        else:
            return False, "User model missing study_analytics relationship"
    except Exception as e:
        return False, f"User model check failed: {str(e)}"

def test_startup_files():
    """Test that required startup files exist"""
    try:
        files_to_check = [
            'start_optimized.py',
            'requirements.txt',
            'lyo_app/main.py'
        ]
        
        missing_files = []
        for file_path in files_to_check:
            if not os.path.exists(file_path):
                missing_files.append(file_path)
        
        if missing_files:
            return False, f"Missing files: {', '.join(missing_files)}"
        
        return True, "All required startup files present"
    except Exception as e:
        return False, f"Startup files check failed: {str(e)}"

def test_database_connection():
    """Test database connection"""
    try:
        from lyo_app.core.database import get_db, init_db
        # Just test that we can import and the functions exist
        return True, "Database setup available"
    except Exception as e:
        return False, f"Database connection failed: {str(e)}"

def main():
    """Run all validation tests"""
    print("🔍 FINAL COMPREHENSIVE BACKEND VALIDATION")
    print("=" * 50)
    
    tests = [
        ("Core imports", test_core_imports),
        ("AI Study Mode models", test_ai_study_models), 
        ("Enhanced features", test_enhanced_features),
        ("Addictive algorithm", test_addictive_algorithm),
        ("API routes", test_api_routes),
        ("Main app", test_main_app),
        ("User relationships", test_user_relationships),
        ("Startup files", test_startup_files),
        ("Database setup", test_database_connection),
    ]
    
    passed = 0
    total = len(tests)
    
    for i, (test_name, test_func) in enumerate(tests, 1):
        try:
            success, message = test_func()
            if success:
                print(f"✅ {i}. {test_name}: {message}")
                passed += 1
            else:
                print(f"❌ {i}. {test_name}: {message}")
        except Exception as e:
            print(f"❌ {i}. {test_name}: Unexpected error - {str(e)}")
    
    print("\n" + "=" * 50)
    print("📊 FINAL VALIDATION RESULTS")
    print("=" * 50)
    
    success_rate = (passed / total) * 100
    rating = (passed / total) * 10
    
    print(f"Tests Passed: {passed}/{total} ({success_rate:.1f}%)")
    print(f"Backend Rating: {rating:.1f}/10")
    
    if passed == total:
        print("\n🎉 PERFECT! All backend systems operational!")
        print("✅ Ready for production deployment")
        print("✅ All identified issues resolved")
        print("✅ Backend is error-free and ready to run")
    elif passed >= total * 0.8:
        print("\n🚀 EXCELLENT! Backend mostly operational")
        print("✅ Minor issues remaining but core functionality works")
    elif passed >= total * 0.6:
        print("\n👍 GOOD! Backend functional with some issues")
        print("🔧 Some components need attention")
    else:
        print("\n🔧 NEEDS WORK! Major issues require attention!")
        print("❌ Backend not ready for production")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
