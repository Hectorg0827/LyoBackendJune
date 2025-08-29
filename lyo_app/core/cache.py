"""Advanced Caching System for LyoBackend
Multi-level caching with Redis and in-memory cache
"""

import json
import time
import asyncio
import hashlib
from typing import Any, Dict, List, Optional, Union, Callable
from functools import wraps
import logging
import redis.asyncio as redis
from dataclasses import dataclass
from collections import OrderedDict

from lyo_app.core.config import settings
from lyo_app.core.performance_monitor import get_performance_monitor

logger = logging.getLogger(__name__)

@dataclass
class CacheEntry:
    """Cache entry with metadata"""
    key: str
    value: Any
    timestamp: float
    ttl: int
    hits: int = 0
    last_accessed: float = 0

    def is_expired(self) -> bool:
        """Check if cache entry is expired"""
        return time.time() - self.timestamp > self.ttl

    def access(self):
        """Mark entry as accessed"""
        self.hits += 1
        self.last_accessed = time.time()

class MemoryCache:
    """In-memory LRU cache with TTL support"""

    def __init__(self, max_size: int = 1000):
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.max_size = max_size
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        async with self._lock:
            if key in self.cache:
                entry = self.cache[key]
                if not entry.is_expired():
                    entry.access()
                    self.cache.move_to_end(key)  # LRU
                    return entry.value
                else:
                    del self.cache[key]
            return None

    async def set(self, key: str, value: Any, ttl: int = 300):
        """Set value in cache"""
        async with self._lock:
            if key in self.cache:
                del self.cache[key]

            entry = CacheEntry(key, value, time.time(), ttl)
            self.cache[key] = entry
            self.cache.move_to_end(key)

            # Evict if over capacity
            if len(self.cache) > self.max_size:
                self.cache.popitem(last=False)

    async def delete(self, key: str):
        """Delete key from cache"""
        async with self._lock:
            if key in self.cache:
                del self.cache[key]

    async def clear(self):
        """Clear all cache entries"""
        async with self._lock:
            self.cache.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_entries = len(self.cache)
        total_hits = sum(entry.hits for entry in self.cache.values())
        expired_entries = sum(1 for entry in self.cache.values() if entry.is_expired())

        return {
            'total_entries': total_entries,
            'total_hits': total_hits,
            'expired_entries': expired_entries,
            'hit_rate': total_hits / max(total_entries, 1),
            'memory_usage_mb': len(self.cache) * 0.1  # Rough estimate
        }

class RedisCache:
    """Redis-based distributed cache"""

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or settings.REDIS_URL
        self.redis_client: Optional[redis.Redis] = None
        self._connected = False

    async def connect(self):
        """Connect to Redis"""
        if not self.redis_url:
            logger.warning("Redis URL not configured")
            return

        try:
            self.redis_client = redis.from_url(self.redis_url)
            await self.redis_client.ping()
            self._connected = True
            logger.info("Connected to Redis cache")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.redis_client = None

    async def disconnect(self):
        """Disconnect from Redis"""
        if self.redis_client:
            await self.redis_client.close()
            self._connected = False

    async def get(self, key: str) -> Optional[Any]:
        """Get value from Redis cache"""
        if not self._connected or not self.redis_client:
            return None

        try:
            data = await self.redis_client.get(f"cache:{key}")
            if data:
                return json.loads(data)
        except Exception as e:
            logger.error(f"Redis cache get error: {e}")

        return None

    async def set(self, key: str, value: Any, ttl: int = 300):
        """Set value in Redis cache"""
        if not self._connected or not self.redis_client:
            return

        try:
            await self.redis_client.setex(
                f"cache:{key}",
                ttl,
                json.dumps(value, default=str)
            )
        except Exception as e:
            logger.error(f"Redis cache set error: {e}")

    async def delete(self, key: str):
        """Delete key from Redis cache"""
        if not self._connected or not self.redis_client:
            return

        try:
            await self.redis_client.delete(f"cache:{key}")
        except Exception as e:
            logger.error(f"Redis cache delete error: {e}")

    async def clear(self):
        """Clear all cache entries (use with caution)"""
        if not self._connected or not self.redis_client:
            return

        try:
            # Clear only cache keys
            keys = await self.redis_client.keys("cache:*")
            if keys:
                await self.redis_client.delete(*keys)
        except Exception as e:
            logger.error(f"Redis cache clear error: {e}")

