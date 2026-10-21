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
from lyo_app.core.rate_limiter import InMemoryRateLimiter, in_memory_rate_limiter as _shared_rate_limiter

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
        self._rate_limiter = _shared_rate_limiter  # shared singleton — no duplicate state
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        
        # Rate limiting
        if self.enable_rate_limiting:
            client_ip = self._get_client_ip(request)
            if not self._check_rate_limit(client_ip, request.url.path, request.method):
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
    
    def _check_rate_limit(self, client_ip: str, path: str, method: str = "GET") -> bool:
        """Independently throttle auth attempts, ordinary reads and AI traffic.

        The shared in-memory limiter must never use the bare client IP for
        buckets with different limits: twenty harmless Home/API reads would
        otherwise exhaust the 10/minute auth limit and make /auth/me return
        429, causing a working learner to appear signed out.
        """
        normalized_method = method.upper()
        if path.startswith("/api/v1/auth/"):
            credential_mutation = normalized_method in {"POST", "PUT", "PATCH", "DELETE"}
            if credential_mutation:
                bucket, limit = "credential-attempt", 10
            else:
                bucket, limit = "auth-read", 120
        elif path.startswith("/api/v1/ai/"):
            bucket, limit = "ai", 60
        else:
            bucket, limit = "general", 120
        return self._rate_limiter.is_allowed(f"{client_ip}:{bucket}", limit, 60)

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


# InMemoryRateLimiter imported from lyo_app.core.rate_limiter above
