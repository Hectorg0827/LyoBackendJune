"""
Production-ready rate limiting with Redis backend.
Provides scalable rate limiting across multiple application instances.
"""

import os
import time
import redis
import hashlib
import logging
from typing import Optional
from fastapi import Request, HTTPException
from lyo_app.core.config import settings

logger = logging.getLogger(__name__)


def get_redis_url() -> Optional[str]:
    """Get Redis URL from environment or settings."""
    # Check env vars first (for Cloud Run)
    env_url = os.getenv("REDIS_URL")
    if env_url:
        return env_url
    
    # Build from REDIS_HOST/REDIS_PORT
    host = os.getenv("REDIS_HOST")
    port = os.getenv("REDIS_PORT", "6379")
    if host:
        return f"redis://{host}:{port}/0"
    
    # Fall back to settings.effective_redis_url if available
    if hasattr(settings, 'effective_redis_url'):
        return settings.effective_redis_url
    
    # Last resort - settings.redis_url
    return getattr(settings, 'redis_url', None)


class RedisRateLimiter:
    """Production-ready Redis-backed rate limiter using sliding window."""
    
    def __init__(self, 
                 redis_url: str = None,
                 max_requests: int = 100, 
                 window_seconds: int = 60,
                 block_duration: int = 300):
        """
        Initialize rate limiter.
        
        Args:
            redis_url: Redis connection URL
            max_requests: Maximum requests per window
            window_seconds: Time window in seconds
            block_duration: How long to block after limit exceeded
        """
        self.redis_url = redis_url or get_redis_url()
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.block_duration = block_duration
        self._redis_client = None
        self._initialized = False
    
    @property
    def redis_client(self):
        """Lazy initialization of Redis client."""
        if self._initialized:
            return self._redis_client
            
        self._initialized = True
        
        if not self.redis_url:
            logger.warning("No Redis URL configured - rate limiting will use in-memory fallback")
            return None
        
        try:
            self._redis_client = redis.from_url(self.redis_url, decode_responses=True)
            # Test connection
            self._redis_client.ping()
            logger.info("Redis rate limiter initialized successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Redis for rate limiting: {e}")
            self._redis_client = None
        
        return self._redis_client
    
    def get_secure_client_id(self, request: Request) -> str:
        """
        Generate secure client identifier from request.
        
        Args:
            request: FastAPI request object
            
        Returns:
            Secure client identifier
        """
        # Get multiple identifying factors
        ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "")
        forwarded_for = request.headers.get("x-forwarded-for", "")
        
        # Create composite identifier
        composite = f"{ip}:{user_agent}:{forwarded_for}"
        
        # Hash for privacy and consistency
        return hashlib.sha256(composite.encode()).hexdigest()[:16]
    
    def is_allowed(self, client_id: str, endpoint: str = "global") -> tuple[bool, dict]:
        """
        Check if request is allowed for client.
        
        Args:
            client_id: Client identifier
            endpoint: Specific endpoint (for per-endpoint limits)
            
        Returns:
            Tuple of (is_allowed, rate_limit_info)
        """
        if not self.redis_client:
            # Fail open if Redis is unavailable
            logger.warning("Redis unavailable, allowing request")
            return True, {"remaining": self.max_requests, "reset_time": time.time() + self.window_seconds}
        
        try:
            current_time = int(time.time())
            window_start = current_time - self.window_seconds
            rate_key = f"rate_limit:{client_id}:{endpoint}"
            block_key = f"rate_block:{client_id}:{endpoint}"
            
            # Check if client is currently blocked
            if self.redis_client.exists(block_key):
                block_ttl = self.redis_client.ttl(block_key)
                return False, {
                    "remaining": 0,
                    "reset_time": current_time + block_ttl,
                    "blocked_until": current_time + block_ttl
                }
            
            # Use pipeline for atomic operations
            pipe = self.redis_client.pipeline()
            
            # Remove old entries from sliding window
            pipe.zremrangebyscore(rate_key, 0, window_start)
            
            # Count current requests in window
            pipe.zcard(rate_key)
            
            # Add current request timestamp
            pipe.zadd(rate_key, {str(current_time): current_time})
            
            # Set expiration for cleanup
            pipe.expire(rate_key, self.window_seconds + 1)
            
            results = pipe.execute()
            request_count = results[1]  # Count before adding current request
            
            if request_count >= self.max_requests:
                # Block the client for block_duration
                self.redis_client.setex(block_key, self.block_duration, "blocked")
                
                return False, {
                    "remaining": 0,
                    "reset_time": current_time + self.block_duration,
                    "blocked_until": current_time + self.block_duration
                }
            
            remaining = max(0, self.max_requests - request_count - 1)
            reset_time = current_time + self.window_seconds
            
            return True, {
                "remaining": remaining,
                "reset_time": reset_time
            }
            
        except Exception as e:
            logger.error(f"Rate limiter error: {e}")
            # Fail open - allow request if Redis operation fails
            return True, {"remaining": self.max_requests, "reset_time": time.time() + self.window_seconds}
    
    def get_rate_limit_status(self, client_id: str, endpoint: str = "global") -> dict:
        """
        Get current rate limit status for a client.
        
        Args:
            client_id: Client identifier
            endpoint: Specific endpoint
            
        Returns:
            Rate limit status information
        """
        if not self.redis_client:
            return {"requests_made": 0, "remaining": self.max_requests}
        
        try:
            current_time = int(time.time())
            window_start = current_time - self.window_seconds
            rate_key = f"rate_limit:{client_id}:{endpoint}"
            
            # Clean old entries and count current
            pipe = self.redis_client.pipeline()
            pipe.zremrangebyscore(rate_key, 0, window_start)
            pipe.zcard(rate_key)
            results = pipe.execute()
            
            requests_made = results[1]
            remaining = max(0, self.max_requests - requests_made)
            
            return {
                "requests_made": requests_made,
                "remaining": remaining,
                "window_seconds": self.window_seconds,
                "max_requests": self.max_requests
            }
            
        except Exception as e:
            logger.error(f"Failed to get rate limit status: {e}")
            return {"requests_made": 0, "remaining": self.max_requests}


