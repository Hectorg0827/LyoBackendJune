"""
Pytest configuration and fixtures for testing.
Provides database and service fixtures for tests.
"""

import asyncio
import pytest
import pytest_asyncio
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from lyo_app.core.database import Base


# Test database URL (in-memory SQLite for testing)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Create a test database session.
    Each test gets a fresh database.
    """
    # Import models to ensure they're registered (match database.py init_db)
    from lyo_app.auth.models import User  # noqa: F401
    from lyo_app.learning.models import Course, Lesson, CourseEnrollment, LessonCompletion  # noqa: F401
    from lyo_app.feeds.models import Post, Comment, PostReaction, CommentReaction, UserFollow, FeedItem  # noqa: F401
    from lyo_app.community.models import StudyGroup, GroupMembership, CommunityEvent, EventAttendance  # noqa: F401
    from lyo_app.gamification.models import UserXP, Achievement, UserAchievement, Streak, UserLevel, LeaderboardEntry, Badge, UserBadge  # noqa: F401
    
    # Optional models - import with try/except for resilience
    try:
        from lyo_app.ai_study.models import StudySession, StudyMessage, GeneratedQuiz, QuizAttempt  # noqa: F401
    except ImportError:
        pass
    try:
        from lyo_app.tasks.models import Task, TaskState  # noqa: F401
    except ImportError:
        pass
    try:
        from lyo_app.notifications.models import PushDevice  # noqa: F401
    except ImportError:
        pass
    try:
        from lyo_app.stack.models import StackItem  # noqa: F401
    except ImportError:
        pass
    try:
        from lyo_app.auth.rbac import Role, Permission  # noqa: F401
    except ImportError:
        pass
    
    # Create test engine
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Create session
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    async with async_session() as session:
        yield session
        await session.rollback()
    
    # Clean up
    await engine.dispose()
