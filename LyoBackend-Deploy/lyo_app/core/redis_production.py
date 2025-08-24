"""
Production Redis client with pub/sub support for real-time updates.
Used for WebSocket progress tracking and caching.
"""

import asyncio
import json
import logging
from typing import Optional, Dict, Any, Callable
import aioredis
from aioredis import Redis

from lyo_app.core.config import settings

logger = logging.getLogger(__name__)

# Redis configuration
REDIS_URL = getattr(settings, "REDIS_URL", "redis://localhost:6379/0")
REDIS_MAX_CONNECTIONS = getattr(settings, "REDIS_MAX_CONNECTIONS", 10)

# Global Redis clients
redis_client: Optional[Redis] = None
redis_pubsub: Optional[Redis] = None


async def init_redis() -> None:
    """Initialize Redis connections."""
    global redis_client, redis_pubsub
    
    try:
        # Main Redis client for caching
        redis_client = aioredis.from_url(
            REDIS_URL,
            encoding="utf8",
            decode_responses=True,
            max_connections=REDIS_MAX_CONNECTIONS
        )
        
        # Separate client for pub/sub
        redis_pubsub = aioredis.from_url(
            REDIS_URL,
            encoding="utf8", 
            decode_responses=True,
            max_connections=5
        )
        
        # Test connections
        await redis_client.ping()
        await redis_pubsub.ping()
        
        logger.info("Redis connections initialized successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize Redis: {e}")
        raise


async def close_redis() -> None:
    """Close Redis connections."""
    global redis_client, redis_pubsub
    
    if redis_client:
        await redis_client.close()
        redis_client = None
    
    if redis_pubsub:
        await redis_pubsub.close()
        redis_pubsub = None
    
    logger.info("Redis connections closed")


def get_redis() -> Redis:
    """Get Redis client instance."""
    if not redis_client:
        raise RuntimeError("Redis not initialized")
    return redis_client


def get_redis_pubsub() -> Redis:
    """Get Redis pub/sub client instance."""
    if not redis_pubsub:
        raise RuntimeError("Redis pub/sub not initialized")
    return redis_pubsub


