#!/usr/bin/env python3
"""
Database setup and migration script.
Tests database connection and creates tables.
"""

import asyncio
import sys
from pathlib import Path

async def test_database_connection():
    """Test database connection and setup."""
    print("🗄️ Testing Database Connection...")
    
    try:
        # Import database components
        from lyo_app.core.database import engine, init_db
        from lyo_app.core.config import settings
        
        print(f"📋 Database URL: {settings.database_url}")
        print(f"🔧 Environment: {settings.environment}")
        
        # Test connection
        async with engine.begin() as conn:
            print("✅ Database connection successful")
        
        # Initialize database (create tables)
        print("🏗️ Creating database tables...")
        await init_db()
        print("✅ Database tables created successfully")
        
        # Test that tables exist
        async with engine.begin() as conn:
            from sqlalchemy import text
            
            # For SQLite, check sqlite_master table
            if "sqlite" in settings.database_url:
                result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table';"))
                tables = [row[0] for row in result.fetchall()]
                print(f"📊 Created tables: {', '.join(tables)}")
            
        return True
        
    except Exception as e:
        print(f"❌ Database setup failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_basic_operations():
    """Test basic database operations."""
    print("\n🧪 Testing Basic Database Operations...")
    
    try:
        from lyo_app.core.database import AsyncSessionLocal
        from lyo_app.auth.models import User
        from sqlalchemy import select
        
        async with AsyncSessionLocal() as session:
            # Test creating a user
            test_user = User(
                username="testuser",
                email="test@example.com",
                hashed_password="dummy_hash"
            )
            session.add(test_user)
            await session.commit()
            await session.refresh(test_user)
            
            print(f"✅ Created test user: {test_user.username} (ID: {test_user.id})")
            
            # Test querying
            result = await session.execute(select(User).where(User.username == "testuser"))
            found_user = result.scalar_one_or_none()
            
            if found_user:
                print(f"✅ Found user: {found_user.email}")
            else:
                print("❌ Could not find created user")
                return False
                
        return True
        
    except Exception as e:
        print(f"❌ Database operations test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_all_models():
    """Test that all models can be imported and instantiated."""
    print("\n🏗️ Testing All Models...")
    
    try:
        # Test imports
        from lyo_app.auth.models import User
        from lyo_app.learning.models import Course, Lesson
        from lyo_app.feeds.models import Post, Comment
        from lyo_app.community.models import StudyGroup, CommunityEvent
        from lyo_app.gamification.models import UserXP, Achievement, Badge
        
        print("✅ All model imports successful")
        
        # Test that models have proper table names
        models = [User, Course, Lesson, Post, Comment, StudyGroup, CommunityEvent, UserXP, Achievement, Badge]
        for model in models:
            table_name = model.__tablename__
            print(f"   📋 {model.__name__}: {table_name}")
        
        return True
        
    except Exception as e:
        print(f"❌ Model testing failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run all database tests."""
    print("=" * 70)
    print("🗄️ DATABASE SETUP & TESTING")
    print("=" * 70)
    
    tests = [
        ("Database Connection", test_database_connection),
        ("Basic Operations", test_basic_operations),
        ("Model Testing", test_all_models),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            print(f"\n{test_name}:")
            print("-" * 50)
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results.append((test_name, False))
    
    print("\n" + "=" * 70)
    print("📊 DATABASE SETUP SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
    
    print(f"\n🎯 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 Database setup completed successfully!")
        print("✅ Ready for application testing and development")
        
        # Show database file location
        from lyo_app.core.config import settings
        if "sqlite" in settings.database_url:
            db_file = settings.database_url.split("///")[-1]
            if Path(db_file).exists():
                size = Path(db_file).stat().st_size
                print(f"📄 Database file: {db_file} ({size} bytes)")
        
        return True
    else:
        print("⚠️ Some database setup tests failed")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
