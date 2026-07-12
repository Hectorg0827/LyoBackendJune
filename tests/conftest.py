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

from lyo_app.models.enhanced import Base


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
    from lyo_app.models.enhanced import User  # noqa: F401
    try:
        from lyo_app.models.clips import Clip, ClipAnnotation, ClipComment  # noqa: F401
    except ImportError:
        pass
    try:
        from lyo_app.models.notebook import NotebookEntry, NotebookTag  # noqa: F401
    except ImportError:
        pass
    try:
        from lyo_app.models.social import Follow, Reaction, Conversation, Message  # noqa: F401
    except ImportError:
        pass
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
        # In-app notification rows live in the router module; without this
        # import create_all skips the notifications table and every service
        # action that notifies (follow, comment, ...) rolls back mid-test.
        from lyo_app.routers.notifications import Notification  # noqa: F401
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
    try:
        from lyo_app.skills.models import Skill, SkillEdge, SkillTag  # noqa: F401
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


@pytest_asyncio.fixture(scope="function")
async def async_client(db_session):
    """HTTP client over the real app with the DB swapped for the test session.

    Route tests (feeds/community/...) drive the full request/response cycle;
    the app's get_db dependency is overridden so everything lands in the
    per-test in-memory database.
    """
    from httpx import ASGITransport, AsyncClient

    from lyo_app.core.database import get_db
    from lyo_app.enhanced_main import app

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    # The security middleware rate-limits by client IP, and every ASGI test
    # request shares one — a module's worth of register/login calls trips the
    # 10/min auth limit. Each test starts with a clean window, like its DB.
    from lyo_app.core.rate_limiter import in_memory_rate_limiter

    in_memory_rate_limiter.clients.clear()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture(scope="function")
async def client(async_client):
    """Alias — community/gamification route tests use the name `client`."""
    return async_client


@pytest_asyncio.fixture(scope="function")
async def auth_headers(async_client) -> dict:
    """Register + log in a fresh user through the API; return its bearer header."""
    user_data = {
        "email": "conftest_user@example.com",
        "username": "conftest_user",
        "password": "testpassword123",
        "confirm_password": "testpassword123",
        "first_name": "Test",
        "last_name": "User",
    }
    # /api/v1/auth/register returns 200 {"message", "user_id"}; the token
    # comes from the follow-up login call.
    response = await async_client.post("/api/v1/auth/register", json=user_data)
    assert response.status_code in (200, 201), f"register failed: {response.text}"

    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": user_data["email"], "password": user_data["password"]},
    )
    assert response.status_code == 200, f"login failed: {response.text}"
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest_asyncio.fixture(scope="function")
async def second_auth_headers(async_client) -> dict:
    """A second authenticated user, for tests exercising member/other roles."""
    user_data = {
        "email": "conftest_user2@example.com",
        "username": "conftest_user2",
        "password": "testpassword123",
        "confirm_password": "testpassword123",
        "first_name": "Second",
        "last_name": "User",
    }
    response = await async_client.post("/api/v1/auth/register", json=user_data)
    assert response.status_code in (200, 201), f"register failed: {response.text}"

    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": user_data["email"], "password": user_data["password"]},
    )
    assert response.status_code == 200, f"login failed: {response.text}"
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
