"""JWT authentication system with access and refresh tokens."""

import jwt
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from lyo_app.core.settings import settings
from lyo_app.core.problems import AuthenticationProblem, AuthorizationProblem
from lyo_app.core.database import get_db
from lyo_app.models.enhanced import User
from lyo_app.auth.jwt_cache import JWTCache
from lyo_app.core.logging import logger

# Lazy import for redis_manager to avoid startup issues
_redis_manager = None
_redis_checked = False


def _get_redis_manager():
    """Lazily get redis_manager for rate limiting."""
    global _redis_manager, _redis_checked
    if not _redis_checked:
        try:
            from lyo_app.core.redis_v2 import redis_manager
            _redis_manager = redis_manager
        except (ImportError, Exception) as e:
            logger.debug(f"Redis not available for rate limiting: {e}")
            _redis_manager = None
        _redis_checked = True
    return _redis_manager


# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT bearer token extraction
security = HTTPBearer(auto_error=False)

# Initialize JWT Cache
jwt_cache = JWTCache(ttl=300)  # 5 minutes cache

class TokenData:
    """Token payload data structure."""
    
    def __init__(self, user_id: str, token_type: str, exp: datetime, **extra):
        self.user_id = user_id
        self.token_type = token_type  # "access" or "refresh"
        self.exp = exp
        self.extra = extra


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Generate password hash."""
    # Bcrypt has a 72-byte limit, truncate if necessary
    password_bytes = password.encode('utf-8')[:72]
    return pwd_context.hash(password_bytes.decode('utf-8'))


def create_access_token(user_id: str, additional_claims: Optional[Dict[str, Any]] = None) -> str:
    """Create JWT access token."""
    expire = datetime.utcnow() + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {
        "user_id": user_id,
        "token_type": "access",
        "exp": expire,
        "iat": datetime.utcnow(),
        "iss": "lyo-backend"
    }
    
    if additional_claims:
        to_encode.update(additional_claims)
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def create_refresh_token(user_id: str) -> str:
    """Create JWT refresh token."""
    expire = datetime.utcnow() + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    
    to_encode = {
        "user_id": user_id,
        "token_type": "refresh",
        "exp": expire,
        "iat": datetime.utcnow(),
        "iss": "lyo-backend"
    }
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


async def verify_token_async(token: str, expected_type: str = "access") -> TokenData:
    """
    Verify and decode JWT token with caching.
    
    Args:
        token: JWT token string
        expected_type: Expected token type ("access" or "refresh")
        
    Returns:
        TokenData object with decoded claims
        
    Raises:
        AuthenticationProblem: If token is invalid or expired
    """
    # Try cache first for access tokens
    if expected_type == "access":
        cached_payload = await jwt_cache.get_cached_payload(token)
        if cached_payload:
            # Reconstruct TokenData from cache
            exp_timestamp = cached_payload.get("exp")
            exp_datetime = datetime.fromtimestamp(exp_timestamp)
            return TokenData(
                user_id=cached_payload.get("user_id"),
                token_type=cached_payload.get("token_type"),
                exp=exp_datetime,
                **{k: v for k, v in cached_payload.items() if k not in ["user_id", "token_type", "exp"]}
            )

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp", "iat", "user_id", "token_type"]}
        )
        
        user_id: str = payload.get("user_id")
        token_type: str = payload.get("token_type")
        exp_timestamp: float = payload.get("exp")
        
        if not user_id:
            raise AuthenticationProblem("Token missing user_id")
        
        if token_type != expected_type:
            raise AuthenticationProblem(f"Invalid token type. Expected {expected_type}")
        
        exp_datetime = datetime.fromtimestamp(exp_timestamp)
        
        # Cache successful validation for access tokens
        if expected_type == "access":
            await jwt_cache.cache_payload(token, payload)
        
        return TokenData(
            user_id=user_id,
            token_type=token_type,
            exp=exp_datetime,
            **{k: v for k, v in payload.items() if k not in ["user_id", "token_type", "exp"]}
        )
        
    except jwt.ExpiredSignatureError:
        raise AuthenticationProblem("Token has expired")
    except jwt.InvalidTokenError as e:
        raise AuthenticationProblem(f"Invalid token: {str(e)}")

def verify_token(token: str, expected_type: str = "access") -> TokenData:
    """Synchronous wrapper for verify_token (for backward compatibility)."""
    # Note: This bypasses async cache. Use verify_token_async where possible.
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp", "iat", "user_id", "token_type"]}
        )
        
        user_id: str = payload.get("user_id")
        token_type: str = payload.get("token_type")
        exp_timestamp: float = payload.get("exp")
        
        if not user_id:
            raise AuthenticationProblem("Token missing user_id")
        
        if token_type != expected_type:
            raise AuthenticationProblem(f"Invalid token type. Expected {expected_type}")
        
        exp_datetime = datetime.fromtimestamp(exp_timestamp)
        
        return TokenData(
            user_id=user_id,
            token_type=token_type,
            exp=exp_datetime,
            **{k: v for k, v in payload.items() if k not in ["user_id", "token_type", "exp"]}
        )
        
    except jwt.ExpiredSignatureError:
        raise AuthenticationProblem("Token has expired")
    except jwt.InvalidTokenError as e:
        raise AuthenticationProblem(f"Invalid token: {str(e)}")


from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# ... (imports)

async def authenticate_user(db: AsyncSession, email: str, password: str) -> Optional[User]:
    """
    Authenticate user with email and password.
    
    Returns:
        User object if authentication successful, None otherwise
    """
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalars().first()
    
    if not user:
        return None
    
    if not user.is_active:
        return None
    
    if not verify_password(password, user.password_hash):
        # Increment failed login attempts
        user.login_attempts += 1
        
        # Lock account after max attempts
        if user.login_attempts >= settings.MAX_LOGIN_ATTEMPTS:
            user.locked_until = datetime.utcnow() + timedelta(minutes=30)
        
        await db.commit()
        return None
    
    # Reset login attempts on successful auth
    if user.login_attempts > 0:
        user.login_attempts = 0
        user.locked_until = None
    
    user.last_login_at = datetime.utcnow()
    await db.commit()
    
    return user


def check_account_locked(user: User) -> bool:
    """Check if user account is locked due to failed login attempts."""
    if not user.locked_until:
        return False
    
    return datetime.utcnow() < user.locked_until


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Dependency to get current authenticated user.
    
    Returns:
        User object for authenticated user
        
    Raises:
        AuthenticationProblem: If no valid token provided
        AuthorizationProblem: If user not found or inactive
    """
    if not credentials:
        raise AuthenticationProblem("Authentication required")
    
    token = credentials.credentials
    # Use async verification with cache
    token_data = await verify_token_async(token, "access")
    
    result = await db.execute(select(User).where(User.id == token_data.user_id))
    user = result.scalars().first()
    
    if not user:
        raise AuthorizationProblem("User not found")
    
    if not user.is_active:
        raise AuthorizationProblem("Account is inactive")
    
    if check_account_locked(user):
        raise AuthorizationProblem("Account is temporarily locked due to failed login attempts")
    
    return user


