"""Pytest configuration & fixtures migrated from misnamed pytest.ini (which contained Python code)."""

import os
import pytest
from pathlib import Path

def pytest_configure(config):
    config.addinivalue_line("markers", "performance: performance tests")
    config.addinivalue_line("markers", "integration: integration tests")
    config.addinivalue_line("markers", "slow: slow tests")
    config.addinivalue_line("markers", "database: db tests")
    config.addinivalue_line("markers", "api: api tests")
    os.environ.setdefault("ENVIRONMENT", "testing")
    os.environ.setdefault("DEBUG", "False")
    os.environ.setdefault("TESTING", "True")
    # Provide mandatory config values so pydantic Settings doesn't fail during import
    os.environ.setdefault("SECRET_KEY", "test-secret-key")
    os.environ.setdefault("GCS_BUCKET_NAME", "test-bucket")
    os.environ.setdefault("GCS_PROJECT_ID", "test-project")
    # Optional cloud vars to avoid downstream conditional logic issues
    os.environ.setdefault("GCS_CREDENTIALS_PATH", "")
    os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
    os.environ.setdefault("GOOGLE_AI_API_KEY", "test-google-key")

@pytest.fixture(scope="session")
def test_data_dir():
    return Path(__file__).parent / "test_data"

@pytest.fixture(scope="session")
def fixtures_dir():
    return Path(__file__).parent / "fixtures"
"""
Comprehensive Testing Infrastructure
Provides base test classes, fixtures, and utilities for testing the LyoBackend.
Enhanced with performance testing, error handling, and comprehensive mocking.
"""

import asyncio
import os
import pytest
import pytest_asyncio
from typing import AsyncGenerator, Generator, Dict, Any, Optional
from unittest.mock import Mock, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import AsyncClient

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool, NullPool

from lyo_app.core.database import Base
from lyo_app.enhanced_main import create_app
from lyo_app.core.database import get_db

# Test Database Configuration
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")

# Test database engine
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    poolclass=StaticPool if "sqlite" in TEST_DATABASE_URL else NullPool,
    connect_args={"check_same_thread": False} if "sqlite" in TEST_DATABASE_URL else {}
)

# Test session factory
TestingSessionLocal = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


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
    # Import all models to ensure they're registered
    from lyo_app.auth.models import User  # noqa: F401
    from lyo_app.auth.rbac import Role, Permission, role_permissions, user_roles  # noqa: F401
    from lyo_app.learning.models import Course, Lesson, CourseEnrollment, LessonCompletion  # noqa: F401
    from lyo_app.feeds.models import Post, Comment, PostReaction, CommentReaction, UserFollow, FeedItem  # noqa: F401
    from lyo_app.community.models import StudyGroup, GroupMembership, CommunityEvent, EventAttendance  # noqa: F401
    from lyo_app.gamification.models import UserXP, Achievement, UserAchievement, Streak, UserLevel, LeaderboardEntry, Badge, UserBadge  # noqa: F401
    from lyo_app.ai_study.models import StudySession, StudyMessage, GeneratedQuiz, QuizAttempt, StudySessionAnalytics  # noqa: F401

    # Create all tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestingSessionLocal() as session:
        yield session
        await session.rollback()


@pytest.fixture
def test_client() -> Generator[TestClient, None, None]:
    """Create test client for API testing."""
    app = create_app()
    with TestClient(app) as client:
        yield client


@pytest.fixture
async def async_test_client(db_session) -> AsyncGenerator[AsyncClient, None]:
    """Create async test client for API testing."""
    app = create_app()

    # Override database dependency
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(app=app, base_url="http://testserver") as client:
        yield client


@pytest.fixture
def mock_user_data() -> dict:
    """Sample user data for testing."""
    return {
        "id": "test-user-id",
        "username": "testuser",
        "email": "test@example.com",
        "password": "hashed_password",
        "full_name": "Test User",
        "bio": "Test bio",
        "profile_image_url": "https://example.com/avatar.jpg",
        "followers": 10,
        "following": 5,
        "is_verified": False,
        "joined_at": "2024-01-01T00:00:00Z",
        "last_active_at": "2024-01-01T00:00:00Z"
    }