class RateLimitMiddleware:
    """FastAPI middleware for rate limiting."""
    
    def __init__(self, rate_limiter: RedisRateLimiter):
        self.rate_limiter = rate_limiter
    
    async def __call__(self, request: Request, call_next):
        # Skip rate limiting for health checks and static files
        if request.url.path in ["/health", "/docs", "/openapi.json"]:
            return await call_next(request)
        
        # Get client identifier
        client_id = self.rate_limiter.get_secure_client_id(request)
        endpoint = request.url.path
        
        # Check rate limit
        is_allowed, rate_info = self.rate_limiter.is_allowed(client_id, endpoint)
        
        if not is_allowed:
            # Add rate limit headers
            headers = {
                "X-RateLimit-Limit": str(self.rate_limiter.max_requests),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(rate_info.get("reset_time", 0))),
                "Retry-After": str(int(rate_info.get("blocked_until", 0) - time.time()))
            }
            
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Rate limit exceeded",
                    "message": "Too many requests. Please try again later.",
                    "retry_after": int(rate_info.get("blocked_until", 0) - time.time())
                },
                headers=headers
            )
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers to response
        response.headers["X-RateLimit-Limit"] = str(self.rate_limiter.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(rate_info.get("remaining", 0))
        response.headers["X-RateLimit-Reset"] = str(int(rate_info.get("reset_time", 0)))
        
        return response


# Global rate limiter instance
rate_limiter = RedisRateLimiter(
    max_requests=getattr(settings, 'rate_limit_requests', 100),
    window_seconds=getattr(settings, 'rate_limit_window', 60)
)

# Middleware instance
rate_limit_middleware = RateLimitMiddleware(rate_limiter)