class RedisService:
    """Redis service with caching and pub/sub operations."""
    
    def __init__(self):
        self.client = get_redis()
        self.pubsub_client = get_redis_pubsub()
    
    # Caching operations
    async def get(self, key: str) -> Optional[str]:
        """Get value from Redis."""
        try:
            return await self.client.get(key)
        except Exception as e:
            logger.error(f"Redis GET error for key {key}: {e}")
            return None
    
    async def set(self, key: str, value: str, expire: Optional[int] = None) -> bool:
        """Set value in Redis with optional expiration."""
        try:
            return await self.client.set(key, value, ex=expire)
        except Exception as e:
            logger.error(f"Redis SET error for key {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete key from Redis."""
        try:
            return bool(await self.client.delete(key))
        except Exception as e:
            logger.error(f"Redis DELETE error for key {key}: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in Redis."""
        try:
            return bool(await self.client.exists(key))
        except Exception as e:
            logger.error(f"Redis EXISTS error for key {key}: {e}")
            return False
    
    # JSON operations
    async def get_json(self, key: str) -> Optional[Dict[str, Any]]:
        """Get JSON value from Redis."""
        value = await self.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error for key {key}: {e}")
        return None
    
    async def set_json(self, key: str, value: Dict[str, Any], expire: Optional[int] = None) -> bool:
        """Set JSON value in Redis."""
        try:
            json_str = json.dumps(value)
            return await self.set(key, json_str, expire)
        except (TypeError, ValueError) as e:
            logger.error(f"JSON encode error for key {key}: {e}")
            return False
    
    # List operations
    async def lpush(self, key: str, *values: str) -> int:
        """Push values to the left of a list."""
        try:
            return await self.client.lpush(key, *values)
        except Exception as e:
            logger.error(f"Redis LPUSH error for key {key}: {e}")
            return 0
    
    async def rpop(self, key: str) -> Optional[str]:
        """Pop value from the right of a list."""
        try:
            return await self.client.rpop(key)
        except Exception as e:
            logger.error(f"Redis RPOP error for key {key}: {e}")
            return None
    
    async def lrange(self, key: str, start: int = 0, end: int = -1) -> list:
        """Get range of values from a list."""
        try:
            return await self.client.lrange(key, start, end)
        except Exception as e:
            logger.error(f"Redis LRANGE error for key {key}: {e}")
            return []
    
    # Set operations
    async def sadd(self, key: str, *values: str) -> int:
        """Add values to a set."""
        try:
            return await self.client.sadd(key, *values)
        except Exception as e:
            logger.error(f"Redis SADD error for key {key}: {e}")
            return 0
    
    async def srem(self, key: str, *values: str) -> int:
        """Remove values from a set."""
        try:
            return await self.client.srem(key, *values)
        except Exception as e:
            logger.error(f"Redis SREM error for key {key}: {e}")
            return 0
    
    async def smembers(self, key: str) -> set:
        """Get all members of a set."""
        try:
            return await self.client.smembers(key)
        except Exception as e:
            logger.error(f"Redis SMEMBERS error for key {key}: {e}")
            return set()
    
    # Hash operations
    async def hget(self, key: str, field: str) -> Optional[str]:
        """Get field value from hash."""
        try:
            return await self.client.hget(key, field)
        except Exception as e:
            logger.error(f"Redis HGET error for key {key}, field {field}: {e}")
            return None
    
    async def hset(self, key: str, field: str, value: str) -> bool:
        """Set field value in hash."""
        try:
            return bool(await self.client.hset(key, field, value))
        except Exception as e:
            logger.error(f"Redis HSET error for key {key}, field {field}: {e}")
            return False
    
    async def hgetall(self, key: str) -> Dict[str, str]:
        """Get all fields and values from hash."""
        try:
            return await self.client.hgetall(key)
        except Exception as e:
            logger.error(f"Redis HGETALL error for key {key}: {e}")
            return {}


class RedisPubSub:
    """Redis pub/sub service for real-time messaging."""
    
    def __init__(self):
        self.client = get_redis_pubsub()
    
    async def publish(self, channel: str, message: Dict[str, Any]) -> bool:
        """Publish message to channel."""
        try:
            json_message = json.dumps(message)
            result = await self.client.publish(channel, json_message)
            logger.debug(f"Published to {channel}: {message} (subscribers: {result})")
            return result > 0
        except Exception as e:
            logger.error(f"Redis PUBLISH error for channel {channel}: {e}")
            return False
    
    async def subscribe(self, channel: str, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Subscribe to channel with callback."""
        pubsub = self.client.pubsub()
        
        try:
            await pubsub.subscribe(channel)
            logger.info(f"Subscribed to channel: {channel}")
            
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        await callback(data)
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON decode error for channel {channel}: {e}")
                    except Exception as e:
                        logger.error(f"Callback error for channel {channel}: {e}")
        
        except Exception as e:
            logger.error(f"Redis SUBSCRIBE error for channel {channel}: {e}")
        
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
    
    async def pattern_subscribe(self, pattern: str, callback: Callable[[str, Dict[str, Any]], None]) -> None:
        """Subscribe to channel pattern with callback."""
        pubsub = self.client.pubsub()
        
        try:
            await pubsub.psubscribe(pattern)
            logger.info(f"Subscribed to pattern: {pattern}")
            
            async for message in pubsub.listen():
                if message["type"] == "pmessage":
                    channel = message["channel"]
                    try:
                        data = json.loads(message["data"])
                        await callback(channel, data)
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON decode error for pattern {pattern}, channel {channel}: {e}")
                    except Exception as e:
                        logger.error(f"Callback error for pattern {pattern}, channel {channel}: {e}")
        
        except Exception as e:
            logger.error(f"Redis PSUBSCRIBE error for pattern {pattern}: {e}")
        
        finally:
            await pubsub.punsubscribe(pattern)
            await pubsub.close()


# Global services
redis_service = RedisService()
redis_pubsub = RedisPubSub()


# Convenience functions for task progress tracking
async def publish_task_progress(task_id: str, progress: Dict[str, Any]) -> bool:
    """Publish task progress update."""
    channel = f"task:{task_id}"
    return await redis_pubsub.publish(channel, progress)


async def subscribe_task_progress(task_id: str, callback: Callable[[Dict[str, Any]], None]) -> None:
    """Subscribe to task progress updates."""
    channel = f"task:{task_id}"
    await redis_pubsub.subscribe(channel, callback)


# Cache decorators and utilities
def cache_key(*parts: str) -> str:
    """Generate cache key from parts."""
    return ":".join(str(part) for part in parts)


async def cached_get_or_set(
    key: str,
    fetch_func: Callable[[], Any],
    expire: int = 3600
) -> Any:
    """Get from cache or set if not exists."""
    # Try to get from cache
    cached = await redis_service.get_json(key)
    if cached is not None:
        return cached
    
    # Fetch and cache
    value = await fetch_func()
    if value is not None:
        await redis_service.set_json(key, value, expire)
    
    return value