@pytest.fixture
def mock_course_data() -> dict:
    """Sample course data for testing."""
    return {
        "id": "test-course-id",
        "title": "Test Course",
        "description": "A comprehensive test course",
        "instructor": "Test Instructor",
        "duration": 120,
        "difficulty": "intermediate",
        "tags": ["test", "python", "programming"],
        "thumbnail_url": "https://example.com/course.jpg",
        "progress": 0,
        "is_enrolled": False,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z"
    }


@pytest.fixture
def mock_post_data() -> dict:
    """Sample post data for testing."""
    return {
        "id": "test-post-id",
        "content": "This is a test post",
        "image_urls": ["https://example.com/image1.jpg"],
        "video_url": None,
        "likes": 5,
        "comments": 2,
        "shares": 1,
        "is_liked": False,
        "is_bookmarked": False,
        "created_at": "2024-01-01T00:00:00Z",
        "tags": ["test", "sample"],
        "author": {
            "id": "test-user-id",
            "username": "testuser",
            "full_name": "Test User"
        }
    }


class MockRedis:
    """Mock Redis client for testing."""

    def __init__(self):
        self.data = {}

    async def get(self, key: str) -> str:
        return self.data.get(key)

    async def set(self, key: str, value: str, ex: int = None) -> bool:
        self.data[key] = value
        return True

    async def delete(self, key: str) -> int:
        if key in self.data:
            del self.data[key]
            return 1
        return 0

    async def exists(self, key: str) -> int:
        return 1 if key in self.data else 0

    async def expire(self, key: str, time: int) -> bool:
        return True

    async def ping(self) -> bool:
        return True


@pytest.fixture
def mock_redis() -> MockRedis:
    """Mock Redis client for testing."""
    return MockRedis()


class MockAIClient:
    """Mock AI client for testing."""

    async def generate_response(self, prompt: str, **kwargs) -> dict:
        return {
            "response": f"Mock response for: {prompt[:50]}...",
            "model": "mock-gemini",
            "tokens_used": 100
        }

    async def analyze_content(self, content: str) -> dict:
        return {
            "sentiment": "positive",
            "topics": ["test", "mock"],
            "confidence": 0.95
        }

    async def generate_quiz(self, content: str, **kwargs) -> dict:
        return {
            "questions": [
                {
                    "question": "Test question?",
                    "options": ["A", "B", "C", "D"],
                    "correct_answer": 0
                }
            ]
        }


@pytest.fixture
def mock_ai_client() -> MockAIClient:
    """Mock AI client for testing."""
    return MockAIClient()


class BaseTestCase:
    """Base test case with common utilities."""

    @pytest.fixture(autouse=True)
    def setup_method(self, db_session):
        """Setup method called before each test."""
        self.db = db_session

    async def create_test_user(
        self,
        email: str = "test@example.com",
        username: str = "testuser",
        password: str = "testpass123",
        **kwargs
    ):
        """Create a test user in the database."""
        from lyo_app.auth.models import User
        from lyo_app.auth.security import get_password_hash

        user = User(
            id="test-user-id",
            email=email,
            username=username,
            hashed_password=get_password_hash(password),
            is_active=True,
            is_verified=True,
            **kwargs
        )

        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def create_test_course(
        self,
        title: str = "Test Course",
        instructor: str = "Test Instructor",
        **kwargs
    ):
        """Create a test course in the database."""
        from lyo_app.learning.models import Course

        course = Course(
            id="test-course-id",
            title=title,
            description="Test course description",
            instructor=instructor,
            duration=60,
            difficulty="beginner",
            **kwargs
        )

        self.db.add(course)
        await self.db.commit()
        await self.db.refresh(course)
        return course

    async def create_test_post(
        self,
        author_id: str,
        content: str = "Test post content",
        **kwargs
    ):
        """Create a test post in the database."""
        from lyo_app.feeds.models import Post

        post = Post(
            id="test-post-id",
            author_id=author_id,
            content=content,
            **kwargs
        )

        self.db.add(post)
        await self.db.commit()
        await self.db.refresh(post)
        return post

    def get_auth_headers(self, token: str) -> Dict[str, str]:
        """Get authorization headers for authenticated requests."""
        return {"Authorization": f"Bearer {token}"}


class AsyncTestCase(BaseTestCase):
    """Base test case for async tests."""

    @pytest.fixture(autouse=True)
    async def setup_method_async(self, db_session):
        """Async setup method called before each test."""
        self.db = db_session


