"""
Database configuration and session management using SQLAlchemy async.
Provides database engine, session factory, and base model class.
Uses PostgreSQL for all environments (production, staging, testing) for scalability and consistency.
Development environment can use SQLite if explicitly configured, but PostgreSQL is recommended.
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict, Any

from sqlalchemy import MetaData, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

try:  # Enhanced config first
    from .enhanced_config import settings
except ImportError:  # Fallback to legacy config
    from .config import settings

logger = logging.getLogger(__name__)

# Database connection configuration
def get_engine_config() -> Dict[str, Any]:
    """Get database engine configuration based on database type and environment."""
    config = {
        "echo": settings.get_database_config()["echo"] if hasattr(settings, 'get_database_config') else getattr(settings, 'database_echo', False),
        "future": True,
        "pool_pre_ping": True,  # Verify connections before use
        "pool_recycle": 300,    # Recycle connections every 5 minutes
    }

    # Determine environment
    environment = getattr(settings, 'ENVIRONMENT', getattr(settings, 'environment', 'development')).lower()
    database_url = settings.get_database_url() if hasattr(settings, 'get_database_url') else getattr(settings, 'database_url', '')

    # Force PostgreSQL for production and staging
    if environment in ['production', 'staging'] and "sqlite" in database_url:
        raise ValueError(f"SQLite is not supported in {environment} environment. Please use PostgreSQL.")
    
    # Configure database-specific settings
    if "sqlite" in database_url:
        if environment != 'development':
            logger.warning("⚠️ SQLite should only be used for development. Consider using PostgreSQL for better performance and reliability.")
        
        config.update({
            "poolclass": NullPool,  # SQLite doesn't support connection pooling
            "connect_args": {"check_same_thread": False}
        })
        logger.info("Using SQLite database (DEVELOPMENT ONLY)")
    else:
        # PostgreSQL configuration (recommended for all environments)
        db_config = settings.get_database_config() if hasattr(settings, 'get_database_config') else {}
        config.update({
            "pool_size": db_config.get('pool_size', getattr(settings, 'database_pool_size', 20)),
            "max_overflow": db_config.get('max_overflow', getattr(settings, 'database_max_overflow', 30)),
            "pool_timeout": db_config.get('pool_timeout', getattr(settings, 'database_pool_timeout', 30)),
            "pool_recycle": db_config.get('pool_recycle', getattr(settings, 'database_pool_recycle', 3600)),
        })
        logger.info("Using PostgreSQL database (recommended for all environments)")

    return config

# Create async engine with dynamic configuration
database_url = settings.get_database_url() if hasattr(settings, 'get_database_url') else getattr(settings, 'database_url', '')
engine = create_async_engine(database_url, **get_engine_config())

# Add connection event listeners for better debugging
@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Set SQLite pragmas for better performance and consistency."""
    if "sqlite" in database_url:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=10000")
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.close()

# Create async session factory with better configuration
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    """Base class for all database models."""

    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s"
        }
    )


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency that provides a database session.
    Ensures proper cleanup of database connections.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()  # Only commit if there were no exceptions
        except Exception:
            await session.rollback()
            raise


# Alias for backward compatibility
get_async_session = get_db


async def get_db_session() -> AsyncSession:
    """
    Get a database session for direct use (not as dependency).
    Remember to close the session when done.
    """
    return AsyncSessionLocal()


async def init_db() -> None:
    """Initialize the database by creating all tables."""
    try:
        async with engine.begin() as conn:
            # Import all models here to ensure they are registered
            from lyo_app.auth.models import User  # noqa: F401
            from lyo_app.auth.rbac import Role, Permission, role_permissions, user_roles  # noqa: F401
            from lyo_app.learning.models import Course, Lesson, CourseEnrollment, LessonCompletion  # noqa: F401
            from lyo_app.feeds.models import Post, Comment, PostReaction, CommentReaction, UserFollow, FeedItem  # noqa: F401
            from lyo_app.community.models import StudyGroup, GroupMembership, CommunityEvent, EventAttendance  # noqa: F401
            from lyo_app.gamification.models import UserXP, Achievement, UserAchievement, Streak, UserLevel, LeaderboardEntry, Badge, UserBadge  # noqa: F401
            from lyo_app.ai_study.models import StudySession, StudyMessage, GeneratedQuiz, QuizAttempt, StudySessionAnalytics  # noqa: F401

            await conn.run_sync(Base.metadata.create_all)
            logger.info("✅ Database tables created successfully")

            # Create indexes for better performance
            await create_database_indexes(conn)

    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {e}")
        raise


async def create_database_indexes(conn):
    """Create additional database indexes for better performance."""
    try:
        # User-related indexes
        await conn.execute("CREATE INDEX IF NOT EXISTS ix_users_email ON users(email)")
        await conn.execute("CREATE INDEX IF NOT EXISTS ix_users_username ON users(username)")
        await conn.execute("CREATE INDEX IF NOT EXISTS ix_users_created_at ON users(created_at)")

        # Post-related indexes
        await conn.execute("CREATE INDEX IF NOT EXISTS ix_posts_author_id ON posts(author_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS ix_posts_created_at ON posts(created_at)")
        await conn.execute("CREATE INDEX IF NOT EXISTS ix_posts_tags ON posts USING GIN(tags)")

        # Course-related indexes
        await conn.execute("CREATE INDEX IF NOT EXISTS ix_courses_category ON courses(category)")
        await conn.execute("CREATE INDEX IF NOT EXISTS ix_courses_difficulty ON courses(difficulty)")
        await conn.execute("CREATE INDEX IF NOT EXISTS ix_course_enrollments_user_id ON course_enrollments(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS ix_course_enrollments_course_id ON course_enrollments(course_id)")

        # Follow relationships
        await conn.execute("CREATE INDEX IF NOT EXISTS ix_user_follows_follower_id ON user_follows(follower_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS ix_user_follows_following_id ON user_follows(following_id)")

        logger.info("✅ Database indexes created successfully")

    except Exception as e:
        logger.warning(f"⚠️ Some database indexes could not be created: {e}")


async def close_db() -> None:
    """Close database connections."""
    await engine.dispose()
    logger.info("✅ Database connections closed")


async def check_db_health() -> Dict[str, Any]:
    """Check database health and connection status."""
    try:
        async with engine.begin() as conn:
            result = await conn.execute("SELECT 1 as health_check")
            row = result.fetchone()
            return {
                "status": "healthy",
                "connection": "active",
                "database_type": "postgresql" if "postgresql" in str(engine.url) else "sqlite",
                "pool_size": getattr(engine.pool, 'size', 0) if hasattr(engine.pool, 'size') else 0
            }
    except Exception as e:
        return {
            "status": "unhealthy",
            "connection": "failed",
            "error": str(e)
        }
