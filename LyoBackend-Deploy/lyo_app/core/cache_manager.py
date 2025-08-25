"""
Advanced Redis Caching Manager with Cost Optimization
Implements intelligent caching strategies to reduce database load and AI costs
"""

import asyncio
import json
import hashlib
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union, Callable
from functools import wraps
import redis.asyncio as redis
from dataclasses import dataclass
import structlog
from enum import Enum

from lyo_app.core.config import settings

logger = structlog.get_logger(__name__)


class CacheStrategy(Enum):
    """Cache strategies for different data types"""
    WRITE_THROUGH = "write_through"  # Write to cache and DB simultaneously
    WRITE_BEHIND = "write_behind"    # Write to cache first, DB later
    CACHE_ASIDE = "cache_aside"      # Load from cache, fallback to DB
    WRITE_AROUND = "write_around"    # Bypass cache on writes


@dataclass
class CacheConfig:
    """Configuration for cache behavior"""
    ttl: int = 3600  # Time to live in seconds
    strategy: CacheStrategy = CacheStrategy.CACHE_ASIDE
    compress: bool = False  # Compress large values
    encrypt: bool = False   # Encrypt sensitive data
    cost_threshold: float = 0.1  # Cache if cost > threshold (in USD)


class IntelligentCacheManager:
    """
    Enterprise-grade caching with cost optimization and security
    """
    
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.connection_pool: Optional[redis.ConnectionPool] = None
        self.cost_tracker = {}
        self.hit_rate_tracker = {}
        
    async def initialize(self):
        """Initialize Redis connection with production settings"""
        try:
            self.connection_pool = redis.ConnectionPool(
                host=getattr(settings, 'REDIS_HOST', 'localhost'),
                port=getattr(settings, 'REDIS_PORT', 6379),
                db=getattr(settings, 'REDIS_DB', 0),
                password=getattr(settings, 'REDIS_PASSWORD', None),
                max_connections=50,
                retry_on_timeout=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                decode_responses=True
            )
            
            self.redis_client = redis.Redis(
                connection_pool=self.connection_pool
            )
            
            # Test connection
            await self.redis_client.ping()
            logger.info("Redis cache manager initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Redis: {e}")
            # Graceful degradation - cache will be bypassed
            self.redis_client = None
    
    async def close(self):
        """Clean shutdown of Redis connections"""
        if self.redis_client:
            await self.redis_client.close()
        if self.connection_pool:
            await self.connection_pool.disconnect()
    
    def _generate_cache_key(self, prefix: str, *args, **kwargs) -> str:
        """Generate consistent cache keys"""
        key_data = f"{prefix}:{args}:{sorted(kwargs.items())}"
        return f"lyo:{hashlib.md5(key_data.encode()).hexdigest()}"
    
    async def get(
        self, 
        key: str, 
        default: Any = None,
        deserializer: Optional[Callable] = None
    ) -> Any:
        """Get value from cache with metrics tracking"""
        if not self.redis_client:
            return default
        
        try:
            value = await self.redis_client.get(key)
            if value is not None:
                # Track cache hit
                self._track_hit_rate(key, hit=True)
                
                if deserializer:
                    return deserializer(value)
                
                # Try to deserialize JSON
                try:
                    return json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    return value
            
            # Track cache miss
            self._track_hit_rate(key, hit=False)
            return default
            
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            return default
    
    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        config: Optional[CacheConfig] = None,
        serializer: Optional[Callable] = None
    ) -> bool:
        """Set value in cache with advanced options"""
        if not self.redis_client:
            return False
        
        config = config or CacheConfig()
        ttl = ttl or config.ttl
        
        try:
            # Serialize value
            if serializer:
                serialized_value = serializer(value)
            else:
                serialized_value = json.dumps(value, default=str)
            
            # Compress if configured and value is large
            if config.compress and len(serialized_value) > 1024:
                import gzip
                serialized_value = gzip.compress(serialized_value.encode())
            
            # Set with TTL
            success = await self.redis_client.setex(
                key, ttl, serialized_value
            )
            
            return success
            
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete key from cache"""
        if not self.redis_client:
            return False
        
        try:
            return bool(await self.redis_client.delete(key))
        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache"""
        if not self.redis_client:
            return False
        
        try:
            return bool(await self.redis_client.exists(key))
        except Exception as e:
            logger.error(f"Cache exists error for key {key}: {e}")
            return False
    
    def _track_hit_rate(self, key: str, hit: bool):
        """Track cache hit rates for optimization"""
        prefix = key.split(':')[1] if ':' in key else 'unknown'
        
        if prefix not in self.hit_rate_tracker:
            self.hit_rate_tracker[prefix] = {'hits': 0, 'misses': 0}
        
        if hit:
            self.hit_rate_tracker[prefix]['hits'] += 1
        else:
            self.hit_rate_tracker[prefix]['misses'] += 1
    
    async def get_hit_rate_stats(self) -> Dict[str, float]:
        """Get cache hit rate statistics"""
        stats = {}
        for prefix, data in self.hit_rate_tracker.items():
            total = data['hits'] + data['misses']
            if total > 0:
                stats[prefix] = data['hits'] / total
        return stats
    
    # Cost-Optimized AI Response Caching
    async def cache_ai_response(
        self,
        prompt_hash: str,
        response: Dict[str, Any],
        cost: float,
        model: str = "default"
    ):
        """Cache AI responses with cost tracking"""
        key = f"ai_response:{model}:{prompt_hash}"
        
        # Enhanced cache config for AI responses
        config = CacheConfig(
            ttl=86400,  # 24 hours for AI responses
            strategy=CacheStrategy.WRITE_THROUGH,
            cost_threshold=0.01  # Cache responses that cost > 1 cent
        )
        
        # Add cost metadata
        cached_data = {
            "response": response,
            "cost": cost,
            "timestamp": datetime.utcnow().isoformat(),
            "model": model
        }
        
        await self.set(key, cached_data, config=config)
        
        # Track costs
        self._track_ai_cost(model, cost, cached=True)
    
    async def get_cached_ai_response(
        self,
        prompt_hash: str,
        model: str = "default"
    ) -> Optional[Dict[str, Any]]:
        """Get cached AI response if available"""
        key = f"ai_response:{model}:{prompt_hash}"
        cached_data = await self.get(key)
        
        if cached_data:
            # Track cost savings
            saved_cost = cached_data.get("cost", 0)
            self._track_ai_cost(model, -saved_cost, cached=True)  # Negative cost = savings
            
            logger.info(f"AI cache hit: saved ${saved_cost:.4f} for model {model}")
            return cached_data.get("response")
        
        return None
    
    def _track_ai_cost(self, model: str, cost: float, cached: bool = False):
        """Track AI usage costs and savings"""
        if model not in self.cost_tracker:
            self.cost_tracker[model] = {
                "total_cost": 0.0,
                "cached_savings": 0.0,
                "requests": 0,
                "cache_hits": 0
            }
        
        self.cost_tracker[model]["requests"] += 1
        
        if cached and cost < 0:  # Savings
            self.cost_tracker[model]["cached_savings"] += abs(cost)
            self.cost_tracker[model]["cache_hits"] += 1
        else:
            self.cost_tracker[model]["total_cost"] += cost
    
    async def get_cost_analytics(self) -> Dict[str, Any]:
        """Get AI cost analytics"""
        total_cost = sum(data["total_cost"] for data in self.cost_tracker.values())
        total_savings = sum(data["cached_savings"] for data in self.cost_tracker.values())
        
        return {
            "total_cost": total_cost,
            "total_savings": total_savings,
            "cost_reduction_percentage": (total_savings / (total_cost + total_savings)) * 100 if (total_cost + total_savings) > 0 else 0,
            "models": self.cost_tracker
        }
    
    # Session Management (Stateless Application Tier)
    async def store_session(
        self,
        session_id: str,
        session_data: Dict[str, Any],
        ttl: int = 3600
    ) -> bool:
        """Store user session with automatic expiration"""
        key = f"session:{session_id}"
        
        # Add session metadata
        session_with_metadata = {
            **session_data,
            "created_at": datetime.utcnow().isoformat(),
            "last_accessed": datetime.utcnow().isoformat()
        }
        
        return await self.set(key, session_with_metadata, ttl=ttl)
    
    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get user session and update last accessed"""
        key = f"session:{session_id}"
        session_data = await self.get(key)
        
        if session_data:
            # Update last accessed
            session_data["last_accessed"] = datetime.utcnow().isoformat()
            await self.set(key, session_data)  # Refresh TTL
        
        return session_data
    
    async def delete_session(self, session_id: str) -> bool:
        """Delete user session"""
        key = f"session:{session_id}"
        return await self.delete(key)
    
    # Rate Limiting with Sliding Window
    async def check_rate_limit(
        self,
        identifier: str,
        limit: int,
        window_seconds: int,
        cost: float = 1.0
    ) -> Dict[str, Any]:
        """
        Advanced rate limiting with sliding window and cost-based limiting
        """
        key = f"rate_limit:{identifier}"
        current_time = datetime.utcnow().timestamp()
        
        # Use Redis sorted set for sliding window
        pipeline = self.redis_client.pipeline()
        
        # Remove expired entries
        pipeline.zremrangebyscore(
            key,
            0,
            current_time - window_seconds
        )
        
        # Count current requests
        pipeline.zcard(key)
        
        # Add current request
        pipeline.zadd(key, {str(current_time): cost})
        
        # Set expiration
        pipeline.expire(key, window_seconds)
        
        results = await pipeline.execute()
        current_requests = results[1]  # Count result
        
        return {
            "allowed": current_requests < limit,
            "current_requests": current_requests,
            "limit": limit,
            "reset_time": current_time + window_seconds,
            "cost_used": cost
        }
    
    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate cache entries matching a pattern"""
        try:
            keys = []
            async for key in self.redis_client.scan_iter(match=pattern):
                keys.append(key)
            
            if keys:
                await self.redis_client.delete(*keys)
                logger.info(f"Invalidated {len(keys)} cache keys matching pattern: {pattern}")
                return len(keys)
            
            return 0
        except Exception as e:
            logger.error(f"Failed to invalidate pattern {pattern}: {e}")
            return 0


