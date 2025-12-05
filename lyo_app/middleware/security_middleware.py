"""
Security Middleware for LYO Backend

Provides security-related middleware functionality including:
- Rate limiting
- Security headers
- Audit logging
"""

import logging
import time
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


class SecurityMiddleware(BaseHTTPMiddleware):
    """
    Security middleware providing rate limiting, security headers, and audit logging.
    """
    
    def __init__(
        self,
        app,
        enable_rate_limiting: bool = True,
        enable_audit_logging: bool = True,
        enable_security_headers: bool = True,
    ):
        super().__init__(app)
        self.enable_rate_limiting = enable_rate_limiting
        self.enable_audit_logging = enable_audit_logging
        self.enable_security_headers = enable_security_headers
        self._rate_limiter = InMemoryRateLimiter()
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        
        # Rate limiting
        if self.enable_rate_limiting:
            client_ip = self._get_client_ip(request)
            if not self._check_rate_limit(client_ip, request.url.path):
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded"},
                    headers={"Retry-After": "60"}
                )
        
        # Process request
        response = await call_next(request)
        
        # Add security headers
        if self.enable_security_headers:
            self._add_security_headers(response)
        
        # Audit logging
        if self.enable_audit_logging:
            duration = time.time() - start_time
            self._log_request(request, response, duration)
        
        return response
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request."""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        return request.client.host if request.client else "unknown"
    
    def _check_rate_limit(self, client_ip: str, path: str) -> bool:
        """Check if request is within rate limits."""
        # Define limits for different paths
        if path.startswith("/api/v1/auth/"):
            limit, window = 10, 60  # 10 requests per minute for auth
        elif path.startswith("/api/v1/ai/"):
            limit, window = 60, 60  # 60 requests per minute for AI
        else:
            limit, window = 120, 60  # 120 requests per minute for general
        
        return self._rate_limiter.is_allowed(client_ip, limit, window)
    
    def _add_security_headers(self, response: Response) -> None:
        """Add security headers to response."""
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    
    def _log_request(self, request: Request, response: Response, duration: float) -> None:
        """Log request details."""
        logger.debug(
            f"{request.method} {request.url.path} - "
            f"Status: {response.status_code} - "
            f"Duration: {duration:.3f}s"
        )


class InMemoryRateLimiter:
    """Simple in-memory rate limiter."""
    
    def __init__(self):
        self._requests: dict = {}
    
    def is_allowed(self, client_id: str, limit: int, window: int) -> bool:
        """Check if request is allowed within rate limit."""
        now = time.time()
        key = f"{client_id}:{window}"
        
        # Clean up old entries
        self._cleanup(now, window)
        
        # Get current count for this client
        if key not in self._requests:
            self._requests[key] = []
        
        # Filter to requests in current window
        self._requests[key] = [
            req_time for req_time in self._requests[key]
            if now - req_time < window
        ]
        
        # Check limit
        if len(self._requests[key]) >= limit:
            return False
        
        # Record this request
        self._requests[key].append(now)
        return True
    
    def _cleanup(self, now: float, max_window: int = 3600) -> None:
        """Remove old entries to prevent memory growth."""
        keys_to_remove = []
        for key, requests in self._requests.items():
            if not requests or now - max(requests) > max_window:
                keys_to_remove.append(key)
        for key in keys_to_remove:
            del self._requests[key]
