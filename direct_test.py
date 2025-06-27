#!/usr/bin/env python3
"""
Direct FastAPI app test without server startup
"""

import asyncio
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path.cwd()))

async def test_app_directly():
    """Test the FastAPI app creation and basic functionality"""
    
    print("🔍 Testing FastAPI app creation...")
    
    try:
        # Import the app
        from lyo_app.main import create_app
        
        # Create the app
        app = create_app()
        
        print("✅ App created successfully")
        print(f"   Title: {app.title}")
        print(f"   Version: {app.version}")
        
        # Check routes
        routes = [route.path for route in app.routes]
        print(f"   Routes: {len(routes)} total")
        
        # Key routes to check
        key_routes = ["/", "/health", "/api/v1/auth/register", "/api/v1/auth/login"]
        for route in key_routes:
            if route in routes:
                print(f"   ✅ {route}")
            else:
                print(f"   ❌ {route} missing")
        
        print("✅ App validation complete")
        return True
        
    except Exception as e:
        print(f"❌ App creation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_database_connection():
    """Test database connection"""
    
    print("\n🗄️ Testing database connection...")
    
    try:
        from lyo_app.core.database import AsyncSessionLocal, engine
        from lyo_app.auth.models import User
        
        async with AsyncSessionLocal() as session:
            # Try a simple query
            from sqlalchemy import text
            result = await session.execute(text("SELECT 1"))
            row = result.fetchone()
            
            if row and row[0] == 1:
                print("✅ Database connection successful")
                return True
            else:
                print("❌ Database query failed")
                return False
                
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

async def test_imports():
    """Test all critical imports"""
    
    print("\n📦 Testing imports...")
    
    modules_to_test = [
        "lyo_app.main",
        "lyo_app.auth.routes",
        "lyo_app.auth.email_routes", 
        "lyo_app.core.health",
        "lyo_app.core.file_routes",
        "lyo_app.learning.routes",
        "lyo_app.feeds.routes",
        "lyo_app.community.routes",
        "lyo_app.gamification.routes",
        "lyo_app.admin.routes"
    ]
    
    success_count = 0
    for module in modules_to_test:
        try:
            __import__(module)
            print(f"   ✅ {module}")
            success_count += 1
        except Exception as e:
            print(f"   ❌ {module}: {e}")
    
    print(f"✅ {success_count}/{len(modules_to_test)} modules imported successfully")
    return success_count == len(modules_to_test)

async def test_configuration():
    """Test configuration"""
    
    print("\n⚙️ Testing configuration...")
    
    try:
        from lyo_app.core.config import settings
        
        print(f"   Environment: {settings.environment}")
        print(f"   Debug: {settings.debug}")
        print(f"   Database URL: {settings.database_url}")
        print(f"   API Prefix: {settings.api_v1_prefix}")
        
        if settings.database_url and settings.secret_key:
            print("✅ Configuration loaded successfully")
            return True
        else:
            print("❌ Configuration incomplete")
            return False
            
    except Exception as e:
        print(f"❌ Configuration test failed: {e}")
        return False

async def main():
    """Run all tests"""
    
    print("=" * 80)
    print("🔧 LYOAPP DIRECT APPLICATION TEST")
    print("=" * 80)
    
    tests = [
        ("Configuration", test_configuration),
        ("Imports", test_imports),
        ("Database Connection", test_database_connection),
        ("FastAPI App", test_app_directly)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 80)
    print("📊 TEST SUMMARY")
    print("=" * 80)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
    
    print(f"\n🎯 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        print("✅ LyoApp backend is ready")
        print("\n🚀 To start the server:")
        print("   python start_server.py")
        print("   # or")
        print("   uvicorn lyo_app.main:app --reload")
    else:
        print("\n⚠️ Some tests failed")
        print("🔧 Please check the errors above")
    
    return passed == total

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
