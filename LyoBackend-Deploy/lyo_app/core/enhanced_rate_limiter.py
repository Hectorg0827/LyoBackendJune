"""
Enhanced rate limiting with Redis backend and sliding window algorithm.
Provides scalable rate limiting across multiple application instances.
"""

import asyncio
import time
import logging
from typing import Optional, Dict, Any
from collections import defaultdict

from fastapi import Request, HTTPException, status
import redis.asyncio as redis

from lyo_app.core.config import settings

logger = logging.getLogger(__name__)


class TokenBucketRateLimiter:
    """Token bucket rate limiter for in-memory rate limiting."""
    
    def __init__(self, rate: int, per: int):
        self.rate = rate  # tokens per period
        self.per = per    # period in seconds
        self.buckets = defaultdict(lambda: {"tokens": rate, "last_refill": time.time()})
    
    async def is_allowed(self, key: str) -> bool:
        """Check if request is allowed and consume a token."""
        bucket = self.buckets[key]
        current_time = time.time()
        
        # Refill tokens based on time passed
        time_passed = current_time - bucket["last_refill"]
        tokens_to_add = time_passed * self.rate / self.per
        bucket["tokens"] = min(self.rate, bucket["tokens"] + tokens_to_add)
        bucket["last_refill"] = current_time
        
        # Check if request can be allowed
        if bucket["tokens"] >= 1:
            bucket["tokens"] -= 1
            return True
        
        return False


class RedisRateLimiter:
    """Redis-backed sliding window rate limiter."""
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis_client = redis_client
        self.fallback_limiter = TokenBucketRateLimiter(60, 60)  # fallback to memory
    
    async def is_allowed(
        self,
        key: str,
        limit: int,
        window: int,
        cost: int = 1
    ) -> tuple[bool, Dict[str, Any]]:
        """
        Check if request is allowed using sliding window algorithm.
        
        Args:
            key: Unique identifier for the rate limit bucket
            limit: Maximum number of requests allowed
            window: Time window in seconds
            cost: Cost of this request (default 1)
        
        Returns:
            Tuple of (is_allowed, info_dict)
        """
        if not self.redis_client:
            # Fallback to in-memory limiter
            allowed = await self.fallback_limiter.is_allowed(key)
            return allowed, {"remaining": 0, "reset_time": 0, "total": limit}
        
        try:
            current_time = time.time()
            pipeline = self.redis_client.pipeline()
            
            # Remove expired entries
            pipeline.zremrangebyscore(key, 0, current_time - window)
            
            # Count current requests
            pipeline.zcard(key)
            
            # Add current request
            pipeline.zadd(key, {str(current_time): current_time})
            
            # Set expiration
            pipeline.expire(key, window)
            
            results = await pipeline.execute()
            current_requests = results[1]
            
            if current_requests + cost <= limit:
                remaining = limit - current_requests - cost
                reset_time = current_time + window
                return True, {
                    "remaining": remaining,
                    "reset_time": reset_time,
                    "total": limit,
                    "current": current_requests + cost
                }
            else:
                # Remove the request we just added since it's not allowed
                await self.redis_client.zrem(key, str(current_time))
                remaining = 0
                reset_time = current_time + window
                return False, {
                    "remaining": remaining,
                    "reset_time": reset_time,
                    "total": limit,
                    "current": current_requests
                }
                
        except Exception as e:
            logger.error(f"Redis rate limiter error: {e}")
            # Fallback to in-memory limiter
            allowed = await self.fallback_limiter.is_allowed(key)
            return allowed, {"remaining": 0, "reset_time": 0, "total": limit}


class RateLimitMiddleware:
    """FastAPI middleware for rate limiting."""
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.limiter = RedisRateLimiter(redis_client)
    
    def get_client_ip(self, request: Request) -> str:
        """Get client IP address with proxy support."""
        # Check for forwarded headers first
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fallback to direct client IP
        return request.client.host if request.client else "unknown"
    
    def get_rate_limit_key(self, request: Request) -> str:
        """Generate rate limit key for the request."""
        client_ip = self.get_client_ip(request)
        
        # Different limits for different endpoints
        if request.url.path.startswith("/api/v1/auth"):
            return f"auth:{client_ip}"
        elif request.url.path.startswith("/api/v1/ai"):
            return f"ai:{client_ip}"
        else:
            return f"general:{client_ip}"
    
    def get_rate_limit_config(self, request: Request) -> tuple[int, int]:
        """Get rate limit configuration for the request."""
        if request.url.path.startswith("/api/v1/auth"):
            return 10, 60  # 10 requests per minute for auth endpoints
        elif request.url.path.startswith("/api/v1/ai"):
            return 20, 60  # 20 requests per minute for AI endpoints
        else:
            return settings.rate_limit_per_minute, 60  # Default limit


# Global rate limiter instance
rate_limiter = None


async def init_rate_limiter(redis_client: Optional[redis.Redis] = None):
    """Initialize the global rate limiter."""
    global rate_limiter
    rate_limiter = RateLimitMiddleware(redis_client)


async def rate_limit_middleware(request: Request, call_next):
    """Rate limiting middleware function."""
    if not rate_limiter:
        # Initialize with no Redis if not set up
        await init_rate_limiter()
    
    # Skip rate limiting for health checks
    if request.url.path in ["/health", "/", "/docs", "/openapi.json"]:
        return await call_next(request)
    
    # Get rate limit configuration
    key = rate_limiter.get_rate_limit_key(request)
    limit, window = rate_limiter.get_rate_limit_config(request)
    
    # Check rate limit
    allowed, info = await rate_limiter.limiter.is_allowed(key, limit, window)
    
    if not allowed:
        logger.warning(
            f"Rate limit exceeded for {rate_limiter.get_client_ip(request)} "
            f"on {request.method} {request.url.path}"
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": str(info["remaining"]),
                "X-RateLimit-Reset": str(int(info["reset_time"])),
                "Retry-After": str(window)
            }
        )
    
    # Process request
    response = await call_next(request)
    
    # Add rate limit headers to response
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
    response.headers["X-RateLimit-Reset"] = str(int(info["reset_time"]))
    
    return response
