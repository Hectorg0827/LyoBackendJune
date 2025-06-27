"""
Unit tests for the authentication service.
Following TDD principles - tests are written before implementation.
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.auth.schemas import UserCreate, UserLogin
from lyo_app.auth.service import AuthService
from lyo_app.auth.models import User


class TestAuthService:
    """Test cases for AuthService following TDD principles."""

    @pytest.fixture
    async def auth_service(self) -> AuthService:
        """Create an AuthService instance for testing."""
        return AuthService()

    @pytest.fixture
    def valid_user_data(self) -> UserCreate:
        """Create valid user registration data."""
        return UserCreate(
            email="test@example.com",
            username="testuser",
            password="testpass123",
            confirm_password="testpass123",
            first_name="Test",
            last_name="User"
        )

    @pytest.fixture
    def invalid_user_data(self) -> UserCreate:
        """Create invalid user registration data (passwords don't match)."""
        return UserCreate(
            email="test@example.com",
            username="testuser",
            password="testpass123",
            confirm_password="differentpass",
            first_name="Test",
            last_name="User"
        )

    async def test_register_user_success(
        self, 
        auth_service: AuthService, 
        valid_user_data: UserCreate,
        db_session: AsyncSession
    ):
        """
        Test successful user registration.
        Should create a new user with hashed password.
        """
        # This test will initially fail - we'll implement to make it pass
        user = await auth_service.register_user(db_session, valid_user_data)
        
        assert user is not None
        assert user.email == valid_user_data.email
        assert user.username == valid_user_data.username
        assert user.first_name == valid_user_data.first_name
        assert user.last_name == valid_user_data.last_name
        assert user.hashed_password != valid_user_data.password  # Should be hashed
        assert user.is_active is True
        assert user.is_verified is False
        assert user.created_at is not None

    async def test_register_user_password_hashing(
        self, 
        auth_service: AuthService, 
        valid_user_data: UserCreate,
        db_session: AsyncSession
    ):
        """
        Test that password is properly hashed during registration.
        """
        user = await auth_service.register_user(db_session, valid_user_data)
        
        # Password should be hashed and verifiable
        assert auth_service.verify_password(
            valid_user_data.password, 
            user.hashed_password
        )

    async def test_register_user_duplicate_email(
        self, 
        auth_service: AuthService, 
        valid_user_data: UserCreate,
        db_session: AsyncSession
    ):
        """
        Test that registering with duplicate email raises an error.
        """
        # Register first user
        await auth_service.register_user(db_session, valid_user_data)
        
        # Try to register with same email
        duplicate_data = valid_user_data.copy()
        duplicate_data.username = "different_username"
        
        with pytest.raises(ValueError, match="Email already registered"):
            await auth_service.register_user(db_session, duplicate_data)

    async def test_register_user_duplicate_username(
        self, 
        auth_service: AuthService, 
        valid_user_data: UserCreate,
        db_session: AsyncSession
    ):
        """
        Test that registering with duplicate username raises an error.
        """
        # Register first user
        await auth_service.register_user(db_session, valid_user_data)
        
        # Try to register with same username
        duplicate_data = valid_user_data.copy()
        duplicate_data.email = "different@example.com"
        
        with pytest.raises(ValueError, match="Username already taken"):
            await auth_service.register_user(db_session, duplicate_data)

    async def test_login_success(
        self, 
        auth_service: AuthService, 
        valid_user_data: UserCreate,
        db_session: AsyncSession
    ):
        """
        Test successful user login.
        Should return a valid JWT token.
        """
        # First register a user
        await auth_service.register_user(db_session, valid_user_data)
        
        # Then try to login
        login_data = UserLogin(
            email=valid_user_data.email,
            password=valid_user_data.password
        )
        
        token = await auth_service.login(db_session, login_data)
        
        assert token is not None
        assert token.access_token is not None
        assert token.token_type == "bearer"
        assert token.expires_in > 0

    async def test_login_invalid_email(
        self, 
        auth_service: AuthService,
        db_session: AsyncSession
    ):
        """
        Test login with non-existent email.
        Should raise authentication error.
        """
        login_data = UserLogin(
            email="nonexistent@example.com",
            password="somepassword"
        )
        
        with pytest.raises(ValueError, match="Invalid credentials"):
            await auth_service.login(db_session, login_data)

    async def test_login_invalid_password(
        self, 
        auth_service: AuthService, 
        valid_user_data: UserCreate,
        db_session: AsyncSession
    ):
        """
        Test login with incorrect password.
        Should raise authentication error.
        """
        # First register a user
        await auth_service.register_user(db_session, valid_user_data)
        
        # Try to login with wrong password
        login_data = UserLogin(
            email=valid_user_data.email,
            password="wrongpassword"
        )
        
        with pytest.raises(ValueError, match="Invalid credentials"):
            await auth_service.login(db_session, login_data)

    async def test_get_user_by_id(
        self, 
        auth_service: AuthService, 
        valid_user_data: UserCreate,
        db_session: AsyncSession
    ):
        """
        Test retrieving user by ID.
        """
        # Register user
        created_user = await auth_service.register_user(db_session, valid_user_data)
        
        # Retrieve by ID
        retrieved_user = await auth_service.get_user_by_id(db_session, created_user.id)
        
        assert retrieved_user is not None
        assert retrieved_user.id == created_user.id
        assert retrieved_user.email == created_user.email

    async def test_get_user_by_email(
        self, 
        auth_service: AuthService, 
        valid_user_data: UserCreate,
        db_session: AsyncSession
    ):
        """
        Test retrieving user by email.
        """
        # Register user
        created_user = await auth_service.register_user(db_session, valid_user_data)
        
        # Retrieve by email
        retrieved_user = await auth_service.get_user_by_email(
            db_session, 
            created_user.email
        )
        
        assert retrieved_user is not None
        assert retrieved_user.email == created_user.email
        assert retrieved_user.id == created_user.id
