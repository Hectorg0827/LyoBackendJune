"""
Production JWT authentication with refresh tokens.
Implements secure authentication following best practices.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Any, Dict
import secrets
import hashlib
import bcrypt
import jwt
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.core.database import get_db
from lyo_app.auth.models import User
from lyo_app.core.errors import AuthenticationError, AuthorizationError
from lyo_app.core.config import settings

logger = logging.getLogger(__name__)

# JWT Configuration
JWT_ALGORITHM = getattr(settings, "JWT_ALGORITHM", "HS256")
JWT_SECRET_KEY = getattr(settings, "JWT_SECRET_KEY", "your-secret-key-here")
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = getattr(settings, "JWT_ACCESS_TOKEN_EXPIRE_MINUTES", 30)
JWT_REFRESH_TOKEN_EXPIRE_DAYS = getattr(settings, "JWT_REFRESH_TOKEN_EXPIRE_DAYS", 30)

# Security
security = HTTPBearer()


def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def verify_password(password: str, hashed_password: str) -> bool:
    """Verify password against hash."""
    password_bytes = password.encode('utf-8')
    hashed_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hashed_bytes)


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token."""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({
        "exp": expire,
        "type": "access",
        "iat": datetime.utcnow(),
    })
    
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT refresh token."""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    
    to_encode.update({
        "exp": expire,
        "type": "refresh",
        "iat": datetime.utcnow(),
        "jti": secrets.token_urlsafe(32),  # JWT ID for revocation tracking
    })
    
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt


def verify_token(token: str, token_type: str = "access") -> Dict[str, Any]:
    """Verify JWT token and return payload."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        
        # Verify token type
        if payload.get("type") != token_type:
            raise AuthenticationError("Invalid token type")
        
        # Check if token is expired
        exp = payload.get("exp")
        if exp and datetime.utcnow().timestamp() > exp:
            raise AuthenticationError("Token has expired")
        
        return payload
        
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Token has expired")
    except jwt.InvalidTokenError:
        raise AuthenticationError("Invalid token")


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """Get user by email."""
    from sqlalchemy import select
    
    result = await db.execute(select(User).filter(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: str) -> Optional[User]:
    """Get user by ID."""
    from sqlalchemy import select
    
    result = await db.execute(select(User).filter(User.id == user_id))
    return result.scalar_one_or_none()


async def authenticate_user(db: AsyncSession, email: str, password: str) -> Optional[User]:
    """Authenticate user with email and password."""
    user = await get_user_by_email(db, email)
    
    if not user:
        return None
    
    if not verify_password(password, user.hashed_password):
        return None
    
    if not user.is_active:
        return None
    
    # Update last login
    user.last_login = datetime.utcnow()
    await db.commit()
    
    return user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Get current user from JWT token."""
    
    if not credentials:
        raise AuthenticationError("Authorization header required")
    
    token = credentials.credentials
    
    try:
        payload = verify_token(token, "access")
        user_id = payload.get("sub")
        
        if not user_id:
            raise AuthenticationError("Invalid token payload")
        
        user = await get_user_by_id(db, user_id)
        
        if not user:
            raise AuthenticationError("User not found")
        
        if not user.is_active:
            raise AuthenticationError("User account is disabled")
        
        return user
        
    except Exception as e:
        if isinstance(e, (AuthenticationError, AuthorizationError)):
            raise
        logger.exception("Error getting current user")
        raise AuthenticationError("Invalid authentication credentials")


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Get current active user (convenience function)."""
    if not current_user.is_active:
        raise AuthenticationError("User account is disabled")
    return current_user


async def require_user(current_user: User = Depends(get_current_active_user)) -> User:
    """Require authenticated user (alias for get_current_active_user)."""
    return current_user


async def require_verified_user(current_user: User = Depends(require_user)) -> User:
    """Require verified user."""
    if not current_user.is_verified:
        raise AuthorizationError("Email verification required")
    return current_user


async def require_superuser(current_user: User = Depends(require_user)) -> User:
    """Require superuser privileges."""
    if not current_user.is_superuser:
        raise AuthorizationError("Superuser privileges required")
    return current_user


class AuthService:
    """Authentication service with user management."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_user(
        self,
        email: str,
        password: str,
        full_name: Optional[str] = None,
        username: Optional[str] = None
    ) -> User:
        """Create a new user."""
        from sqlalchemy import select
        from lyo_app.models.production import UserProfile
        
        # Check if user already exists
        existing_user = await get_user_by_email(self.db, email)
        if existing_user:
            raise HTTPException(status_code=409, detail="User already exists")
        
        # Check username uniqueness if provided
        if username:
            result = await self.db.execute(select(User).filter(User.username == username))
            if result.scalar_one_or_none():
                raise HTTPException(status_code=409, detail="Username already taken")
        
        # Create user
        hashed_password = hash_password(password)
        user = User(
            email=email,
            username=username,
            full_name=full_name,
            hashed_password=hashed_password,
            is_active=True,
            is_verified=False
        )
        
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        
        # Create user profile for gamification
        profile = UserProfile(user_id=user.id)
        self.db.add(profile)
        await self.db.commit()
        
        logger.info(f"Created new user: {user.email}")
        return user
    
    async def login_user(self, email: str, password: str) -> Dict[str, Any]:
        """Login user and return tokens."""
        user = await authenticate_user(self.db, email, password)
        
        if not user:
            raise AuthenticationError("Incorrect email or password")
        
        # Create tokens
        access_token = create_access_token(data={"sub": str(user.id)})
        refresh_token = create_refresh_token(data={"sub": str(user.id)})
        
        logger.info(f"User logged in: {user.email}")
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {
                "id": str(user.id),
                "email": user.email,
                "full_name": user.full_name,
                "username": user.username,
                "is_verified": user.is_verified
            }
        }
    
    async def refresh_tokens(self, refresh_token: str) -> Dict[str, str]:
        """Refresh access token using refresh token."""
        try:
            payload = verify_token(refresh_token, "refresh")
            user_id = payload.get("sub")
            
            if not user_id:
                raise AuthenticationError("Invalid refresh token")
            
            user = await get_user_by_id(self.db, user_id)
            
            if not user or not user.is_active:
                raise AuthenticationError("User not found or inactive")
            
            # Create new tokens
            new_access_token = create_access_token(data={"sub": str(user.id)})
            new_refresh_token = create_refresh_token(data={"sub": str(user.id)})
            
            return {
                "access_token": new_access_token,
                "refresh_token": new_refresh_token,
                "token_type": "bearer"
            }
            
        except Exception as e:
            logger.exception("Error refreshing tokens")
            raise AuthenticationError("Invalid refresh token")
    
    async def update_user_profile(self, user: User, **updates) -> User:
        """Update user profile."""
        for key, value in updates.items():
            if hasattr(user, key) and key not in ["id", "hashed_password", "created_at"]:
                setattr(user, key, value)
        
        user.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(user)
        
        return user
    
    async def change_password(self, user: User, old_password: str, new_password: str) -> bool:
        """Change user password."""
        if not verify_password(old_password, user.hashed_password):
            raise AuthenticationError("Current password is incorrect")
        
        user.hashed_password = hash_password(new_password)
        user.updated_at = datetime.utcnow()
        
        await self.db.commit()
        
        logger.info(f"Password changed for user: {user.email}")
        return True


def get_auth_service(db: AsyncSession = Depends(get_db)) -> AuthService:
    """Dependency to get authentication service."""
    return AuthService(db)
