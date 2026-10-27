"""
Integration tests for authentication routes.
Tests the complete request/response cycle for auth endpoints.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.auth.routes import router as auth_router
from lyo_app.auth.schemas import UserCreate
from lyo_app.core.database import get_db
from unittest.mock import patch


class TestAuthRoutes:
    """Integration tests for authentication routes."""

    @pytest.fixture
    async def app(self) -> FastAPI:
        """Create test FastAPI app."""
        app = FastAPI()
        app.include_router(auth_router, prefix="/auth")
        return app

    @pytest.fixture(autouse=True)
    def mock_rate_limiter(self):
        """Mock rate limiter to avoid Redis connection."""
        with patch("lyo_app.auth.routes.auth_rate_limiter.is_allowed", return_value=(True, {})):
            yield

    @pytest.fixture
    def valid_user_data(self) -> dict:
        """Valid user registration data."""
        return {
            "email": "test@example.com",
            "username": "testuser",
            "password": "testpass123",
            "confirm_password": "testpass123",
            "first_name": "Test",
            "last_name": "User"
        }

    async def test_register_user_success(
        self,
        app: FastAPI,
        valid_user_data: dict,
        db_session: AsyncSession
    ):
        """Test successful user registration through API."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Mock the database dependency
            app.dependency_overrides[get_db] = lambda: db_session
            
            response = await client.post("/auth/register", json=valid_user_data)
            
            assert response.status_code == 201
            data = response.json()
            # /register returns a LoginResponse (token + nested user)
            assert data["access_token"]
            user = data["user"]
            assert user["email"] == valid_user_data["email"]
            assert user["username"] == valid_user_data["username"]
            assert user["first_name"] == valid_user_data["first_name"]
            assert user["last_name"] == valid_user_data["last_name"]
            assert "hashed_password" not in user  # Should not be in response
            assert "password" not in user  # Should not be in response
            assert user["is_active"] is True

    async def test_register_user_duplicate_email(
        self,
        app: FastAPI,
        valid_user_data: dict,
        db_session: AsyncSession
    ):
        """Test registration with duplicate email returns 400."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            app.dependency_overrides[get_db] = lambda: db_session
            
            # Register first user
            await client.post("/auth/register", json=valid_user_data)
            
            # Try to register with same email but different username
            duplicate_data = valid_user_data.copy()
            duplicate_data["username"] = "different_username"
            
            response = await client.post("/auth/register", json=duplicate_data)
            
            assert response.status_code == 400
            assert "Email already registered" in response.json()["detail"]

    async def test_register_user_invalid_data(
        self,
        app: FastAPI,
        db_session: AsyncSession
    ):
        """Test registration with invalid data returns 422."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            app.dependency_overrides[get_db] = lambda: db_session
            
            invalid_data = {
                "email": "not-an-email",  # Invalid email
                "username": "ab",  # Too short
                "password": "123",  # Too short
                "confirm_password": "123"
            }
            
            response = await client.post("/auth/register", json=invalid_data)
            
            assert response.status_code == 422  # Validation error

    async def test_login_success(
        self,
        app: FastAPI,
        valid_user_data: dict,
        db_session: AsyncSession
    ):
        """Test successful user login."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            app.dependency_overrides[get_db] = lambda: db_session
            
            # First register a user
            await client.post("/auth/register", json=valid_user_data)
            
            # Then login
            login_data = {
                "email": valid_user_data["email"],
                "password": valid_user_data["password"]
            }
            
            response = await client.post("/auth/login", json=login_data)
            
            assert response.status_code == 200
            data = response.json()
            assert "access_token" in data
            assert data["token_type"] == "bearer"
            assert data["expires_in"] > 0

    async def test_login_invalid_credentials(
        self,
        app: FastAPI,
        valid_user_data: dict,
        db_session: AsyncSession
    ):
        """Test login with invalid credentials returns 401."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            app.dependency_overrides[get_db] = lambda: db_session
            
            # Register a user first
            await client.post("/auth/register", json=valid_user_data)
            
            # Try to login with wrong password
            login_data = {
                "email": valid_user_data["email"],
                "password": "wrongpassword"
            }
            
            response = await client.post("/auth/login", json=login_data)
            
            assert response.status_code == 401
            assert "Invalid credentials" in response.json()["detail"]

    async def test_login_nonexistent_user(
        self,
        app: FastAPI,
        db_session: AsyncSession
    ):
        """Test login with non-existent user returns 401."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            app.dependency_overrides[get_db] = lambda: db_session
            
            login_data = {
                "email": "nonexistent@example.com",
                "password": "somepassword"
            }
            
            response = await client.post("/auth/login", json=login_data)
            
            assert response.status_code == 401
            assert "Invalid credentials" in response.json()["detail"]

    async def test_get_user_by_id(
        self,
        app: FastAPI,
        valid_user_data: dict,
        db_session: AsyncSession
    ):
        """Test getting user by ID."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            app.dependency_overrides[get_db] = lambda: db_session
            
            # Register a user first
            register_response = await client.post("/auth/register", json=valid_user_data)
            user_id = register_response.json()["user"]["id"]
            token = register_response.json()["access_token"]

            # Their own record, signed in, includes the email
            response = await client.get(
                f"/auth/users/{user_id}",
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["id"] == user_id
            assert data["email"] == valid_user_data["email"]

    async def test_get_user_requires_sign_in(
        self,
        app: FastAPI,
        valid_user_data: dict,
        db_session: AsyncSession
    ):
        """A profile cannot be read without signing in."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            app.dependency_overrides[get_db] = lambda: db_session

            register_response = await client.post("/auth/register", json=valid_user_data)
            user_id = register_response.json()["user"]["id"]

            response = await client.get(f"/auth/users/{user_id}")

            assert response.status_code in (401, 403)
            assert "email" not in response.text

    async def test_get_other_user_hides_private_fields(
        self,
        app: FastAPI,
        valid_user_data: dict,
        db_session: AsyncSession
    ):
        """Another learner's profile comes back without email or login details."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            app.dependency_overrides[get_db] = lambda: db_session

            first = await client.post("/auth/register", json=valid_user_data)
            first_id = first.json()["user"]["id"]
            second = await client.post("/auth/register", json={
                **valid_user_data,
                "email": "other@example.com",
                "username": "otheruser",
            })
            token = second.json()["access_token"]

            response = await client.get(
                f"/auth/users/{first_id}",
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["id"] == first_id
            assert data["username"] == valid_user_data["username"]
            for private in ("email", "is_verified", "last_login", "is_active"):
                assert private not in data

    async def test_schema_repair_endpoint_is_gone(self, app: FastAPI):
        """The old schema-repair route accepted any X-API-Key; it no longer exists."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/auth/fix-db-schema", headers={"X-API-Key": "anything"})

            assert response.status_code == 404

    async def test_get_user_not_found(
        self,
        app: FastAPI,
        valid_user_data: dict,
        db_session: AsyncSession
    ):
        """Test getting non-existent user returns 404."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            app.dependency_overrides[get_db] = lambda: db_session
            
            registered = await client.post("/auth/register", json=valid_user_data)
            token = registered.json()["access_token"]
            response = await client.get(
                "/auth/users/999",
                headers={"Authorization": f"Bearer {token}"},
            )
            
            assert response.status_code == 404
            assert "User not found" in response.json()["detail"]
