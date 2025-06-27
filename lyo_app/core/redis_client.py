"""
Redis integration for LyoApp.
Provides caching, session storage, and rate limiting capabilities.
"""

import json
import pickle
from typing import Any, Optional, Union
from datetime import timedelta

import redis.asyncio as redis

from lyo_app.core.config import settings
from lyo_app.core.logging import get_logger

logger = get_logger(__name__)


class RedisClient:
    """Redis client wrapper with additional functionality."""
    
    def __init__(self):
        self.redis_url = getattr(settings, 'REDIS_URL', None)
        self.client: Optional[redis.Redis] = None
    
    async def connect(self):
        """Connect to Redis."""
        if self.redis_url:
            try:
                self.client = redis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=False
                )
                # Test connection
                await self.client.ping()
                logger.info("Redis connected successfully")
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                self.client = None
        else:
            logger.warning("Redis URL not configured")
    
    async def disconnect(self):
        """Disconnect from Redis."""
        if self.client:
            await self.client.close()
            self.client = None
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        expire: Optional[Union[int, timedelta]] = None,
        json_encode: bool = True
    ) -> bool:
        """Set a key-value pair in Redis."""
        if not self.client:
            return False
        
        try:
            if json_encode:
                value = json.dumps(value, default=str)
            
            return await self.client.set(key, value, ex=expire)
        except Exception as e:
            logger.error(f"Redis set error for key {key}: {e}")
            return False
    
    async def get(
        self, 
        key: str, 
        json_decode: bool = True
    ) -> Optional[Any]:
        """Get a value from Redis."""
        if not self.client:
            return None
        
        try:
            value = await self.client.get(key)
            if value is None:
                return None
            
            if json_decode:
                return json.loads(value)
            return value
        except Exception as e:
            logger.error(f"Redis get error for key {key}: {e}")
            return None
    
    async def delete(self, key: str) -> bool:
        """Delete a key from Redis."""
        if not self.client:
            return False
        
        try:
            return bool(await self.client.delete(key))
        except Exception as e:
            logger.error(f"Redis delete error for key {key}: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if a key exists in Redis."""
        if not self.client:
            return False
        
        try:
            return bool(await self.client.exists(key))
        except Exception as e:
            logger.error(f"Redis exists error for key {key}: {e}")
            return False
    
    async def incr(self, key: str, amount: int = 1) -> Optional[int]:
        """Increment a key value."""
        if not self.client:
            return None
        
        try:
            return await self.client.incr(key, amount)
        except Exception as e:
            logger.error(f"Redis incr error for key {key}: {e}")
            return None
    
    async def expire(self, key: str, seconds: int) -> bool:
        """Set expiration for a key."""
        if not self.client:
            return False
        
        try:
            return await self.client.expire(key, seconds)
        except Exception as e:
            logger.error(f"Redis expire error for key {key}: {e}")
            return False


class CacheService:
    """High-level caching service."""
    
    def __init__(self, redis_client: RedisClient):
        self.redis = redis_client
        self.default_ttl = 3600  # 1 hour
    
    async def cache_user_data(self, user_id: int, data: dict, ttl: int = None):
        """Cache user data."""
        key = f"user:{user_id}"
        await self.redis.set(key, data, expire=ttl or self.default_ttl)
    
    async def get_user_data(self, user_id: int) -> Optional[dict]:
        """Get cached user data."""
        key = f"user:{user_id}"
        return await self.redis.get(key)
    
    async def invalidate_user_cache(self, user_id: int):
        """Invalidate user cache."""
        key = f"user:{user_id}"
        await self.redis.delete(key)
    
    async def cache_leaderboard(self, leaderboard_type: str, data: list, ttl: int = 300):
        """Cache leaderboard data (5 minutes default)."""
        key = f"leaderboard:{leaderboard_type}"
        await self.redis.set(key, data, expire=ttl)
    
    async def get_leaderboard(self, leaderboard_type: str) -> Optional[list]:
        """Get cached leaderboard."""
        key = f"leaderboard:{leaderboard_type}"
        return await self.redis.get(key)
    
    async def cache_feed(self, user_id: int, feed_data: list, ttl: int = 600):
        """Cache user feed (10 minutes default)."""
        key = f"feed:{user_id}"
        await self.redis.set(key, feed_data, expire=ttl)
    
    async def get_feed(self, user_id: int) -> Optional[list]:
        """Get cached user feed."""
        key = f"feed:{user_id}"
        return await self.redis.get(key)
    
    async def invalidate_feed(self, user_id: int):
        """Invalidate user feed cache."""
        key = f"feed:{user_id}"
        await self.redis.delete(key)


class SessionService:
    """Session management service."""
    
    def __init__(self, redis_client: RedisClient):
        self.redis = redis_client
        self.session_ttl = 86400  # 24 hours
    
    async def create_session(self, session_id: str, user_id: int, data: dict = None):
        """Create a user session."""
        session_data = {
            "user_id": user_id,
            "created_at": str(datetime.utcnow()),
            "data": data or {}
        }
        key = f"session:{session_id}"
        await self.redis.set(key, session_data, expire=self.session_ttl)
    
    async def get_session(self, session_id: str) -> Optional[dict]:
        """Get session data."""
        key = f"session:{session_id}"
        return await self.redis.get(key)
    
    async def update_session(self, session_id: str, data: dict):
        """Update session data."""
        key = f"session:{session_id}"
        session = await self.get_session(session_id)
        if session:
            session["data"].update(data)
            await self.redis.set(key, session, expire=self.session_ttl)
    
    async def delete_session(self, session_id: str):
        """Delete a session."""
        key = f"session:{session_id}"
        await self.redis.delete(key)


class RateLimitService:
    """Rate limiting service."""
    
    def __init__(self, redis_client: RedisClient):
        self.redis = redis_client
    
    async def is_rate_limited(
        self, 
        key: str, 
        limit: int, 
        window: int = 60
    ) -> tuple[bool, int]:
        """Check if a key is rate limited."""
        current = await self.redis.incr(key)
        
        if current == 1:
            # First request, set expiration
            await self.redis.expire(key, window)
        
        is_limited = current > limit
        return is_limited, current
    
    async def reset_rate_limit(self, key: str):
        """Reset rate limit for a key."""
        await self.redis.delete(key)


# Global instances
redis_client = RedisClient()
cache_service = CacheService(redis_client)
session_service = SessionService(redis_client)
rate_limit_service = RateLimitService(redis_client)


async def init_redis():
    """Initialize Redis connection."""
    await redis_client.connect()


async def close_redis():
    """Close Redis connection."""
    await redis_client.disconnect()
