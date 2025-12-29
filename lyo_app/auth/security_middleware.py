"""
Security middleware and utilities for LyoApp.
Implements rate limiting, input validation, and security headers.
"""

import asyncio
import hashlib
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Optional, Set, Any, List
from functools import wraps

from fastapi import HTTPException, Request, Response, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.models.enhanced import User
from lyo_app.auth.rbac import PermissionType
from lyo_app.auth.security import verify_access_token
from lyo_app.core.database import get_db_session


class SecurityConfig:
    """Security configuration constants."""
    
    # Rate limiting
    DEFAULT_RATE_LIMIT = "100/minute"
    AUTH_RATE_LIMIT = "5/minute"
    STRICT_RATE_LIMIT = "10/minute"
    
    # Request size limits
    MAX_REQUEST_SIZE = 10 * 1024 * 1024  # 10MB
    MAX_JSON_SIZE = 1 * 1024 * 1024      # 1MB
    
    # Security headers
    SECURITY_HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "microphone=(), camera=(), geolocation=()"
    }
    
    # Input validation
    MIN_PASSWORD_LENGTH = 8
    MAX_PASSWORD_BYTES = 72  # Bcrypt limit
    MAX_INPUT_LENGTH = 1000
    ALLOWED_FILE_TYPES = {".jpg", ".jpeg", ".png", ".gif", ".pdf", ".txt", ".md"}
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB


# Rate limiter setup
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",  # In production, use Redis
    default_limits=["1000/hour"]
)


class InMemoryRateLimiter:
    """Simple in-memory rate limiter for development."""
    
    def __init__(self):
        self.clients: Dict[str, List[float]] = defaultdict(list)
        self.cleanup_interval = 3600  # 1 hour
        self.last_cleanup = time.time()
    
    def is_allowed(self, client_id: str, limit: int, window: int) -> bool:
        """Check if request is allowed based on rate limit."""
        now = time.time()
        
        # Cleanup old entries periodically
        if now - self.last_cleanup > self.cleanup_interval:
            self._cleanup()
            self.last_cleanup = now
        
        # Get client requests in the current window
        client_requests = self.clients[client_id]
        window_start = now - window
        
        # Filter requests within the window
        recent_requests = [req_time for req_time in client_requests if req_time > window_start]
        
        # Update client requests
        self.clients[client_id] = recent_requests
        
        # Check if limit exceeded
        if len(recent_requests) >= limit:
            return False
        
        # Add current request
        self.clients[client_id].append(now)
        return True
    
    def _cleanup(self):
        """Remove old client data."""
        now = time.time()
        cutoff = now - 3600  # Keep last hour
        
        for client_id in list(self.clients.keys()):
            self.clients[client_id] = [
                req_time for req_time in self.clients[client_id] 
                if req_time > cutoff
            ]
            if not self.clients[client_id]:
                del self.clients[client_id]


# Global rate limiter instance
rate_limiter = InMemoryRateLimiter()


def get_client_id(request: Request) -> str:
    """Get unique client identifier for rate limiting."""
    # Try to get user ID from token
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        try:
            token = auth_header.split(" ")[1]
            payload = verify_access_token(token)
            return f"user_{payload.get('sub')}"
        except:
            pass
    
    # Fall back to IP address
    client_ip = request.client.host if request.client else "unknown"
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    
    return f"ip_{client_ip}"


async def rate_limit_middleware(request: Request, call_next):
    """Rate limiting middleware."""
    client_id = get_client_id(request)
    
    # Define rate limits for different endpoints
    path = request.url.path
    if path.startswith("/api/v1/auth/"):
        limit, window = 5, 60  # 5 requests per minute for auth
    elif path.startswith("/api/v1/admin/"):
        limit, window = 10, 60  # 10 requests per minute for admin
    else:
        limit, window = 100, 60  # 100 requests per minute for general APIs
    
    if not rate_limiter.is_allowed(client_id, limit, window):
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "error": "Rate limit exceeded",
                "detail": f"Too many requests. Limit: {limit} per {window} seconds",
                "retry_after": window
            },
            headers={"Retry-After": str(window)}
        )
    
    response = await call_next(request)
    return response


async def security_headers_middleware(request: Request, call_next):
    """Add security headers to responses."""
    response = await call_next(request)
    
    # Add security headers
    for header, value in SecurityConfig.SECURITY_HEADERS.items():
        response.headers[header] = value
    
    return response


async def request_size_middleware(request: Request, call_next):
    """Limit request size."""
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            size = int(content_length)
            if size > SecurityConfig.MAX_REQUEST_SIZE:
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={
                        "error": "Request too large",
                        "detail": f"Request size {size} exceeds limit {SecurityConfig.MAX_REQUEST_SIZE}"
                    }
                )
        except ValueError:
            pass
    
    response = await call_next(request)
    return response