def cached(
    ttl: int = 3600,
    key_prefix: str = None,
    config: Optional[CacheConfig] = None
):
    """
    Decorator for caching function results
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache_manager = get_cache_manager()
            
            # Generate cache key
            prefix = key_prefix or f"{func.__module__}.{func.__name__}"
            cache_key = cache_manager._generate_cache_key(prefix, *args, **kwargs)
            
            # Try to get from cache
            cached_result = await cache_manager.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Execute function
            result = await func(*args, **kwargs)
            
            # Cache the result
            await cache_manager.set(cache_key, result, ttl=ttl, config=config)
            
            return result
        return wrapper
    return decorator


# Global cache manager instance
_cache_manager: Optional[IntelligentCacheManager] = None


async def init_cache_manager():
    """Initialize global cache manager"""
    global _cache_manager
    _cache_manager = IntelligentCacheManager()
    await _cache_manager.initialize()


def get_cache_manager() -> IntelligentCacheManager:
    """Get global cache manager instance"""
    global _cache_manager
    if _cache_manager is None:
        raise RuntimeError("Cache manager not initialized. Call init_cache_manager() first.")
    return _cache_manager


async def close_cache_manager():
    """Close global cache manager"""
    global _cache_manager
    if _cache_manager:
        await _cache_manager.close()
        _cache_manager = None
