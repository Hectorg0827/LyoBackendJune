"""
Market-Ready Redis Manager V2
============================

Production-grade Redis integration for Google Memorystore.
Supports connection pooling, health checks, and failover.
"""

import asyncio
import time
from typing import Optional, Any, Dict, List, Union
import json
import pickle
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from redis.asyncio import ConnectionPool
from redis.exceptions import RedisError, ConnectionError as RedisConnectionError

from lyo_app.core.config_v2 import settings
from lyo_app.core.logging_v2 import logger


class RedisManager:
    """Centralized Redis management with connection pooling and health checks."""
    
    def __init__(self):
        self.pool: Optional[ConnectionPool] = None
        self.redis: Optional[aioredis.Redis] = None
        self._is_initialized = False
        self._circuit_breaker_failures = 0
        self._circuit_breaker_last_failure = 0
        self._circuit_breaker_threshold = 5
        self._circuit_breaker_timeout = 60  # seconds
    
    async def initialize(self):
        """Initialize Redis connection pool."""
        try:
            logger.info("🔄 Initializing Redis connections...")
            
            # Create connection pool
            self.pool = ConnectionPool.from_url(
                str(settings.REDIS_URL),
                max_connections=settings.REDIS_POOL_SIZE,
                retry_on_timeout=True,
                socket_keepalive=True,
                socket_keepalive_options={
                    1: 1,  # TCP_KEEPIDLE
                    2: 3,  # TCP_KEEPINTVL
                    3: 5,  # TCP_KEEPCNT
                } if not settings.is_production() else {},
                decode_responses=False,  # We'll handle encoding manually
            )
            
            # Create Redis client
            self.redis = aioredis.Redis(connection_pool=self.pool)
            
            # Test connection
            await self._test_connection()
            
            self._is_initialized = True
            logger.info("✅ Redis connections initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Redis initialization failed: {e}")
            # Don't raise - Redis should be optional for basic functionality
            self._is_initialized = False
    
    async def shutdown(self):
        """Cleanup Redis connections."""
        if self.redis:
            logger.info("🔄 Shutting down Redis connections...")
            await self.redis.close()
            if self.pool:
                await self.pool.disconnect()
            self._is_initialized = False
            logger.info("✅ Redis connections closed")
    
    async def health_check(self) -> bool:
        """Quick Redis health check."""
        if not self._is_initialized:
            return False
        
        try:
            result = await self.redis.ping()
            return result is True
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False
    
    async def ready_check(self) -> bool:
        """Comprehensive Redis readiness check."""
        if not self._is_initialized:
            return False
        
        try:
            start_time = time.time()
            
            # Test basic operations
            test_key = "health_check_test"
            await self.redis.set(test_key, "test_value", ex=60)
            value = await self.redis.get(test_key)
            await self.redis.delete(test_key)
            
            if value != b"test_value":
                return False
            
            # Check response time
            response_time = time.time() - start_time
            if response_time > 1.0:  # 1 second threshold
                logger.warning(f"Redis response time high: {response_time:.2f}s")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Redis readiness check failed: {e}")
            return False
    
    async def _test_connection(self):
        """Test initial Redis connection."""
        try:
            info = await self.redis.info()
            version = info.get('redis_version', 'unknown')
            logger.info(f"Connected to Redis: {version}")
            
        except Exception as e:
            logger.error(f"Redis connection test failed: {e}")
            raise
    
    def _is_circuit_breaker_open(self) -> bool:
        """Check if circuit breaker is open."""
        if self._circuit_breaker_failures < self._circuit_breaker_threshold:
            return False
        
        if time.time() - self._circuit_breaker_last_failure > self._circuit_breaker_timeout:
            # Reset circuit breaker
            self._circuit_breaker_failures = 0
            return False
        
        return True
    
    def _record_failure(self):
        """Record circuit breaker failure."""
        self._circuit_breaker_failures += 1
        self._circuit_breaker_last_failure = time.time()
    
    def _record_success(self):
        """Record circuit breaker success."""
        self._circuit_breaker_failures = 0
    
    async def _execute_with_circuit_breaker(self, operation, *args, **kwargs):
        """Execute Redis operation with circuit breaker pattern."""
        if not self._is_initialized or self._is_circuit_breaker_open():
            raise RedisError("Redis unavailable (circuit breaker open)")
        
        try:
            result = await operation(*args, **kwargs)
            self._record_success()
            return result
        except Exception as e:
            self._record_failure()
            logger.error(f"Redis operation failed: {e}")
            raise
    
    # Cache Operations
    async def get(self, key: str, default: Any = None) -> Any:
        """Get value from Redis with deserialization."""
        try:
            raw_value = await self._execute_with_circuit_breaker(self.redis.get, key)
            if raw_value is None:
                return default
            
            # Try JSON first, then pickle
            try:
                return json.loads(raw_value.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return pickle.loads(raw_value)
                
        except Exception as e:
            logger.error(f"Redis GET failed for key {key}: {e}")
            return default
    
    async def set(self, key: str, value: Any, ex: Optional[int] = None, nx: bool = False) -> bool:
        """Set value in Redis with serialization."""
        try:
            # Try JSON first, then pickle
            try:
                serialized_value = json.dumps(value).encode('utf-8')
            except (TypeError, ValueError):
                serialized_value = pickle.dumps(value)
            
            result = await self._execute_with_circuit_breaker(
                self.redis.set, key, serialized_value, ex=ex, nx=nx
            )
            return result is True
            
        except Exception as e:
            logger.error(f"Redis SET failed for key {key}: {e}")
            return False
    
    async def delete(self, *keys: str) -> int:
        """Delete keys from Redis."""
        try:
            return await self._execute_with_circuit_breaker(self.redis.delete, *keys)
        except Exception as e:
            logger.error(f"Redis DELETE failed for keys {keys}: {e}")
            return 0
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in Redis."""
        try:
            result = await self._execute_with_circuit_breaker(self.redis.exists, key)
            return result > 0
        except Exception as e:
            logger.error(f"Redis EXISTS failed for key {key}: {e}")
            return False
    
    async def expire(self, key: str, seconds: int) -> bool:
        """Set expiration for key."""
        try:
            result = await self._execute_with_circuit_breaker(self.redis.expire, key, seconds)
            return result is True
        except Exception as e:
            logger.error(f"Redis EXPIRE failed for key {key}: {e}")
            return False
    
    async def incr(self, key: str, amount: int = 1) -> Optional[int]:
        """Increment counter in Redis."""
        try:
            return await self._execute_with_circuit_breaker(self.redis.incr, key, amount)
        except Exception as e:
            logger.error(f"Redis INCR failed for key {key}: {e}")
            return None
    
    async def decr(self, key: str, amount: int = 1) -> Optional[int]:
        """Decrement counter in Redis."""
        try:
            return await self._execute_with_circuit_breaker(self.redis.decr, key, amount)
        except Exception as e:
            logger.error(f"Redis DECR failed for key {key}: {e}")
            return None
    
    # List Operations
    async def lpush(self, key: str, *values: Any) -> Optional[int]:
        """Push values to the left of a list."""
        try:
            serialized_values = []
            for value in values:
                try:
                    serialized_values.append(json.dumps(value).encode('utf-8'))
                except (TypeError, ValueError):
                    serialized_values.append(pickle.dumps(value))
            
            return await self._execute_with_circuit_breaker(
                self.redis.lpush, key, *serialized_values
            )
        except Exception as e:
            logger.error(f"Redis LPUSH failed for key {key}: {e}")
            return None
    
    async def rpop(self, key: str) -> Any:
        """Pop value from the right of a list."""
        try:
            raw_value = await self._execute_with_circuit_breaker(self.redis.rpop, key)
            if raw_value is None:
                return None
            
            # Try JSON first, then pickle
            try:
                return json.loads(raw_value.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return pickle.loads(raw_value)
                
        except Exception as e:
            logger.error(f"Redis RPOP failed for key {key}: {e}")
            return None
    
    async def llen(self, key: str) -> int:
        """Get length of a list."""
        try:
            return await self._execute_with_circuit_breaker(self.redis.llen, key)
        except Exception as e:
            logger.error(f"Redis LLEN failed for key {key}: {e}")
            return 0
    
    # Set Operations
    async def sadd(self, key: str, *values: Any) -> Optional[int]:
        """Add values to a set."""
        try:
            serialized_values = []
            for value in values:
                try:
                    serialized_values.append(json.dumps(value).encode('utf-8'))
                except (TypeError, ValueError):
                    serialized_values.append(pickle.dumps(value))
            
            return await self._execute_with_circuit_breaker(
                self.redis.sadd, key, *serialized_values
            )
        except Exception as e:
            logger.error(f"Redis SADD failed for key {key}: {e}")
            return None
    
    async def sismember(self, key: str, value: Any) -> bool:
        """Check if value is member of a set."""
        try:
            # Serialize value for comparison
            try:
                serialized_value = json.dumps(value).encode('utf-8')
            except (TypeError, ValueError):
                serialized_value = pickle.dumps(value)
            
            result = await self._execute_with_circuit_breaker(
                self.redis.sismember, key, serialized_value
            )
            return result is True
        except Exception as e:
            logger.error(f"Redis SISMEMBER failed for key {key}: {e}")
            return False
    
    # Hash Operations
    async def hset(self, key: str, mapping: Dict[str, Any]) -> Optional[int]:
        """Set hash fields."""
        try:
            serialized_mapping = {}
            for field, value in mapping.items():
                try:
                    serialized_mapping[field] = json.dumps(value).encode('utf-8')
                except (TypeError, ValueError):
                    serialized_mapping[field] = pickle.dumps(value)
            
            return await self._execute_with_circuit_breaker(
                self.redis.hset, key, mapping=serialized_mapping
            )
        except Exception as e:
            logger.error(f"Redis HSET failed for key {key}: {e}")
            return None
    
    async def hget(self, key: str, field: str) -> Any:
        """Get hash field value."""
        try:
            raw_value = await self._execute_with_circuit_breaker(
                self.redis.hget, key, field
            )
            if raw_value is None:
                return None
            
            # Try JSON first, then pickle
            try:
                return json.loads(raw_value.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return pickle.loads(raw_value)
                
        except Exception as e:
            logger.error(f"Redis HGET failed for key {key}, field {field}: {e}")
            return None
    
    # Pub/Sub Operations
    async def publish(self, channel: str, message: Any) -> Optional[int]:
        """Publish message to channel."""
        try:
            # Serialize message
            try:
                serialized_message = json.dumps(message).encode('utf-8')
            except (TypeError, ValueError):
                serialized_message = pickle.dumps(message)
            
            return await self._execute_with_circuit_breaker(
                self.redis.publish, channel, serialized_message
            )
        except Exception as e:
            logger.error(f"Redis PUBLISH failed for channel {channel}: {e}")
            return None
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get Redis statistics for monitoring."""
        try:
            info = await self._execute_with_circuit_breaker(self.redis.info)
            
            return {
                "version": info.get("redis_version", "unknown"),
                "connected_clients": info.get("connected_clients", 0),
                "used_memory": info.get("used_memory", 0),
                "used_memory_human": info.get("used_memory_human", "0B"),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "total_commands_processed": info.get("total_commands_processed", 0),
            }
        except Exception as e:
            logger.error(f"Redis stats failed: {e}")
            return {}


# Global Redis manager instance
redis_manager = RedisManager()


# Convenience functions
async def cache_get(key: str, default: Any = None) -> Any:
    """Get value from cache."""
    return await redis_manager.get(key, default)


async def cache_set(key: str, value: Any, ttl: Optional[int] = None) -> bool:
    """Set value in cache."""
    return await redis_manager.set(key, value, ex=ttl)


async def cache_delete(*keys: str) -> int:
    """Delete keys from cache."""
    return await redis_manager.delete(*keys)
