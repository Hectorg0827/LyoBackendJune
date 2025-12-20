"""
Database configuration and session management using SQLAlchemy async.
Provides database engine, session factory, and base model class.
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import MetaData, event, inspect, text
from sqlalchemy.engine import make_url
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
db_url = settings.database_url

# Inject password from environment variable if available and missing in URL
# This is crucial for Cloud Run where password is provided as a separate secret
db_password = os.getenv("DB_PASSWORD")
if db_password and "postgresql" in db_url:
    try:
        url_obj = make_url(db_url)
        if url_obj.password is None:
            url_obj = url_obj.set(password=db_password)
            db_url = str(url_obj)
            logger.info("✅ Injected DB_PASSWORD into database URL")
    except Exception as e:
        logger.warning(f"⚠️ Failed to inject DB_PASSWORD: {e}")

if db_url and db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(db_url, **get_engine_config())

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

@event.listens_for(engine.sync_engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    conn.info.setdefault('query_start_time', []).append(time.time())

@event.listens_for(engine.sync_engine, "after_cursor_execute")
def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    total = time.time() - conn.info['query_start_time'].pop(-1)
    if total > 0.5:  # Log queries taking longer than 500ms
        logger.warning(f"Slow Query: {total:.4f}s\n{statement}\nParameters: {parameters}")

import time

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
        from lyo_app.learning.models import Course, Lesson, CourseEnrollment, LessonCompletion, CourseItem, CourseStatus  # noqa: F401
        from lyo_app.feeds.models import Post, Comment, PostReaction, CommentReaction, UserFollow, FeedItem  # noqa: F401
        from lyo_app.community.models import StudyGroup, GroupMembership, CommunityEvent, EventAttendance  # noqa: F401
        from lyo_app.gamification.models import UserXP, Achievement, UserAchievement, Streak, UserLevel, LeaderboardEntry, Badge, UserBadge, GamificationProfile  # noqa: F401
        from lyo_app.ai_study.models import StudySession, StudyMessage, GeneratedQuiz, QuizAttempt, StudySessionAnalytics  # noqa: F401
        from lyo_app.tasks.models import Task, TaskState  # noqa: F401
        from lyo_app.notifications.models import PushDevice  # noqa: F401
        # Chat module models (for session continuity + notes/courses)
        from lyo_app.chat.models import ChatConversation, ChatMessage, ChatNote, ChatCourse, ChatTelemetry  # noqa: F401
        # Import new mentor chat models
        from lyo_app.ai_chat.mentor_models import MentorConversation, MentorMessage, MentorAction, MentorSuggestion  # noqa: F401
        from lyo_app.stack.models import StackItem  # noqa: F401
        from lyo_app.classroom.models import ClassroomSession  # noqa: F401
        
        await conn.run_sync(Base.metadata.create_all)

        # Best-effort schema reconciliation for legacy production DBs.
        # create_all() does NOT add missing columns, so older tables can drift.
        await _ensure_stack_items_schema(conn)
        logger.info("Database tables created successfully")


async def _ensure_stack_items_schema(conn) -> None:
    """Ensure stack_items table has required columns (Postgres-only, additive)."""

    def _get_table_info(sync_conn):
        dialect_name = sync_conn.dialect.name
        inspector = inspect(sync_conn)
        has_table = inspector.has_table("stack_items")
        column_names = set()
        if has_table:
            column_names = {col["name"] for col in inspector.get_columns("stack_items")}
        return dialect_name, has_table, column_names

    try:
        dialect_name, has_table, column_names = await conn.run_sync(_get_table_info)
    except Exception as e:
        logger.warning(f"⚠️ stack_items schema inspection failed: {e}")
        return

    if not has_table:
        return

    # Keep this tight: only run DDL on Postgres where we know the syntax.
    if dialect_name != "postgresql":
        return

    ddl_statements: list[str] = []

    # Required by API response model
    if "title" not in column_names:
        ddl_statements.append(
            "ALTER TABLE stack_items ADD COLUMN title VARCHAR(255) NOT NULL DEFAULT 'Untitled'"
        )

    # Optional / commonly used columns (safe additions)
    if "description" not in column_names:
        ddl_statements.append("ALTER TABLE stack_items ADD COLUMN description TEXT")

    if "item_type" not in column_names:
        ddl_statements.append(
            "ALTER TABLE stack_items ADD COLUMN item_type VARCHAR(50) NOT NULL DEFAULT 'topic'"
        )

    if "status" not in column_names:
        ddl_statements.append(
            "ALTER TABLE stack_items ADD COLUMN status VARCHAR(50) NOT NULL DEFAULT 'not_started'"
        )

    if "progress" not in column_names:
        ddl_statements.append(
            "ALTER TABLE stack_items ADD COLUMN progress DOUBLE PRECISION NOT NULL DEFAULT 0.0"
        )

    if "priority" not in column_names:
        ddl_statements.append(
            "ALTER TABLE stack_items ADD COLUMN priority INTEGER NOT NULL DEFAULT 0"
        )

    if "content_id" not in column_names:
        ddl_statements.append("ALTER TABLE stack_items ADD COLUMN content_id VARCHAR(255)")

    if "content_type" not in column_names:
        ddl_statements.append("ALTER TABLE stack_items ADD COLUMN content_type VARCHAR(50)")

    if "extra_data" not in column_names:
        ddl_statements.append(
            "ALTER TABLE stack_items ADD COLUMN extra_data JSONB NOT NULL DEFAULT '{}'::jsonb"
        )

    if "created_at" not in column_names:
        ddl_statements.append(
            "ALTER TABLE stack_items ADD COLUMN created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()"
        )

    if "updated_at" not in column_names:
        ddl_statements.append(
            "ALTER TABLE stack_items ADD COLUMN updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()"
        )

    if "started_at" not in column_names:
        ddl_statements.append("ALTER TABLE stack_items ADD COLUMN started_at TIMESTAMP WITHOUT TIME ZONE")

    if "completed_at" not in column_names:
        ddl_statements.append("ALTER TABLE stack_items ADD COLUMN completed_at TIMESTAMP WITHOUT TIME ZONE")

    if not ddl_statements:
        return

    try:
        for stmt in ddl_statements:
            await conn.execute(text(stmt))
        logger.info(
            "✅ Applied stack_items schema patch (added missing columns)"
        )
    except Exception as e:
        # Don't fail startup if patch can't be applied; log and proceed.
        logger.error(f"❌ Failed applying stack_items schema patch: {e}")


async def close_db() -> None:
    """Close database connections."""
    await engine.dispose()
    logger.info("Database connections closed")
