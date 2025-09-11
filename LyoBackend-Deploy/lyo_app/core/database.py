"""
Database configuration and session management using SQLAlchemy async.
Provides database engine, session factory, and base model class.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import MetaData, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from .config import settings

logger = logging.getLogger(__name__)

# Database connection configuration
def get_engine_config():
    """Get database engine configuration based on database type."""
    config = {
        "echo": settings.database_echo,
        "future": True,
        "pool_pre_ping": True,  # Verify connections before use
        "pool_recycle": 300,    # Recycle connections every 5 minutes
    }
    
    # SQLite-specific configuration
    if "sqlite" in settings.database_url:
        config.update({
            "poolclass": NullPool,  # SQLite doesn't support connection pooling
            "connect_args": {"check_same_thread": False}
        })
    else:
        # PostgreSQL/MySQL configuration
        config.update({
            "pool_size": settings.connection_pool_size,
            "max_overflow": settings.max_overflow,
            "pool_timeout": 30,
        })
    
    return config

# Create async engine with dynamic configuration
engine = create_async_engine(settings.database_url, **get_engine_config())

# Add connection event listeners for better debugging
@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Set SQLite pragmas for better performance and consistency."""
    if "sqlite" in settings.database_url:
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
            # Only commit if there were no exceptions
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
        logger.info("Database tables created successfully")


async def close_db() -> None:
    """Close database connections."""
    await engine.dispose()
    logger.info("Database connections closed")
