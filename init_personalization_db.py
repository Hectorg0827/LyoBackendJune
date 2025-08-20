#!/usr/bin/env python3
"""
Initialize personalization database tables directly using SQLAlchemy
Since Alembic is having issues with async configuration, we'll create tables directly
"""

import sys
import os
import asyncio
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from lyo_app.core.database import Base
from lyo_app.core.config import settings

# Import all models to ensure they're registered with Base
try:
    from lyo_app.models.user_model import User
    from lyo_app.models.resource_model import Resource
    from lyo_app.models.playlist_model import Playlist, PlaylistItem
    from lyo_app.models.review_model import Review
    from lyo_app.models.achievement_model import Achievement
    from lyo_app.models.study_session_model import StudySession
    from lyo_app.models.social_model import Follow, Like, Comment
    from lyo_app.models.messenger_model import Conversation, Message
    print("✅ Core models imported successfully")
except ImportError as e:
    print(f"⚠️  Some core models not found: {e}")

# Import personalization models
try:
    from lyo_app.personalization.models import (
        LearnerState, 
        LearnerMastery, 
        AffectSample, 
        SpacedRepetitionSchedule
    )
    print("✅ Personalization models imported successfully")
except ImportError as e:
    print(f"❌ Personalization models import failed: {e}")
    sys.exit(1)

async def init_database():
    """Initialize database tables"""
    print("🚀 Initializing Personalization Database Tables...")
    
    try:
        # Create async engine
        engine = create_async_engine(
            settings.database_url, 
            echo=True
        )
        
        # Create tables
        async with engine.begin() as conn:
            print("📊 Creating all database tables...")
            await conn.run_sync(Base.metadata.create_all)
        
        print("✅ Database tables created successfully!")
        
        # Verify tables exist
        async with engine.begin() as conn:
            result = await conn.execute(text("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name LIKE '%learner%' OR name LIKE '%affect%' OR name LIKE '%spaced%'
                ORDER BY name;
            """))
            tables = result.fetchall()
            
            if tables:
                print(f"✅ Found {len(tables)} personalization tables:")
                for table in tables:
                    print(f"  - {table[0]}")
            else:
                print("⚠️  No personalization tables found")
        
        await engine.dispose()
        
    except Exception as e:
        print(f"❌ Error initializing database: {e}")
        return False
    
    return True

async def main():
    """Main function"""
    print("=" * 60)
    print("🎯 LyoApp Personalization Database Initialization")
    print("=" * 60)
    
    success = await init_database()
    
    if success:
        print("\n🎉 Personalization database initialization complete!")
        print("✅ Ready to test personalization endpoints")
        print("\nNext steps:")
        print("1. Start the server: python start_server.py") 
        print("2. Visit: http://localhost:8000/docs")
        print("3. Test personalization endpoints")
    else:
        print("\n❌ Database initialization failed")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
