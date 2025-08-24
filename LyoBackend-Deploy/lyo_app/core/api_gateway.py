"""
Enhanced API Gateway with Rate Limiting and Caching
Provides advanced API management with comprehensive resilience features
"""

import asyncio
import time
import hashlib
import json
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from collections import defaultdict, deque
from contextlib import asynccontextmanager
import aioredis
import logging
from functools import wraps
from lyo_app.core.config import settings

logger = logging.getLogger(__name__)

@dataclass
class RateLimitConfig:
    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    requests_per_day: int = 10000
    burst_allowance: int = 10  # Extra requests allowed in burst

@dataclass
class CacheConfig:
    default_ttl: int = 300  # 5 minutes
    max_entries: int = 10000
    compress_large_responses: bool = True
    compression_threshold: int = 1024  # bytes

class MemoryRateLimiter:
    """In-memory rate limiter with sliding window"""
    
    def __init__(self, config: RateLimitConfig):
        self.config = config
        self.request_history: Dict[str, deque] = defaultdict(deque)
        self.cleanup_interval = 300  # 5 minutes
        self.last_cleanup = time.time()
    
    def is_allowed(self, identifier: str, endpoint: str = "default") -> tuple[bool, Dict[str, Any]]:
        """Check if request is allowed under rate limits"""
        
        now = time.time()
        key = f"{identifier}:{endpoint}"
        
        # Clean up old entries periodically
        if now - self.last_cleanup > self.cleanup_interval:
            self._cleanup_old_entries()
            self.last_cleanup = now
        
        # Get request history for this key
        history = self.request_history[key]
        
        # Remove requests older than 1 day
        while history and now - history[0] > 86400:
            history.popleft()
        
        # Count requests in different time windows
        minute_count = sum(1 for t in history if now - t <= 60)
        hour_count = sum(1 for t in history if now - t <= 3600)
        day_count = len(history)
        
        # Check limits
        limits_info = {
            "requests_this_minute": minute_count,
            "requests_this_hour": hour_count,
            "requests_this_day": day_count,
            "limits": {
                "per_minute": self.config.requests_per_minute,
                "per_hour": self.config.requests_per_hour,
                "per_day": self.config.requests_per_day
            },
            "reset_times": {
                "minute_reset": int(now + (60 - (now % 60))),
                "hour_reset": int(now + (3600 - (now % 3600))),
                "day_reset": int(now + (86400 - (now % 86400)))
            }
        }
        
        # Check if any limit is exceeded
        if (minute_count >= self.config.requests_per_minute or
            hour_count >= self.config.requests_per_hour or
            day_count >= self.config.requests_per_day):
            
            # Allow burst if within allowance
            if minute_count < self.config.requests_per_minute + self.config.burst_allowance:
                history.append(now)
                limits_info["burst_used"] = True
                return True, limits_info
            
            limits_info["rate_limited"] = True
            return False, limits_info
        
        # Add request to history
        history.append(now)
        return True, limits_info
    
    def _cleanup_old_entries(self):
        """Clean up old request history entries"""
        now = time.time()
        keys_to_remove = []
        
        for key, history in self.request_history.items():
            # Remove requests older than 1 day
            while history and now - history[0] > 86400:
                history.popleft()
            
            # Remove empty histories
            if not history:
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self.request_history[key]
        
        logger.debug(f"Cleaned up {len(keys_to_remove)} empty rate limit histories")

