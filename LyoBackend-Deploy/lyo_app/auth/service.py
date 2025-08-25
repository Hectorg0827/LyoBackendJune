"""
Authentication service implementation.
Handles user registration, login, and user management operations with RBAC integration.
"""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from lyo_app.auth.models import User
from lyo_app.auth.rbac import Role, RoleType
from lyo_app.auth.schemas import UserCreate, UserLogin, Token
from lyo_app.auth.security import hash_password, verify_password, create_access_token
from lyo_app.auth.rbac_service import RBACService
from lyo_app.auth.security_middleware import InputValidator
from lyo_app.core.config import settings


class AuthService:
    """Service class for authentication operations."""

    async def register_user(self, db: AsyncSession, user_data: UserCreate) -> User:
        """
        Register a new user with input validation and automatic role assignment.
        
        Args:
            db: Database session
            user_data: User registration data
            
        Returns:
            Created user instance
            
        Raises:
            ValueError: If validation fails or email/username already exists
        """
        # Validate inputs
        try:
            email = InputValidator.validate_email(user_data.email)
            username = InputValidator.validate_username(user_data.username)
            password = InputValidator.validate_password(user_data.password)
        except ValueError as e:
            raise ValueError(f"Input validation failed: {str(e)}")
        
        # Validate password confirmation
        if user_data.password != user_data.confirm_password:
            raise ValueError("Passwords do not match")
        
        # Check if email already exists
        existing_email = await self.get_user_by_email(db, email)
        if existing_email:
            raise ValueError("Email already registered")
        
        # Check if username already exists
        existing_username = await self.get_user_by_username(db, username)
        if existing_username:
            raise ValueError("Username already taken")
        
        # Hash the password
        hashed_password = hash_password(password)
        
        # Create user with validated data
        user = User(
            email=email,
            username=username,
            hashed_password=hashed_password,
            first_name=InputValidator.validate_string(user_data.first_name or "", max_length=100) if user_data.first_name else None,
            last_name=InputValidator.validate_string(user_data.last_name or "", max_length=100) if user_data.last_name else None,
        )
        
        try:
            db.add(user)
            await db.flush()  # Get the user ID
            
            # Assign default student role
            rbac_service = RBACService(db)
            await rbac_service.assign_default_role_to_user(user.id, RoleType.STUDENT)
            
            await db.commit()
            
            # Reload user with roles
            await db.refresh(user)
            return user
            
        except IntegrityError:
            await db.rollback()
            raise ValueError("User registration failed due to database constraint")

    async def login(self, db: AsyncSession, login_data: UserLogin) -> Token:
        """
        Authenticate user and return JWT token.
        
        Args:
            db: Database session
            login_data: User login credentials
            
        Returns:
            JWT token response
            
        Raises:
            ValueError: If credentials are invalid
        """
        # Get user by email
        user = await self.get_user_by_email(db, login_data.email)
        if not user:
            raise ValueError("Invalid credentials")
        
        # Verify password
        if not verify_password(login_data.password, user.hashed_password):
            raise ValueError("Invalid credentials")
        
        # Check if user is active
        if not user.is_active:
            raise ValueError("Account is disabled")
        
        # Update last login
        user.last_login = datetime.utcnow()
        await db.commit()
        
        # Create access token
        access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
        access_token = create_access_token(
            data={"sub": str(user.id), "username": user.username},
            expires_delta=access_token_expires
        )
        
        return Token(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.access_token_expire_minutes * 60  # Convert to seconds
        )

    async def get_user_by_id(self, db: AsyncSession, user_id: int, include_roles: bool = True) -> Optional[User]:
        """
        Get user by ID with optional role loading.
        
        Args:
            db: Database session
            user_id: User ID to search for
            include_roles: Whether to load user roles
            
        Returns:
            User instance if found, None otherwise
        """
        query = select(User).where(User.id == user_id)
        if include_roles:
            query = query.options(
                selectinload(User.roles).selectinload(Role.permissions)
            )
        
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_user_by_email(self, db: AsyncSession, email: str, include_roles: bool = False) -> Optional[User]:
        """
        Get user by email address with optional role loading.
        
        Args:
            db: Database session
            email: Email address to search for
            include_roles: Whether to load user roles
            
        Returns:
            User instance if found, None otherwise
        """
        query = select(User).where(User.email == email)
        if include_roles:
            query = query.options(
                selectinload(User.roles).selectinload(Role.permissions)
            )
        
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_user_by_username(self, db: AsyncSession, username: str, include_roles: bool = False) -> Optional[User]:
        """
        Get user by username.
        
        Args:
            db: Database session
            username: Username to search for
            
        Returns:
            User instance if found, None otherwise
        """
        result = await db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """
        Verify a password against its hash.
        
        Args:
            plain_password: Plain text password
            hashed_password: Hashed password
            
        Returns:
            True if password matches, False otherwise
        """
        return verify_password(plain_password, hashed_password)
