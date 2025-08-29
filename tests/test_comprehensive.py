"""
Comprehensive Test Suite for LyoBackend
Unit tests, integration tests, and API tests
"""

import pytest
import asyncio
from typing import Dict, Any, Optional
from unittest.mock import Mock, AsyncMock, patch
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from lyo_app.enhanced_main import create_app
from lyo_app.core.database import get_db, init_db, close_db
from lyo_app.core.enhanced_config import settings
from lyo_app.auth.models import User
from lyo_app.auth.schemas import UserCreate, UserLogin


# Test Database Setup
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_engine():
    """Create test database engine."""
    # Use SQLite for testing
    test_database_url = "sqlite+aiosqlite:///./test_lyo_app.db"

    engine = create_async_engine(
        test_database_url,
        echo=False,
        future=True,
        pool_pre_ping=True,
    )

    # Create all tables
    async with engine.begin() as conn:
        from lyo_app.core.database import Base
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def test_db_session(test_engine):
    """Create test database session."""
    async_session = sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )

    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
def test_client():
    """Create test client for API testing."""
    app = create_app()
    with TestClient(app) as client:
        yield client


@pytest.fixture
def test_user_data() -> Dict[str, Any]:
    """Sample user data for testing."""
    return {
        "username": "testuser",
        "email": "test@example.com",
        "password": "testpassword123",
        "full_name": "Test User"
    }


@pytest.fixture
def test_course_data() -> Dict[str, Any]:
    """Sample course data for testing."""
    return {
        "title": "Test Course",
        "description": "A test course for unit testing",
        "instructor": "Test Instructor",
        "duration": 60,
        "difficulty": "beginner",
        "tags": ["test", "python"],
        "thumbnail_url": "https://example.com/thumbnail.jpg"
    }


# Unit Tests
class TestUserModel:
    """Test User model functionality."""

    def test_user_creation(self, test_user_data):
        """Test creating a user instance."""
        user = User(
            username=test_user_data["username"],
            email=test_user_data["email"],
            full_name=test_user_data["full_name"]
        )

        assert user.username == test_user_data["username"]
        assert user.email == test_user_data["email"]
        assert user.full_name == test_user_data["full_name"]
        assert user.is_verified == False
        assert user.followers == 0
        assert user.following == 0

    def test_user_str_representation(self, test_user_data):
        """Test user string representation."""
        user = User(
            username=test_user_data["username"],
            email=test_user_data["email"]
        )

        assert str(user) == f"User(id=None, username={test_user_data['username']}, email={test_user_data['email']})"


class TestConfiguration:
    """Test configuration management."""

    def test_development_config(self):
        """Test development environment configuration."""
        # Mock development environment
        with patch.object(settings, 'ENVIRONMENT', 'development'):
            assert settings.is_development() == True
            assert settings.is_production() == False
            assert settings.DEBUG == True

    def test_production_config_validation(self):
        """Test production configuration validation."""
        with patch.object(settings, 'ENVIRONMENT', 'production'):
            # Should require certain settings in production
            assert settings.is_production() == True

    def test_database_url_selection(self):
        """Test database URL selection based on environment."""
        # Development should use SQLite
        with patch.object(settings, 'ENVIRONMENT', 'development'):
            db_url = settings.get_database_url()
            assert "sqlite" in db_url

        # Production should use PostgreSQL
        with patch.object(settings, 'ENVIRONMENT', 'production'):
            with patch.object(settings, 'DATABASE_URL', 'postgresql+asyncpg://user:pass@localhost/db'):
                db_url = settings.get_database_url()
                assert "postgresql" in db_url


# Integration Tests
class TestDatabaseOperations:
    """Test database operations."""

    @pytest.mark.asyncio
    async def test_database_connection(self, test_db_session):
        """Test database connection and basic operations."""
        # Test that we can execute a simple query
        result = await test_db_session.execute("SELECT 1")
        assert result.scalar() == 1

    @pytest.mark.asyncio
    async def test_user_creation_in_db(self, test_db_session, test_user_data):
        """Test creating a user in the database."""
        # Create user
        user = User(
            username=test_user_data["username"],
            email=test_user_data["email"],
            full_name=test_user_data["full_name"]
        )

        test_db_session.add(user)
        await test_db_session.commit()
        await test_db_session.refresh(user)

        # Verify user was created
        assert user.id is not None
        assert user.username == test_user_data["username"]
        assert user.email == test_user_data["email"]

        # Test retrieval
        retrieved_user = await test_db_session.get(User, user.id)
        assert retrieved_user is not None
        assert retrieved_user.username == test_user_data["username"]