class ResponseCache:
    """High-performance response cache with compression"""
    
    def __init__(self, config: CacheConfig):
        self.config = config
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.access_times: Dict[str, float] = {}
        self.redis_client: Optional[aioredis.Redis] = None
    
    async def initialize_redis(self):
        """Initialize Redis connection if available"""
        try:
            if hasattr(settings, 'redis_url') and settings.redis_url:
                self.redis_client = await aioredis.from_url(
                    settings.redis_url,
                    encoding="utf-8",
                    decode_responses=False  # We'll handle encoding ourselves
                )
                logger.info("Redis cache initialized")
        except Exception as e:
            logger.warning(f"Redis initialization failed, using memory cache: {e}")
    
    async def get(self, key: str) -> Optional[Any]:
        """Get cached response"""
        
        # Try Redis first if available
        if self.redis_client:
            try:
                cached_data = await self.redis_client.get(f"cache:{key}")
                if cached_data:
                    data = json.loads(cached_data)
                    if time.time() - data["timestamp"] < data["ttl"]:
                        logger.debug(f"Cache hit (Redis): {key}")
                        return data["response"]
                    else:
                        await self.redis_client.delete(f"cache:{key}")
            except Exception as e:
                logger.warning(f"Redis cache get error: {e}")
        
        # Fallback to memory cache
        if key in self.cache:
            cached_item = self.cache[key]
            if time.time() - cached_item["timestamp"] < cached_item["ttl"]:
                self.access_times[key] = time.time()
                logger.debug(f"Cache hit (memory): {key}")
                return cached_item["response"]
            else:
                del self.cache[key]
                if key in self.access_times:
                    del self.access_times[key]
        
        return None
    
    async def set(self, key: str, response: Any, ttl: Optional[int] = None) -> bool:
        """Set cached response"""
        
        if ttl is None:
            ttl = self.config.default_ttl
        
        cached_item = {
            "response": response,
            "timestamp": time.time(),
            "ttl": ttl
        }
        
        # Try Redis first if available
        if self.redis_client:
            try:
                await self.redis_client.setex(
                    f"cache:{key}",
                    ttl,
                    json.dumps(cached_item, default=str)
                )
                logger.debug(f"Cache set (Redis): {key}")
                return True
            except Exception as e:
                logger.warning(f"Redis cache set error: {e}")
        
        # Fallback to memory cache
        # Check if we need to evict entries
        if len(self.cache) >= self.config.max_entries:
            self._evict_lru_entries()
        
        self.cache[key] = cached_item
        self.access_times[key] = time.time()
        logger.debug(f"Cache set (memory): {key}")
        return True
    
    def _evict_lru_entries(self):
        """Evict least recently used entries"""
        if not self.access_times:
            return
        
        # Remove 10% of entries (LRU)
        num_to_remove = max(1, len(self.cache) // 10)
        lru_keys = sorted(self.access_times.items(), key=lambda x: x[1])[:num_to_remove]
        
        for key, _ in lru_keys:
            if key in self.cache:
                del self.cache[key]
            del self.access_times[key]
        
        logger.debug(f"Evicted {len(lru_keys)} LRU cache entries")
    
    def get_cache_key(self, method: str, url: str, headers: Dict[str, str], body: str = "") -> str:
        """Generate cache key for request"""
        # Include relevant headers that might affect response
        relevant_headers = {k: v for k, v in headers.items() 
                          if k.lower() in ['accept', 'accept-language', 'authorization']}
        
        cache_input = f"{method}:{url}:{json.dumps(relevant_headers, sort_keys=True)}:{body}"
        return hashlib.sha256(cache_input.encode()).hexdigest()[:32]
    
    async def clear_pattern(self, pattern: str):
        """Clear cache entries matching pattern"""
        if self.redis_client:
            try:
                keys = await self.redis_client.keys(f"cache:*{pattern}*")
                if keys:
                    await self.redis_client.delete(*keys)
                    logger.info(f"Cleared {len(keys)} Redis cache entries matching pattern: {pattern}")
            except Exception as e:
                logger.warning(f"Redis pattern clear error: {e}")
        
        # Clear from memory cache
        keys_to_remove = [k for k in self.cache.keys() if pattern in k]
        for key in keys_to_remove:
            del self.cache[key]
            if key in self.access_times:
                del self.access_times[key]
        
        logger.info(f"Cleared {len(keys_to_remove)} memory cache entries matching pattern: {pattern}")

class APIGateway:
    """Enhanced API Gateway with rate limiting, caching, and monitoring"""
    
    def __init__(self):
        self.rate_limiter = MemoryRateLimiter(RateLimitConfig())
        self.cache = ResponseCache(CacheConfig())
        self.request_metrics: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "avg_response_time": 0,
            "last_request_time": 0,
            "rate_limited_requests": 0
        })
        self.circuit_breakers: Dict[str, Any] = {}
        self.middleware_stack: List[Callable] = []
    
    async def initialize(self):
        """Initialize the API Gateway"""
        await self.cache.initialize_redis()
        logger.info("API Gateway initialized")
    
    def add_middleware(self, middleware: Callable):
        """Add middleware to the processing stack"""
        self.middleware_stack.append(middleware)
    
    async def process_request(
        self,
        method: str,
        endpoint: str,
        handler: Callable,
        request_data: Dict[str, Any],
        user_id: Optional[str] = None,
        use_cache: bool = True,
        cache_ttl: Optional[int] = None
    ) -> Dict[str, Any]:
        """Process API request with all gateway features"""
        
        start_time = time.time()
        request_id = f"{method}:{endpoint}:{int(start_time)}"
        
        try:
            # Apply middleware
            for middleware in self.middleware_stack:
                request_data = await self._apply_middleware(middleware, request_data)
            
            # Rate limiting
            rate_limit_key = user_id or request_data.get("client_ip", "anonymous")
            is_allowed, rate_info = self.rate_limiter.is_allowed(rate_limit_key, endpoint)
            
            if not is_allowed:
                self._update_metrics(endpoint, "rate_limited", start_time)
                return {
                    "error": "Rate limit exceeded",
                    "rate_limit_info": rate_info,
                    "retry_after": rate_info["reset_times"]["minute_reset"],
                    "status_code": 429
                }
            
            # Check cache
            cache_key = None
            if use_cache and method in ["GET"]:
                cache_key = self.cache.get_cache_key(
                    method, endpoint, 
                    request_data.get("headers", {}),
                    json.dumps(request_data.get("params", {}), sort_keys=True)
                )
                
                cached_response = await self.cache.get(cache_key)
                if cached_response:
                    self._update_metrics(endpoint, "cached", start_time)
                    cached_response["cached"] = True
                    cached_response["rate_limit_info"] = rate_info
                    return cached_response
            
            # Execute handler
            response = await handler(**request_data)
            
            # Cache successful responses
            if (use_cache and cache_key and 
                response.get("status_code", 200) == 200):
                await self.cache.set(cache_key, response, cache_ttl)
            
            # Add metadata
            response["rate_limit_info"] = rate_info
            response["request_id"] = request_id
            response["processing_time"] = time.time() - start_time
            
            self._update_metrics(endpoint, "success", start_time)
            return response
            
        except Exception as e:
            self._update_metrics(endpoint, "error", start_time)
            logger.error(f"API Gateway error for {endpoint}: {e}")
            
            return {
                "error": str(e),
                "endpoint": endpoint,
                "request_id": request_id,
                "status_code": 500
            }
    
    async def _apply_middleware(self, middleware: Callable, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply middleware function to request data"""
        try:
            if asyncio.iscoroutinefunction(middleware):
                return await middleware(request_data)
            else:
                return middleware(request_data)
        except Exception as e:
            logger.warning(f"Middleware error: {e}")
            return request_data
    
    def _update_metrics(self, endpoint: str, result: str, start_time: float):
        """Update request metrics"""
        metrics = self.request_metrics[endpoint]
        metrics["total_requests"] += 1
        metrics["last_request_time"] = time.time()
        
        if result == "success" or result == "cached":
            metrics["successful_requests"] += 1
        elif result == "error":
            metrics["failed_requests"] += 1
        elif result == "rate_limited":
            metrics["rate_limited_requests"] += 1
        
        # Update average response time
        processing_time = time.time() - start_time
        if metrics["avg_response_time"] == 0:
            metrics["avg_response_time"] = processing_time
        else:
            metrics["avg_response_time"] = (
                (metrics["avg_response_time"] * (metrics["total_requests"] - 1) + processing_time) 
                / metrics["total_requests"]
            )
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Get comprehensive API metrics"""
        
        total_requests = sum(m["total_requests"] for m in self.request_metrics.values())
        total_successful = sum(m["successful_requests"] for m in self.request_metrics.values())
        total_failed = sum(m["failed_requests"] for m in self.request_metrics.values())
        total_rate_limited = sum(m["rate_limited_requests"] for m in self.request_metrics.values())
        
        return {
            "summary": {
                "total_requests": total_requests,
                "successful_requests": total_successful,
                "failed_requests": total_failed,
                "rate_limited_requests": total_rate_limited,
                "success_rate": (total_successful / total_requests * 100) if total_requests > 0 else 0
            },
            "endpoints": dict(self.request_metrics),
            "cache_stats": {
                "memory_entries": len(self.cache.cache),
                "max_entries": self.cache.config.max_entries,
                "redis_available": self.cache.redis_client is not None
            },
            "rate_limiting": {
                "active_limits": len(self.rate_limiter.request_history),
                "config": {
                    "requests_per_minute": self.rate_limiter.config.requests_per_minute,
                    "requests_per_hour": self.rate_limiter.config.requests_per_hour,
                    "requests_per_day": self.rate_limiter.config.requests_per_day
                }
            }
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Comprehensive health check"""
        
        health_status = {
            "status": "healthy",
            "timestamp": time.time(),
            "components": {}
        }
        
        # Check cache health
        try:
            if self.cache.redis_client:
                await self.cache.redis_client.ping()
                health_status["components"]["redis_cache"] = "healthy"
            else:
                health_status["components"]["memory_cache"] = "healthy"
        except Exception as e:
            health_status["components"]["cache"] = f"unhealthy: {e}"
            health_status["status"] = "degraded"
        
        # Check rate limiter
        try:
            test_allowed, _ = self.rate_limiter.is_allowed("health_check")
            health_status["components"]["rate_limiter"] = "healthy" if test_allowed else "degraded"
        except Exception as e:
            health_status["components"]["rate_limiter"] = f"unhealthy: {e}"
            health_status["status"] = "unhealthy"
        
        return health_status
    
    async def close(self):
        """Clean up resources"""
        if self.cache.redis_client:
            await self.cache.redis_client.close()
        logger.info("API Gateway closed")

# Singleton instance
api_gateway = APIGateway()

# Decorator for easy endpoint protection
def gateway_protected(
    use_cache: bool = True,
    cache_ttl: Optional[int] = None,
    rate_limit_override: Optional[RateLimitConfig] = None
):
    """Decorator to add gateway protection to endpoints"""
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request info
            method = kwargs.get("method", "GET")
            endpoint = f"{func.__module__}.{func.__name__}"
            
            # Process through gateway
            return await api_gateway.process_request(
                method=method,
                endpoint=endpoint,
                handler=func,
                request_data=kwargs,
                use_cache=use_cache,
                cache_ttl=cache_ttl
            )
        
        return wrapper
    return decorator