async def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """
    Dependency to get current user if authenticated, None otherwise.
    
    Useful for endpoints that work for both authenticated and anonymous users.
    """
    if not credentials:
        return None
    
    try:
        return await get_current_user(credentials, db)
    except (AuthenticationProblem, AuthorizationProblem):
        return None


def require_active_user(current_user: User = Depends(get_current_user)) -> User:
    """
    Dependency that requires an active authenticated user.
    
    This is an alias for get_current_user with a clearer name.
    """
    return current_user


def require_verified_user(current_user: User = Depends(get_current_user)) -> User:
    """
    Dependency that requires a verified authenticated user.
    
    Raises:
        AuthorizationProblem: If user email is not verified
    """
    if not current_user.is_verified:
        raise AuthorizationProblem("Email verification required")
    
    return current_user


class RateLimiter:
    """Rate limiter with Redis backend support."""
    
    def __init__(self):
        self.attempts: Dict[str, Dict[str, Any]] = {}
    
    @property
    def redis_enabled(self) -> bool:
        """Check if Redis is available."""
        return _get_redis_manager() is not None
    
    async def check_rate_limit_async(self, identifier: str, max_attempts: int = 5, window_minutes: int = 15) -> bool:
        """
        Check if identifier is within rate limit (Async/Redis).
        """
        redis = _get_redis_manager()
        if redis:
            try:
                key = f"rate_limit:{identifier}"
                current = await redis.incr(key)
                if current == 1:
                    await redis.expire(key, window_minutes * 60)
                return current <= max_attempts
            except Exception as e:
                logger.warning(f"Redis rate limit check failed: {e}")
                # Fallback to in-memory
                return self.check_rate_limit(identifier, max_attempts, window_minutes)
        else:
            return self.check_rate_limit(identifier, max_attempts, window_minutes)

    def check_rate_limit(self, identifier: str, max_attempts: int = 5, window_minutes: int = 15) -> bool:
        """
        Check if identifier is within rate limit (Sync/In-memory).
        """
        now = datetime.utcnow()
        window_start = now - timedelta(minutes=window_minutes)
        
        if identifier not in self.attempts:
            self.attempts[identifier] = {"count": 1, "first_attempt": now}
            return True
        
        attempt_data = self.attempts[identifier]
        
        # Reset if outside window
        if attempt_data["first_attempt"] < window_start:
            self.attempts[identifier] = {"count": 1, "first_attempt": now}
            return True
        
        # Increment and check limit
        attempt_data["count"] += 1
        
        return attempt_data["count"] <= max_attempts
    
    def reset_attempts(self, identifier: str):
        """Reset rate limit for identifier."""
        # Just clear in-memory - to clear redis, use reset_attempts_async 
        self.attempts.pop(identifier, None)
        
    async def reset_attempts_async(self, identifier: str):
        """Reset rate limit for identifier (Async)."""
        redis = _get_redis_manager()
        if redis:
            try:
                key = f"rate_limit:{identifier}"
                await redis.delete(key)
            except Exception as e:
                logger.warning(f"Redis rate limit reset failed: {e}")
        self.attempts.pop(identifier, None)


# Global rate limiter instance
rate_limiter = RateLimiter()
