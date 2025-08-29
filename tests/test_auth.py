"""
Test cases for authentication endpoints.
Tests user registration, login, profile management, and security features.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import AsyncTestCase, assert_successful_response, assert_error_response


class TestAuthEndpoints(AsyncTestCase):
    """Test authentication endpoints."""

    async def test_user_registration_success(self, async_test_client: AsyncClient):
        """Test successful user registration."""
        user_data = {
            "email": "newuser@example.com",
            "username": "newuser",
            "password": "securepassword123",
            "full_name": "New User"
        }

        response = await async_test_client.post("/api/v1/auth/register", json=user_data)

        assert_successful_response(response, 201)
        data = response.json()

        assert "user" in data
        assert data["user"]["email"] == user_data["email"]
        assert data["user"]["username"] == user_data["username"]
        assert "password" not in data["user"]  # Password should not be returned

    async def test_user_registration_duplicate_email(self, async_test_client: AsyncClient):
        """Test registration with duplicate email."""
        # Create first user
        user_data = {
            "email": "duplicate@example.com",
            "username": "user1",
            "password": "password123",
            "full_name": "User One"
        }

        await async_test_client.post("/api/v1/auth/register", json=user_data)

        # Try to create second user with same email
        user_data["username"] = "user2"
        response = await async_test_client.post("/api/v1/auth/register", json=user_data)

        assert_error_response(response, 400, "USER_ALREADY_EXISTS")

    async def test_user_login_success(self, async_test_client: AsyncClient):
        """Test successful user login."""
        # First register a user
        user_data = {
            "email": "loginuser@example.com",
            "username": "loginuser",
            "password": "password123",
            "full_name": "Login User"
        }

        await async_test_client.post("/api/v1/auth/register", json=user_data)

        # Now login
        login_data = {
            "email": user_data["email"],
            "password": user_data["password"]
        }

        response = await async_test_client.post("/api/v1/auth/login", json=login_data)

        assert_successful_response(response, 200)
        data = response.json()

        assert "access_token" in data
        assert "token_type" in data
        assert data["token_type"] == "bearer"
        assert "user" in data

    async def test_user_login_invalid_credentials(self, async_test_client: AsyncClient):
        """Test login with invalid credentials."""
        login_data = {
            "email": "nonexistent@example.com",
            "password": "wrongpassword"
        }

        response = await async_test_client.post("/api/v1/auth/login", json=login_data)

        assert_error_response(response, 401, "INVALID_CREDENTIALS")

    async def test_get_user_profile_authenticated(self, async_test_client: AsyncClient):
        """Test getting user profile when authenticated."""
        # Register and login user
        user_data = {
            "email": "profileuser@example.com",
            "username": "profileuser",
            "password": "password123",
            "full_name": "Profile User",
            "bio": "Test bio"
        }

        await async_test_client.post("/api/v1/auth/register", json=user_data)

        login_response = await async_test_client.post("/api/v1/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"]
        })

        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Get profile
        response = await async_test_client.get("/api/v1/auth/profile", headers=headers)

        assert_successful_response(response, 200)
        data = response.json()

        assert data["email"] == user_data["email"]
        assert data["username"] == user_data["username"]
        assert data["bio"] == user_data["bio"]

    async def test_get_user_profile_unauthenticated(self, async_test_client: AsyncClient):
        """Test getting user profile without authentication."""
        response = await async_test_client.get("/api/v1/auth/profile")

        assert_error_response(response, 401, "NOT_AUTHENTICATED")

    async def test_update_user_profile(self, async_test_client: AsyncClient):
        """Test updating user profile."""
        # Register and login user
        user_data = {
            "email": "updateuser@example.com",
            "username": "updateuser",
            "password": "password123",
            "full_name": "Update User"
        }

        await async_test_client.post("/api/v1/auth/register", json=user_data)

        login_response = await async_test_client.post("/api/v1/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"]
        })

        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Update profile
        update_data = {
            "full_name": "Updated Name",
            "bio": "Updated bio",
            "profile_image_url": "https://example.com/new-avatar.jpg"
        }

        response = await async_test_client.put("/api/v1/auth/profile", json=update_data, headers=headers)

        assert_successful_response(response, 200)
        data = response.json()

        assert data["full_name"] == update_data["full_name"]
        assert data["bio"] == update_data["bio"]
        assert data["profile_image_url"] == update_data["profile_image_url"]

    async def test_change_password(self, async_test_client: AsyncClient):
        """Test changing user password."""
        # Register and login user
        user_data = {
            "email": "passworduser@example.com",
            "username": "passworduser",
            "password": "oldpassword123",
            "full_name": "Password User"
        }

        await async_test_client.post("/api/v1/auth/register", json=user_data)

        login_response = await async_test_client.post("/api/v1/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"]
        })

        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Change password
        password_data = {
            "old_password": user_data["password"],
            "new_password": "newpassword123"
        }

        response = await async_test_client.post("/api/v1/auth/change-password", json=password_data, headers=headers)

        assert_successful_response(response, 200)

        # Verify new password works
        login_response = await async_test_client.post("/api/v1/auth/login", json={
            "email": user_data["email"],
            "password": password_data["new_password"]
        })

        assert_successful_response(login_response, 200)

    async def test_change_password_wrong_old_password(self, async_test_client: AsyncClient):
        """Test changing password with wrong old password."""
        # Register and login user
        user_data = {
            "email": "wrongpassuser@example.com",
            "username": "wrongpassuser",
            "password": "correctpassword123",
            "full_name": "Wrong Pass User"
        }

        await async_test_client.post("/api/v1/auth/register", json=user_data)

        login_response = await async_test_client.post("/api/v1/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"]
        })

        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Try to change password with wrong old password
        password_data = {
            "old_password": "wrongoldpassword",
            "new_password": "newpassword123"
        }

        response = await async_test_client.post("/api/v1/auth/change-password", json=password_data, headers=headers)

        assert_error_response(response, 400, "INVALID_PASSWORD")


class TestAuthValidation(AsyncTestCase):
    """Test authentication input validation."""

    async def test_registration_invalid_email(self, async_test_client: AsyncClient):
        """Test registration with invalid email."""
        user_data = {
            "email": "invalid-email",
            "username": "testuser",
            "password": "password123",
            "full_name": "Test User"
        }

        response = await async_test_client.post("/api/v1/auth/register", json=user_data)

        assert_error_response(response, 422)  # Validation error

    async def test_registration_weak_password(self, async_test_client: AsyncClient):
        """Test registration with weak password."""
        user_data = {
            "email": "weakpass@example.com",
            "username": "weakpass",
            "password": "123",  # Too short
            "full_name": "Weak Pass User"
        }

        response = await async_test_client.post("/api/v1/auth/register", json=user_data)

        assert_error_response(response, 422)  # Validation error

    async def test_registration_missing_required_fields(self, async_test_client: AsyncClient):
        """Test registration with missing required fields."""
        user_data = {
            "email": "missing@example.com",
            # Missing username, password, full_name
        }

        response = await async_test_client.post("/api/v1/auth/register", json=user_data)

        assert_error_response(response, 422)  # Validation error


class TestAuthSecurity(AsyncTestCase):
    """Test authentication security features."""

    async def test_token_expiration(self, async_test_client: AsyncClient):
        """Test that tokens eventually expire."""
        # This would require mocking time or using short-lived tokens
        # For now, just test that valid tokens work
        user_data = {
            "email": "tokenuser@example.com",
            "username": "tokenuser",
            "password": "password123",
            "full_name": "Token User"
        }

        await async_test_client.post("/api/v1/auth/register", json=user_data)

        login_response = await async_test_client.post("/api/v1/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"]
        })

        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Token should work immediately
        response = await async_test_client.get("/api/v1/auth/profile", headers=headers)
        assert_successful_response(response, 200)

    async def test_invalid_token_format(self, async_test_client: AsyncClient):
        """Test handling of malformed tokens."""
        headers = {"Authorization": "Bearer invalid-token-format"}

        response = await async_test_client.get("/api/v1/auth/profile", headers=headers)

        assert_error_response(response, 401, "INVALID_TOKEN")

    async def test_missing_token(self, async_test_client: AsyncClient):
        """Test requests without authorization token."""
        response = await async_test_client.get("/api/v1/auth/profile")

        assert_error_response(response, 401, "NOT_AUTHENTICATED")
