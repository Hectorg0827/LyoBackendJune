"""
Performance Caching System for A2UI and AI Classroom
Implements Redis-based caching with lazy loading and performance optimizations
"""
import redis
import json
import asyncio
import time
from typing import Optional, Dict, Any, List, Union
from functools import wraps
from datetime import datetime, timedelta
import hashlib
import pickle
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

class CacheConfig(BaseModel):
    """Cache configuration settings"""
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    default_ttl: int = 3600  # 1 hour
    course_data_ttl: int = 7200  # 2 hours
    ui_layout_ttl: int = 1800  # 30 minutes
    user_progress_ttl: int = 300  # 5 minutes
    max_retries: int = 3
    retry_delay: float = 0.1

class PerformanceCache:
    """High-performance caching system with Redis backend"""

    def __init__(self, config: CacheConfig = None):
        self.config = config or CacheConfig()
        self.redis_client = None
        self.connection_pool = None
        self._connect()

    def _connect(self):
        """Initialize Redis connection with connection pooling"""
        try:
            self.connection_pool = redis.ConnectionPool(
                host=self.config.redis_host,
                port=self.config.redis_port,
                db=self.config.redis_db,
                max_connections=20,
                retry_on_timeout=True
            )
            self.redis_client = redis.Redis(connection_pool=self.connection_pool)
            # Test connection
            self.redis_client.ping()
            logger.info("Redis cache connection established")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}. Using memory fallback")
            self.redis_client = None
            self._memory_cache = {}

    def _generate_key(self, prefix: str, identifier: str, **kwargs) -> str:
        """Generate cache key with optional parameters"""
        key_data = f"{prefix}:{identifier}"
        if kwargs:
            params = ":".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
            key_data += f":{params}"
        return hashlib.md5(key_data.encode()).hexdigest()[:16]

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache with fallback to memory"""
        try:
            if self.redis_client:
                data = self.redis_client.get(key)
                if data:
                    return pickle.loads(data)
            else:
                return self._memory_cache.get(key)
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
        return None

    async def set(self, key: str, value: Any, ttl: int = None) -> bool:
        """Set value in cache with TTL"""
        try:
            ttl = ttl or self.config.default_ttl
            serialized_value = pickle.dumps(value)

            if self.redis_client:
                return self.redis_client.setex(key, ttl, serialized_value)
            else:
                self._memory_cache[key] = value
                # Simple TTL for memory cache (not perfect but functional)
                asyncio.create_task(self._expire_memory_key(key, ttl))
                return True
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
            return False

    async def _expire_memory_key(self, key: str, ttl: int):
        """Expire memory cache key after TTL"""
        await asyncio.sleep(ttl)
        self._memory_cache.pop(key, None)

    async def delete(self, key: str) -> bool:
        """Delete key from cache"""
        try:
            if self.redis_client:
                return bool(self.redis_client.delete(key))
            else:
                return self._memory_cache.pop(key, None) is not None
        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {e}")
            return False

    async def clear_pattern(self, pattern: str) -> int:
        """Clear all keys matching pattern"""
        try:
            if self.redis_client:
                keys = self.redis_client.keys(pattern)
                if keys:
                    return self.redis_client.delete(*keys)
            else:
                # Memory cache pattern clearing
                keys_to_delete = [k for k in self._memory_cache.keys() if pattern in k]
                for key in keys_to_delete:
                    del self._memory_cache[key]
                return len(keys_to_delete)
        except Exception as e:
            logger.error(f"Cache clear pattern error for {pattern}: {e}")
        return 0

# Global cache instance
cache_instance = PerformanceCache()

class CacheKeys:
    """Centralized cache key definitions"""
    COURSE_DATA = "course_data"
    UI_LAYOUT = "ui_layout"
    USER_PROGRESS = "user_progress"
    INTENT_DETECTION = "intent_detection"
    TOPIC_EXTRACTION = "topic_extraction"
    COURSE_GENERATION = "course_generation"
    A2UI_COMPONENT = "a2ui_component"

def cache_result(key_prefix: str, ttl: int = None, use_args: bool = True):
    """Decorator for caching function results"""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Generate cache key
            if use_args:
                key_data = f"{func.__name__}:{str(args)}:{str(sorted(kwargs.items()))}"
            else:
                key_data = func.__name__

            cache_key = cache_instance._generate_key(key_prefix, key_data)

            # Try to get from cache
            cached_result = await cache_instance.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit for {cache_key}")
                return cached_result

            # Execute function and cache result
            logger.debug(f"Cache miss for {cache_key}")
            result = await func(*args, **kwargs)

            if result is not None:
                await cache_instance.set(cache_key, result, ttl)

            return result

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # For sync functions, convert to async
            return asyncio.create_task(async_wrapper(*args, **kwargs))

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator

class LazyLoader:
    """Lazy loading system for complex UI components"""

    def __init__(self, cache: PerformanceCache = None):
        self.cache = cache or cache_instance
        self._pending_loads = {}
        self._load_semaphore = asyncio.Semaphore(5)  # Max 5 concurrent loads

    async def load_component_lazy(self, component_type: str, component_id: str,
                                 loader_func, **kwargs) -> Dict[str, Any]:
        """Load component with lazy loading and caching"""
        cache_key = self.cache._generate_key("lazy_component", f"{component_type}:{component_id}")

        # Check cache first
        cached_component = await self.cache.get(cache_key)
        if cached_component:
            return cached_component

        # Check if already loading
        if cache_key in self._pending_loads:
            return await self._pending_loads[cache_key]

        # Start loading
        async with self._load_semaphore:
            load_task = asyncio.create_task(self._load_and_cache(
                cache_key, loader_func, **kwargs
            ))
            self._pending_loads[cache_key] = load_task

            try:
                result = await load_task
                return result
            finally:
                self._pending_loads.pop(cache_key, None)

    async def _load_and_cache(self, cache_key: str, loader_func, **kwargs) -> Dict[str, Any]:
        """Internal method to load and cache component"""
        try:
            start_time = time.time()
            component_data = await loader_func(**kwargs)
            load_time = time.time() - start_time

            logger.debug(f"Component loaded in {load_time:.3f}s")

            # Cache the result
            await self.cache.set(cache_key, component_data, ttl=1800)  # 30 min TTL

            return component_data
        except Exception as e:
            logger.error(f"Lazy loading failed for {cache_key}: {e}")
            # Return minimal error component
            return {
                "id": str(uuid.uuid4()),
                "type": "text",
                "content": "Loading failed",
                "font_style": "caption",
                "color": "red"
            }

class PerformanceMonitor:
    """Monitor and track performance metrics"""

    def __init__(self):
        self.metrics = {}
        self.start_times = {}

    def start_timing(self, operation: str, identifier: str = "default"):
        """Start timing an operation"""
        key = f"{operation}:{identifier}"
        self.start_times[key] = time.time()

    def end_timing(self, operation: str, identifier: str = "default") -> float:
        """End timing and record duration"""
        key = f"{operation}:{identifier}"
        start_time = self.start_times.pop(key, None)
        if start_time:
            duration = time.time() - start_time

            if operation not in self.metrics:
                self.metrics[operation] = []

            self.metrics[operation].append({
                "identifier": identifier,
                "duration": duration,
                "timestamp": datetime.now().isoformat()
            })

            return duration
        return 0.0

    def get_average_duration(self, operation: str) -> float:
        """Get average duration for an operation"""
        if operation in self.metrics and self.metrics[operation]:
            durations = [m["duration"] for m in self.metrics[operation]]
            return sum(durations) / len(durations)
        return 0.0

    def get_performance_report(self) -> Dict[str, Any]:
        """Generate performance report"""
        report = {}
        for operation, measurements in self.metrics.items():
            if measurements:
                durations = [m["duration"] for m in measurements]
                report[operation] = {
                    "count": len(measurements),
                    "avg_duration": sum(durations) / len(durations),
                    "min_duration": min(durations),
                    "max_duration": max(durations),
                    "total_time": sum(durations)
                }
        return report

# Global instances
lazy_loader = LazyLoader()
performance_monitor = PerformanceMonitor()

# Optimized cache utilities for specific use cases
class CourseDataCache:
    """Specialized caching for course data"""

    @staticmethod
    @cache_result(CacheKeys.COURSE_DATA, ttl=7200)  # 2 hours
    async def get_course_data(course_id: str) -> Optional[Dict[str, Any]]:
        """This will be implemented by the actual course service"""
        pass

    @staticmethod
    @cache_result(CacheKeys.USER_PROGRESS, ttl=300)  # 5 minutes
    async def get_user_progress(user_id: str, course_id: str) -> Optional[Dict[str, Any]]:
        """This will be implemented by the progress service"""
        pass

class UILayoutCache:
    """Specialized caching for UI layouts"""

    @staticmethod
    @cache_result(CacheKeys.UI_LAYOUT, ttl=1800)  # 30 minutes
    async def get_ui_layout(layout_type: str, **params) -> Optional[Dict[str, Any]]:
        """This will be implemented by the UI assembly service"""
        pass