# API Tests
class TestAuthAPI:
    """Test authentication API endpoints."""

    def test_health_check(self, test_client):
        """Test health check endpoint."""
        response = test_client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "environment" in data

    def test_root_endpoint(self, test_client):
        """Test root endpoint."""
        response = test_client.get("/")
        assert response.status_code == 200

        data = response.json()
        assert "name" in data
        assert "version" in data
        assert "status" in data
        assert data["status"] == "operational"

    @pytest.mark.asyncio
    async def test_user_registration(self, test_client, test_user_data):
        """Test user registration endpoint."""
        # Mock the database operations
        with patch('lyo_app.auth.routes.get_db') as mock_get_db:
            mock_session = AsyncMock()
            mock_get_db.return_value.__aenter__.return_value = mock_session

            # Mock user creation
            mock_user = User(
                id=1,
                username=test_user_data["username"],
                email=test_user_data["email"],
                full_name=test_user_data["full_name"]
            )
            mock_session.add.return_value = None
            mock_session.commit.return_value = None
            mock_session.refresh.return_value = None

            response = test_client.post(
                "/api/v1/auth/register",
                json=test_user_data
            )

            # Should return 201 for successful registration
            assert response.status_code in [200, 201]

    def test_invalid_registration_data(self, test_client):
        """Test registration with invalid data."""
        invalid_data = {
            "username": "",  # Invalid: empty username
            "email": "invalid-email",  # Invalid: bad email format
            "password": "123"  # Invalid: too short
        }

        response = test_client.post(
            "/api/v1/auth/register",
            json=invalid_data
        )

        # Should return validation error
        assert response.status_code == 422

        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "VALIDATION_ERROR"


class TestErrorHandling:
    """Test error handling and responses."""

    def test_404_error(self, test_client):
        """Test 404 error response."""
        response = test_client.get("/nonexistent-endpoint")
        assert response.status_code == 404

        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "HTTP_404"

    def test_method_not_allowed(self, test_client):
        """Test method not allowed error."""
        response = test_client.post("/health")  # GET only endpoint
        assert response.status_code == 405

        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "HTTP_405"


class TestCORS:
    """Test CORS configuration."""

    def test_cors_headers(self, test_client):
        """Test CORS headers are present."""
        response = test_client.options("/health")
        assert response.status_code == 200

        # Check CORS headers
        assert "access-control-allow-origin" in response.headers
        assert "access-control-allow-methods" in response.headers
        assert "access-control-allow-headers" in response.headers


# Performance Tests
class TestPerformance:
    """Test performance and load handling."""

    def test_response_time(self, test_client):
        """Test that responses are reasonably fast."""
        import time

        start_time = time.time()
        response = test_client.get("/health")
        end_time = time.time()

        assert response.status_code == 200
        assert end_time - start_time < 1.0  # Should respond within 1 second

    def test_concurrent_requests(self, test_client):
        """Test handling multiple concurrent requests."""
        import concurrent.futures
        import requests

        def make_request():
            try:
                response = test_client.get("/health")
                return response.status_code
            except Exception:
                return None

        # Make 10 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(10)]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]

        # All requests should succeed
        successful_requests = [r for r in results if r == 200]
        assert len(successful_requests) == 10


# Security Tests
class TestSecurity:
    """Test security features."""

    def test_rate_limiting(self, test_client):
        """Test rate limiting functionality."""
        # Make multiple rapid requests
        responses = []
        for _ in range(10):
            response = test_client.get("/health")
            responses.append(response.status_code)

        # Should not be rate limited for health endpoint
        # (rate limiting might be applied to other endpoints)
        assert all(code == 200 for code in responses)

    def test_input_validation(self, test_client):
        """Test input validation and sanitization."""
        # Test SQL injection attempt
        malicious_data = {
            "username": "test'; DROP TABLE users; --",
            "email": "test@example.com",
            "password": "password123"
        }

        response = test_client.post(
            "/api/v1/auth/register",
            json=malicious_data
        )

        # Should either validate and reject, or sanitize
        assert response.status_code in [200, 201, 422]


# Configuration Tests
@pytest.mark.parametrize("environment", ["development", "staging", "production"])
def test_environment_configuration(environment):
    """Test configuration for different environments."""
    with patch.object(settings, 'ENVIRONMENT', environment):
        if environment == "development":
            assert settings.is_development() == True
            assert settings.DEBUG == True
        elif environment == "production":
            assert settings.is_production() == True
            # In production, debug should be False
            assert settings.DEBUG == False


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