# Test utilities
def assert_successful_response(response, status_code: int = 200):
    """Assert that API response is successful."""
    assert response.status_code == status_code
    data = response.json()
    assert "error" not in data or data.get("success") is not False


def assert_error_response(response, status_code: int = 400, error_code: Optional[str] = None):
    """Assert that API response contains an error."""
    assert response.status_code == status_code
    data = response.json()
    assert "error" in data

    if error_code:
        assert data["error"]["code"] == error_code


def assert_pagination_response(response, expected_items: Optional[int] = None):
    """Assert that response contains proper pagination data."""
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    assert "has_next" in data
    assert "has_prev" in data

    if expected_items is not None:
        assert len(data["items"]) == expected_items


# Mock factories
def create_mock_user(**overrides):
    """Create a mock user object."""
    from lyo_app.auth.models import User

    default_data = {
        "id": "test-user-id",
        "email": "test@example.com",
        "username": "testuser",
        "full_name": "Test User",
        "is_active": True,
        "is_verified": True,
        "created_at": "2024-01-01T00:00:00Z"
    }
    default_data.update(overrides)

    mock_user = Mock(spec=User)
    for key, value in default_data.items():
        setattr(mock_user, key, value)

    return mock_user


def create_mock_course(**overrides):
    """Create a mock course object."""
    from lyo_app.learning.models import Course

    default_data = {
        "id": "test-course-id",
        "title": "Test Course",
        "description": "Test course description",
        "instructor": "Test Instructor",
        "duration": 60,
        "difficulty": "beginner",
        "created_at": "2024-01-01T00:00:00Z"
    }
    default_data.update(overrides)

    mock_course = Mock(spec=Course)
    for key, value in default_data.items():
        setattr(mock_course, key, value)

    return mock_course


# Test data factories
def generate_test_user_data(**overrides):
    """Generate test user data."""
    import uuid
    from datetime import datetime

    data = {
        "id": str(uuid.uuid4()),
        "email": f"test_{uuid.uuid4().hex[:8]}@example.com",
        "username": f"testuser_{uuid.uuid4().hex[:8]}",
        "full_name": "Test User",
        "bio": "Test bio",
        "is_active": True,
        "is_verified": True,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }
    data.update(overrides)
    return data


def generate_test_course_data(**overrides):
    """Generate test course data."""
    import uuid
    from datetime import datetime

    data = {
        "id": str(uuid.uuid4()),
        "title": f"Test Course {uuid.uuid4().hex[:8]}",
        "description": "Test course description",
        "instructor": "Test Instructor",
        "duration": 60,
        "difficulty": "beginner",
        "category": "programming",
        "tags": ["test", "programming"],
        "thumbnail_url": "https://example.com/thumbnail.jpg",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }
    data.update(overrides)
    return data


# Performance testing utilities
async def measure_response_time(client: AsyncClient, url: str, method: str = "GET", **kwargs) -> float:
    """Measure response time for a request."""
    import time

    start_time = time.time()
    if method.upper() == "GET":
        await client.get(url, **kwargs)
    elif method.upper() == "POST":
        await client.post(url, **kwargs)
    elif method.upper() == "PUT":
        await client.put(url, **kwargs)
    elif method.upper() == "DELETE":
        await client.delete(url, **kwargs)

    return time.time() - start_time


def assert_performance_threshold(response_time: float, threshold: float = 1.0):
    """Assert that response time is within acceptable threshold."""
    assert response_time <= threshold, f"Response time {response_time:.2f}s exceeds threshold {threshold:.2f}s"


# Environment setup for testing
def setup_test_environment():
    """Setup test environment variables."""
    os.environ.setdefault("ENVIRONMENT", "testing")
    os.environ.setdefault("DEBUG", "False")
    os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-" + "x" * 32)
    os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
    os.environ.setdefault("GOOGLE_API_KEY", "test-google-api-key")


def teardown_test_environment():
    """Clean up test environment variables."""
    test_vars = [
        "ENVIRONMENT", "DEBUG", "SECRET_KEY",
        "DATABASE_URL", "REDIS_URL", "GOOGLE_API_KEY"
    ]

    for var in test_vars:
        if var in os.environ:
            del os.environ[var]


# Setup and teardown
def pytest_configure(config):
    """Configure pytest."""
    setup_test_environment()


def pytest_unconfigure(config):
    """Unconfigure pytest."""
    teardown_test_environment()
