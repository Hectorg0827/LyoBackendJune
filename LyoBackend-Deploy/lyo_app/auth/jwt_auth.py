"""JWT authentication system with access and refresh tokens."""

import jwt
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

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT bearer token extraction
security = HTTPBearer(auto_error=False)


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
    return pwd_context.hash(password)


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


def verify_token(token: str, expected_type: str = "access") -> TokenData:
    """
    Verify and decode JWT token.
    
    Args:
        token: JWT token string
        expected_type: Expected token type ("access" or "refresh")
        
    Returns:
        TokenData object with decoded claims
        
    Raises:
        AuthenticationProblem: If token is invalid or expired
    """
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


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    """
    Authenticate user with email and password.
    
    Returns:
        User object if authentication successful, None otherwise
    """
    user = db.query(User).filter(User.email == email).first()
    
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
        
        db.commit()
        return None
    
    # Reset login attempts on successful auth
    if user.login_attempts > 0:
        user.login_attempts = 0
        user.locked_until = None
    
    user.last_login_at = datetime.utcnow()
    db.commit()
    
    return user


def check_account_locked(user: User) -> bool:
    """Check if user account is locked due to failed login attempts."""
    if not user.locked_until:
        return False
    
    return datetime.utcnow() < user.locked_until


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
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
    token_data = verify_token(token, "access")
    
    user = db.query(User).filter(User.id == token_data.user_id).first()
    
    if not user:
        raise AuthorizationProblem("User not found")
    
    if not user.is_active:
        raise AuthorizationProblem("Account is inactive")
    
    if check_account_locked(user):
        raise AuthorizationProblem("Account is temporarily locked due to failed login attempts")
    
    return user


async def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
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
    """Simple in-memory rate limiter for authentication endpoints."""
    
    def __init__(self):
        self.attempts: Dict[str, Dict[str, Any]] = {}
    
    def check_rate_limit(self, identifier: str, max_attempts: int = 5, window_minutes: int = 15) -> bool:
        """
        Check if identifier is within rate limit.
        
        Args:
            identifier: IP address or user identifier
            max_attempts: Maximum attempts allowed
            window_minutes: Time window in minutes
            
        Returns:
            True if within limit, False if exceeded
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
        self.attempts.pop(identifier, None)


# Global rate limiter instance
rate_limiter = RateLimiter()