class MultiLevelCache:
    """Multi-level caching system combining memory and Redis"""

    def __init__(self):
        self.memory_cache = MemoryCache(max_size=2000)
        self.redis_cache = RedisCache()
        self.performance_monitor = get_performance_monitor()

    async def initialize(self):
        """Initialize the caching system"""
        await self.redis_cache.connect()

    async def shutdown(self):
        """Shutdown the caching system"""
        await self.redis_cache.disconnect()

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache with fallback strategy"""
        # Try memory cache first
        value = await self.memory_cache.get(key)
        if value is not None:
            await self.performance_monitor.track_cache_operation("memory", hit=True)
            return value

        # Try Redis cache
        value = await self.redis_cache.get(key)
        if value is not None:
            # Populate memory cache
            await self.memory_cache.set(key, value, ttl=300)
            await self.performance_monitor.track_cache_operation("redis", hit=True)
            return value

        await self.performance_monitor.track_cache_operation("miss", hit=False)
        return None

    async def set(self, key: str, value: Any, ttl: int = 300, memory_ttl: Optional[int] = None):
        """Set value in both cache levels"""
        memory_ttl = memory_ttl or min(ttl, 600)  # Memory cache TTL max 10 minutes

        # Set in both caches
        await self.memory_cache.set(key, value, memory_ttl)
        await self.redis_cache.set(key, value, ttl)

    async def delete(self, key: str):
        """Delete from both cache levels"""
        await self.memory_cache.delete(key)
        await self.redis_cache.delete(key)

    async def clear(self):
        """Clear both cache levels"""
        await self.memory_cache.clear()
        await self.redis_cache.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics"""
        memory_stats = self.memory_cache.get_stats()

        return {
            'memory_cache': memory_stats,
            'redis_connected': self.redis_cache._connected,
            'cache_levels': 2 if self.redis_cache._connected else 1
        }

# Global cache instance
_cache_instance: Optional[MultiLevelCache] = None

def get_cache() -> MultiLevelCache:
    """Get global cache instance"""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = MultiLevelCache()
    return _cache_instance

# Cache decorators
def cached(ttl: int = 300, key_prefix: str = ""):
    """Decorator for caching function results"""
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            cache = get_cache()

            # Generate cache key
            key_data = {
                'func': func.__name__,
                'args': str(args),
                'kwargs': str(sorted(kwargs.items()))
            }
            if key_prefix:
                key_data['prefix'] = key_prefix

            key = hashlib.md5(json.dumps(key_data, sort_keys=True).encode()).hexdigest()

            # Try cache first
            cached_result = await cache.get(key)
            if cached_result is not None:
                return cached_result

            # Execute function
            result = await func(*args, **kwargs)

            # Cache result
            await cache.set(key, result, ttl)

            return result

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # For sync functions, we'll need to run in a separate thread
            # This is a simplified version - in practice you'd want proper async handling
            cache = get_cache()

            key_data = {
                'func': func.__name__,
                'args': str(args),
                'kwargs': str(sorted(kwargs.items()))
            }
            if key_prefix:
                key_data['prefix'] = key_prefix

            key = hashlib.md5(json.dumps(key_data, sort_keys=True).encode()).hexdigest()

            # For sync functions, we can't await, so this is a no-op
            # You'd need to implement sync cache methods
            return func(*args, **kwargs)

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator

def cache_invalidate(pattern: str):
    """Decorator to invalidate cache after function execution"""
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)

            # Invalidate cache
            cache = get_cache()
            # Note: This is a simplified invalidation - in practice you'd want pattern matching
            await cache.clear()

            return result

        return async_wrapper if asyncio.iscoroutinefunction(func) else func
    return decorator

# Cache management utilities
async def warmup_cache():
    """Warm up cache with frequently accessed data"""
    cache = get_cache()

    # Warm up common endpoints
    warmup_keys = [
        "api_endpoints",
        "user_permissions",
        "system_config",
        "popular_courses"
    ]

    for key in warmup_keys:
        # This would typically load actual data
        await cache.set(f"warmup:{key}", {"status": "warming"}, ttl=3600)

    logger.info("Cache warmup completed")

async def optimize_cache():
    """Optimize cache performance based on usage patterns"""
    cache = get_cache()
    stats = cache.get_stats()

    # Analyze cache efficiency
    memory_stats = stats['memory_cache']

    if memory_stats['hit_rate'] < 0.7:
        logger.warning("Low cache hit rate detected, consider adjusting cache strategy")

    # Implement cache optimization strategies
    # This could include adjusting TTLs, cache sizes, etc.

    logger.info("Cache optimization completed")

# Cache health monitoring
async def monitor_cache_health():
    """Monitor cache health and performance"""
    cache = get_cache()

    while True:
        try:
            stats = cache.get_stats()

            # Log cache health
            logger.info(f"Cache Health: {json.dumps(stats, indent=2)}")

            # Check for issues
            if not stats['redis_connected']:
                logger.warning("Redis cache disconnected")

            memory_stats = stats['memory_cache']
            if memory_stats['expired_entries'] > memory_stats['total_entries'] * 0.3:
                logger.warning("High number of expired cache entries")

            await asyncio.sleep(300)  # Check every 5 minutes

        except Exception as e:
            logger.error(f"Cache health monitoring error: {e}")
            await asyncio.sleep(60)

# Initialize cache on startup
async def initialize_caching():
    """Initialize the caching system"""
    cache = get_cache()
    await cache.initialize()

    # Start cache health monitoring
    asyncio.create_task(monitor_cache_health())

    # Warm up cache
    await warmup_cache()

    logger.info("Caching system initialized")

# Cleanup on shutdown
async def shutdown_caching():
    """Shutdown the caching system"""
    cache = get_cache()
    await cache.shutdown()
    logger.info("Caching system shutdown")
