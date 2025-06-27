#!/usr/bin/env python3
"""
Quick database verification script.
"""

import asyncio
import sqlite3

async def verify_database():
    """Verify database setup quickly."""
    print("🔍 Quick Database Verification...")
    
    try:
        # Check database file
        import os
        db_file = "./lyo_app_dev.db"
        if os.path.exists(db_file):
            size = os.path.getsize(db_file)
            print(f"✅ Database file exists: {db_file} ({size} bytes)")
            
            # Check tables using sqlite3
            conn = sqlite3.connect(db_file)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]
            conn.close()
            
            print(f"📊 Tables found: {len(tables)}")
            for table in sorted(tables):
                print(f"   📋 {table}")
            
            # Check for our expected tables
            expected_tables = [
                'users', 'courses', 'lessons', 'posts', 'comments', 
                'study_groups', 'community_events', 'user_xp', 'achievements', 'badges'
            ]
            
            found_tables = set(tables)
            expected_set = set(expected_tables)
            
            missing = expected_set - found_tables
            extra = found_tables - expected_set
            
            if missing:
                print(f"❌ Missing tables: {missing}")
            else:
                print("✅ All expected tables found")
            
            if extra:
                print(f"ℹ️ Additional tables: {extra}")
            
            return len(missing) == 0
        else:
            print("❌ Database file not found")
            return False
            
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False

async def test_app_import():
    """Test if the app can be imported."""
    print("\n🚀 Testing App Import...")
    
    try:
        from lyo_app.main import app
        print("✅ App imported successfully")
        
        # Check routes
        routes = [route.path for route in app.routes]
        gamification_routes = [r for r in routes if "/gamification" in r]
        
        print(f"📊 Total routes: {len(routes)}")
        print(f"🎮 Gamification routes: {len(gamification_routes)}")
        
        return True
        
    except Exception as e:
        print(f"❌ App import failed: {e}")
        return False

async def main():
    """Run quick verification."""
    print("=" * 60)
    print("⚡ QUICK DATABASE & APP VERIFICATION")
    print("=" * 60)
    
    db_ok = await verify_database()
    app_ok = await test_app_import()
    
    print("\n" + "=" * 60)
    print("📊 VERIFICATION SUMMARY")
    print("=" * 60)
    
    if db_ok and app_ok:
        print("🎉 SUCCESS! Database and app are ready!")
        print("✅ Database tables created")
        print("✅ App imports successfully")
        print("🚀 Ready for API testing!")
        return True
    else:
        print("⚠️ Some issues found:")
        if not db_ok:
            print("❌ Database setup incomplete")
        if not app_ok:
            print("❌ App import failed")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
