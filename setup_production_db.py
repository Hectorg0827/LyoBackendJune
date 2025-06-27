#!/usr/bin/env python3
"""
Production database setup script.
Handles PostgreSQL setup, migration, and data verification.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from lyo_app.core.config import settings
from lyo_app.core.database import Base
from lyo_app.core.logging import get_logger

logger = get_logger(__name__)


async def verify_database_connection(engine):
    """Verify database connection."""
    try:
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT version()"))
            version = result.scalar()
            logger.info(f"Database connected: {version}")
            return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False


async def run_migrations():
    """Run Alembic migrations."""
    import subprocess
    
    try:
        logger.info("Running database migrations...")
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            cwd=project_root
        )
        
        if result.returncode == 0:
            logger.info("Migrations completed successfully")
            logger.info(result.stdout)
            return True
        else:
            logger.error(f"Migration failed: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"Migration execution failed: {e}")
        return False


async def verify_tables(engine):
    """Verify that all expected tables exist."""
    expected_tables = [
        'users', 'roles', 'permissions', 'user_roles', 'role_permissions',
        'courses', 'lessons', 'enrollments', 'user_progress',
        'posts', 'comments', 'reactions', 'user_follows',
        'groups', 'group_memberships', 'events', 'event_attendees',
        'xp_transactions', 'achievements', 'user_achievements', 'streaks',
        'user_levels', 'leaderboard_entries', 'badges', 'user_badges',
        'email_verification_tokens', 'password_reset_tokens', 'file_uploads'
    ]
    
    try:
        async with engine.begin() as conn:
            # Get list of tables
            result = await conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """))
            
            existing_tables = [row[0] for row in result.fetchall()]
            
            missing_tables = []
            for table in expected_tables:
                if table not in existing_tables:
                    missing_tables.append(table)
            
            if missing_tables:
                logger.warning(f"Missing tables: {missing_tables}")
                return False
            else:
                logger.info(f"All {len(expected_tables)} tables verified")
                return True
                
    except Exception as e:
        logger.error(f"Table verification failed: {e}")
        return False


async def create_default_data(engine):
    """Create default roles and permissions if they don't exist."""
    try:
        from lyo_app.auth.rbac_service import RBACService
        
        async_session = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        
        async with async_session() as session:
            rbac_service = RBACService()
            
            # Initialize default roles and permissions
            await rbac_service.initialize_default_roles_and_permissions(session)
            
            logger.info("Default roles and permissions created")
            return True
            
    except Exception as e:
        logger.error(f"Default data creation failed: {e}")
        return False


async def verify_performance(engine):
    """Run basic performance tests."""
    try:
        async with engine.begin() as conn:
            # Test simple query performance
            import time
            
            start_time = time.time()
            await conn.execute(text("SELECT COUNT(*) FROM users"))
            query_time = (time.time() - start_time) * 1000
            
            logger.info(f"Basic query performance: {query_time:.2f}ms")
            
            if query_time > 1000:  # 1 second
                logger.warning("Database queries are slow, consider optimization")
            
            return True
            
    except Exception as e:
        logger.error(f"Performance test failed: {e}")
        return False


async def main():
    """Main setup function."""
    logger.info("🚀 Starting production database setup")
    
    # Check environment
    if settings.ENVIRONMENT != "production":
        logger.warning(f"Environment is {settings.ENVIRONMENT}, not production")
    
    # Create database engine
    if not settings.DATABASE_URL:
        logger.error("DATABASE_URL not configured")
        return False
    
    if "postgresql" not in settings.DATABASE_URL:
        logger.error("Production requires PostgreSQL database")
        return False
    
    logger.info(f"Connecting to database: {settings.DATABASE_URL.split('@')[1] if '@' in settings.DATABASE_URL else 'localhost'}")
    
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DATABASE_ECHO,
        pool_size=10,
        max_overflow=20
    )
    
    try:
        # Step 1: Verify connection
        if not await verify_database_connection(engine):
            return False
        
        # Step 2: Run migrations
        if not await run_migrations():
            return False
        
        # Step 3: Verify tables
        if not await verify_tables(engine):
            return False
        
        # Step 4: Create default data
        if not await create_default_data(engine):
            return False
        
        # Step 5: Performance check
        if not await verify_performance(engine):
            return False
        
        logger.info("🎉 Production database setup completed successfully!")
        
        # Print summary
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT COUNT(*) FROM users"))
            user_count = result.scalar()
            
            result = await conn.execute(text("SELECT COUNT(*) FROM roles"))
            role_count = result.scalar()
            
            logger.info(f"📊 Database summary:")
            logger.info(f"   Users: {user_count}")
            logger.info(f"   Roles: {role_count}")
        
        return True
        
    except Exception as e:
        logger.error(f"Setup failed: {e}")
        return False
        
    finally:
        await engine.dispose()


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