class InputValidator:
    """Input validation utilities."""
    
    @staticmethod
    def validate_string(value: Any, min_length: int = 0, max_length: int = SecurityConfig.MAX_INPUT_LENGTH) -> str:
        """Validate string input."""
        if not isinstance(value, str):
            raise ValueError("Input must be a string")
        
        if len(value) < min_length:
            raise ValueError(f"Input too short. Minimum length: {min_length}")
        
        if len(value) > max_length:
            raise ValueError(f"Input too long. Maximum length: {max_length}")
        
        # Basic XSS prevention
        dangerous_chars = ["<script", "</script", "javascript:", "onload=", "onerror="]
        value_lower = value.lower()
        for char in dangerous_chars:
            if char in value_lower:
                raise ValueError("Input contains potentially dangerous content")
        
        return value.strip()
    
    @staticmethod
    def validate_email(email: str) -> str:
        """Validate email format."""
        import re
        
        email = InputValidator.validate_string(email, min_length=5, max_length=255)
        
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            raise ValueError("Invalid email format")
        
        return email.lower()
    
    @staticmethod
    def validate_username(username: str) -> str:
        """Validate username format."""
        import re
        
        username = InputValidator.validate_string(username, min_length=3, max_length=50)
        
        # Allow only alphanumeric characters, underscores, and hyphens
        username_pattern = r'^[a-zA-Z0-9_-]+$'
        if not re.match(username_pattern, username):
            raise ValueError("Username can only contain letters, numbers, underscores, and hyphens")
        
        return username.lower()
    
    @staticmethod
    def validate_password(password: str) -> str:
        """Validate password strength."""
        import re
        
        if len(password) < SecurityConfig.MIN_PASSWORD_LENGTH:
            raise ValueError(f"Password must be at least {SecurityConfig.MIN_PASSWORD_LENGTH} characters long")
        
        if len(password) > 128:
            raise ValueError("Password too long")
        
        # Check for at least one uppercase, lowercase, digit, and special character
        if not re.search(r'[A-Z]', password):
            raise ValueError("Password must contain at least one uppercase letter")
        
        if not re.search(r'[a-z]', password):
            raise ValueError("Password must contain at least one lowercase letter")
        
        if not re.search(r'\d', password):
            raise ValueError("Password must contain at least one digit")
        
        if not re.search(r'[!@#$%^&*()_+\-=\[\]{};:"\\|,.<>\?]', password):
            raise ValueError("Password must contain at least one special character")
        
        return password


class PermissionChecker:
    """Permission checking utilities."""
    
    @staticmethod
    async def check_permission(
        user: User,
        permission: PermissionType,
        resource_owner_id: Optional[int] = None
    ) -> bool:
        """Check if user has permission to perform an action."""
        # Super admin has all permissions
        if user.is_superuser or user.has_role("super_admin"):
            return True
        
        # Check if user has the specific permission
        if user.has_permission(permission.value):
            # For update operations, check if user owns the resource
            if resource_owner_id and permission.value.startswith("update_"):
                return user.id == resource_owner_id or user.has_permission("admin_access")
            return True
        
        return False
    
    @staticmethod
    def require_permission(permission: PermissionType):
        """Decorator to require specific permission."""
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Extract user from kwargs or args
                user = None
                for arg in list(args) + list(kwargs.values()):
                    if isinstance(arg, User):
                        user = arg
                        break
                
                if not user:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Authentication required"
                    )
                
                if not await PermissionChecker.check_permission(user, permission):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Insufficient permissions. Required: {permission.value}"
                    )
                
                return await func(*args, **kwargs)
            return wrapper
        return decorator


def sanitize_html(content: str) -> str:
    """Sanitize HTML content to prevent XSS."""
    import html
    
    # Basic HTML escaping
    content = html.escape(content)
    
    # Remove dangerous tags and attributes
    dangerous_patterns = [
        r'<script[^>]*>.*?</script>',
        r'<iframe[^>]*>.*?</iframe>',
        r'<object[^>]*>.*?</object>',
        r'<embed[^>]*>.*?</embed>',
        r'on\w+="[^"]*"',  # Event handlers
        r"on\w+='[^']*'",  # Event handlers
        r'javascript:',
        r'vbscript:',
        r'data:',
    ]
    
    import re
    for pattern in dangerous_patterns:
        content = re.sub(pattern, '', content, flags=re.IGNORECASE | re.DOTALL)
    
    return content


def generate_csrf_token() -> str:
    """Generate CSRF token."""
    import secrets
    return secrets.token_urlsafe(32)


def validate_csrf_token(token: str, session_token: str) -> bool:
    """Validate CSRF token."""
    import hmac
    return hmac.compare_digest(token, session_token)
